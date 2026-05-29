---
title: Databricks Genie (and Mosaic AI Agent Framework) — Builder's Deep Dive
category: harnesses
status: draft
last_updated: 2026-05-29
source_external:
  - https://docs.databricks.com/aws/en/genie/ (Databricks AI/BI Genie overview)
  - https://docs.databricks.com/aws/en/genie/conversation-api (Genie Conversation API)
  - https://docs.databricks.com/aws/en/generative-ai/agent-framework/author-agent (Mosaic AI Agent Framework — authoring)
  - https://docs.databricks.com/aws/en/generative-ai/agent-framework/multi-agent-genie (Multi-agent Genie pattern)
  - https://docs.databricks.com/aws/en/generative-ai/mcp/ (Databricks MCP support, updated 2026-05-07)
applies_when:
  workloads: [databricks-resident-bi-qa, unity-catalog-governed-text-to-sql, mosaic-ai-deployed-agents]
  constraints: [data-cannot-leave-databricks, unity-catalog-is-source-of-truth, narrow-bi-question-scope, team-on-databricks-platform]
contradicts: []
related: [harnesses/landscape-2026-may, harnesses/cortex-deep-dive, decision-guides/what-kind-of-agent-are-you-building]
snapshot_date: 2026-05-29
---

# Databricks Genie (and Mosaic AI Agent Framework) — Builder's Deep Dive

The Databricks entry in `patterns/harnesses/` covers two things that get conflated in customer conversations: **AI/BI Genie** (the conversational BI / text-to-SQL product that lives in a Genie Space) and **Mosaic AI Agent Framework** (the code-defined agent runtime that can call Genie as one tool among many). These are *not* the same product, and the most common Databricks agent-build mistake as of mid-2026 is treating Genie as a general-purpose agent harness when its surface area is "conversational BI over a curated Unity Catalog scope."

This deep-dive exists because the landscape survey doesn't carry enough detail to decide for or against Genie on a real use case. Genie's skill/tool support has been broadening — Databricks-managed MCP servers landed in spring 2026 — but as a general agent harness it remains **narrower than LangGraph, less mature than Mosaic AI Agent Framework, and brittle outside the verified-query / Unity-Catalog-grounded sweet spot.** Databricks-resident agents are, in most cases as of mid-2026, better served by **LangGraph + Databricks MCP servers** or by **Mosaic AI Agent Framework wrapping Genie as a sub-agent** than by Genie alone.

## The two layers (and why the conflation hurts)

| Layer | What it is | Authoring surface |
|---|---|---|
| **AI/BI Genie** | Per-Space conversational BI product. Natural language → SQL → table/chart, scoped to a curated set of Unity Catalog tables. | Genie Space UI (instructions, sample queries, trusted assets) + Conversation API |
| **Mosaic AI Agent Framework** | Code-defined agent runtime on Databricks. Wraps any framework (LangGraph, OpenAI Agents SDK, LangChain, plain PyFunc) behind MLflow's `ResponsesAgent` interface and deploys via Model Serving or Databricks Apps. | Python code in a Databricks notebook / project; MLflow for tracing/eval/registry |

The pattern Databricks recommends for anything beyond pure BI Q&A is: **author the agent in Mosaic AI Agent Framework, wrap Genie as a sub-agent via the `GenieAgent` helper, supervise with LangGraph or OpenAI Agents SDK.** Genie is a tool inside that agent, not the agent itself. Customers who skip the framework and try to make a Genie Space "into an agent" end up fighting the verified-query model.

The mental model that helps: **Genie Space ≈ "a saved BI conversation surface scoped to a curated Unity Catalog slice."** It is not a general agent runtime. The runtime, when you need one, is Mosaic AI Agent Framework, and the relationship between the two is "Genie is a tool you can call from an agent" not "Genie is the agent."

## Anatomy of a Genie Space

A Space is described as a **compound AI system**, not a single LLM call. The knowledge it draws from:

