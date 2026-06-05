---
title: Operating agent memory well — the write/retrieve/forget/consolidate lifecycle
category: skill-design
status: draft
last_updated: 2026-06-03
source_external:
  - Anthropic — "Memory tool" (https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool) — progress-log pattern, expiry/size-cap/path-traversal/PII guidance, compaction pairing
  - Anthropic — "Effective context engineering for AI agents" (https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — just-in-time retrieval, context budget
  - Mem0 — "Add memory / memory operations" (https://docs.mem0.ai/core-concepts/memory-operations/add) — extraction phase + ADD/UPDATE/DELETE/NOOP decision cycle, overwrite conflict resolution
  - Mem0 — "State of AI Agent Memory 2026" (https://mem0.ai/blog/state-of-ai-agent-memory-2026) — eval stack, LoCoMo/LongMemEval/BEAM benchmarks, async-write/rerank operational patterns, staleness gap
  - LangChain — "Semantic search for LangGraph long-term memory" (https://blog.langchain.com/semantic-search-for-langgraph-memory/) + LangGraph persistence docs — store semantic search, TTL eviction
  - Rasmussen et al. — "Zep: A Temporal Knowledge Graph Architecture for Agent Memory" (https://arxiv.org/abs/2501.13956) — bi-temporal invalidation
  - "Episodic Memory is the Missing Piece for Long-Term LLM Agents" (arXiv:2502.06975) — encode/retrieve/consolidate/evict stages; consolidation as the load-bearing, least-implemented stage
  - "Memory Poisoning Attack and Defense on Memory-Based LLM Agents" (arXiv:2601.05504); MemoryGraft (arXiv:2512.16962); MINJA — persistent poisoning via the write path
  - "Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers" (arXiv:2603.07670) — four-layer eval stack (precision/recall, contradiction rate, staleness distribution, coverage)
applies_when:
  workloads: [any-agent-with-memory]
  constraints: [memory-in-the-design]
contradicts: []
related:
  - decision-guides/does-this-agent-need-memory
  - decision-guides/memory-architecture-selection
  - anti-patterns/silent-tool-fallback
  - harnesses/langgraph-deep-dive
snapshot_date: 2026-06-03
---

# Operating agent memory well — the write/retrieve/forget/consolidate lifecycle

Picking the right memory store is necessary but not sufficient. A correctly-chosen store operated badly degrades the agent it was supposed to help: stale facts surface with full confidence, the context fills with low-relevance recall that crowds out reasoning, contradictions persist because nobody decided what to do when new info disagrees with old. Memory that isn't *operated* is a liability that looks like an asset — it has the shape of knowledge without the freshness, precision, or bounds that make knowledge useful.

This entry is the third layer. The sibling decision guides answer **whether** memory is needed and **what kind** (`does-this-agent-need-memory.md`), and **what architecture/tooling** to build it on (`memory-architecture-selection.md`). Both defer here for the part neither covers: **given that you need memory of kind X on tool Y, how do you operate it well?** The lifecycle (write → retrieve → forget → consolidate), conflict resolution, evaluation, and the operational failure modes. It does not redefine the memory kinds (read the first sibling for those) or re-survey the tools (read the second). It assumes both are settled and asks the next question.

The framing that holds the entry together: **a memory store with no operational policy is an incomplete design**, the same way a tool-using agent with no failure-surfacing is incomplete (`anti-patterns/silent-tool-fallback.md`). "Use mem0" is not a memory design. "Use mem0; write on reflection at task boundaries; retrieve top-5 reranked above 0.75 similarity; evict by 30-day TTL plus salience; consolidate episodic→semantic nightly" is.

---

## The memory lifecycle — four operations

Memory is not a database you write once and read forever. It's a loop with four operations, each of which has a best practice and a specific failure if you skip it. The research framing (arXiv:2502.06975) names four stages for episodic memory — **encode, retrieve, consolidate, evict** — and the same four generalize across kinds. Treat each as a policy you must name, not a default you inherit.

### 1. Write — what to persist, and when

**The decision is *what* is memory-worthy and *when* the write fires.** Three timing policies, in increasing selectivity:

- **Write-on-every-turn** — persist after each exchange. Highest recall, highest noise, highest cost; every turn pays an extraction tax. Rarely right outside short sessions.
- **Write-on-reflection** — at a boundary (task complete, session end, a "what did I learn" checkpoint), the agent reflects and extracts the salient facts/decisions/outcomes. This is the default for durable memory: it batches the extraction, filters noise, and matches how the Anthropic memory tool's end-of-session progress-log pattern works ("record status / progress / thoughts ... ASSUME INTERRUPTION").
- **Write-on-event** — only on a defined trigger (a correction, a decision, a state change, an explicit "remember this"). Highest precision, lowest noise; the right policy for entity/profile memory where most turns change nothing.

**What's worth persisting:** salient facts, decisions, outcomes, corrections, stable preferences, new entities. mem0's extraction phase makes the cut explicit — it prompts an LLM to distill messages into "key facts, decisions, or preferences," triggering on user preferences/feedback, decisions, completed goals, new entities, and clarifications. **What is noise:** transient conversational filler, intermediate scratch the agent won't need again, anything reconstructable from a tool on demand. The extraction step *is* the quality gate — the agent deciding what's memory-worthy is itself an LLM judgment, and its precision bounds everything downstream.

> **Async by default.** The 2026 state-of-memory survey lists async writes as the first production pattern: extraction is an LLM call, and doing it on the request path adds latency to every turn. Run the write out of band (LangMem's "background" manager, mem0's async add) unless the agent must act on what it just learned *within the same session* — then hot-path write is justified, at a token/latency cost.

**Failure if skipped:** no write policy means write-on-every-turn-by-accident (a memory layer that auto-extracts from every message) or never-write (the store exists but stays empty because nothing triggers a write). The first floods the store with noise; the second is failure-mode-B from the first sibling — the memory you built but never populated.

### 2. Retrieve — relevance, recency, and how *much*

Retrieval has two knobs and a budget. The knobs: **relevance** (semantic similarity to the current query) and **recency** (how fresh). The budget: **how much recall you inject into context.**

- **Rank by relevance *and* recency, not similarity alone.** A vector store gives you nearest-neighbors; nearest is not most-useful. The 2026 patterns put a **reranking layer** on the candidate set as standard, and the Atlan build-a-memory-layer guidance is explicit: "combine TTL-based expiration with recency scoring in retrieval — do not rely on TTL alone." Pure-similarity retrieval is the #1 silent failure of the RAG rung (see retrieval drift below).
- **Set a relevance floor.** Returning the top-k regardless of score means low-similarity hits get treated as facts. Threshold the similarity (e.g. drop below ~0.7–0.75, tuned per embedding model) and return *fewer, better* memories — including zero when nothing clears the bar.
- **Inject less than you can.** This is the counterintuitive one: more recall is its own failure. Anthropic's context-engineering guidance frames memory as **just-in-time retrieval** — "store what you learn, pull it back on demand, keep the active window focused" — precisely because dumping all recall into context degrades reasoning (over-injection, below). Budget a token allotment for retrieved memory per turn and stay under it.
- **Formulate the query deliberately.** The retrieval query is not always the raw user turn. For episodic recall, query on the *task* ("prior outreach to account X"), not the user's phrasing. mem0's newer pipeline uses **hybrid retrieval** (semantic + keyword + entity signals) precisely because pure-embedding queries miss exact-match facts (IDs, names, dates).

**The precision/recall tension:** tightening the floor and shrinking k raises precision (fewer wrong memories) at the cost of recall (you might miss a relevant one). Loosening does the opposite. There is no universal setting — it's a tuned tradeoff, which is exactly why you measure it (see Evaluating memory).

**Failure if skipped:** no retrieval policy means "top-k by cosine, k hard-coded, no floor, dump it all in." That is the configuration that produces retrieval drift and context bloat simultaneously.

### 3. Forget / evict / decay — unbounded memory is a bug

**Unbounded memory is not a feature; it is a defect with two bills: cost/latency (the store and the retrieval grow forever) and retrieval noise (more old entries means more chances to surface the wrong one).** A store that only grows monotonically degrades its own precision over time — the survey calls this out directly: "the inability to discard outdated information gradually poisons retrieval precision."

Three eviction mechanisms, usually combined:

- **TTL / expiry** — drop entries older than a window. LangGraph's store integrates TTL (e.g. MongoDB TTL indexes) for automatic removal of stale items; the Anthropic memory-tool docs literally suggest "clearing out memory files periodically that haven't been accessed in an extended time." TTL alone is blunt (a 6-month-old preference may still be true) — pair it with recency-weighted retrieval rather than relying on it to define truth.
- **Salience-based eviction** — keep what's been retrieved/used, drop what never gets touched. A memory written once and never read in N retrievals is dead weight; evict it. This is the operational version of the first sibling's tell ("a memory written to but whose contents never change a decision").
- **Warm/cold tiering** — don't hard-delete; demote. Move rarely-touched memories from a warm searchable tier to a cold archive (MemGPT/Letta recall→archival; the warm/cold split "enables compliance archiving without polluting active retrieval"). Cold storage keeps the audit trail and the right-to-recall without taxing every live query.

**Failure if skipped:** the store grows without bound. Costs climb, P95 latency climbs, and — worse — retrieval precision *falls* because every query now competes against a larger pile of stale candidates. Hoarding is not conservative; it actively degrades the agent.

### 4. Consolidate — summarize, merge, dedup, promote

Consolidation is the operation teams most often skip and the one the research calls most important. arXiv:2502.06975 argues episodic reflection and consolidation — "converting past events into compact, reusable representations" — is the key mechanism for long-term reasoning: **agents get smarter not by storing more, but by consolidating what they store.** The Atlan episodic-memory write-up is blunter — consolidation is "the most important and the least implemented" stage.

Four consolidation moves:

- **Rolling summarization / compaction** — compress old turns/episodes into a summary so the detail's *gist* survives without its token cost. Anthropic's compaction (server-side summarization near the window limit) pairs with the memory tool so "nothing critical is lost in the summary." The gotcha: summaries lose detail silently — the agent "forgets" a fact it summarized away. Consolidate the *low-salience* tail, not the load-bearing specifics.
- **Fact merging / dedup** — collapse "user prefers SQL" stated five times into one fact. mem0's ADD/UPDATE/DELETE/NOOP cycle does this on write: it semantically searches existing memories and lets the LLM decide whether the new candidate is new (ADD), a refinement (UPDATE), obsolete (DELETE), or redundant (NOOP) — dedup at write time, not read time.
- **Periodic compaction** — a scheduled background pass that re-summarizes, merges, and prunes the whole store (LangMem's background manager, Letta's sleep-time consolidation). Cheaper and more coherent than ad-hoc per-turn edits.
- **Promoting episodic → semantic** — the highest-value move. When the same outcome recurs across episodes ("contacting accounts on Fridays gets replies"), promote the *pattern* from episodic memory (what happened, timestamped) into semantic/procedural memory (what is true / the right way). This is the mechanism behind any "the agent improves over time" claim — and if the design promises learning, this promotion path is the thing it must actually specify.

**Failure if skipped:** the store accretes near-duplicates and raw episodes forever. Retrieval returns five phrasings of the same fact (wasting budget), contradictions sit side by side unresolved, and the "learns over time" promise never materializes because nothing ever gets distilled.

---

## Conflict resolution — when new info contradicts stored memory

The write path's hardest decision: the new fact disagrees with a stored one. Three strategies, each right in different cases:

- **Overwrite** — replace the old fact with the new. Simple, cheap, keeps the store small. **mem0 overwrites** — its update phase resolves conflicts so "the latest truth wins," updating the existing record rather than appending a duplicate. Right when only the *current* truth matters and you'll never ask "what did we believe last month?" (preferences, current status, profile fields).
- **Version** — keep the old fact, append the new, mark which is current. Right when you want an audit trail of how a fact changed but don't need point-in-time *query* ("show me the history of this account's owner").
- **Bi-temporal ("what was true when")** — record both *when the fact was valid* and *when you learned it*, and invalidate (don't delete) superseded facts. **Zep/Graphiti is bi-temporal** — every fact edge carries validity-start and validity-end, old facts are invalidated not deleted, and you can query "what was true at time T." Right when temporal reasoning is load-bearing ("the contact moved from company A to B in March; for a query about February, A is correct").

The selection rule: **overwrite is the default; escalate to versioning when you need history, to bi-temporal when you need to *query* history at a point in time.** Don't stand up a temporal graph to remember "prefers dark mode" — that's the over-reach the architecture-selection sibling warns about. But equally, don't overwrite in a domain where last month's truth is still a valid question (compliance, account history, anything auditable) — silent overwrite there is a data-loss bug.

The redline that cuts across all three: **never let untrusted input write to a privileged memory namespace** without validation. Conflict resolution assumes the new fact is trustworthy; if an attacker controls the write path, "latest truth wins" means "attacker's fact wins" (see Memory poisoning).

---

## Evaluating memory — is it helping or hurting?

This is the part teams skip, and it's why staleness and poisoning ship undetected. A memory store has no built-in signal that it's *helping*; you have to wire one. The 2026 memory-eval research converges on a layered stack — make it concrete:

**Memory-quality metrics (measure the store itself):**
- **Retrieval precision** — of the memories injected this turn, what fraction were actually relevant? Low precision = retrieval drift / over-injection.
- **Retrieval recall** — of the memories that *would have* helped, what fraction were retrieved? Low recall = floor too tight or k too small.
- **Contradiction rate** — what fraction of the store contains mutually contradictory facts? Rising = conflict resolution is failing.
- **Staleness distribution** — age profile of retrieved memories; a long stale tail means decay/eviction isn't working. The survey's failure phrase to test against: "high-relevance memories become confidently wrong."
- **Coverage** — of the facts a task needs, what fraction does the store hold at all?

**Task-effectiveness metrics (measure the agent with vs without memory):**
- **With-vs-without A/B** — run the eval suite twice, memory on and memory off. If scores don't *rise* with memory on, the memory isn't earning its cost (failure-mode-A from the first sibling — the store nobody reads usefully). If they *fall*, memory is actively hurting (over-injection or poisoning). This single experiment is the highest-value memory eval you can run, and almost nobody runs it.
- **Benchmark anchors (cite cautiously):** LoCoMo (1,540 Qs: single/multi-hop, temporal recall), LongMemEval (500 Qs: knowledge updates, multi-session), BEAM (1M–10M-token scale). As of mid-2026 top systems report ~92–94 on LoCoMo/LongMemEval at ~6,900 tokens/query — useful as a sanity ceiling, not a target; your domain's recall is what matters.

**Wire it into the eval/judge harness.** This ties directly to how our eval seed and judge work. The judge already scores grounding (silent-tool-fallback's claims-vs-traces dimension); memory adds two dimensions on the same trace:
- **Regression tests for poisoning** — plant a known-false fact in the store, run the suite, assert the agent does *not* surface it as truth. A standing poisoning regression catches the failure that otherwise persists forever.
- **Regression tests for staleness** — store a fact, advance the clock past its TTL (or supersede it), assert the agent uses the fresh value, not the stale one.

The judge dimension, stated like silent-tool-fallback's: *"For each memory the agent surfaced as fact, (a) was it retrieved from the store and not fabricated, (b) is it still current, (c) was it relevant to the query? A surfaced memory that is stale, contradicted, or irrelevant scores 0."* That single rubric line catches poisoning, staleness, and drift in one pass.

---

## Operational anti-patterns

Concrete shapes and prevention, in the style of `silent-tool-fallback.md`. These are the failure modes a memory store falls into when operated without policy.

### Memory poisoning — a wrong fact persisted, then trusted forever
A false fact enters the store and resurfaces as ground truth on every future retrieval. The dangerous version is adversarial: 2026 research (MINJA, MemoryGraft, arXiv:2601.05504) shows attackers planting persistent malicious memories through *query-only* interaction — no direct store access needed — with attack success rates reported above 80%, and the poison surviving across sessions. Microsoft documented "AI recommendation poisoning" in production (Feb 2026): a single crafted link click embeds false context that persists into every later session.
**Prevention:** validate/filter before write; never let untrusted input write to a privileged namespace; prefer overwrite-with-conflict-resolution (mem0) or invalidation (Zep) over blind append; run a standing poisoning regression in the eval harness (above). Treat anything the model extracts and persists as a trust surface, because it is.

### Staleness — memory outlives its truth
A fact was true when written and is wrong now; the agent asserts it with full confidence. The survey's exact failure mode: high-relevance memories become confidently wrong when circumstances change. Worse than no memory, because it *looks* like knowledge.
**Prevention:** TTL + recency-weighted retrieval (not TTL alone); bi-temporal invalidation where "what was true when" matters; a staleness-distribution metric and a staleness regression test. If the design promises freshness, it must name the decay policy.

### Over-injection / context bloat — dumping all recall into context
The retrieval step returns everything plausibly related and stuffs it into the window. Reasoning *degrades* — the model now reasons over a haystack, and the relevant memory competes with ten irrelevant ones. This is the failure the just-in-time-retrieval framing exists to prevent.
**Prevention:** a per-turn retrieval token budget; a relevance floor; rerank-and-trim to top-few; measure retrieval precision. Inject less than you can.

### Retrieval drift — semantically-close-but-wrong recall
Nearest-neighbor returns a memory that's *similar* to the query but not the *right* one (the wrong customer with a similar name, last quarter's metric definition). Recall is not relevance; a vector store gives you similarity, not correctness.
**Prevention:** hybrid retrieval (semantic + keyword + entity) for exact-match facts; reranking; a similarity floor; precision/recall in the eval. Bad chunking or a weak embedding model is the root cause as often as the policy is.

### Unbounded growth — cost, latency, and noise
The store only grows. Bills climb (storage, embedding, retrieval), P95 latency climbs, and precision falls because every query competes against more candidates. LangGraph checkpoint bloat, mem0 hitting tier limits, vector indexes ballooning.
**Prevention:** the forget operation, on purpose — TTL, salience eviction, warm/cold tiering, periodic compaction. Cap sizes (the memory-tool docs suggest size caps + pagination). Store references, not blobs.

### Persisting hallucinations — the agent's own fabrication becomes "memory"
The extraction step persists something the model made up, and the fabrication is now a "remembered fact" — laundered from guess to ground truth by the act of storage. The cross-product with silent-tool-fallback: a fabricated answer that gets written to memory poisons every future session, not just the current turn.
**Prevention:** ground the write — extract facts only from tool outputs / user statements present in the trace, not from the model's free generation; the same claims-vs-traces grounding the judge already enforces, applied at the *write* boundary, not just the response boundary. Don't write what you couldn't cite.

---

## A full policy in one shape

What a complete operational memory design looks like — the sales-outreach claw from the first sibling's worked example (episodic + entity + procedural + semantic, on a LangGraph store with a cross-runtime mem0 layer). This is the level of specificity inception should emit, not "use mem0":

```
MEMORY OPERATIONS — sales-outreach claw
  episodic (interactions log):
    write     write-on-event — one record per send/reply, async, extracted from
              the tool trace (never from model prose) → no persisted hallucinations
    retrieve  query on account-id, hybrid (entity + recency); top-5, floor 0.75,
              ≤1.5k tokens/turn
    forget    90-day TTL + salience (drop accounts untouched 60d to cold tier)
    consolidate  nightly: dedup sends, promote "Fri sends → replies" pattern
                 episodic→procedural
  entity/profile (per-account facts):
    write     write-on-event (a fact changed); overwrite conflict resolution
              — only current truth matters for outreach
    retrieve  load the account's profile blob at session start, no floor
    forget    no TTL (profile is durable); deletion targets by account-id (RTBF)
  conflict   overwrite (entity) / append-episode (episodic) — NOT bi-temporal:
             "what was true when" is not a question this agent answers
  eval       with/without A/B on reply-rate; poisoning regression (plant a fake
             "do-not-contact" fact, assert it's surfaced not silently obeyed);
             staleness regression (superseded owner → assert fresh value used)
  governance mask contact PII at extraction; namespace = tenant:{org}:{account}
```

Every line is a decision a reviewer can check. A memory section that reads "episodic + profile memory via mem0" without these lines is the incomplete design this entry exists to catch.

---

## Governance note (operational discipline)

The architecture-selection sibling covers storage-level governance (tenant-scoped namespaces, DPA-before-vendor, encryption). The operational layer adds two disciplines:

- **Mask before write.** PII/secrets/tokens get stripped *at the extraction step*, before anything is persisted — not scrubbed later. The Anthropic memory-tool docs flag sensitive-info stripping as a write-time concern; a memory store inherits the same `[MUST]` rules as any data store (no secrets written, mask PII before persisting).
- **Audit what's persisted.** Log the *categories* of what's written (not raw content), so you can answer "what does this agent remember about user X" — which is also the **right-to-deletion surface**: deletion is only operable if you can enumerate and target a user's memories. Tenant isolation of memory namespaces is a `[MUST]` (a cross-tenant memory leak is CRITICAL); the operational test is that eviction and deletion can be *scoped to one tenant/user* and verified.

Brief by design — but the right-to-deletion surface only exists if the forget operation (above) was built to target by owner, which is why governance and the eviction policy are the same decision viewed twice.

---

## Hard rule for inception

When a design includes memory, the recommendation **must name a write policy + a retrieval policy + an eviction/consolidation policy** — not just a kind and a tool. A memory store with no operational policy is an incomplete design, the same way a tool-using agent with no failure-surfacing is incomplete (`silent-tool-fallback.md`). Concretely, the memory section of `design_rationale` must answer:

1. **Write:** when does a write fire (every-turn / reflection / event), and what's the extraction filter (what's memory-worthy)? Async or hot-path?
2. **Retrieve:** rank by what (relevance + recency)? What's the relevance floor and the per-turn token budget? Hybrid or pure-semantic?
3. **Forget/consolidate:** what's the TTL / salience-eviction / tiering policy, and the consolidation cadence (rolling summary, dedup, episodic→semantic promotion)?
4. **Conflict resolution:** overwrite / version / bi-temporal — and why that one for this domain?
5. **Eval:** which memory-quality metrics, and is there a with-vs-without A/B plus poisoning + staleness regressions in the judge harness?

A design that lands "use mem0" (or any tool) without 1–3 is sent back the same way a claw with no episodic memory is sent back by the first sibling — the kind+tool is the start of the memory design, not the end.

**Does this change the inception hook?** Yes. The first sibling established that `design_rationale` must name a memory *kind* per the five-kind table; the second added the *tool/rung*. This entry says **that pair is still incomplete without an operational policy triple (write / retrieve / evict-consolidate) plus a conflict-resolution choice and an eval hook.** The hook should require all three layers: a memory section that names a kind and a tool but no write/retrieve/eviction policy should be flagged as incomplete — not because the tool choice is wrong, but because an un-operated store predictably degrades into staleness, bloat, and poisoning. The minimal valid memory section is: *kind → tool/rung → write policy → retrieval policy → eviction/consolidation policy → conflict-resolution choice → eval hook.* Anything less ships a liability that looks like an asset.
