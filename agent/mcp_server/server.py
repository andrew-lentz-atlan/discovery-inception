"""MCP server exposing the v0.8 discovery agent + the intake (priors)
pipeline as tools Claude Code / Claude Desktop can invoke.

This is the canonical user-facing entry point. The MCP tools, the CLI
(`agent.cli`, which thin-wraps these tools), and the Claude skill
(`claude-skill/SKILL.md`, which drives the CLI) all run through here —
so flipping the orchestrator import below changes the version every
external user gets.

Currently wired to `agent.v08.orchestrator` (sharpener + tensions +
deterministic close-out). To run an older version for comparison,
swap the import. To keep this honest, only flip after smoke-testing
the new pipeline end-to-end through the MCP path.

The colleague's experience:
  - One-time: add this server to their Claude Code/Desktop MCP config.
  - Open Claude, say "build a SoCo agent for onboarding at TechCo —
    here's a job description" and Claude calls generate_priors, then
    start_discovery_session, then submit_customer_turn turn-by-turn as
    the colleague (playing customer) answers, then finalize_discovery_
    session to export a spec.md.

The tester ALWAYS plays customer. The mega-agent is the FDE.

Eight tools across two groups:

  Priors / intake:
    generate_priors(artifact_text, role_id, source_name?)
    list_priors()
    get_priors(role_id)

  Discovery:
    start_discovery_session(use_case_seed, role_id?)
    submit_customer_turn(session_id, message)
    get_session_state(session_id)
    finalize_discovery_session(session_id)
    list_sessions()
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

from agent.atlan_client import fetch_bounded_context  # noqa: E402
from agent.baselines.mega_agent import MegaAgentSession  # noqa: E402
from agent.schemas import DiscoverySpec, WorkingTheory  # noqa: E402
from agent.state import DiscoverySession  # noqa: E402
from agent.v08.orchestrator import run_v08_turn, run_final_synthesis  # noqa: E402
from intake.run import run_intake  # noqa: E402

SKILLS_DIR = PROJECT_ROOT / "skills"
SESSIONS_DIR = PROJECT_ROOT / "sessions"


# ---------------------------------------------------------------------------
# Shared state (in-memory) — keyed by session_id
# ---------------------------------------------------------------------------

# Mega-agent conversational state per discovery session. Survives within one
# MCP server process; rehydrated from disk if a previously-saved session is
# referenced after a restart.
_MEGA_SESSIONS: dict[str, MegaAgentSession] = {}

_OPENAI_CLIENT: AsyncOpenAI | None = None


def _llm_client() -> AsyncOpenAI:
    global _OPENAI_CLIENT
    if _OPENAI_CLIENT is None:
        base_url = os.environ.get("LITELLM_BASE_URL", "").strip()
        api_key = os.environ.get("LITELLM_API_KEY", "").strip()
        if not base_url or not api_key:
            raise RuntimeError(
                "LITELLM_BASE_URL and LITELLM_API_KEY must be set (shell or "
                "discovery-inception/.env) for the MCP server to run."
            )
        _OPENAI_CLIENT = AsyncOpenAI(base_url=base_url, api_key=api_key)
    return _OPENAI_CLIENT


def _rehydrate_mega_session(session: DiscoverySession) -> MegaAgentSession:
    """Reconstruct a MegaAgentSession from persisted session.messages.

    Called when an MCP tool references a session_id whose mega-agent
    conversation history isn't in memory (process restart, fresh session
    on disk, etc.).
    """
    mega = MegaAgentSession(
        use_case_seed=session.spec.use_case_seed,
        role_id=session.spec.role_id,
    )
    # Rebuild the OpenAI-shape message list from persisted session.messages.
    # We use the persisted "messages" array — alternating customer/agent —
    # as the source of truth for what the mega-agent has seen.
    for msg in session.messages:
        role = "user" if msg.role == "customer" else "assistant"
        mega.messages.append({"role": role, "content": msg.content})
    return mega


def _get_or_rehydrate_session(session_id: str) -> tuple[DiscoverySession, MegaAgentSession]:
    """Load a session from disk (and rehydrate mega-state if needed)."""
    session_file = SESSIONS_DIR / session_id / "session.json"
    if not session_file.exists():
        raise ValueError(f"Session not found: {session_id}")
    raw = json.loads(session_file.read_text())
    spec = DiscoverySpec.model_validate(raw["spec"])
    session = DiscoverySession(spec=spec)
    # Restore the persistent fields we care about
    session.session_id = raw["session_id"]
    from agent.state import Message, Turn, TurnEvent

    session.messages = [Message.model_validate(m) for m in raw.get("messages", [])]
    session.turns = [Turn.model_validate(t) for t in raw.get("turns", [])]

    mega = _MEGA_SESSIONS.get(session_id)
    if mega is None:
        mega = _rehydrate_mega_session(session)
        _MEGA_SESSIONS[session_id] = mega
    return session, mega


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def tool_generate_priors(
    artifact_text: str,
    role_id: str,
    source_name: str = "pasted_artifact",
) -> dict[str, Any]:
    """Run the 6-step intake pipeline on a customer artifact (JD, runbook,
    transcript, etc.) and produce a structured RoleContext on disk."""
    client = _llm_client()
    role_context = await run_intake(artifact_text, source_filename=source_name)

    # Write to skills/<role_id>/context.json
    target_dir = SKILLS_DIR / role_id
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "context.json").write_text(role_context.model_dump_json(indent=2))

    return {
        "ok": True,
        "role_id": role_id,
        "role_summary": role_context.role_summary,
        "n_topics_covered": len(role_context.typical_workflows or []),
        "n_vocab_terms": len(role_context.domain_vocabulary or {}),
        "n_unwritten_rules": len(role_context.unwritten_rules or []),
        "n_flagged_unknowns": len(role_context.flagged_unknowns or []),
        "saved_to": str(target_dir / "context.json"),
        "use_with_discovery": f"start_discovery_session(use_case_seed=..., role_id='{role_id}')",
    }


def tool_list_priors() -> dict[str, Any]:
    """List available RoleContexts (priors) in skills/."""
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    available: list[dict] = []
    for entry in sorted(SKILLS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        context_path = entry / "context.json"
        if not context_path.exists():
            continue
        try:
            rc = json.loads(context_path.read_text())
            available.append({
                "role_id": entry.name,
                "role_summary": rc.get("role_summary", "")[:200],
                "n_vocab_terms": len(rc.get("domain_vocabulary") or {}),
                "n_unwritten_rules": len(rc.get("unwritten_rules") or []),
                "n_flagged_unknowns": len(rc.get("flagged_unknowns") or []),
            })
        except Exception as exc:
            available.append({"role_id": entry.name, "error": str(exc)[:100]})
    return {"ok": True, "n_available": len(available), "available": available}


def tool_get_priors(role_id: str) -> dict[str, Any]:
    """Inspect a RoleContext — returns the full JSON."""
    context_path = SKILLS_DIR / role_id / "context.json"
    if not context_path.exists():
        return {"ok": False, "error": f"No priors for role_id={role_id!r}"}
    return {"ok": True, "role_id": role_id, "role_context": json.loads(context_path.read_text())}


async def tool_start_discovery_session(
    use_case_seed: str,
    role_id: str | None = None,
    atlan_tenant: str | None = None,
    atlan_glossary: str | None = None,
    atlan_tables: list[str] | None = None,
    atlan_domains: list[str] | None = None,
) -> dict[str, Any]:
    """Start a new discovery session. The tester plays the customer; the
    mega-agent runs the FDE interview. No initial probe is generated —
    submit the customer's opening message first.

    Atlan integration (optional): if `atlan_tenant` is provided (or
    `ATLAN_BASE_URL` is set), the discovery agent queries the named scope
    at session start. Cataloged glossary terms, table schemas, lineage,
    ownership, governance tags, and business domains land in the
    mega-agent's system prompt as authoritative "established context" —
    technical-thread probes skip what's already known. Graceful degradation:
    if Atlan is unavailable, discovery runs in probe-only mode and a
    warning surfaces in the session state.
    """
    spec = DiscoverySpec(use_case_seed=use_case_seed, role_id=role_id)

    # Attempt the bounded-context fetch when any Atlan scope arg is set,
    # OR when env vars are configured even without explicit args (assumes
    # the user wants integration on but hasn't named a scope — we'll return
    # an empty bounded context with fetch_status='not_configured' to be
    # transparent rather than guessing a default scope).
    any_atlan_arg = atlan_tenant or atlan_glossary or atlan_tables or atlan_domains
    if any_atlan_arg:
        bc = await fetch_bounded_context(
            tenant=atlan_tenant,
            glossary=atlan_glossary,
            tables=atlan_tables,
            domains=atlan_domains,
        )
        spec.bounded_context = bc.model_dump()
    session = DiscoverySession(spec=spec)
    mega = MegaAgentSession(use_case_seed=use_case_seed, role_id=role_id)
    _MEGA_SESSIONS[session.session_id] = mega
    session.save()
    response: dict[str, Any] = {
        "ok": True,
        "session_id": session.session_id,
        "use_case_seed": use_case_seed,
        "role_id": role_id,
        "next_step": (
            f"Call submit_customer_turn(session_id='{session.session_id}', "
            "message=<your_first_message_as_customer>)."
        ),
    }
    if spec.bounded_context:
        bc_status = spec.bounded_context.get("fetch_status")
        response["atlan_context"] = {
            "tenant": spec.bounded_context.get("source_tenant"),
            "status": bc_status,
            "n_glossary_terms": len(spec.bounded_context.get("glossary_terms") or []),
            "n_tables": len(spec.bounded_context.get("tables") or []),
            "n_lineage_edges": len(
                (spec.bounded_context.get("lineage") or {}).get("edges") or []
            ),
            "n_business_domains": len(spec.bounded_context.get("business_domains") or []),
            "error": spec.bounded_context.get("error_message"),
        }
    return response


async def tool_submit_customer_turn(
    session_id: str,
    message: str,
) -> dict[str, Any]:
    """Submit a customer turn. Runs the v0.8 pipeline (triage → distill →
    mega-agent with 4 tools → probe-sharpener) and returns the agent's
    response + state summary."""
    client = _llm_client()
    session, mega = _get_or_rehydrate_session(session_id)
    turn, checklist = await run_v08_turn(client, session, mega, message)
    return {
        "ok": True,
        "session_id": session_id,
        "turn_index": turn.turn_index,
        "agent_response": turn.agent_message,
        "triage_label": next(
            (e.output.get("label") for e in turn.events if e.sub_agent == "triage"),
            None,
        ),
        "checklist_missing": checklist.missing,
        "declared_ready": session.spec.declared_ready,
    }


def tool_get_session_state(session_id: str) -> dict[str, Any]:
    """Inspect the current structured state of a session."""
    session, _ = _get_or_rehydrate_session(session_id)
    spec = session.spec.model_dump()
    payload: dict[str, Any] = {
        "ok": True,
        "session_id": session_id,
        "phase": spec.get("phase"),
        "n_topics": len(spec.get("topics", [])),
        "n_facts": sum(len(t.get("facts", [])) for t in spec.get("topics", [])),
        "n_gaps": len(spec.get("gaps", [])),
        "n_turns": len(session.turns),
        "working_theory": spec.get("working_theory"),
        "full_spec": spec,
    }
    bc = spec.get("bounded_context")
    if bc:
        payload["atlan_context_summary"] = {
            "tenant": bc.get("source_tenant"),
            "status": bc.get("fetch_status"),
            "n_glossary_terms": len(bc.get("glossary_terms") or []),
            "n_tables": len(bc.get("tables") or []),
            "n_lineage_edges": len((bc.get("lineage") or {}).get("edges") or []),
            "n_business_domains": len(bc.get("business_domains") or []),
        }
    return payload


async def tool_finalize_discovery_session(session_id: str) -> dict[str, Any]:
    """Run the deterministic close-out synthesis and export the spec brief.

    Writes:
      sessions/<session_id>/spec.json  — machine-readable
      sessions/<session_id>/spec.md    — human-readable brief
    """
    client = _llm_client()
    session, _ = _get_or_rehydrate_session(session_id)
    final_theory = await run_final_synthesis(client, session)

    spec = session.spec
    session_dir = SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "spec.json").write_text(spec.model_dump_json(indent=2))

    md = _render_spec_markdown(session)
    (session_dir / "spec.md").write_text(md)

    return {
        "ok": True,
        "session_id": session_id,
        "spec_md_path": str(session_dir / "spec.md"),
        "spec_json_path": str(session_dir / "spec.json"),
        "final_theory": final_theory.model_dump(),
        "n_topics": len(spec.topics),
        "n_facts": sum(len(t.facts) for t in spec.topics),
        "n_gaps": len(spec.gaps),
        "confidence": final_theory.confidence,
    }


def tool_list_sessions() -> dict[str, Any]:
    """List existing discovery sessions on disk."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    sessions: list[dict] = []
    for entry in sorted(SESSIONS_DIR.iterdir()):
        if not entry.is_dir() or not entry.name.startswith("sess_"):
            continue
        path = entry / "session.json"
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text())
            spec = raw.get("spec", {})
            sessions.append({
                "session_id": raw.get("session_id", entry.name),
                "use_case_seed": spec.get("use_case_seed", "")[:120],
                "role_id": spec.get("role_id"),
                "phase": spec.get("phase"),
                "n_turns": len(raw.get("turns", [])),
                "n_topics": len(spec.get("topics", [])),
            })
        except Exception as exc:
            sessions.append({"session_id": entry.name, "error": str(exc)[:100]})
    return {"ok": True, "n_sessions": len(sessions), "sessions": sessions}


