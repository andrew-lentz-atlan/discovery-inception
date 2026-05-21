"""Pydantic models for the inception pipeline.

Each sub-agent emits a typed intermediate. The final output is an
agent_starter/ directory + a design_rationale.md with pattern citations.

This module currently defines schemas for step 1 (workload_classifier).
Downstream sub-agents' schemas will be added as they are implemented.
"""
from __future__ import annotations

from typing import Any, Literal

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
# Step 2: skill_proposer
# ---------------------------------------------------------------------------


class SkillProvenance(BaseModel):
    """Why this skill exists — cites specific evidence from the spec / RoleContext.

    Required for every proposed skill. The audit-trail principle: a builder
    reviewing the starter design should be able to trace any skill back to
    the source facts that justified it.
    """

    role_context_decisions: list[str] = Field(
        default_factory=list,
        description=(
            "Names of decision_criteria from the RoleContext this skill encapsulates "
            "(e.g., 'Market Selection', 'Product Granularity Selection'). Pulled "
            "verbatim from RoleContext.decision_criteria[].name."
        ),
    )
    role_context_workflows: list[str] = Field(
        default_factory=list,
        description=(
            "Names of typical_workflows / workflow step indices this skill implements "
            "(e.g., 'Brand Market Share Diagnostic step 2-3')."
        ),
    )
    role_context_facts: list[str] = Field(
        default_factory=list,
        description=(
            "Specific facts from RoleContext.primary_outcomes / unwritten_rules / "
            "vocabulary that motivate this skill. Quote the source fact verbatim."
        ),
    )
    flagged_gaps_addressed: list[str] = Field(
        default_factory=list,
        description=(
            "Names of flagged_unknowns this skill is designed to address (the gap-handling "
            "logic). E.g., 'Question Parsing Ambiguity Resolution' for a question_parser skill."
        ),
    )


class ProposedSkill(BaseModel):
    """One skill in the proposed agent design."""

    name: str = Field(..., description="Short snake_case name (e.g., 'market_share_analyzer').")
    purpose: str = Field(
        ...,
        description=(
            "1-2 sentence statement of what the skill does. Specific, not generic. "
            "'Analyze AOS to compute weekly brand share at chosen granularities' beats "
            "'Handles market share analysis'."
        ),
    )
    inputs: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Input parameter name → type / description. Value can be a string "
            "(simple shape) or a nested dict (structured shape). E.g., "
            "{'parsed_question': 'structured query from question_parser'} or "
            "{'context': {'brand': 'string', 'market': 'string', 'time_window': 'string'}}"
        ),
    )
    outputs: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Output field name → type / description. Value can be a string (simple "
            "shape) or a nested dict (structured shape). The structured result this "
            "skill returns; the downstream scaffold_writer will generate concrete "
            "Pydantic models from these descriptions."
        ),
    )
    data_sources: list[str] = Field(
        default_factory=list,
        description=(
            "External systems / tables / APIs this skill queries. E.g., "
            "'Databricks: default.aos', 'Atlan glossary: Fabric_Care_Analytics'."
        ),
    )
    owned_decisions: list[str] = Field(
        default_factory=list,
        description=(
            "Which judgment-loaded decisions this skill encapsulates. Cross-references "
            "provenance.role_context_decisions but in operational framing."
        ),
    )
    suggested_body_shape: Literal[
        "single-llm-call",      # one model call inside the skill
        "inner-pipeline",       # multiple LLM calls (Bala's pattern)
        "deterministic",        # no LLM call (pure Python utility)
        "adversarial-pair",     # producer + critic inside the skill
    ] = Field(
        default="single-llm-call",
        description=(
            "How the skill should be implemented internally. inner-pipeline (Bala's "
            "pattern) for skills that generate SQL → execute → interpret. "
            "single-llm-call for simple lookups + reasoning. deterministic for pure "
            "data shaping. adversarial-pair for skills with quality-critical output."
        ),
    )
    provenance: SkillProvenance = Field(
        ...,
        description="Audit trail — what RoleContext entries justify this skill.",
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description=(
            "Aspects of this skill's design the spec doesn't fully settle. Flag "
            "explicitly so the builder can choose or so a follow-up discovery probe "
            "can ask the customer."
        ),
    )


