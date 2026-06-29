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
    learns_from_experience: bool = Field(
        default=False,
        description=(
            "Does the agent improve from its own past runs — refining behavior "
            "based on prior outcomes, corrections, or accumulated patterns? This "
            "is the procedural-memory trigger, and it is NOT implied by state_shape: "
            "a long-horizon agent can be static, and a stateless task agent can "
            "still learn across tasks. Together with state_shape (which governs "
            "working + episodic memory) this lets the downstream memory "
            "recommendation be a deterministic lookup rather than a guess. See "
            "decision-guides/does-this-agent-need-memory.md."
        ),
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


class AtlanContextLayer(BaseModel):
    """Step 2's distilled Atlan context-layer recommendation.

    v1.0 is an Atlan-native product, so this is ALWAYS produced. The context
    repo is the portable home for the agent's STATIC scaffold (skills, semantic
    models, definitions, YAMLs) — recommended unconditionally, even when the
    tenant is thin (then the move is to SEED it). The live-access surface(s)
    (MCP / MDLH / SDK) are routed by the customer's Atlan posture facts captured
    in discovery. Step 2 has the spec prose (posture) and the atlan-* entries;
    steps 3/4/5c do NOT get the prose, so this typed field is how the decision
    travels downstream (the pipeline's progressive-distillation boundary)."""

    repo_recommendation: str = Field(
        ...,
        description=(
            "ALWAYS recommend an Atlan context repo as the portable home for the "
            "agent's static scaffold (skills, semantic models, definitions, YAMLs) — "
            "write-once, pulled by whatever runtime the customer uses. If the tenant "
            "is thin/cold, frame this as 'seed the repo'. Cite "
            "patterns/skill-design/atlan-context-repos.md."
        ),
    )
    live_access_surfaces: list[str] = Field(
        default_factory=list,
        description=(
            "The live-access surface(s) the agent uses at RUNTIME for fresh reads / "
            "writes, routed by posture: 'mcp' (Remote MCP — live reads + writes), "
            "'mdlh' (bulk / analytics reads), 'sdk' (pyatlan mutations). A static repo "
            "can't serve fresh data or writes, so most agents need at least one. Empty "
            "ONLY when posture genuinely rules out live access — justify in `rationale`."
        ),
    )
    posture_assumptions: list[str] = Field(
        default_factory=list,
        description=(
            "The Atlan posture facts (from the spec) this recommendation rests on — "
            "context repo set up? skills-as-assets configured? MCP reachable? MDLH "
            "tier? metadata coverage? Where the spec is silent, state the assumption "
            "and flag it (mirror into open questions) rather than inventing a fact."
        ),
    )
    cited_entries: list[str] = Field(
        default_factory=list,
        description=(
            "Full patterns/skill-design/atlan-*.md slugs supporting this layer, "
            "verbatim (e.g. 'patterns/skill-design/atlan-context-repos.md', "
            "'patterns/skill-design/atlan-mcp-integration.md')."
        ),
    )
    rationale: str = Field(
        ...,
        description=(
            "1-3 sentences tying the repo + live-surface choice to the posture facts. "
            "If live_access_surfaces is empty, justify why posture rules it out."
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
    atlan_context_layer: AtlanContextLayer = Field(
        ...,
        description=(
            "REQUIRED. The distilled Atlan context-layer recommendation: context repo "
            "as the portable home (always) + the live-access surface(s) routed by "
            "posture. v1.0 is Atlan-native, so this is always produced and carried to "
            "steps 3/4/5c, which don't receive the raw spec prose."
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
    pan out — prompts inherit flavor from the model + runtime they were authored against).
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
# Step 5: scaffold_writer — sub-step outputs
# ---------------------------------------------------------------------------
#
# scaffold_writer produces a multi-file agent_starter/ directory. It runs as
# a small internal sub-pipeline. Each sub-step has its own typed output;
# the writer aggregates them and writes the files deterministically.
#
# Tonight's scope (initial implementation): 3 LLM sub-steps + deterministic
# meta + readme. Eval question seed + LLM-as-judge harness deferred to a
# subsequent iteration.


class SkillMdContent(BaseModel):
    """Output of `generate_skill_md`. Called once per proposed skill."""

    skill_name: str = Field(..., description="snake_case name (must match the proposed skill's name).")
    skill_md: str = Field(
        ...,
        description=(
            "Full markdown content for the SKILL.md file, including YAML frontmatter "
            "(name + description) and body sections. The body should include: Purpose, "
            "Inputs, Outputs, Implementation guidance, Provenance (which RoleContext "
            "entries justified this skill), Open questions for the builder. Body shape "
            "should adapt to suggested_body_shape (inner-pipeline gets code structure; "
            "single-llm-call gets simpler shape; deterministic gets pure-Python pointers)."
        ),
    )


class OrchestratorStub(BaseModel):
    """Output of `generate_orchestrator_stub`. Single call."""

    filename: str = Field(
        default="orchestrator.py",
        description="The orchestrator file name; usually orchestrator.py.",
    )
    orchestrator_py: str = Field(
        ...,
        description=(
            "Python source for the orchestrator stub. Should be runnable in principle "
            "(imports, function signatures, agent loop scaffold) but skill implementations "
            "are TODO markers — the builder fills them. Must match the selected "
            "architecture + runtime: e.g., for single-agent-react + Claude Agent SDK, "
            "use anthropic SDK tool-use loop with the proposed skills bound as tools."
        ),
    )
    imports_needed: list[str] = Field(
        default_factory=list,
        description=(
            "External packages this stub imports (e.g., 'anthropic>=0.40', "
            "'pydantic>=2.0'). Used by the writer to populate a requirements section "
            "in the starter README."
        ),
    )
    env_vars_needed: list[str] = Field(
        default_factory=list,
        description=(
            "Environment variables the builder must set (e.g., 'ANTHROPIC_API_KEY', "
            "'DATABRICKS_HOST'). Used by the writer to populate setup instructions."
        ),
    )


class DesignRationale(BaseModel):
    """Output of `generate_design_rationale`. Single call.

    This is the audit-trail artifact. Aggregates every decision made in
    steps 1-4 with the specific evidence (RoleContext entries, pattern
    citations, workload axes) that justified it.
    """

    rationale_md: str = Field(
        ...,
        description=(
            "Full markdown content for design_rationale.md. Sections: Workload classification "
            "(with rationale + open questions), Skill cut (per-skill provenance), Architecture "
            "choice (with pattern citation + rejected alternatives), Runtime choice (with "
            "harness citation + calibration cost), Add-ons (if any), Bake-off variables. "
            "Every decision must cite its source — a RoleContext entry, a pattern, or a "
            "workload axis. Reads like a brief but defensible audit trail."
        ),
    )


# ---------------------------------------------------------------------------
# Step 5d: eval seed generation
# ---------------------------------------------------------------------------


class EvalQuestion(BaseModel):
    """One seed question for the agent's eval harness."""

    id: str = Field(..., description="Stable identifier like 'Q01'. Used for tracking and reporting.")
    question: str = Field(
        ..., description="The user-facing natural-language question (e.g., 'Why did Gain lose share at Target?')."
    )
    category: str = Field(
        ...,
        description=(
            "What the question is testing — a short label like 'share-decline-diagnosis', "
            "'growth-driver-analysis', 'cross-retailer-comparison', 'ambiguous-market', etc. "
            "Used to organize the eval set + report coverage."
        ),
    )
    expected_entities: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Entities the agent should extract from the question. Keys depend on the workload domain "
            "(e.g., 'brand', 'market', 'time_context', 'channel'). Values can be canonical strings, "
            "lists (e.g., market_def_candidates), nulls (when the question deliberately omits a "
            "dimension), or booleans (e.g., requires_clarification). The shape matches whatever the "
            "agent's question_parser is expected to output for that question."
        ),
    )
    expected_skills_invoked: list[str] = Field(
        default_factory=list,
        description="Which skills should fire (by snake_case name) for this question.",
    )
    expected_output_features: list[str] = Field(
        default_factory=list,
        description=(
            "Features the final output must include for a passing answer. E.g., 'signal week identified', "
            "'BCA classification provided', 'competitor share-shift quantified'. These are the binary "
            "checks the judge can apply."
        ),
    )
    test_intent: str = Field(
        ...,
        description=(
            "Why this question is in the seed set. Specifically: what edge case or capability "
            "does it stress-test? E.g., 'ambiguity handling: Target without channel hint'."
        ),
    )


class EvalSeed(BaseModel):
    """Output of `generate_eval_seed`. Single call producing 10-15 questions."""

    questions: list[EvalQuestion] = Field(
        ...,
        description="The seed question set, typically 10-15 questions covering distinct scenarios.",
    )
    coverage_notes: str = Field(
        ...,
        description=(
            "1-2 paragraphs explaining what the seed set covers — which brands / markets / "
            "ambiguity scenarios / edge cases — and what it deliberately doesn't cover yet "
            "(builder follow-up scope)."
        ),
    )
    data_requirements: str = Field(
        ...,
        description=(
            "What synthetic-or-real data the builder needs to actually run these questions "
            "through the agent. E.g., 'AOS table with 52 weeks of brand × market × week share "
            "data; Trade Panel / Decon / HHP tables with DPSM metrics; embedded ground-truth "
            "signal (e.g., Bala's week-20 distribution drop pattern) so judge can verify accuracy.'"
        ),
    )


# ---------------------------------------------------------------------------
# Step 5e: LLM-as-judge harness generation
# ---------------------------------------------------------------------------


class JudgeHarness(BaseModel):
    """Output of `generate_judge_harness`. Single call producing eval/judge.py source."""

    judge_py: str = Field(
        ...,
        description=(
            "Python source for the eval/judge.py scaffold. Should implement the LLM-as-judge "
            "pattern with N scoring dimensions adapted to the workload (Bala's 5-dimension "
            "canonical: accuracy / root-cause-classification / hallucination / reasoning / "
            "actionability — adapt as workload requires). Includes a Judge class, score() function "
            "with TODO markers for the dimension-specific scoring prompts, and a CLI entry."
        ),
    )
    dimensions: list[str] = Field(
        default_factory=list,
        description=(
            "The scoring dimensions the judge uses. Bala's canonical 5 for diagnostic agents are "
            "a strong default; adapt for different workloads (e.g., a conversational agent might "
            "score 'question quality' instead of 'root-cause classification')."
        ),
    )
    judging_model_recommended: str = Field(
        default="claude-opus-4-7",
        description=(
            "Recommended model for the judge. Should be at least as capable as the agent being "
            "judged. Independent of the agent's model family is good practice — reduces "
            "self-evaluation bias."
        ),
    )


# ---------------------------------------------------------------------------
# Step 5f: Architecture diagram generation
# ---------------------------------------------------------------------------


class ArchitectureDiagram(BaseModel):
    """Output of `generate_architecture_diagram`. Single call producing a
    Mermaid-rendered architecture.md that lets a builder skim the agent's
    shape in 30 seconds.

    Two diagrams in one file:
      - `skill_graph_mermaid`: flowchart showing which skills exist, their
        types (LLM / inner-pipeline / deterministic), and the typical
        dependency/data-flow between them
      - `execution_flow_mermaid`: sequence diagram showing the orchestrator's
        per-turn behavior — which skills get invoked in which order, where
        escalation gates fire, where the loop exits

    Plus a 2-paragraph summary that frames the diagrams for someone who's
    never seen this kind of agent.

    Architecture-aware: single-agent-react gets a ReAct loop shape;
    chained-pipeline gets a linear stages shape; adversarial-decomposition
    gets producer + critic. The prompt is given the architecture's slug so
    it can adapt.
    """

    skill_graph_mermaid: str = Field(
        ...,
        description=(
            "Mermaid `graph TD` (or `flowchart TD`) source showing the skill "
            "graph. One node per skill, labeled with name + type tag (LLM / "
            "inner-pipeline / deterministic). Edges show typical invocation "
            "order or data dependency. Wrap in mermaid fence is NOT needed — "
            "the renderer adds fences when writing to disk."
        ),
    )
    execution_flow_mermaid: str = Field(
        ...,
        description=(
            "Mermaid `sequenceDiagram` source showing one full agent turn "
            "from user input to final response. Includes the orchestrator, "
            "the skills it invokes, conditional branches (e.g., escalation "
            "gates), and where the loop ends. Wrap in mermaid fence is NOT "
            "needed — the renderer adds fences."
        ),
    )
    summary_md: str = Field(
        ...,
        description=(
            "2-paragraph markdown summary framing what the agent does, the "
            "shape of one turn, and where the key judgment moments live. "
            "Reads before the diagrams in architecture.md."
        ),
    )


# ---------------------------------------------------------------------------
# Prior iteration feedback (intra-session learning)
# ---------------------------------------------------------------------------
#
# Intra-session learning: a builder iterates on the agent_starter/ produced
# by one inception run, and the next inception run for the SAME spec
# consumes that feedback as
# constraints. Feedback stays session-scoped — it does NOT leak to other
# agents (that's Loop 3's job, via the patterns_curator agent).
#
# Each feedback item targets one inception sub-agent's step. Session-level
# `free_text_lessons` apply across all steps.


FeedbackTargetStep = Literal[
    "workload",      # workload_classifier
    "skills",        # skill_proposer
    "architecture",  # architecture_proposer
    "runtime",       # runtime_proposer
    "scaffold",      # scaffold_writer (any of its sub-steps)
]


FeedbackType = Literal[
    "worked_as_proposed",         # confirm: keep the decision
    "worked_with_modification",   # adapt: builder made a tweak; propose that tweaked version directly
    "wrong_for_this_use_case",    # reject: do not repeat without explicit justification
    "missing",                    # add: this aspect was missing from the prior output and must be addressed
]


class FeedbackItem(BaseModel):
    """One piece of feedback targeting a specific inception sub-agent's decision."""

    targets_step: FeedbackTargetStep = Field(
        ...,
        description=(
            "Which inception sub-agent's output this feedback targets. Each sub-agent "
            "filters feedback to items targeting its own step."
        ),
    )
    decision: str = Field(
        ...,
        description=(
            "Short label naming the specific decision this feedback is about. "
            "E.g., 'selected_runtime: Claude Agent SDK', 'skill cut: 4 skills including "
            "question_parser', 'calibration_cost.cross_runtime_same_provider rated moderate'."
        ),
    )
    feedback_type: FeedbackType = Field(
        ...,
        description=(
            "Category of feedback. worked_as_proposed confirms the prior decision; "
            "worked_with_modification means the modification IS the right answer; "
            "wrong_for_this_use_case rejects it; missing flags an addition needed."
        ),
    )
    detail: str = Field(
        ...,
        description=(
            "Explanation. For worked_with_modification: what the modification was. "
            "For wrong_for_this_use_case: what was done instead, and why. For missing: "
            "what should have been included and what specifically should change."
        ),
    )


class PriorIterationFeedback(BaseModel):
    """Builder feedback from a previous inception iteration on the same spec.

    Consumed by every inception sub-agent on re-run. Treated as constraints —
    not advisory. Each sub-agent filters items by `targets_step` to its own
    step; `free_text_lessons` applies session-wide.

    Stays scoped to ONE session / ONE spec. Cross-stage learnings (across
    multiple agent builds) flow through the patterns_curator's promote
    operation, NOT through this schema.
    """

    iteration: int = Field(
        ...,
        description=(
            "Which iteration produced this feedback. The next inception run is "
            "iteration N+1. Used in the prompt to clarify ordering."
        ),
    )
    items: list[FeedbackItem] = Field(
        default_factory=list,
        description="Per-decision feedback items. Each targets one step.",
    )
    free_text_lessons: str = Field(
        default="",
        description=(
            "Session-level insights that don't fit the per-decision grain. Applied "
            "as background context to every sub-agent regardless of which step the "
            "lesson targets."
        ),
    )
    source: str | None = Field(
        default=None,
        description=(
            "Optional: where this feedback came from. A findings/ doc, an empirical "
            "receipt from running the agent, a builder's notes. Useful for audit trail."
        ),
    )


# ---------------------------------------------------------------------------
# Subsequent steps' schemas (when implemented):
#   - SkillCritique         (skill_critic; back-burner per Andrew's call)
#   - ArchitectureCritique  (architecture_critic; back-burner)
# ---------------------------------------------------------------------------
