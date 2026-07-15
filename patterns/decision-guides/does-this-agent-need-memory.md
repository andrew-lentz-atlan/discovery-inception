---
title: Does this agent need memory? (And what kind?)
category: decision-guides
status: draft
last_updated: 2026-06-03
source_external:
  - "Sumers, Yao, Narasimhan, Griffiths — Cognitive Architectures for Language Agents (CoALA), arXiv:2309.02427"
  - "Packer et al. — MemGPT: Towards LLMs as Operating Systems (memory hierarchy; core/archival/recall), and the Letta agent-memory writeups"
  - "2026 agent-memory taxonomy surveys: 'Anatomy of Agentic Memory' (arXiv:2602.19320), 'Memory in the Age of AI Agents' (arXiv:2512.13564), mem0 'State of AI Agent Memory 2026'"
applies_when:
  workloads: [any]
  constraints: [memory-decision-point]
contradicts: []
related:
  - decision-guides/what-kind-of-agent-are-you-building
  - decision-guides/memory-architecture-selection
  - skill-design/memory-operations
  - decision-guides/subagent-vs-skill-tradeoffs
  - harnesses/langgraph-deep-dive
snapshot_date: 2026-06-03
---

# Does this agent need memory? (And what kind?)

Memory is the most-skipped agent design decision, because nothing forces it. An agent "works" in a demo without it — the demo is one session, the context window holds everything, and the gap is invisible. Then it ships, and on the second session it re-asks the user for the thing they told it on the first, or it never gets better at a task it's done two hundred times, and the gap is suddenly the whole product.

The thesis of this entry: **memory is a deliberate design choice, not a default that materializes when you reach for a vector store.** It has a real cost on *both* sides. Memory you don't need buys you complexity, staleness, a privacy/PII surface, and retrieval noise that degrades answers. Missing memory you do need buys you no continuity, no learning, and frustrated users who can feel the agent forgetting them. The decision has to be made on purpose, and it has to be made for *every* agent — including the agents whose answer is "none beyond the conversation."

This guide is the **conceptual** layer: *do you need memory, and what kind?* It maps memory needs onto the five agent classes from `what-kind-of-agent-are-you-building.md` and onto the `state_shape` axis (stateless → session-scoped → long-horizon). It deliberately does **not** pick tools. Which store, which framework, which checkpointer — mem0, Zep, LangGraph checkpointers, a knowledge wiki, a managed memory service — is the job of the sibling entry `memory-architecture-selection.md`. Decide *what kind* here; decide *how to build it* there.

---

## The kinds of memory

This is the vocabulary the rest of the entry uses. The taxonomy is borrowed from the CoALA framework (which gave the field its shared language by translating cognitive science onto LLM agents) and sharpened with the entity/profile distinction that 2026 production taxonomies make explicit. Five kinds:

| Kind | What it holds | Lifetime | The question it answers |
|---|---|---|---|
| **Working / conversation memory** | The current session: system prompt, turns so far, tool outputs, the active scratchpad | This session only | "What are we talking about right now?" |
| **Episodic memory** | Records of events the agent experienced — tasks, actions, outcomes, trajectories, with timestamps | Persists across sessions | "What happened last week? What did I try, and how did it go?" |
| **Semantic memory** | Facts and knowledge — domain rules, glossaries, a curated corpus, often RAG over a knowledge wiki | Persists; curated/governed | "What is true about this domain?" |
| **Procedural memory** | Learned how-to — patterns, skills, routines the agent refines over time from experience | Persists; accretes | "What's the *right way* to do this, based on what's worked before?" |
| **Entity / profile memory** | Durable structured facts about a specific user/account/customer — preferences, prior decisions, stable attributes | Persists per entity | "Who is this person/account, and what do I already know about them?" |

A few sharpening notes, because the categories blur in practice:

- **Working memory is not "memory" in the design sense.** Every agent has it — it's the context window. When someone says "this agent has no memory," they almost always mean "no memory *beyond* the conversation." Naming working memory as its own kind keeps that distinction honest.
- **Episodic vs. semantic is the experience/knowledge split.** Episodic is *what I did and what happened* (specific, timestamped, mine). Semantic is *what is true* (general, curated, shared). An agent can learn a fact from an episode, which is how episodic feeds semantic — but they're stored and retrieved differently.
- **Procedural memory is the one that means "the agent improves."** It's the difference between an agent that does the task the same way forever and one that gets better. Most agents don't have it and don't need it; the ones that do are making a real claim ("learns from experience") that the design must back up.
- **Entity/profile memory is semantic memory *scoped to one entity*.** Some taxonomies fold it into "user-specific semantic memory." It's broken out here because the design implications are distinct: it's the continuity-per-user dimension, and it's where almost all the PII lives.
- **MemGPT/Letta's hierarchy is orthogonal to this list.** Core/archival/recall is about *where memory lives relative to the context window* (the OS-style paging story) — a tooling/architecture concern. That's the sibling entry's axis, not this one's. Here we care about *what kind of thing* is remembered, not where it's paged.

