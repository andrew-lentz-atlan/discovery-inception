---
title: Context Engineering as Working-Memory Architecture: Patterns, Failure Modes, and Evaluation
category: skill-design
status: draft
last_updated: 2026-07-15
source_findings: []
source_external:
  - Chroma Context Rot study (July 2025)
  - NoLiMa (arXiv 2502.05167, ICML 2025)
  - Lost-in-the-middle (Liu et al., 2023, TACL)
  - LongMemEval (arXiv 2410.10813, ICLR 2025)
  - Anthropic internal evals (Sept–Nov 2025)
  - Mem0 vs. baselines on LoCoMo (arXiv 2504.19413, 2025)
  - Zep temporal knowledge graph (arXiv 2501.13956, Jan 2025)
  - Are We Ready For An Agent-Native Memory System? (arXiv 2606.24775, 2026)
  - BrainMem (2026)
  - BEAM (ICLR 2026, arXiv 2510.27246)
  - Manus KV-cache metric (July 2025)
  - RULER cross-checks
applies_when:
  workloads:
    - multi-turn-conversational
    - long-horizon-task-execution
    - multi-agent-with-extractors
    - chained-pipeline-with-orchestrator
  constraints:
    - token-budget-constrained
    - latency-sensitive-retrieval
    - long-context-degradation-observed
    - governance-and-compliance-critical
contradicts: []
related:
  - decision-guides/does-this-agent-need-memory
  - decision-guides/memory-architecture-selection
  - skill-design/memory-operations
  - skill-design/inner-pipeline
  - architectures/chained-pipeline
  - architectures/single-agent-react
  - anti-patterns/wasteful-subagent-context-reload
  - anti-patterns/silent-tool-fallback
snapshot_date: 2026-07-15
source_hash: 7b25967ed4fa8101
---

# Context Engineering as Working-Memory Architecture: Patterns, Failure Modes, and Evaluation

Context engineering is now formalized as working-memory architecture—the discipline of curating and maintaining an optimal token set during LLM inference. Context is a depleting attention budget, not a free buffer; every architectural move (compaction, scratchpads, sub-agent isolation, just-in-time retrieval, code offload) is a deliberate allocation decision about scarce working store. Measured degradation across 18+ frontier models, specific failure modes in compaction (causal-structure loss, governance decay, drift), and a converging evaluation harness (on/off/oracle arms + memory-quality metrics + regression gates) now make context engineering a quantifiable design discipline rather than prompt-engineering intuition.

## The N, summarized