class SkillProposalResult(BaseModel):
    """Output of step 2 — skill_proposer.

    A complete proposed skill set for the agent, with explicit provenance per skill
    and one cross-cutting concern that doesn't fit inside any single skill (e.g.,
    'Analysis Path Routing' lives at the orchestrator level, not inside a skill).
    """

    skills: list[ProposedSkill] = Field(
        ...,
        description="The proposed skills, in suggested invocation order.",
    )
    orchestrator_level_concerns: list[str] = Field(
        default_factory=list,
        description=(
            "Concerns that DON'T belong inside any single skill — they live at the "
            "agent's orchestrator level (e.g., 'decide which skills to invoke based on "
            "the question shape'). These shape the architecture decision (step 3)."
        ),
    )
    rationale: str = Field(
        ...,
        description=(
            "1-3 sentences explaining the cut. Specifically: why this number of skills "
            "(not more, not fewer)? Why these decompositions? Cite the workload axes "
            "from step 1's classification."
        ),
    )
    granularity_argument: str = Field(
        ...,
        description=(
            "Why this granularity is right for this workload. Anchored in workload "
            "classification axes (e.g., 'judgment-heavy decision_complexity favors "
            "finer skill cuts so each judgment can be tested in isolation')."
        ),
    )


# ---------------------------------------------------------------------------
# Step 3: architecture_proposer
# ---------------------------------------------------------------------------


class RejectedAlternative(BaseModel):
    """A candidate architecture that was considered and rejected, with reasoning."""

    pattern_slug: str = Field(
        ..., description="The slug of the rejected pattern entry (e.g., 'chained-pipeline')."
    )
    pattern_title: str = Field(
        ..., description="The title of the rejected pattern (e.g., 'Chained Pipeline (Pure Sub-Agent Decomposition)')."
    )
    reason: str = Field(
        ...,
        description=(
            "Why this architecture was rejected for this workload. Cite specific "
            "evidence: pattern's `applies_when`/`don't use when` sections, status "
            "(deprecated), or contradiction with the workload classification."
        ),
    )


class CandidateAddon(BaseModel):
    """A pattern that layers on top of the selected architecture (not a replacement)."""

    pattern_slug: str = Field(
        ..., description="Pattern slug (e.g., 'adversarial-decomposition')."
    )
    pattern_title: str = Field(..., description="Title of the add-on pattern.")
    addresses_concern: str = Field(
        ...,
        description=(
            "Which orchestrator_level_concern (from skill_proposer's output) or workload "
            "axis motivates considering this add-on. E.g., 'Evaluation and Quality "
            "Gating' → adversarial-decomposition for LLM-as-judge review."
        ),
    )
    recommendation: Literal["strongly_recommended", "recommended", "optional", "not_now"] = Field(
        ...,
        description=(
            "How strongly to recommend the add-on. strongly_recommended = the workload "
            "axes plus concerns clearly call for it. optional = useful but not load-bearing."
        ),
    )
    rationale: str = Field(
        ..., description="1-2 sentences citing both the pattern entry and the workload/concern that motivates it."
    )


class ArchitectureProposal(BaseModel):
    """Output of step 3 — architecture_proposer."""

    selected_pattern_slug: str = Field(
        ...,
        description=(
            "The slug of the chosen architecture pattern (e.g., 'single-agent-react'). "
            "Must be the slug of an entry currently in patterns/architectures/."
        ),
    )
    selected_pattern_title: str = Field(
        ...,
        description="The title of the chosen pattern, pulled verbatim from the pattern entry.",
    )
    selection_rationale: str = Field(
        ...,
        description=(
            "Why this architecture was selected. Must cite specific evidence from the "
            "pattern entry (Use when, Empirical anchor) AND from the workload "
            "classification (which axes pointed to this pattern)."
        ),
    )
    rejected_alternatives: list[RejectedAlternative] = Field(
        default_factory=list,
        description=(
            "Other candidates considered and rejected, each with reasoning. The model "
            "should rule out every non-selected architecture explicitly — not silently."
        ),
    )
    candidate_addons: list[CandidateAddon] = Field(
        default_factory=list,
        description=(
            "Patterns to LAYER on top of the selected architecture. E.g., "
            "adversarial-decomposition on single-agent-react when the workload has "
            "Evaluation and Quality Gating as an orchestrator-level concern."
        ),
    )
    bake_off_variables: list[str] = Field(
        default_factory=list,
        description=(
            "If we ran an empirical bake-off across candidate architectures, what would "
            "vary? E.g., 'orchestration loop shape', 'sub-agent count', 'whether the "
            "critic has rewrite authority'. Used to scope the bake-off harness."
        ),
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description=(
            "Aspects of the architecture choice the spec doesn't fully settle. Flag "
            "explicitly so the next step (runtime_proposer) treats them as constraints."
        ),
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="0.0-1.0; how settled is this architecture choice given the inputs."
    )


