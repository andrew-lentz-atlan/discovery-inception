# 04 — Atlan Context Integration

**Status:** design — not yet built. READ pathway is in-scope; write-back is deferred.
**Depends on:** access to Atlan's MCP / REST API (already exists in production at `ces.atlan.com` and `tenants.atlan.com`).
**Pairs with:** `05-technical-thread-discovery.md` (which consumes the bounded context this surfaces).
**Future:** `04b-atlan-write-back.md` will eventually cover the CES handshake for pushing `context_repo_gaps.md` proposals back. Deferred until CES integration patterns stabilize.

---

## The premise (and the deferred half)

Atlan is a customer's bottom-up context layer: tables, glossary terms, lineage, ownership, tags, business definitions. When a customer asks Atlan to help them build an agent, that context layer is already partly populated — and the parts that aren't populated yet are exactly the bottleneck that bottom-up tools can't fix on their own. That's where top-down discovery earns its keep.

**This plan covers the READ direction.** Discovery queries Atlan at session start to establish what's already known, primes the mega-agent with that context, and skips redundant questioning. It also captures gaps as a discrete artifact (`context_repo_gaps.md`) — an output the customer can act on manually for now.

**The WRITE direction (gaps flowing back into Atlan as proposed glossary terms / table descriptions / lineage edges) is deferred.** Two reasons:

1. The CES synthesis pipeline that would consume these gaps is itself in flux. Designing our output to match a target that's still being shaped wastes design effort.
2. The READ pathway delivers most of the value on its own. Without ever writing back, the discovery agent gets to skip 50–80% of technical probing on use cases where Atlan is well-populated. That's where the immediate quality win lives.

A stub for the eventual write-back is captured at the bottom of this doc.

---

## Why read from Atlan rather than from Databricks / Snowflake directly

Three reasons:

1. **Atlan is the customer's canonical context layer.** It's where their domain knowledge lives, not just their schemas. Reading from there means we get business definitions, lineage, ownership, governance tags — not just column types.
2. **Atlan abstracts the underlying warehouse.** A customer might be on Databricks today, Snowflake tomorrow, BigQuery for a specific business unit. Atlan presents a uniform view; the warehouse beneath is implementation detail.
3. **Atlan-as-context is the bet the company has made.** Building agents that go around Atlan would undercut the strategic story Atlan tells about itself. Reading from Atlan, citing Atlan, and feeding gaps back to Atlan is the consistent posture.

The customer's data warehouse only gets consulted at *agent runtime*, not at discovery time. Discovery's job is to read what's already cataloged, not to crawl raw data.

---

## What "reading from Atlan" looks like operationally

Discovery accepts new arguments at session start:

```bash
uv run python -m agent.cli start-session \
    --use-case-seed "Brand analyst agent for FS account ..." \
    --role-id fs-account-director \
    --atlan-tenant ces.atlan.com \
    --atlan-glossary Fabric_Care_Analytics \
    --atlan-tables "default.aos,default.ddm" \
    --atlan-domains "F&HC"
```

Each `--atlan-*` argument is optional. When provided, the `atlan_context_probe` sub-agent (defined in `05-technical-thread-discovery.md`) fetches the named scope at session start. The fetched context becomes part of the priors the mega-agent reads.

When no `--atlan-*` arguments are provided, the technical thread runs in probe-only mode (asks the customer the technical questions directly).

---

## What gets fetched

The bounded context returned by `atlan_context_probe` has six structural slots:

| Slot | What | Why discovery cares |
|---|---|---|
| `glossary_terms` | Business definitions, formulas, decision rules | Skip asking "what does ACV mean?" if it's defined |
| `tables` | Schemas, column descriptions, types, sample sizes | Skip asking "what columns are in aos?" if cataloged |
| `lineage` | Upstream / downstream relationships | Surfaces where data flows; informs root-cause-analyzer-style skill design |
| `ownership` | Steward / owner / certifier per asset | Informs escalation paths; matches discovery's existing `escalation_rule` topic |
| `tags` | PII / governance / certified-quality flags | Informs `governance_constraints` topic |
| `business_domains` | The semantic-domain organization the customer uses | Informs how to scope skills; cross-domain skills need different routing than intra-domain |

These map cleanly to Atlan's existing model (`AtlasGlossaryTerm`, `Table`, lineage relations, custom metadata). We don't need new Atlan concepts — we're consuming what's already there.

---

## The Atlan client

