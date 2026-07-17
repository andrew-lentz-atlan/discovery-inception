---
title: Atlan MCP Server — Integration Deep Dive
category: skill-design
status: draft
last_updated: 2026-05-29
source_findings: []
source_external:
  - Atlan public docs — Model Context Protocol (MCP) overview
  - Atlan public docs — Remote MCP overview
  - Atlan public docs — Set up Claude Code with Remote MCP
  - Atlan public docs — Integrate Model Context Protocol (Application SDK)
  - atlanhq/agent-toolkit/modelcontextprotocol — README
  - Internal Confluence — "Atlan MCP Server — What's New" (Arpit Upadhyay, 2026-03)
  - Internal Confluence — "Atlan MCP Server — What Changed & Why" (2026-03)
  - Internal Confluence — "Atlan MCP Server — Security & Authentication FAQ" (2026-05)
  - Internal Confluence — "Remote MCP — Dual Authorization Design"
applies_when:
  workloads: [agent-needs-atlan-metadata, claude-code-cursor-resident-workflows, multi-runtime-context-sharing, governed-cross-team-agent-reuse]
  constraints: [runtime-speaks-mcp, prefer-managed-integration-over-sdk-glue, want-rbac-from-atlan-to-propagate]
contradicts: []
related: [skill-design/atlan-context-without-repo, skill-design/atlan-context-repos, skill-design/atlan-skills-as-assets, harnesses/claude-agent-sdk-deep-dive]
snapshot_date: 2026-05-29
---

# Atlan MCP Server — Integration Deep Dive

Atlan exposes an MCP server. That sentence is doing a lot of work. Concretely: Atlan runs a hosted, per-tenant Model Context Protocol endpoint at `https://mcp.atlan.com/mcp` (and a tenant-specific `/mcp/api-key` variant) that any MCP-compatible runtime can call as a tool provider. The same protocol is also available via a Dockerized local server (`ghcr.io/atlanhq/atlan-mcp-server:latest`, `pip install atlan-mcp-server`) — though as of May 2026 the local install path is **maintenance-only** and the hosted endpoint is the recommended integration. The pitch: **one integration layer, many runtime consumers.** Claude Code, Claude Desktop, Claude Connector (web), Cursor, ChatGPT (developer mode), Gemini CLI, VS Code, Windsurf, Microsoft Copilot Studio, n8n, Google ADK — anything that speaks MCP plugs into the same tools.

This deep-dive is the long form of one of three integration paths surveyed in [`atlan-context-without-repo.md`](./atlan-context-without-repo.md). The other two — pyatlan SDK calls and MDLH lakehouse reads — are also valid, and the last section here is when to pick which.

## What the server actually is

```
┌── Agent runtime (Claude Code, Cursor, LangGraph + MCP adapter, ...) ──┐
│                                                                        │
│   MCP client  ─────── HTTPS / streamable-http ────────────►            │
│                                                                        │
└─────────────────────────────────────────┬──────────────────────────────┘
                                          ▼
                ┌──────────────────────────────────────────┐
                │   Atlan Remote MCP (mcp.atlan.com/mcp)   │
                │   FastMCP 2.x server (Python 3.11+)      │
                │                                          │
                │   ── OAuth 2.1 (Keycloak JWKS) ─┐        │
                │   ── API key (Bearer)  ────────┤        │
                │   ── Tool restriction middleware│       │
                │                                 ▼        │
                │   28 registered tools  ─►  pyatlan +    │
                │                            search APIs +│
                │                            DSL + lineage │
                └────────────────┬─────────────────────────┘
                                 ▼
                         Atlan tenant
                         (atlas pods, metastore,
                          search index, lineage graph)
```

Three things to internalize:

1. **It's not a thin proxy over pyatlan.** Atlan's MCP team rewrote the tool surface twice. The original 14-tool implementation had a 2,500-token search docstring, broken tag search, no discoverability for tags/CM schemas/users, and a monolithic update tool that confused models. The current implementation (~28 tools) added `resolve_metadata` as a single vector-search discovery endpoint, split search into semantic vs. structured, and trimmed roughly 85% of token overhead via deferred loading and compressed docstrings. The tool design *is* the product.
2. **Auth propagates Atlan RBAC.** OAuth mode validates JWTs against Atlan's Keycloak (RS256, JWKS endpoint), reads `sub` as the calling user, and every downstream Atlan API call runs under that user's roles, personas, and policies. API-key mode binds to the API token's persona. Either way, the agent inherits the user's visibility — not the agent's.
3. **Per-tenant.** The hosted endpoint is one URL but the tenant is identified by the OAuth realm / API key. There is no cross-tenant call surface.