# ---------------------------------------------------------------------------
# Step 4: runtime_proposer
# ---------------------------------------------------------------------------


class RejectedRuntime(BaseModel):
    """A harness/runtime that was considered and rejected."""

    runtime_name: str = Field(
        ..., description="Name of the rejected harness (e.g., 'LangGraph', 'CrewAI', 'Mastra')."
    )
    reason: str = Field(
        ...,
        description=(
            "Why this runtime was rejected for this workload + architecture. Cite specific "
            "evidence from the harness landscape entry (per-harness 'when to use', "
            "constraints, lock-in concerns) AND the architecture choice (does it preserve "
            "the architectural shape with few impositions?)."
        ),
    )


class CalibrationCostEstimate(BaseModel):
    """Estimate of what porting the agent across runtime boundaries would cost.

    Cross-boundary moves (architecture / model / runtime) trigger prompt re-tuning per
    the empirical finding documented in findings/08 (cheap-cascade gpt-4o-mini didn't
    pan out) and plans/10 (anti-patterns: prompt-flavor portability blindness).
    """

    same_runtime_family: str = Field(
        default="trivial",
        description=(
            "If swapping to a different model within the same runtime family (e.g., "
            "Haiku → Sonnet on Claude Agent SDK), what's the calibration cost? "
            "Typical answer: 'trivial — model swap'."
        ),
    )
    cross_runtime_same_provider: str = Field(
        default="moderate",
        description=(
            "Porting to a different runtime in the same model-provider ecosystem "
            "(e.g., Claude Agent SDK → Claude Managed Agents). Typical: 'moderate — "
            "API surface differs but prompts mostly portable'."
        ),
    )
    cross_provider: str = Field(
        default="high",
        description=(
            "Porting across model providers (e.g., Anthropic → OpenAI). Typical: "
            "'high — prompts need re-tuning (see findings/08); behavior calibration "
            "required even though structure ports cleanly'."
        ),
    )


class RuntimeProposal(BaseModel):
    """Output of step 4 — runtime_proposer."""

    selected_runtime: str = Field(
        ...,
        description=(
            "Name of the selected harness/runtime (e.g., 'Claude Agent SDK', "
            "'Anthropic SDK direct', 'Pydantic AI'). Should match a harness named in "
            "patterns/harnesses/landscape-*.md."
        ),
    )
    selected_model_family: str = Field(
        ...,
        description=(
            "The model family the runtime is paired with (e.g., 'claude-opus-4-7', "
            "'claude-haiku-4-5', 'gpt-5.4'). If the workload's spec doesn't settle a "
            "specific model, propose the simplest sufficient model and flag in open_questions."
        ),
    )
    selection_rationale: str = Field(
        ...,
        description=(
            "Why this runtime preserves the architectural shape with the fewest "
            "impositions. Cites both the harness pattern entry and the architecture "
            "choice from step 3. Quotes specific evidence."
        ),
    )
    rejected_alternatives: list[RejectedRuntime] = Field(
        default_factory=list,
        description=(
            "Other runtimes considered and rejected, each with reasoning. Should rule "
            "out at least the top-5 plausible alternatives for this architecture+workload."
        ),
    )
    constraints_respected: list[str] = Field(
        default_factory=list,
        description=(
            "Tech-stack constraints from the spec the chosen runtime respects (e.g., "
            "'team has standardized on Anthropic SDK; runtime choice honors this'). "
            "If the spec has no technical-thread section, this can be empty."
        ),
    )
    constraints_violated: list[str] = Field(
        default_factory=list,
        description=(
            "Stated constraints the chosen runtime CANNOT meet, with explanation. "
            "Should be empty in most cases; if non-empty, this is a critical flag for "
            "the human builder reviewing the starter."
        ),
    )
    calibration_cost: CalibrationCostEstimate = Field(
        default_factory=CalibrationCostEstimate,
        description=(
            "Cross-boundary porting cost estimates. Used by the human builder to "
            "understand future-portability tradeoffs."
        ),
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description="Aspects the spec doesn't settle (e.g., specific model choice, hosted vs self-hosted).",
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="0.0–1.0; how settled is this runtime choice.")


# ---------------------------------------------------------------------------
# Subsequent steps' schemas will be added as implemented:
#   - SkillCritique         (skill_critic)
#   - ArchitectureCritique  (architecture_critic)
#   - ScaffoldArtifact      (scaffold_writer — the agent_starter/ contents)
# ---------------------------------------------------------------------------
