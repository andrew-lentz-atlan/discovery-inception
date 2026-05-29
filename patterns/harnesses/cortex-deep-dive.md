---
title: Snowflake Cortex Agents / Cortex Analyst — Builder's Deep Dive
category: harnesses
status: draft
last_updated: 2026-05-29
source_external:
  - Snowflake Cortex Agents docs (https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents)
  - Snowflake Cortex Analyst docs (https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst)
  - Snowflake AI features overview (https://docs.snowflake.com/en/guides-overview-ai-features)
applies_when:
  workloads: [snowflake-resident-bi-qa, semantic-layer-text-to-sql, governed-analyst-workflows]
  constraints: [data-must-stay-in-snowflake, team-is-snowflake-native, narrow-analyst-scope, willing-to-author-and-maintain-yaml]
contradicts: []
related: [harnesses/landscape-2026-may, harnesses/genie-deep-dive, decision-guides/what-kind-of-agent-are-you-building]
snapshot_date: 2026-05-29
---

# Snowflake Cortex Agents / Cortex Analyst — Builder's Deep Dive

The second per-warehouse deep-dive in `patterns/harnesses/` (paired with `genie-deep-dive.md` on the Databricks side). Snowflake Cortex is the vertically-integrated, Snowflake-native agent layer that runs alongside the warehouse: **Cortex Analyst** for natural-language-to-SQL over a semantic model, and **Cortex Agents** for broader orchestration across Analyst, Cortex Search, web search, and custom stored-procedure tools. For a narrow band of workloads — governed analyst Q&A where the data must never leave Snowflake — it is compelling. Outside that band, the **YAML-first semantic model** and the **constrained tool/skill surface** are real architectural limitations a downstream agent builder needs to see clearly before choosing it.

This entry exists so the inception pipeline's `runtime_proposer` has concrete reasons to recommend *against* Cortex when LangGraph, Claude Agent SDK, or even a Snowflake-MCP-fronted external orchestrator would fit the use case better. The framing here is deliberately not Snowflake's marketing framing. The audience is a builder deciding harness, not an evaluator deciding warehouse.

## The two surfaces

Snowflake ships Cortex as a family. Two of those components are the agent surface; the rest are infrastructure or building blocks the agent surface composes.

| Surface | What it is | Status (mid-2026) |
|---|---|---|
| **Cortex Analyst** | Natural-language → SQL over a YAML/Semantic-View-defined semantic model. The text-to-SQL engine. | GA across AWS/Azure in US, EU, APAC. Per-token pricing. |
| **Cortex Agents** | Multi-tool orchestrator: Analyst + Cortex Search + Web Search + custom tools (stored procs / UDFs). Has a planning/reflection loop and a REST API. | GA for core orchestration; specific tool types and the agent-as-Snowflake-object DDL surface mix GA and preview. |
| **Cortex Search** | Hybrid (vector + keyword) retrieval service over unstructured data in Snowflake. Used as a tool by Cortex Agents. | GA. |
| **Cortex AISQL / AI Functions** | LLM functions callable from SQL (`COMPLETE`, `EXTRACT_ANSWER`, `SUMMARIZE`, `CLASSIFY`, etc.). Not itself an agent — building block. | GA. |
| **Snowflake-managed MCP server** | Exposes Cortex Analyst and Cortex Search as MCP tools to *external* MCP clients (Claude, Cursor, LangGraph, OpenAI Agents SDK). | Listed in the AI features index; maturity is uneven across regions and capabilities as of mid-2026 — verify per-region before building on it. |
| **Cortex Code / CLI** | Snowflake's developer-side coding assistant; includes its own MCP client. Not the agent surface for end-user agents. | Preview / evolving. |

If your mental model is "Cortex = LangGraph for Snowflake," reset it. Cortex Analyst is the engine. Cortex Agents is the orchestrator. Everything else is either a tool the orchestrator calls or a different product entirely.

## The Cortex Agent loop

Cortex Agents follow the standard agentic four-phase loop, with the loop **hosted by Snowflake**, not by your code:

1. **Plan** — parse the request, split into subtasks, route to tools.
2. **Tool use** — call Analyst (for SQL), Search (for unstructured retrieval), Web Search (Brave-backed), or your custom stored-proc tools.
3. **Reflect** — evaluate intermediate results, decide on next steps.
4. **Iterate** — repeat until the orchestrator considers the response complete or a budget is hit.

The orchestration model is configurable — **Claude Sonnet 4.5/4.6, Claude Haiku 4.5, OpenAI GPT-4.1**, and an `auto` mode that picks the best-available are the supported choices as of mid-2026, with regional availability and cross-region inference for unavailable models. You do **not** write the loop. You configure a static spec that Snowflake's runtime executes.

## The agent spec (REST surface)

A Cortex Agent is described by a JSON spec submitted to the REST API (or persisted as a Snowflake object via DDL). The shape:

```json
{
  "models": { "orchestration": "claude-sonnet-4-5" },
  "instructions": {
    "response": "Be concise. Always cite tables.",
    "orchestration": "Prefer Analyst for numeric questions; Search for policy lookups."
  },
  "orchestration": { "budget": { "seconds": 60, "tokens": 8000 } },
  "tools": [
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "sales_analyst",
        "description": "Question-answering over the curated sales semantic model."
      }
    },
    {
      "tool_spec": {
        "type": "cortex_search",
        "name": "policy_search",
        "description": "Retrieval over the corporate policy library."
      }
    },
    {
      "tool_spec": {
        "type": "generic",
        "name": "create_followup_ticket",
        "description": "Files a Jira ticket from an analyst conversation.",
        "input_schema": { /* JSON Schema for the stored proc inputs */ }
      }
    }
  ],
  "tool_resources": {
    "sales_analyst": { "semantic_model_file": "@my_db.public.semantic_stage/sales.yaml" },
    "policy_search":  { "name": "MY_DB.PUBLIC.POLICY_SEARCH_SERVICE", "max_results": 5 },
    "create_followup_ticket": { "execute_as": "MY_DB.PUBLIC.CREATE_TICKET_PROC" }
  }
}
```

Two structural things to internalize:

1. **`tools[]` is the declaration; `tool_resources{}` is the binding.** Names must match. This is the entire "how do I add a capability" surface — there is no skill loader, no MCP discovery, no dynamic tool registration. The set is closed at spec time.
2. **`type` is enumerated.** `cortex_analyst_text_to_sql`, `cortex_search`, `web_search`, `generic`. The agent's world is the union of those four types plus whatever stored procs you wire under `generic`. No "Claude tool", no "skill", no portable artifact.

## The YAML semantic model — what Cortex Analyst actually reads

Cortex Analyst's entire understanding of your business comes from a **YAML semantic model file** (legacy form, still supported) or a **Snowflake Semantic View** (the newer first-class object, also defined via YAML uploaded through Snowsight or DDL). The YAML captures:

- **Logical tables** — business entities (e.g., `orders`, `customers`) mapped to physical Snowflake tables/views.
- **Dimensions** — categorical columns with descriptions and synonyms (e.g., `region` aka `geo`, `territory`).
- **Facts** — row-level numeric columns used to construct measures/metrics.
- **Measures / Metrics** — named aggregations (`SUM(amount) AS revenue`) with descriptions.
- **Time dimensions** — date/timestamp columns with granularity hints.
- **Filters** — named, reusable WHERE-clause fragments.
- **Joins / Relationships** — predefined join paths between logical tables.
- **Verified queries** — curated NL → SQL examples used as in-context exemplars at generation time.
- **Synonyms** — alternate phrasings users will ask in.

What the YAML **cannot** express well, in practice:

- **Recursive or graph-shaped relationships** — hierarchies (org charts, BOMs) need either a flattened view or pre-materialized closure tables.
- **Conditional logic across measures** — "revenue but only if region != 'INTL'" tends to require either a separate logical measure or a verified query for every variant.
- **Runtime-parameterized SQL** — the model is static; dynamic shape (e.g., pivoting by a user-chosen dimension) doesn't have a first-class slot.
- **Multi-step analyst reasoning across SQL turns** — Cortex Analyst cannot reference results from a previous query in the same conversation. Each turn re-generates SQL from scratch against the semantic model.
- **Broader business reasoning** — the docs are explicit: questions like "what trends do you observe" struggle because they're not resolvable as a single SQL query.

The YAML is the schema, the prompt, *and* the contract. Evolving it is a maintenance burden a downstream agent builder should plan for from day one.

## Tools and the MCP gap

This is the section where the runtime_proposer should bookmark specifics.

### What's there

- **Cortex Analyst as a tool** — first-class, well-instrumented, governed.
- **Cortex Search as a tool** — first-class. Hybrid retrieval, time-decay, filters.
- **Web Search as a tool** — Brave-backed, zero-data-retention, requires ACCOUNTADMIN enablement. Not always desirable in a governed account.
- **Custom tools via `generic` type** — backed by stored procedures or UDFs. JSON Schema for inputs. Execution incurs warehouse compute.
- **Snowflake-managed MCP server** — exposes Cortex Analyst and Cortex Search *outbound* so external MCP clients (Claude Desktop, Cursor, LangGraph via an MCP adapter, OpenAI Agents SDK) can call Snowflake capabilities as tools.

### What's not there (or thin) as of mid-2026

- **Inbound MCP for Cortex Agents** — Cortex Agents themselves do **not** consume arbitrary external MCP servers as tools the way Agentforce 360 or Claude Agent SDK do. The agent's tool world is the four enumerated types. If your design needs the agent to call out to a Notion MCP server, a Slack MCP server, a GitHub MCP server — that orchestration has to happen *outside* Cortex Agents, with Cortex Analyst/Search invoked from outside as MCP tools.
- **Portable skill artifacts** — there is no `SKILL.md`-equivalent. A capability is a stored proc tied to a Snowflake account, named in a JSON spec.
- **Multi-agent orchestration** — there is no first-class subagent / multi-agent topology. An agent can call tools; an agent cannot natively delegate to another Cortex Agent as a tool. You can simulate this with a stored proc that calls the Agents REST API, but that's not the same as a framework-supported pattern.
- **Maturity uniformity** — the MCP server, the agent-as-DDL-object, and several tool types are at different maturity levels across regions. Building on the bleeding edge here means accepting that capabilities may shift between minor releases.

This is the architectural truth the rest of this doc supports: **Cortex Agents is a static-spec, closed-world orchestrator with a strong Analyst tool and a thin everything-else.**

## Production patterns where Cortex fits

When the workload sits inside Cortex's actual sweet spot, it's a genuinely good answer:

1. **Governed BI Q&A over a curated semantic layer.** Sales asks "what was Q1 revenue by region in EMEA"; Cortex Analyst generates correct SQL against a maintained semantic model; the answer never leaves Snowflake's governance boundary. Role-based access is enforced because the generated SQL inherits the calling user's RBAC.
2. **Analyst-style workflows with Search + Analyst together.** "What did the policy say about returns, and how many returns did we process in March?" — Search retrieves the policy text, Analyst generates the SQL. The Cortex Agents orchestrator decides which tool to use per sub-question.
3. **Snowflake-resident PII and governance.** Masking policies, row access policies, object tagging, and audit logging apply to everything the agent does because the agent runs *inside* the data plane. For regulated workloads where "data must not leave the warehouse" is the requirement, this is the simplest way to honor it.
4. **Embedding Cortex Analyst as one tool inside a Streamlit or external app.** Used surgically, Analyst is a strong NL→SQL component even when the larger orchestrator lives elsewhere.

## Failure modes / limitations to be honest about

The cases where Cortex is the wrong harness aren't edge cases — they're common shapes.

1. **YAML-first semantic models are rigid.** Every measure, every dimension, every synonym, every join path is hand-authored in YAML and lives on a stage (or as a Semantic View). For evolving schemas — Atlan-style metadata that grows with the org — this is a real maintenance tax. There is no code-defined schema, no decorator-driven model registration, no migration system. Two teams trying to share a semantic model often end up forking the YAML.

2. **The skill/tool model is less expressive than LangGraph or Claude Agent SDK.** Tools are typed (`cortex_analyst_text_to_sql`, `cortex_search`, `web_search`, `generic`) and the set is closed at agent-spec time. No dynamic skill discovery, no MCP-discovered tool list, no nested subagents-as-tools, no programmatic orchestration of the loop. If you need conditional routing logic richer than what an LLM-planner inside an enumerated tool set can express, you'll hit a ceiling.

3. **Lock-in to the Snowflake data plane.** The agent runs in Snowflake. Tools are Snowflake objects. Identity is Snowflake identity. Exposing the agent to an external channel (web app, mobile, Slack, voice) means calling the REST API from outside, which works — but you've now split your stack and given up the "everything in one place" pitch that was Cortex's value prop. The outbound Snowflake MCP server helps for the inverse case (external agent calling Snowflake), not for this one.

4. **Multi-agent orchestration is weaker than dedicated frameworks.** No first-class subagent topology, no A2A protocol, no native delegate-to-specialist pattern. For workflows that need an orchestrator + several specialist agents — exactly the shape most non-trivial agent builds end up in by month two — Cortex Agents needs to be embedded *as a tool* inside a real framework (LangGraph, Claude Agent SDK), not the other way around.

5. **Cost model is opaque relative to token-priced frameworks.** Cortex Agents charges for orchestration tokens *and* per-tool execution (Analyst tokens, Search index size & persistence, custom-tool warehouse compute). The cost per conversation is the sum of several meters with different units. Compare to a LangGraph + direct-Claude-API setup where token cost is one explicit number; Cortex's bill is harder to forecast and harder to attribute when something blows up.

6. **Cortex Analyst can't carry state across SQL turns.** Each turn regenerates SQL from the semantic model in isolation. Iterative analysis ("now filter that to last quarter and break out by territory") works only as far as the LLM can re-derive the full intent from conversation context — there's no SQL chaining or intermediate-result memory.

7. **Verified queries are a maintenance surface, not a free lunch.** They materially improve accuracy but they're hand-curated, drift as the schema evolves, and have to be re-validated on every Snowflake/model update.

## When to choose Cortex anyway

The decision is honest if all of these are true:

- "Data does not leave Snowflake" is a non-negotiable requirement (regulated industries, contract terms, sovereignty).
- The team is **Snowflake-native** — SQL and YAML are first languages, Python is a second, building Python agent orchestrators from scratch is not on the table.
- The agent's scope is **narrow analyst-style Q&A** over a known semantic layer plus retrieval over Snowflake-resident unstructured data. Not a workflow agent. Not a multi-system agent. Not an action-taking agent.
- The team is **willing to author and maintain the YAML** as a living artifact — treating verified queries, synonyms, and join paths as first-class engineering work, not a one-time setup.

In that footprint Cortex earns its keep. The governance story is real, the Analyst engine is genuinely good when the semantic model is well-maintained, and there is no orchestration code for the team to own.

## When LangGraph + Snowflake-native MCP beats Cortex

The inverse case — and as of mid-2026 this is the majority case for non-trivial agent builds:

- **Complex orchestration** — branching workflows, retries with backoff, parallel fan-out, conditional gating. LangGraph's graph model fits this; Cortex's enumerated-tool, hosted-loop model fights it.
- **Multi-source agents** — the agent reads from Snowflake *and* Salesforce *and* a Jira MCP server *and* an internal HTTP API. LangGraph composes those; Cortex doesn't reach outside its closed tool world.
- **Agents that act on outputs, not just analyze** — write to Snowflake (or elsewhere), open tickets, send messages, trigger workflows. Cortex's `generic` tool type can technically call stored procs that do these things, but you lose the orchestration affordances (retries, branching, observability) that a real framework gives you.
- **Evolving schema** — code-defined models, lineage-aware tooling, automated regeneration of the semantic layer from upstream metadata. The YAML-first approach doesn't compose with this kind of pipeline.
- **The agent surface needs to live outside Snowflake** — embedded in a product UI, in Slack, in a CRM. Calling Cortex Analyst as an MCP tool from a LangGraph agent is a better factoring than running the orchestrator inside Snowflake and reaching out.

The decision rule: **if the agent's job is "answer questions about Snowflake data," Cortex is plausible. If the agent's job is "do things across systems, one of which happens to be Snowflake," put Snowflake-native MCP behind a real framework.**

## Atlan integration shape (neutral)

What's *possible* if a Cortex-hosted agent needs to interact with Atlan metadata:

- **Cortex Agents calls Atlan via a custom `generic` tool** backed by a Snowflake stored procedure. The stored proc uses external network access to call Atlan's REST API or pyatlan, returning JSON the agent consumes. Auth is managed in Snowflake; egress is allowlisted via Snowflake's network rules.
- **Cortex Search over an Atlan metadata snapshot** materialized in Snowflake. Lineage, glossary, and tag metadata exported to Snowflake tables, indexed by Cortex Search, queryable inside the agent as a retrieval tool.
- **MDLH-style queries from Cortex Analyst** — if Atlan's metadata is replicated into the customer's Snowflake account (the Metadata Lakehouse pattern), Analyst can answer NL questions over it via a semantic model defined on the metadata schema.
- **Outbound from Snowflake MCP server** — an *external* agent (Claude Agent SDK, LangGraph) calls Snowflake's Cortex tools via MCP and also calls Atlan via a separate Atlan MCP server or pyatlan. This is the pattern where Atlan and Snowflake compose well without binding either to the other's runtime.

Friction to flag honestly: stored-proc-based custom tools mean Atlan SDK calls run inside Snowflake's compute environment with Snowflake's egress rules and Snowflake's secret-management story. That's solvable but not free. The cleanest factoring is "Atlan and Snowflake-Cortex both expose MCP, a real agent framework composes them" — which is also the factoring that means you didn't pick Cortex Agents as your primary harness.

## Maturity / ecosystem mid-2026

- **Cortex Analyst** — production-grade for in-scope use cases. Teams have shipped it. The honest read is "great engine, the burden is the semantic model maintenance."
- **Cortex Agents** — GA orchestration with a still-evolving surface for custom tools, agent-as-Snowflake-object DDL, and MCP integration. Building on it today means accepting some moving parts.
- **Snowflake-managed MCP server** — listed in the AI features overview; tool coverage and regional availability are uneven. Better used as one direction (expose Cortex outbound) than as a bidirectional integration story.
- **Community / examples** — heavily skewed toward Snowflake's own blog and partner ecosystem. Independent recipes and battle-tested open-source patterns lag what's available for LangGraph, Claude Agent SDK, and OpenAI Agents SDK.
- **Model choice** — improving (Claude Sonnet 4.5/4.6, Claude Haiku 4.5, GPT-4.1, `auto`). Still narrower than what a direct API gives you.

## The fair "is Cortex an agent framework" question

Like Agentforce, the honest answer is no — not in the LangGraph / Claude Agent SDK sense. Cortex Agents is a **vertically-integrated agent product** that wraps Snowflake's strong NL→SQL engine and its hybrid retrieval engine in a hosted orchestration loop. You don't write the loop, you don't pick the agent topology, and the tool surface is closed at spec time.

The right way to compare Cortex to the other harnesses: **Cortex is to agents what the Snowflake warehouse is to databases.** A great answer for the workloads that live entirely inside its data plane. A wrong answer when the agent's job spans systems, when the orchestration needs to be programmable, or when the semantic-model-as-YAML maintenance cost exceeds the team's appetite.

The downstream runtime_proposer should default to **LangGraph (or Claude Agent SDK) fronting a Snowflake-native MCP integration** for all but the narrowest Snowflake-resident analyst-Q&A use cases. Cortex is the right call when the use case fits cleanly inside Cortex Analyst's footprint *and* the governance constraint forces hosting inside Snowflake. Outside that intersection, the limitations enumerated above are not abstract — they will be felt by month three.

## Empirical anchor

Snowflake's own published wins concentrate on the narrow workload Cortex is best at: NL→SQL over curated semantic models for internal BI consumers. The honest counter-data — semantic-model maintenance overhead, closed tool world, weak multi-agent story, opaque cost model — is qualitative and visible in how teams *factor* their builds in practice: Cortex Analyst tends to survive as a tool inside larger architectures; Cortex Agents as the top-level orchestrator tends to get replaced when the use case grows. Neither set of signals is independently auditable; both are useful as the shape of the wins-and-losses distribution.

Origin: Snowflake's public Cortex documentation as of 2026-05-29, plus the framing decision that this entry should give the inception pipeline concrete reasons to recommend *against* Cortex when a more general framework fits. Not a Snowflake marketing surface.