## The tool catalog (as of May 2026)

Source: `docs.atlan.com/product/capabilities/atlan-ai/how-tos/atlan-mcp-overview`. Twenty-eight tools, grouped into eight categories. Read-only vs. write classification is enforced server-side and per-tenant; admin-only tools require admin role on the tenant.

| Category | Tool | Access | What it does |
|---|---|---|---|
| **Search & discovery** | `semantic_search` | Read | NL query → ranked assets via vector search |
| | `search_assets` | Read | Structured filters (type, certification, dates). Default limit 10, max 100/call |
| | `count_assets` | Read | Aggregation without fetch — answers "how many?" |
| | `get_asset` | Read | Full asset by GUID. Column-level attrs only available here, not from search |
| | `resolve_metadata` | Read | Vector search across 5 namespaces (users, tags, glossary, CM, domains) |
| | `get_groups` | Read | List groups + members for ownership resolution |
| **Lineage & exploration** | `traverse_lineage` | Read | Upstream/downstream traversal. Recommend single-hop calls for wide graphs |
| | `query_assets` | Read | Run SQL on connected sources (Snowflake, Databricks). Sample data only |
| **Asset metadata** | `update_assets` | Write | Description, certification, README. Glossary term updates require parent glossary GUID |
| | `update_custom_metadata` | Write | Set CM attribute values on an asset |
| | `add_atlan_tags` | Write | Apply classification tags, optional propagation |
| | `remove_atlan_tag` | Write | Remove a tag |
| | `manage_announcements` | Write | Add/remove info/warning/issue notices |
| **Custom metadata** | `create_custom_metadata_set` | Admin | Define a new CM set |
| | `add_attributes_to_cm_set` | Admin | Extend CM schema |
| | `remove_attributes_from_cm_set` | Admin | Trim CM schema |
| | `remove_custom_metadata` | Write | Clear CM values from an asset |
| | `delete_custom_metadata_set` | Admin | Permanently delete a CM set |
| **Asset lifecycle** | `manage_asset_lifecycle` | Write | Archive, restore, purge |
| **Business glossary** | `create_glossary` / `create_category` / `create_term` | Write | Glossary scaffolding |
| **Data domains** | `create_domain` / `create_data_product` | Write | Domain hierarchy + data products |
| **Data quality** | `create_dq_rule` / `update_dq_rule` / `schedule_dq_rule` / `delete_dq_rule` | Write | Column/table/SQL DQ rules |

GA posture: the Remote MCP server itself was in private preview through 2025 H2 and is now **enabled for all tenants** per `docs.atlan.com/.../remote-mcp-overview`. The tool list is versioned at the server, not the client — Remote MCP picks up new tools automatically; Local MCP requires a Docker image bump. Individual tools can be enabled/disabled per tenant via LaunchDarkly flags (confirmed in the internal "What's New" page). If a customer says "we don't see X" the answer is often "your tenant has it gated, not the server."

## Tool design from the consumer side

The agent author's job is to give the orchestrating LLM enough scaffolding that it picks the right tool at the right point. Two patterns matter.

### Registration

In **Claude Code**, registration is one shell command (OAuth) or a short JSON snippet (API key):

```bash
# OAuth — uses your Atlan SSO, scoped to your roles
claude mcp add --transport http atlan https://mcp.atlan.com/mcp

# API key — for automation, service accounts, or local dev
claude mcp add-json atlan-key '{
  "type": "http",
  "url": "https://mcp.atlan.com/mcp/api-key",
  "headers": {"Authorization": "Bearer <API_KEY>"}
}'
```

In the **Claude Agent SDK** (Python), the same server registers via the SDK's MCP-server config block — see `harnesses/claude-agent-sdk-deep-dive.md` for the full pattern. The point is the agent code doesn't import pyatlan; it just lists the MCP endpoint and the SDK handles discovery, schema, and invocation.

