"""DiscoverySession — the per-conversation state object.

Holds the running spec, the message history, and the trace-friendly per-turn
event log. Persists to disk as JSON on every mutation so a session survives
a server restart.

State mutations are explicit named methods, not direct attribute writes —
keeps the orchestrator readable and gives one place to add invariants if
they emerge.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from agent.schemas import (
    ChecklistResult,
    ConfidenceLevel,
    DiscoverySpec,
    DistilledFact,
    FactRecord,
    FlaggedGap,
    Probe,
    TopicEntry,
    TriageResult,
    WhyProbeResult,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
# SESSIONS_DIR respects the SESSIONS_DIR env var so comparison harnesses
# (e.g. tools/compare_inception.py) can point at session directories that
# live outside the working tree. Default is the in-repo sessions/ dir.
SESSIONS_DIR = (
    Path(os.environ["SESSIONS_DIR"])
    if os.environ.get("SESSIONS_DIR")
    else PROJECT_ROOT / "sessions"
)


# ---------------------------------------------------------------------------
# Conversation message + per-turn event log
# ---------------------------------------------------------------------------

Role = Literal["customer", "agent"]


class Message(BaseModel):
    role: Role
    content: str
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TurnEvent(BaseModel):
    """One sub-agent invocation within a turn. Recorded to the trace."""

    sub_agent: str
    input_summary: str
    output: dict[str, Any]
    duration_ms: int
    model: str | None = None


class Turn(BaseModel):
    """The envelope for one customer-turn → agent-turn round trip."""

    turn_index: int
    customer_message: str
    events: list[TurnEvent] = Field(default_factory=list)
    agent_message: str | None = None
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ended_at: str | None = None


# ---------------------------------------------------------------------------
# DiscoverySession — the aggregate
# ---------------------------------------------------------------------------

class DiscoverySession(BaseModel):
    session_id: str = Field(default_factory=lambda: f"sess_{uuid.uuid4().hex[:12]}")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    spec: DiscoverySpec
    messages: list[Message] = Field(default_factory=list)
    turns: list[Turn] = Field(default_factory=list)

    # ---- Persistence ----
    @property
    def session_dir(self) -> Path:
        d = SESSIONS_DIR / self.session_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save(self) -> None:
        """Persist the session to disk. Call after every mutation."""
        (self.session_dir / "session.json").write_text(self.model_dump_json(indent=2))

    # ---- Convenience lookups ----
    def find_topic(self, topic: str) -> TopicEntry | None:
        for t in self.spec.topics:
            if t.topic == topic:
                return t
        return None

    # ---- Mutations (these are the four "tools" from the original design,
    #      but called by the orchestrator, not by an LLM) ----

    def record_fact(self, fact: DistilledFact, artifact_id: str | None = None) -> TopicEntry:
        """Record a distilled fact under its topic, with provenance.

        `artifact_id` identifies which ingested artifact this fact came from
        (the stored filename, e.g. '00_call-transcript.txt'). The ingest
        pipeline passes it; live-discovery callers omit it (the fact came from
        conversation, so artifact_id stays None — that absence is the signal).
        Any `provenance_unit` the extractor emitted on the DistilledFact is
        carried onto the stored FactRecord.

        Special-cases `source = stated_overrides_prior`: instead of just
        appending the new fact, move all existing facts on this topic to
        `superseded_facts` (with a marker) before appending the new one.
        Preserves contradiction history without polluting the active spec.
        """
        entry = self.find_topic(fact.topic)
        if entry is None:
            entry = TopicEntry(topic=fact.topic)
            self.spec.topics.append(entry)

        if fact.source == "stated_overrides_prior" and entry.facts:
            for old in entry.facts:
                marker = f"[was {old.source}" + (f" @{old.artifact_id}" if old.artifact_id else "") + "]"
                entry.superseded_facts.append(f"{marker} {old.content}")
            entry.facts = []

        entry.facts.append(
            FactRecord(
                content=fact.content,
                source=fact.source,
                artifact_id=artifact_id,
                provenance_unit=fact.provenance_unit,
            )
        )
        return entry

    def flag_gap(self, gap: FlaggedGap) -> None:
        self.spec.gaps.append(gap)

    def log_pending_question(self, topic: str, question: str) -> TopicEntry:
        """Queue a question on a topic for later drilling (phase 2).

        Phase 1 uses this to log "we should drill on X later" without asking
        immediately — keeps breadth in phase 1, gives phase 2 a queue to
        prioritize from.
        """
        entry = self.find_topic(topic)
        if entry is None:
            entry = TopicEntry(topic=topic)
            self.spec.topics.append(entry)
        if question not in entry.pending_questions:
            entry.pending_questions.append(question)
        return entry

    def declare_bedrock(self, topic: str, result: WhyProbeResult) -> TopicEntry | None:
        entry = self.find_topic(topic)
        if entry is None:
            return None
        entry.bedrock_reached = True
        entry.why_chain = list(result.why_chain_so_far)
        entry.terminal_answer = result.terminal_answer
        return entry

    def declare_ready(
        self, summary: str, confidence: ConfidenceLevel, remaining: list[str]
    ) -> None:
        self.spec.declared_ready = True
        self.spec.ready_summary = summary
        self.spec.ready_confidence = confidence
        self.spec.remaining_known_gaps = list(remaining)

    # ---- Turn lifecycle ----
    def start_turn(self, customer_message: str) -> Turn:
        turn = Turn(turn_index=len(self.turns), customer_message=customer_message)
        self.turns.append(turn)
        self.messages.append(Message(role="customer", content=customer_message))
        return turn

    def end_turn(self, turn: Turn, agent_message: str) -> None:
        turn.agent_message = agent_message
        turn.ended_at = datetime.now(timezone.utc).isoformat()
        self.messages.append(Message(role="agent", content=agent_message))


# ---------------------------------------------------------------------------
# Stop-condition checklist (deterministic, no LLM)
# ---------------------------------------------------------------------------

CANONICAL_CHECKLIST_TOPICS = (
    "desired_outcome",
    "success_metric",
    "anti_goal",
    "current_pain",
    "persona",
    "decision_point",
    "escalation_rule",
    "risk",
)

# Technical-concern topics — the parallel concern thread the mega-agent should
# weave into discovery alongside the conceptual checklist above. These are not
# part of the hard stop-condition (gating to inception doesn't require them to
# all be covered), but the inception pipeline downstream needs them to produce
# defensible starter designs. The mega-agent probes for them when the customer's
# answer naturally touches a technical asset, OR when the conceptual checklist
# is largely complete and these gaps remain.
TECHNICAL_TOPICS = (
    "tech_stack",              # SDKs / frameworks / runtimes the team is committed to
    "data_sources",            # warehouses, tables, schemas, where data physically lives
    "semantic_layer",          # Cortex Analyst / dbt semantic / hand-rolled SQL / none
    "existing_context",        # what's already cataloged in Atlan or equivalent
    "runtime_target",          # where the agent eventually deploys + infra constraints
    "governance_constraints",  # must-use / can't-use / compliance
    "data_freshness",          # real-time / daily / weekly / batch
    "identity_model",          # per-user auth / service account / OAuth / etc.
)

# Convenience: complete catalog of canonical topics across both concern threads.
ALL_CANONICAL_TOPICS = CANONICAL_CHECKLIST_TOPICS + TECHNICAL_TOPICS


def topic_concern_thread(topic_name: str) -> str:
    """Classify a topic name as belonging to the 'conceptual', 'technical', or
    'other' concern thread. Used for rendering split sections in spec.md."""
    if topic_name in CANONICAL_CHECKLIST_TOPICS:
        return "conceptual"
    if topic_name in TECHNICAL_TOPICS:
        return "technical"
    return "other"

# Topics that the validator (Stage 3) cares about for bedrock. In v0.5 of the
# discovery agent, bedrock is ADVISORY — it's tracked and surfaced as a "soft"
# checklist item, but it does NOT block declare_ready. The hard stop-condition
# is left to Stage 3 once it exists.
BEDROCK_ADVISORY_TOPICS = ("why_now", "desired_outcome")

# Topics needing >= N entries (to enforce 'at least 3 decision points')
MULTI_INSTANCE_REQUIREMENTS = {
    "decision_point": 3,
}

# Phase 1 → Phase 2 transition: how many canonical topics need at least one
# fact recorded before we flip from breadth-first to drilling.
PHASE_ADVANCE_THRESHOLD = 5


def evaluate_checklist(spec: DiscoverySpec) -> ChecklistResult:
    """Pure-Python stop-condition check. No LLM call.

    Hard requirements (block declare_ready):
      - Each canonical checklist topic has at least one recorded fact
      - Decision points have at least 3 entries
    Advisory items (tracked, surfaced, but DON'T block):
      - Bedrock declared on why_now and desired_outcome
    """
    items: dict[str, bool] = {}
    missing: list[str] = []
    advisory: list[str] = []

    topics_by_name = {t.topic: t for t in spec.topics}

    for topic in CANONICAL_CHECKLIST_TOPICS:
        n_required = MULTI_INSTANCE_REQUIREMENTS.get(topic, 1)
        entry = topics_by_name.get(topic)
        ok = entry is not None and len(entry.facts) >= n_required
        items[f"has_{topic}_x{n_required}"] = ok
        if not ok:
            missing.append(
                f"{topic}: need {n_required}, have {len(entry.facts) if entry else 0}"
            )

    for topic in BEDROCK_ADVISORY_TOPICS:
        entry = topics_by_name.get(topic)
        ok = entry is not None and entry.bedrock_reached
        items[f"bedrock_on_{topic}"] = ok
        if not ok:
            advisory.append(f"(advisory) bedrock not yet on {topic}")

    return ChecklistResult(
        ready=len(missing) == 0,
        items=items,
        missing=missing + advisory,
    )


def should_advance_phase(spec: DiscoverySpec) -> bool:
    """True when phase 1 has covered enough breadth to flip to phase 2."""
    if spec.phase != "lay_of_the_land":
        return False
    topic_names = {t.topic for t in spec.topics if len(t.facts) >= 1}
    n_covered = sum(1 for t in CANONICAL_CHECKLIST_TOPICS if t in topic_names)
    return n_covered >= PHASE_ADVANCE_THRESHOLD
