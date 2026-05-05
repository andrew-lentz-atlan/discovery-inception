"""Run the chained agent (A) and the mega-agent baseline (B) through the
same customer script, side-by-side, and emit a markdown comparison.

Same model. Same priors. Same customer turns. The point is to isolate
"is decomposition load-bearing?" from "is the model good at discovery?"

Usage:
    cd discovery-inception
    uv run python -m agent.baselines.run_comparison \\
        --script agent/baselines/scripts/scope_creep_5turn.json \\
        --out-dir agent/baselines/results

The chained agent runs against the FastAPI server at localhost:8010
(start it first: uv run uvicorn agent.server:app --port 8010). The
mega-agent runs in-process — same LiteLLM proxy, same model, same priors.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

from agent.baselines.mega_agent import MegaAgentSession  # noqa: E402
from agent.schemas import DiscoverySpec  # noqa: E402
from agent.state import DiscoverySession  # noqa: E402
from agent.v06.orchestrator import run_v06_turn  # noqa: E402

CHAINED_SERVER_URL = os.environ.get("CHAINED_SERVER_URL", "http://localhost:8010")


# ---------------------------------------------------------------------------
# Chained agent client (talks to our running FastAPI server)
# ---------------------------------------------------------------------------

async def chained_create_session(client: httpx.AsyncClient, *, use_case_seed: str, role_id: str | None) -> str:
    payload = {"use_case_seed": use_case_seed, "role_id": role_id}
    r = await client.post(f"{CHAINED_SERVER_URL}/sessions", json=payload, timeout=30.0)
    r.raise_for_status()
    return r.json()["session_id"]


async def chained_turn(client: httpx.AsyncClient, session_id: str, message: str) -> tuple[str, dict]:
    started = time.perf_counter()
    r = await client.post(
        f"{CHAINED_SERVER_URL}/sessions/{session_id}/turn",
        json={"message": message},
        timeout=120.0,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    r.raise_for_status()
    body = r.json()
    return body["agent_message"], {"duration_ms": duration_ms, "raw": body}


async def chained_get_session(client: httpx.AsyncClient, session_id: str) -> dict:
    r = await client.get(f"{CHAINED_SERVER_URL}/sessions/{session_id}", timeout=30.0)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Lightweight metrics over agent responses
# ---------------------------------------------------------------------------

# Customer-specific vocabulary terms from the SoCo onboarding context. If the
# agent uses these, it's mirroring the customer's language; if it invents
# generic alternatives, it's not.
VOCAB_TERMS = [
    "SoCo", "CSM", "CSA", "IE", "Support",
    "success plan", "priority connectors", "presales",
    "metadata bootstrapped", "Phase 2", "scope creep",
    "TTFV", "time-to-first-value",
    "coordination and design brain",
]

# Generic SaaS-org language we DO NOT want — if these show up the agent is
# inventing vocabulary instead of using the customer's.
GENERIC_TERMS = [
    "ops team", "operations team", "leadership team",
    "stakeholder", "key stakeholders", "kpi dashboard",
    "north star metric",
]


def vocab_score(text: str) -> dict:
    """Count uses of customer vocabulary vs generic substitutes."""
    lower = text.lower()
    customer = sum(1 for t in VOCAB_TERMS if t.lower() in lower)
    generic = sum(1 for t in GENERIC_TERMS if t.lower() in lower)
    return {"customer_terms": customer, "generic_terms": generic}


def question_count(text: str) -> int:
    """Number of question marks — proxy for multi-part questions."""
    return text.count("?")


def has_rationale(text: str) -> bool:
    """Heuristic: does the response justify itself in customer-facing terms?

    Looks for cause/explanation language rather than just a question.
    Conservative — false negatives are fine, false positives are the risk.
    """
    lower = text.lower()
    cues = [
        "because", "the reason", "if we don't know", "without knowing",
        "this matters because", "here's why", "without that",
        "to know what to", "so the agent can", "so we can tell",
    ]
    return any(cue in lower for cue in cues)


# ---------------------------------------------------------------------------
# Comparison driver
# ---------------------------------------------------------------------------

async def run_comparison(script_path: Path, out_dir: Path) -> Path:
    script = json.loads(script_path.read_text())
    use_case_seed = script["use_case_seed"]
    role_id = script.get("role_id")
    turns = script["turns"]

    # Set up clients
    base_url = os.environ.get("LITELLM_BASE_URL", "").strip()
    api_key = os.environ.get("LITELLM_API_KEY", "").strip()
    if not base_url or not api_key:
        raise RuntimeError("LITELLM_BASE_URL and LITELLM_API_KEY must be set")
    openai_client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    http_client = httpx.AsyncClient()

    print(f"→ Loading script: {script['name']} ({len(turns)} turns)")
    print(f"  use_case_seed: {use_case_seed}")
    print(f"  role_id: {role_id}")
    print()

    # ---- Start both systems ----
    print("→ Starting chained agent (A) session against running server…")
    session_a = await chained_create_session(http_client, use_case_seed=use_case_seed, role_id=role_id)
    print(f"  session_id: {session_a}")
    print()

    print("→ Starting mega-agent baseline (B) — in-process…")
    session_b = MegaAgentSession(use_case_seed=use_case_seed, role_id=role_id)
    print(f"  system_prompt_chars: {len(session_b.system_prompt)}")
    print()

    print("→ Starting v0.6 hybrid (C) — extractors + mega-agent with tools, in-process…")
    spec_c = DiscoverySpec(use_case_seed=use_case_seed, role_id=role_id)
    session_c = DiscoverySession(spec=spec_c)
    mega_c = MegaAgentSession(use_case_seed=use_case_seed, role_id=role_id)
    print(f"  hybrid session_id: {session_c.session_id}")
    print()

    # ---- Drive all three through the script ----
    rows: list[dict] = []
    for t in turns:
        n = t["n"]
        msg = t["customer"]
        tests = t.get("tests", "")
        print(f"━━━ Turn {n} ━━━")
        print(f"customer: {msg[:120]}{'…' if len(msg) > 120 else ''}")
        print(f"  testing: {tests}")

        # Run A, B, C concurrently — same customer turn
        a_resp_task = chained_turn(http_client, session_a, msg)
        b_resp_task = session_b.turn(openai_client, msg)
        c_resp_task = run_v06_turn(openai_client, session_c, mega_c, msg)
        (a_msg, a_meta), (b_msg, b_meta), (c_turn, c_checklist) = await asyncio.gather(
            a_resp_task, b_resp_task, c_resp_task
        )
        c_msg = c_turn.agent_message or ""
        c_mega_event = next((e for e in c_turn.events if e.sub_agent == "mega_agent"), None)
        c_extractor_events = [e for e in c_turn.events if e.sub_agent != "mega_agent"]

        a_metrics = {
            "duration_ms": a_meta["duration_ms"],
            "response_chars": len(a_msg),
            "question_marks": question_count(a_msg),
            "has_rationale": has_rationale(a_msg),
            "vocab": vocab_score(a_msg),
            "raw_summary": {
                k: a_meta["raw"].get(k)
                for k in ("triage_label", "checklist_missing", "declared_ready")
            },
        }
        b_metrics = {
            "duration_ms": b_meta["duration_ms"],
            "response_chars": len(b_msg),
            "question_marks": question_count(b_msg),
            "has_rationale": has_rationale(b_msg),
            "vocab": vocab_score(b_msg),
            "tokens": {
                "input": b_meta.get("input_tokens"),
                "output": b_meta.get("output_tokens"),
                "total": b_meta.get("total_tokens"),
            },
        }
        # C: total turn duration includes extractors + mega-agent
        c_total_ms = sum(e.duration_ms for e in c_turn.events)
        c_mega_output = c_mega_event.output if c_mega_event else {}
        c_metrics = {
            "duration_ms": c_total_ms,
            "response_chars": len(c_msg),
            "question_marks": question_count(c_msg),
            "has_rationale": has_rationale(c_msg),
            "vocab": vocab_score(c_msg),
            "extractor_events": [
                {"sub_agent": e.sub_agent, "duration_ms": e.duration_ms}
                for e in c_extractor_events
            ],
            "mega_tool_calls": [tc.get("name") for tc in c_mega_output.get("tool_calls", [])],
            "tokens": {
                "input": c_mega_output.get("input_tokens"),
                "output": c_mega_output.get("output_tokens"),
            },
            "triage_label": next(
                (e.output.get("label") for e in c_extractor_events if e.sub_agent == "triage"),
                None,
            ),
        }

        print(f"  A ({a_metrics['duration_ms']}ms, vocab={a_metrics['vocab']['customer_terms']}c/{a_metrics['vocab']['generic_terms']}g): {a_msg[:140]}")
        print(f"  B ({b_metrics['duration_ms']}ms, vocab={b_metrics['vocab']['customer_terms']}c/{b_metrics['vocab']['generic_terms']}g): {b_msg[:140]}")
        print(f"  C ({c_metrics['duration_ms']}ms, vocab={c_metrics['vocab']['customer_terms']}c/{c_metrics['vocab']['generic_terms']}g, tools={c_metrics['mega_tool_calls']}): {c_msg[:140]}")
        print()

        rows.append({
            "n": n, "customer": msg, "tests": tests,
            "a_response": a_msg, "a_metrics": a_metrics,
            "b_response": b_msg, "b_metrics": b_metrics,
            "c_response": c_msg, "c_metrics": c_metrics,
        })

    # ---- Pull both A's and C's structured spec for the artifact ----
    print("→ Fetching chained agent's final state…")
    session_a_final = await chained_get_session(http_client, session_a)
    session_c_final = json.loads(session_c.model_dump_json())

    await http_client.aclose()
    await openai_client.close()

    # ---- Emit artifact ----
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    artifact_path = out_dir / f"{script['name']}_ABC__{timestamp}.md"
    artifact_path.write_text(_render_markdown_abc(script, rows, session_a_final, session_c_final))
    print(f"\n✓ Wrote {artifact_path}")
    return artifact_path


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def _render_markdown_abc(
    script: dict,
    rows: list[dict],
    session_a_final: dict,
    session_c_final: dict,
) -> str:
    lines: list[str] = []
    lines.append("# Comparison: A (chained v0.5) vs B (mega-agent) vs C (v0.6 hybrid)")
    lines.append("")
    lines.append(f"**Script:** `{script['name']}` — {script.get('description','')}")
    lines.append(f"**Use case seed:** {script['use_case_seed']}")
    lines.append(f"**Role priors:** `{script.get('role_id')}`")
    lines.append(f"**Run at:** {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    lines.append("**System definitions:**")
    lines.append("- **A** — chained v0.5: 5 sub-agents per turn (triage → distill → synthesizer → why-prober → probe-generator); orchestrator drives the conversation.")
    lines.append("- **B** — mega-agent baseline: 1 LLM call per turn with a strong system prompt that bakes in everything the chain encodes structurally.")
    lines.append("- **C** — v0.6 hybrid: extractors (triage → distill → synthesizer) run as a structured-output skill; mega-agent runs the conversation as a single call WITH spec-introspection tools (get_current_spec_state, get_working_theory, get_checklist_progress).")
    lines.append("")

    # Aggregates
    def _sum(metric_key: str, system: str) -> int:
        return sum(r[f"{system}_metrics"].get(metric_key, 0) or 0 for r in rows)

    def _vocab_sum(system: str, kind: str) -> int:
        return sum(r[f"{system}_metrics"]["vocab"][kind] for r in rows)

    def _rat_count(system: str) -> int:
        return sum(1 for r in rows if r[f"{system}_metrics"]["has_rationale"])

    a_total_ms = _sum("duration_ms", "a")
    b_total_ms = _sum("duration_ms", "b")
    c_total_ms = _sum("duration_ms", "c")

    lines.append("## Summary metrics")
    lines.append("")
    lines.append("| Metric | A (chained) | B (mega) | C (hybrid) |")
    lines.append("|---|---|---|---|")
    lines.append(f"| Total wall time | {a_total_ms}ms | {b_total_ms}ms | {c_total_ms}ms |")
    lines.append(f"| Avg per turn | {a_total_ms // len(rows)}ms | {b_total_ms // len(rows)}ms | {c_total_ms // len(rows)}ms |")
    lines.append(f"| Customer-vocab terms (sum) | {_vocab_sum('a','customer_terms')} | {_vocab_sum('b','customer_terms')} | {_vocab_sum('c','customer_terms')} |")
    lines.append(f"| Generic SaaS-org terms | {_vocab_sum('a','generic_terms')} | {_vocab_sum('b','generic_terms')} | {_vocab_sum('c','generic_terms')} |")
    lines.append(f"| Detected rationale | {_rat_count('a')}/{len(rows)} | {_rat_count('b')}/{len(rows)} | {_rat_count('c')}/{len(rows)} |")

    # Token totals
    b_in = sum((r["b_metrics"]["tokens"].get("input") or 0) for r in rows)
    b_out = sum((r["b_metrics"]["tokens"].get("output") or 0) for r in rows)
    c_in = sum((r["c_metrics"]["tokens"].get("input") or 0) for r in rows)
    c_out = sum((r["c_metrics"]["tokens"].get("output") or 0) for r in rows)
    lines.append(f"| Tokens (input/output, mega-call only for B and C) | n/a | {b_in}in/{b_out}out | {c_in}in/{c_out}out |")
    lines.append("")

    # Tool-call summary for C
    all_tool_calls: list[str] = []
    for r in rows:
        all_tool_calls.extend(r["c_metrics"]["mega_tool_calls"])
    if all_tool_calls:
        from collections import Counter
        counts = Counter(all_tool_calls)
        lines.append(f"**C — total spec-tool invocations across the script:** {len(all_tool_calls)}")
        for name, n in counts.most_common():
            lines.append(f"  - `{name}`: {n}")
    else:
        lines.append("**C** did not invoke any spec-introspection tools across the script.")
    lines.append("")

    # Structured-output state — A and C both have one; B does not
    def _spec_summary(spec: dict, label: str) -> list[str]:
        n_topics = len(spec.get("topics", []))
        n_facts = sum(len(t.get("facts", [])) for t in spec.get("topics", []))
        theory = spec.get("working_theory") or {}
        out = [
            f"### {label} — final structured state",
            "",
            f"- Phase: `{spec.get('phase')}`",
            f"- Topics covered: {n_topics}, total facts recorded: {n_facts}",
            f"- Working-theory confidence: `{theory.get('confidence')}`",
        ]
        if theory.get("one_line_framing"):
            out.append("- Working-theory framing:")
            out.append(f"  > {theory['one_line_framing']}")
        if theory.get("candidate_framings"):
            out.append(f"- Candidate framings: {len(theory['candidate_framings'])}")
        out.append(f"- Gaps flagged: {len(spec.get('gaps', []))}")
        out.append("")
        return out

    lines.extend(_spec_summary(session_a_final.get("spec", {}), "A (chained)"))
    lines.extend(_spec_summary(session_c_final.get("spec", {}), "C (hybrid)"))
    lines.append("**Note:** B (mega-agent) has NO structured spec — everything it knows lives in conversational history.")
    lines.append("")

    # Per-turn side-by-side
    lines.append("## Per-turn side-by-side")
    lines.append("")
    for r in rows:
        lines.append(f"### Turn {r['n']}")
        lines.append(f"_{r['tests']}_")
        lines.append("")
        lines.append("**Customer:**")
        lines.append("")
        lines.append("> " + r["customer"].replace("\n", "\n> "))
        lines.append("")
        lines.append(
            f"**A (chained v0.5)** — `{r['a_metrics']['duration_ms']}ms`, "
            f"vocab `{r['a_metrics']['vocab']['customer_terms']}c/{r['a_metrics']['vocab']['generic_terms']}g`, "
            f"rationale `{r['a_metrics']['has_rationale']}`, triage `{r['a_metrics']['raw_summary'].get('triage_label')}`"
        )
        lines.append("")
        lines.append("> " + r["a_response"].replace("\n", "\n> "))
        lines.append("")
        lines.append(
            f"**B (mega-agent)** — `{r['b_metrics']['duration_ms']}ms`, "
            f"vocab `{r['b_metrics']['vocab']['customer_terms']}c/{r['b_metrics']['vocab']['generic_terms']}g`, "
            f"rationale `{r['b_metrics']['has_rationale']}`, "
            f"tokens `{r['b_metrics']['tokens'].get('input')}in/{r['b_metrics']['tokens'].get('output')}out`"
        )
        lines.append("")
        lines.append("> " + r["b_response"].replace("\n", "\n> "))
        lines.append("")
        c_tools_str = ", ".join(r["c_metrics"]["mega_tool_calls"]) or "none"
        lines.append(
            f"**C (v0.6 hybrid)** — `{r['c_metrics']['duration_ms']}ms` total, "
            f"vocab `{r['c_metrics']['vocab']['customer_terms']}c/{r['c_metrics']['vocab']['generic_terms']}g`, "
            f"rationale `{r['c_metrics']['has_rationale']}`, triage `{r['c_metrics']['triage_label']}`, "
            f"tools used: {c_tools_str}, "
            f"mega tokens `{r['c_metrics']['tokens'].get('input')}in/{r['c_metrics']['tokens'].get('output')}out`"
        )
        lines.append("")
        lines.append("> " + r["c_response"].replace("\n", "\n> "))
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _render_markdown(script: dict, rows: list[dict], session_a_final: dict) -> str:
    lines: list[str] = []
    lines.append(f"# Comparison: chained agent (A) vs mega-agent baseline (B)")
    lines.append("")
    lines.append(f"**Script:** `{script['name']}` — {script.get('description','')}")
    lines.append(f"**Use case seed:** {script['use_case_seed']}")
    lines.append(f"**Role priors:** `{script.get('role_id')}`")
    lines.append(f"**Run at:** {datetime.now(timezone.utc).isoformat()}")
    lines.append("")

    # Aggregate metrics
    a_total_ms = sum(r["a_metrics"]["duration_ms"] for r in rows)
    b_total_ms = sum(r["b_metrics"]["duration_ms"] for r in rows)
    a_vocab_total = sum(r["a_metrics"]["vocab"]["customer_terms"] for r in rows)
    b_vocab_total = sum(r["b_metrics"]["vocab"]["customer_terms"] for r in rows)
    a_generic_total = sum(r["a_metrics"]["vocab"]["generic_terms"] for r in rows)
    b_generic_total = sum(r["b_metrics"]["vocab"]["generic_terms"] for r in rows)
    a_rationale_count = sum(1 for r in rows if r["a_metrics"]["has_rationale"])
    b_rationale_count = sum(1 for r in rows if r["b_metrics"]["has_rationale"])

    b_total_input = sum((r["b_metrics"]["tokens"].get("input") or 0) for r in rows)
    b_total_output = sum((r["b_metrics"]["tokens"].get("output") or 0) for r in rows)

    lines.append("## Summary metrics")
    lines.append("")
    lines.append("| Metric | Chained (A) | Mega-agent (B) |")
    lines.append("|---|---|---|")
    lines.append(f"| Total wall time | {a_total_ms}ms | {b_total_ms}ms |")
    lines.append(f"| Avg per turn | {a_total_ms // len(rows)}ms | {b_total_ms // len(rows)}ms |")
    lines.append(f"| Customer-vocabulary terms used (sum across turns) | {a_vocab_total} | {b_vocab_total} |")
    lines.append(f"| Generic SaaS-org terms used (lower = better) | {a_generic_total} | {b_generic_total} |")
    lines.append(f"| Turns with detectable customer-facing rationale | {a_rationale_count}/{len(rows)} | {b_rationale_count}/{len(rows)} |")
    lines.append(f"| Mega-agent token usage (input / output) | — | {b_total_input} / {b_total_output} |")
    lines.append("")

    spec = session_a_final.get("spec", {})
    n_topics = len(spec.get("topics", []))
    n_facts = sum(len(t.get("facts", [])) for t in spec.get("topics", []))
    theory = spec.get("working_theory") or {}
    lines.append("### Chained agent (A) — final structured state after script")
    lines.append("")
    lines.append(f"- Phase: `{spec.get('phase')}`")
    lines.append(f"- Topics covered: {n_topics}, total facts recorded: {n_facts}")
    lines.append(f"- Working theory confidence: `{theory.get('confidence')}`")
    if theory.get("one_line_framing"):
        lines.append(f"- Working-theory framing:")
        lines.append(f"  > {theory['one_line_framing']}")
    if theory.get("candidate_framings"):
        lines.append(f"- Candidate framings: {len(theory['candidate_framings'])}")
    lines.append("")
    lines.append("**Note:** the mega-agent (B) has NO structured spec or working theory. Everything it knows lives in its conversational history. Lack of structured output is itself a measurable difference.")
    lines.append("")

    # Per-turn side-by-side
    lines.append("## Per-turn side-by-side")
    lines.append("")
    for r in rows:
        lines.append(f"### Turn {r['n']}")
        lines.append(f"_{r['tests']}_")
        lines.append("")
        lines.append(f"**Customer:**")
        lines.append("")
        lines.append("> " + r["customer"].replace("\n", "\n> "))
        lines.append("")
        lines.append(f"**Chained agent (A)** — `{r['a_metrics']['duration_ms']}ms`, "
                     f"vocab `{r['a_metrics']['vocab']['customer_terms']}c/{r['a_metrics']['vocab']['generic_terms']}g`, "
                     f"rationale: `{r['a_metrics']['has_rationale']}`, triage: `{r['a_metrics']['raw_summary'].get('triage_label')}`")
        lines.append("")
        lines.append("> " + r["a_response"].replace("\n", "\n> "))
        lines.append("")
        lines.append(f"**Mega-agent (B)** — `{r['b_metrics']['duration_ms']}ms`, "
                     f"vocab `{r['b_metrics']['vocab']['customer_terms']}c/{r['b_metrics']['vocab']['generic_terms']}g`, "
                     f"rationale: `{r['b_metrics']['has_rationale']}`, "
                     f"tokens `{r['b_metrics']['tokens'].get('input')}in/{r['b_metrics']['tokens'].get('output')}out`")
        lines.append("")
        lines.append("> " + r["b_response"].replace("\n", "\n> "))
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "results",
    )
    args = parser.parse_args()
    asyncio.run(run_comparison(args.script, args.out_dir))


if __name__ == "__main__":
    main()
