---
title: Subagent vs skill vs memory-augmented subagent — decomposition trade-offs
category: decision-guides
status: draft
last_updated: 2026-05-29
source_external:
  - Anthropic — "Subagents in the SDK" (https://code.claude.com/docs/en/agent-sdk/subagents)
  - Anthropic — "Agent Skills in the SDK" (https://code.claude.com/docs/en/agent-sdk/skills)
  - OpenAI — "Handoffs" (https://openai.github.io/openai-agents-python/handoffs/)
  - OpenAI — "Agents as tools" (https://openai.github.io/openai-agents-python/agents/)
  - LangChain — "LangGraph multi-agent concepts" (https://langchain-ai.github.io/langgraph/concepts/multi_agent/)
  - LangChain — "LangGraph persistence" (https://langchain-ai.github.io/langgraph/concepts/persistence/)
applies_when:
  workloads: [any-multi-step-agent]
  constraints: [decomposition-decision-point]
contradicts: []
related:
  - decision-guides/what-kind-of-agent-are-you-building
  - anti-patterns/wasteful-subagent-context-reload
  - anti-patterns/over-decomposition
  - harnesses/claude-agent-sdk-deep-dive
  - harnesses/langgraph-deep-dive
  - harnesses/openai-agents-sdk-deep-dive
  - harnesses/pydantic-ai-deep-dive
  - harnesses/cortex-deep-dive
  - harnesses/genie-deep-dive
snapshot_date: 2026-05-29
---

# Subagent vs skill vs memory-augmented subagent — decomposition trade-offs

When inception's `architecture_proposer` or `orchestrator_stub` decides to "split off" some work into its own unit, there are at least **five distinct reasons** that lead to different right answers. The proposer today often produces a sub-agent because the decomposition *felt clean* — but "felt clean" is not actually one of the reasons that justifies a sub-agent. When you split for the wrong reason, you pay infrastructure cost for nothing, or worse, you abstract context away from the orchestrator that needed it.

This entry gives the proposer an explicit framework: name the reason before you pick the primitive, and let the reason select the primitive. The orchestrator_stub generator should refuse to emit a sub-agent that can't cite one of these five reasons.

## The five reasons matrix

| # | Reason for splitting | Right answer | Why it fits |
|---|---|---|---|
| 1 | Block conversational noise from the orchestrator | **Sub-agent** (ephemeral, fresh context) | Context isolation is the whole point |
| 2 | Logical decomposition felt clean | **Skill** (not a sub-agent) | Sub-agent buys nothing here; keep work in main context so the orchestrator can reason over it |
| 3 | Specialized tool surface (only this subtask needs Glean/MCP/SDK) | **Sub-agent with restricted tools** | Tool isolation, not context isolation |
| 4 | Parallelizable independent work (N similar items at once) | **Sub-agent** (fan-out) | Concurrency is the win |
| 5 | Each invocation has different durable state to carry | **Sub-agent with persisted memory** | Memory isolation, not context isolation |

The proposer today guesses based on architecture vibes. Make it cite the row, then pick.

---

## Reason 1: Block conversational noise

**What it looks like in a spec/workload:** a research-shaped subtask the orchestrator delegates that will read 30 files, run 12 searches, follow 4 dead ends, and then return a 200-token summary. If those 46 intermediate tool calls land in the orchestrator's context, the orchestrator's next turn pays for tokens it will never look at again — and worse, the orchestrator may get distracted by them when answering its real question.

**Why a sub-agent fits:** the Claude Agent SDK is explicit about this: *"Each subagent runs in its own fresh conversation. Intermediate tool calls and results stay inside the subagent; only its final message returns to the parent."* The whole point of the primitive is that the parent sees the *result*, not the *trajectory*. If you instead implemented this as inline tool calls in the orchestrator, every Read/Grep/WebFetch result accumulates in the main conversation.

**Failure mode when you pick wrong:** if you implement this as a skill (which expands into the main context), you blow up the orchestrator's token budget on intermediate artifacts. Skills are loaded on demand but their *execution* still happens in the main loop's context window — there's no isolation. For a high-fanout research subtask, this is the difference between "the agent works" and "the agent hits context_length_exceeded by turn 8."

---

## Reason 2: Logical decomposition felt clean

**What it looks like:** the proposer's writeup says something like *"and a separate sub-agent for the validation step"* or *"a sub-agent that handles report generation."* When you read it, you nod — yes, that's a separable unit of work. But ask: does the orchestrator need to *see* the result and reason over it? Almost always, yes. The validation result drives the next decision; the report content gets handed to the user. The orchestrator wants the actual content, not a summary.

**Why a skill fits:** a skill is a packaged capability with a `SKILL.md` brief that the model loads on demand. It runs *in the orchestrator's context* — same conversation, same tool results visible, same downstream reasoning. The orchestrator stays in charge and can chain the skill's output into whatever comes next without an extra round of summarization.

The Claude Agent SDK skill docs frame it as: *"Skills extend Claude with specialized capabilities that Claude autonomously invokes when relevant... model-invoked"* — the model decides when to load the skill content, but the content executes in the same loop. No subagent isolation, no separate fresh conversation. That's the entire point: you want the orchestrator to do the work with extra instructions, not to delegate the work away and lose visibility.

**Failure mode when you pick wrong:** you pay for a sub-agent's setup cost (the round-trip prompt construction, the cold-start token spend, the separate billing footprint per Claude Agent SDK note that *"subagents... their token usage rolls up to the parent's billing"*) and then the parent immediately needs to ask the sub-agent for "the actual content" because the summary lost the signal. You did two LLM passes to do one task. Worse, you've made the orchestrator's reasoning *shallower* — it can no longer cite specifics from the work it delegated.

**This is the most common architectural mistake the proposer makes.** When you see "split off X into a sub-agent" with no further justification, the prior should be: **make it a skill until proven otherwise**.

---

## Reason 3: Specialized tool surface

**What it looks like:** the orchestrator handles the high-level conversation, but one subtask needs access to tools the parent shouldn't have — a write-capable Atlan SDK client, an MCP server exposing destructive commands, Glean enterprise search with permission scopes the parent doesn't carry, or a vector-store-bound retriever that only this one subtask needs. Giving the parent every tool inflates the tool catalog the model has to reason over and risks the parent picking the wrong tool out of curiosity.

**Why a sub-agent fits:** sub-agents let you scope tool access. In the Claude Agent SDK: *"Subagents can be limited to specific tools, reducing the risk of unintended actions."* Example from the docs — *"a `doc-reviewer` subagent might only have access to Read and Grep tools, ensuring it can analyze but never accidentally modify your documentation files."* In LangGraph the same shape comes via a worker subgraph bound to a narrower toolset. In the OpenAI Agents SDK, you'd build a specialist `Agent` with its own `tools=[...]` list, then either hand off to it or expose it as a sub-tool.

**Failure mode when you pick wrong:** a skill alone can't restrict tool access. The Claude Agent SDK is explicit that the `allowed-tools` field in SKILL.md frontmatter *"is only supported when using Claude Code CLI directly. It does not apply when using Skills through the SDK"* — in SDK applications, tool restrictions live at the `query()` level, which is parent-wide. If you tried to use a skill for tool isolation, the model could still invoke the broader tool set; the skill's authoring guidance is advisory, not enforced. A sub-agent's `tools=[...]` is enforced.

**Practical pattern:** the sub-agent's role is *gatekeeping* the tool surface, not abstracting context. The orchestrator's prompt to the sub-agent should be specific enough that the sub-agent can complete in 1-3 tool calls and return concrete results. Don't conflate this case with Reason 1 — if the work is gatekeeping a tool, the result should still be detailed, not summarized.

---

## Reason 4: Parallelizable independent work

**What it looks like:** the workload has N similar items that need the same treatment — review 8 files for security issues, run 5 different lint checks on the same diff, fetch 12 pages and extract structured data from each. Sequentially this is slow; in parallel it's seconds.

**Why a sub-agent fits:** the Claude Agent SDK docs cite this directly: *"Multiple subagents can run concurrently, dramatically speeding up complex workflows. Example: during a code review, you can run `style-checker`, `security-scanner`, and `test-coverage` subagents simultaneously, reducing review time from minutes to seconds."* In LangGraph the equivalent is fan-out via parallel branches in the graph (a single super-step with N nodes, each invoking a worker). In OpenAI Agents SDK you can run several `agent.as_tool()` calls in parallel from a manager agent.

**Failure mode when you pick wrong:** a skill is invoked one-at-a-time by the model — there's no native concurrency primitive. You'd have to roll your own parallel execution outside the agent loop, which loses the agent's ability to react to partial results (e.g., short-circuit on the first failure). For genuinely independent fan-out, a sub-agent (or LangGraph parallel branch) is the correct primitive.

**Caveat:** if N is small (≤2) and the items aren't truly independent, the parallelization win doesn't justify the sub-agent overhead. The Claude Agent SDK docs note that *"subagents work well for a few delegated tasks per turn. For runs that coordinate dozens to hundreds of agents, use the `Workflow` tool, which moves the orchestration into a script the runtime executes outside the conversation context."* The fan-out shape has a sweet spot — small enough to keep one orchestrator, large enough to justify the overhead.

---

## Reason 5: Durable state across invocations

**What it looks like:** the same logical sub-agent needs to remember what it learned last time. A research agent that builds up a knowledge base across runs. A planning agent that tracks where it is in a multi-day workflow. A specialist that should pick up where it left off when re-invoked.

**Why a sub-agent with persisted memory fits:** you need a unit of work that has *its own* state separate from the parent's state, and that state has to survive across invocations. LangGraph is the canonical fit: the *checkpointer* primitive saves a `StateSnapshot` at every super-step, backed by Postgres or SQLite, with the result that a subgraph can be resumed exactly where it left off after a process crash. The Claude Agent SDK has a weaker version — subagents can be *resumed* within a session via `resume: sessionId`, and *"Subagent transcripts persist independently of the main conversation... they're stored in separate files"* — but durable cross-session memory is something you have to roll yourself via the `memory` field (`'user' | 'project' | 'local'`) plus your own state management.

**Failure mode when you pick wrong:** a skill has no state. A pure sub-agent (no checkpointer, no persisted memory) loses its conversation on every invocation — the next call starts fresh, the prior work is gone. If your spec includes *"the agent remembers what it did last week"* or *"resume the planning where the last call stopped,"* you need durable state and a primitive that supports it. LangGraph with a Postgres checkpointer is the strongest fit; rolled-your-own with the Claude Agent SDK is feasible but you're building the state layer.

This is the case that maps cleanly to the **autonomous worker ("claw")** class in `decision-guides/what-kind-of-agent-are-you-building.md` — the durable-state-plus-trigger pattern. Sub-agents with persisted memory are how multi-agent claws decompose.

---

## Cross-harness sub-agent semantics

The five-reason matrix applies regardless of harness, but each harness models the primitives differently. Pick the harness whose primitive shape matches the reason you're splitting.

### Claude Agent SDK — sub-agents as context isolators

The canonical "context isolation" primitive. The sub-agent is defined via `AgentDefinition` (programmatic) or `.claude/agents/*.md` (filesystem) and invoked via the `Agent` tool. The contract is sharp: *"A subagent's context window starts fresh (no parent conversation) but isn't empty. The only channel from parent to subagent is the Agent tool's prompt string."*

What the sub-agent receives: its own system prompt (`AgentDefinition.prompt`), the Agent tool's invocation prompt, project CLAUDE.md (if `setting_sources` loads it), and tool definitions (inherited or the subset in `tools`). What it does **not** receive: the parent's conversation history, the parent's tool results, the parent's system prompt, preloaded skill content unless explicitly listed in `AgentDefinition.skills`.

This is the canonical Reason 1 (block noise) and Reason 3 (specialized tool surface) primitive. Reason 4 (parallel) is supported natively. Reason 5 (durable state) is *not* — sub-agents can resume within a session but cross-session durable memory needs to be rolled yourself. **Hard limit:** *"Subagents cannot spawn their own subagents."* If your decomposition needs three levels of delegation, the second level must be sibling sub-agents from the parent, not nested. The recently-introduced `Workflow` tool (TypeScript SDK v0.3.149+) is the escape hatch for runs that coordinate "dozens to hundreds of agents" — it moves orchestration into a script the runtime executes outside the conversation context.

**Context isolation is the #1 bug class on this SDK.** The `claude-agent-sdk-deep-dive.md` entry calls it out: *"Subagent context isolation is silent. If you delegate to a subagent and the subagent doesn't have the information it needs (because the parent didn't pass it in the Agent tool prompt), the subagent will hallucinate or ask the parent — and the parent often doesn't know either."* Treat the delegation prompt as the complete brief; "Review the file" is useless, "Review `src/auth/login.py` for OAuth-token-handling issues, return findings with line numbers" is what works.

### LangGraph — subgraphs + checkpointers

Multi-agent in LangGraph is a graph topology, not a special primitive. The two prebuilt patterns: **Supervisor** (one orchestrator node routes to N worker subgraphs) wrapped by `langgraph-supervisor`, and **Swarm** (workers hand off to each other via `Command(goto="other_worker", update={...})`) wrapped by `langgraph-swarm`. Subgraphs are first-class — a worker is itself a compiled `StateGraph`, and state can be shared or namespaced across the boundary.

This is where Reason 5 (durable state) shines. The checkpointer primitive *"saves a `StateSnapshot` at every 'super-step.' Backed by memory, SQLite, Postgres, or Cosmos DB. Required for interrupts, durability, time-travel, and conversational memory."* A memory-augmented sub-agent in LangGraph is just a subgraph compiled with a `PostgresSaver` and addressed by `thread_id` — the persistence is native, not bolted on.

**The sharp edge for sub-agents:** *"Subgraph namespace collisions. When a subgraph and parent share a state key without a reducer, the subgraph's value silently overwrites the parent's on exit."* Either namespace your subgraph state explicitly, or be deliberate about which keys cross the boundary. This is the LangGraph equivalent of the Claude Agent SDK's "context isolation is silent" — same class of bug, different shape.

### OpenAI Agents SDK — handoff vs. agent.as_tool()

This is the framework where the decomposition decision matters most because there are **two distinct sub-agent primitives**:

- **`handoff()`** — *"a typed transfer of control from one agent to another. Exposed to the LLM as a tool named `transfer_to_<agent_name>`."* When agent A hands off to agent B, *"the receiving agent takes over the conversation, and gets to see the entire previous conversation history."* The current agent at any moment is *the* agent — no parent-child stack. The conversation moves.
- **`agent.as_tool()`** — wraps an agent as a callable sub-tool. *"Control returns to the caller after execution, the sub-agent doesn't take over the conversation."* Manager pattern: *"a central manager/orchestrator invokes specialized sub-agents as tools and retains control of the conversation."*

The `openai-agents-sdk-deep-dive.md` entry calls out the conflation as *"the most common architectural mistake: people reach for handoffs when they actually want sub-tools, and end up with conversations that ping-pong between agents instead of cleanly delegating sub-tasks."* The OpenAI docs themselves recommend `agent.as_tool()` *"if you want structured input for a nested specialist without transferring the conversation."*

Mapping to the five reasons:
- **Reason 1 (block noise)** → `agent.as_tool()`, because the sub-agent's transcript stays scoped.
- **Reason 2 (logical decomposition felt clean)** → neither; restructure as a longer single agent with better instructions.
- **Reason 3 (specialized tool surface)** → `agent.as_tool()` with a narrow `tools=[...]` on the specialist.
- **Reason 4 (parallel fan-out)** → parallel `agent.as_tool()` invocations from a manager.
- **Reason 5 (durable state)** → not natively supported; pair with sessions or an external store.

`handoff()` is for a different shape entirely — *"specialist routing, triage-then-deep-dive, multi-step workflows where each step wants its own tight system prompt and tool list."* It's a decentralized conversation graph, not a sub-task primitive. If you reach for it for Reason 1-5 you're using the wrong tool.

### Pydantic AI — RunContext.deps, not sub-agents

Pydantic AI does not have a strong sub-agent primitive. Its decomposition unit is the **structured-output skill** plus dependency injection via `RunContext.deps`. The `pydantic-ai-deep-dive.md` entry is honest about this: *"For cyclic or branching state machines, `pydantic-graph` is the companion package, but most production deployments stay flat ReAct."*

State this explicitly to the proposer: **if the harness choice is Pydantic AI, the right answer for almost any of the five reasons is "use tools, structured output, and `deps_type` injection," not "use a sub-agent."** For workloads that genuinely need sub-agent topology, the recommendation in `pydantic-ai-deep-dive.md` is to pair Pydantic AI with an external orchestrator (LangGraph or hand-rolled) rather than try to express it in the framework. Reason 5 (durable state) is partially served by Pydantic AI's mid-2026 durable-execution support, but long-horizon multi-agent state lives better in LangGraph or Temporal.

### Cortex / Genie — multi-agent is weak; skills as tools dominate

Per the `cortex-deep-dive.md` and `genie-deep-dive.md` entries: *"Multi-agent orchestration is weaker than dedicated frameworks. No first-class subagent topology, no A2A protocol, no native delegate-to-specialist pattern."* Cortex Agents can call tools (Cortex Analyst, Cortex Search, web search, generic stored-proc) but cannot natively delegate to another Cortex Agent. Genie does not orchestrate at all — the documented multi-agent pattern wraps Genie as one worker inside a LangGraph or DSPy supervisor.

Decomposition options in this harness family are constrained: **most cases collapse to "skills as tools"** — Cortex Analyst is the one well-instrumented skill in Cortex's catalog; Genie Space is the equivalent in Databricks. Reasons 1, 3, 4, 5 from the matrix push you to embed Cortex/Genie *as a tool* inside a real multi-agent framework (LangGraph fronting it via the Snowflake-managed MCP server, for example), not the other way around. The downstream `runtime_proposer` should default to this composition for anything past pure analyst Q&A.

---

## Class-by-class defaults

The five-class taxonomy in `what-kind-of-agent-are-you-building.md` shapes which reasons show up:

- **Chatbot:** rarely needs sub-agents. The work is "retrieve and answer." Skills are the unit of organization (one skill for retrieval, one for citation, one for follow-up). Reason 4 (parallel fan-out of search) might briefly justify a sub-agent for very fan-out-y retrieval, but usually parallel tool calls inside one loop are enough.

- **Conversational agent:** sub-agents for Reason 1 (block noise) when the read-mostly search/retrieval loop would noise the main conversation. Skills for everything else. The classic shape: a research sub-agent that fetches and summarizes, returning a short brief to the conversational orchestrator that owns turn-taking with the human.

- **Task agent:** sub-agents for Reason 4 (parallelizable independent steps) and Reason 3 (specialized tool surface for one sub-step). Skills for sequential reasoning. Don't over-reach for sub-agents here — a task agent's job is usually a pipeline, and pipelines compose better as skill chains than as sub-agent delegations, because the orchestrator wants to see the intermediate state to decide what to do next.

- **Co-pilot:** sub-agents for Reason 3 (specialized tool access — e.g., one sub-agent owns the codebase-search tools, another owns the linting tools) when the host-tool integration has natural tool boundaries. Skills for the host-tool integration glue itself. Claude Code is the reference build: it's mostly skills (`/init`, `/review`, `/security-review`, `/verify`) with sub-agents used for context-isolation when scanning lots of files (`code-reviewer`, `Explore`).

- **Autonomous worker ("claw"):** sub-agents with persisted memory (Reason 5) are common — each sub-agent owns one durable concern (memory, planning, execution). LangGraph with Postgres checkpointer is the canonical pattern. Each sub-agent has its own thread_id namespace; the parent supervisor reads their state to coordinate.

---

## Memory-augmented sub-agent design

When Reason 5 is the driver, the question becomes: how does the sub-agent's state persist, and how does the parent address it on the next invocation?

**LangGraph (canonical):** every compiled subgraph can be paired with a checkpointer. The thread_id is the address. Resuming a sub-agent is *"the same graph code runs unchanged. Pending writes survive process crashes: if a node fails mid super-step, on resume the completed nodes don't re-execute."* Time-travel debugging falls out of the same mechanism — `graph.get_state_history(config)` returns every checkpoint and you can re-invoke from any of them. This is the strongest memory-augmented-sub-agent story in the landscape.

**Claude Agent SDK (rolled-yourself):** sub-agent transcripts persist as files (*"automatic cleanup: transcripts are cleaned up based on the `cleanupPeriodDays` setting (default: 30 days)"*) and a sub-agent can be resumed within a session via `resume: sessionId` plus the `agentId` returned in the Agent tool result. The `memory` field on `AgentDefinition` accepts `'user' | 'project' | 'local'` — a memory source for the agent — but the cross-session durability story is not as native as LangGraph's checkpointer. You're combining session resume + your own state file + your own retrieval logic.

**OpenAI Agents SDK:** sessions persist conversation but the multi-agent memory story is weaker. For durable specialist state, pair with an external session backend or treat the sub-agent's state as a tool result you store yourself.

**Pydantic AI:** durable execution shipped mid-2026 but it's runtime durability (survive a worker crash mid-run), not "this sub-agent remembers last week's run." For the latter, externalize state into `deps`.

**Trade-off to surface:** native checkpointer = less code, more lock-in to the harness's serialization format and migration story. The `langgraph-deep-dive.md` entry flags this: *"Checkpointer schema migration is real pain. When you change the `State` TypedDict shape, old checkpoints in your Postgres don't auto-migrate."* Rolled-yourself memory = more code, but you control the schema. Pick by team's tolerance for migration pain vs. building.

---

## The "sub-agent abstracts real context away" failure mode

This is the subtler failure mode, and the one that catches proposer outputs that *technically* fit Reason 1 but actually shouldn't have been sub-agents.

The shape: the orchestrator delegates to a sub-agent and gets back only a summary. Sometimes the summary loses signal the orchestrator needed. A "search sub-agent" returns *"found 3 relevant docs about X"* — and now the orchestrator has to ask again to get the actual passages, because it can't quote or reason over content it never saw.

**The fix isn't "don't use a sub-agent" — it's "be deliberate about what the sub-agent returns to the orchestrator."** The Claude Agent SDK docs are explicit about this: *"The parent receives the subagent's final message verbatim as the Agent tool result, but may summarize it in its own response. To preserve subagent output verbatim in the user-facing response, include an instruction to do so in the prompt or `systemPrompt` option you pass to the main `query()` call."* The contract on what the sub-agent returns is part of the design, not an afterthought.

**Concrete pattern:** if the orchestrator will need to quote or reason over specifics, the sub-agent's `AgentDefinition.prompt` must instruct it to return structured content with the actual passages, not a summary. *"Return findings as a list of `{file_path, line_range, relevant_passage, finding}` records"* is what works. *"Summarize what you found"* is the trap.

If the work is genuinely *"give me a decision/recommendation, you decide what evidence to keep"* — that's a real Reason 1 case and a sub-agent is the right call. If the orchestrator needs the evidence too — that's Reason 2 in disguise and probably wants a skill, or a sub-agent that returns structured results rather than prose.

---

## Prompt caching as the economic mitigation

When sub-agents are unavoidable but expensive (re-loading large context every call), prompt caching is the way to make them economical. The `claude-agent-sdk-deep-dive.md` entry flags it: *"The `excludeDynamicSections` cache-sharing optimization is essential for fleets. Without it, two identical agents running from different cwds get different system prompts (because the preset embeds cwd, OS, shell, git status) and miss the prompt cache."*

A cache hit on a sub-agent's static system-prompt + tool-definition block pays back roughly 5-10× on repeat invocations. For high-frequency sub-agent fan-out (Reason 4) or persistent specialist patterns (Reason 5 where you re-invoke the same sub-agent across sessions), it's the difference between affordable and not. Deeper coverage belongs in a separate anti-pattern entry on wasteful re-loading; the brief note here is: **if the proposal includes high-fanout sub-agents, the runtime_proposer should also surface a prompt-cache strategy as a first-class output**.

---

## Decision tree

Walk it in order. The first match wins.

1. **Does the orchestrator need to reason over the raw output of this subtask?**
   → If yes: **Skill** (in-context, orchestrator sees content directly).
   → If no: continue.

2. **Does this subtask need isolation from the parent's chat history because of context-window pressure?**
   → If yes: **Sub-agent** (Reason 1 — block noise).
   → If no: continue.

3. **Does this subtask need tools the parent shouldn't have access to?**
   → If yes: **Sub-agent with restricted `tools=[...]`** (Reason 3 — tool isolation). Make sure the harness is one that enforces tool gating per sub-agent (Claude Agent SDK, LangGraph subgraph, OpenAI Agents SDK specialist).
   → If no: continue.

4. **Will this subtask be invoked N≥3 times in parallel with similar setup?**
   → If yes: **Sub-agent fan-out** (Reason 4 — concurrency). Pair with prompt caching if N is large.
   → If no: continue.

5. **Does this subtask need state that survives across invocations or sessions?**
   → If yes: **Sub-agent with persisted memory** (Reason 5 — LangGraph checkpointer, or rolled-yourself with Claude Agent SDK).
   → If no: continue.

6. **None of the above triggered, but the decomposition felt clean?**
   → **Skill.** Resist the urge to sub-agent. If you can't cite one of reasons 1-5, you don't have a sub-agent reason; you have a refactoring instinct that wants a skill body, not a separate conversation.

---

## Hard rule for the orchestrator_stub generator

When the proposer emits a sub-agent in `orchestrator.py`, it must cite the **reason number** from the five-row matrix. The orchestrator_stub generator should enforce this:

1. **Every sub-agent proposal must name a reason** (1, 2, 3, 4, or 5). If the reason isn't articulated, the proposer didn't actually decide — it pattern-matched on "decomposition vibes."

2. **If the cited reason is #2 ("logical decomposition felt clean"), REJECT the sub-agent proposal and emit a skill instead.** Update the SKILL.md inventory; remove the sub-agent from the orchestrator. This is the single most impactful rule for fixing today's proposer output.

3. **If the cited reason is #3 ("specialized tool surface"), the generator must explicitly scope the sub-agent's tool access** in the `AgentDefinition.tools` array (Claude Agent SDK), the subgraph's tool binding (LangGraph), or the specialist agent's `tools=[...]` (OpenAI Agents SDK). A sub-agent justified on tool-isolation grounds that inherits the parent's full tool set is misconfigured.

4. **If the cited reason is #5 ("durable state"), the generator must surface the persistence primitive explicitly** — checkpointer + thread_id (LangGraph), session resume + memory field + your own state layer (Claude Agent SDK), or external session store (OpenAI Agents SDK). A sub-agent justified on state grounds with no persistence wiring is a bug.

5. **If the cited reason is #1 ("block noise"), the generator must include explicit guidance in the sub-agent's prompt about what to return** to the orchestrator — structured records vs. prose summary, what to preserve verbatim, what to drop. Per the Claude Agent SDK docs, the delegation prompt is the *only* parent → sub-agent channel and the return contract is part of the design.

6. **The architecture_proposer should also stop using "sub-agent" as a default decomposition primitive.** When ambiguous, default to **skill**, then escalate to sub-agent only when one of reasons 1, 3, 4, or 5 fires.

Atlan note (kept neutral): when integrating with Atlan as a context layer, the choice still follows the matrix — Atlan-write tools (pyatlan SDK mutations) belong inside a sub-agent with restricted tool access (Reason 3) so the conversational orchestrator can't accidentally mutate; Atlan-read patterns (MDLH SQL templates) are usually skills (in-context, orchestrator reasons over results). The matrix doesn't change because the integration is Atlan-specific.
