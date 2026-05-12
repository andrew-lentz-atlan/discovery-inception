"""Drive v0.6 (eager synthesizer + format-constrained mega) and v0.7
(lazy synthesizer + free-form mega) through the same customer script
and emit a side-by-side markdown comparison.

Same model. Same priors. Same customer turns. The point is to isolate
two specific architectural changes (lazy synth + free-form output) and
measure whether they hold quality while cutting cost.

Usage:
    cd discovery-inception
    uv run python -m agent.baselines.run_v06_v07_comparison \\
        --script agent/baselines/scripts/scope_creep_5turn.json
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

from dotenv import load_dotenv
from openai import AsyncOpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

from agent.baselines.mega_agent import MegaAgentSession  # noqa: E402
from agent.baselines.run_comparison import (  # noqa: E402
    VOCAB_TERMS,
    GENERIC_TERMS,
    vocab_score,
    question_count,
    has_rationale,
)
from agent.schemas import DiscoverySpec  # noqa: E402
from agent.state import DiscoverySession  # noqa: E402
from agent.v06.orchestrator import run_v06_turn  # noqa: E402
from agent.v07.orchestrator import run_v07_turn  # noqa: E402


async def run_v06_v07(script_path: Path, out_dir: Path) -> Path:
    script = json.loads(script_path.read_text())
    use_case_seed = script["use_case_seed"]
    role_id = script.get("role_id")
    turns = script["turns"]

    base_url = os.environ.get("LITELLM_BASE_URL", "").strip()
    api_key = os.environ.get("LITELLM_API_KEY", "").strip()
    if not base_url or not api_key:
        raise RuntimeError("LITELLM_BASE_URL and LITELLM_API_KEY must be set")
    openai_client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    print(f"→ Loading script: {script['name']} ({len(turns)} turns)")
    print(f"  use_case_seed: {use_case_seed}")
    print(f"  role_id: {role_id}")
    print()

    # ---- Start both systems ----
    print("→ Starting v0.6 hybrid (eager synth + format-constrained mega) — in-process…")
    spec_v6 = DiscoverySpec(use_case_seed=use_case_seed, role_id=role_id)
    sess_v6 = DiscoverySession(spec=spec_v6)
    mega_v6 = MegaAgentSession(use_case_seed=use_case_seed, role_id=role_id)
    print(f"  v0.6 session_id: {sess_v6.session_id}")
    print()

    print("→ Starting v0.7 hybrid (lazy synth + free-form mega) — in-process…")
    spec_v7 = DiscoverySpec(use_case_seed=use_case_seed, role_id=role_id)
    sess_v7 = DiscoverySession(spec=spec_v7)
    mega_v7 = MegaAgentSession(use_case_seed=use_case_seed, role_id=role_id)
    print(f"  v0.7 session_id: {sess_v7.session_id}")
    print()

    rows: list[dict] = []
    for t in turns:
        n = t["n"]
        msg = t["customer"]
        tests = t.get("tests", "")
        print(f"━━━ Turn {n} ━━━")
        print(f"customer: {msg[:120]}{'…' if len(msg) > 120 else ''}")
        print(f"  testing: {tests}")

        v6_task = run_v06_turn(openai_client, sess_v6, mega_v6, msg)
        v7_task = run_v07_turn(openai_client, sess_v7, mega_v7, msg)
        (v6_turn, v6_checklist), (v7_turn, v7_checklist) = await asyncio.gather(v6_task, v7_task)

        v6_msg = v6_turn.agent_message or ""
        v7_msg = v7_turn.agent_message or ""

        def _summarize_turn(turn) -> dict:
            mega_event = next((e for e in turn.events if e.sub_agent == "mega_agent"), None)
            extractor_events = [e for e in turn.events if e.sub_agent != "mega_agent"]
            total_ms = sum(e.duration_ms for e in turn.events)
            mega_out = mega_event.output if mega_event else {}
            triage_label = next(
                (e.output.get("label") for e in extractor_events if e.sub_agent == "triage"),
                None,
            )
            return {
                "total_ms": total_ms,
                "extractor_events": [
                    {"sub_agent": e.sub_agent, "duration_ms": e.duration_ms}
                    for e in extractor_events
                ],
                "mega_tool_calls": [tc.get("name") for tc in mega_out.get("tool_calls", [])],
                "tokens": {
                    "input": mega_out.get("input_tokens"),
                    "output": mega_out.get("output_tokens"),
                },
                "triage_label": triage_label,
            }

        v6_summary = _summarize_turn(v6_turn)
        v7_summary = _summarize_turn(v7_turn)

        v6_metrics = {
            "duration_ms": v6_summary["total_ms"],
            "response_chars": len(v6_msg),
            "question_marks": question_count(v6_msg),
            "has_rationale": has_rationale(v6_msg),
            "vocab": vocab_score(v6_msg),
            "mega_tool_calls": v6_summary["mega_tool_calls"],
            "tokens": v6_summary["tokens"],
            "triage_label": v6_summary["triage_label"],
            "n_extractor_calls": len(v6_summary["extractor_events"]),
        }
        v7_metrics = {
            "duration_ms": v7_summary["total_ms"],
            "response_chars": len(v7_msg),
            "question_marks": question_count(v7_msg),
            "has_rationale": has_rationale(v7_msg),
            "vocab": vocab_score(v7_msg),
            "mega_tool_calls": v7_summary["mega_tool_calls"],
            "tokens": v7_summary["tokens"],
            "triage_label": v7_summary["triage_label"],
            "n_extractor_calls": len(v7_summary["extractor_events"]),
        }

        print(f"  v0.6 ({v6_metrics['duration_ms']}ms, vocab={v6_metrics['vocab']['customer_terms']}c/{v6_metrics['vocab']['generic_terms']}g, "
              f"extractors={v6_metrics['n_extractor_calls']}, tools={v6_metrics['mega_tool_calls']}): {v6_msg[:140]}")
        print(f"  v0.7 ({v7_metrics['duration_ms']}ms, vocab={v7_metrics['vocab']['customer_terms']}c/{v7_metrics['vocab']['generic_terms']}g, "
              f"extractors={v7_metrics['n_extractor_calls']}, tools={v7_metrics['mega_tool_calls']}): {v7_msg[:140]}")
        print()

        rows.append({
            "n": n, "customer": msg, "tests": tests,
            "v6_response": v6_msg, "v6_metrics": v6_metrics,
            "v7_response": v7_msg, "v7_metrics": v7_metrics,
        })

    sess_v6_final = json.loads(sess_v6.model_dump_json())
    sess_v7_final = json.loads(sess_v7.model_dump_json())

    await openai_client.close()

    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    artifact_path = out_dir / f"{script['name']}_v06_vs_v07__{timestamp}.md"
    artifact_path.write_text(_render_markdown(script, rows, sess_v6_final, sess_v7_final))
    print(f"\n✓ Wrote {artifact_path}")
    return artifact_path


def _render_markdown(script, rows, sess_v6_final, sess_v7_final) -> str:
    lines: list[str] = []
    lines.append("# Comparison: v0.6 (eager synth + format-constrained mega) vs v0.7 (lazy synth + free-form mega)")
    lines.append("")
    lines.append(f"**Script:** `{script['name']}`")
    lines.append(f"**Use case seed:** {script['use_case_seed']}")
    lines.append(f"**Role priors:** `{script.get('role_id')}`")
    lines.append(f"**Run at:** {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    lines.append("**The two architectural changes in v0.7:**")
    lines.append("1. Synthesizer is LAZY — invoked when the mega-agent calls `synthesize_my_thinking()`. Not pre-computed every turn.")
    lines.append("2. Mega-agent's prompt does NOT constrain output format. It can produce multi-sentence, multi-clause, free-form responses. Structure happens in extractors.")
    lines.append("")

    def _sum(metric, system):
        return sum(r[f"{system}_metrics"].get(metric, 0) or 0 for r in rows)

    def _vocab_sum(system, kind):
        return sum(r[f"{system}_metrics"]["vocab"][kind] for r in rows)

    def _rat_count(system):
        return sum(1 for r in rows if r[f"{system}_metrics"]["has_rationale"])

    v6_total = _sum("duration_ms", "v6")
    v7_total = _sum("duration_ms", "v7")
    v6_ex_calls = _sum("n_extractor_calls", "v6")
    v7_ex_calls = _sum("n_extractor_calls", "v7")

    v6_in = sum((r["v6_metrics"]["tokens"].get("input") or 0) for r in rows)
    v6_out = sum((r["v6_metrics"]["tokens"].get("output") or 0) for r in rows)
    v7_in = sum((r["v7_metrics"]["tokens"].get("input") or 0) for r in rows)
    v7_out = sum((r["v7_metrics"]["tokens"].get("output") or 0) for r in rows)

    all_tool_calls_v6 = [t for r in rows for t in r["v6_metrics"]["mega_tool_calls"]]
    all_tool_calls_v7 = [t for r in rows for t in r["v7_metrics"]["mega_tool_calls"]]

    lines.append("## Summary metrics")
    lines.append("")
    lines.append("| Metric | v0.6 | v0.7 |")
    lines.append("|---|---|---|")
    lines.append(f"| Total wall time | {v6_total}ms | {v7_total}ms |")
    lines.append(f"| Avg per turn | {v6_total // len(rows)}ms | {v7_total // len(rows)}ms |")
    lines.append(f"| Sum of extractor sub-agent calls | {v6_ex_calls} | {v7_ex_calls} |")
    lines.append(f"| Customer-vocab terms (sum) | {_vocab_sum('v6','customer_terms')} | {_vocab_sum('v7','customer_terms')} |")
    lines.append(f"| Generic SaaS-org terms | {_vocab_sum('v6','generic_terms')} | {_vocab_sum('v7','generic_terms')} |")
    lines.append(f"| Detected rationale | {_rat_count('v6')}/{len(rows)} | {_rat_count('v7')}/{len(rows)} |")
    lines.append(f"| Mega-agent tokens (input / output) | {v6_in}in/{v6_out}out | {v7_in}in/{v7_out}out |")
    lines.append(f"| Total spec-tool invocations | {len(all_tool_calls_v6)} | {len(all_tool_calls_v7)} |")
    lines.append("")

    from collections import Counter
    if all_tool_calls_v6:
        v6_cnt = Counter(all_tool_calls_v6)
        lines.append(f"**v0.6 tool calls:** {dict(v6_cnt)}")
    if all_tool_calls_v7:
        v7_cnt = Counter(all_tool_calls_v7)
        lines.append(f"**v0.7 tool calls:** {dict(v7_cnt)}")
    lines.append("")

    def _spec_summary(spec, label):
        n_topics = len(spec.get("topics", []))
        n_facts = sum(len(t.get("facts", [])) for t in spec.get("topics", []))
        theory = spec.get("working_theory") or {}
        out = [
            f"### {label} — final structured state",
            "",
            f"- Phase: `{spec.get('phase')}`",
            f"- Topics covered: {n_topics}, facts recorded: {n_facts}",
            f"- Working theory confidence: `{theory.get('confidence')}`",
        ]
        if theory.get("one_line_framing"):
            out.append(f"- Working-theory framing:")
            out.append(f"  > {theory['one_line_framing']}")
        out.append(f"- Theory history snapshots: {len(spec.get('theory_history') or [])}")
        out.append(f"- Gaps flagged: {len(spec.get('gaps', []))}")
        out.append("")
        return out

    lines.extend(_spec_summary(sess_v6_final.get("spec", {}), "v0.6"))
    lines.extend(_spec_summary(sess_v7_final.get("spec", {}), "v0.7"))

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
        v6_tools = ", ".join(r["v6_metrics"]["mega_tool_calls"]) or "none"
        v7_tools = ", ".join(r["v7_metrics"]["mega_tool_calls"]) or "none"
        lines.append(
            f"**v0.6** — `{r['v6_metrics']['duration_ms']}ms` total, "
            f"vocab `{r['v6_metrics']['vocab']['customer_terms']}c/{r['v6_metrics']['vocab']['generic_terms']}g`, "
            f"triage `{r['v6_metrics']['triage_label']}`, "
            f"extractors `{r['v6_metrics']['n_extractor_calls']}`, "
            f"tools `{v6_tools}`, "
            f"mega tokens `{r['v6_metrics']['tokens'].get('input')}in/{r['v6_metrics']['tokens'].get('output')}out`"
        )
        lines.append("")
        lines.append("> " + r["v6_response"].replace("\n", "\n> "))
        lines.append("")
        lines.append(
            f"**v0.7** — `{r['v7_metrics']['duration_ms']}ms` total, "
            f"vocab `{r['v7_metrics']['vocab']['customer_terms']}c/{r['v7_metrics']['vocab']['generic_terms']}g`, "
            f"triage `{r['v7_metrics']['triage_label']}`, "
            f"extractors `{r['v7_metrics']['n_extractor_calls']}`, "
            f"tools `{v7_tools}`, "
            f"mega tokens `{r['v7_metrics']['tokens'].get('input')}in/{r['v7_metrics']['tokens'].get('output')}out`"
        )
        lines.append("")
        lines.append("> " + r["v7_response"].replace("\n", "\n> "))
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "results",
    )
    args = parser.parse_args()
    asyncio.run(run_v06_v07(args.script, args.out_dir))


if __name__ == "__main__":
    main()
