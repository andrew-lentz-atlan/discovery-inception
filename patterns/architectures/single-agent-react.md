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
contradicts:
  - chained-pipeline
related:
  - adversarial-decomposition
  - skill-design/inner-pipeline
  - harnesses/claude-agent-sdk
  - harnesses/openai-agents-sdk
---

# Single-Agent ReAct (with Tools)

One LLM call per turn, with a strong system prompt and a bound set of tools (or skills) the model decides to invoke. The model reads the user input, reasons, picks tools, gets results back, reasons again, picks more tools, until it produces a final answer. The whole agent is the prompt + the tools + the loop.

The "ReAct" name comes from Reason-and-Act — the loop is conceptually `[reason → act → observe]`, repeated until done. In modern SDKs (Anthropic SDK, OpenAI Agents SDK), this is the default shape — you bind tools and the harness handles the loop until the model emits `stop_reason: "end_turn"`.

---

## When to use

- **Query-response workloads with a known answer shape.** *"Why did X lose share at Y?"* — single question, multi-step lookup, structured answer. Bala's P&G Brand Analyst Agent is the canonical example: 4 tools bound, 4-6 tool calls in 2-3 iterations, final HTML report.
- **Workloads where the model is competent at routing without external planning.** Frontier models (Claude Opus 4.7, GPT-5.4) decide tool sequence well; weaker models benefit from explicit planning (see `planning-first` pattern, not yet written).
- **Conversational agents where the conversation shape is unknown ahead of time.** Discovery interviews where the agent must adapt to whatever the customer says next. Empirically (findings/01), the single-agent mega prompt produced 2/5 wins on conversation quality vs the chained alternative's 0/5.
- **Production agent surfaces where simplicity is a feature.** One loop is one thing to debug.

---

## When NOT to use

- **Workloads where the deliverable is heavily structured.** findings/01 showed mega-only produced no structured spec — it could converse but couldn't maintain spec state across turns. If you need a `spec.json` at the end, you need either decomposed state extractors (the hybrid pattern) or explicit state-management tools.
- **Multi-domain workloads with conflicting reasoning patterns.** A single agent juggling SQL generation + customer-empathy + executive-narrative-voice tends to degrade on all three. Decompose to skills (each skill being its own inner-pipeline).
- **Long-horizon workflows that need durability and replay.** Single-agent loops are stateless across crashes. For durability, use a graph runtime (LangGraph) underneath the same conceptual ReAct loop.
- **When you need adversarial review.** If output quality is critical, add an adversarial-decomposition pair on top of (not instead of) the single-agent loop. See `adversarial-decomposition.md`.

---

## Empirical receipts

`findings/01-architecture-comparison.md` (2026-05-05, 5-turn deterministic script):

| Variant | Conversation quality (subjective wins) | Wall time | Structured spec produced |
|---|---|---|---|
| Chained (v0.5) | 0/5 | 75s | ✓ |
| **Mega-only** | **2/5** | **16s** | ✗ |
| Hybrid (extractors + mega + tools) | 3/5 | 85s | ✓ |

The headline finding: **decomposition is not load-bearing for conversation quality.** The single-agent prompt produced more compelling conversation than the chained pipeline at 4× the speed. But it sacrificed structured state.

Bala's P&G Brand Analyst Agent (https://github.com/bladata1990/pg-brand-analyst-agent) is an independent empirical receipt:

- Single Anthropic SDK tool-use loop, claude-opus-4-7
- 4 tools bound (search_atlan, analyze_market_share, diagnose_root_cause, generate_report)
- Typical 4-6 tool calls across 2-3 loop iterations
- LLM-as-judge independent score: **97/100**

Same architecture, very different workload (query-response analyst vs conversational discovery), both empirically successful. The pattern travels across workload shapes.

---

## Implementation gotchas

- **Tool definitions must be precise.** Vague tool descriptions cause the model to invoke them at wrong moments. Be explicit about *when to call*, not just *what it does*.
- **Stop-condition handling.** Anthropic SDK uses `stop_reason: "end_turn"`. OpenAI Agents SDK uses similar. Be careful with `max_iterations` defaults — too low and the model gives up mid-task; too high and runaway loops are possible.
- **Sequential tool calls per iteration.** Most SDKs let the model emit multiple tool calls per turn; they run in parallel. Make sure your tools are idempotent / order-independent if you rely on this.
- **Context bloat across iterations.** Tool results stay in the message history. Over 5+ iterations the context gets large. Mitigation: compact older tool results (summarize them) or use the harness's built-in compaction.
- **System prompt is load-bearing.** Bala's was ~1.5K tokens encoding workflow rules + BCA categories + citation discipline. The mega-agent in v0.7-v0.8 of discovery uses ~2-3K tokens of system prompt. Skimping here is the most common failure mode.

---

## Variants & related patterns

- **Hybrid (extractors + mega-agent + tools)** — the pattern findings/01 actually recommended for discovery. Single-agent ReAct at the conversation layer, plus structured extractor sub-agents producing per-turn state. Best of both. Not yet promoted into a separate pattern entry.
- **`adversarial-decomposition.md`** — orthogonal layer: add a critic to review the single-agent's output. Pairs cleanly.
- **`chained-pipeline.md`** — the alternative this contradicts. Read both before choosing.
- **`skill-design/inner-pipeline.md`** — a single-agent loop where each *tool* is itself an inner pipeline (LLM #1 generates SQL, LLM #2 interprets results). Bala's pattern. Combines well.

---

## Cost / latency profile

For Claude Opus 4.7 in production (Bala's P&G agent, 97/100 baseline):

| Component | Latency |
|---|---|
| Per iteration (model call) | 5-12s |
| Per tool call (inside iteration) | varies — 1-3s for Atlan API, 2-5s for inner-pipeline skill |
| Typical full session | 30-90s end-to-end for a 4-6-tool-call task |

For Claude Haiku 4.5 (discovery v0.8 mega-agent):

| Component | Latency |
|---|---|
| Per iteration | 5-8s |
| Plus sharpener post-processor | +3-5s |
| Total per turn | 13-17s end-to-end |

---

## Maintenance notes

- Promoted during the gold-standard seed pass 2026-05-20.
- Status remained `validated` rather than going to `experimental` because we have two independent empirical receipts (findings/01 + Bala's repo) showing the pattern works across distinct workloads.
- The `hybrid` variant deserves its own entry once another finding validates it independently of findings/01.
