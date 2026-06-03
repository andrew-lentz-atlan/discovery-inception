"""Pydantic schemas for the discovery agent.

Mirrors the intake-side pattern: every sub-agent has its own tightly-scoped
Pydantic output type. The orchestrator chains sub-agent calls per customer
turn and mutates the DiscoverySession.

Decomposition reminder: each sub-agent does ONE thing. If a schema starts
collecting fields from multiple jobs, that's a smell — split the sub-agent
before splitting the schema.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal
from pydantic import BaseModel, BeforeValidator, Field, model_validator


# Bump when DiscoverySpec's shape changes in a way that affects deserialization
# of on-disk session.json files. Stamped onto every DiscoverySpec; the
# discovery→inception handoff reads it so a consumer can refuse a spec it
# doesn't understand instead of silently mis-parsing.
#   1 = pre-provenance (parallel facts[]/sources[] arrays on TopicEntry)
#   2 = FactRecord provenance (facts[] is list[FactRecord]; artifact_id +
#       provenance_unit per fact; sources[] folded into FactRecord)
SPEC_SCHEMA_VERSION = 2


def _coerce_to_list_of_str(value: Any) -> Any:
    if isinstance(value, str):
        return [value]
    if value is None:
        return []
    return value


ListOfStr = Annotated[list[str], BeforeValidator(_coerce_to_list_of_str)]


# ---------------------------------------------------------------------------
# Per-sub-agent output types
# ---------------------------------------------------------------------------

TriageLabel = Literal[
    "concrete",                     # specific, time-bound, testable answer to the asked probe
    "concrete_off_topic",           # concrete fact, but answers a different question than the one asked
    "hedge",                        # vague, "kind of", "we haven't really figured that out"
    "redirect_question",            # the customer asked the agent a question (genuine, not relevance pushback)
    "relevance_challenge",          # the customer is questioning WHY this line of questioning matters
    "out_of_scope_for_counterparty",# concrete answer that names a knowledge boundary ("above my paygrade")
    "contradiction",                # contradicts something already in the spec
    "meta",                         # non-content (greeting, "let's pause", etc.)
]


class TriageResult(BaseModel):
    """Classification of the customer's last message."""

    label: TriageLabel = Field(..., description="One of the canonical labels.")
    reasoning: str = Field(
        ..., description="One sentence: why you picked this label."
    )
    contradicted_topic: str | None = Field(
        None,
        description="If label=contradiction, the topic in the spec that's contradicted. Else null.",
    )
    inferred_topic: str | None = Field(
        None,
        description=(
            "If label=concrete_off_topic, the topic the customer actually addressed "
            "(snake_case slug, ideally a canonical topic). Else null."
        ),
    )
    escalation_target: str | None = Field(
        None,
        description=(
            "If label=out_of_scope_for_counterparty, who would need to be asked "
            "to answer this — verbatim from the customer's own framing if they "
            "named one (e.g., 'upper leadership', 'product team', 'finance'). "
            "Else null."
        ),
    )


class DistilledFact(BaseModel):
    """Structured capture of a concrete answer."""

    topic: str = Field(
        ...,
        description=(
            "A short snake_case slug for the topic. Use canonical topics when "
            "they fit (why_now, desired_outcome, anti_goal, success_metric, "
            "current_pain, persona, decision_point, escalation_rule, risk). "
            "If none fit, mint a fresh slug — Stage 3 will normalize."
        ),
    )
    content: str = Field(
        ...,
        description=(
            "Distilled version of what the customer said. Concrete, "
            "time-bound, testable. NOT a verbatim quote — your distillation."
        ),
    )
    source: Literal["stated", "inferred_from_priors", "stated_overrides_prior"] = Field(
        ...,
        description=(
            "stated = the customer said it directly. "
            "inferred_from_priors = lifted from RoleContext priors and the "
            "customer didn't contradict. "
            "stated_overrides_prior = the customer contradicted the priors."
        ),
    )
    provenance_unit: str | None = Field(
        default=None,
        description=(
            "Optional locator WITHIN the source where this fact was found: "
            "'line 88', 't=14:03', 'slide 4', 'msg from @alice'. The extractor "
            "fills this when it can cite a precise location; null otherwise. "
            "Which artifact the fact came from (artifact_id) is assigned by the "
            "ingest pipeline at record time, not by the extractor — the "
            "extractor only knows the position inside the text it was handed."
        ),
    )