> **Atlan note (kept neutral):** an organization's governed knowledge layer — a knowledge wiki, certified metric definitions, lineage graphs — is *one instance of semantic memory*. It's a curated corpus the agent reads facts from. Treat it as a semantic-memory source like any other when deciding need; don't let a specific product's presence inflate the memory design.

---

## Memory need by workload class

Cross-reference `what-kind-of-agent-are-you-building.md`. For each class, each memory kind is **load-bearing** (the agent is broken without it), **optional** (helps some variants, not required), or **unneeded** (adds cost, not value). The `state_shape` column ties this back to the axis the classifier already emits.

| Class | `state_shape` | Working/conv | Episodic | Semantic | Procedural | Entity/profile |
|---|---|---|---|---|---|---|
| **Chatbot** | stateless | load-bearing (coherence) | unneeded | **load-bearing** (the corpus *is* the agent) | unneeded | unneeded |
| **Conversational agent** | session-scoped | **load-bearing** | optional | optional → often load-bearing | unneeded | optional |
| **Task agent** | stateless per task | load-bearing (within task) | unneeded *unless it learns across tasks* | optional (domain grounding) | optional → load-bearing *if it learns* | unneeded |
| **Co-pilot** | session-scoped | **load-bearing** | optional | optional | optional | **often load-bearing** |
| **Autonomous worker ("claw")** | long-horizon | load-bearing | **load-bearing** | **load-bearing** | optional → load-bearing | often load-bearing |

Reading the rows:

- **Chatbot — conversation + semantic only.** A chatbot is a retrieval system in a conversational coat. Its "memory" is the corpus it retrieves from (semantic), plus enough conversation history to stay coherent across turns. It does not remember *you* between sessions and does not learn. If a chatbot design proposes episodic or procedural memory, that's a smell — it's probably outgrowing the class.

- **Conversational agent — session is the unit; semantic often joins.** The defining property is multi-turn working memory: it remembers what it learned in turn 3 when answering turn 7. Cross-session episodic memory is *rarely* needed — sessions are usually self-contained. Semantic memory becomes load-bearing the moment the agent grounds answers in a domain corpus (text-to-SQL over a semantic layer, a research assistant over a doc set). Entity/profile is optional and only earns its place if the agent is expected to greet the user with context from last time.

- **Task agent — stateless by default; the exception is learning.** Per-task working memory, and that's it — *unless the task agent improves with experience.* A reconciliation agent that does the same job every time needs no durable memory. A triage agent that gets better at routing because it remembers how prior routings turned out needs **episodic** (what happened) feeding **procedural** (the refined routing heuristic). That exception is exactly the boundary where a task-agent-on-a-schedule starts becoming a claw. Memory is the tell.

- **Co-pilot — session plus, very often, the user.** Working memory is load-bearing; the agent assists within a live session. The interesting axis is entity/profile: a co-pilot that knows the human's preferences, conventions, and prior choices across sessions is materially more useful than one that meets them fresh every time. Note that much of a co-pilot's durable state lives in the *host tool* (the editor's files, the ticket's history) — so "the co-pilot needs entity memory" sometimes resolves to "read it from the host tool," not "build a store." The need is real even when the implementation isn't a new database.

- **Autonomous worker (claw) — episodic and semantic are LOAD-BEARING.** This is the row that motivates the whole entry. A claw runs on its own schedule across wake-ups. **A claw with no memory of what it did yesterday is broken** — not under-featured, broken. It will redo work, re-send messages, miss follow-ups, and drift without noticing. Episodic memory (what I did, what happened) is non-negotiable. Semantic memory (the domain facts it acts on) is non-negotiable. Procedural memory (learned patterns) and entity/profile (per-account continuity) are frequently load-bearing too, depending on the job. If a claw design doesn't specify episodic + semantic memory, the design is incomplete — full stop.

**The pattern across the `state_shape` axis:** stateless → conversation/semantic only; session-scoped → working memory is the unit, entity/profile optional-to-important; long-horizon → episodic + semantic become load-bearing and the others light up by job. State shape is a strong *prior* on memory need. It is not, by itself, a complete answer — see the closing section.

