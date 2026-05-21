"""CLI wrapper around the discovery-inception tools (same functions the
MCP server exposes, just shell-friendly).

Designed for use by the Claude skill, by colleagues comfortable in
terminal, or by scripts that want to drive a discovery without going
through MCP.

Subcommands match the MCP tool names so the skill can drop in either
transport.

Usage:
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

from agent.mcp_server.server import (  # noqa: E402
    tool_generate_priors,
    tool_list_priors,
    tool_get_priors,
    tool_start_discovery_session,
    tool_submit_customer_turn,
    tool_get_session_state,
    tool_finalize_discovery_session,
    tool_list_sessions,
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
        if cmd == "generate-priors":
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
            )
        elif cmd == "state":
            result = tool_get_session_state(session_id=args.session_id)
        elif cmd == "finalize":
            result = await tool_finalize_discovery_session(session_id=args.session_id)
        elif cmd == "list-sessions":
            result = tool_list_sessions()
        else:
            result = {"ok": False, "error": f"Unknown command: {cmd}"}
    except Exception as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    _emit(result)


def main() -> None:
    parser = argparse.ArgumentParser(prog="discovery-inception")
    sub = parser.add_subparsers(dest="command", required=True)

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
    p = sub.add_parser("submit-turn", help="Submit a customer turn → agent response")
    p.add_argument("--session-id", required=True)
    p.add_argument("--message", required=True)

    # state
    p = sub.add_parser("state", help="Inspect session state — spec, working theory, gaps")
    p.add_argument("--session-id", required=True)

    # finalize
    p = sub.add_parser("finalize", help="Close-out synthesis + export spec.md + spec.json")
    p.add_argument("--session-id", required=True)

    # list-sessions
    sub.add_parser("list-sessions", help="List existing discovery sessions on disk")

    args = parser.parse_args()
    asyncio.run(_async_main(args))


if __name__ == "__main__":
    main()