| # | Item | What it is | The one gotcha that bites |
|---|---|---|---|
| 1 | Compaction (summarize-and-reinitialize) | Message history is summarized preserving architectural decisions, unresolved bugs, and implementation details while discarding redundant tool outputs; agent continues with summary plus most recently accessed files. | Loss of subtle context, causal-structure destruction, governance decay, drift, non-determinism in summarization. |
| 2 | Scratchpads / structured note-taking | Agent writes its own notes to files outside the window and re-reads on demand; observations too large for window live as files; context keeps only paths/URLs (restorable references, not payloads). | Compression is reversible by design, but requires discipline in what gets written and when it gets pruned. |
| 3 | Sub-agent context isolation | Each subagent gets self-contained task, fresh window, no knowledge of siblings; returns condensed summary (typically 1,000–2,000 tokens) to lead. | Parallel subagents carry conflicting implicit decisions; actions encode choices that summaries drop, requiring full-trace sharing where decisions interlock. |
| 4 | Just-in-time retrieval over pre-loading | Maintain lightweight identifiers (paths, queries, links) and load data at runtime via tools—progressive disclosure through exploration. | Working-memory rehearsal loop requires pointers resident and payloads fetched on demand; staleness poisons retrieval by default without active maintenance. |
| 5 | Deterministic core / LLM rim | Treat tool ecosystems as code APIs; agent writes code that runs outside the model. Intermediate data flows through execution environment; only filtered result enters context. | Control flow moves to deterministic code instead of token-burning inference round-trips; KV-cache hit rate is the #1 production metric. |
| 6 | LoCoMo benchmark | ~1,540 questions over multi-session synthetic dialogs; QA F1 + retrieval metrics. Baseline: open/commercial LLMs scored F1 13.9 (Mistral-7B) – 32.1 (GPT-4) vs. human 87.9. | LLM-generated, keyword-rich dialogue flatters exact-match retrieval; documented inaccurate gold answers; no knowledge-update scoring. Treat as baseline floor, not a bar. |
| 7 | LongMemEval benchmark | 500 questions over histories of ~115k tokens/~40 sessions (S) up to ~500 sessions (M); scores five abilities: information extraction, multi-session reasoning, temporal reasoning, knowledge updates, abstention. | Abstention and knowledge-update axes are what production needs and LoCoMo lacks; headline 30–60% accuracy loss vs. oracle retrieval. |
| 8 | BEAM benchmark | 100 conversations up to 10M tokens, 2,000 probing questions; scaling receipt—~25% performance loss going 1M → 10M; temporal queries hardest. | Tests long-horizon stability, the least-measured axis in prior benchmarks; addresses production gap where agents run months/thousands of sessions. |
| 9 | MemoryAgentBench | Four competencies—accurate retrieval, test-time learning, long-range understanding, conflict resolution/selective forgetting. | No current system masters all four; selective-forgetting competency doubles as regression probe for continual-learning evaluation gap. |
| 10 | Production memory-quality metrics (four-layer stack) | Layer 1: task effectiveness. Layer 2: memory quality (retrieval precision/recall, contradiction rate, staleness rate, coverage, update correctness). Layer 3: efficiency (tokens/query, latency, construction cost). Layer 4: governance/drift monitoring. | Without maintenance/forgetting layer, stale records gradually poison retrieval precision—memory quality decays by default. Staleness must be tracked as rate, not assumption. |
| 11 | Regression gating for learned behavior | After every memory/skill update, re-run frozen suite of previously-passing tasks; ship update only if old capabilities hold. | Continual-learning practitioners: model that improves on new tasks while regressing on old ones erodes trust faster than model that never improves. |

## The few that actually matter for most decisions

For most production agents, three patterns dominate: **compaction** (when history grows beyond effective context window), **scratchpads** (when intermediate state exceeds token budget), and **deterministic core / LLM rim** (when data volume or control flow complexity makes token burn unsustainable). Sub-agent isolation scales only when subtasks are high-volume, low-relevance, and read-only-ish; Opus-4-lead + Sonnet-4-subagents outperformed single-agent Opus by 90.2% on internal research evals, but multi-agent burns ~15× more tokens than chat. Just-in-time retrieval is the default for any agent with access to external tools; the question is whether to pre-load a small upfront set (like CLAUDE.md) or fetch everything on demand.

Evaluation harness choice depends on your failure mode: LoCoMo catches retrieval precision gaps; LongMemEval surfaces temporal reasoning and knowledge-update failures; BEAM exposes long-horizon stability decay; MemoryAgentBench isolates selective-forgetting regressions. Production deployments should gate on all four axes—task effectiveness, memory quality, efficiency, and governance—rather than optimizing any single metric.

## Decision tree (when to pick which)

1. **History exceeds effective context window (typically 50–65% of advertised size per RULER cross-checks):** Use compaction with fine-tuned summarization model (off-the-shelf unreliable). Maximize recall first, then iterate on precision. Anthropic tuning guidance: capture everything relevant, then strip superfluous.

2. **Intermediate state (notes, tallies, maps, strategy) too large for window:** Use scratchpads with reversible compression—drop content, keep pointer. Manus recitation pattern: agent continuously rewrites todo.md at end of context, reciting objectives to bias attention and fight lost-in-the-middle.