---

## The decision procedure

Run these questions in order. The first "yes" that lands tells you a memory kind is in scope; keep going to catch the others. If every answer is "no," the answer is **"no memory beyond conversation history"** — which is a valid, explicit result, not a skipped decision.

1. **Does the agent act or converse across more than one session?**
   - No → working/conversation memory only. Stop here unless Q5 applies.
   - Yes → continue; cross-session memory is in play.

2. **Does it need continuity about a specific user / account / customer between sessions?**
   - Yes → **entity/profile memory.** (Check whether the host tool already holds it before building a store.)

3. **Does it need to remember what *it itself did* — prior actions, tasks, outcomes — to do the next thing correctly?**
   - Yes → **episodic memory.** (For any claw, this is almost always yes.)

4. **Does the agent improve with experience — get measurably better at the task over time?**
   - Yes → **procedural memory** (the learned how-to), usually fed by episodic. This is a strong claim; the design must say *how* the refinement happens and *how* it's evaluated.
   - No → don't build procedural memory just because it sounds smart. A static, reliable agent beats a "self-improving" one that quietly drifts.

5. **Does the agent need to ground answers/actions in a body of domain facts or a curated corpus?**
   - Yes → **semantic memory** (RAG over a corpus / knowledge wiki / fact store). This is independent of Q1–Q4; even a stateless chatbot needs it.

6. **Is re-asking acceptable?** (The sanity check on Q2.)
   - If a user being asked the same thing twice is fine for this product → you may not need entity/profile memory even if sessions repeat.
   - If re-asking would erode trust or feel broken → entity/profile memory is load-bearing, not optional.

Routing summary: Q1 gates *durable memory at all*; Q2 → entity/profile; Q3 → episodic; Q4 → procedural; Q5 → semantic; Q6 sanity-checks Q2. Working/conversation memory is assumed in all cases.

### Worked example

*"A sales-outreach agent that wakes daily, picks accounts to follow up, drafts and sends messages, and adjusts its approach based on which messages get replies."*

- Q1: acts across sessions? **Yes** — it's long-horizon. Durable memory in play.
- Q2: continuity per account? **Yes** → entity/profile (what we know about each account, prior touches).
- Q3: remembers what it did? **Yes, critically** → episodic (which accounts were contacted, when, with what — without this it double-sends). Load-bearing.
- Q4: improves with experience? **Yes** ("adjusts based on replies") → procedural, fed by episodic. Design must say how the adjustment is learned and evaluated.
- Q5: grounds in a corpus? **Yes** → semantic (product facts, messaging guidelines).
- Q6: re-asking acceptable? **No** — re-contacting an account from scratch is a visible failure.

Verdict: four of five kinds load-bearing. This is a textbook claw, and the memory design *is* most of the design. Compare to a single-session "draft me one outreach email" task agent: only working memory + (optionally) semantic — every other answer is "no."

### Boundary cases that come up

**"Task agent that runs on a schedule"** — still a task agent *unless* it needs memory of prior task outcomes to do the next one well (Q3/Q4 = yes). Memory is what separates a cron'd task agent from a claw. If episodic/procedural light up, re-classify.

**"Conversational agent that should remember me next time"** — that's entity/profile memory crossing the session boundary. The class stays conversational; the memory call is what changes. Don't upgrade the whole class for one memory kind.

**"Co-pilot needs to know my preferences"** — check the host tool first. The editor, ticket system, or CRM may already persist what looks like entity memory. The *need* is real; the *new store* may not be.

**"We want it to get smarter over time"** — the procedural-memory tell. Pin down what "smarter" means and how it's measured *before* building procedural memory. An unmeasurable learning loop is failure mode A (built, never improves anything) or silent drift.

---

## The two failure modes

Symmetric, like the framework-vs-hand-roll cost framing. Both hurt; they hurt in opposite directions.

### Failure mode A — memory you didn't need

You built durable memory the workload didn't require. The bills:

- **Complexity.** A store, a retrieval path, an eviction/consolidation policy, and an extra failure surface — for state nobody reads usefully.
- **Staleness.** Persisted facts go wrong silently. The agent now confidently acts on last quarter's preference, last month's schema, a decision the user reversed. Stale memory is worse than no memory because it *looks* like knowledge.
- **Privacy / PII surface.** The moment you persist facts about users, you own a data-protection problem: retention, deletion, access scoping, tenant isolation. Entity/profile memory in particular is a PII store by definition. Don't open that surface unless the product needs it.
- **Retrieval noise.** Irrelevant retrieved memories crowd the context window and *degrade* answer quality. More memory does not monotonically improve an agent; past a point it actively hurts.

