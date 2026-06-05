---
title: What kind of agent are you building?
category: decision-guides
status: draft
last_updated: 2026-05-29
source_findings: []
source_external: []
applies_when:
  workloads: [any]
  constraints: [first-pass-classification]
contradicts: []
related:
  - decision-guides/cost-vs-latency-tradeoffs
  - decision-guides/does-this-agent-need-memory
  - harnesses/landscape-2026-may
  - harnesses/agentforce-deep-dive
snapshot_date: 2026-05-29
---

# What kind of agent are you building?

This is the **first-pass classification** every other decision flows from. Architecture, runtime, memory pattern, observability scope, deployment shape, evaluation strategy — all of them branch on what *class* of agent the build is. Get this wrong and the rest of the decisions don't compose.

The discovery-inception pipeline's `workload_classifier` step is the codified version of this guide. When you're outside that pipeline — reading a transcript, scoping a project before chat-fill, sanity-checking an inception output — this is the cheat-sheet to run through your head.

Five classes. They're not crisp partitions — real agents land on a continuum and sometimes shift class as the spec sharpens. But the differences in architecture/runtime/memory are large enough that "which class is dominant" is a load-bearing call.

## The five classes

| Class | One-liner | The defining property |
|---|---|---|
| **Chatbot** | Answers questions from a fixed knowledge base | No persistent state between turns; no actions |
| **Conversational agent** | Talks to data / talks to humans, possibly with tools | Multi-turn state; reads-mostly; humans drive turn-taking |
| **Task agent** | Completes a discrete bounded job per invocation | Stateless per task; clear definition of done; humans gate retries |
| **Co-pilot agent** | Assists a human in real time, sidecar style | Operates *alongside* a human in their tool; ephemeral state; trust depends on UX |
| **Autonomous worker** ("claw") | Acts on its own schedule, possibly indefinitely | Durable state; self-triggered; heartbeat + memory + recovery |

Each row implies a different default architecture, runtime, memory pattern, and failure-mode posture. The rest of this entry expands each row.

---

## Chatbot

**Definition:** A retrieval-augmented Q&A system over a known corpus. Answers come from documents, FAQ entries, or a curated knowledge base. No actions, no side effects, no real reasoning about the world — just *"find the answer and phrase it well."*

**What it is NOT:** Anything that takes actions. Anything that maintains state across user sessions. Anything that needs to reason about evolving inputs.

**Defining property:** Each turn is essentially independent. Same question → same answer. The "agent" is really a retrieval system wearing a conversational coat.

**Typical architectures:**
- RAG over a vector store + LLM-as-rephraser
- LLM with tool: search_docs(query) → return passages
- Single-LLM-call with the corpus prepended for small corpora

**Memory pattern:** Conversation history (last N turns) for coherence. No durable state.

**Observability:** Track retrieval quality (was the right doc found?) and answer faithfulness (did the LLM stick to the retrieved content?). Don't track agent state — there isn't any.

**Failure modes:** Hallucinated answers when retrieval misses, stale-knowledge problem when the corpus drifts, citation drift (LLM invents source attribution).

**When this is wrong as a classification:** The moment the agent has to *do* anything — write to a system, kick off a workflow, decide between paths based on prior turns — it's not a chatbot anymore. Be careful with "intelligent FAQ" projects that quietly grow into conversational agents.

**Don't reach for:** Persistent state stores, durable execution, multi-step planning, heavyweight orchestration frameworks.

---

## Conversational agent

**Definition:** A multi-turn agent that reasons about an evolving context, may call tools to read external data, and produces answers grounded in what it has gathered. The human drives turn-taking. The agent does not act unilaterally — it answers, asks clarifying questions, surfaces options.

**Examples in the wild:** *"Talk to your data"* analytics agents (text-to-SQL with semantic understanding), SE/support co-pilots that pull context and draft responses for a human to send, research assistants that gather + summarize.

**Defining property:** Multi-turn state matters (the agent remembers what it learned in turn 3 when answering turn 7), but the agent reads-mostly and the human owns the actions.

**Typical architectures:**
- Single-agent ReAct loop with read tools (search, query, fetch)
- LangGraph state machine for more complex routing (intent → tool selection → answer construction)
- Claude Agent SDK with skills for repeated capability patterns

**Memory pattern:** Conversation history is the primary state. Sometimes a per-session "scratchpad" or working theory. Episodic memory across sessions is rarely needed.

**Observability:** Per-turn latency, tool-call efficiency, answer grounding (did it cite real retrieved data?), conversational coherence over long sessions.