class FactRecord(BaseModel):
    """One captured fact with its provenance, as STORED in a TopicEntry.

    Distinct from DistilledFact (the sub-agent OUTPUT type): FactRecord is the
    stored form. `record_fact()` converts a DistilledFact into a FactRecord,
    attaching the `artifact_id` the extractor doesn't know (assigned by the
    ingest pipeline based on which artifact was being processed) and carrying
    forward any `provenance_unit` the extractor emitted.

    Why this exists (provenance):
      Before this, TopicEntry held two parallel arrays — facts: list[str] and
      sources: list[str] — kept in lockstep by index. That couldn't answer
      "which artifact did this fact come from?", which becomes a trust + UX
      requirement the moment sources are multimodal ("this unwritten rule came
      from minute 14 of the screen recording"). Folding content + source +
      provenance into one record makes each fact self-describing and removes
      the fragile parallel-array invariant.
    """

    content: str = Field(..., description="The distilled fact text.")
    source: Literal["stated", "inferred_from_priors", "stated_overrides_prior"] = Field(
        ...,
        description="How the fact was obtained — see DistilledFact.source for semantics.",
    )
    artifact_id: str | None = Field(
        default=None,
        description=(
            "Which artifact this fact came from — the stored artifact filename "
            "(e.g. '00_call-transcript.txt', matching sessions/<id>/artifacts/). "
            "None means the fact came from live conversation, not an ingested "
            "artifact. The absence of an artifact_id IS the signal a fact is "
            "conversation-sourced."
        ),
    )
    provenance_unit: str | None = Field(
        default=None,
        description=(
            "Locator within the artifact: 'line 88', 't=14:03', 'slide 4'. "
            "Carried from DistilledFact.provenance_unit when the extractor "
            "emitted one. Becomes load-bearing for multimodal sources."
        ),
    )


class WhyProbeResult(BaseModel):
    """Output of the why-prober.

    Either produces the next 'why' to ask, or signals bedrock if the next
    why would be tautological / 'that's just how the business works.'
    """

    bedrock_reached: bool = Field(
        ..., description="True if no further useful 'why' can be asked."
    )
    next_why: str | None = Field(
        None,
        description=(
            "If bedrock_reached=False: the next concrete 'why' question. "
            "If bedrock_reached=True: null."
        ),
    )
    terminal_answer: str | None = Field(
        None,
        description=(
            "If bedrock_reached=True: the bedrock answer that closed the chain. "
            "If bedrock_reached=False: null."
        ),
    )
    why_chain_so_far: ListOfStr = Field(
        default_factory=list,
        description=(
            "Sequence of (Q, A) pairs accumulated so far on this topic, "
            "as 'Q: ... → A: ...' strings. Echo back the running chain so "
            "the orchestrator can persist it."
        ),
    )


GapType = Literal[
    "vague",
    "contradictory",
    "untested",
    "templatey",
    "missing_why",
    "untriaged",
]


class FlaggedGap(BaseModel):
    """A known unknown captured by the orchestrator (NOT an LLM output type).

    Created when triage labels a turn as 'hedge' and probe-gen decides the
    gap is load-bearing rather than skippable.
    """

    question: str = Field(..., description="The specific question the customer couldn't answer.")
    why_it_matters: str = Field(
        ...,
        description="Why this gap blocks downstream work. Forces load-bearing-ness.",
    )
    related_topic: str | None = Field(None, description="Optional topic the gap blocks.")
    gap_type: GapType = Field(default="untriaged", description="What kind of gap this is.")


