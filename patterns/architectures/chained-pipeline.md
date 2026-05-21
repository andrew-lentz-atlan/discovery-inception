---
title: Chained Pipeline (Pure Sub-Agent Decomposition)
category: architectures
status: deprecated
last_updated: 2026-05-05
source_findings: [findings/01-architecture-comparison.md]
source_external: []
applies_when:
  workloads: [batch, deterministic-multi-stage, structured-extraction-only]
  constraints: []
contradicts: [single-agent-react]
related: []
superseded_by: [single-agent-react]
reference: chained-pipeline.reference.md
---

# Chained Pipeline (Pure Sub-Agent Decomposition)

Sequential small task-scoped LLM calls. Each sub-agent has one prompt + one Pydantic output type, consuming the previous sub-agent's output. The orchestrator is dumb Python — the path is fixed, no model "decides" what runs next.

**Status: deprecated for agent-level conversational architectures.** Still valid for batch extraction (see `## Where this is still alive`). Kept readable for traceability.

## Use when

- Pure batch extraction: artifact in → fixed pipeline → structured output. No conversation, no adaptive routing. Example: the `intake/` pipeline producing a RoleContext.
- Deterministic multi-stage outputs where you know every step that needs to run, in order, every time.
- Each step's model can be downsized independently (cost-sensitive workloads).
- Per-step traceability is the load-bearing requirement.

## Don't use when

- Conversational workloads. **This is the deprecation case** — see `## Empirical anchor`.
- Any workload where the next step depends on judgment about prior steps. The chain runs every step every turn; can't decide.
- Multi-turn workloads with cross-turn dependencies. Maintaining state across turns becomes a separate problem the chain doesn't solve.

## Key gotchas

- **"Smart routing" between chain steps is the slippery slope to hybrid.** Once one sub-agent decides whether to run another, you're not in pure-chain anymore. Either commit (every step every time) or switch to single-agent-with-tools.
- **Sub-agent failures cascade.** When step N hallucinates, step N+1 receives bad input. The chain doesn't self-correct.
- **Trace volume explodes.** N customer turns × M sub-agents = N×M traces. Plan retention accordingly.

## Empirical anchor

`findings/01`: same script across three architectures.

| | chained | mega-only | hybrid |
|---|---|---|---|
| conversation-quality wins | **0/5** | 2/5 | 3/5 |
| wall time | 75s | 16s | 85s |
| structured spec | ✓ | ✗ | ✓ |

Hard to find a column where chained wins. The hybrid (extractors + single-agent + tools) became the actual recommendation. See `chained-pipeline.reference.md` for the full comparison + where the pattern is still alive in our codebase.
