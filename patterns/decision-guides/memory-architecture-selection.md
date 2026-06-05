---
title: Memory architecture & tooling selection — pick the cheapest sufficient layer
category: decision-guides
status: draft
last_updated: 2026-06-03
source_external:
  - Anthropic — "Memory tool" (https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
  - Anthropic — "Context editing" (https://platform.claude.com/docs/en/build-with-claude/context-editing)
  - LangChain — "LangGraph persistence (checkpointers & store)" (https://docs.langchain.com/oss/python/langgraph/persistence)
  - LangChain — "LangMem" (https://langchain-ai.github.io/langmem/)
  - Mem0 — "Memory types & overview" (https://docs.mem0.ai)
  - Zep — "Concepts: temporal knowledge graph / context graph" (https://help.getzep.com)
  - Graphiti — Rasmussen et al., "Zep: A Temporal Knowledge Graph Architecture for Agent Memory" (https://arxiv.org/abs/2501.13956)
  - Letta — "Memory management / MemGPT agents" (https://docs.letta.com/concepts/memory-management)
applies_when:
  workloads: [any-conversational-agent, any-task-agent, any-co-pilot, any-autonomous-worker, any-agent-needing-persistence]
  constraints: [memory-kind-already-decided, harness-chosen-or-being-chosen, persistence-required]
contradicts: []
related:
  - decision-guides/does-this-agent-need-memory
  - decision-guides/subagent-vs-skill-tradeoffs
  - harnesses/langgraph-deep-dive
  - harnesses/claude-agent-sdk-deep-dive
  - skill-design/atlan-context-without-repo
snapshot_date: 2026-06-03
---

# Memory architecture & tooling selection — pick the cheapest sufficient layer

This entry takes a decision as **input** and produces one as **output**. The input — *does this agent need memory, and which kind (working / episodic / semantic / procedural / entity-profile)?* — is answered by the sibling entry `decision-guides/does-this-agent-need-memory.md`. Read that first; it defines the memory kinds, and this entry uses them without redefining them at length. The output here is the **architecture and the tooling**: given that the agent needs, say, semantic memory plus an entity profile, what do you actually stand up?

The decision is a product of four inputs:

> **memory architecture = (memory kind needed) × (harness you're on) × (scale) × (governance)**

- **Memory kind** narrows the *architecture* (a profile wants a durable record; "what happened last Tuesday" wants an episodic store; "what does *net revenue* mean here" wants retrieval over a curated corpus).
- **Harness** is the strongest input on *tooling*, because every major harness gives you *some* memory for free, and the path of least resistance is almost always the harness-native option.
- **Scale** decides whether an in-process store survives (one user, one box) or you need a managed/shared backend (many users, many agents, cross-runtime).
- **Governance** decides whether persisted facts need access control, audit, PII handling, and a single source of truth — which is where the cheap options stop being sufficient.

The recurring failure is **over-reach**: a team names "mem0" or "Zep" in the design before they've established that conversation history plus a rolling summary wouldn't do. The cheapest sufficient option usually wins, and for a large fraction of agents that option is *the harness's own session/state plus a summary*. Reach for a managed memory product when you've hit a specific wall — cross-runtime sharing, temporal fact invalidation, automatic extraction at scale — not because "agents should have memory."

---

## The architectural approaches (patterns before products)

Pick the *pattern* from the memory kind first; tooling comes after. Six patterns cover the field.

| Pattern | Serves which memory kind | Good for | The gotcha |
|---|---|---|---|
| **In-context / conversation history** (+ rolling summarization / compaction) | working | The default. Everything that fits in one session, or spills over but compresses cleanly. | Summaries lose detail silently; the agent "forgets" a fact it summarized away two turns ago. |
| **Retrieval / semantic memory (RAG)** over a curated corpus | semantic | "What is X here" — definitions, policies, governed knowledge the model wasn't trained on. | Only as good as the corpus and the retriever; stale or low-precision retrieval poisons answers. |
| **Episodic store** (append events, retrieve by recency/relevance) | episodic | "Last Tuesday you asked me to…" — a log of past interactions, retrieved at session start. | Unbounded growth; without decay/relevance ranking, retrieval drowns in old events. |
| **Entity / profile memory** (durable per-user/account record) | entity-profile | Stable facts about a user/account/asset that should survive every session. | Conflict resolution on write — when the fact changes, do you overwrite, version, or duplicate? |
| **Knowledge-graph memory** (temporal, entity-centric) | semantic + entity + episodic, unified | Relationships that change over time; "what was true when"; multi-hop reasoning over facts. | Heaviest to operate; extraction quality bounds graph quality; overkill for flat preference storage. |
| **Hierarchical / paging memory** (MemGPT-style page-in/out) | working + episodic + semantic, self-managed | Long-horizon agents that must manage a memory budget larger than the window themselves. | The agent spends tokens *and tool calls* managing its own memory; added latency and a new failure surface. |

A few notes on the patterns themselves:

- **In-context is not "no memory"** — it's the memory you get for free, and it's sufficient for more agents than people assume. The escalation from here is *summarization/compaction*, not a database.
- **Episodic vs. semantic is the most-confused pair.** Episodic = *what happened* (events, timestamped, retrieved by recency/relevance). Semantic = *what is true* (facts/definitions, retrieved by meaning). They want different stores and different write paths; conflating them gives you a log that can't answer "what is X" and a fact-store that can't answer "what did we do last week."
- **Knowledge-graph memory subsumes several kinds** at the cost of operational weight. It's the right call when *relationships and their change over time* are load-bearing — not when you just need to remember a user prefers dark mode.

---

## The tooling landscape

The pattern selects a *class* of tool. This is the comparison; per-option detail follows.

| Tool | Pattern(s) it implements | Hosted? OSS? | Memory kinds covered | Reach for it when | Skip it when |
|---|---|---|---|---|---|
| **Runtime-native** (Claude memory tool, LangGraph store+checkpointer, OpenAI threads) | in-context, episodic, profile, file-based | Free with the harness | working + whatever you build on top | You're already on that harness — *always evaluate this first* | You need cross-runtime sharing or temporal facts |
| **mem0** | episodic + profile + (graph) | Hosted (tiered) + OSS (Apache-2.0) | user / session / agent / org scopes; self-editing on write | You want a drop-in memory layer with automatic extraction, multi-scope, low setup | The harness's own store already covers you; you need temporal "what was true when" |
| **Zep / Graphiti** | knowledge-graph (temporal) | Zep hosted; Graphiti OSS | semantic + entity + episodic, unified, bi-temporal | Relationships change over time and you need "state at any point in time" | Flat preference/profile storage; you don't need the graph |
| **Letta / MemGPT** | hierarchical / paging, self-editing | OSS (Apache-2.0) + Letta Cloud | core (in-context) + recall + archival | The *agent* should own and edit its own memory across a budget larger than the window | You want the orchestrator (not the model) to control memory; you're on another harness already |
| **LangMem** | semantic + episodic + profile extraction | OSS lib over LangGraph store | semantic / episodic / profile, hot-path or background | You're on LangGraph and want extraction/consolidation on top of the store | You're not on LangGraph; the raw store suffices |
| **Vector store (Pinecone / pgvector / Qdrant / …)** | retrieval / semantic (build-your-own) | Hosted + OSS | semantic, episodic (DIY) | You want full control of corpus, chunking, retriever; you already run one | You'd be rebuilding what a managed memory layer gives you for free |

### Runtime-native — what each harness gives you for free

**Always evaluate this row first.** The harness you've chosen (see `framework-or-hand-roll.md`: you *did* choose a framework) almost certainly ships a memory primitive that costs zero extra infrastructure.

- **Claude / Claude Agent SDK — the memory tool + context management.** The memory tool (`type: "memory_20250818"`) gives the model a `/memories` file directory it reads before each task and writes to as it works: `view`, `create`, `str_replace`, `insert`, `delete`, `rename`. Critically, **it operates client-side — *you* control where the files live** (filesystem, DB, cloud, encrypted store; subclass `BetaAbstractMemoryTool` in Python or `betaMemoryTool` in TypeScript). The docs frame it as "just-in-time context retrieval": store what you learn, page it back on demand, keep the active window focused. It pairs with **context editing** (clears stale tool results client-side) and **compaction** (server-side summarization near the window limit). The canonical pattern is a progress-log file the agent updates end-of-session so the next session resumes in seconds — the model is told *"ASSUME INTERRUPTION: your context window might be reset at any moment."* This is file-based working + episodic + procedural memory, free, but the *storage and its security are your problem* (path-traversal validation, size caps, PII stripping, expiry — all called out in the docs). Note the Claude Agent SDK's `CLAUDE.md` is a *separate* project-memory mechanism loaded into the conversation, not the system prompt.
- **LangGraph — checkpointer (short-term) + store (long-term).** Keep these two straight; it's the single most useful distinction in the landscape. The **checkpointer** is *thread-scoped*: it snapshots `State` at every super-step, keyed by `thread_id` — that's working memory and intra-conversation persistence, and it's what `subagent-vs-skill-tradeoffs.md` and `langgraph-deep-dive.md` already cover (durable execution, interrupts, time-travel). The **store** (`BaseStore`) is *cross-thread*: arbitrary data namespaced by a tuple like `(user_id, "memories")`, surviving across all of a user's conversations — that's profile + semantic memory. The store supports **semantic search over its items** when you configure an embedding model at init (`index={"embed": …, "dims": …, "fields": […]}`). Backends: `InMemoryStore` (dev), `PostgresStore` / `MongoDBStore` / `RedisStore` (prod). **Consistency note:** the related entries describe checkpointers as the durable-state primitive (correct for *thread* state); the *store* is the separate cross-thread long-term layer — when an agent needs cross-session profile/semantic memory on LangGraph, the store, not the checkpointer, is the answer.
- **OpenAI Agents SDK — sessions/threads.** Persist conversation history per thread; weaker on structured long-term/profile memory than LangGraph's store. For durable specialist state you pair an external store (consistent with `subagent-vs-skill-tradeoffs.md`'s Reason-5 note).

The shape of the free option, concretely — same profile-memory task, two harnesses:

```python
# LangGraph: cross-session profile memory = the store, namespaced by user, with embeddings.
from langgraph.store.memory import InMemoryStore
from langchain.embeddings import init_embeddings

store = InMemoryStore(index={"embed": init_embeddings("openai:text-embedding-3-small"),
                             "dims": 1536, "fields": ["fact"]})
ns = ("user-42", "memories")                       # tuple namespace == tenant/user isolation
store.put(ns, "pref-1", {"fact": "prefers SQL over the UI for bulk edits"})
hits = store.search(ns, query="how does this user like to work")  # semantic recall, cross-thread
# checkpointer (thread_id) handles working memory *within* a session; the store is the long-term layer.
```

```python
# Claude memory tool: same persistence, but the model drives it via file ops and YOU own storage.
tools = [{"type": "memory_20250818", "name": "memory"}]   # model gets view/create/str_replace/...
# Your client executes the ops against /memories. Subclass BetaAbstractMemoryTool to back it with
# a per-user, access-controlled directory — that namespace boundary is the tenant-isolation control.
```

The difference that matters for selection: **LangGraph's store is orchestrator-controlled** (your code does `put`/`search`); **Claude's memory tool is model-controlled** (the model decides what to write). That's the same axis as Letta vs. a hand-managed store — see below.

**The takeaway for inception:** if the memory kind needed is working or modest episodic/profile memory and the harness is already chosen, the runtime-native option is the recommendation. Don't add a vendor.

### mem0 — the drop-in memory layer most people name

mem0 is "a universal, self-improving memory layer for LLM applications that enables persistent context across sessions." It's the one teams reach for by name, and it earns the slot for **automatic extraction + multi-scope + low setup**. What it actually does:

- **Scopes, not academic kinds:** memories are isolated by `user_id` (long-lived profile/preferences), `run_id` (= session/thread, expires when the task completes — episodic), and `agent_id` (agent-specific knowledge). Org-level scope exists for shared context across agents/teams.
- **Self-editing on write (conflict resolution):** mem0's distinguishing behavior is that when a user corrects a fact, it *updates the existing record* rather than appending a duplicate — extraction and dedup happen in the add pipeline, not at read time.
- **Storage:** a vector store (15+ backends — Qdrant, Chroma, Pinecone, Weaviate, etc.; semantic search always, hybrid where available) plus optional **graph memory** for relationship modeling. As of mid-2026 mem0 reworked its graph path toward entity-linking stored alongside the vector collection; Neo4j (and other graph DBs) remain supported providers.
- **Hosted vs OSS:** **Platform** is managed (tiered — a free Hobby tier, paid tiers up to a Pro tier that unlocks unlimited memories and the richer graph features). **Open source** is Apache-2.0, self-hosted, full control; graph memory is available OSS via `pip install mem0ai[graph]`.

**When to use:** cross-runtime memory (you're not all-in on one harness), or you want extraction/dedup/multi-scope without building it. **When not:** the harness store already covers you; or you need true *temporal* "what was true at time T" (mem0 resolves conflicts by overwriting — it's not bi-temporal). **Gotcha:** because it extracts and overwrites, mem0 is conversation/agent-centric; it's weaker as a *document* knowledge base than a purpose-built RAG corpus. Its 2026 graph rework (entity-linking inside the vector collection, replacing ~4k lines of dedicated graph paths) means OSS configs that pinned the old `graph_store` block + Neo4j/Memgraph drivers need a migration — check the version before copying an older integration.

### Zep / Graphiti — temporal knowledge-graph memory

Zep builds a **temporal knowledge graph** ("context graph"): **nodes are entities, edges are facts/relationships**, and the graph evolves as chat, business data, documents, and JSON are ingested. Its differentiator is **bi-temporal tracking** — every fact edge carries when it *became valid* and when it *became invalid*. Old facts are **invalidated, not deleted**; you can query "what was true at any point in time." Retrieval assembles token-efficient context (facts, summaries, observations) from a governed store with sub-200ms P95; interfaces are `thread.get_user_context` (high-level) and `graph.search` (low-level).

- **Zep vs Graphiti:** **Graphiti** is the open-source library implementing the temporal graph (the underlying engine, per the arXiv paper); **Zep** is the managed cloud platform built on it (enterprise scale, governed context lake, the retrieval APIs). Use Graphiti to self-host the graph; use Zep when you want it operated for you.
- **Memory kinds:** unifies semantic (facts), entity (the nodes/profiles), and episodic (the episodes ingested) in one structure.
- **Benchmark anchor (cite cautiously):** the Graphiti paper reports strong results on temporal-reasoning benches (DMR, LongMemEval) versus a MemGPT baseline — credible signal that the temporal model helps on *time-sensitive* recall, not a license to assume it wins everywhere. The benefit is specific to "what was true when."

**When to use:** relationships change over time and *temporality matters* — "the account's owner changed in March," "this contact was at company A, now at company B." **When not:** you need a flat preference store or a single profile blob — the graph is operational weight you won't use. **Gotcha:** graph quality is bounded by extraction quality; the LLM that turns episodes into entities/edges is now part of your reliability surface, and the ingestion-LLM cost scales with event volume.

### Letta / MemGPT — self-editing hierarchical memory

Letta (formerly MemGPT) is the **OS-as-memory** model: the agent manages a memory hierarchy larger than its context window, page-style.

- **Core memory** — always in-context (the "RAM"): labeled, persistent **memory blocks** the agent edits directly. Conventional blocks are `persona` (the agent's self-description) and `human` (what it knows about the user); custom blocks hold task/project state.
- **Recall memory** — conversation history, searchable on demand (saved to disk automatically — Letta handles persistence the agent would otherwise have to manage).
- **Archival memory** — an external vector store the agent queries explicitly for long-running facts and external data.
- **Self-editing tools:** the `memgpt_agent` archetype exposes `core_memory_append` / `core_memory_replace` (edit the in-context blocks), `conversation_search` (recall), and `archival_memory_insert` / `archival_memory_search` (archival). The **model** decides what to promote, demote, and rewrite.
- **OSS + Cloud:** Apache-2.0 (self-host) plus Letta Cloud. (Its newer git-tracked `MemFS` file-memory system sits alongside the classic block model.)

**When to use:** a long-horizon agent that should *own* its memory and operate over a budget bigger than the window — the agent-as-memory-manager shape. **When not:** you want the *orchestrator* (your code), not the model, to control what persists; or you're already on a harness whose store/memory tool does the job. **Gotcha:** the agent spends tokens *and tool calls* managing memory — added latency and a new failure surface (the model can mis-edit its own core memory). Note Claude's memory tool occupies a similar file-based niche but keeps *you* in control of storage rather than handing the model archival/recall tooling — choose Letta when you *want* model-owned memory, the Claude memory tool when you want model-written-but-client-stored, and the LangGraph store when you want orchestrator-owned memory.

### LangMem — extraction/consolidation on top of the LangGraph store

LangMem is a LangGraph-ecosystem library that "helps agents learn and adapt from their interactions over time." It's **not a separate store** — it provides primitives over LangGraph's `BaseStore` (and works with any store). It manages **semantic** memories (facts/preferences), **episodic** memories (events), and **user profiles**, with two write paths: **hot-path** (`create_manage_memory_tool` / `create_search_memory_tool` — the agent manages memory mid-conversation) and **background** (a manager that extracts and consolidates without the agent in the loop).

**When to use:** you're on LangGraph and want extraction/consolidation/profile-building rather than hand-writing memory CRUD over the store. The **hot-path vs background** split is the real design choice: hot-path (`create_manage_memory_tool`) lets the agent decide what to remember mid-turn but costs tokens and latency every turn; background extraction runs the consolidation out of band so the conversation isn't taxed but new facts aren't available until the next run. Default to background unless the agent must act on something it just learned *within the same session*. **When not:** you're not on LangGraph, or the raw store with your own write logic suffices. **Gotcha:** it inherits the store's namespacing model and the checkpointer-schema-migration pain `langgraph-deep-dive.md` flags — versioning your `State`/store shape is still on you.

### Vector stores as memory — the build-your-own semantic option

Pinecone, pgvector, Qdrant, Weaviate, Chroma — embed your corpus/events, retrieve by similarity. This is **RAG used as memory**, and it's the right primitive for *semantic memory over a corpus you control*.

- **The dividing line vs a memory layer:** a vector store gives you `upsert(embedding, metadata)` and `query(embedding, k)`. A *memory layer* adds the parts you'd otherwise build — extraction (turning a conversation into a fact), dedup/conflict resolution, scoping by user/session/agent, decay, and the prompt-assembly step. If you only need "retrieve from a fixed governed corpus," the vector store alone is correct and lighter. If you need "learn from conversations over time," you're signing up to build a memory layer on top — at which point compare the build cost to mem0/LangMem.

**When to use:** you want full control over corpus curation, chunking, embedding model, and retriever; you already operate one (pgvector next to your Postgres is the lowest-marginal-cost case — no new dependency). **When not:** you'd be reimplementing extraction, dedup, scoping, and conflict resolution that mem0/Zep/LangMem give you — a raw vector store is *storage*, not a *memory layer*. **Gotcha:** retrieval precision is everything — bad chunking or a weak embedding model means the agent confidently retrieves the wrong fact. A vector store gives you recall, not relevance; you own the re-ranking and the relevance threshold (returning a low-similarity hit as if it were a fact is a top poisoning vector).

---

## Selection logic

Map **memory kind → architecture → tooling**, with **harness as a strong tie-breaker**. The harness you're on usually decides the tool, because the native option is free and integrated.

| Memory kind (from sibling entry) | Architecture | Default tooling — by harness |
|---|---|---|
| **Working** | in-context + summarization/compaction | Claude: context editing + compaction. LangGraph: checkpointer. OpenAI: thread/session. *No new infra.* |
| **Episodic** | episodic store, retrieve by recency/relevance | LangGraph: store. Claude: memory-tool progress files. Cross-runtime: mem0 (`run_id` scope). |
| **Semantic** | RAG over curated corpus, or KG | LangGraph: store w/ embeddings, or LangMem. Otherwise: a vector store you run, or mem0. Governed corpus → Atlan (below). |
| **Procedural** | learned rules/skills in a durable record | Claude memory-tool files; LangGraph store; or skills (`subagent-vs-skill-tradeoffs.md`) if the procedure is static. |
| **Entity / profile** | durable per-user/account record | LangGraph store (`(user_id, …)`) + LangMem profiles; or mem0 (`user_id`); temporal → Zep. |
| **Multiple kinds, agent self-manages** | hierarchical / paging | Letta/MemGPT, or Claude memory tool if you want to keep storage control. |
| **Relationships that change over time** | temporal knowledge graph | Zep (managed) / Graphiti (OSS). |

### Start-here / escalate-to ladder

Default to the **lowest rung that's sufficient**. Escalate only when you hit the named wall.

1. **Conversation history** — the harness's session/thread. *Wall:* the window fills, or coherence degrades over a long session.
2. **+ Rolling summarization / compaction** — Claude compaction, or a summary node in LangGraph. *Wall:* you need facts to survive *across sessions*, not just within one.
3. **+ Cross-session store (profile/episodic)** — LangGraph store, Claude memory-tool files, OpenAI thread persistence. Still no vendor. *Wall:* you need automatic extraction at scale, multi-scope, or you're cross-runtime.
4. **+ Semantic/RAG** — a vector store or LangMem over a curated corpus, for "what is X here." *Wall:* writing/dedup/scoping is becoming its own project, or memory must be shared across runtimes.
5. **Managed memory product** — mem0 (extraction + multi-scope + dedup) or Letta (agent self-manages). *Wall:* relationships change over time and you need "what was true when."
6. **Knowledge-graph memory** — Zep / Graphiti. The top rung; the most operational weight.

**Hard rule for inception's memory_proposer (or architecture_proposer):** name the memory kind, then name the *lowest rung* that satisfies it, then justify any escalation past it with the specific wall. A proposal that lands on rung 5–6 (mem0/Zep/Letta) without articulating why rungs 1–4 are insufficient is over-reaching — emit the lower rung instead. And **always check the runtime-native option first**: if the harness is chosen, the native store/memory-tool is the default unless a wall pushes past it.

### Two walkthroughs

**A support co-pilot on Claude Agent SDK that should "remember each customer."** Sibling entry says: working (the live ticket) + entity-profile (the customer). Walk the ladder: rung 1 (conversation history) covers the live ticket. The profile is cross-session → rung 3. Harness is Claude → runtime-native = the **memory tool**, backed by a per-customer directory your client owns (the directory boundary *is* the tenant-isolation control). No vendor. *Escalate only if* you later need automatic fact-extraction across thousands of customers without the model managing it — then rung 5 (mem0, `user_id` scope). Stop at rung 3 until that wall is real.

**An account-intelligence claw on LangGraph that tracks how relationships change.** Sibling entry says: episodic (interactions) + entity (accounts/contacts) + semantic (account facts), and the facts *change over time* ("contact moved from company A to B"). Working/episodic → checkpointer + store (rungs 1–3, free on LangGraph). But "what was true when" is the named wall that the store can't answer — it overwrites. That justifies rung 6: **Zep/Graphiti** for the temporal graph, with the LangGraph store still handling non-temporal working state. This is a legitimate top-rung landing *because the wall is articulated*.

---

## Atlan angle (neutral — one option among several)

When the agent is **Atlan-integrated**, Atlan's knowledge wiki / context repos / lakehouse (MDLH) can *serve as the semantic-memory layer*: RAG over **governed, curated metadata** — definitions, lineage, ownership, certified terms, policies. This is one strong option for **semantic and entity memory**, not a requirement and not a replacement for the runtime-native layer.

The honest framing of the boundary: a memory layer (mem0, Zep, the harness store) stores **what was said/what happened**; a governed context layer stores **what is true** about the organization's data, and can answer "what does *net revenue* mean here" even if no agent ever discussed it. Internal Atlan material draws this line explicitly — see the public articles *"In-Context vs External Memory for AI Agents"* and *"Agent Memory Architectures: 5 Patterns and Trade-offs"* (which adds a fifth, enterprise "organizational context memory" type to the CoALA four), and the internal Confluence page *"Memory In Agents"* (Data & AI Governance space, which maps mem0 scopes — user/session/agent — to an enterprise integration). The internal GTM project brief *"Project Brief: Atlan LLM Wiki for GTM"* states the relevant design principle directly: **"one context layer, many agents"** — a single governed wiki every agent reads from, rather than per-agent memory copies that drift. (Titles cited; internal URLs omitted.)

Practically, for an Atlan-integrated agent: use the runtime-native layer for working/episodic/profile memory, and consider an Atlan-backed corpus (MDLH read patterns or a context repo — see `skill-design/atlan-context-without-repo.md`) as the **semantic-memory source** when the agent needs governed metadata grounding. Keep it neutral: it's the right *semantic* layer when the agent is already Atlan-integrated and the knowledge is governed; it does nothing for the working-memory or temporal-fact problems, which still want the harness store or a graph layer.

---

## Gotchas / failure modes

These cut across every tool. The proposer should surface mitigations as first-class output, not footnotes.

- **Staleness.** Persisted facts go out of date; the agent confidently asserts last quarter's owner. Mitigate with TTL/expiry (Claude docs literally suggest clearing memory files not accessed in a while), recency-weighted retrieval, or a temporal model (Zep's invalidation) where "what was true when" matters.
- **Memory poisoning.** A wrong fact gets written once and resurfaces forever — worse, an adversary can *plant* one via crafted input (prompt-injection into the write path). Anything the model extracts and persists is now a trust surface. Validate/filter before write; prefer overwrite-with-conflict-resolution (mem0) or invalidation (Zep) over blind append; never let untrusted input write to a privileged memory namespace.
- **Retrieval relevance/precision.** Recall isn't relevance. Bad chunking, a weak embedding model, or no re-ranking means the agent retrieves the *wrong* memory and reasons from it. Measure retrieval precision in your eval seed; this is the #1 silent failure of the RAG/vector-store rung.
- **Unbounded growth + cost.** Episodic stores and checkpointers grow forever. LangGraph state bloat (every checkpoint serializes full state — see `langgraph-deep-dive.md`), mem0 memory counts hitting tier limits, vector indexes ballooning. Cap sizes, decay old entries, store references not blobs, and budget retrieval token cost per turn.
- **PII / privacy in persisted memory — a real governance surface.** The moment you persist conversation-derived facts, you've created a data store subject to the same `[MUST]` rules as any other: no secrets/tokens written to memory, mask PII before persisting, scope memory namespaces to the authenticated user/tenant (a cross-tenant memory leak is a CRITICAL per the tenant-isolation rule), and support deletion (right-to-be-forgotten). Claude's memory tool docs flag sensitive-info stripping and ZDR eligibility; managed products (mem0/Zep) move customer-derived data into a vendor — confirm the DPA before sending it there, consistent with the AI/LLM data-handling rules. Treat the memory store as governed data, because it is.

## The four common mistakes (what the proposer gets wrong)

1. **Naming a memory product before establishing the wall.** "We'll use mem0" appears in the design with no statement of why the LangGraph store or Claude memory tool wouldn't do. → Default to the runtime-native layer; escalate only against a named wall.
2. **Confusing the checkpointer with long-term memory on LangGraph.** Teams put cross-session profile facts in the checkpointer (thread-scoped) and wonder why a new conversation starts blank. → Cross-session = the **store**; the checkpointer is *thread* state.
3. **Using a knowledge graph for flat preferences.** Standing up Zep/Graphiti to remember "prefers dark mode" — all the operational weight, none of the temporal payoff. → KG only when relationships *change over time*.
4. **Treating the memory store as not-data.** Skipping tenant-scoped namespaces, PII masking, and deletion because "it's just memory." → It's a governed data store; the tenant-isolation and PII rules apply in full.

The single most important operational reminder: **most agents that "need memory" need rung 1–3, not a memory product.** Establish the wall before you add the vendor.
