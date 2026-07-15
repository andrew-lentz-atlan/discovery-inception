---
title: Memory Retrieval Policy: Scoring, Injection, and Gating
category: skill-design
status: draft
last_updated: 2026-07-15
source_findings: []
source_external:
  - Chroma Context Rot (July 2025)
  - Lost in the Middle (Liu et al., Stanford 2023/TACL 2024)
  - LongMemEval (arXiv 2410.10813, Oct 2024)
  - Experience-following (arXiv 2505.16067, ACL 2026)
  - MemoryAgentBench (arXiv 2507.05257, ICLR 2026)
  - Mem0 paper (arXiv 2504.19413, Apr 2025)
  - Zep paper (arXiv 2501.13956, Jan 2025)
  - Anthropic context management (Sept 29, 2025)
  - Generative Agents (Park et al., UIST 2023)
  - On the Structural Memory of LLM Agents (arXiv 2412.15266)
  - Memanto (arXiv 2604.22085)
  - TARG (arXiv 2511.09803)
  - Adapt-LLM (arXiv 2404.19705)
applies_when:
  workloads:
    - long-lived-agent-with-persistent-memory
    - multi-turn-iterative-retrieval
    - multi-user-scoped-memory
    - high-traffic-assistant-with-cost-constraints
    - temporal-or-entity-centric-queries
  constraints:
    - context-rot-risk-high
    - token-budget-constrained
    - retrieval-latency-measurable
    - memory-must-be-scoped
    - facts-needed-on-most-turns
contradicts: []
related:
  - decision-guides/does-this-agent-need-memory
  - decision-guides/memory-architecture-selection
  - skill-design/memory-operations
  - decision-guides/cost-vs-latency-tradeoffs
  - anti-patterns/silent-tool-fallback
source_hash: 526b622ca4997f84
---

# Memory Retrieval Policy: Scoring, Injection, and Gating

Memory retrieval policy—what enters context, when, and how much—dominates storage backend choice for agent memory quality. Four independent lines of evidence show that focused injection policies, scored recall combining relevance + recency + importance, two-tier architectures with always-loaded cores, and retrieval gating consistently outperform naive top-k semantic search, even on identical storage systems. The pattern covers seven operational decisions: scored recall, two-tier injection, agent-directed vs harness-injected retrieval, scoped namespacing, hybrid retrieval + reranking, gating, and token budgeting. Retrieval policy matters more than storage backend; the same vector database yields vastly different quality depending on how memories are scored, filtered, and injected into context.

## Use when

- Building a long-lived agent where pure semantic similarity retrieves stale or trivial memories over recent updates.
- Multi-turn or agentic tasks where the model can iterate: search → read → refine (agent-directed retrieval).
- Multi-user or multi-project systems where memory must be scoped to prevent cross-cutting leakage and improve recall quality.
- High-traffic assistants where retrieval cost matters and retrieved memories act as demonstrations (gating blocks error propagation).
- Any persistent agent where facts needed on most turns should stay always-loaded, and everything else earns its way in per-query.
- Systems where temporal questions ('what did I say before X changed?') or entity-centric questions matter—pure vectors fail both.

## Don't use when

- Stateless, single-turn tasks where context rot and over-injection are not concerns.
- Latency budgets forbid extra round trips (use harness-injected retrieval with a budgeted core instead of agent-directed tool calls).
- Models are weak at tool use and cannot reliably invoke memory search functions.
- Memory has no natural temporal or entity structure; file-based or structured lookup adds no value over pure embeddings.

## Key gotchas

