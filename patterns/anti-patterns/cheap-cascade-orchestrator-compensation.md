---
title: Cheap-Cascade Orchestrator Compensation
category: anti-patterns
status: validated
last_updated: 2026-05-22
source_findings:
  - findings/08-cheap-cascade-gpt4o-mini-doesnt-pan-out.md
source_external: []
applies_when:
  workloads: [multi-agent-with-extractors, mega-agent-with-sub-agents, chained-pipeline-with-orchestrator]
  constraints: [extractors-feed-an-orchestrator, orchestrator-can-call-tools-or-extend-context]
contradicts: []
related: [definitions-without-context, single-agent-react]
---

# Cheap-Cascade Orchestrator Compensation

Swapping the sub-agent extractors (triage, distill, synthesize) to a cheaper model while keeping the orchestrator/mega-agent on a frontier model **doesn't save money**. The orchestrator detects the thinner extractor outputs and compensates — calling more tools, producing longer responses, re-fetching state — and its own token usage balloons enough to swamp the sub-agent savings.

The intuition "extractors are simple, smaller model should be fine" is wrong in the load-bearing direction. Extractor quality affects orchestrator behavior. Treat them as upstream of the same budget, not as independent line items.

## Detect when

- Sub-agent costs are 30–50% of total; tempting to "just make those cheaper"
- The cheaper extractor model is in the same provider family (Haiku → Mini, GPT-5 → 4o-mini)
- The orchestrator can call tools to fetch state, re-read priors, or extend its reasoning
- Quality metric is fuzzy (LLM-as-judge, conversation feel) rather than binary (did the SQL run?)

## Don't worry about when

- Extractors emit purely structured output that the orchestrator uses without interpretation (e.g., a deterministic gate: did extraction find a date? if no, escalate)
- Orchestrator is itself rule-based / non-LLM
- You've measured end-to-end cost AND quality AFTER the swap on representative load, not estimated savings before

## Key gotchas

- **Cost balloons in the orchestrator's input tokens, not its output.** It re-reads system prompt + history + tool results more often. Caching helps only if your provider supports it.
- **Quality degrades in subtle ways.** Topic granularity collapses (21 distinct topics → 9 lumpy ones in the empirical anchor below). The orchestrator doesn't crash; it just produces less-faithful captures.
- **Same-provider swaps share failure modes.** GPT-4o-mini occasionally returns `{}` for triage; the orchestrator routes the turn as if no extraction happened, then the next turn's mega-agent re-investigates. Cross-provider swaps (Claude → GPT) might compound this with format-instruction-following gaps.
- **The reverse is also true:** if you upgrade the extractors to a frontier model, the orchestrator gets *less* talkative — but you've already paid for the orchestrator-class spend on every turn. Net savings only show up when you can also downgrade the orchestrator, which usually you can't without quality loss.

## What to do instead

- **Keep extractors and orchestrator on the same model class.** Treat them as a single budget unit.
- **If you must cut cost, cut latency-correlated things first:** prompt caching, history compaction, conditional sub-agent invocation. These don't trigger orchestrator compensation.
- **If you must cut spend on extractors specifically, replace them with deterministic code** where possible (regex triage, schema-validating distiller). Deterministic outputs don't make the orchestrator anxious.

## Empirical anchor

`findings/08` — controlled comparison on the same 50-turn TechCo Sales Pipeline Analyst script:

|   | All-Haiku-4.5 baseline | Mini-extractors + Haiku-mega |
|---|---|---|
| Wall time | 671s | 613s (–9%) |
| Mega-agent input tokens | 540K | **1,706K (+216%)** |
| Mega-agent tool calls | 6 | **27 (+350%)** |
| Sharpener-rewrite rate | 55% | **77%** |
| Final theory confidence | medium | **low** |
| Topics captured (granularity) | 21 | **9** (lumpier) |
| Total cost est. | ~$1.08 | **~$1.81 (+67%)** |

The cheap-cascade was net negative on both axes — sub-agent savings of ~$0.45 were swamped by +$1.18 of mega-agent compensation. Latency improved 9% but that's an aggregate of "fewer extractor calls" minus "more orchestrator iterations" — both happened, the orchestrator just happens to be the lighter-weight one in this codebase.

n=1 use case; the effect size is large enough (+67% cost, –27% quality) that the finding is load-bearing even with single-script data.

## What this rules out for downstream proposers

When `inception/runtime_proposer` is selecting models for a multi-agent architecture, the temptation to recommend a cheap-cascade configuration ("Haiku for sub-agents, Opus for orchestrator") should be flagged against this entry. The proposer should either:

1. Pick a single model class for all roles, OR
2. Explicitly call out the orchestrator-compensation risk and recommend a measured comparison before the cheap-cascade configuration ships.
