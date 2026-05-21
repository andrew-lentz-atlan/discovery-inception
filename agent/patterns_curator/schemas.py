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
    "internal_plan",          # one of our plans/ docs
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