| Component | What it captures | What it can't |
|---|---|---|
| **Curated datasets** | A scoped set of Unity Catalog tables. Per-user row-level security and column masks enforced at query time. | Tables outside the curated scope; unstructured data. |
| **General instructions** | Natural-language guidance — terminology, what "active customer" means, table-selection hints. | Anything that can't be expressed as text the SQL-generator LLM will read. |
| **Sample SQL queries** | Example queries the model uses for pattern learning. Genie can auto-suggest popular workspace queries when assets are added. | Generalization beyond the patterns shown — out-of-distribution questions fall back to schema-only reasoning. |
| **SQL functions / parameterized queries** | Reusable SQL expressions encoding business semantics (e.g., `monthly_active_users(month)`). | Logic that can't be expressed in a single SQL function. |
| **Trusted assets** | When a parameterized example query or SQL function is used *exactly*, the response is marked "Trusted." | Anything where the LLM had to deviate from the verified pattern — those answers are explicitly *not* Trusted. |
| **Column metadata + synonyms** | Descriptions, PK/FK relationships, column-level synonym hints. | Schema gaps — bad table/column descriptions silently degrade accuracy. |

The **Inspect feature** (Public Preview as of the docs snapshot) layers a verification step over generated SQL. Useful, still preview.

**The verified-query model is the central design choice and the central limitation.** Genie is at its best when 80%+ of asked questions can be served by parameterized SQL functions the analyst already wrote and a "Trusted" badge appears. It degrades fast on novel analytical questions, questions that span multiple curated scopes, or questions whose answers require reasoning beyond SQL.

## What Genie cannot answer (state this explicitly)

Per the official docs: **"Genie cannot answer questions about unstructured data such as PDFs, Word documents, or other file-based content."** Structured-data only. No RAG over docs out of the box. If the use case mixes "what does the contract say" with "show me revenue by region," that's a Mosaic AI Agent Framework job, not a Genie job.

Other categories Genie is *not* the right tool for, regardless of how the question is phrased: tasks that require **write operations** (Genie generates SQL but the productized surface is read-oriented BI); tasks that require **multi-step computation outside SQL** (Pandas transformations, ML scoring, calling an external API mid-conversation); tasks that require **reasoning over multiple disconnected curated scopes** (Spaces are bounded; cross-Space orchestration is a supervisor job, not a Genie job).

## The Genie Conversation API (and its limits)

Spaces are callable programmatically:

```
POST /api/2.0/genie/spaces/{space_id}/start-conversation
GET  /api/2.0/genie/spaces/{space_id}/conversations/{id}/messages/{msg_id}
POST /api/2.0/genie/spaces/{space_id}/conversations/{id}/messages   # follow-up
```

Two operational ceilings to know about:

1. **Five questions per minute per workspace** (best-effort on the free tier). This is the rate limit you'll hit first when wrapping Genie in an agent loop that fans out queries.
2. **10,000 conversations per Space** maximum. Recommended polling timeout is 10 minutes per query.

The API returns **tabular data only** — charts are a client-side render concern. Anything that needs an image artifact in an agent transcript needs an explicit visualization step.

## Mosaic AI Agent Framework — the code-defined layer

When the build is "an agent that does more than BI Q&A on Databricks," this is the layer Databricks expects you to be at. Key shape:

- **`ResponsesAgent` interface** — MLflow wrapper. The framework is explicitly framework-agnostic: "you can author agents using any framework. The key is wrapping your agent with MLflow `ResponsesAgent` interface."
- **Supported authoring frameworks** — OpenAI Agents SDK (the primary template), LangChain / LangGraph (via `@tool` decorator), plain PyFunc, and others wrapped in `ResponsesAgent`.
- **Tools** — local Python functions, **Unity Catalog functions** (governed, reusable across agents), and **MCP servers** (Databricks-managed or external).
- **Deployment** — Databricks recommends **Databricks Apps** for new builds (full control over server + deployment workflow); Model Serving endpoints remain supported for simpler cases.
- **Tracing / eval / registry** — MLflow ResponsesAgent gives automatic tracing, multi-agent message history, streaming outputs, and tie-in to MLflow Evaluation.

