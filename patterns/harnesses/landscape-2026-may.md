---
title: Agent Harness Landscape — May 2026
category: harnesses
status: validated
last_updated: 2026-05-22
source_findings: []
source_external:
  - Internal Atlan research doc — "Agent Harnesses: A Builder's Deep Dive" (2026-05)
  - Internal Atlan research doc — "Agentforce — Builder's Deep Dive" (2026-05-21, owner Himanshu Sikaria)
applies_when:
  workloads: [picking-a-harness, surveying-the-field, comparing-frameworks]
  constraints: []
contradicts: []
related: [architectures/single-agent-react, architectures/adversarial-decomposition, harnesses/agentforce-deep-dive]
snapshot_date: 2026-05-22
---

# Agent Harness Landscape — May 2026

Survey of 16 production-grade agent harnesses as of May 2026. Snapshot of the field at a point in time — the field moves fast, so revisit when authoring agents 3+ months after the snapshot date. Sourced from internal Atlan research docs reviewing each framework's architecture, code patterns, gotchas, and applicability.

The single most useful observation from the source review (validated independently by our own work): **runtime choice matters less than it did a year ago. The portable artifacts you author — skills, MCP servers, prompts — matter more than ever.** Six of the fifteen harnesses below already consume the Anthropic `SKILL.md` format; MCP works in all fifteen. If you encode the work in skills + MCP, the runtime is substitutable.

## The 15, summarized

| # | Harness | What it is | The one gotcha that bites |
|---|---|---|---|
| 1 | Claude Agent SDK | Python/TS wrapper around Claude Code CLI subprocess | `setting_sources` defaults to none — skills silently don't load on migration |
| 2 | Claude Managed Agents | Anthropic-hosted version of #1 | $0.08/session-hour while idle but "running"; budget alerts mandatory |
| 3 | Deep Agents (LangChain) | Opinionated "be Claude Code" harness on LangGraph | `execute` shell tool is unrestricted by default; sandbox not optional in prod |
| 4 | LangGraph | Graph runtime — assembly language for an agent | `langgraph dev` uses in-memory storage; state vanishes on restart |
| 5 | OpenAI Agents SDK | OpenAI's CC-equivalent (huge Apr 2026 release) | Guardrails only run on first/last agent in chain; handoffs unguarded mid-chain |
| 6 | Pydantic AI | Type-safe production-Python agent framework | Sync deps with `await` inside silently blocks event loop |
| 7 | MS Agent Framework | AutoGen + Semantic Kernel merged (GA Apr 3, 2026) | Group chat has no default termination; infinite loops trivially easy |
| 8 | Google ADK | Code-first agent framework for Gemini/GCP | `ParallelAgent` shares state across all children silently |
| 9 | AWS Bedrock AgentCore | Hosting layer, not a framework — wraps Strands/LangGraph/etc. | Deeply AWS-coupled; lock-in is the feature |
| 10 | CrewAI | Role-based multi-agent ("hire characters") | Hierarchical mode misassigns ~30% of tasks; memory grows linearly |
| 11 | LlamaIndex AgentWorkflow | RAG-first framework that pivoted to agents | Niche outside doc-heavy use cases |
| 12 | Mastra | TypeScript-native, "Next.js for agents" | TS-only; Python users skip |
| 13 | Smolagents (HF) | ~1K-line minimalist; "code-as-actions" | Local exec is sandboxed but not invincible; weak models loop forever |
| 14 | Strands (AWS) | Lightweight SDK that pairs with AgentCore | Skills not native; bidi streaming experimental |
| 15 | OpenHarness / ohmo | Open-source CC-clone, multi-provider | DIY teams only; not battle-tested |
| 16 | Agentforce (Salesforce) | Vertically-integrated agent platform on Atlas Reasoning Engine + Data Cloud + Trust Layer | The 15/15/20 wall (15 topics per agent × 15 actions per topic × 20 active agents per org); hit fast on enterprise workloads — multi-agent A2A orchestration is the official workaround |

Plus **Pi (pi.dev)** — same category as OpenHarness; missing from the source doc but should be included in future revisions.

## The five (now six) that actually matter for most decisions

For the majority of agent-building decisions, the live shortlist collapses to:

- **Claude Agent SDK** — if you're on Claude
- **OpenAI Agents SDK** — if you're on OpenAI (post the Apr 2026 release)
- **LangGraph** — if you need durable graph workflows with checkpointing and HITL (often with Deep Agents on top)
- **Pydantic AI** — if you care about type safety in Python
- **MS Agent Framework** — if you're enterprise .NET / Azure-native
- **Agentforce** — if you're on Salesforce and the agent acts on Salesforce data + processes (see `harnesses/agentforce-deep-dive.md` for depth)

