"""Pydantic models for the patterns_curator ingest pipeline.

Each step in the pipeline emits a typed intermediate. The final output
is a draft PatternEntry that mirrors the YAML frontmatter + body shape
of entries in patterns/.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Step 1: classify_source
# ---------------------------------------------------------------------------

PatternCategory = Literal[
    "architectures",
    "anti-patterns",
    "skill-design",
    "harnesses",
    "decision-guides",
]


BodyShape = Literal[
    "operational-decision",   # Use when / Don't use when / Gotchas / Empirical anchor
    "code-pattern",           # Pattern / Code / Variants / Anti-pattern callouts
    "comparative-survey",     # Tables + per-item analysis + cross-cutting observations
    "theoretical",            # Premises / Implications / Open questions
    "historical",             # Trajectory / What came before / What it enabled
    "open-questions",         # Question list / What we'd test / Current best guesses
]


SourceType = Literal[
    "internal_finding",       # one of our findings/ docs
    "internal_design_doc",    # internal design document (local; not in the public repo)
    "external_research",      # external doc / blog / framework comparison
    "builder_report",         # README / write-up from a specific build
    "external_repo",          # code repo with documented patterns
    "other",
]


class SourceClassification(BaseModel):
    """Output of step 1 — classify_source."""

    source_type: SourceType = Field(
        ..., description="What kind of source this is."
    )
    target_category: PatternCategory = Field(
        ..., description="Which patterns/ subdirectory the resulting entry should live in."
    )
    body_shape: BodyShape = Field(
        ..., description=(
            "Which body shape the resulting entry should use. "
            "operational-decision is the most common — only deviate when the content genuinely warrants it "
            "(e.g., a comparative survey of multiple items, a code-heavy skill pattern, a theoretical-foundations entry)."
        )
    )
    candidate_title: str = Field(
        ..., description="Proposed entry title (becomes the markdown title and influences the filename slug)."
    )
    candidate_slug: str = Field(
        ..., description="Lowercase-with-dashes filename slug (no extension). Named by content, never by source."
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Classifier confidence 0.0–1.0."
    )
    rationale: str = Field(
        ..., description="Why this category / body_shape / title was chosen."
    )


# ---------------------------------------------------------------------------
# Step 2: extract_pattern — stub
# ---------------------------------------------------------------------------

class ExtractedPattern(BaseModel):
    """Output of step 2 — extract_pattern. STUB; not yet implemented."""

    summary: str = Field(..., description="One-paragraph summary of the pattern.")
    use_when: list[str] = Field(default_factory=list, description="Conditions favoring this pattern.")
    dont_use_when: list[str] = Field(default_factory=list, description="Conditions against.")
    gotchas: list[str] = Field(default_factory=list, description="Implementation pitfalls.")
    empirical_receipts: list[str] = Field(
        default_factory=list,
        description="Citations to findings/, external sources, or builder reports.",
    )
    code_excerpts: list[str] = Field(
        default_factory=list,
        description="Code blocks (markdown-formatted) — used for code-pattern body shape.",
    )
    survey_items: list[dict] = Field(
        default_factory=list,
        description="Items to compare — used for comparative-survey body shape.",
    )


# ---------------------------------------------------------------------------
# Final output: draft PatternEntry
# ---------------------------------------------------------------------------

PatternStatus = Literal["validated", "experimental", "deprecated"]


class AppliesWhen(BaseModel):
    workloads: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class PatternFrontmatter(BaseModel):
    """Mirrors the YAML frontmatter at the top of every pattern entry."""

    title: str
    category: PatternCategory
    status: PatternStatus
    last_updated: str  # YYYY-MM-DD
    source_findings: list[str] = Field(default_factory=list)
    source_external: list[str] = Field(default_factory=list)
    applies_when: AppliesWhen = Field(default_factory=AppliesWhen)
    contradicts: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    superseded_by: list[str] = Field(default_factory=list)
    reference: str | None = None
    snapshot_date: str | None = None


class PatternEntry(BaseModel):
    """Final output of the curator's ingest pipeline.

    Renders to a markdown file at `patterns/<category>/<slug>.draft.md`.
    Becomes the canonical `<slug>.md` after human review.
    """

    frontmatter: PatternFrontmatter
    body: str = Field(
        ..., description="The full body of the entry, markdown-formatted, matching the chosen body_shape."
    )
    body_shape: BodyShape = Field(
        ..., description="Recorded for traceability — which body shape was used."
    )


# ---------------------------------------------------------------------------
# Loop 3 — cross-session knowledge promotion
#
# These schemas drive the patterns_curator's `promote` pipeline (distinct from
# the `ingest` pipeline above which handles single sources). Signals are
# atomic lessons extracted from per-session feedback artifacts; clusters
# group recurring signals across sessions; classification gates which cross
# from session-scoped to global.
# ---------------------------------------------------------------------------


SignalStage = Literal["discovery", "inception"]


SignalKind = Literal[
    "worked_as_proposed",
    "worked_with_modification",
    "wrong_for_this_use_case",
    "missing",
    "lesson",  # free-text lesson
]


class FeedbackSignal(BaseModel):
    """One atomic feedback item from one session.

    Extracted deterministically from a per-session feedback file. The curator
    treats each signal as a candidate input to the cross-session clustering
    step. Multiple signals come from one feedback file; multiple feedback
    files are aggregated into the corpus.
    """

    session_id: str = Field(..., description="The session this signal came from.")
    stage: SignalStage = Field(..., description="Discovery or inception side.")
    kind: SignalKind = Field(..., description="Which feedback bucket this item belongs to.")
    content: str = Field(..., description="The verbatim lesson / item text.")
    target_area: str | None = Field(
        None,
        description=(
            "Optional: the decision area or sub-agent this signal targets. "
            "Free-text — examples: 'skill_proposer', 'data_summary shape', 'discovery_breadth', "
            "'bca_framework'. Set by the feedback author when known."
        ),
    )


GenericKind = Literal[
    "workload_shape",       # applies to all agents with a workload shape
    "architecture",         # applies to all agents using an architecture
    "domain",               # applies to all agents in a domain (sub-folder)
    "skill_design",         # applies to any skill of a particular shape
    "discovery_process",    # applies to all discovery sessions of a shape
]


class SignalClassification(BaseModel):
    """Output of specific_vs_generic_classifier for one signal.

    `is_generic=False` → drop, stays session-scoped. `is_generic=True` →
    eligible for clustering. The classifier defaults to specific when
    ambiguous; the prompt enforces "if you cannot articulate the workload
    shape / architecture / domain / discovery-pattern this lesson applies
    to, it's not generic enough."
    """

    is_generic: bool = Field(
        ..., description="True if the signal generalizes beyond the originating session."
    )
    generic_kind: GenericKind | None = Field(
        None,
        description=(
            "If is_generic=True, which axis of generality. Required when is_generic; "
            "null when is_generic=False."
        ),
    )
    generalizes_to: str | None = Field(
        None,
        description=(
            "If is_generic=True, the explicit articulation of WHAT shape / "
            "architecture / domain / pattern this lesson applies to. "
            "If you can't write this concretely, the signal isn't generic enough. "
            "Examples: 'query-response agents that interpret SQL results', "
            "'inner-pipeline skills that classify into a closed taxonomy'."
        ),
    )
    rationale: str = Field(
        ..., description="One sentence: why this classification."
    )


class SignalCluster(BaseModel):
    """A cluster of related signals across multiple sessions.

    Produced by signal_clusterer. The recurrence threshold gate (≥3 distinct
    sessions) is enforced after clustering, not during — so the human (or
    a downstream review pass) can still see clusters that don't meet the
    threshold for diagnostic purposes.
    """

    cluster_id: str = Field(..., description="Stable slug for this cluster.")
    theme: str = Field(..., description="One-sentence summary of what binds these signals.")
    signal_indices: list[int] = Field(
        ...,
        description="0-based indices into the input signal corpus that belong to this cluster.",
    )
    n_distinct_sessions: int = Field(
        ..., description="Count of unique session_ids represented in this cluster."
    )
    crosses_stages: bool = Field(
        ...,
        description=(
            "True if signals in this cluster come from BOTH discovery and "
            "inception stages. Cross-stage clusters are the highest-value "
            "promotions per plan 10 — they're the connective tissue."
        ),
    )


class SignalClusteringResult(BaseModel):
    """Output of signal_clusterer over the full corpus."""

    clusters: list[SignalCluster] = Field(
        default_factory=list,
        description=(
            "All clusters detected. Some may have <3 sessions and won't promote — "
            "still returned for trace / diagnostics."
        ),
    )
    unclustered_indices: list[int] = Field(
        default_factory=list,
        description="Signals that didn't fit into any cluster — singletons or noise.",
    )


class PromotionCandidate(BaseModel):
    """A draft pattern entry produced from a recurring + generic cluster.

    The curator writes these to `patterns/<category>/<slug>.candidate.md`
    (NOT the canonical `.md` — human review is the gate before promotion
    to experimental status, then a second gate before validated).
    """

    cluster_id: str
    n_distinct_sessions: int
    generic_kind: GenericKind
    generalizes_to: str
    candidate_pattern: PatternEntry
    suggested_path: str = Field(
        ...,
        description="patterns/<category>/<slug>.candidate.md — where the draft would be written.",
    )
    promotion_status: Literal["candidate", "below_recurrence_threshold", "duplicate_of_existing"] = Field(
        ...,
        description=(
            "candidate = ready for human review. below_recurrence_threshold = "
            "interesting cluster but only N<3 sessions; surfaced for diagnostics. "
            "duplicate_of_existing = matched an existing pattern entry by slug or theme; "
            "no draft written but the recurrence is recorded."
        ),
    )
    overlap_with_existing: str | None = Field(
        None,
        description="If duplicate_of_existing, the slug of the pattern this overlaps with.",
    )


class PromotionRunReport(BaseModel):
    """Top-level output of one `promote` invocation. Written to disk as
    `patterns/.promotion_runs/<timestamp>.json` for audit trail.
    """

    run_id: str
    run_at: str  # ISO timestamp
    n_signals_scanned: int
    n_signals_generic: int
    n_clusters: int
    n_clusters_above_threshold: int
    recurrence_threshold: int
    candidates: list[PromotionCandidate]