**Failure modes:** Context window saturation, tool-call loops on bad queries, stale-context (acting on something the user said 20 turns ago that no longer applies), confident-wrong answers when no tool returned the right data.

**When this is wrong as a classification:** If the agent is expected to take material actions (write to a system, send messages externally, modify state others depend on), it's a task agent or co-pilot, not a conversational agent. If it operates without a human turn-driving it, it's an autonomous worker.

**Don't reach for:** Durable workflow engines, heartbeats, complex memory architectures — unless something specific demands them.

---

## Task agent

**Definition:** Given a well-defined job, complete it and return. The job has a clear input, a clear definition of done, and a bounded scope. The agent may take multiple steps and tool calls internally, but from the outside it's *"send job → receive result."*

**Examples in the wild:** *"Generate a draft contract from this RFP,"* *"Reconcile these two ledgers and flag mismatches,"* *"Triage this support ticket and route to the right team."* Anything that fits the shape of a function call where the function happens to take an LLM thirty seconds.

**Defining property:** Stateless per task. The agent doesn't remember prior tasks. Definition-of-done is concrete enough to evaluate deterministically (did the contract draft compile? did the reconciliation surface real mismatches?).

**Typical architectures:**
- Inner pipeline (deterministic orchestrator calling LLM sub-steps)
- Single-agent ReAct with bounded tool palette
- LangGraph for tasks with branching workflows (route → enrich → validate → emit)
- Claude Agent SDK with subagents for decomposable jobs

**Memory pattern:** Per-task scratchpad only. No durable cross-task memory unless tasks explicitly share context (in which case reconsider — that may be a conversational agent or co-pilot).

**Observability:** Task success rate (deterministic where possible), per-task cost and latency, tool-call efficiency. Set a hard timeout — task agents that don't terminate are the most common production failure.

**Failure modes:** Indefinite loops on ambiguous inputs, partial-completion (agent thinks it's done when it isn't), silent fallback to LLM-generated dummy data when a tool fails.

**When this is wrong as a classification:** If the job has no clear definition of done, it's a conversational agent or co-pilot. If the job triggers itself on a schedule, it's an autonomous worker. If a human stays in the loop for each step, it's a co-pilot.

**Don't reach for:** Conversational state, episodic memory, heartbeats — unless the task genuinely requires resumability across long-running operations (in which case lean into durable execution, not memory).

---

## Co-pilot agent

**Definition:** Operates **alongside** a human in their tool of choice. The human drives the work; the agent assists in real time. The agent suggests, drafts, completes, annotates — the human decides what to keep.

**Examples in the wild:** Claude Code (alongside a developer in a terminal), Cursor / Copilot (alongside in an editor), Google Docs AI suggestions (alongside in a writer), a triage co-pilot inside a support agent's existing ticket UI.

**Defining property:** The agent is **not the surface.** Someone else's tool (an IDE, a doc editor, a ticket UI, a CRM) is. The agent's value is measured by how much it accelerates the human's primary task without getting in the way.

**Typical architectures:**
- Claude Agent SDK pattern (rich tool use, skills, hooks, MCP)
- Inline LLM calls with structured outputs embedded in the host tool
- Multi-modal agents when the host tool exposes images / canvas / spatial context

