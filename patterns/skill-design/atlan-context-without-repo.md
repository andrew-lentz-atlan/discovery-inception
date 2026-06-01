---
title: Using Atlan as Context Layer (without a Context Repo)
category: skill-design
status: draft
last_updated: 2026-05-29
source_external:
  - Atlan MCP Server README (atlanhq/agent-toolkit, GitHub)
  - Atlan MCP Overview (docs.atlan.com/product/capabilities/atlan-ai/how-tos/atlan-mcp-overview)
  - Atlan Remote MCP (docs.atlan.com/product/capabilities/atlan-ai/how-tos/remote-mcp-overview)
  - Atlan MCP Server — What's New (Confluence, Data & AI Governance, 2026-03)
  - atlanhq/atlan-python HISTORY.md
  - "Build your first metadata workflow" tutorial (docs.atlan.com Python SDK tutorials)
  - Atlan Metadata Lakehouse Documentation (Bowornmet Hudson, 2025-06)
  - MDLH Gold Layer reference (docs.atlan.com/platform/lakehouse/references/gold-layer)
  - atlanhq/lakehouse-solutions — snowflake/gold-layer/MDLH_Gold_layer.sql
  - "Issue: API Rate Limiting Error When Using Atlan Python SDK .save()" (TFKB, 2025-04)
  - "Agent Memory Layer on Your Data Catalog: A How-To Guide" (atlan.com/know)
applies_when:
  workloads: [agent-needs-metadata-context, single-customer-agent, prototype-with-atlan-grounding, metadata-driven-tool-call, write-back-to-atlan]
  constraints: [no-context-repo-overhead, customer-already-has-atlan-tenant, single-purpose-context-need, per-invocation-scope, fast-iteration]
contradicts: []
related:
  - skill-design/atlan-context-repos
  - skill-design/atlan-mcp-integration
  - skill-design/atlan-skills-as-assets
snapshot_date: 2026-05-29
---

# Using Atlan as Context Layer (without a Context Repo)

When an agent needs Atlan context but the team doesn't have or doesn't want a full context repo, the question becomes: how do you reach into Atlan from the agent loop directly? This entry covers the three first-class paths — pyatlan SDK, the Atlan MCP server, and the Metadata Lakehouse (MDLH) — and when each fits.

This is the fallback path relative to [`atlan-context-repos`](./atlan-context-repos.md) — but it's also often the *right* path. Most agents don't need a versioned, governed, multi-team context graph. They need glossary terms for one workflow, lineage for one asset, or to write back a description after generating one. For those, plumbing into Atlan directly is faster and clearer than standing up repo machinery. The dangerous default is the inverse — teams reach for "context repo" as the only legitimate option and burn weeks on plumbing before validating whether the agent even needs that structure.

## The three paths at a glance

| Path | What it is | Best for |
|---|---|---|
| **pyatlan SDK** | Python client. Full read + write surface. | Targeted lookups (1–100 assets), all mutations, custom-metadata writes, lineage from a known anchor. |
| **Atlan MCP server** | ~25 MCP tools over OAuth/API key. Hosted at `mcp.atlan.com/mcp`. | Agents in MCP-aware runtimes (Claude, Cursor, ChatGPT, Codex, Copilot Studio) where tool semantics beat SDK plumbing. |
| **Metadata Lakehouse (MDLH)** | Atlan metadata as Iceberg tables, queryable from Snowflake / Databricks / Athena / Spark / BigQuery. | Bulk reads (1000s+ assets), analytics, joins across asset types. Read-only. |

The boundary isn't sharp. The choice collapses on three axes: **direction** (read vs. write), **volume** (one asset vs. thousands), and **runtime** (Python loop vs. MCP-aware client).

## Path 1 — pyatlan (the SDK)

Python-native. The most expressive surface. Required for **all mutations** — MCP exposes a subset of writes, MDLH is read-only.

```python
from pyatlan.client.atlan import AtlanClient
from pyatlan.model.assets import Table

client = AtlanClient(base_url="https://tenant.atlan.com", api_key="...")

# Targeted read — the workhorse "agent has an anchor" pattern
table = client.asset.get_by_qualified_name(
    asset_type=Table,
    qualified_name="default/snowflake/1234567890/DB/SCHEMA/CUSTOMERS",
)
```

