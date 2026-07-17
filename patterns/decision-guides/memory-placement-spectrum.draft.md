---
title: Memory placement spectrum — resident, stored, or referenced
category: decision-guides
status: draft
last_updated: 2026-07-16
source_external:
  - Anthropic — "Effective context engineering for AI agents" (https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
  - Anthropic — "Memory tool" docs (https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
  - Anthropic — "Claude Code best practices" (CLAUDE.md guidance) (https://code.claude.com/docs/en/best-practices)
  - Packer et al. — "MemGPT: Towards LLMs as Operating Systems" (arXiv:2310.08560)
  - Letta — "Memory blocks" / "Archival memory" docs (https://docs.letta.com/guides/core-concepts/memory/memory-blocks, https://docs.letta.com/guides/core-concepts/memory/archival-memory)
  - Hong, Troynikov, Huber — "Context Rot" (Chroma, July 2025, https://research.trychroma.com/context-rot)
  - Liu et al. — "Lost in the Middle" (TACL 2024, arXiv:2307.03172)
  - Modarressi et al. — "NoLiMa: Long-Context Evaluation Beyond Literal Matching" (ICML 2025, arXiv:2502.05167)
  - Wu et al. — "LongMemEval" (ICLR 2025, arXiv:2410.10813)
  - Labruna et al. — "Adapt-LLM: When to Retrieve" (arXiv:2404.19705)
  - Wang et al. — "TARG: Training-Free Adaptive Retrieval Gating" (arXiv:2511.09803)
  - Yichao Ji — "Context Engineering for AI Agents: Lessons from Building Manus" (https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
  - Redis — "AI agent context engine FAQ: RAG, memory & caching" (https://redis.io/blog/faq-real-time-context-engine-agent-memory-and-retrieval/)
  - Sumers, Yao, Narasimhan, Griffiths — "Cognitive Architectures for Language Agents (CoALA)" (arXiv:2309.02427)
applies_when:
  workloads: [any]
  constraints: [memory-kind-already-decided, per-fact-placement-decision]
contradicts: []
related:
  - decision-guides/does-this-agent-need-memory
  - decision-guides/memory-architecture-selection
  - skill-design/memory-operations
  - anti-patterns/memory-as-shadow-copy
snapshot_date: 2026-07-16
---

# Memory placement spectrum — resident, stored, or referenced

The sibling memory guides decide *whether* an agent needs memory and which kind (`does-this-agent-need-memory.md`), *which store* to build it on (`memory-architecture-selection.md`), and *how to operate it* (`memory-operations.md`). All three operate at the agent level. This entry operates at the **fact level**: for each category of fact the agent uses, placement is a three-position decision, and the positions have opposite failure modes. A memory design that names a kind and a tool but never places its facts has skipped the decision this entry forces.

| Position | What it is | Cost | Failure mode |
|---|---|---|---|
| **1. Resident** | Always loaded into context — standing "fact" the agent never has to look up (system-prompt facts, CLAUDE.md-style index, MemGPT/Letta core memory blocks) | Taxes the attention budget of **every turn of every session**, whether used or not | Context rot: bloated resident sets degrade instruction-following on everything else |
| **2. Stored** | Persisted in a memory store; retrieved on demand (archival memory, memory-tool files, vector recall — "check your memory for whether X happened") | Free until needed; pays a retrieval step at use time | Retrieval failure: the agent doesn't look, or looks and misses — an empirically large risk by default |
| **3. Referenced** | Not persisted at all; fetched live from the system of record via tool/API at use time. Only the pointer (GUID, URL, query) is stored | Latency + availability of the upstream system per use | Upstream dependency: no offline operation, per-use latency, rate limits |

The one-line trade between positions 1 and 2: a resident fact costs attention on every turn (Context Rot: ~300-token focused prompts beat ~113k-token full prompts containing the same relevant information, across 18 frontier models) but has ~100% availability; a stored fact is free until needed but arrives with a retrieval-failure probability that is large by default (LongMemEval: ~30% accuracy drop for online memory vs. having the information present) and shrinks only with deliberate engineering. The trade between positions 2 and 3 is ownership of truth: a stored fact is a snapshot that rots; a referenced fact is always current but couples the agent to the upstream system. See `anti-patterns/memory-as-shadow-copy.md` for the position-2-instead-of-3 failure.

---

## Boundary 1: resident vs. stored

A fact earns **resident** status when it scores high on most of:

1. **Cross-task frequency** — needed in most sessions, not just some. Anthropic's CLAUDE.md rule ("only information that applies broadly") and Letta's memory-block criterion ("should always be visible") converge here independently. *(Vendor consensus.)*
2. **Criticality of omission** — a miss causes silent wrong behavior (a safety rule, a tenant URL, "never do X") rather than a recoverable gap. Given default retrieval-failure rates, must-never-miss facts are unsafe in the stored tier. *(Empirical: LongMemEval abstention/knowledge-update weakness.)*
3. **Non-obvious relevance** — nothing on the task surface would cue a lookup. Models measurably fail at knowing what they don't know (Adapt-LLM had to train a dedicated retrieval token to get a usable when-to-look policy), so a fact with no lexical/semantic trigger will not be fetched. *(Empirical — with the caveat that NoLiMa shows residency only mitigates non-obvious relevance, it does not solve it.)*
4. **Small and stable** — fits a capped block and rarely changes. Stability matters doubly: churn invalidates the KV cache (cached input tokens run ~10x cheaper than uncached — Manus), so a *stable* resident prefix is nearly free per-turn while a *churning* one is expensive. *(Cache economics: hard pricing fact. Size ceilings ~500 tokens / ~200 lines: community folklore, directionally consistent with Context Rot.)*
5. **Gating/steering role** — the fact changes *how the agent proceeds* (a workflow rule, a verification protocol) rather than supplying content. *(Vendor practice.)*

Everything else defaults to **stored**: large or unbounded content (histories, logs, reference corpora), cold/episodic facts needed in a minority of sessions, self-cueing facts (the task itself will contain the trigger), and anything re-derivable from a pointer.

**The gate-is-resident pattern.** The two positions compose: keep the *facts* stored, but make the *instruction to check* resident and unconditional. Anthropic's memory tool does exactly this — the facts live in `/memories` files, but the API injects a standing system-prompt directive to always view the memory directory before doing anything else. A skill of the form "check your memory for whether X happened before answering" is this pattern; its reliability comes from being unconditional, because "check memory when it seems relevant" inherits the model's measurably poor when-to-look judgment. Where an unconditional check is too expensive, gate on an explicit signal (TARG-style uncertainty gating matched always-retrieve accuracy with 70–90% fewer retrievals) — never on unaided model judgment.

**Residency is necessary but not sufficient.** A resident fact parked mid-context can be functionally invisible (Lost in the Middle: >30% accuracy degradation for mid-context position). High-stakes standing facts belong at the prefix (cache-friendly) or get re-recited near the suffix (the Manus todo.md recitation pattern) — or both.

**The boundary is dynamic, not design-time.** MemGPT/Letta treat promotion and demotion between tiers as a runtime or background (sleep-time) process under memory pressure. A fact can earn residency through observed use and lose it through disuse; the placement table in a design is the initial assignment, not a constant.

## Boundary 2: stored vs. referenced

Before any fact enters the stored tier, it must pass the **storability gate** (operationalized in `memory-operations.md`'s write policy):

1. **Does a queryable system of record exist for it?** → **Referenced.** Store the pointer (GUID, URL, saved query), fetch the content at use time. A stored copy of record-owned state is the shadow-copy anti-pattern.
2. **Is the fact volatile relative to session frequency?** → **Referenced** (or not kept at all), even without a clean system of record. A fact that changes faster than the agent sessions that would consume it is a tool call, not a memory.
3. **Is it stable AND either expensive to re-derive or underivable in principle?** → **Stored.** This is memory's comparative advantage: conclusions, decisions and their rationale, corrections, preferences, hard-won procedural insights. CoALA formalizes the distinction — writing to memory is a *learning* action; grounding/tool-use is *interacting with the environment* — two different action classes for two different kinds of fact.

**The middle case: slow-moving reference data.** Content fetched repeatedly but owned upstream (policy documents, glossary definitions, schema descriptions) is neither memory nor a per-use fetch — it is an **explicit cache**, and it must be declared as one: a TTL or invalidation trigger, a named owner, and bypass logic for anything fast-changing (Redis: semantic caching is "an optimization layer, not a source of truth"). The shadow-copy failure is precisely this category dumped into the memory store *without* the cache discipline. A bi-temporal store (Zep/Graphiti — see `memory-architecture-selection.md`) is the heavyweight version of the same discipline: a managed local copy with fact invalidation, justified when latency or point-in-time reasoning is load-bearing.

---

## Hard rules for inception

1. **A memory design places its facts.** For each fact category the design names, it assigns resident / stored / referenced with a one-line reason. A design whose memory section names kinds and tools but no placements is incomplete.
2. **Resident sets are budgeted.** The design states what is always-loaded and why each line survives the pruning test ("would removing it cause mistakes?"). An unbounded resident set is flagged.
3. **Stored facts name their retrieval trigger.** Unconditional check at a defined point, or an explicit gate. "The agent will check when relevant" is rejected as a trigger.
4. **Referenced facts name the pointer and the tool.** "Fetched from X" requires that a tool to fetch from X actually exists in the design; otherwise the fact silently regresses to stored.
5. **Anything cached from an upstream owner declares TTL + owner + bypass.** A copy without invalidation discipline is sent back as shadow-copy.

## Empirical anchor

- Residency tax: Context Rot (Chroma, July 2025, 18 models); NoLiMa (11 of 13 models below 50% of short-context baseline at 32K tokens on non-lexical matching); Lost in the Middle (U-shaped position curve). **Strong.**
- Retrieval risk: LongMemEval (~30% online-vs-offline gap; abstention among the weakest tested abilities); Adapt-LLM (native when-to-retrieve judgment is poor; a learned policy beats always/never-retrieve); TARG (explicit gating recovers always-retrieve accuracy at 70–90% fewer calls). **Strong.**
- Cache economics of stable prefixes: ~10x cached/uncached input-token pricing spread (Manus, published rates). **Hard fact.**
- The small-resident-kernel + on-demand-everything hybrid: Anthropic, Letta, and Manus landed on it independently. **Convergent vendor practice, not controlled evidence.**
- Known gap (as of 2026-07): no published source directly A/B-tests the *same fact* resident vs. stored in an agentic setting; the rubric triangulates residency-cost studies and retrieval-failure studies measured separately. LongMemEval's offline-vs-online contrast is the closest proxy.