**Memory pattern:** Per-session ephemeral state. Persistence happens in the host tool (the developer's git history, the writer's document, the agent's ticket trail) — the agent rarely needs its own durable store.

**Observability:** Acceptance rate (suggestions accepted vs rejected), time-saved metrics, intrusiveness signals (how often does the human dismiss?). User trust is the load-bearing metric, not raw accuracy.

**Failure modes:** Being annoying (suggestions when none are wanted), being slow (suggestions arrive after the human has moved on), being confidently wrong in ways the human doesn't catch, ruining the host tool's UX (e.g., cluttered IDE, broken keyboard flow).

**When this is wrong as a classification:** If the agent IS the surface (its own UI), it's a conversational agent. If the agent takes actions without the human at the keyboard, it's an autonomous worker. If invocations are discrete jobs rather than continuous accompaniment, it's a task agent.

**Don't reach for:** Heavyweight memory architectures, durable workflow engines — the host tool owns durability.

---

## Autonomous worker ("claw")

**Definition:** An agent that runs **on its own schedule or trigger**, possibly indefinitely. Wakes itself up, decides what to do, takes actions, and persists state across invocations. There is no human in the per-turn loop; humans set up the agent, audit it, and intervene when something looks wrong.

**Examples in the wild:** Long-running data quality monitors that act on drift, autonomous trading bots, sales-outreach agents that send follow-ups on schedules, customer-success agents that escalate at-risk accounts, evergreen content updaters.

**Defining property:** **Durable state + self-triggered.** The agent has memory that persists across wake-ups, a heartbeat or cron or event trigger that brings it back to life, and a recovery posture for partial-completion across restarts. Removing any one of these breaks the model.

**Typical architectures:**
- Temporal / Dapr workflow engines for durable orchestration
- LangGraph with persistent checkpointer + scheduled triggers
- Custom orchestrator over a job queue + state store
- Multi-agent supervisor patterns when the work decomposes

**Memory pattern:** **Episodic memory** is load-bearing — the agent remembers what it did last week, what worked, what failed, what the user reacted well to. Some implementations layer semantic memory (learned patterns) on top of episodic.

**Observability:** Heartbeat health, action authorization audit trails, intervention rate (how often did a human have to step in?), drift detection (is the agent's behavior changing over time?), cost-per-day trends.

**Failure modes:** Runaway loops (the most expensive failure mode in agents — autonomous + LLM = costly bugs), silent drift (agent quietly stops doing useful work), unauthorized actions, identity/permission leakage, debugging-blindness (no one watches the agent until something breaks badly).

**When this is wrong as a classification:** If a human triggers each task, it's a task agent. If the agent only acts during a conversation, it's conversational or co-pilot. If it runs on a fixed schedule but each invocation is a discrete bounded job with no memory of prior invocations, it's task agent + scheduler, not a claw.

**This class is the most failure-prone.** When the spec smells like claw, treat that as a yellow flag — verify the spec hasn't underspecified guardrails, escalation paths, and intervention surfaces. Most "autonomous agent" proposals in mid-2026 are actually task agents with schedules, and that simpler classification ships safer.

---

## How to use this taxonomy

### As a discovery checkpoint

When chat-filling a spec, run the answers against the five classes. Ask: *which class does this most resemble?* If the answer is "more than one," that's a signal the spec hasn't converged — surface it as a gap for the customer to resolve, don't paper over it.

### As an inception input

The `workload_classifier` step expects you to identify the class explicitly. The `architecture_proposer` and `runtime_proposer` branches read the class as their primary anchor. A misclassified workload propagates through every downstream proposal.

### As a guardrail against over-engineering

The most common error is **classifying up** — calling something a co-pilot when it's a conversational agent, calling something an autonomous worker when it's a task agent on a cron. Each step up the chain adds infrastructure cost. When in doubt, classify **down** and add complexity only if specifics demand it.

### As a guardrail against under-engineering

The complementary error is **classifying down** — calling something a task agent when it's actually an autonomous worker because the spec didn't surface that someone wanted it to run on its own. Common in claw-shaped builds where the customer says "we want it to handle X" and what they mean is "we want it to handle X without us watching." Probe for the trigger model explicitly: *what wakes the agent up?*

---

## Boundary cases that come up

**"Conversational agent that takes actions on the human's behalf"** — usually a co-pilot, not a conversational agent. The action-taking pushes it past read-mostly.

**"Task agent that runs on a schedule"** — usually still a task agent + scheduler, not a claw, *unless* the task agent needs memory of prior task outcomes to do the next one well. Memory is the tell.

**"Co-pilot that runs in the background without a human present"** — that's not a co-pilot; the host-tool surface is missing. Re-classify as task agent or claw.

**"Chatbot with one tool"** — almost certainly a conversational agent. The tool moves it past pure retrieval.

**"Multi-agent system"** — multi-agent is an architecture, not a class. Any of the five classes can be implemented multi-agent. Don't let the architecture pick the class.

---

## What each class costs you to get wrong

| Misclassification | Cost when wrong |
|---|---|
| Chatbot → actually conversational | Under-engineered: missing tools, no state, frustrated users |
| Conversational → actually co-pilot | Wrong surface: built an app when you needed an IDE extension |
| Conversational → actually task agent | Over-engineered: ran a chat loop for a one-shot job |
| Task agent → actually claw | Under-engineered: no durable state, no heartbeat, agent doesn't know what it did yesterday |
| Co-pilot → actually conversational | Wrong measurement: measured accuracy instead of acceptance/non-intrusiveness |
| Claw → actually task agent on schedule | Over-engineered: ran Temporal for a cron job |

**Classifying up costs infrastructure. Classifying down costs production failures.** Both hurt; the second hurts louder.

---

## Open question — sub-class shape for multi-agent systems

Multi-agent is currently treated as an architectural choice within each class. As patterns/ deepens, we may want sub-class language ("supervisor-pattern conversational agent," "decomposed-tasks task agent") to capture the cross-cutting concerns specific to multi-agent designs within each class. Track as a v1.0 question, not a v1.0 blocker.