API keys tie to a service user; the user's permissions are the agent's. Prefer env vars (`ATLAN_BASE_URL`, `ATLAN_API_KEY`); never hardcode. Token rotation is manual — no built-in refresh on API keys.

### Search via FluentSearch

```python
from pyatlan.model.fluent_search import FluentSearch
from pyatlan.model.enums import CertificateStatus

request = (
    FluentSearch()
    .where(FluentSearch.asset_type(Table))
    .where(FluentSearch.active_assets())
    .where(Table.CERTIFICATE_STATUS.eq(CertificateStatus.VERIFIED))
    .include_on_results(Table.NAME, Table.QUALIFIED_NAME, Table.DESCRIPTION)
    .page_size(100)
).to_request()

for table in client.asset.search(request):  # lazy paginated iterator
    ...
```

Past ~5K rows you start hitting timeouts — move to MDLH.

### Writes — updater + batch

```python
to_update = Table.updater(qualified_name=qn, name="CUSTOMERS")
to_update.description = "Cleaned customer master. Source of truth for ID resolution."
to_update.certificate_status = CertificateStatus.VERIFIED
client.asset.save(to_update)
```

`updater()` and `creator()` produce partial assets; `.save()` is upsert by qualified name. For bulk, use `Batch(client.asset, max_size=20)` — bundles multiple `.save()` calls and stays under rate limits.

### Custom metadata — the footgun

```python
from pyatlan.model.custom_metadata import CustomMetadataDict

cm = CustomMetadataDict(client=client, name="Data Stewardship")  # client= REQUIRED in 2.x
cm["Owner"] = "data-platform@co.com"

response = client.asset.save(asset)
guid = response.mutated_entities.update[0].guid

# Apply CM AFTER save, with GUID from response. Not via asset.set_custom_metadata().
client.asset.update_custom_metadata_attributes(guid=guid, custom_metadata=cm)
```

Two real production footguns: `CustomMetadataDict(name=...)` without `client=` raises `TypeError`; `asset.set_custom_metadata(cm)` + `.save()` silently no-ops. Several customer scripts shipped the second bug.

### When SDK is right

Anchored reads (you know QN/GUID), all writes, inline mutations inside skills, App Framework apps.

### When it's not

Filter-based bulk queries ("all tables where description is empty AND tier='gold' AND no owner") — that's MDLH, not 8000 search round trips.

## Path 2 — Atlan MCP server

Two flavors as of mid-2026:

- **Remote MCP** (recommended, GA): hosted at `https://mcp.atlan.com/mcp`. Per-tenant. OAuth or API key. Zero install. Where Atlan is actively investing.
- **Local MCP** (`ghcr.io/atlanhq/atlan-mcp-server`): **maintenance-mode only** per the README. Use Remote unless you have a hard requirement (air-gapped).

MCP gives the agent **tool semantics it understands natively** — discovery, structured inputs/outputs — without you wrapping pyatlan calls in tool definitions yourself. If the runtime is Claude Desktop / Claude Code / Cursor / ChatGPT / Codex / Gemini CLI / Microsoft Copilot Studio, MCP is the lowest-friction path.

### Tools exposed (post-March-2026 split)

| Tool | Purpose |
|---|---|
| `semantic_search_tool` / `search_assets_tool` | NL search / structured filters (split deliberately — original monolithic search had a ~2500-token docstring eating LLM context) |
| `count_assets_tool` | Aggregate count without fetching rows |
| `get_asset_tool` | Single asset by GUID |
| `resolve_metadata_tool` | Vector-resolve users / tags / terms / schemas / domains |
| `traverse_lineage_tool` | Upstream/downstream walks |
| `update_assets_tool`, `update_custom_metadata_tool` | Description, certificate, README, CM |
| `add_atlan_tags_tool` / `remove_atlan_tag_tool` | Classification tags |
| `create_glossary*_tool`, `create_dq_rule_tool` (+ variants) | Glossary, DQ rule creation |
| `search_atlan_docs_tool` | Atlan docs search with LLM-cited answers |

### Minimal Remote MCP config (Claude Desktop)