This is closer to "LangGraph + AWS Bedrock" in shape than to "Agentforce." You write the loop. You pick the model. You define the tools. The platform provides governance, deploy, and observability.

### Unity Catalog functions as tools — the governed building block

Unity Catalog functions are first-class tool definitions: SQL or Python functions registered to UC, governed by the same permission model as tables. Two operational implications:

1. **Tool surface inherits UC governance.** A function the agent calls is subject to the same per-user grants as a table. On-behalf-of-user auth carries through. This is the strongest argument for the stack: the tool layer and the data layer share a single permission model.
2. **Tool authoring is SQL-DDL-flavored, not Pythonic.** Registering a UC function is a `CREATE FUNCTION` operation. Teams used to `@tool` decorators in LangGraph have to context-switch between Python tool definitions and UC-DDL function definitions when both layers are in play. Not a blocker; worth knowing before the architecture decision.

## MCP support — recent, and the key unlock

Per the official MCP docs page (last updated **May 7, 2026**), Databricks now offers four MCP server categories:

1. **Databricks-managed MCP servers** — pre-built endpoints for Vector Search, **Genie Spaces, Databricks SQL, and Unity Catalog functions**. No setup. This is what makes "agent calls Genie as one tool among many" actually clean.
2. **External MCP servers** — third-party servers accessed through Databricks-managed proxies, authenticated via Unity Catalog connections.
3. **Custom MCP servers** — user-hosted, deployed as Databricks Apps.
4. **Client connections** — Claude, Cursor, MCP Inspector connecting *into* Databricks MCPs.

Access flows through **Unity AI Gateway** (access controls, credential management, centralized visibility). This is the right governance shape, and it's also why **the "agent that mixes Databricks data with other tools" pattern works much better than it did in 2025** — you no longer have to glue Genie's REST API into a hand-rolled tool loop.

State the version posture explicitly: MCP server support on Databricks is **recent (publicly documented at May 2026 cadence)** and the broader skill/tool ecosystem around Genie itself is **nascent compared to LangGraph, the Claude Agent SDK, or even Agentforce's MCP gateway**. Build accordingly.

### A note on the OpenAI Agents SDK as the primary template

Databricks' primary Mosaic AI Agent Framework template (as of the docs snapshot) uses the **OpenAI Agents SDK** for conversation management and tool orchestration. This is worth noting because it's a non-obvious choice — most enterprise Databricks customers default to LangGraph or LangChain — but the template-of-record uses OpenAI Agents SDK wrapped in `ResponsesAgent`. The framework is genuinely agnostic; the *default examples* lean OpenAI-SDK-first. Match the framework choice to team familiarity, not to the template.

## Multi-agent Genie pattern (when it's the right shape)

The documented multi-agent pattern uses a **supervisor-worker topology**: a supervisor agent (authored in LangGraph or DSPy) routes between specialized workers; one of those workers is `GenieAgent` wrapping a Genie Space; another might be a RAG agent over unstructured docs; another might be a Python-tool agent for transformations.

```
[Supervisor (LangGraph)]
        |
   ┌────┼─────────────┐
   ▼    ▼             ▼
[GenieAgent]   [RAG agent]   [Python-tool agent]
  (Space A)    (vector idx)    (transformations)
```

On-behalf-of-user authorization carries the end user's Unity Catalog permissions through to the Genie call. This is the **right** pattern for "Databricks-resident agent that needs to talk to structured data sometimes" — much better than trying to make a Genie Space itself handle the orchestration.

Practical sequencing for a team going down this path: stand up the Genie Space first, prove out trusted-asset coverage on a benchmark set of expected questions, *then* wrap it as `GenieAgent` in a Mosaic AI supervisor that adds the other workers. Building the supervisor before the Space is mature is the common reverse-order mistake — the supervisor inherits the Space's accuracy problems and they're harder to debug through a layer of orchestration.

## Production patterns when Genie fits