- **Relevance-only top-k is the failure default.** It happily surfaces a 6-month-old contradicted preference over yesterday's update; recency must be a first-class retrieval signal, not a post-hoc tiebreak.
- **Importance scored once at write time goes stale.** Refresh it via access frequency or periodic consolidation (Letta's sleep-time compute, LangMem background jobs).
- **Unbounded always-injected core tier.** The core memory grows without bound unless capped (Letta enforces fixed size; harness patterns need an explicit line/token cap plus periodic consolidation). Uncapped 'profile' sections are the most common over-injection source in production.
- **Agent-directed retrieval adds turns and depends on model behavior.** Weak models under-retrieve; harness-injected retrieval silently over-injects because nothing pushes back on k.
- **Over-narrow scopes hide cross-cutting facts.** User preferences learned in project A apply in project B; keep a user-global scope above project scopes.
- **Rerankers add latency.** LLM-heavy search measured at p50 17.99s / p95 59.82s is impractical for interactive use; keep LLM calls out of the hot retrieval path; do LLM work at write/consolidation time instead.
- **Logit-based gates need logprob access.** Popularity gates need an entity linker; all gates need a monitored escape hatch (user says 'remember when…' → force retrieval).
- **Budget the memory block, not the whole prompt.** Memory competes with system prompt, tool schemas, and history; every retrieved token evicts a token of something else. Fixed k without a token cap fails when memories vary in length.
- **Trusting vendor benchmark deltas.** The LoCoMo dispute shows scores are a function of retrieval config + judge setup; rerun on your own traces.
- **No abstention path.** A memory system that can't say 'nothing relevant stored' fabricates continuity; LongMemEval treats abstention as a first-class ability because assistants fail it.

## Empirical anchor

Lost in the Middle (Liu et al., Stanford, 2023 / TACL 2024) established the U-shaped position curve: >30% accuracy degradation when relevant documents sit mid-context; ~20 retrieved documents (~4k tokens) can drop QA accuracy from 70–75% to 55–60%. LongMemEval (Oct 2024) measured 500 questions over chat histories and found commercial assistants show ~30% accuracy drop on sustained interactions; GPT-4o fell from 91.8% (offline) to 57.7% (online memory). Chroma's Context Rot study (July 2025, 18 models including Claude 4, GPT-4.1, Gemini 2.5) showed focused ~300-token prompts vastly outperformed full ~113k-token prompts; lower needle–question similarity correlated with steeper degradation as context length grew. Experience-following (ACL 2026) demonstrated that retrieved memories act as demonstrations and erroneous stored experiences propagate into future tasks; selective addition + deletion policies yielded +10% absolute average gain over naive memory growth. Mem0 (Apr 2025) achieved +26% relative improvement vs OpenAI's memory with 91% lower p95 latency (1.44s vs 17.12s) and >90% token savings; the graph variant added only +2% over the base retrieval policy, showing storage backend upgrades bought far less than retrieval and extraction policy tuning. Zep (Jan 2025) achieved +18.5% accuracy and −90% latency on LongMemEval vs full-context with an LLM-free hot path at p95 ~300ms. The LoCoMo score dispute (2025) revealed the same systems measured at 58.44%–75.14% depending on retrieval config and eval methodology, underscoring that benchmark deltas are a function of policy, not just backend. Anthropic's context management work (Sept 29, 2025) showed memory tool + context editing yielded +39% on agentic search evals; on a 100-turn web-search task, clearing stale tool results cut token consumption 84% and let runs finish that otherwise died of context exhaustion. Generative Agents (Park et al., UIST 2023) established the canonical scoring policy: score = α_rel · relevance + α_rec · recency + α_imp · importance, with recency using exponential decay 0.995/hour on last-retrieval time, not creation time. Retrieval gating (TARG, arXiv 2511.09803) triggered only when mean token entropy or logit margin exceeded threshold from short draft prefix, and Adapt-LLM (arXiv 2404.19705) showed learned abstention tokens beat always-retrieve and never-retrieve baselines. Simple popularity/frequency gates (Mallen et al.) achieved ~15% cost reduction for GPT-3 at equivalent quality; pre-generation classifiers using 27 cheap features retrieved/skipped at <1% of total FLOPS with comparable QA performance, often outperforming complex purpose-built adaptive-RAG pipelines.

Origin: Composite pattern from Mem0, Zep, Letta, LangMem, and Anthropic memory work; validated across LongMemEval, MemoryAgentBench, and LoCoMo benchmarks (2024–2026).
