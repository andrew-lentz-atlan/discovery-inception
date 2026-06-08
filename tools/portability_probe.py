"""Portability probe — does the inception slice produce the same decisions
across orchestration substrates (hand-rolled Python / LangGraph / Claude
Workflow)?

The thesis under test: if the contract (prompts + schemas + lifecycle) is
built right, the runtime is a swappable adapter and the decisions converge —
so runtime choice is a maintenance-economics question, not a capability one.

The methodological anchor: you cannot claim "same across runtimes" without
first knowing the within-runtime variance. So this probe runs the SAME runtime
N times to establish the noise band; cross-runtime difference is only
meaningful if it exceeds that band.

This file runs the PYTHON (hand-rolled) leg. The LangGraph leg lives in
portability_probe_langgraph.py; the Claude Workflow leg was run via the
Workflow tool. All three feed the SAME rendered prompts + schemas + SE spec —
only the orchestration substrate differs.

Usage:
    SESSIONS_DIR=~/Desktop/discovery-inception/sessions \
      uv run python -m tools.portability_probe --runs 3
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from agent.schemas import DiscoverySpec
from agent.inception.run import (
    _client,
    build_spec_digest,
    step_workload_classifier,
    step_skill_proposer,
    step_architecture_proposer,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SE_SESSION = "sess_b6b350634626"


def _load_inputs(sessions_dir: Path) -> tuple[str, str, str]:
    sess = sessions_dir / SE_SESSION
    raw = json.loads((sess / "session.json").read_text())
    spec = DiscoverySpec.model_validate(raw["spec"])
    spec_md = (sess / "spec.md").read_text()
    role_id = spec.role_id
    rc_path = PROJECT_ROOT / "skills" / (role_id or "") / "context.json"
    role_context_json = (
        rc_path.read_text() if (role_id and rc_path.exists()) else '{"role_summary":"(stub)"}'
    )
    spec_structured = build_spec_digest(spec)
    return spec_md, role_context_json, spec_structured


def _decisions(classification, proposal, architecture) -> dict:
    """Pull the decision-relevant fields for cross-run / cross-runtime comparison."""
    return {
        "interaction_shape": classification.interaction_shape,
        "decision_complexity": classification.decision_complexity,
        "state_shape": classification.state_shape,
        "learns_from_experience": classification.learns_from_experience,
        "workload_confidence": round(classification.confidence, 2),
        "skill_count": len(proposal.skills),
        "skill_names": sorted(s.name for s in proposal.skills),
        "architecture": architecture.selected_pattern_slug,
        "arch_confidence": round(architecture.confidence, 2),
        "rejected": sorted(r.pattern_slug for r in architecture.rejected_alternatives),
        "addons": sorted(a.pattern_slug for a in (architecture.candidate_addons or [])),
    }


async def run_python_slice(spec_md: str, rc: str, ss: str) -> dict:
    client = _client()
    classification = await step_workload_classifier(client, spec_md, rc, spec_structured=ss)
    proposal = await step_skill_proposer(client, classification, spec_md, rc, spec_structured=ss)
    architecture = await step_architecture_proposer(client, classification, proposal, spec_structured=ss)
    return _decisions(classification, proposal, architecture)


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=int, default=3, help="How many times to run (variance baseline).")
    ap.add_argument(
        "--sessions-dir",
        default=str(PROJECT_ROOT / "sessions"),
        help="Where the SE session lives (default in-repo sessions/).",
    )
    ap.add_argument("--out", default="/tmp/portability/python_runs.json")
    args = ap.parse_args()

    spec_md, rc, ss = _load_inputs(Path(args.sessions_dir).expanduser())
    runs = []
    for i in range(args.runs):
        print(f"→ Python slice run {i+1}/{args.runs}...")
        d = await run_python_slice(spec_md, rc, ss)
        runs.append(d)
        print(
            f"   class={d['interaction_shape']}/{d['decision_complexity']}/{d['state_shape']} "
            f"learns={d['learns_from_experience']} conf={d['workload_confidence']} | "
            f"skills={d['skill_count']} | arch={d['architecture']}@{d['arch_confidence']}"
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"runtime": "python-handrolled", "runs": runs}, indent=2))
    print(f"\nWrote {args.runs} runs → {out}")


if __name__ == "__main__":
    asyncio.run(main())