- **Unity-Catalog-governed conversational BI.** Analyst-curated Space, verified queries cover 80%+ of expected questions, Trusted-asset badge is the user trust signal. Self-service BI for an exec/ops audience without giving them direct SQL access. The analyst-curated nature is the load-bearing assumption — *someone* has to keep the trusted-query coverage high enough for the badge to mean something.
- **MLflow-integrated agents.** Mosaic AI Agent Framework + LangGraph + Databricks-managed MCP servers, with Genie as one of several tools. MLflow gives tracing, eval, and registry for free; deployment to Databricks Apps or Model Serving stays inside the governance perimeter. The MLflow evaluation harness (LLM-judge + structured metrics) is genuinely good and is the strongest single reason to stay inside the Mosaic AI envelope once the agent is real.
- **On-behalf-of-user data agents.** Per-user RLS and column masks enforced through the Genie call. This is hard to replicate outside Databricks and is the strongest reason to prefer this stack when data residency + per-user authorization is non-negotiable. Common in regulated industries (financial services, healthcare) where the customer's compliance posture *requires* that the agent never see data the end user couldn't see directly.

## Failure modes (where this stack actually breaks)

1. **Genie-alone is BI Q&A, not an agent.** A Space cannot tool-call out, cannot loop, cannot do multi-step reasoning across non-SQL operations. Teams that try to "make the Genie Space into the agent" end up with a brittle text-to-SQL pipeline dressed as an agent. The agent loop, if you want one, lives in Mosaic AI Agent Framework — Genie is a tool.

2. **Verified-query coverage doesn't generalize.** Trusted-asset badges only fire when a parameterized query or SQL function is used *exactly*. Anything that requires the LLM to deviate gets a non-Trusted answer with no rich confidence signal. Operationally: Spaces need ongoing analyst investment to keep verified-query coverage above the threshold where users trust the answers. Without that, accuracy degrades and the "Trusted" badge becomes noise.

3. **Skill/tool surface is nascent vs. the broader ecosystem.** As of mid-2026, the catalog of mature, well-documented Databricks-managed tools available to a Genie-fronted or Mosaic-AI-fronted agent is much smaller than what LangGraph + Anthropic's tool-use ecosystem, or the Claude Agent SDK's `SKILL.md` model, can reach. The MCP-server unlock helps, but the *third-party MCP server* ecosystem inside Databricks is still small compared to standalone MCP usage from Claude, Cursor, or generic LangGraph builds.

4. **Databricks platform lock-in.** Unity Catalog as source of truth, MLflow as eval/registry, Databricks Apps or Model Serving as deploy target. This is fine when the rest of the platform is already Databricks; it's a cost when the agent needs to live partially outside (e.g., a customer-facing agent that needs CDN-fronted deploy, or an agent that has to integrate with non-Databricks data planes).

5. **Multi-agent orchestration depends on Mosaic AI, not Genie.** Genie itself does not orchestrate. The supervisor-worker pattern requires LangGraph or DSPy code in Mosaic AI Agent Framework. If you wanted "Genie does the orchestration," that's not the product — and pretending it is leads to building a fake orchestrator out of Space instructions, which doesn't compose.

6. **English-language prompt envelope.** Per the official docs: multi-language input is supported, but underlying prompts wrap in English, which can cause English-language responses even when the user wrote in another language. Real issue for non-English-first deployments.

7. **Unstructured data is out of scope for Genie.** If the use case mixes "what does the contract say" + "show me revenue," Genie is exactly half the system and needs a RAG worker beside it under a supervisor. Don't oversell Genie as a single answer here.

8. **Rate ceilings hit fast in agent loops.** Five questions per minute per workspace, 10k conversations per Space. An agent that fans out 4 Genie sub-queries per turn for a chat audience of 50 will saturate the workspace before lunch.

9. **The `ResponsesAgent` template churn.** As of mid-2026 the recommended deployment target shifted from Model Serving to Databricks Apps for new agent builds. Older tutorials still point at Model Serving; the templates are evolving. Anchor to the current docs, not stale blog posts.