For **LangGraph / OpenAI Agents SDK / Pydantic AI**, you need an MCP-to-tool adapter (FastMCP client, `langchain-mcp-adapters`, or the OpenAI Agents SDK's MCP support). Each of these turns MCP tools into native tool objects in their respective frameworks. The integration is a few lines once you've added the adapter dependency.

### Prompting the orchestrator

The MCP server does its own work to make tools self-describing, but the agent author still has to teach the LLM the right *sequence*. A customer ticket (May 2026) is the canonical bad case: customer asked Claude to "retrieve columns for a Databricks View"; the LLM called `search_assets` (which returns asset envelopes without column-level details), got back the qualified name, and stopped — because it didn't know to follow with `get_asset` to pull columns. The tool descriptions don't enforce sequence; the agent's system prompt has to.

A workable system-prompt skeleton for an Atlan-aware agent:

```
You have access to Atlan via MCP tools. Two patterns to follow strictly:

1. RESOLVE → ACT. Before calling any write tool, call resolve_metadata
   to convert user-spoken names (tag names, user names, glossary terms,
   custom metadata schemas, domains) into Atlan GUIDs. Never guess GUIDs.

2. SEARCH → GET. search_assets returns asset envelopes only — no
   column lists, no full custom metadata. If the user asks about
   columns, data types, or full custom-metadata values, follow up
   with get_asset using the GUID from the search.

For lineage on wide graphs, call traverse_lineage one hop at a time.
For aggregation questions ("how many...") use count_assets, not search.
```

This is `skill-design/inner-pipeline.md` applied at the system-prompt level rather than inside a single skill. If you find yourself writing this scaffolding inside every agent that touches Atlan, that's the signal to package it as a SKILL.md — see [`skill-design/atlan-skills-as-assets.md`](./atlan-skills-as-assets.md).

## The composition story

Three integration paths exist for an agent that needs Atlan context. MCP is one of them and is increasingly the default for runtimes that speak the protocol natively.

| Path | Use it for | Avoid when |
|---|---|---|
| **MCP server** | Runtime is MCP-native; cross-team/cross-runtime reuse; want Atlan RBAC to propagate; agent author shouldn't have to know pyatlan internals | Bulk reads (1000s+ assets); operations the MCP server doesn't expose; agent runtime has no MCP adapter |
| **pyatlan SDK** | Custom writes, batch mutations, anything the MCP tool surface doesn't cover; tight control over retries/backoff; non-MCP runtimes (older LangChain, custom Python loops) | You just want "give me an asset by name" from inside an MCP-native agent — that's overkill |
| **MDLH lakehouse** | Reporting, analytics, metadata completeness scans, anything that joins millions of assets; SQL-shaped questions over the catalog | Mutations (read-only); per-asset detail (MDLH is denormalized snapshots, may lag by minutes); workflows that need real-time freshness |

Composition is normal. The brand-analytics reference build calls Databricks for source-data SQL and could use pyatlan-direct or MCP for glossary/metric definitions. The DDLC app in this repo uses pyatlan directly because it's running in-process inside the Atlan app framework — MCP would be an unnecessary round-trip. A Claude Code session sitting on a developer's laptop wants MCP because it gives every other Claude session on that machine the same access without code changes.

The MCP server can also be the surface for content from a [context repo](./atlan-context-repos.md): a customer-specific repo with SKILLs, glossary YAML, and runbooks can be served through the MCP server's `resources/` endpoint (the MCP protocol's read-only resource concept, distinct from tools). This is currently more theoretical than productized — Atlan's MCP surface is heavily tool-centric — but it's the natural place this evolves.

## Authentication: the part most builders underestimate

Two modes, documented in the internal "Remote MCP — Dual Authorization Design" page.

**OAuth 2.1 (recommended)** uses Atlan's Keycloak IdP. Flow:

1. Client hits `/.well-known/oauth-protected-resource` on the MCP server.
2. Client registers with Keycloak (per-tenant client, mocked as pre-created in current implementation).
3. PKCE code flow → JWT access token.
4. Every `POST /mcp` request carries the Bearer token; MCP server validates signature against JWKS, checks issuer + expiry, reads `sub` to identify the user.
5. Downstream calls to Heracles / Atlas / Atlan APIs run under that user's identity.

Token TTL is roughly 4 hours. **This bites.** A canonical customer incident (May 2026) is the canonical failure: an MCP server credential rotation invalidated tokens across all client sessions simultaneously, producing `invalid_token` 401s from many IPs at once. Clients can re-auth, but interactive Claude Code sessions surface this as "MCP server disconnected" with no obvious user remediation path beyond `/mcp` → re-auth.

**API key (Bearer)** uses an Atlan API key associated with a persona. Endpoint is `/mcp/api-key` rather than `/mcp`. The API key's persona determines what the MCP server can see — *for every user calling through that key*. This is fine for service-to-service automation but wrong for multi-user Claude Connector / ChatGPT deployments, where you'd want each user's SSO to flow through. Recent addition (per a customer ticket, May 2026): OAuth client-credentials flow with ClientID + ClientSecret, for backend automation that needs OAuth identity without a browser.