ConfidenceLevel = Literal["high", "medium", "low"]


class WorkingTheory(BaseModel):
    """The agent's current best hypothesis about what the customer wants built.

    Produced by the Synthesizer sub-agent after each concrete answer. Persists
    on the DiscoverySpec; probe-generator anchors its next probe to the theory
    (confirming, disconfirming, or sharpening one of its open questions).

    The theory is the difference between "playbook discovery" (ask why, fill
    checklist) and "consultative discovery" (have a working hypothesis,
    pressure-test it). Without it, probes are topic-anchored not theory-
    anchored, which feels artificial to the customer.
    """

    one_line_framing: str = Field(
        ...,
        description=(
            "ONE sentence: the agent's current best guess at what's being "
            "built. Use the customer's vocabulary. Examples: 'A workflow "
            "executor that drives priority-connector setup → metadata "
            "bootstrap → success-plan completion for new enterprise customers.' "
            "or 'A copilot for the SoCo that drafts and updates the success "
            "plan as connectors and metadata land.' If you genuinely don't "
            "have enough signal yet, say so explicitly: '(too early — only "
            "have a goal, no shape yet).'"
        ),
    )
    candidate_framings: ListOfStr = Field(
        default_factory=list,
        description=(
            "2-4 alternative framings the customer's answers could support, "
            "with the dominant one named. Disjoint, contrastable. Examples: "
            "'workflow executor (does the work)' vs 'coordinator (drives "
            "human SoCo)' vs 'customer-facing chatbot (answers questions). "
            "Empty list is fine if there's only one plausible framing yet."
        ),
    )
    open_questions: ListOfStr = Field(
        default_factory=list,
        description=(
            "1-3 open questions whose answers would most sharpen or "
            "disconfirm the theory. NOT random gaps — questions that would "
            "actually move the theory. Each should be ONE sentence."
        ),
    )
    sharpest_disconfirmer: str = Field(
        ...,
        description=(
            "ONE sentence: what's the single observation that would tell us "
            "this theory is WRONG? Forces the agent to commit to a falsifiable "
            "hypothesis rather than an unfalsifiable mush."
        ),
    )
    confidence: ConfidenceLevel = Field(
        ...,
        description="High/medium/low — how settled is this theory? Bias low early.",
    )
    internal_tensions: ListOfStr = Field(
        default_factory=list,
        description=(
            "0-3 pairs of customer statements that are in implicit tension — "
            "facts that don't obviously fit together. Surfaced by the synthesizer "
            "as 'things a sharp FDE would catch in real time.' Each entry is "
            "one sentence naming what's in tension; the synthesizer names them, "
            "the next probe resolves them. Used by v0.8+ to drive sharper "
            "questioning."
        ),
    )


class TensionsResult(BaseModel):
    """Output of the find_tensions sub-agent (v0.8+).

    A focused readout of implicit contradictions across captured facts.
    Distinct from the synthesizer's working_theory.internal_tensions in
    that this sub-agent runs cheaply on demand without rebuilding the
    full theory.
    """

    tensions: ListOfStr = Field(
        default_factory=list,
        description=(
            "0-3 one-sentence statements naming a tension between two prior "
            "facts the customer stated. Empty list is fine — most conversations "
            "don't have many real tensions; padding is forbidden."
        ),
    )


class SharpenerResult(BaseModel):
    """Output of the probe-sharpener sub-agent (v0.8+).

    Runs as a post-processor on every probe the mega-agent produces.
    Either ships the draft as-is or rewrites it to be sharper.
    """

    scores: dict[str, int] = Field(
        ...,
        description=(
            "Per-axis 1-5 scores for novelty / extension / provenance_pressure / "
            "tension_surfacing. Sum into quality_score."
        ),
    )
    quality_score: int = Field(
        ...,
        description="Sum of the four axis scores; max 20. <=10 = weak, 11-15 = acceptable, 16+ = sharp.",
    )
    weakness: str = Field(
        ...,
        description="One-sentence diagnosis of what's weak about the draft probe, or '(none — probe is sharp)'.",
    )
    ships_as_is: bool = Field(
        ...,
        description="True if quality_score >= 11. False = the rewritten_probe field is what should ship.",
    )
    rewritten_probe: str | None = Field(
        None,
        description="The sharpened probe text, or null if ships_as_is=True.",
    )
    rewritten_customer_facing_rationale: str | None = Field(
        None,
        description="Customer-facing rationale for the rewritten probe, or null if ships_as_is=True.",
    )