```json
{
  "mcpServers": {
    "atlan": { "url": "https://mcp.atlan.com/mcp" }
  }
}
```

OAuth runs on first invocation; the agent inherits the user's roles. For headless / service-account agents, use API-key mode (Local MCP or self-hosted Remote):

```json
{
  "mcpServers": {
    "atlan": {
      "command": "uvx",
      "args": ["atlan-mcp-server"],
      "env": {
        "ATLAN_API_KEY": "...",
        "ATLAN_BASE_URL": "https://tenant.atlan.com",
        "ATLAN_AGENT_ID": "my-agent"
      }
    }
  }
}
```

**Always set `ATLAN_AGENT_ID`.** It populates the `X-Atlan-Agent-Id` audit header — the only way to trace which agent did what in Atlas/nginx logs. Without it, audit trails attribute everything to "unknown service".

### Tool restriction — the cheapest write-safety lever

```bash
RESTRICTED_TOOLS=update_assets_tool,update_custom_metadata_tool,add_atlan_tags_tool
```

Set this to expose reads only. Most production read-only deployments do this. Tool availability is also **LaunchDarkly-gated per tenant** — a tool that works on tenant A may not be enabled on tenant B, with no clean API to enumerate enabled tools.

### When MCP is right

MCP-aware runtimes with zero SDK plumbing; conversational interfaces over Atlan; shared infra serving many agents from one configured server.

### When it's not

Programmatic Python loops doing thousands of writes (SDK). Complex multi-asset joins (MDLH).

## Path 3 — Metadata Lakehouse (MDLH)

Atlan publishes the full metadata estate as **Apache Iceberg tables** via an Iceberg REST Catalog (Apache Polaris). Any Iceberg-compatible engine reads it — Snowflake, Databricks, Athena, Trino/Presto, Spark, BigQuery. Tenant-isolated S3 / ADLS / GCS.

| Namespace | Contents | When to use |
|---|---|---|
| `entity_metadata` | Raw — 350+ tables, one per asset type. Mirrors the metamodel. 200+ cols/table. | Fine-grained, lineage edge traversal, custom joins. |
| `gold` | Curated, pre-joined ~11 tables (`assets`, `glossaries`, `lineage`, `data_mesh`). 20–40 cols. | LLM-friendly. Most agent queries should start here. |
| `entity_history` | 90-day snapshot history | Change-over-time analysis |
| `usage_analytics` | Usage events, identity snapshots | Adoption, popularity signals |
| `observability` | Workflow runs, DQ scores | Pipeline health, DQ trending |

The gold layer was built specifically to make MDLH **agent-queryable without a giant schema preamble.** If you're plumbing an LLM-generated-SQL skill, target gold.

### Sample query — gold

```sql
SELECT asset_name, asset_qualified_name, certificate_status
FROM atlan_lakehouse.gold.assets
WHERE connector_name = 'snowflake'
  AND asset_type = 'Table'
  AND certificate_status = 'VERIFIED'
  AND (owner_users IS NULL OR cardinality(owner_users) = 0)
LIMIT 100;
```

### Sample query — column lineage via `entity_metadata`

```sql
WITH table_cols AS (
  SELECT col_guid FROM atlan_lakehouse.entity_metadata.column
  WHERE table_guid = 'aeaf7ed9-...'
)
SELECT cp.input_qualified_name, cp.output_qualified_name, cp.process_name
FROM atlan_lakehouse.entity_metadata.column_process cp
WHERE cp.input_column_guid IN (SELECT col_guid FROM table_cols)
   OR cp.output_column_guid IN (SELECT col_guid FROM table_cols);
```

### Engine paths

- **Snowflake** — external catalog via Iceberg REST. Most mature.
- **Databricks** — native Iceberg REST is **still preview**; workaround uses `CREATE TABLE … UNIFORM ICEBERG … METADATA_PATH` against metadata files, gated by a private-preview Databricks feature.
- **Athena** — Lake Formation federated Iceberg catalog. Works for AWS-resident customers.
- **BigQuery** — Iceberg REST Catalog Federation. Newer path.

### Freshness — read the fine print

