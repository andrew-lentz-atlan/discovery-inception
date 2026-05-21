"""Pydantic models for the inception pipeline.

Each sub-agent emits a typed intermediate. The final output is an
agent_starter/ directory + a design_rationale.md with pattern citations.

This module currently defines schemas for step 1 (workload_classifier).
Downstream sub-agents' schemas will be added as they are implemented.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Step 1: workload_classifier
# ---------------------------------------------------------------------------

InteractionShape = Literal[
    "conversational",   # multi-turn dialogue with adaptive routing
    "query-response",   # one question → multi-step lookup → structured answer
    "batch",            # process N items / artifacts in sequence, no interaction
    "streaming",        # real-time or near-real-time stream of inputs
]


LatencySensitivity = Literal[
    "real-time",          # sub-second to ~2s targets (voice, live UI)
    "near-real-time",     # 5-15s acceptable (interactive analyst UIs)
    "tolerant",           # 30s-many-minutes acceptable (async batch, long-horizon)
]


DecisionComplexity = Literal[
    "deterministic",      # answers follow a fixed rule (SQL classification, etc.)
    "rule-based",         # multiple rules with conditional branching
    "judgment-heavy",     # subjective calls; need an LLM to reason
]


DataIntensity = Literal[
    "light",              # < 100 rows / < 5KB per skill call
    "moderate",           # 100-10K rows / 5KB-500KB per skill call
    "heavy",              # 10K+ rows / 500KB+ per skill call (data shaping needed)
]


MultiStepOrSingleStep = Literal[
    "single",             # one tool call resolves the workload
    "multi",              # multiple tool calls (or sub-agent invocations) needed
]


StateShape = Literal[
    "stateless",          # each invocation independent
    "session-scoped",     # state persists within a session but not across
    "long-horizon",       # state persists across many sessions / requires durability
]


class WorkloadClassification(BaseModel):
    """Output of step 1 — workload_classifier."""

    interaction_shape: InteractionShape = Field(
        ..., description="The primary shape of agent-user interaction."
    )
    latency_sensitivity: LatencySensitivity = Field(
        ..., description="How much latency the workload tolerates per response."
    )
    decision_complexity: DecisionComplexity = Field(
        ..., description="How much judgment vs. rules the decisions require."
    )
    data_intensity: DataIntensity = Field(
        ..., description="Volume of data per typical skill invocation."
    )
    multi_step_or_single_step: MultiStepOrSingleStep = Field(
        ..., description="Whether the workload is one-tool or multi-tool."
    )
    state_shape: StateShape = Field(
        ..., description="How state persists across invocations."
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Classifier confidence 0.0–1.0."
    )
    rationale: str = Field(
        ..., description=(
            "1-3 sentences explaining the classification. Cite specific evidence "
            "from the spec (e.g., 'role_summary mentions executive narrative reports — "
            "data_intensity is moderate-heavy because the analyst queries 52 weeks of "
            "data per question')."
        )
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description=(
            "Aspects of the workload the spec doesn't unambiguously settle. The downstream "
            "proposer sub-agents should treat these as flagged uncertainties when narrowing "
            "their candidate set."
        ),
    )


# ---------------------------------------------------------------------------
# Subsequent steps' schemas will be added here as they are implemented:
#   - SkillProposal       (skill_proposer)
#   - SkillCritique       (skill_critic)
#   - ArchitectureProposal
#   - ArchitectureCritique
#   - RuntimeProposal
#   - ScaffoldArtifact (the agent_starter/ contents)
# ---------------------------------------------------------------------------