Note: Agentforce isn't a framework in the same sense as the others — it's a vertically-integrated agent product. You don't write the loop, you configure topics and write actions. For a huge class of Salesforce-resident problems that opinion is exactly right; outside that footprint, one of the other five fits better.

The conditionally useful set is constraint-driven (CrewAI for 2-hour demos throwaway, Mastra for TS-first, Google ADK for GCP-first, Strands+AgentCore for AWS-first, Smolagents for code-as-actions). The remaining set is niche, hosting infrastructure, or reference implementations rather than production choices.

## Decision tree (when to pick which)

1. **On Anthropic and want the same loop as Claude Code:** Claude Agent SDK. Hosted: Claude Managed Agents. Build on top: Deep Agents (works with any model via LangGraph).
2. **Need graph-based stateful workflows with durable execution and HITL:** LangGraph. Add Deep Agents on top for filesystem + planning + subagents pre-wired.
3. **Prototyping multi-agent and want a demo by lunch:** CrewAI (migrate to LangGraph or MS Agent Framework when you need durability).
4. **TypeScript-native:** Mastra.
5. **.NET / Azure-native:** Microsoft Agent Framework.
6. **GCP / Gemini-native:** Google ADK.
7. **AWS-native and want managed infra:** Strands + AgentCore.
8. **Production-grade type safety and clean API in Python:** Pydantic AI.
9. **On OpenAI with sandbox + skills + filesystem stack:** OpenAI Agents SDK (post-April 2026).
10. **Minimalism, code-as-actions, open-weight models:** Smolagents.
11. **Building your own Claude Code:** OpenHarness, Pi, or Deep Agents as starting point.
12. **Work is document-heavy (contracts, compliance, knowledge extraction):** LlamaIndex AgentWorkflow.
13. **You're a Salesforce shop and the agent needs to act on Salesforce data and processes:** Agentforce. Don't try to bolt LangGraph onto Salesforce — the Trust Layer, Data Cloud grounding, identity model, and audit trail are extremely hard to replicate from outside.
14. **You're *not* on Salesforce but want to integrate with Agentforce-owned data:** use Salesforce-Hosted MCP from your other harness (Claude Agent SDK, OpenAI Agents SDK, etc.). The MCP bridge means you don't migrate to Agentforce to leverage its data layer.

## Cross-cutting observation (the load-bearing point)

Most discussions of agent frameworks treat *which runtime do I import* as the load-bearing decision. It isn't. The load-bearing decisions are *what skills does the agent need*, *what architectural shape best executes this kind of work*, and *which runtime preserves that shape with the fewest impositions*. The runtime choice falls out of the first two; teams that skip the architecture question inherit whatever shape their first import happened to default to.

Architectural shape (`architectures/single-agent-react.md`, `architectures/adversarial-decomposition.md`, etc.) is its own decision tier, separate from harness choice. Pick the architecture first; the harness narrows automatically.

Prompts authored against one harness/model don't always port cleanly across boundaries (`anti-patterns/...` — TBD pattern entry on prompt-flavor portability). Budget for a calibration pass anywhere you cross an architecture, model, or runtime boundary. Not a regression on portability; the last-mile cost of any cross-boundary move.

## When to revisit this entry

| Trigger | Action |
|---|---|
| 90+ days since `snapshot_date` | Refresh the table; the field moves fast |
| A new major framework ships (post-1.0) | Add a row; reorder the decision tree if applicable |
| A listed framework is deprecated or sunset | Update its row + decision-tree entry; consider removing if discontinued |
| Atlan's own architecture choices contradict the decision tree | Update the cross-cutting observation section with the empirical receipt |

## Maintenance notes

- This is a **comparative survey** entry, not an operational-decision entry. The body shape is intentionally different from `architectures/*.md` entries — tables + per-item analysis + decision tree + cross-cutting observation, rather than `Use when / Don't use when / Gotchas / Empirical anchor`.
- Survey entries date faster than operational-decision entries. The `snapshot_date` field is added to the frontmatter for this category — when the date is stale, the entry needs a refresh ingest pass.
- Per-harness deep-dive entries live alongside this survey (the first is `harnesses/agentforce-deep-dive.md`, added 2026-05-22). They're code-pattern shaped (gotchas + code excerpts + decision criteria) and cover one framework each in depth. This entry is the meta-view; deep-dives are the detail. Each deep-dive is cited from the relevant row in this survey's table.
- Source: internal Atlan research docs reviewed in conversation. Cited but not co-located in this repo; if the source docs are committed, link directly.

## Provenance

`status: validated` rests on sustained pipeline use, not a single measurement:
this survey has been loaded into every runtime-proposal step since 2026-05 and
is cited in the selection rationales of the SE co-pilot and P&G FHC baseline
runs (see the repo's baseline comparisons). Survey claims themselves carry the
`snapshot_date` and should be re-verified against vendor docs when consumed
after a major release cycle.
