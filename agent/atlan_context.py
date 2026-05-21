"""BoundedContext — the structured snapshot of what Atlan already knows.

When a discovery session starts with `--atlan-tenant` (+ scope arguments),
`agent/atlan_client.py` queries the Atlan REST API and returns one of these
objects. The mega-agent reads it (rendered into the system prompt) and uses
it to skip probes for facts that are already cataloged.

The schema mirrors Atlan's native model — `AtlasGlossaryTerm`, `Table`,
lineage relations, custom-metadata-as-tags — but only carries the fields
the discovery agent actually needs. No domain transformations; just the
slice that informs probing.

Six slots, per docs/internal/plans/06-atlan-context-integration.md:
  glossary_terms   business definitions, formulas, decision rules
  tables           schemas, column descriptions, types
  lineage          upstream / downstream relationships
  ownership        steward / owner per asset
  tags             governance / compliance flags
  business_domains semantic-domain organization
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Slot types
# ---------------------------------------------------------------------------


class GlossaryTerm(BaseModel):
    """One AtlasGlossaryTerm: a business-defined concept."""

    name: str = Field(..., description="Term display name (e.g. 'AOS', '%ACV', 'BCA_Competitive').")
    qualified_name: str | None = Field(
        None, description="Atlan QN, used for lineage joins."
    )
    definition: str | None = Field(
        None, description="The business definition. Authoritative — discovery should not re-ask if present."
    )
    glossary: str | None = Field(
        None, description="Parent glossary name."
    )
    category: str | None = Field(
        None, description="Parent category if the glossary uses hierarchy."
    )


class TableColumn(BaseModel):
    name: str
    data_type: str | None = None
    description: str | None = None


class TableDefinition(BaseModel):
    """One catalogued table — schema + column descriptions."""

    name: str
    qualified_name: str | None = None
    description: str | None = None
    columns: list[TableColumn] = Field(default_factory=list)
    row_count: int | None = None


class LineageEdge(BaseModel):
    """A single upstream→downstream relationship."""

    upstream_qn: str
    downstream_qn: str
    edge_type: Literal["column", "table", "term_to_table", "other"] = "other"


class LineageGraph(BaseModel):
    edges: list[LineageEdge] = Field(default_factory=list)


class Ownership(BaseModel):
    asset_qn: str
    asset_name: str
    owner: str | None = None
    steward: str | None = None
    certifier: str | None = None


class Tag(BaseModel):
    """A governance/compliance tag attached to an asset (e.g. PII, Certified)."""

    asset_qn: str
    asset_name: str
    tag_name: str
    classification: Literal["pii", "compliance", "certified_quality", "other"] = "other"


class BusinessDomain(BaseModel):
    """A semantic-domain boundary the customer uses to organize their work."""

    name: str
    description: str | None = None
    n_assets: int | None = None


# ---------------------------------------------------------------------------
# The aggregate — what gets attached to a DiscoverySession
# ---------------------------------------------------------------------------


class BoundedContext(BaseModel):
    """Snapshot of established Atlan context for the discovery scope.

    Attached to `DiscoverySpec.bounded_context` when the session starts with
    `--atlan-*` scope arguments. Persists with the session on disk; the
    mega-agent renders it into its system prompt on every turn so it's
    always in scope.

    `source_tenant` is captured verbatim from the CLI arg (e.g.
    `ces.atlan.com`). `fetch_status` distinguishes 'populated' (real data),
    'empty' (scope queried, nothing found — bootstrap case), and 'error'
    (Atlan unreachable; discovery degrades to probe-only mode).
    """

    source_tenant: str
    fetch_status: Literal["populated", "empty", "error", "not_configured"] = "not_configured"
    error_message: str | None = None

    # Scope arguments captured for trace.
    scope_glossary: str | None = None
    scope_tables: list[str] = Field(default_factory=list)
    scope_domains: list[str] = Field(default_factory=list)

    # The six slots.
    glossary_terms: list[GlossaryTerm] = Field(default_factory=list)
    tables: list[TableDefinition] = Field(default_factory=list)
    lineage: LineageGraph = Field(default_factory=LineageGraph)
    ownership: list[Ownership] = Field(default_factory=list)
    tags: list[Tag] = Field(default_factory=list)
    business_domains: list[BusinessDomain] = Field(default_factory=list)

    # ---- Convenience ----

    def is_populated(self) -> bool:
        return self.fetch_status == "populated" and (
            self.glossary_terms
            or self.tables
            or self.lineage.edges
            or self.ownership
            or self.tags
            or self.business_domains
        )

    def render_for_prompt(self, max_terms: int = 30, max_tables: int = 10) -> str:
        """Render as the 'Established context' block injected into the mega-agent
        system prompt. Keep it dense — every line should be load-bearing for
        the agent's probing.

        Truncates long lists to avoid blowing the prompt; if the customer
        references something truncated, the mega-agent can call `search_glossary`
        at runtime (when that tool lands).
        """
        if self.fetch_status == "not_configured":
            return ""
        if self.fetch_status == "error":
            return (
                f"### Established context (from Atlan tenant: {self.source_tenant})\n\n"
                f"*(Atlan was reachable, but the context fetch errored: "
                f"{self.error_message or 'unknown'}. Discovery proceeds in probe-only mode "
                f"for the technical thread.)*\n"
            )
        if not self.is_populated():
            return (
                f"### Established context (from Atlan tenant: {self.source_tenant})\n\n"
                f"*(Scope queried but no terms / tables / lineage cataloged for it yet. "
                f"This is the bootstrap case — capture every technical fact the customer "
                f"states as a candidate seed for their context layer.)*\n"
            )

        lines: list[str] = []
        lines.append(f"### Established context (from Atlan tenant: {self.source_tenant})")
        lines.append("")
        lines.append(
            "Treat the definitions and assets below as **authoritative** — the "
            "customer has already cataloged them. If they reference one of these, "
            "do NOT re-ask for the definition; build on what's known. If they "
            "describe a concept that isn't listed here, capture it as a candidate "
            "context gap (don't interrupt to ask)."
        )
        lines.append("")

        if self.glossary_terms:
            shown = self.glossary_terms[:max_terms]
            extra = len(self.glossary_terms) - len(shown)
            lines.append(f"**Glossary terms ({len(self.glossary_terms)} total)**")
            for term in shown:
                defn = term.definition or "(no definition cataloged)"
                # Compact one-line render.
                lines.append(f"- `{term.name}` — {defn.strip().splitlines()[0][:140]}")
            if extra > 0:
                lines.append(f"- ... ({extra} more terms not shown — call search_glossary if needed)")
            lines.append("")

        if self.tables:
            shown_t = self.tables[:max_tables]
            extra_t = len(self.tables) - len(shown_t)
            lines.append(f"**Tables ({len(self.tables)} cataloged)**")
            for tbl in shown_t:
                desc = tbl.description or ""
                cols_summary = (
                    f"{len(tbl.columns)} columns" if tbl.columns else "schema not loaded"
                )
                lines.append(
                    f"- `{tbl.name}` ({cols_summary}) — {desc.strip().splitlines()[0][:140] if desc else 'no description'}"
                )
            if extra_t > 0:
                lines.append(f"- ... ({extra_t} more tables)")
            lines.append("")

        if self.lineage.edges:
            lines.append(f"**Lineage** — {len(self.lineage.edges)} edges captured (downstream consumers of cataloged assets)")
            lines.append("")

        if self.ownership:
            lines.append("**Ownership**")
            for o in self.ownership[:10]:
                bits = []
                if o.owner:
                    bits.append(f"owner={o.owner}")
                if o.steward:
                    bits.append(f"steward={o.steward}")
                if not bits:
                    continue
                lines.append(f"- `{o.asset_name}` — {', '.join(bits)}")
            lines.append("")

        if self.tags:
            # Group by classification for compactness.
            by_class: dict[str, list[Tag]] = {}
            for t in self.tags:
                by_class.setdefault(t.classification, []).append(t)
            lines.append("**Governance tags**")
            for cls, tags in by_class.items():
                names = sorted({t.asset_name for t in tags})[:8]
                more = len({t.asset_name for t in tags}) - len(names)
                suffix = f" (+{more} more)" if more > 0 else ""
                lines.append(f"- {cls}: {', '.join(names)}{suffix}")
            lines.append("")

        if self.business_domains:
            lines.append("**Business domains**")
            for d in self.business_domains[:8]:
                count = f" ({d.n_assets} assets)" if d.n_assets is not None else ""
                lines.append(f"- `{d.name}`{count}{(' — ' + d.description) if d.description else ''}")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"
