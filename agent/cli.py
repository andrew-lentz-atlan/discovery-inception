"""CLI wrapper around the discovery-inception tools (same functions the
MCP server exposes, just shell-friendly).

Designed for use by the Claude skill, by colleagues comfortable in
terminal, or by scripts that want to drive a discovery without going
through MCP.

Subcommands match the MCP tool names so the skill can drop in either
transport.

Usage:
    # Artifact-first (recommended) — ingest call transcripts + docs first;
    # produces a populated spec + gap_list.md the FDE acts on.
    uv run python -m agent.cli ingest \\
        --use-case-seed "build SoCo agent for onboarding at TechCo" \\
        --artifact intake/sources/call-transcript.txt \\
        --artifact intake/sources/runbook.md \\
        --role-id soco-techco

    uv run python -m agent.cli list-priors
    uv run python -m agent.cli generate-priors \\
        --role-id soco-tc \\
        --artifact-file ./jd.md
    uv run python -m agent.cli start-session \\
        --use-case-seed "we want a SoCo agent for onboarding at TechCo" \\
        --role-id solutions-consultant
    # With Atlan context priming:
    uv run python -m agent.cli start-session \\
        --use-case-seed "brand analyst agent for fabric care" \\
        --atlan-tenant ces.atlan.com \\
        --atlan-glossary Fabric_Care_Analytics \\
        --atlan-tables default.aos,default.ddm
    uv run python -m agent.cli submit-turn \\
        --session-id sess_abc \\
        --message "We want to reduce TTFV from 90 to 30 days."
    uv run python -m agent.cli state --session-id sess_abc
    uv run python -m agent.cli finalize --session-id sess_abc
    uv run python -m agent.cli list-sessions

    # Run inception against a finalized discovery session — produces
    # agent_starter/<role_id_or_session_id>/ with orchestrator.py,
    # proposed skills, design_rationale.md, eval seed, judge harness.
    uv run python -m agent.cli inception --session-id sess_abc

Every subcommand prints JSON to stdout on success. Errors print JSON
with {"ok": false, "error": "..."} and exit code 1.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

from agent.ingest import run_ingest  # noqa: E402
from agent.mcp_server.server import (  # noqa: E402
    tool_generate_priors,
    tool_list_priors,
    tool_get_priors,
    tool_start_discovery_session,
    tool_submit_customer_turn,
    tool_get_session_state,
    tool_finalize_discovery_session,
    tool_list_sessions,
    tool_run_inception,
)


def _emit(result: dict) -> None:
    """Print result as JSON. Exit non-zero if ok=False."""
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not result.get("ok", True):
        sys.exit(1)


def _read_artifact(args: argparse.Namespace) -> str:
    """Get artifact text from --artifact-file or --artifact-text."""
    if args.artifact_text:
        return args.artifact_text
    if args.artifact_file:
        return Path(args.artifact_file).read_text()
    raise SystemExit("Either --artifact-text or --artifact-file is required.")


async def _async_main(args: argparse.Namespace) -> None:
    try:
        cmd = args.command
        if cmd == "ingest":
            result = await run_ingest(
                use_case_seed=args.use_case_seed,
                artifact_paths=[Path(p).resolve() for p in args.artifact],
                role_id=args.role_id,
            )
        elif cmd == "generate-priors":
            text = _read_artifact(args)
            result = await tool_generate_priors(
                artifact_text=text,
                role_id=args.role_id,
                source_name=args.source_name or "pasted_artifact",
            )
        elif cmd == "list-priors":
            result = tool_list_priors()
        elif cmd == "get-priors":
            result = tool_get_priors(role_id=args.role_id)
        elif cmd == "start-session":
            atlan_tables = (
                [t.strip() for t in args.atlan_tables.split(",") if t.strip()]
                if args.atlan_tables
                else None
            )
            atlan_domains = (
                [d.strip() for d in args.atlan_domains.split(",") if d.strip()]
                if args.atlan_domains
                else None
            )
            result = await tool_start_discovery_session(
                use_case_seed=args.use_case_seed,
                role_id=args.role_id,
                atlan_tenant=args.atlan_tenant,
                atlan_glossary=args.atlan_glossary,
                atlan_tables=atlan_tables,
                atlan_domains=atlan_domains,
            )
        elif cmd == "submit-turn":
            result = await tool_submit_customer_turn(
                session_id=args.session_id,
                message=args.message,
                no_probe=args.no_probe,
            )
        elif cmd == "state":
            result = tool_get_session_state(session_id=args.session_id)
        elif cmd == "finalize":
            result = await tool_finalize_discovery_session(session_id=args.session_id)
        elif cmd == "list-sessions":
            result = tool_list_sessions()
        elif cmd == "inception":
            result = await tool_run_inception(
                session_id=args.session_id,
                output_dir=args.output_dir,
                prior_feedback_path=args.prior_feedback,
            )
        else:
            result = {"ok": False, "error": f"Unknown command: {cmd}"}
    except Exception as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    _emit(result)


def main() -> None:
    parser = argparse.ArgumentParser(prog="discovery-inception")
    sub = parser.add_subparsers(dest="command", required=True)

    # ingest — the artifact-first entry point (recommended)
    p = sub.add_parser(
        "ingest",
        help=(
            "Multi-artifact ingest: feed N artifacts (calls, docs, runbooks) → "
            "produces a populated discovery session with facts captured + a "
            "gap_list.md the FDE acts on. The recommended starting command."
        ),
    )
    p.add_argument("--use-case-seed", required=True,
                   help="One-line description of what the customer wants to build.")
    p.add_argument("--artifact", action="append", required=True,
                   help="Path to an artifact file. Repeat for multiple artifacts.")
    p.add_argument("--role-id", default=None,
                   help="Optional: slug for the merged RoleContext (written to skills/<role_id>/context.json).")

    # generate-priors
    p = sub.add_parser("generate-priors", help="Run intake on a customer artifact → RoleContext on disk")
    p.add_argument("--role-id", required=True, help="Slug for the role (used as directory name)")
    p.add_argument("--artifact-text", help="Artifact text inline")
    p.add_argument("--artifact-file", help="Path to a file containing the artifact text")
    p.add_argument("--source-name", help="Name of the source (e.g. 'sc-jd.md')")

    # list-priors
    sub.add_parser("list-priors", help="List available RoleContexts in skills/")

    # get-priors
    p = sub.add_parser("get-priors", help="Inspect a RoleContext")
    p.add_argument("--role-id", required=True)

    # start-session
    p = sub.add_parser("start-session", help="Start a discovery session — tester plays customer")
    p.add_argument("--use-case-seed", required=True)
    p.add_argument("--role-id", help="Optional role_id from list-priors")
    p.add_argument(
        "--atlan-tenant",
        help="Optional Atlan host (e.g. 'ces.atlan.com'). Primes the agent with established context at session start.",
    )
    p.add_argument(
        "--atlan-glossary",
        help="Optional: scope the established-context fetch to one glossary by display name.",
    )
    p.add_argument(
        "--atlan-tables",
        help="Optional: comma-separated fully-qualified table names (e.g. 'default.aos,default.ddm').",
    )
    p.add_argument(
        "--atlan-domains",
        help="Optional: comma-separated DataDomain names (e.g. 'F&HC,Customer360').",
    )

    # submit-turn
    p = sub.add_parser(
        "submit-turn",
        help=(
            "Submit a customer turn → agent response. Pass --no-probe for "
            "FDE chat-fill mode (capture the fact, skip the follow-up question)."
        ),
    )
    p.add_argument("--session-id", required=True)
    p.add_argument("--message", required=True)
    p.add_argument(
        "--no-probe",
        action="store_true",
        help=(
            "FDE chat-fill mode: skip the mega-agent's follow-up probe. "
            "The fact still gets captured via triage + distill. Use when "
            "you're answering known gaps from gap_list.md and don't need "
            "the agent to ask anything next."
        ),
    )

    # state
    p = sub.add_parser("state", help="Inspect session state — spec, working theory, gaps")
    p.add_argument("--session-id", required=True)

    # finalize
    p = sub.add_parser("finalize", help="Close-out synthesis + export spec.md + spec.json")
    p.add_argument("--session-id", required=True)

    # list-sessions
    sub.add_parser("list-sessions", help="List existing discovery sessions on disk")

    # inception — turn the finalized spec into a starter agent design
    p = sub.add_parser(
        "inception",
        help=(
            "Run the inception pipeline against a finalized discovery session. "
            "Auto-resolves spec.md + role-context paths from the session id. "
            "Six sub-agents (3-5 min) produce a complete agent_starter/ "
            "directory with proposed skills, architecture, runtime + model, "
            "scaffolded code, eval seed, and judge harness."
        ),
    )
    p.add_argument("--session-id", required=True,
                   help="Discovery session id (sess_xxx). Must have been finalized first.")
    p.add_argument("--output-dir", default=None,
                   help="Optional output path. Default: agent_starter/<role_id_or_session_id>.")
    p.add_argument("--prior-feedback", default=None,
                   help="Optional path to a PriorIterationFeedback JSON file (Loop 2 — re-running with builder feedback).")

    args = parser.parse_args()
    asyncio.run(_async_main(args))


if __name__ == "__main__":
    main()