class Probe(BaseModel):
    """The next probe the agent will speak to the customer."""

    question: str = Field(
        ...,
        description=(
            "ONE concrete question. Time-bound where possible. Naive-on-purpose "
            "if probing the priors. No multi-part questions."
        ),
    )
    target_topic: str = Field(
        ...,
        description="Topic this probe is trying to land on. snake_case slug.",
    )
    rationale: str = Field(
        ...,
        description=(
            "INTERNAL one-sentence rationale: why this is the right next question "
            "given pipeline state. Used for trace, not shown to the customer."
        ),
    )
    customer_facing_rationale: str = Field(
        ...,
        description=(
            "How the agent would justify this question if the customer asked "
            "'why does answering this matter?' Must tie back to the use-case "
            "seed in the customer's own goal terms — NOT in pipeline language. "
            "If you cannot write one cleanly, pick a different probe — the "
            "ability to articulate this IS the relevance gate."
        ),
    )


# ---------------------------------------------------------------------------
# Spec — what the discovery agent is building, turn over turn
# ---------------------------------------------------------------------------

class TopicEntry(BaseModel):
    """A captured topic in the running spec."""

    topic: str
    facts: list[FactRecord] = Field(
        default_factory=list,
        description=(
            "Captured facts on this topic, each self-describing (content + "
            "source + provenance). Was two parallel arrays (facts/sources) "
            "before schema v2; see the migration validator below."
        ),
    )
    superseded_facts: ListOfStr = Field(
        default_factory=list,
        description=(
            "When a fact is overridden by a stated_overrides_prior fact, the old "
            "version is moved here with a marker. Preserves the contradiction "
            "history without polluting the active spec."
        ),
    )
    bedrock_reached: bool = False
    why_chain: ListOfStr = Field(default_factory=list, description="The why-chain that hit bedrock, if it has.")
    terminal_answer: str | None = None
    pending_questions: ListOfStr = Field(
        default_factory=list,
        description=(
            "Question lines we logged in phase 1 (lay of the land) for later "
            "drilling. The why-prober's next_why goes here when phase=1 instead "
            "of being asked immediately. Phase 2 reads from this queue."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _migrate_parallel_arrays(cls, data: Any) -> Any:
        """Migrate pre-v2 on-disk shape (parallel facts[]/sources[]) → FactRecord.

        Old sessions persisted `facts: list[str]` + `sources: list[str]` kept
        in lockstep by index. New code expects `facts: list[FactRecord]`. When
        we deserialize an old session.json, `facts` is a list of strings; zip it
        with `sources` (popped) into FactRecord dicts. New-shape data (facts
        already list[dict]) and empty topics pass through untouched.

        Provenance for migrated facts is null — pre-v2 facts genuinely had no
        artifact_id captured, and inventing one would be worse than admitting
        the gap. The null is honest: "this fact predates provenance capture."
        """
        if not isinstance(data, dict):
            return data
        facts = data.get("facts")
        if facts and isinstance(facts[0], str):
            sources = data.get("sources") or []
            migrated = []
            for i, content in enumerate(facts):
                src = sources[i] if i < len(sources) else "stated"
                migrated.append(
                    {
                        "content": content,
                        "source": src,
                        "artifact_id": None,
                        "provenance_unit": None,
                    }
                )
            data = {**data, "facts": migrated}
            data.pop("sources", None)
        return data


DiscoveryPhase = Literal["lay_of_the_land", "drilling"]


class DiscoverySpec(BaseModel):
    """The spec the discovery session is building.

    This is the artifact handed to Stage 4 (Build Bridge) when ready.
    """

    schema_version: int = Field(
        default=SPEC_SCHEMA_VERSION,
        description=(
            "Schema version of this spec. Stamped at creation; carried through "
            "the discovery→inception handoff so a consumer can detect a shape it "
            "doesn't understand instead of silently mis-parsing. Old sessions on "
            "disk without this field default to the current version after the "
            "TopicEntry migration validator has already up-converted their facts."
        ),
    )

    use_case_seed: str = Field(..., description="The one-line use-case seed the session started with.")
    role_id: str | None = Field(
        None,
        description="The RoleContext skill id used as priors (e.g. 'solutions-consultant').",
    )

    phase: DiscoveryPhase = Field(
        default="lay_of_the_land",
        description=(
            "Which discovery phase we're in. Phase 1 = lay_of_the_land — record "
            "facts breadth-first, why-prober off, follow-ups logged. Phase 2 = "
            "drilling — why-prober enabled, target bedrock on highest-value "
            "topics. Transitions when ~5 of 8 canonical topics have ≥1 fact."
        ),
    )

    topics: list[TopicEntry] = Field(default_factory=list)
    gaps: list[FlaggedGap] = Field(default_factory=list)

    # Working theory — the agent's current best hypothesis about what's being
    # built. Mutated by the Synthesizer sub-agent after each concrete answer.
    # Probe-generator reads this to anchor probes to the theory rather than
    # to a topic checklist.
    working_theory: WorkingTheory | None = None
    theory_history: list[WorkingTheory] = Field(
        default_factory=list,
        description=(
            "Snapshot of every prior working theory, in order. Lets us see "
            "how the theory evolved as the customer answered probes."
        ),
    )
    strawman_shown: bool = Field(
        default=False,
        description=(
            "Whether we've already shown a strawman (theory presented to "
            "customer as 'here's what I'm hearing'). One per session, fired "
            "the first time we have a non-trivial theory."
        ),
    )

    # Stop-condition tracking
    declared_ready: bool = False
    ready_summary: str | None = None
    ready_confidence: ConfidenceLevel | None = None
    remaining_known_gaps: ListOfStr = Field(default_factory=list)

    # Established Atlan context — populated at session start if --atlan-* CLI
    # args / MCP arguments named a tenant + scope. The mega-agent renders this
    # into its system prompt every turn so cataloged definitions are always in
    # scope and the technical-thread probes can skip what's already known.
    # See agent/atlan_context.py for the slot types. Stored loosely as a dict
    # so old sessions on disk (without this field) deserialize cleanly.
    bounded_context: dict[str, Any] | None = Field(
        default=None,
        description=(
            "BoundedContext.model_dump() if Atlan was queried at session start; "
            "None when the session ran without Atlan integration."
        ),
    )


# ---------------------------------------------------------------------------
# Stop-condition checklist (deterministic — no LLM)
# ---------------------------------------------------------------------------

class ChecklistResult(BaseModel):
    """Output of the deterministic stop-condition checker."""

    ready: bool
    items: dict[str, bool] = Field(
        ...,
        description="Per-criterion booleans. Keys match the canonical checklist.",
    )
    missing: ListOfStr = Field(
        default_factory=list, description="Human-readable list of failed criteria."
    )


# ---------------------------------------------------------------------------
# Multi-artifact ingest (fact extractor wrapper)
# ---------------------------------------------------------------------------


class FactExtractionResult(BaseModel):
    """Output of the fact_extractor sub-agent over one artifact.

    The model emits a list; we wrap it in a Pydantic object so the
    structured-output extractor has a stable top-level shape (LiteLLM /
    Claude-via-proxy is more reliable returning `{"facts": [...]}` than a
    bare JSON array).
    """

    facts: list[DistilledFact] = Field(
        default_factory=list,
        description="One DistilledFact per atomic use-case fact in the artifact.",
    )