A new module: `agent/atlan_client.py` (or under `intake/` if it's primarily consumed there).

**Initial functions (read-only):**

```python
async def fetch_bounded_context(
    tenant: str,
    glossary: str | None = None,
    tables: list[str] | None = None,
    domains: list[str] | None = None,
    auth: AtlanAuth,
) -> BoundedContext:
    """Pull a structured snapshot of what Atlan knows about the given scope."""

async def get_glossary_terms(
    tenant: str,
    glossary: str,
    auth: AtlanAuth,
) -> list[GlossaryTerm]: ...

async def get_table_definitions(
    tenant: str,
    table_qns: list[str],
    auth: AtlanAuth,
) -> list[TableDefinition]: ...

async def get_lineage(
    tenant: str,
    asset_qns: list[str],
    auth: AtlanAuth,
    depth: int = 2,
) -> LineageGraph: ...

async def search_glossary(
    tenant: str,
    query: str,
    auth: AtlanAuth,
    limit: int = 10,
) -> list[GlossaryTerm]:
    """Free-text search across glossary terms — used when discovery surfaces a
    concept the bounded context didn't include."""
```

**Transport options:**

| Option | Trade-offs |
|---|---|
| Atlan REST API | Direct, well-documented, no extra dependencies. Bala's `atlan_client.py` is a working reference. |
| Atlan MCP server | Standardized agent-to-tool interface. Bala used this for SSE-streamed access. Cleaner long-term but more setup. |
| pyatlan (Python SDK) | Higher-level, batteries-included. Best for write paths; for reads, REST is fine. |

Lean toward **REST for the initial implementation** (smallest footprint, easiest to reason about) with **MCP as a parallel option** for any environment that already speaks MCP (Claude Desktop / Claude Code installations).

---

## Authentication

`.env` adds:

```
ATLAN_BASE_URL=https://ces.atlan.com    # or the customer's tenant
ATLAN_API_KEY=...                        # service account token
```

Customer-tenant variant: `ATLAN_BASE_URL` is per-session, not baked. CLI can override:

```bash
--atlan-tenant ces.atlan.com  # implies ATLAN_BASE_URL=https://ces.atlan.com
```

API keys never embedded in artifacts. They live in env vars; the recorded `session.json` references "tenant: ces.atlan.com" but no credentials.

---

## What "primed mega-agent" actually means

When `atlan_context_probe` returns a populated `BoundedContext`, the mega-agent's per-turn input gets a new section in the priors it reads:

```
### Established context (from Atlan tenant: ces.atlan.com)

**Glossary: Fabric_Care_Analytics**
- AOS Metrics (8 terms): Dollar Sales, Unit Sales, Dollar Share, ...
- DDM Metrics (13 terms): %ACV, TDP Total, Display TDP, ...
- BCA Framework (5 categories): Distribution, Promotion, Pricing, Assortment, Competitive
- ... (full term list with definitions)

**Tables**
- default.aos (17 columns) — fiscal-week brand × market × subbrand × form
- default.ddm (30 columns) — DPSM diagnostics at brand × form × segment × market

**Lineage**
- AOS Metrics → default.aos (column-level)
- DDM Metrics → default.ddm

**Ownership**
- F&HC bounded context owner: Megan (DNA platforms team)

If the customer references one of these assets, treat the definition as
authoritative. If they describe a concept that isn't listed here, capture
it as a candidate gap.
```

This is the structural difference between a discovery that asks *"what's a brand?"* and one that asks *"how do you distinguish a brand from a sub-brand in your hierarchy?"* — the difference between a generic interview and one anchored in the customer's actual vocabulary.

---

## Per-turn behavior

When the customer references an asset, the mega-agent should:

1. **Check the established context first.** If the asset is known, frame the next probe in terms of what's *above* the asset (decision rules, business meaning) rather than re-asking the asset itself.
2. **Capture the asset reference** on the resulting fact (`technical_asset_references` field per `03`).
3. **Flag the gap if the asset isn't established.** Don't interrupt the conversation — just record it for the close-out `context_gap_proposer`.

When `search_glossary` is exposed as a tool the mega-agent can call (analogous to `synthesize_my_thinking`), the agent can also opportunistically search for concepts mid-conversation rather than relying only on the initial bounded-context fetch.

---

## The 6 sub-questions the bounded-context fetch tries to answer

When discovery boots with Atlan integration on, the bounded-context probe is implicitly answering:

1. **What business vocabulary is canonical here?** (glossary terms)
2. **What data exists in machine-readable form?** (tables + schemas)
3. **How does the data flow?** (lineage)
4. **Who owns / can authoritatively answer questions about each piece?** (ownership)
5. **What governance / compliance constraints already apply?** (tags)
6. **What semantic-domain boundaries do they use?** (business_domains)

If the answers to all 6 come back populated, the technical thread basically doesn't need to probe — it just verifies. If they come back empty, the technical thread runs hot.

---

## The deferred write-back direction

When `context_gap_proposer` produces `context_repo_gaps.md` at session close (per `03`), each entry has the shape:

```yaml
- asset_type: glossary_term
  proposed_name: BCA_Competitive
  proposed_description: "Competitive root cause in the DPSM framework. Applies when..."
  rationale_facts: [fact_id_017, fact_id_023]   # which discovery facts justified it
  source_quote: "We classify root causes into Distribution, Promotion, Pricing, Assortment, Competitive..."
  proposed_category: Business_Change_Analysis
  proposed_glossary: Fabric_Care_Analytics
```

That artifact is the seed for the eventual write-back path. What the deferred path needs to figure out:

| Decision | Deferred |
|---|---|
| Direct write via Atlan API vs handoff to CES vs human-in-the-loop approval | Defer to CES integration design |
| Conflict resolution if a proposed term already exists | Defer — start with a "proposed, awaiting review" status |
| Versioning of glossary terms (which version did discovery propose?) | Defer to glossary versioning conventions in Atlan |
| Who owns the proposed terms before they're approved | Defer to stewardship model in the customer tenant |

For now: `context_repo_gaps.md` is a markdown artifact a human reads. The pathway to "agent writes to Atlan" is the next iteration.

---

## What happens when Atlan returns nothing

The bootstrap case — customer has a tenant but the relevant domain is empty.

```
$ uv run python -m agent.cli start-session ... \
    --atlan-tenant ces.atlan.com \
    --atlan-glossary Customer360_Analytics

[atlan_context_probe] Querying ces.atlan.com for glossary 'Customer360_Analytics'...
[atlan_context_probe] Glossary exists but has 0 terms.
[atlan_context_probe] No tables tagged with this domain.
[atlan_context_probe] No lineage.
[atlan_context_probe] Status: empty — technical thread will probe customer directly.
```

Discovery proceeds normally. Technical thread runs in probe-only mode. At close, `context_repo_gaps.md` is a substantive document with proposed glossary terms, table descriptions, and lineage relationships drawn from the conversation.

That artifact becomes the customer's seed for populating their Atlan tenant — *"if you want to enable agentic workflows on this domain, here's what you need to put in your context layer first."*

---

## What happens when Atlan is unavailable

Graceful degradation. The `atlan_context_probe` step times out or errors. Discovery proceeds without the established context — same behavior as if `--atlan-tenant` was never specified. A warning surfaces in the session log; the resulting spec.md is annotated with "(Atlan context was not available for this session — technical thread captured by probing only)."

We never block discovery on Atlan availability. The bottom-up layer is a nice-to-have at the discovery stage, not a hard dependency.

---

## Open questions

1. **What tenant authentication model do we support?** Service-account API keys (the simplest)? Per-user OAuth (the safest)? Both? Lean simplest-first.
2. **Should we cache fetched bounded contexts?** Same use case run twice in a day — re-fetch from Atlan or read a local cache? Caching speeds things up; freshness might matter. Start with no-cache; revisit if it becomes painful.
3. **What's the granularity of bounded-context scope?** Glossary-level (`Fabric_Care_Analytics`)? Domain-level (`F&HC`)? Multi-glossary (`["A", "B"]`)? Support all three; pick the loosest as default behavior when scope is ambiguous.
4. **Should we expose `search_glossary` as a runtime tool to the mega-agent?** Probably yes — adds latency but lets the agent fill gaps as the conversation surfaces them, not just at session start. Test empirically.
5. **How do we handle the `ces.atlan.com` vs customer-tenant case in development?** During Atlan-internal dev work, `ces.atlan.com` is the testing tenant; customer-facing deployments would point at a customer tenant. The CLI argument handles this cleanly; no other affordance needed.

---

## Implementation sequence

1. Add `agent/atlan_client.py` with the five fetch functions (`fetch_bounded_context`, `get_glossary_terms`, `get_table_definitions`, `get_lineage`, `search_glossary`)
2. Add `BoundedContext` Pydantic schema with the 6 slots
3. Wire `atlan_context_probe` sub-agent to fetch + summarize on session start (matches `03`'s spec)
4. Extend mega-agent's priors block to include the "Established context" section when present
5. CLI: add `--atlan-tenant`, `--atlan-glossary`, `--atlan-tables`, `--atlan-domains` arguments
6. Auth: `.env` reads `ATLAN_BASE_URL`, `ATLAN_API_KEY`
7. Validate on the P&G case: re-run discovery against `ces.atlan.com` with the `Fabric_Care_Analytics` glossary scope. Confirm the established context includes BCA, table schemas, and that the technical thread skips re-asking what's already there.
8. Document the deferred write-back stub (this doc's footer becomes `04b-atlan-write-back.md` once the CES handshake is defined).

Estimated 2–3 days of focused work. Atlan client + schema is most of it; the prompt integration is small.