3. **Data volume or control flow complexity makes token burn unsustainable:** Push data OUT of context entirely via deterministic core / LLM rim. Workflow tool-definitions-plus-intermediate-results load dropped 150,000 → 2,000 tokens (98.7% reduction); community replication achieved 112 tools while holding ~98% token reduction. Mask tools via logit masking rather than dynamic definition changes; KV-cache hit rate is #1 production metric (input:output ~100:1).

4. **Subtask is high-volume, low-relevance, read-only-ish, and parallelizable:** Consider sub-agent context isolation. Each subagent gets fresh window, returns condensed summary (1,000–2,000 tokens) to lead. Cost: ~15× more tokens than chat. Benefit: lead-agent working memory stays clean; exploration happens in disposable windows.

5. **Retrieval precision is the bottleneck (not token budget):** Use just-in-time retrieval over pre-loading. Maintain lightweight identifiers and load data at runtime via tools. Hybrid approach recommended: small upfront set plus grep/glob at will.

## Cross-cutting observation

All five patterns share a single principle: **context is a depleting attention budget, not a free buffer**. The empirical receipts converge on this: Chroma Context Rot (July 2025) tested 18 frontier models on NIAH, LongMemEval, repeated-words; every model degraded with input length even on trivial tasks. NoLiMa (arXiv 2502.05167, ICML 2025) found 11 of 12 models claiming ≥128K context dropped below 50% of their own short-context baseline at 32K tokens. Lost-in-the-middle (Liu et al., 2023, TACL) showed U-shaped position curve; accuracy drops 30+ points when relevant document sits mid-context. LongMemEval (arXiv 2410.10813, ICLR 2025) reported 30% accuracy drop memorizing information across sustained interactions; 30–60% below oracle retrieval on 115k-token histories.

The architectural response is not to fight this bottleneck but to design around it: treat context as a working-memory stack with explicit allocation decisions. Compaction, scratchpads, sub-agent isolation, just-in-time retrieval, and code offload are all mechanisms for *choosing what lives in the window at any moment*. The discipline is quantifiable: Anthropic internal evals (Sept 2025) showed memory tool + context editing = +39% over baseline on agentic search; context editing alone = +29%. Anthropic context editing (Sept 2025) enabled agents to finish otherwise-impossible 100-turn web-search workflows while cutting token consumption 84%. Mem0 vs. baselines on LoCoMo (arXiv 2504.19413, 2025) achieved 66.9% LLM-judge score vs. OpenAI memory 52.9% (+26% relative); full-context stuffing scored 72.9% (memory lost 6% accuracy vs. oracle while cutting p95 latency 91% and tokens 90%).

The emerging consensus: **memory quality (retrieval precision/recall, contradiction rate, staleness rate, coverage, update correctness) is a first-class design axis, not an afterthought**. Zep temporal knowledge graph (arXiv 2501.13956, Jan 2025) achieved +15.2% (gpt-4o-mini) / +18.5% (gpt-4o) accuracy over full-context baseline with ~90% latency reduction and <2% of baseline tokens. BrainMem (2026) showed stepwise adding working/episodic/semantic memory lifts embodied task planning 64.0% → 76.0%. BEAM (ICLR 2026, arXiv 2510.27246) tested 100 conversations up to 10M tokens with 2,000 probing questions; ~25% performance loss going 1M → 10M; temporal queries hardest. Are We Ready For An Agent-Native Memory System? (arXiv 2606.24775, 2026) evaluated 12 memory systems + 2 baselines across 5 workloads/11 datasets with per-module ablations quantifying representation fidelity, retrieval precision, update correctness, and long-horizon stability.

## When to revisit

