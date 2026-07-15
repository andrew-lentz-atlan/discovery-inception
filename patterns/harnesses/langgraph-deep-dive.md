---
title: LangGraph — Builder's Deep Dive
category: harnesses
status: draft
last_updated: 2026-05-29
source_findings: []
source_external:
  - https://docs.langchain.com/oss/python/langgraph/overview
  - https://docs.langchain.com/oss/python/langgraph/graph-api
  - https://docs.langchain.com/oss/python/langgraph/persistence
  - https://docs.langchain.com/oss/python/langgraph/human-in-the-loop
  - https://docs.langchain.com/oss/python/langchain/agents
  - https://github.com/langchain-ai/langgraph/releases
applies_when:
  workloads: [graph-state-machine-agents, durable-multi-step-workflows, human-in-the-loop-pipelines, multi-agent-supervisor-systems]
  constraints: [team-on-python, explicit-control-flow-needed, durability-or-resumability-required, complex-routing-or-approval-gates]
contradicts: []
related: [harnesses/landscape-2026-may, decision-guides/what-kind-of-agent-are-you-building]
snapshot_date: 2026-05-29
---

# LangGraph — Builder's Deep Dive

The second per-framework deep-dive in `patterns/harnesses/`. Where Agentforce is a vertically-integrated *product*, LangGraph is the opposite end of the spectrum: a **low-level orchestration framework and runtime for long-running, stateful agents** that gives you the graph, the state, the checkpointer, and the interrupt primitive — and stays out of your way on everything else. It is the harness builders reach for when the agent's control flow is itself the product.

This entry exists because LangGraph sits in an awkward spot in the landscape — it looks superficially like "LangChain" but is a separate, much more opinionated runtime; it can express the same ReAct loop the Claude Agent SDK gives you in 5 lines, but its real reason for existing is the workloads where that loop isn't enough. Deciding *for* or *against* LangGraph requires understanding its reasoning model (explicit graph state machine, not a hidden loop), its durability story (checkpointers + threads), and its sharp edges (state-bloat, accidental cycles, checkpointer migration). None of that fits a comparison-table row.

## The core primitives

Every LangGraph application is built from six things:

| Primitive | What it is |
|---|---|
| **State** | A `TypedDict` (or dataclass / Pydantic model) describing the shared data structure that flows through the graph. Channels with `Annotated[T, reducer]` define how updates merge. |
| **StateGraph** | The graph builder. Parameterized by the `State` type. Holds nodes, edges, and entry/exit points until you compile it. |
| **Nodes** | Plain Python functions `(state, config, runtime) -> dict`. Return a partial state update; the reducer merges it. Can be sync or async. |
| **Edges** | Wires between nodes. Three kinds: static (`add_edge`), conditional (`add_conditional_edges` — a router function returns the next node's name), and the implicit edge from `START` / to `END`. |
| **Checkpointer** | Persistence layer. Saves a `StateSnapshot` at every "super-step." Backed by memory, SQLite, Postgres, or Cosmos DB. Required for interrupts, durability, time-travel, and conversational memory. |
| **Interrupt** | A function call inside a node that pauses the graph, persists state, and surfaces a value to the caller. Resumes via `Command(resume=value)` on the same `thread_id`. |

The compile step (`builder.compile(checkpointer=...)`) is where the graph becomes runnable and where structural validation happens. **You MUST compile your graph before you can use it** — the docs are explicit about this because the failure mode of forgetting is silent: you call `.invoke()` on an uncompiled `StateGraph` and get a confusing attribute error.

## The reasoning model — explicit state machine, not a hidden loop

This is the single most important thing to internalize about LangGraph, and the place where most teams initially get it wrong by mental-modeling it as a fancier LangChain agent.

**Claude Agent SDK and OpenAI Agents SDK give you a loop you configure.** You write a system prompt, hand it a list of tools, set a max-iteration count, and the SDK runs `model → tool → model → tool → …` until the model stops calling tools. The loop is the harness's job. You think in terms of "what tools does this agent have."

**LangGraph gives you a graph you draw.** You define states (what data exists at each step), nodes (what computation happens), and edges (what transitions are allowed). The loop, if you want one, is an explicit edge from a node back to itself — visible, version-controlled, debuggable in LangGraph Studio as an actual diagram. You think in terms of "what is the control flow of this workflow."

The trade is straightforward:
- The Agent SDK style is shorter, faster to prototype, and right for the large class of agents that genuinely are "talk to the model in a loop with tools."
- The LangGraph style is longer, more explicit, and right when the control flow has structure the model shouldn't have to re-derive each turn — approval gates, parallel branches, retry-with-different-strategy, supervisor-over-workers, durable multi-day workflows.

A useful tell: if drawing your agent on a whiteboard requires more than "model in the middle, tools around it," LangGraph's structure starts paying for itself. If the whiteboard drawing is "model in the middle, tools around it," you'd be fighting the framework.

For the simplest case, LangGraph ships a prebuilt: `from langgraph.prebuilt import create_react_agent` returns a compiled graph that is exactly a ReAct loop. People reach for it as a sanity check ("can I rebuild what the Agent SDK gives me?") and then graduate to a custom `StateGraph` as their control flow grows.

## The minimum viable agent

A complete, runnable graph with two nodes, a conditional edge, a checkpointer, and a thread-scoped invocation:

```python
from typing import Annotated, Literal
from typing_extensions import TypedDict
from operator import add

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langchain.chat_models import init_chat_model

class State(TypedDict):
    messages: Annotated[list, add]   # reducer: append, don't overwrite
    needs_human: bool

llm = init_chat_model("anthropic:claude-opus-4-7")

def respond(state: State) -> dict:
    reply = llm.invoke(state["messages"])
    return {
        "messages": [reply],
        "needs_human": "ESCALATE" in reply.content,
    }

def escalate(state: State) -> dict:
    return {"messages": [{"role": "system", "content": "Handing off to a human."}]}

def route(state: State) -> Literal["escalate", END]:
    return "escalate" if state["needs_human"] else END

builder = StateGraph(State)
builder.add_node("respond", respond)
builder.add_node("escalate", escalate)
builder.add_edge(START, "respond")
builder.add_conditional_edges("respond", route)
builder.add_edge("escalate", END)

graph = builder.compile(checkpointer=InMemorySaver())

config = {"configurable": {"thread_id": "user-42"}}
out = graph.invoke({"messages": [{"role": "user", "content": "hi"}], "needs_human": False}, config)
```

Four things to internalize from this snippet:

1. **`Annotated[list, add]` is the reducer.** Without it, every node return value would *overwrite* `messages` instead of appending. Forgetting the reducer is the #1 bug in first LangGraph agents.
2. **`thread_id` is the persistence primary key.** The same `thread_id` resumes a session; a new one starts fresh. No `thread_id`, no persistence and no interrupts.
3. **`START` and `END` are sentinels**, imported from `langgraph.graph`. They are nodes you don't write — they're the implicit entry/exit.
4. **The graph is data**, not a function. You build it, compile it, then invoke it many times.

## Production patterns

### Durability via Postgres checkpointer

For anything past a notebook, swap `InMemorySaver` for `PostgresSaver` (from `langgraph-checkpoint-postgres`). The same graph code runs unchanged. Pending writes survive process crashes: if a node fails mid super-step, on resume the completed nodes don't re-execute — LangGraph picks up exactly where the failed node left off. This is the feature that makes multi-hour workflows feasible without writing your own state machine.

`AsyncPostgresSaver` for async workloads; `AsyncSqliteSaver` for local dev with persistence. The interfaces match; choose by deployment target.

### Human-in-the-loop via `interrupt()`

The canonical approval pattern:

```python
from langgraph.types import interrupt, Command

def review_before_action(state: State) -> dict:
    proposed = state["proposed_action"]
    decision = interrupt({"action": proposed, "reason": "approval required"})
    # When resumed, `decision` becomes the resume value.
    if decision == "approve":
        return execute(proposed)
    return {"messages": [{"role": "system", "content": f"Rejected: {decision}"}]}

# Caller side:
result = graph.invoke(inputs, config)
if "__interrupt__" in result:
    # Surface to a human, collect their answer, then:
    graph.invoke(Command(resume="approve"), config)
```

Two sharp edges most teams hit:

- **The node restarts from the top when resumed.** Anything before the `interrupt()` call runs *again*. Treat code-before-interrupt as idempotent setup, never as a side-effecting step.
- **Interrupts require a checkpointer.** With `InMemorySaver` they survive within the process; with `PostgresSaver` they survive across process restarts, which is the actual point.

### Time-travel and forking

`graph.get_state_history(config)` returns every checkpoint in a thread. You can re-invoke from any of them, or call `graph.update_state(config, values=...)` to patch state at an old checkpoint and create a new branch. This is the killer feature for debugging non-deterministic agent failures: when an LLM does something wrong, you can replay from the checkpoint before the wrong call, edit the prompt, and re-run — without redoing the 14 steps that came before.

### Multi-agent supervisor pattern

LangGraph supports several multi-agent topologies. The two that matter:

- **Supervisor** — one orchestrator node routes to one of N worker subgraphs based on intent. The `langgraph-supervisor` package wraps this pattern; underneath it's a regular `StateGraph` with a router node and worker nodes that are themselves compiled graphs (subgraphs are first-class).
- **Swarm** — workers hand off to each other directly via the `Command(goto="other_worker", update={...})` primitive, with no central orchestrator. The `langgraph-swarm` package is the canonical implementation.

Both are sugar over the same graph primitives. Build with the prebuilts first; drop down to hand-rolled `StateGraph` when you need control they don't expose.

### Streaming

`graph.stream(...)` emits events as the graph runs. Modes: `"values"` (full state after each node), `"updates"` (just deltas), `"messages"` (token-by-token from LLM calls). The v3 stream API (recent — 2025) surfaces interrupts alongside tokens, which is what makes streaming UIs with mid-stream approval gates actually buildable.

## Failure modes and gotchas

1. **Missing reducer = silent overwrite.** A `list` field without `Annotated[list, add]` gets overwritten by each node's return. Symptom: your `messages` channel only ever contains the most recent message. Always declare reducers explicitly; default behavior is overwrite.

2. **State bloat.** Every checkpoint serializes the entire state. Putting large blobs (raw HTML, embeddings, PDF bytes) directly in state and then running a 30-step workflow generates 30 copies in the checkpointer. Use external storage (S3, object store) and put references in state, or use `DeltaChannel` for append-heavy fields.

3. **Accidental cycles → infinite loops.** Conditional edges that don't have a guaranteed exit will run forever (or until you hit the recursion limit, default 25). Always have a counter in state and a route that returns `END` when it's exceeded.

4. **`@tool` vs node confusion.** `langchain.tools.tool`-decorated functions are LLM-callable tools; they are *not* graph nodes. A node is a Python function added with `builder.add_node(...)`. A common mistake: decorating a node with `@tool` and then wondering why the graph never calls it.

5. **Checkpointer schema migration is real pain.** When you change the `State` TypedDict shape, old checkpoints in your Postgres don't auto-migrate. Either version your `thread_id` namespace, or build a one-shot migration script before deploying. The docs are quiet on this; the operational burden is not.

6. **`JsonPlusSerializer` doesn't handle everything.** Pandas DataFrames, custom classes without `__dict__`, NumPy arrays — these fail to serialize. The escape hatch is `pickle_fallback=True`, which works but introduces a "anyone with write access to the checkpoint store can execute code" security surface. Prefer keeping state JSON-clean.

7. **Subgraph namespace collisions.** When a subgraph and parent share a state key without a reducer, the subgraph's value silently overwrites the parent's on exit. Either namespace your subgraph state explicitly, or be deliberate about which keys cross the boundary.

8. **Debugging the graph isn't print-debugging.** Because nodes can run in parallel and state merges via reducers, `print(state)` inside a node doesn't show you the post-merge value the next node will see. Use LangGraph Studio's visual debugger or `graph.get_state(config)` after the fact.

9. **Cost of the `langchain` dependency.** `langgraph` itself is small; pulling in `langchain` (which most builders do, for `init_chat_model` and tool integrations) brings a large transitive tree. CI cold-install times can balloon to several minutes. Pin and cache aggressively.

10. **Studio is local-first; production observability lives in LangSmith.** LangGraph Studio is great for development (visual graph, replay, state inspection) but it runs against `langgraph dev`. For production traces, you need LangSmith — which is a paid product, free tier is limited.

## When to choose LangGraph

- Your agent's control flow has **structure the model shouldn't re-derive each turn** — explicit approval gates, parallel branches, retries with different strategies, supervisor-over-workers.
- You need **durable execution**: the workflow runs for minutes to days, may span machine restarts, and must not lose work on failure.
- You need **human-in-the-loop at arbitrary points** in a multi-step process — not just "show the user the final answer," but "pause halfway, get input, continue."
- You need **time-travel debugging** — replay from any checkpoint, fork, edit state, re-run.
- You're building a **multi-agent system** with explicit supervisor or swarm topology and want a runtime that knows about handoffs.

## When *not* to choose LangGraph

- **Simple ReAct loop** — model + tools + loop until done. Use the Claude Agent SDK or OpenAI Agents SDK; you'll write 80% less code and the abstraction matches the problem.
- **Salesforce-resident** — use Agentforce; the governance, identity, and CRM grounding aren't worth replicating.
- **Snowflake/Databricks-resident analytics agents** — Cortex Agents / Genie are warehouse-resident, governance-inherited, and don't require you to move data out. LangGraph can call them as tools, but standing up LangGraph as the *primary* harness for a "talk to the warehouse" use case is over-engineering.
- **Single-shot generation** — RAG-and-respond, summarization, classification. A direct model call (or a chain) is fine; the graph machinery is overhead.
- **Team has no Python depth.** LangGraph is a Python framework with real abstractions. It is not a no-code product. If the building team is admins, look at Agentforce or platform-resident options.

## Atlan integration shape (neutral)

LangGraph itself has no opinion about Atlan. It consumes metadata the same way it consumes any other context: as Python objects flowing through state, or as the return values of tool calls inside nodes. Three integration patterns are available to a LangGraph builder who wants Atlan-grounded behavior:

- **Atlan MCP server as a tool source.** LangGraph nodes can call any MCP server; Atlan's MCP exposes search/lookup/lineage tools that a node can invoke. Standard MCP client wiring — nothing LangGraph-specific.
- **pyatlan / MDLH from inside tool nodes.** A node is just a Python function; it can use `pyatlan` for targeted reads or writes (creating assets, updating CM, traversing lineage) or run a SQL query against MDLH for bulk metadata pulls. The result lands in state via the node's return value.
- **Context-repo loading at graph construction.** Domain prompts, glossaries, or ontologies sourced from an Atlan-backed context repo can be loaded once at startup and injected into the system prompt of model-calling nodes. No runtime calls.

None of these require LangGraph. None require Atlan. They're the surface where the two meet if a builder chooses to combine them.

## Maturity and ecosystem snapshot (mid-2026)

- **Version line:** stable on the `1.x` track. Recent (May 2025) shipped `1.2.x` with durable error-handler resume across host crashes and `set_node_defaults()` on `StateGraph`. The `langgraph-sdk` 0.4.0 brought websocket streaming, reconnection hardening, and sync subgraph support. As of mid-2026 the API surface has stabilized — breaking changes are now rare.
- **Documentation:** consolidated under `docs.langchain.com` (the old `langchain-ai.github.io/langgraph/` URLs redirect). Coverage is good for primitives, weaker on operational topics like checkpointer migration and large-scale debugging.
- **Studio + LangSmith:** Studio is the visual debugger (free, local); LangSmith is the production traces / evals / deployment product (paid, with a free tier). Strong integration — LangGraph is the most observable agent framework if you're willing to pay for LangSmith.
- **Deployment:** `langgraph dev` for local, `langgraph up` for production-like Docker testing, **LangGraph Platform** (managed) and **LangGraph Server** (self-hosted) for production. Self-hosting is straightforward; the managed offering is a meaningful uplift for teams that don't want to operate Postgres-checkpoint infrastructure themselves.
- **Community:** the agent framework with the largest GitHub footprint as of mid-2026; corresponding signal-to-noise tradeoff in community examples — lots of out-of-date 0.x code still in circulation. Anchor on official docs and prebuilts (`create_react_agent`, `langgraph-supervisor`, `langgraph-swarm`) rather than blog posts.
- **Customer signal:** Lyft's self-serve AI agent platform (May 2026 LangChain blog), Klarna, Replit, AppFolio, Elastic — all using LangGraph in production. The "is this real" question is settled; the "is it the right tool for *my* problem" question is what this entry is for.

## The fair "isn't this just LangChain?" question

No, and the confusion is the framework's biggest naming tax. LangChain is the higher-level library with chains, agents, retrievers, integrations. LangGraph is the lower-level runtime — graph + state + checkpointer + interrupt — that LangChain's agent abstractions are now built on top of. You can use LangGraph without using LangChain (though most builders pull in `langchain` for `init_chat_model` and tool definitions). You can use LangChain without using LangGraph (but the modern `create_agent` API in LangChain is itself a LangGraph wrapper, so the line is blurry).

Mental model: **LangChain is the library; LangGraph is the runtime.** When you read a comparison of "agent frameworks" and see both listed, they're not really alternatives — they're layers of the same stack. The decision is whether the LangGraph layer's opinions (graph, state, checkpointer, interrupt) match your workload, regardless of whether you're also using LangChain on top.