10. **Genie Space is not source-controlled like code.** Spaces are edited in-product (instructions, sample queries, trusted assets). There's no clean Git story for the Space configuration itself the way there is for Mosaic AI agent code. Treat the Space as a stateful, in-product artifact and the agent code around it as the version-controlled piece. Management APIs allow programmatic Space creation/deployment across workspaces, which closes part of the gap, but the per-Space content authoring still lives in the UI.

11. **Schema-quality dependency is silent.** Genie pulls heavily on column descriptions, PK/FK metadata, and synonyms. Bad or missing schema metadata degrades accuracy without an obvious failure signal — the model just generates worse SQL. There's no equivalent of a compile error here; only end-to-end accuracy regression on the benchmark set will catch it. Spaces over poorly-described Unity Catalog scopes underperform Spaces over well-described scopes by a wide margin.

12. **No turn-key prompt-injection defense at the Space layer.** Unlike Agentforce's Einstein Trust Layer, Genie does not advertise a built-in policy/safety envelope between the user input and the SQL-generator LLM. Per-user grants and RLS bound *what data* the generated SQL can touch, but mis-targeted SQL (wrong join, wrong filter) is on the agent designer to detect. Production deployments handling sensitive data need explicit verification (Inspect, benchmark suites, supervisor-side checks) — don't assume the platform layer catches it.

## When to choose Genie / Mosaic AI Agent Framework

- **"Data cannot leave Databricks"** is a hard mandate.
- **Unity Catalog is the source of truth** for the assets the agent reasons over (governance, RLS, column masks, lineage).
- **Narrow, well-scoped BI Q&A** is the dominant workload — and an analyst is willing to invest in verified queries / SQL functions to drive Trusted-asset coverage above the trust threshold.
- The team is **already LangChain/LangGraph or OpenAI-Agents-SDK-flavored** in their agent code, *and* wants Databricks-native deploy / governance / MLflow tracing.
- **Per-user authorization** (on-behalf-of-user, RLS/column masks at query time) is a non-negotiable part of the agent's value.

## When LangGraph + Databricks MCP beats it

- **Complex multi-step orchestration** with significant non-Databricks tool surface (third-party APIs, SaaS systems, vector DBs outside Databricks).
- **Multi-source agents** where structured data is a minority of the work — most calls are RAG over docs, web fetch, computation, or external API.
- **Evolving / open-ended Q&A** where the verified-query model breaks down — the user population doesn't ask predictable questions, so trusted-asset coverage never gets above the threshold.
- **Portable / `SKILL.md`-style work** the team wants to keep portable across runtimes (Claude Agent SDK, generic LangGraph deploy, etc.). Databricks-native deploy adds friction that may not be worth it.
- **Prototype on a tight timeline** without Databricks platform experience on the team.

In these cases, the right shape is usually: **LangGraph agent → Databricks-managed MCP servers as the data-side tools (Genie Space, UC functions, SQL, Vector Search) → deploy wherever the rest of the org's services live.** You still get Databricks governance for the data tools; you don't pay the Databricks-native-deploy tax for the orchestration layer.

## A decision flow for "we're a Databricks shop, what do we build on?"

The decision tree that holds in mid-2026, roughly:

1. **Is the workload narrow BI Q&A over a curated, well-described Unity Catalog scope, with an analyst able to invest in verified queries?** → **Genie Space** (no agent layer needed unless you want one).
2. **Is the workload "BI Q&A + a few other things" (RAG over docs, external API calls, multi-step reasoning)?** → **Mosaic AI Agent Framework with `GenieAgent` as one worker under a supervisor.** Author the supervisor in LangGraph (most teams) or OpenAI Agents SDK (Databricks template default).
3. **Is the workload "agent that mostly does non-Databricks things and occasionally touches Databricks data"?** → **LangGraph (or your existing agent framework) + Databricks-managed MCP servers as the data-side tools.** Deploy outside Databricks if it makes sense; the data governance still flows through Unity AI Gateway.
4. **Is the workload one where the data residency / per-user-auth posture is the primary reason you're picking the platform?** → **Mosaic AI Agent Framework + Databricks Apps deploy**, regardless of where the orchestration complexity lives. The governance perimeter is the point.