Native gold layer (Atlan-managed) refreshes minutes-to-hour-ish behind the OLTP metastore. Customer-managed gold (Snowflake Dynamic Tables, deployed via `lakehouse-solutions/snowflake/gold-layer/MDLH_Gold_layer.sql`) defaults `SCHEDULE = 'USING CRON 0 * * * * UTC'` — hourly. Self-hosters have been bitten by stale-data bugs (Medtronic, March 2026 — gold table silently stopped refreshing for 19 days due to a tenant config flag).

**For agent design**: if you need real-time consistency for write-back decisions, use the SDK. Use MDLH for analytical queries where minutes-to-hours staleness is fine. **Always include a freshness check** — `SELECT MAX(source_updated_at) FROM gold.assets` — and bail/warn past your tolerance.

## Which to choose when

| Need | Path |
|---|---|
| Look up 1 asset by QN | SDK |
| Search 1–100 assets by attribute | SDK or MCP `search_assets_tool` |
| Find all assets matching a complex filter (1000s+) | MDLH |
| Update description / certificate / CM | SDK or MCP `update_assets_tool` |
| Bulk update 10K assets | SDK `Batch` (rate-limit aware) |
| Trace lineage 2 hops from anchor | SDK or MCP `traverse_lineage_tool` |
| Full-graph lineage analytics | MDLH `column_process` + gold lineage view |
| Catalog usage analytics | MDLH `usage_analytics` |
| Agent in Claude Desktop / Cursor / ChatGPT, no Python loop | MCP (Remote) |
| Agent in a Python orchestrator (Claude Agent SDK, LangGraph) | SDK; MCP only if you want the tool surface |

Common production shape: **SDK for writes, MDLH for bulk reads, MCP if the agent is in an MCP-aware client.** Not mutually exclusive.

## What context to pull (the typical menu)

The same content a context repo would distill — the difference is *where* the distillation happens. With raw integration, it happens at query time, in your agent code.

- **Glossary terms** — vocabulary, definitions, owners, certification. Pull via SDK or MCP `resolve_metadata_tool`; bulk via `entity_metadata.glossary_term`.
- **Asset metadata** — table/column/dashboard descriptions, tags, certifications, READMEs.
- **Lineage** — "what's upstream", "what breaks if I change Y" for impact analysis.
- **Ownership + governance** — who owns this, what classification (PII, Confidential).
- **Custom metadata** — per-org annotations (compliance tags, lifecycle stage, business unit).
- **Usage analytics** — popularity signals for ranking ("which of these 50 candidates is the right one?").

## When this beats a context repo

- **Single-purpose agents that need one slice.** "Answers questions about glossary terms" — wrap `resolve_metadata_tool` and ship. Repo machinery is pure overhead.
- **Per-customer scoping.** Customer A uses their tenant, customer B uses theirs. A static repo would need re-curation per customer.
- **Rapid prototyping.** First two weeks. You don't know what context shape you need. Raw calls let you iterate; lock into a repo *later*, if at all.
- **Write-heavy agents.** Repos describe context for reading. Writers need SDK regardless — repo doesn't help.
- **Per-invocation scope changes.** "For this question fetch lineage; for that question fetch glossary." Fetching dynamically is more honest than a repo that statically declares all of it.

## When a context repo beats raw integration

- Multiple agents need the same configured context (curate once, reuse everywhere).
- Configuration needs versioning + governance (PRs as audit surface).
- Cross-team reuse is a hard requirement.
- Rich structured graphs with relationships, hierarchies, derived fields, business rules — beyond "fetch these fields".
- Testing context changes independently of agent changes.

The honest split: if you're building **the first agent** against Atlan for a use case, start raw. Move to a repo when you have evidence of reuse pressure. Premature repos rot faster than premature inline calls.

## Failure modes — real, with receipts

### SDK rate limits

- **Global SDK limit: 400 RPM** on programmatic calls (`.save()`, search). Block on 429: 1 minute. Per-tenant. Multi-pod tenants scale the ceiling (`500 × pod_count` internal formula).
- Webhooks: separate 1000-RPM default, bumpable on request.
- pyatlan retries 429 with backoff by default. Don't write retry logic; write batching.
- Production incident (Dec 2025, pod-app-longtail): newer pyatlan started hitting rate-limited `v2/lineage/list` endpoints. Sub-minute workflows started failing. Atlan rolled two packages back to pyatlan 8.0.2. **Newer-is-better doesn't hold if your code hits lineage endpoints heavily.** Pin and test.

