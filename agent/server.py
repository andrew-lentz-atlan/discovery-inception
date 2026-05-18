"""FastAPI server for the **v0.5 chained baseline** of the discovery agent.

> **Heads up:** this is NOT the user-facing entry point. The MCP server
> (`agent/mcp_server/server.py`) is what the CLI and Claude skill drive,
> and that one runs v0.8. This file exists only for the architecture
> comparison harness (`agent/baselines/run_comparison.py`), which speaks
> to the v0.5 chained pipeline over HTTP. See
> `findings/01-architecture-comparison.md` for what gets compared.

Endpoints:
  POST /sessions                       — start a new discovery session
  POST /sessions/{session_id}/turn     — submit a customer turn (v0.5 chained)
  GET  /sessions/{session_id}          — fetch full session state
  GET  /sessions                       — list known sessions

Run (only for baseline comparison, not for real use):
    cd discovery-inception
    uv run uvicorn agent.server:app --reload --port 8010
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

from agent.orchestrator import run_turn  # noqa: E402
from agent.schemas import DiscoverySpec  # noqa: E402
from agent.state import SESSIONS_DIR, DiscoverySession  # noqa: E402


# ---------------------------------------------------------------------------
# App + LLM client
# ---------------------------------------------------------------------------

app = FastAPI(title="Discovery Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _llm_client() -> AsyncOpenAI:
    base_url = os.environ.get("LITELLM_BASE_URL", "").strip()
    api_key = os.environ.get("LITELLM_API_KEY", "").strip()
    if not base_url or not api_key:
        raise RuntimeError(
            "LITELLM_BASE_URL and LITELLM_API_KEY must be set "
            "(in your shell or in discovery-inception/.env)."
        )
    return AsyncOpenAI(base_url=base_url, api_key=api_key)


# Lazy global — same client reused across turns to keep TCP/TLS warm.
_CLIENT: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = _llm_client()
    return _CLIENT


# ---------------------------------------------------------------------------
# Session persistence helpers
# ---------------------------------------------------------------------------

def _load_session(session_id: str) -> DiscoverySession:
    session_path = SESSIONS_DIR / session_id / "session.json"
    if not session_path.exists():
        raise HTTPException(404, f"Session not found: {session_id}")
    return DiscoverySession.model_validate_json(session_path.read_text())


# ---------------------------------------------------------------------------
# Request/response shapes
# ---------------------------------------------------------------------------

class CreateSessionRequest(BaseModel):
    use_case_seed: str = Field(
        ...,
        description="One-line fuzzy goal. Example: 'we want a SoCo agent for new-customer onboarding at TechCo'.",
    )
    role_id: str | None = Field(
        None,
        description="Optional RoleContext skill id to use as priors (e.g. 'solutions-consultant').",
    )


class TurnRequest(BaseModel):
    message: str = Field(..., description="The customer's turn.")


class TurnResponse(BaseModel):
    agent_message: str
    triage_label: str
    bedrock_topics: list[str]
    checklist_missing: list[str]
    declared_ready: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/sessions")
def create_session(req: CreateSessionRequest) -> dict:
    spec = DiscoverySpec(use_case_seed=req.use_case_seed, role_id=req.role_id)
    session = DiscoverySession(spec=spec)
    session.save()
    return {
        "session_id": session.session_id,
        "use_case_seed": req.use_case_seed,
        "role_id": req.role_id,
        "opening_probe": (
            "Let's start at the top. In one sentence: what would success "
            "look like for this agent — measured how, and by when?"
        ),
    }


@app.post("/sessions/{session_id}/turn", response_model=TurnResponse)
async def submit_turn(session_id: str, req: TurnRequest) -> TurnResponse:
    session = _load_session(session_id)
    client = get_client()
    turn, checklist = await run_turn(client, session, req.message)
    bedrock = [t.topic for t in session.spec.topics if t.bedrock_reached]
    return TurnResponse(
        agent_message=turn.agent_message or "(no probe generated)",
        triage_label=next(
            (e.output.get("label", "?") for e in turn.events if e.sub_agent == "triage"),
            "?",
        ),
        bedrock_topics=bedrock,
        checklist_missing=checklist.missing,
        declared_ready=session.spec.declared_ready,
    )


@app.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    session = _load_session(session_id)
    return json.loads(session.model_dump_json())


@app.get("/sessions")
def list_sessions() -> list[dict]:
    if not SESSIONS_DIR.exists():
        return []
    out: list[dict] = []
    for d in sorted(SESSIONS_DIR.iterdir()):
        if not d.is_dir():
            continue
        path = d / "session.json"
        if not path.exists():
            continue
        try:
            session = DiscoverySession.model_validate_json(path.read_text())
        except Exception:
            continue
        out.append(
            {
                "session_id": session.session_id,
                "created_at": session.created_at,
                "use_case_seed": session.spec.use_case_seed,
                "turns": len(session.turns),
                "declared_ready": session.spec.declared_ready,
            }
        )
    return out


@app.get("/")
def index() -> dict:
    return {"app": "discovery-agent", "version": "0.1.0"}