If none of these match — for instance, the customer mostly needs a chat agent over docs with no structured-data dimension — Genie / Mosaic AI Agent Framework isn't necessarily wrong, but the platform isn't doing meaningful work for the use case. Reach for the harness that fits the workload, not the harness that matches the data warehouse.

## Integration shape with an external context layer (e.g., Atlan)

A common pattern when a metadata platform sits alongside Databricks: the platform reads Unity Catalog metadata for cataloging / lineage / governance UX, and surfaces deep-links back into the relevant Databricks Genie Space or Mosaic AI agent.

Practical points:

- **Unity Catalog → external metadata sync** is well-documented; lineage exposure via the Databricks REST/SDK API is feasible.
- **Genie Space configuration** (instructions, sample queries, trusted assets) is *not* exposed as a clean external API as of mid-2026. Treat it as in-product configuration; the external layer can reference the Space by ID, not author it.
- **MCP is the cleanest seam** in the other direction: an external agent (Claude, an agent in a third-party platform) can call Databricks-managed MCP servers — including the Genie Spaces MCP server — through the Unity AI Gateway with proper authentication.
- **Friction to acknowledge**: customer-side commitment to Unity Catalog as the authoritative catalog is a precondition. If the external platform is the authoritative catalog and Unity Catalog is downstream, the integration is harder and the value proposition needs more care.

## Ecosystem maturity (mid-2026)

- **Genie Space** itself is mature *as a BI product*. Verified queries, instructions, trusted assets, Inspect (Public Preview) — all production-usable for analyst-curated BI Q&A.
- **Genie as an agent tool** is **recently mature** — the Databricks-managed Genie Spaces MCP server and the `GenieAgent` helper for Mosaic AI Agent Framework are the right building blocks, and both are recent additions on the May 2026 doc cadence.
- **Mosaic AI Agent Framework** is **rapidly evolving** — templates, deployment recommendations (shift toward Databricks Apps), and MCP integrations have all moved in the last few releases. Anchor builds to current docs, not 2025-era blog posts.
- **Third-party MCP ecosystem inside Databricks** is **small but growing**; the broader MCP-server catalog (Anthropic, Cursor, community) is reachable through Databricks-managed proxies but adds an auth and governance step at the boundary.

## The fair "is Genie really an agent framework" question

It's a fair question, and the answer is: **AI/BI Genie is not. Mosaic AI Agent Framework is.** Genie is a vertically-integrated conversational BI product that can be exposed as a tool to an agent — and a very good tool, when the BI scope is well-defined. Mosaic AI Agent Framework is the actual code-defined agent runtime, and the right comparison to LangGraph + Bedrock or Claude Agent SDK + your-own-deploy is *Mosaic AI Agent Framework wrapping LangGraph* — not Genie alone.

The most common Databricks agent-build mistake we see is teams picking "Genie" as the answer because Databricks customers should "obviously" use the Databricks-native option, then trying to do orchestration, multi-step reasoning, or non-BI work inside a Space. That's the wrong layer. The right answer is almost always: **Genie as a tool inside Mosaic AI Agent Framework**, or for genuinely complex / non-Databricks-heavy orchestration, **LangGraph + Databricks MCP servers** with the Databricks-native deploy reserved for when its governance is the actual reason you picked the platform.

## Empirical anchor

Databricks-published reference architectures emphasize the supervisor + GenieAgent pattern and Databricks Apps deployment for new agent builds. The negative receipts in the failure-modes section above — verified-query coverage drift, nascent third-party MCP ecosystem inside Databricks, multi-language English-envelope behavior, rate ceilings at 5 q/min/workspace, agent template churn — are the operational counterpart. As with any vendor-published numbers, the wins are real for the workloads they target; the gotchas are the shape of the misses to plan around.

Origin: Databricks official docs (genie/, generative-ai/agent-framework/, generative-ai/mcp/), snapshot 2026-05-29. Verify version-specific claims (MCP server categories, deployment-target recommendations, Inspect availability) against current docs before committing to architecture.
