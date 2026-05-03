"""Pydantic schemas for the intake agent.

These are the contracts the prompts are tuned to fill. The intake agent's
whole job is to take an unstructured artifact and produce a RoleContext
object. Every other intake module reads from / writes to these types.
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Sub-types
# ---------------------------------------------------------------------------

class Workflow(BaseModel):
    """A named end-to-end flow the role executes."""
    name: str = Field(..., description="Short noun phrase. Example: 'onboard new customer'.")
    purpose: str = Field(..., description="Why this workflow exists. One sentence.")
    trigger: str = Field(..., description="What initiates the workflow.")
    steps: list[str] = Field(default_factory=list, description="Ordered steps the role takes, as written or implied.")
    typical_duration: str | None = Field(None, description="If mentioned: how long this normally takes.")


class Decision(BaseModel):
    """A judgment moment in the role's work."""
    name: str = Field(..., description="Short label. Example: 'choose escalation path'.")
    inputs: list[str] = Field(default_factory=list, description="What information the role consults to make this decision.")
    criteria: list[str] = Field(default_factory=list, description="Rules or heuristics that govern the decision, as stated.")
    is_judgment: bool = Field(False, description="True if criteria are partly subjective; False if rule-based.")


class Escalation(BaseModel):
    """When and how the role hands off to someone else."""
    trigger: str = Field(..., description="The condition under which escalation happens.")
    handoff_target: str = Field(..., description="Who receives the escalation. Role/team name preferred.")
    artifacts_passed: list[str] = Field(default_factory=list, description="What information goes with the handoff.")


class EdgeCase(BaseModel):
    """A non-routine situation the role handles."""
    description: str = Field(..., description="What makes this an edge case.")
    handling: str | None = Field(None, description="How the role handles it, if stated.")


class Unknown(BaseModel):
    """An explicit gap in the source material that the discovery agent should probe."""
    field: str = Field(..., description="What's missing. Example: 'escalation path for refund > $500'.")
    why_it_matters: str = Field(..., description="Why this gap matters for designing an agent.")
    probe_suggestion: str = Field(..., description="A specific question to ask the customer to fill the gap.")


# ---------------------------------------------------------------------------
# Top-level: RoleContext
# ---------------------------------------------------------------------------

class RoleContext(BaseModel):
    """Structured representation of a role's tribal knowledge.

    Produced by the intake agent. Consumed by the discovery agent as a skill
    that provides priors during the discovery conversation.
    """

    role_name: str = Field(..., description="Canonical role name. Example: 'Solutions Consultant'.")
    role_summary: str = Field(..., description="2-3 sentences on what the role exists to do.")
    primary_outcomes: list[str] = Field(
        default_factory=list,
        description="Measurable success states. Each should be specific (named outcome, ideally with a metric).",
    )
    typical_workflows: list[Workflow] = Field(default_factory=list)
    decision_criteria: list[Decision] = Field(default_factory=list)
    escalation_paths: list[Escalation] = Field(default_factory=list)
    domain_vocabulary: dict[str, str] = Field(
        default_factory=dict,
        description="Role-specific terms and definitions. Keys are terms, values are definitions.",
    )
    common_edge_cases: list[EdgeCase] = Field(default_factory=list)
    unwritten_rules: list[str] = Field(
        default_factory=list,
        description=(
            "Heuristics, biases, soft rules captured from the source. These are the most "
            "valuable extractions: things experienced practitioners do automatically that "
            "are rarely formalized. Examples: 'when 50/50, the customer wins'."
        ),
    )
    confidence_per_field: dict[str, float] = Field(
        default_factory=dict,
        description="Per-top-level-field confidence score (0.0-1.0). Set by the confidence scorer.",
    )
    flagged_unknowns: list[Unknown] = Field(
        default_factory=list,
        description="Things the source doesn't cover. Input to the discovery agent's gap finder.",
    )
    source_artifacts: list[str] = Field(
        default_factory=list,
        description="Filenames or URLs of the source artifacts this context was extracted from.",
    )


# ---------------------------------------------------------------------------
# Per-step intermediate types (so each prompt has a typed contract)
# ---------------------------------------------------------------------------

ArtifactType = Literal[
    "job_description",
    "runbook",
    "process_doc",
    "interview_transcript",
    "slack_thread",
    "meeting_notes",
    "policy_doc",
    "other",
]


class ClassificationResult(BaseModel):
    artifact_type: ArtifactType
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str = Field(..., description="One sentence: why you picked this type.")


class ExtractionResult(BaseModel):
    """Output of step 2 — initial structured extraction."""
    role_name: str
    role_summary: str
    primary_outcomes: list[str] = Field(default_factory=list)
    typical_workflows: list[Workflow] = Field(default_factory=list)
    decision_criteria: list[Decision] = Field(default_factory=list)
    escalation_paths: list[Escalation] = Field(default_factory=list)
    common_edge_cases: list[EdgeCase] = Field(default_factory=list)


class VocabularyResult(BaseModel):
    """Output of step 3 — deduplicated, defined domain terms."""
    domain_vocabulary: dict[str, str] = Field(default_factory=dict)
    synonyms_collapsed: list[str] = Field(
        default_factory=list,
        description="Notes on synonyms that were merged. Useful for debugging extraction quality.",
    )


class UnwrittenRulesResult(BaseModel):
    """Output of step 4 — implicit heuristics and soft rules."""
    rules: list[str] = Field(default_factory=list)
    candidate_quotes: list[str] = Field(
        default_factory=list,
        description="The source-text snippets each rule was derived from. Aids verification.",
    )


class GapReport(BaseModel):
    """Output of step 5 — what's missing from the source."""
    flagged_unknowns: list[Unknown] = Field(default_factory=list)


class ConfidenceReport(BaseModel):
    """Output of step 6 — per-field confidence with rationale."""
    confidence_per_field: dict[str, float] = Field(default_factory=dict)
    rationales: dict[str, str] = Field(
        default_factory=dict,
        description="One-line rationale per field. Same keys as confidence_per_field.",
    )
