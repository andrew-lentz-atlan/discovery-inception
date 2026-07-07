"""Portability probe — LangGraph leg.

The same inception slice (classify -> skills -> architecture) expressed as an
idiomatic LangGraph StateGraph: three nodes, each using
`llm.with_structured_output(PydanticModel)` for validated output, wired
START -> classify -> skills -> architecture -> END.

CRITICAL for a fair A/B: same rendered prompts (patterns baked in), same
Pydantic schemas, SAME model via the SAME LiteLLM proxy as the Python leg.
Only the orchestration substrate differs (LangGraph StateGraph vs our
hand-rolled call_step chain). If outputs converge with Python within the
within-runtime variance band, the runtime is a swappable adapter.


FROZEN RESEARCH ARTIFACT: the hardcoded SE_SESSION is deliberate — this
script reproduces the findings/10 experiment against its exact baseline, so
it stays byte-stable rather than growing a --session-id flag. For product
use of the LangGraph substrate, see agent/inception/graph.py (the
maintained adapter).

Run (langgraph installed transiently — NOT added to product deps):
    SESSIONS_DIR=~/Desktop/discovery-inception/sessions \
      uv run --with langgraph --with langchain-openai \
      python -m tools.portability_probe_langgraph --runs 3
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

from agent.schemas import DiscoverySpec
from agent.inception.schemas import (
    WorkloadClassification,
    SkillProposalResult,
    ArchitectureProposal,
)
from agent.inception.run import (
    load_prompt,
    load_pattern_category,
    build_spec_digest,
    feedback_block,
)
from agent.json_utils import parse_json_lenient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SE_SESSION = "sess_b6b350634626"
MODEL = os.environ.get("INCEPTION_MODEL", "claude-haiku-4-5")


def _llm() -> ChatOpenAI:
    base_url = os.environ.get("LITELLM_BASE_URL", "").strip()
    api_key = os.environ.get("LITELLM_API_KEY", "").strip()
    if not base_url or not api_key:
        raise RuntimeError("LITELLM_BASE_URL and LITELLM_API_KEY must be set")
    # Same model, same proxy as the Python leg — only the orchestration differs.
    return ChatOpenAI(model=MODEL, base_url=base_url, api_key=api_key, temperature=0.2, max_tokens=8192)


def _inputs(sessions_dir: Path) -> tuple[str, str, str]:
    sess = sessions_dir / SE_SESSION
    raw = json.loads((sess / "session.json").read_text())
    spec = DiscoverySpec.model_validate(raw["spec"])
    spec_md = (sess / "spec.md").read_text()
    role_id = spec.role_id
    rc_path = PROJECT_ROOT / "skills" / (role_id or "") / "context.json"
    rc = rc_path.read_text() if (role_id and rc_path.exists()) else '{"role_summary":"(stub)"}'
    return spec_md, rc, build_spec_digest(spec)


class State(TypedDict, total=False):
    spec_md: str
    rc: str
    ss: str
    classification: WorkloadClassification
    proposal: SkillProposalResult
    architecture: ArchitectureProposal


# The exact system prompt the Python engine's call_step uses. It's part of the
# PORTABLE CONTRACT — it's how the pipeline reliably gets clean JSON out. The
# LangGraph leg must send it too, or the A/B is unfair (a bare invoke() lets the
# model add trailing prose -> "Extra data" parse failures the Python leg never
# sees). Replicating it is the faithful comparison.
_JSON_SYS = (
    "You produce JSON output exactly as instructed by the user. "
    "Output only the JSON object — no prose, no markdown fences, "
    "no preamble or commentary. Begin your response with `{` and end with `}`."
)


def _structured(llm: ChatOpenAI, prompt: str, model_cls):
    """Same output handling as the Python engine's call_step: same system prompt
    + the user prompt (schema spec is IN the prompt), then lenient-parse +
    Pydantic-validate the response. Deliberately NOT llm.with_structured_output()
    — its Bedrock-native JSON-Schema path rejects number minimum/maximum (our
    `confidence` field), a real provider structured-output gotcha. Handling
    output identically to Python isolates the orchestration substrate
    (StateGraph) as the only difference — the fair A/B."""
    resp = llm.invoke([("system", _JSON_SYS), ("human", prompt)])
    text = resp.content if isinstance(resp.content, str) else str(resp.content)
    return model_cls.model_validate(parse_json_lenient(text))


def build_graph(llm: ChatOpenAI):
    dg = load_pattern_category("decision-guides")
    ap = load_pattern_category("anti-patterns")
    sd = load_pattern_category("skill-design")
    arch_patterns = load_pattern_category("architectures")

    def classify(state: State) -> dict:
        prompt = load_prompt(
            "01_workload_classifier.md",
            SPEC_MD=state["spec_md"], ROLE_CONTEXT_JSON=state["rc"],
            DECISION_GUIDES=dg, SPEC_STRUCTURED=state["ss"],
            PRIOR_FEEDBACK=feedback_block(None, "workload"),
        )
        return {"classification": _structured(llm, prompt, WorkloadClassification)}

    def skills(state: State) -> dict:
        prompt = load_prompt(
            "02_skill_proposer.md",
            WORKLOAD_CLASSIFICATION_JSON=state["classification"].model_dump_json(indent=2),
            DECISION_GUIDES=dg, ANTI_PATTERNS=ap, SKILL_DESIGN=sd,
            SPEC_MD=state["spec_md"], ROLE_CONTEXT_JSON=state["rc"],
            SPEC_STRUCTURED=state["ss"], PRIOR_FEEDBACK=feedback_block(None, "skills"),
        )
        return {"proposal": _structured(llm, prompt, SkillProposalResult)}

    def architecture(state: State) -> dict:
        prompt = load_prompt(
            "03_architecture_proposer.md",
            WORKLOAD_CLASSIFICATION_JSON=state["classification"].model_dump_json(indent=2),
            SKILL_PROPOSAL_JSON=state["proposal"].model_dump_json(indent=2),
            ARCHITECTURE_PATTERNS=arch_patterns, DECISION_GUIDES=dg, ANTI_PATTERNS=ap,
            SKILL_DESIGN=sd, SPEC_STRUCTURED=state["ss"],
            PRIOR_FEEDBACK=feedback_block(None, "architecture"),
        )
        return {"architecture": _structured(llm, prompt, ArchitectureProposal)}

    g = StateGraph(State)
    g.add_node("classify", classify)
    g.add_node("skills", skills)
    g.add_node("architecture", architecture)
    g.add_edge(START, "classify")
    g.add_edge("classify", "skills")
    g.add_edge("skills", "architecture")
    g.add_edge("architecture", END)
    return g.compile()


def _decisions(s: State) -> dict:
    c, p, a = s["classification"], s["proposal"], s["architecture"]
    return {
        "interaction_shape": c.interaction_shape,
        "decision_complexity": c.decision_complexity,
        "state_shape": c.state_shape,
        "learns_from_experience": c.learns_from_experience,
        "workload_confidence": round(c.confidence, 2),
        "skill_count": len(p.skills),
        "skill_names": sorted(x.name for x in p.skills),
        "architecture": a.selected_pattern_slug,
        "arch_confidence": round(a.confidence, 2),
        "rejected": sorted(r.pattern_slug for r in a.rejected_alternatives),
        "addons": sorted(x.pattern_slug for x in (a.candidate_addons or [])),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--sessions-dir", default=str(PROJECT_ROOT / "sessions"))
    ap.add_argument("--out", default="/tmp/portability/langgraph_runs.json")
    args = ap.parse_args()

    spec_md, rc, ss = _inputs(Path(args.sessions_dir).expanduser())
    graph = build_graph(_llm())
    runs = []
    for i in range(args.runs):
        print(f"→ LangGraph slice run {i+1}/{args.runs}...")
        final = graph.invoke({"spec_md": spec_md, "rc": rc, "ss": ss})
        d = _decisions(final)
        runs.append(d)
        print(
            f"   class={d['interaction_shape']}/{d['decision_complexity']}/{d['state_shape']} "
            f"learns={d['learns_from_experience']} conf={d['workload_confidence']} | "
            f"skills={d['skill_count']} | arch={d['architecture']}@{d['arch_confidence']}"
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"runtime": "langgraph", "runs": runs}, indent=2))
    print(f"\nWrote {args.runs} runs → {out}")


if __name__ == "__main__":
    main()
