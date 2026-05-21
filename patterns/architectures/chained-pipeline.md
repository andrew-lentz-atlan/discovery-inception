---
title: Chained Pipeline (Pure Sub-Agent Decomposition)
category: architectures
status: deprecated
last_updated: 2026-05-05
source_findings: [findings/01-architecture-comparison.md]
source_external: []
applies_when:
  workloads: [batch, structured-extraction-only, deterministic-multi-stage]
  constraints: []
contradicts:
  - single-agent-react
related:
  - skill-design/inner-pipeline
  - single-agent-react
superseded_by:
  - single-agent-react  (for conversational workloads)
  - hybrid-extractors-plus-mega-agent  (for structured + conversational; not yet promoted)
---

# Chained Pipeline (Pure Sub-Agent Decomposition)

Sequential small task-scoped LLM calls. Each sub-agent has one prompt, one Pydantic output type, and consumes the previous sub-agent's output. The whole pipeline is the orchestrator stitching them together. No model "decides" the path; the path is fixed Python.

This was the v0.5 architecture of discovery: triage → distill → synthesizer → why-prober → probe-generator. Five sub-agents per customer turn. Pure decomposition all the way down.

**Status: deprecated for conversational workloads.** This entry is kept readable for traceability and to document when the pattern still has value (structured-extraction-only batch workloads).

---

## When to use

- **Pure batch extraction.** Take an artifact, run a fixed pipeline of steps, produce a structured output. No conversation, no adaptive routing, no judgment about which step to run next. Examples: the intake pipeline (`intake/run.py` — 6 sequential steps to produce a RoleContext from an artifact), document parsing chains, ETL with LLM enrichment.
- **Deterministic multi-stage outputs.** When you know exactly which steps need to run, in what order, every time. The orchestrator is dumb Python; each LLM call is small and focused.
- **Cost / latency-sensitive contexts where each step's model can be downsized independently.** Each sub-agent can use the cheapest sufficient model. The chain doesn't need a frontier model for the easy 80%.
- **When per-step traceability is the load-bearing requirement.** Each sub-agent's input + output is one Pydantic instance — clean to log, clean to test, clean to swap.

---

## When NOT to use

- **Conversational workloads.** This is the deprecation case. `findings/01` showed the chained agent produced 0/5 wins on conversation quality vs the single-agent mega prompt's 2/5 and the hybrid's 3/5. Pure decomposition is rigid; conversation needs adaptive routing the chain can't provide.
- **Workloads where the next step depends on judgment about prior steps.** *"Should we synthesize now, or wait?"* — the chain runs every step every turn. Lazy synthesis (`findings/02`) showed that "always synthesize" wasted compute and degraded conversation. Single-agent ReAct can decide; the chain can't.
- **Multi-turn workloads with cross-turn dependencies.** The chain operates per-turn. Maintaining a coherent multi-turn working theory required adding an outer state container, which is just a hybrid by another name.
- **Anywhere a model would benefit from choosing the path.** Frontier models route well. Forcing a fixed Python path overrides that intelligence.

---

## Empirical receipts (the deprecation evidence)

`findings/01-architecture-comparison.md` (2026-05-05):

| Variant | Conversation quality wins | Wall time | Structured spec |
|---|---|---|---|
| **Chained (v0.5)** | **0/5** | **75s** | ✓ |
| Mega-only | 2/5 | 16s | ✗ |
| Hybrid | 3/5 | 85s | ✓ |

The chained pipeline lost on the dimension we cared about most (conversation quality), didn't have the speed advantage of the mega-only variant, and was equal to the hybrid on structured-spec production but worse on conversation. Hard to find a column where the chain wins.

`findings/02-v07-lazy-synthesis-and-free-form-output.md` extended this: even within a chain, running every sub-agent every turn (eager synthesis) wasted compute. Lazy invocation (model decides when to call) won. But once you give the model that decision, you've already left the pure-chain pattern — you're in single-agent-with-tools territory.

The chained pipeline still works for `intake/` (a strict batch pipeline producing a RoleContext from an artifact). 6 sub-agents in sequence: classify → extract → normalize → sniff → report-gaps → score-confidence. No conversation, no routing, deterministic order. **The pattern is genuinely good for this shape.**

---

## Implementation gotchas

- **Adding "smart routing" between chain steps is the slippery slope to hybrid.** Once you let one sub-agent decide whether to run another, you're not in pure-chain anymore. Either commit to the chain (every step every time) or commit to single-agent-with-tools (model decides).
- **Sub-agent failure modes are uncorrelated but cascading.** When sub-agent N hallucinates, sub-agent N+1 receives bad input. The chain doesn't self-correct because there's no judge between steps. Build deterministic validators between sub-agents if reliability matters.
- **Trace volume explodes.** N customer turns × M sub-agents per turn = N×M traces. For a 50-turn discovery session, that's hundreds of structured events. Plan trace retention accordingly.
- **Cost stacks.** Each sub-agent is a separate LLM call. Even on cheap models, the multiplier adds up — discovery's v0.5 was ~$0.50 per session, dominated by the per-turn chain count.

---

## Variants & related patterns

- **`single-agent-react.md`** — the contradicting pattern. For conversational workloads, this is what to use instead.
- **`skill-design/inner-pipeline.md`** — chained pipelines embedded *inside* a single skill. Bala's pattern. Different from a chained agent-level architecture: the chain lives at skill granularity, not the whole agent. This shape is alive and well.
- **The hybrid (extractors + mega-agent + tools)** — combines extraction-style chained sub-agents (the chain lives in the extractor layer) with a single-agent ReAct conversation layer. findings/01 chose this as the winning pattern; not yet promoted to its own entry but referenced widely.

---

## Where this pattern is still alive in our codebase

- **`intake/run.py`** — 6-step batch pipeline producing a `RoleContext`. This is the canonical "chained pipeline is the right answer" case. Don't replace it with a single-agent loop.
- **The extractor layer in v0.8's hybrid discovery agent** — `triage` → `distill` runs every turn as a deterministic chain. The mega-agent on top is single-agent ReAct. This is the *hybrid* pattern — the chain provides the structured state; the mega-agent provides the conversation.

---

## Why this entry is `deprecated` rather than `experimental` or absent

The pattern itself isn't wrong. The pattern is the right answer for batch extraction. The deprecation is specifically about its use as an **agent-level architecture for conversational workloads** — that's where the empirical case (findings/01) says it loses.

Future entries (`hybrid-extractors-plus-mega-agent.md`, `skill-design/inner-pipeline.md`) will capture where chained-style decomposition is still load-bearing. Read those when designing skill internals; read this one when deciding the overall agent shape.

---

## Maintenance notes

- Authored during the gold-standard seed pass 2026-05-20.
- Status: `deprecated` for agent-level architecture; the pattern remains valid at sub-skill level (see `inner-pipeline.md` once authored).
- Next review: if a future finding shows the pattern winning on a workload shape we haven't tested, status may upgrade back to `validated` with the narrower applicability.
