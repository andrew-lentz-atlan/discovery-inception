---
title: Single-Agent ReAct (with Tools)
category: architectures
status: validated
last_updated: 2026-05-20
source_findings: [findings/01-architecture-comparison.md]
source_external:
  - https://github.com/bladata1990/pg-brand-analyst-agent
applies_when:
  workloads: [query-response, single-question-end-to-end, conversational]
  constraints: [simplicity-prized, low-latency-target, single-domain-scope]
contradicts: [chained-pipeline]
related: [adversarial-decomposition]
---

# Single-Agent ReAct (with Tools)

One LLM call per turn with a strong system prompt and a bound set of tools the model decides to invoke. The loop is `reason → act → observe`, repeated until the model emits `stop_reason: "end_turn"`. The whole agent is `prompt + tools + loop` — the harness (Anthropic SDK, OpenAI Agents SDK, Pydantic AI) handles iteration.

## Use when

- Query-response with a known answer shape (*"Why did X lose share at Y?"*) — single question, multi-step lookup, structured answer
- Frontier models doing the routing (Claude Opus 4.7, GPT-5.4 route tool calls well; weaker models benefit from explicit planning)
- Conversational agents where the conversation shape is unknown ahead of time and adaptive routing matters
- Production surfaces where simplicity is a feature — one loop, one thing to debug

## Don't use when

- Deliverable is heavily structured and must persist across turns (use the hybrid — extractors + single-agent + tools)
- Multi-domain workloads with conflicting reasoning patterns (decompose to skills with their own inner pipelines)
- Long-horizon workflows needing durability and replay (put a graph runtime like LangGraph underneath)
- Quality criticality requires adversarial review (layer on `adversarial-decomposition`, don't replace the loop)

## Key gotchas

- **Tool descriptions are load-bearing.** Vague descriptions cause wrong-moment invocations. Be explicit about *when* to call, not just *what*.
- **`max_iterations` defaults.** Too low → model gives up mid-task. Too high → runaway loops.
- **Context bloat across iterations.** Tool results accumulate. After 5+ iterations the context is large. Use harness compaction or summarize older results.
- **System prompt is load-bearing.** Bala's was ~1.5K tokens encoding workflow + BCA categories + citation discipline. Skimping here is the most common failure mode.

## Empirical anchor

Two independent receipts:

- `findings/01`: 5-turn deterministic script comparing chained / mega-only / hybrid. The mega-only variant produced 2/5 conversation-quality wins at 4× the speed of the chain, but no structured spec. The hybrid (single-agent ReAct + extractors) won outright at 3/5.
- The public brand-analytics reference build (https://github.com/bladata1990/pg-brand-analyst-agent): single Anthropic SDK tool-use loop, claude-opus-4-7, 4 tools, 4–6 tool calls across 2–3 iterations. Independent LLM-as-judge score: **97/100**.

Same architectural shape, very different workloads. The pattern travels.