# ---------------------------------------------------------------------------
# Spec markdown renderer
# ---------------------------------------------------------------------------

def _render_spec_markdown(session: DiscoverySession) -> str:
    """Render the structured spec as a builder-readable brief."""
    spec = session.spec
    wt = spec.working_theory

    lines: list[str] = []
    lines.append(f"# Discovery spec: {spec.use_case_seed}")
    lines.append("")
    lines.append(f"**Session:** `{session.session_id}`")
    lines.append(f"**Role priors:** `{spec.role_id or 'none'}`")
    lines.append(f"**Phase at close:** `{spec.phase}`")
    if wt:
        lines.append(f"**Working theory confidence:** `{wt.confidence}`")
    if spec.bounded_context:
        bc = spec.bounded_context
        status = bc.get("fetch_status", "unknown")
        n_terms = len(bc.get("glossary_terms") or [])
        n_tables = len(bc.get("tables") or [])
        lines.append(
            f"**Atlan context:** `{bc.get('source_tenant', '?')}` "
            f"(status: {status}, {n_terms} terms, {n_tables} tables)"
        )
    lines.append("")

    if wt:
        lines.append("## Working theory")
        lines.append("")
        lines.append(f"> {wt.one_line_framing}")
        lines.append("")
        if wt.candidate_framings:
            lines.append("**Alternative framings the data could also support:**")
            for cf in wt.candidate_framings:
                lines.append(f"- {cf}")
            lines.append("")
        if wt.open_questions:
            lines.append("**Open questions that would sharpen this theory:**")
            for q in wt.open_questions:
                lines.append(f"- {q}")
            lines.append("")
        if wt.sharpest_disconfirmer:
            lines.append("**Sharpest disconfirmer** (what would prove this theory wrong):")
            lines.append("")
            lines.append(f"> {wt.sharpest_disconfirmer}")
            lines.append("")

    # Split topics into conceptual / technical / other concern threads.
    # The split is for reader clarity — the inception pipeline downstream
    # consumes the conceptual half to set up the agent's behavior and the
    # technical half to settle architecture / runtime / data-source choices.
    from agent.state import topic_concern_thread

    conceptual_topics = [t for t in spec.topics if topic_concern_thread(t.topic) == "conceptual"]
    technical_topics = [t for t in spec.topics if topic_concern_thread(t.topic) == "technical"]
    other_topics = [t for t in spec.topics if topic_concern_thread(t.topic) == "other"]

    def _render_topic_block(t):
        block: list[str] = []
        bedrock = " — **BEDROCK**" if t.bedrock_reached else ""
        block.append(f"### `{t.topic}`{bedrock}")
        for fact, source in zip(t.facts, t.sources):
            block.append(f"- **[{source}]** {fact}")
        if t.superseded_facts:
            block.append("")
            block.append("Superseded:")
            for f in t.superseded_facts:
                block.append(f"  - {f}")
        block.append("")
        return block

    if not spec.topics:
        lines.append("## Captured topics + facts")
        lines.append("")
        lines.append("*(no facts captured)*")
        lines.append("")
    else:
        if conceptual_topics:
            lines.append("## Conceptual context")
            lines.append("")
            lines.append("*(persona, current pain, success metrics, anti-goals, decision points, escalation rules, risks)*")
            lines.append("")
            for t in conceptual_topics:
                lines.extend(_render_topic_block(t))

        if technical_topics:
            lines.append("## Technical context")
            lines.append("")
            lines.append("*(tech stack, data sources, semantic layer, existing context, runtime target, governance, data freshness, identity model — consumed by the inception pipeline to settle architecture + runtime choices)*")
            lines.append("")
            for t in technical_topics:
                lines.extend(_render_topic_block(t))

        if other_topics:
            lines.append("## Other captured topics")
            lines.append("")
            lines.append("*(topics outside the conceptual/technical canonical sets — domain-specific or use-case-specific concerns)*")
            lines.append("")
            for t in other_topics:
                lines.extend(_render_topic_block(t))

    if spec.gaps:
        lines.append("## Flagged gaps for FDE follow-up")
        lines.append("")
        for g in spec.gaps:
            lines.append(f"- **{g.question}**")
            lines.append(f"  - Why it matters: {g.why_it_matters}")
            if g.related_topic:
                lines.append(f"  - Related topic: `{g.related_topic}`")
            lines.append("")

    # Established context appendix (Atlan) — verbatim what the agent saw.
    # Downstream inception reads this to know what's cataloged vs what came
    # from the customer's own statements. We bump the inner heading from H3
    # to H2 so it slots into spec.md alongside other top-level sections.
    if spec.bounded_context:
        try:
            from agent.atlan_context import BoundedContext

            bc = BoundedContext.model_validate(spec.bounded_context)
            rendered = bc.render_for_prompt()
            if rendered.strip():
                rendered = rendered.replace("### Established context", "## Established context", 1)
                lines.append(rendered.rstrip())
                lines.append("")
        except Exception:
            # Renderer is best-effort — never block spec.md export on this.
            pass

    lines.append("---")
    lines.append("")
    lines.append("*Generated by discovery-inception v0.8 (lazy synthesis + probe-sharpener + tensions surfacing + deterministic close-out).*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MCP server registration
# ---------------------------------------------------------------------------

server = Server("discovery-inception")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="generate_priors",
            description=(
                "Run the 6-step intake pipeline on a customer artifact (job "
                "description, runbook, transcript, success plan, etc.) to "
                "produce a structured RoleContext. The output saves to "
                "skills/<role_id>/context.json and can be passed as role_id "
                "to start_discovery_session for vocabulary mirroring + "
                "scaffolding during discovery."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "artifact_text": {
                        "type": "string",
                        "description": "The customer artifact verbatim — JD, runbook, transcript, etc. Paste the full text.",
                    },
                    "role_id": {
                        "type": "string",
                        "description": "A short kebab-case slug for this role (e.g. 'solutions-consultant-techco'). Used as the directory name under skills/.",
                    },
                    "source_name": {
                        "type": "string",
                        "description": "Optional: name of the source (e.g. 'sc-job-description.md'). Defaults to 'pasted_artifact'.",
                    },
                },
                "required": ["artifact_text", "role_id"],
            },
        ),
        types.Tool(
            name="list_priors",
            description="List available RoleContexts (priors) in skills/. Use to find an existing role_id for start_discovery_session.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="get_priors",
            description="Inspect a RoleContext by role_id — returns the full structured priors.",
            inputSchema={
                "type": "object",
                "properties": {"role_id": {"type": "string"}},
                "required": ["role_id"],
            },
        ),
        types.Tool(
            name="start_discovery_session",
            description=(
                "Start a new discovery session. The user plays the CUSTOMER; "
                "the discovery agent plays the FDE interviewer. No initial "
                "agent question is generated — submit your first customer "
                "message via submit_customer_turn to begin the interview. "
                "Optional Atlan integration: pass atlan_tenant + scope args "
                "(glossary, tables, domains) to prime the agent with the "
                "customer's established context — cataloged definitions, "
                "table schemas, lineage, ownership, governance tags. "
                "Discovery proceeds normally if Atlan is unavailable."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "use_case_seed": {
                        "type": "string",
                        "description": "One-line description of what the customer wants to build, e.g. 'we want a SoCo agent for new-customer onboarding at TechCo'.",
                    },
                    "role_id": {
                        "type": "string",
                        "description": "Optional: role_id from list_priors (e.g. 'solutions-consultant'). Without priors the agent still works but won't mirror domain vocabulary.",
                    },
                    "atlan_tenant": {
                        "type": "string",
                        "description": "Optional: Atlan tenant host (e.g. 'ces.atlan.com'). When set, discovery fetches the customer's established context at session start.",
                    },
                    "atlan_glossary": {
                        "type": "string",
                        "description": "Optional: scope the established-context fetch to one glossary by display name (e.g. 'Fabric_Care_Analytics').",
                    },
                    "atlan_tables": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional: list of fully-qualified table names to pull schemas/columns/ownership for (e.g. ['default.aos', 'default.ddm']).",
                    },
                    "atlan_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional: list of DataDomain names to pull descriptions for (e.g. ['F&HC']).",
                    },
                },
                "required": ["use_case_seed"],
            },
        ),
        types.Tool(
            name="submit_customer_turn",
            description=(
                "Submit a customer turn (the user, playing customer, speaks). "
                "Runs triage → distill → optional mega-agent lazy synth → "
                "mega-agent response. Returns the agent's next message + "
                "state summary (triage label, checklist gaps)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "message": {
                        "type": "string",
                        "description": "The customer's verbatim response to the agent's last probe.",
                    },
                },
                "required": ["session_id", "message"],
            },
        ),
        types.Tool(
            name="get_session_state",
            description="Inspect the structured state of a discovery session — topics, facts, gaps, working theory. Use to see what's been captured before finalizing.",
            inputSchema={
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
            },
        ),
        types.Tool(
            name="finalize_discovery_session",
            description=(
                "Wrap up a discovery session: runs the deterministic close-out "
                "synthesis with the full conversation in scope, then exports a "
                "spec.md (human-readable brief for the FDE/builder) and "
                "spec.json (machine-readable) under sessions/<session_id>/. "
                "Call this when the user signals the discovery is complete."
            ),
            inputSchema={
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
            },
        ),
        types.Tool(
            name="list_sessions",
            description="List existing discovery sessions on disk — useful for resuming or inspecting prior runs.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    try:
        if name == "generate_priors":
            result = await tool_generate_priors(**arguments)
        elif name == "list_priors":
            result = tool_list_priors()
        elif name == "get_priors":
            result = tool_get_priors(**arguments)
        elif name == "start_discovery_session":
            result = await tool_start_discovery_session(**arguments)
        elif name == "submit_customer_turn":
            result = await tool_submit_customer_turn(**arguments)
        elif name == "get_session_state":
            result = tool_get_session_state(**arguments)
        elif name == "finalize_discovery_session":
            result = await tool_finalize_discovery_session(**arguments)
        elif name == "list_sessions":
            result = tool_list_sessions()
        else:
            result = {"ok": False, "error": f"unknown tool: {name}"}
    except Exception as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


async def run() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