| Trigger | Action |
|---|---|
| Task effectiveness drops >5% after memory/skill update | Run regression gate: re-run frozen suite of previously-passing tasks; revert if old capabilities regress. Continual-learning practitioners: improvement and regression analysis belong in same optimization step (RELAI). |
| Retrieval precision drops >10% or staleness rate exceeds 20% | Audit memory maintenance/forgetting layer. Without active pruning, stale records gradually poison top-k results; memory quality decays by default. Staleness must be tracked as rate, not assumption. |
| Token consumption per query exceeds budget or p95 latency exceeds SLA | Profile memory-quality metrics (Layer 3: tokens/query, p50/p95 latency, construction cost). Consider compaction, scratchpads, or code offload. Manus KV-cache metric (July 2025): cached tokens ~10× cheaper on Claude Sonnet ($0.30 vs $3.00/MTok). |
| Agent behavior drifts or contradicts earlier decisions | Check for compaction-induced governance decay. Aggressive summarization systematically drops abstract constraints—safety rules and behavioral guardrails summarize away as 'less essential' than concrete facts, silently eroding compliance. Aggregators attribute ~65% of 2025 enterprise agent failures to drift rather than raw exhaustion. |
| Long-horizon tasks (>1,000 steps) show performance cliff | Test with BEAM or MemoryAgentBench to isolate temporal reasoning and selective-forgetting regressions. Long-horizon stability is the least-measured axis in prior benchmarks; production agents run months/thousands of sessions. |
| Multi-agent system shows conflicting decisions or contradictory actions | Audit sub-agent isolation boundaries. Parallel subagents carry conflicting implicit decisions; actions encode choices that summaries drop. Require full-trace sharing where decisions interlock, or reduce parallelism. |

## Key gotchas

- **Loss of subtle-but-critical context.** Aggressive compaction discards details whose importance only becomes apparent later, eroding decision quality on long horizons. Anthropic tuning guidance: maximize recall first (capture everything relevant), then iterate on precision (strip superfluous).

- **Causal-structure destruction.** Summarization collapses explicit tool-call chains into narrative, erasing provenance and causing agents to re-derive or contradict earlier decisions. Preserve architectural decisions, unresolved bugs, and implementation details in compaction; discard only redundant tool outputs.

- **Governance decay.** Compaction systematically drops abstract constraints—safety rules and behavioral guardrails summarize away as 'less essential' than concrete facts, silently eroding compliance. Aggregators attribute ~65% of 2025 enterprise agent failures to drift rather than raw exhaustion.

- **Context drift.** Compressed summaries introduce rewording that shifts task framing; repeated compaction compounds it. Non-determinism in summarization achieves 90–99% token reduction with no consistency guarantee across runs—same trajectory, different surviving facts.

- **Staleness poisons retrieval by default.** Without a maintenance/forgetting layer, stale records gradually dominate top-k results; memory quality decays over months unless staleness is actively tracked and pruned. Staleness must be tracked as rate, not assumption.

- **Multi-agent implicit-decision loss.** Parallel subagents carry conflicting implicit decisions; actions encode choices that summaries drop, requiring full-trace sharing where decisions interlock. Isolation works only when subtask is high-volume/low-relevance and read-only-ish.

- **Effective context is 50–65% of advertised window.** RULER cross-checks and NoLiMa (arXiv 2502.05167, ICML 2025) show most models claiming ≥128K context drop below 50% of their own short-context baseline at 32K tokens. Plan for degradation, not advertised capacity.

## Empirical anchor

Context engineering is now quantifiable. Chroma Context Rot study (July 2025) tested 18 frontier models on NIAH, LongMemEval, repeated-words; every model degraded with input length even on trivial tasks; shuffled haystacks beat coherent ones across all 18, indicating attention bottleneck. Lost-in-the-middle (Liu et al., 2023, TACL) showed U-shaped position curve; accuracy drops 30+ points when relevant document sits mid-context in multi-document QA. LongMemEval (arXiv 2410.10813, ICLR 2025) reported commercial assistants and long-context LLMs show 30% accuracy drop memorizing information across sustained interactions; 30–60% below oracle retrieval on 115k-token histories.

