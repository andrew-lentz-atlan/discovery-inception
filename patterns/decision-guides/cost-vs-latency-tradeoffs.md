---
title: Cost vs Latency Tradeoffs in Multi-Step Agent Pipelines
category: decision-guides
status: validated
last_updated: 2026-05-22
source_findings:
  - findings/06-cost-latency-and-deployment-modes.md
  - findings/08-cheap-cascade-gpt4o-mini-doesnt-pan-out.md
source_external: []
applies_when:
  workloads: [multi-step-agent, sub-agent-pipeline, conversational-agent]
  constraints: [interactive-or-async-deployment, per-turn-latency-matters]
contradicts: []
related: [cheap-cascade-orchestrator-compensation, single-agent-react, inner-pipeline]
---

# Cost vs Latency Tradeoffs in Multi-Step Agent Pipelines

For multi-step / multi-agent pipelines, **latency is usually the load-bearing constraint, not token cost.** A pipeline that costs $0.50/session but takes 15s/turn loses users; a pipeline that costs $2.00/session at 5s/turn keeps them. Optimize latency first; revisit cost once the deployment shape is settled.

The exception: high-volume async batch workloads (process N transcripts overnight) where nobody is waiting on individual turns. There, cost dominates and the calculus flips.

## How to think about it

The deployment mode determines which dimension is load-bearing. Pick the mode first, then optimize:

| Mode | Latency tolerance | Cost sensitivity |
|---|---|---|
| **Real-time voice** (agent speaks live) | < 2s | low — quality dominates |
| **Live co-pilot** (sidebar; agent annotates while human drives) | 5–10s acceptable | low |
| **Interactive chat** (user types, waits for response) | < 8s ideal, 15s tolerable | moderate |
| **Async batch** (process N artifacts overnight) | minutes is fine | high — cost dominates |

A pipeline tuned for interactive chat at 13s/turn is fine for batch. The reverse — pipeline tuned for batch at $0.10/session — usually misses the latency target for interactive.

## Where the time goes in a multi-step pipeline (representative anchor)

From `findings/06`, an empirical breakdown of a v0.8 conversational discovery agent:

| Step | Typical time | Conditional? |
|---|---|---|
| Triage (sub-agent classification) | 3–4s | always |
| Distill (extract fact from concrete answer) | 2–3s | ~70% of turns |
| Mega-agent (orchestrator w/ tool calls) | 5–8s | always |
| Probe-sharpener (adversarial review) | 3–5s | most question-shaped responses |
| `synthesize_my_thinking` (deep reflection) | 5–8s | rare (~4% of turns) |
| `find_tensions` (cross-fact scan) | 3–5s | rare |

Steps are **sequential by data dependency** (triage → distill → mega-agent → sharpener). Parallelism is limited; eliminating a step is the bigger lever.

## Latency optimizations in rough leverage order

| # | Optimization | Saves | Effort |
|---|---|---|---|
| 1 | **Prompt caching** — system prompts are ~10K tokens, identical every turn | 1–2s/turn | Low (~30 LoC if proxy supports it) |
| 2 | **Skip-when-unlikely** — tiny pre-classifier predicts when expensive step is needed | 3–5s × N% of turns | Medium |
| 3 | **Stream the orchestrator response** — show words as they arrive; review runs in parallel | improves *perceived* latency materially | Medium (streaming API + UI) |
| 4 | **Speculative parallelism** — triage of turn N runs while mega-agent of turn N-1 finishes | 1–2s/turn | Medium (async coordination) |
| 5 | **History compaction** — fold older turns into one condensed message | 0.5–1s/turn (compounds on long sessions) | Low |
| 6 | **Conditional sub-agent invocation** — only run sub-agent X when the trigger condition fires | 2–4s × % skipped turns | Medium |

Note what's NOT on this list: swapping sub-agents to a cheaper model class. That's a cost-optimization that *also* affects latency — but per `cheap-cascade-orchestrator-compensation.md`, it usually backfires on both axes.

## Cost optimizations that don't trigger orchestrator compensation

If cost is the actual constraint (async batch, scale > $1K/day), these are safer than cheap-cascade:

- **Prompt caching** — same as the latency win; cache hits are free
- **Conditional invocation** — fewer LLM calls when not needed
- **Deterministic replacement** — anywhere a sub-agent's output is structured + checkable, replace the LLM with code (regex triage, schema validators)
- **Smaller context** — history compaction also reduces input tokens
- **Cheaper orchestrator only after measuring** — if you must downgrade the orchestrator, validate quality on representative load BEFORE shipping; don't estimate the savings

## Don't worry about latency when

- Deployment is async-batch and turn time < total available compute window
- Per-call cost dominates user experience (regulated industries; high-value-per-call workloads)
- Quality criticality is dominant — users will wait 30s for a correct answer

## Don't worry about cost when

- Deployment is interactive (chat / co-pilot / voice) and latency is the actual bottleneck
- Total spend is below the threshold where it gets attention (often < $0.50/session for human-in-the-loop work)
- The "savings" are tiny relative to the human time they save

## Empirical anchor

`findings/06` documented v0.8 latency (~13–17s/turn) and proposed a 5–8s/turn target via the optimization list above. `findings/08` documented the negative result of the naive cost-optimization (cheap-cascade) — same architecture, swap extractors to a cheaper model, observe a +67% total cost outcome because the orchestrator compensates.

Pattern: optimize the right axis for the deployment mode. Don't reach for "obvious" cost cuts (cheaper sub-agent model) when latency is the actual constraint; don't reach for latency cuts (parallelism, streaming) when cost is dominating.

## What this guides for downstream proposers

- `inception/runtime_proposer` should pick a model class consistent with the workload's interaction shape (real-time → frontier; async → range OK)
- `inception/architecture_proposer` should bias toward fewer sequential sub-agents when latency is tight; toward more decomposition when cost / quality dominate
- Cross-stage signal: if discovery captured `workload.latency_sensitivity = real-time` and `data_intensity = high`, that's a tension — flag it; the customer is asking for incompatible properties
