"""Drive v0.8 through a customer script + deterministic close-out, then
export spec.md + spec.json. Same shape as run_v07_solo.py but runs the
v0.8 orchestrator (with probe-sharpener post-processor + find_tensions
tool).

Usage:
    uv run python -m agent.baselines.run_v08_solo \\
        --script agent/baselines/scripts/sales_analyst_50turn.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

from agent.baselines.mega_agent import MegaAgentSession  # noqa: E402
from agent.schemas import DiscoverySpec  # noqa: E402
from agent.state import DiscoverySession  # noqa: E402
from agent.v08.orchestrator import run_v08_turn, run_final_synthesis  # noqa: E402
from agent.mcp_server.server import _render_spec_markdown  # noqa: E402


async def run_solo(script_path: Path) -> Path:
    script = json.loads(script_path.read_text())
    use_case_seed = script["use_case_seed"]
    role_id = script.get("role_id")
    turns = script["turns"]

    base_url = os.environ.get("LITELLM_BASE_URL", "").strip()
    api_key = os.environ.get("LITELLM_API_KEY", "").strip()
    if not base_url or not api_key:
        raise RuntimeError("LITELLM_BASE_URL and LITELLM_API_KEY must be set")
    client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    print(f"→ v0.8 solo run on script: {script['name']} ({len(turns)} turns)")
    print(f"  use_case_seed: {use_case_seed}")
    print(f"  role_id: {role_id}")
    print()

    spec = DiscoverySpec(use_case_seed=use_case_seed, role_id=role_id)
    session = DiscoverySession(spec=spec)
    mega = MegaAgentSession(use_case_seed=use_case_seed, role_id=role_id)
    print(f"  session_id: {session.session_id}")
    print()

    total_start = time.perf_counter()
    sharpener_rewrites = 0
    sharpener_runs = 0
    tool_invocations_total = 0
    for t in turns:
        n = t["n"]
        msg = t["customer"]
        turn_start = time.perf_counter()
        turn, checklist = await run_v08_turn(client, session, mega, msg)
        turn_ms = int((time.perf_counter() - turn_start) * 1000)

        mega_event = next((e for e in turn.events if e.sub_agent == "mega_agent"), None)
        triage_event = next((e for e in turn.events if e.sub_agent == "triage"), None)
        sharpener_event = next((e for e in turn.events if e.sub_agent == "probe_sharpener"), None)
        triage_label = triage_event.output.get("label") if triage_event else None
        tool_calls = []
        if mega_event:
            tool_calls = [tc.get("name") for tc in mega_event.output.get("tool_calls", [])]
            tool_invocations_total += len(tool_calls)
        sharpener_score = None
        sharpener_action = "skipped"
        if sharpener_event:
            sharpener_runs += 1
            o = sharpener_event.output or {}
            sharpener_score = o.get("quality_score")
            if not o.get("ships_as_is", True):
                sharpener_rewrites += 1
                sharpener_action = f"REWRITE (score={sharpener_score})"
            else:
                sharpener_action = f"ship (score={sharpener_score})"

        agent_msg = (turn.agent_message or "").replace("\n", " ")[:130]
        print(
            f"Turn {n:>2} [{turn_ms:>5}ms, triage={triage_label}, "
            f"tools={tool_calls or 'none'}, sharpener={sharpener_action}]: {agent_msg}"
        )

    print()
    print(f"→ All {len(turns)} turns complete. Running deterministic close-out synthesis…")
    final_start = time.perf_counter()
    final_theory = await run_final_synthesis(client, session)
    finalize_ms = int((time.perf_counter() - final_start) * 1000)
    print(f"  finalize: {finalize_ms}ms — confidence={final_theory.confidence}")
    if final_theory.internal_tensions:
        print(f"  internal_tensions at close: {len(final_theory.internal_tensions)}")

    sessions_dir = PROJECT_ROOT / "sessions" / session.session_id
    sessions_dir.mkdir(parents=True, exist_ok=True)
    (sessions_dir / "spec.json").write_text(session.spec.model_dump_json(indent=2))
    (sessions_dir / "spec.md").write_text(_render_spec_markdown(session))

    total_ms = int((time.perf_counter() - total_start) * 1000)
    await client.close()

    print()
    print("─" * 70)
    print(f"✓ Done in {total_ms / 1000:.1f}s total.")
    print(f"  session_id:              {session.session_id}")
    print(f"  topics:                  {len(session.spec.topics)}")
    print(f"  facts:                   {sum(len(t.facts) for t in session.spec.topics)}")
    print(f"  gaps flagged:            {len(session.spec.gaps)}")
    print(f"  tool invocations:        {tool_invocations_total}")
    print(f"  sharpener runs:          {sharpener_runs}/{len(turns)} turns")
    print(f"  sharpener rewrites:      {sharpener_rewrites}")
    print(f"  spec.md:                 {sessions_dir / 'spec.md'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run_solo(args.script))


if __name__ == "__main__":
    main()