Architectural interventions are measurable. Anthropic internal evals (Sept 2025) showed memory tool + context editing = +39% over baseline on agentic search; context editing alone = +29%. Anthropic Code execution with MCP (Nov 2025) dropped workflow tool-definitions-plus-intermediate-results load from 150,000 → 2,000 tokens (98.7% reduction); community replication achieved 112 tools while holding ~98% token reduction. Anthropic context editing (Sept 2025) enabled agents to finish otherwise-impossible 100-turn web-search workflows while cutting token consumption 84%. Anthropic multi-agent research system (internal evals) showed Opus-4-lead + Sonnet-4-subagents outperformed single-agent Opus by 90.2% on internal research evals; token usage alone explained ~80% of performance variance; multi-agent burns ~15× more tokens than chat.

Memory systems show consistent gains. Mem0 vs. baselines on LoCoMo (arXiv 2504.19413, 2025) achieved 66.9% LLM-judge score vs. OpenAI memory 52.9% (+26% relative); full-context stuffing scored 72.9% (memory lost 6% accuracy vs. oracle while cutting p95 latency 91% and tokens 90%). Zep temporal knowledge graph (arXiv 2501.13956, Jan 2025) achieved +15.2% (gpt-4o-mini) / +18.5% (gpt-4o) accuracy over full-context baseline with ~90% latency reduction and <2% of baseline tokens. BrainMem (2026) showed stepwise adding working/episodic/semantic memory lifts embodied task planning 64.0% → 76.0%. BEAM (ICLR 2026, arXiv 2510.27246) tested 100 conversations up to 10M tokens with 2,000 probing questions; ~25% performance loss going 1M → 10M; temporal queries hardest. Are We Ready For An Agent-Native Memory System? (arXiv 2606.24775, 2026) evaluated 12 memory systems + 2 baselines across 5 workloads/11 datasets with per-module ablations quantifying representation fidelity, retrieval precision, update correctness, and long-horizon stability. MemoryAgentBench (2026) surfaces memory-construction cost (Mem0/Cognee/MemGPT resource-heavy at small chunk sizes) and selective-forgetting competency as regression probe for continual-learning evaluation gap.

Production metrics converge on a four-layer stack: Layer 1 task effectiveness (success rate / accuracy with memory on vs. off); Layer 2 memory quality (retrieval precision/recall, contradiction rate, staleness rate/distribution, coverage, update correctness); Layer 3 efficiency (tokens/query, p50/p95 latency, construction cost); Layer 4 governance/drift monitoring (storage overgrowth, retrieval-quality degradation, stale-content dominance, pruning regret). Mem0 reports ~1.8–6.9K tokens/query vs. ~26K full-context. Manus KV-cache metric (July 2025) shows agent input:output ratio ~100:1; cached tokens ~10× cheaper on Claude Sonnet ($0.30 vs $3.00/MTok). Regression gating for learned behavior—after every memory/skill update, re-run frozen suite of previously-passing tasks; ship update only if old capabilities hold—is now standard practice; 2026 position is improvement and regression analysis belong in same optimization step (RELAI).

Origin: Synthesized from Chroma Context Rot (July 2025), NoLiMa (arXiv 2502.05167, ICML 2025), Lost-in-the-middle (Liu et al., 2023, TACL), LongMemEval (arXiv 2410.10813, ICLR 2025), Anthropic internal evals (Sept–Nov 2025), Mem0 vs. baselines on LoCoMo (arXiv 2504.19413, 2025), Zep temporal knowledge graph (arXiv 2501.13956, Jan 2025), Are We Ready For An Agent-Native Memory System? (arXiv 2606.24775, 2026), BrainMem (2026), BEAM (ICLR 2026, arXiv 2510.27246), Manus KV-cache metric (July 2025), and RULER cross-checks.