### MDLH freshness gaps

- Native gold: minutes-to-hour-ish.
- Customer-managed gold: hourly default; customer owns the refresh job.
- Real outage shape: gold table silently stops refreshing (Medtronic, 19 days stale before detection). The fix is freshness checks in the agent, not trust.

### MCP server reality

- Remote MCP at `mcp.atlan.com/mcp`: GA, per-tenant, hosted.
- Local MCP: maintenance-mode only; the README directs you to Remote.
- Tool availability is LaunchDarkly-flag-gated per tenant; no clean enumeration API. You discover at runtime.
- OAuth (browser-based, per-user) for interactive agents; API key for headless. Don't mix.

### Common pyatlan footguns

- `DataProduct.creator()` requires `asset_selection`. The accepted-empty pattern is `Bool(filter=[Terms(field="__guid", values=[])])`. `MatchNone()` raises at save.
- `CustomMetadataDict(name=...)` without `client=` raises `TypeError` in 2.x.
- `asset.set_custom_metadata(cm)` + `.save()` silently no-ops. Use `update_custom_metadata_attributes(guid, custom_metadata=cm)` *after* save with GUID from response.
- `DataProduct.creator()` doesn't set `daapVisibility` or `owner_users` (pyatlan ≤ 2.x; fix in flight per BLDX-1252). Marketplace tile renders blank without post-creation mutation.
- `Connection.creator()` validates connector slug `^[a-z0-9-]+$` since BLDX-1294. Underscores break server-side import silently.

### Determinism in Temporal / async runtimes

Inside Temporal workflows (App Framework pattern), pyatlan modules must be in `passthrough_modules` on the App class. Otherwise the deterministic sandbox rejects calls. Same for any other deterministic-replay runtime.

## Maturity snapshot — mid-2026

| Surface | Status |
|---|---|
| pyatlan SDK | 8.x stable; fully thread-safe since the `ContextVar`/TLS removal refactor. Active development; some endpoint coverage gaps still ship as patch releases. |
| Atlan Remote MCP | **GA.** `mcp.atlan.com/mcp`. Per-tenant. ~25 tools. The recommended path. |
| Atlan Local MCP | Maintenance-mode only. Use Remote unless air-gapped. |
| MDLH — native gold | **GA** (rolled out across lakehouse tenants March 2026). Recommended starting point for analytical queries. |
| MDLH — Snowflake | Most mature engine path. |
| MDLH — Databricks | Workaround required (no native Iceberg REST); private-preview Databricks feature gates it. |
| MDLH — Athena / BigQuery | Working, newer; expect setup-time tickets. |
| App Framework MCP exposure | Roadmap. Promise: App Framework apps auto-expose actions as MCP tools. Not yet GA. |

## When raw integration is overkill

- **Single-demo agents** — one tenant, one query, never deployed. Curl the REST API. Don't install pyatlan.
- **Agents that just need a glossary list** — a cached JSON dump regenerated nightly is often the right answer.
- **Cross-tool semantics** — if the agent's primary job isn't metadata reasoning, the metadata might belong in the system prompt, not in a live integration.

Cost of integration scales with surface area. Pick the smallest surface that solves the problem.

## Empirical anchor

Patterns observed across Atlan customer integrations and the Atlan internal app stack as of mid-2026: pyatlan-backed scripts (Edenred's classification-sync workflow, Sophos's Copilot harvest exploration), MCP-backed conversational agents (Bancorp's ChatGPT integration, Tiger Global's Snowflake-MDLH integration), and lakehouse-driven analytical agents (Chick-fil-A's Athena queries, Medtronic's Snowflake gold layer). The 400-RPM SDK limit, gold-layer refresh failures, and custom-metadata save footgun are all documented production incidents — not theoretical risks.

Neutral framing: **Atlan integration is the boring, fast-to-build path that solves most agent context needs.** Reach for a context repo when you have evidence you need one, not as a default. Reach for raw integration first.