For audit: every MCP tool call is logged with caller identity, tool name, MCP client name + version, model identifier (when supplied), tenant, request ID, duration, success/error, optional rationale string, and `user_query` argument when present. Atlan does not currently log full request/response bodies. The audit feed is internal at time of writing — surfacing this in-product is on the roadmap.

## Failure modes / gotchas

The receipts here are real Zendesk tickets and Linear issues from the last six months. Read them as the distribution of pain, not as showstoppers.

1. **OAuth token expiry mid-session.** ~4-hour TTL on Keycloak access tokens. Long-running agent sessions hit `invalid_token` and most clients don't auto-refresh gracefully. Mitigation in Claude Code: `claude mcp remove atlan-oauth && claude mcp add --transport http atlan-oauth https://mcp.atlan.com/mcp`. Mitigation as a builder: catch 401 on tool calls and retry-with-reauth.

2. **Rate limit at the Cloudflare edge.** 500 RPM per Atlas pod, scaled by tenant pod count (~4,000 RPM typical). Above that, HTTP 429. Retry strategy: 30–60s backoff. Bulk-fetch agents will hit this before you expect — this is one of the strongest arguments for [MDLH](./atlan-context-without-repo.md) on analytics-shaped workloads.

3. **Latency on semantic_search.** A customer (May 2026) reported `semantic_search_tool` latencies >25s. Confirmed during heavy vector-index load. Watch p95 if your agent is voice-app-adjacent or has a TTFT budget.

4. **Claude Chat (web) blocks write tools.** Same MCP server, but Claude Chat's client policy restricts tool calls it categorizes as write — `update_assets`, `add_atlan_tags`, etc. Documented in DOC-369. Claude Code and Claude Desktop allow them. Surface this to customers up front: "if you need to update metadata via chat, use Claude Connector or Claude Desktop, not claude.ai web."

5. **Microsoft Copilot Studio schema strictness.** An enterprise customer (Feb 2026): same MCP setup that works in Cursor and Claude failed in Copilot Studio because Copilot Studio enforces a stricter MCP tool-schema shape. Atlan's MCP definitions work fine against the spec; Copilot Studio's reading of it is more conservative. Status: optimization in flight on Atlan's side.

6. **Corporate TLS interception.** A European financial-services customer (May 2026): customer's corporate proxy was MITMing the TLS handshake, producing `UNABLE_TO_GET_ISSUER_CERT_LOCALLY`. Fix is client-side `NODE_EXTRA_CA_CERTS` (Node clients) or `SSL_CERT_FILE` + `REQUESTS_CA_BUNDLE` (Python clients). Not yet in public docs; flag for enterprise customers.

7. **Tool sequencing mistakes.** A customer incident (May 2026): Claude called `search_assets` for a view's columns, got back qualified name, didn't follow with `get_asset`. The agent's system prompt didn't enforce search→get for column-level data. This is the most-common "Atlan MCP doesn't work" complaint and almost always a prompt issue, not a server issue.

8. **Custom-metadata fields missing in returns.** A customer (Dec 2025): MCP not fetching specific CM fields. Almost always either (a) the CM attribute is gated by a persona the calling user doesn't have, (b) the field is on a structure the search didn't `include`, or (c) the asset has the CM set but no value for that attribute. Diagnose with pyatlan to compare. Don't assume server bug.

9. **Tool listing latency at client start.** Every MCP client lists tools on connect. With 28 tools and their schemas, this is a measurable startup cost (~300-800ms typical). Not a problem for long-running clients; can be noticeable for short-lived scripted agents.

10. **No public reference architecture yet.** A customer (May 2026): customer explicitly asked for orchestration best-practice docs (tool sequencing, token budgets, parallel-call safety, recursion termination, latency). The Linear issue (DOC-429) is the 17th ticket deflecting to the same gap. Internal Confluence has guidance; public docs do not. This is the single largest documentation hole as of May 2026.

11. **Tool restriction is opt-out, not opt-in.** `RESTRICTED_TOOLS` env var (Local MCP) and per-tenant LaunchDarkly flags (Remote MCP) let admins block specific tools. Default is all-tools-enabled. For customers with strict data-governance reviews, raise this early — a buyer's security team will often want write tools off by default.

12. **The local install is deprecated.** README has a warning banner: local Docker/uv path is maintenance-only. Customers running it should plan migration to Remote MCP. The deprecation doesn't mean "broken next month" but it does mean "no new tools, no bug-fix SLAs."

## When to choose MCP over SDK/MDLH

Choose **MCP** when:

- The agent runtime is MCP-native — Claude Code, Claude Desktop, Cursor, Claude Connector, ChatGPT developer mode, Gemini CLI, VS Code, Windsurf, n8n, Copilot Studio, Google ADK, Claude Agent SDK.
- You want one integration that serves multiple consumers (e.g., the same MCP setup used by analysts in Cursor and data engineers in Claude Code).
- You want Atlan RBAC to propagate per user via OAuth.
- The agent author shouldn't need to learn pyatlan or MDLH.
- Governance and audit at the MCP layer matters (centralized tool-call logging, future support for AI gateways like Salesforce's MCP Server Registry).

Choose **pyatlan SDK** when:

- You need an Atlan operation the MCP server doesn't expose (custom typedef ops, anything from the experimental SDK, complex search DSLs the tool surface flattens).
- The agent is server-side and tightly controls its own retries, backoff, and concurrency.
- The runtime doesn't speak MCP and there's no adapter (older LangChain code, bespoke async Python).
- You're inside the Atlan App Framework — pyatlan is in-process and free; MCP would be a network round-trip.

Choose **MDLH lakehouse** when:

- You're reading thousands of assets at a time (catalog scans, completeness reports, glossary exports).
- You can tolerate snapshot latency (minutes, not seconds).
- The workload is SQL-shaped (joins, aggregations, time-series).
- You're doing analytics on adoption / usage / governance health, not real-time metadata reads.

The decision tree most teams converge on: **MCP for interactive in-IDE flows, SDK for app-resident logic and mutations, MDLH for analytics.** Composing two of these in one agent is normal; composing all three is fine but a smell that you should sanity-check.

## Atlan Application SDK + MCP — the inversion

Worth flagging because it changes the picture. The Atlan Application SDK (`docs.atlan.com/.../integrate-mcp`) ships an `@mcp_tool` decorator. Any activity in a custom Atlan app marked with `@mcp_tool` is automatically discovered and exposed via a FastMCP 2.0 streamable-http endpoint mounted in the app. The same `@InvocableMethod` pattern from Agentforce, basically — write the activity once, it runs as a Temporal activity inside the app *and* as an MCP tool reachable from any MCP client. This is how custom Atlan apps (DDLC, RDM, DPS in the hackathon repo) could in principle expose their own MCP surface to external agents — not yet wired in the demos, but the mechanism is in the SDK.

## Maturity snapshot — May 2026

Remote MCP is **enabled for all Atlan tenants**. The "private preview" label that appeared in older docs is gone. Tool surface (~28 tools) is stable and versioned at the server. OAuth + API key auth modes are both GA; client-credentials OAuth is recent. Major MCP clients (Claude family, Cursor, Gemini CLI, VS Code, ChatGPT developer mode) all have documented setup paths. Copilot Studio support is documented but has known schema-compatibility gaps.

Local MCP (Docker / uv / pip) is **deprecated** but functional. Atlan engineering keeps the GitHub release pipeline running; no new features land there.

Roadmap signals from internal docs and Slack:

- Reporting/observability on MCP usage (per-tenant tool-call dashboards) — in progress
- More clients (richer Slack support, deeper Copilot integration)
- Free pricing tier continues; tool availability gated by tenant feature set (e.g., DQ tools require DQ entitlement)

## Anti-positioning

It is not the case that all Atlan-aware agents should integrate via MCP. Pyatlan-direct integration is faster, has no token-expiry surface, supports operations MCP doesn't, and is the right answer for app-resident logic. MDLH crushes MCP for bulk reads. MCP wins when the agent runtime speaks MCP natively and you want **one integration that serves many consumers** — that's the bet to make explicit when recommending it to a customer.

## Empirical anchor

Two receipts. **Positive**: a partner co-sell demo (May 2026) chained Cortex Code → Atlan MCP → Snowflake to ground a Cortex agent in Atlan metadata. Customer engineer's first build was working in one session. The "MCP server is already attached to your Atlan instance" framing landed because the integration was a config line, not a code change. **Negative**: the a customer orchestration-guidance ticket (May 2026), the 17th deflection to the same documentation gap, where the customer needed reference architecture for parallel-call safety and lineage-payload token budgets. The MCP server worked; the docs didn't carry the customer over the architecture bar. Both shapes — fast-onboarding for simple consumption, doc-gap pain on production-scale builds — are the wins-and-losses distribution to expect mid-2026.

Origin: synthesized from Atlan public docs (atlan-mcp-overview, remote-mcp-overview, claude-code-remote-mcp, integrate-mcp), the atlanhq/agent-toolkit README, internal Confluence ("What's New", "What Changed & Why", "Security & Authentication FAQ", "Remote MCP — Dual Authorization Design"), and customer support tickets across nine enterprise tenants.