The tell: a memory store that's written to but whose contents never change a decision. If you can't name the decision the memory improves, you're in failure mode A.

### Failure mode B — missing memory you needed

You skipped durable memory the workload required. The bills:

- **Re-asking.** The agent asks for what it was just told. The single most common "this feels broken" signal from users.
- **No learning.** The agent that's done the task 200 times is no better than on attempt 1. The "it'll get smarter over time" promise made in the pitch never lands because there's nothing for it to get smarter *with*.
- **No cross-session continuity.** Every session starts cold. For a co-pilot or account agent, this caps usefulness hard — the human does the remembering the agent should have done.
- **The claw that resets every wake-up.** The worst version. An autonomous worker with no episodic memory redoes work, double-sends, drops follow-ups, and drifts — and because no human is in the per-turn loop, nobody notices until it's a mess. This is the failure that motivated this entry.

The tell: any sentence in the spec like "remembers," "learns," "knows the customer," "follows up," or "across sessions" with no memory design behind it.

---

## Hard rule for inception

**Every agent design must make an explicit memory call.** The output of the memory-decision step is never empty. Even the minimal answer — *"no memory beyond conversation history, because the agent is a single-session conversational agent that grounds nothing in a durable corpus"* — is a required, valid result. What is **not** valid is *silence*.

Memory silence is the bug this entry exists to kill. The observed failure pattern that motivates it: a classifier emits a state label (`state_shape`) and downstream steps drop it — the classification never flows into a named memory decision, producing a design that reads as if memory weren't a dimension. **A classification axis that doesn't flow into a named decision is decoration.** The fix is procedural:

1. **`state_shape` must produce a memory *recommendation*, not just a *label*.** Classifying an agent as `long-horizon` is the start of the work, not the end. The classification must flow into a named set of memory kinds (load-bearing / optional / unneeded) per the table above.

2. **The design must name each memory kind's status explicitly.** Working, episodic, semantic, procedural, entity/profile — each gets a verdict and a one-line reason. "Unneeded because X" is a fine verdict. Omission is not.

3. **A claw design with no episodic + semantic memory is rejected.** For `long-horizon` / autonomous-worker classifications, episodic and semantic memory are load-bearing. A design that doesn't specify them is incomplete and should be sent back, the same way a claw with no heartbeat or no escalation path is sent back.

4. **A "learns / improves / remembers the customer" claim with no backing memory kind is flagged.** If the spec promises learning, the design must name procedural (and probably episodic) memory and say how the refinement is evaluated. If it promises per-user continuity, it must name entity/profile memory. Unbacked claims are failure mode B waiting to ship.

5. **Tool selection is deferred, not skipped.** This step decides *what kind* of memory. It then hands off to `memory-architecture-selection.md` for *how to build it* (store, framework, checkpointer, consolidation policy). Naming the kind without the tool is fine here; naming neither is the bug.

---

## Does memory need fall cleanly out of `state_shape` + class?

**Mostly — but not cleanly enough to skip a dedicated step.** `state_shape` + class is a strong *prior*: it reliably pins down *working* memory and reliably flags when *episodic* memory becomes load-bearing (long-horizon → yes). For four of five memory kinds, the class table above gets you most of the way.

The leak is in the two kinds that depend on facts the class label doesn't carry:

- **Procedural memory turns on "does it learn?"** — and *learning is not implied by state shape.* A `long-horizon` claw can be deterministic-and-static (no procedural memory) or self-improving (procedural memory load-bearing). A `stateless`-per-task agent can *also* learn across tasks, which is exactly the boundary case where it's quietly becoming a claw. State shape doesn't see this; the "does it improve with experience?" question (Q4) does.
- **Semantic memory turns on "does it ground in a corpus?"** — which cuts *across* state shape entirely. A stateless chatbot needs it; a long-horizon claw needs it; a session-scoped conversational agent may or may not. It's a function of the *domain*, not the *temporal shape*.

The resolution: **`state_shape` is necessary but not sufficient.** It's the right prior and cleanly handles working + episodic memory, but two additional signals are required to make memory need fall out deterministically: a **`learns_from_experience` binary** (does the agent improve over time?) to resolve procedural memory, and a **domain-grounding question asked independently of state shape** (does the agent ground in a corpus? — often already implied by tool/RAG presence) to resolve semantic memory. With those two signals alongside `state_shape`, the memory decision becomes a lookup against the class table rather than a judgment call. Without them, procedural and semantic memory are the two kinds most likely to be silently dropped.
