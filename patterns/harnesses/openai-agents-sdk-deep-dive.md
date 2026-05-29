---
title: OpenAI Agents SDK — Builder's Deep Dive
category: harnesses
status: draft
last_updated: 2026-05-29
source_external:
  - https://openai.github.io/openai-agents-python/
  - https://openai.github.io/openai-agents-python/handoffs/
  - https://openai.github.io/openai-agents-python/guardrails/
  - https://openai.github.io/openai-agents-python/tools/
  - https://openai.github.io/openai-agents-python/tracing/
  - https://openai.github.io/openai-agents-python/sessions/
  - https://openai.github.io/openai-agents-python/running_agents/
applies_when:
  workloads: [multi-agent-handoff-orchestration, specialist-routing-agents, voice-realtime-agents, openai-stack-resident-agents]
  constraints: [team-on-openai-models, multi-agent-architecture-needed, python-native-orchestration, tracing-debug-loop-acceptable]
contradicts: []
related: [harnesses/landscape-2026-may, architectures/single-agent-react, decision-guides/what-kind-of-agent-are-you-building]
snapshot_date: 2026-05-29
---

# OpenAI Agents SDK — Builder's Deep Dive

OpenAI Agents SDK is the production-grade successor to **Swarm** (the 2024 educational/experimental release that introduced the handoff abstraction). It lives at a different altitude than LangGraph or the Claude Agent SDK: it's not a graph runtime and it's not "the agent loop as a thin loop." It is an **opinionated multi-agent harness whose first-class primitive is the handoff** — one agent transferring control to another specialist agent mid-conversation — wrapped in a deliberately small surface area Python developers can hold in their heads.

This entry exists because the landscape survey can't carry the depth needed to actually choose for or against the OpenAI Agents SDK on a given use case. Handoff semantics, guardrail tripwire mechanics, where traces go by default, what the `litellm` adapter does and doesn't give you — these matter, and they don't fit a row in a comparison table.

## The four primitives (OpenAI's framing)

Every workload built on this SDK is described in terms of four building blocks plus two runtime services. The SDK's design principle is published verbatim in the docs: *"Enough features to be worth using, but few enough primitives to make it quick to learn."*

| Primitive | What it is |
|---|---|
| **Agent** | An LLM with `instructions`, a list of `tools`, an optional list of `handoffs`, and an optional `output_type` (Pydantic model for structured output). |
| **Handoff** | A typed transfer of control from one agent to another. Exposed to the LLM as a tool named `transfer_to_<agent_name>`. |
| **Tool** | A Python function (`@function_tool`), a hosted OpenAI tool (web search, file search, code interpreter, image gen, computer use), an `agent.as_tool()` wrapper, or a `ComputerTool`/`ShellTool`/`ApplyPatchTool` local runtime tool. |
| **Guardrail** | An input or output validator that runs in parallel with (or before) the agent and can raise a *tripwire* to halt execution. |

Plus two cross-cutting runtime services:

| Service | What it does |
|---|---|
| **Sessions** | Conversation memory. Multiple backends: `SQLiteSession`, `RedisSession`, `SQLAlchemySession`, `MongoDBSession`, `DaprSession`, `OpenAIConversationsSession`, `EncryptedSession` wrapper. |
| **Tracing** | Built-in span capture for every LLM call, tool call, handoff, guardrail, and custom event. **Exports to OpenAI's backend by default.** |

The **Runner** is the orchestrator that owns the loop. You don't write the agent loop yourself — `Runner.run()` (async), `Runner.run_sync()`, or `Runner.run_streamed()` does. This is closer to Agentforce's Atlas posture than to LangGraph's "you describe the graph" posture, but at a much thinner altitude.

## The reasoning model — handoffs as a first-class primitive

The differentiator: **a handoff is not a sub-call, it's a transfer of control inside a single run.** When agent A calls the `transfer_to_b` tool, the Runner switches to agent B and continues the same loop with the same conversation. By default B sees the full prior history. The current agent at any moment is *the* agent — there's no parent-child stack, no nested call frame to unwind.

Compare:

- **Agentforce** classifies intent → picks a topic (effectively a routing sub-agent) → executes. Routing happens up front.
- **LangGraph** routes via explicit edges in a state machine you author. Routing is a graph property.
- **OpenAI Agents SDK** lets the *current* agent decide at any turn to hand off to a peer. Routing is an in-loop LLM decision exposed as a tool call.

This is the Swarm idea graduated to production: many small specialist agents, each with a tight system prompt and a narrow tool list, plus a triage/dispatcher agent at the front that mostly just hands off. The mental model is **a hand-off graph drawn by the LLM at runtime**, not a workflow you commit to in code.

## Minimum viable agent

```python
from agents import Agent, Runner, function_tool

@function_tool
def get_weather(city: str) -> str:
    """Return the current weather for a city. Use this when the user asks about weather."""
    return f"Sunny, 72F in {city}."

assistant = Agent(
    name="Assistant",
    instructions="You are a helpful assistant. Use tools when relevant.",
    tools=[get_weather],
)

result = Runner.run_sync(assistant, "What's the weather in Berlin?")
print(result.final_output)
```

That's the full surface. Add a second agent and a handoff and you have a multi-agent system:

```python
refund_agent = Agent(
    name="Refund Agent",
    instructions="Handle refund requests. Verify order ID before refunding.",
    tools=[lookup_order, issue_refund],
)

triage = Agent(
    name="Triage",
    instructions="Route the user to the right specialist. Hand off to Refund Agent for refunds.",
    handoffs=[refund_agent],
)

result = Runner.run_sync(triage, "I want to return order #4471.")
```

The Runner sees the `transfer_to_refund_agent` tool call, swaps the current agent to `refund_agent`, and continues the loop. `result.last_agent` tells you who finished.

## Production patterns

### Handoff design

- **Triage agents should have *no tools* — only `handoffs`.** Forcing the dispatcher to choose a handoff rather than answer prevents it from "absorbing" specialist work badly.
- **Use `handoff()` (the function) over passing raw Agent instances** when you need a callback, an `input_filter` to trim history, or a typed `input_type` for the model to fill in (e.g., `reason: str, priority: Literal["low","high"]`). The docs are explicit: `input_type` is for *model-generated metadata*, not application state — application state belongs in `RunContextWrapper.context`.
- **Name the handoff target agent clearly.** The tool exposed to the LLM is literally `transfer_to_<agent_name>`. Sloppy names produce sloppy routing.

### Structured outputs

`Agent(..., output_type=MyPydanticModel)` makes the final output a typed object. The Runner enforces schema via the OpenAI structured-outputs API. Combine with `output_type` on intermediate agents (e.g., a classifier agent with `output_type=Intent`) when you want determinism at hand-off boundaries.

### Parallel tool calls & concurrency

`RunConfig.max_function_tool_concurrency` caps how many function tools run in parallel within a single turn. Default is high; lower it if your tool implementations hit downstream rate limits or share mutable state. Hosted tools (web search, code interpreter) execute server-side and don't count against local concurrency.

### Guardrails as a cost lever

The input guardrail's first practical purpose isn't safety — it's **cost**. A cheap guardrail (e.g., `gpt-4o-mini` classifier deciding "is this a real coding question or off-topic noise") runs in parallel with the expensive primary agent. If the tripwire fires, `InputGuardrailTripwireTriggered` raises and you never burned the expensive tokens. Two modes:

- **Parallel (default)** — best latency, but if the tripwire fires *after* the agent already produced output, you've spent the tokens.
- **Blocking** — guardrail completes first. Zero waste if the tripwire fires, but adds its latency to TTFT.

Output guardrails always run after the agent completes — no parallel mode possible.

### Tracing for the debug loop

Every run produces a trace tree visible in the OpenAI dashboard: every LLM call, every tool call, every handoff, every guardrail decision. For multi-agent systems with handoff loops, this is the difference between a system you can debug and one you can't. The trace UI is genuinely the daily-driver tool for builders on this SDK — closer to Langfuse/LangSmith in posture than to Temporal's history view.

### Sessions as the persistence boundary

Sessions are the SDK's answer to "I don't want to thread `messages` through every call myself." Picking the backend is a real architectural decision, not a config detail:

- **`SQLiteSession` / `AsyncSQLiteSession`** — dev, single-process, local file or `:memory:`.
- **`RedisSession`** — multi-worker deployments. Shared memory across replicas; lose the Redis instance, lose the conversations.
- **`SQLAlchemySession`** — Postgres/MySQL-backed production. Audit-friendly, durable, the default "real-deployment" choice.
- **`OpenAIConversationsSession`** — server-managed by OpenAI. Zero infra to run, but ties session state to OpenAI's storage and pricing.
- **`DaprSession`** — cloud-native deployments. Useful when the rest of the app is already on Dapr.
- **`EncryptedSession`** — transparent encryption wrapper over any of the above. Use it when conversation contents are sensitive and the storage backend isn't already encrypted at rest.

Sessions are not free: every run prepends the full session history, so cost scales with turn count. Either trim explicitly (custom `Session` implementation) or summarize periodically — the SDK doesn't do this for you.

## Failure modes

1. **Handoff context bloat.** Default behavior: every handoff carries the *full* prior conversation forward. Five handoffs deep in a long session and your prompt cost grows linearly with turns × agents-touched. Fixes: `input_filter` on `handoff()` to drop pre-handoff turns, or the newer `RunConfig.nest_handoff_history` (beta) which collapses prior segments into `<CONVERSATION HISTORY>` summary blocks. The beta path is the right answer for long-lived sessions; the explicit filter is the right answer when you know exactly what each specialist needs.

2. **Guardrail-as-extra-LLM-call cost.** A guardrail that itself invokes a model is a model call. On a hot path with strict latency targets, the guardrail can dominate TTFT. Use the cheapest viable classifier (often a small model with a 1-token logit-bias trick) and prefer blocking mode only when the tripwire is meaningfully likely to fire.

3. **Tracing privacy default is "send to OpenAI."** Out of the box, traces — including LLM inputs, outputs, and function-call arguments — export to OpenAI's backend. Three knobs: `OPENAI_AGENTS_DISABLE_TRACING=1` env var to kill tracing entirely, `RunConfig.trace_include_sensitive_data=False` to redact LLM I/O and tool args from spans, or `set_trace_processors()` to replace the default exporter with your own (e.g., Langfuse, Arize, OTLP). **Organizations on Zero Data Retention agreements with OpenAI lose tracing entirely** — there's no ZDR-compatible OpenAI-hosted trace backend as of mid-2026.

4. **`max_turns` is your only infinite-loop guard.** Two agents that hand off to each other and never converge will burn turns until the cap. Default cap exists but is loose; tune it down explicitly for production. `MaxTurnsExceeded` is a real exception you need to handle.

5. **OpenAI lock-in is the default — `litellm` is the documented escape hatch.** The SDK is built around the OpenAI Responses/Chat Completions APIs. Non-OpenAI models go through the `litellm` third-party adapter (Anthropic, Bedrock, Gemini, OpenRouter, local Ollama, etc.). Functional, but: hosted tools (web search, code interpreter, file search) only work on OpenAI models; structured outputs behave differently per provider; tracing of non-OpenAI calls works but requires `set_tracing_export_api_key()` for the OpenAI dashboard to render them. If multi-provider is a first-class requirement on day one, LangGraph or a thinner harness is a better starting point.

6. **Sessions are persistent state — back them with something durable in production.** `SQLiteSession` is fine for dev. `RedisSession` / `SQLAlchemySession` / `OpenAIConversationsSession` (server-managed) are the real-deployment options. Sessions are not free: every run prepends the full session history, so cost grows with turn count unless you trim or summarize.

7. **Function-tool docstrings *are* the tool spec.** The SDK uses `inspect` + `griffe` to auto-generate JSON schemas from Python signatures and docstrings (Google, Sphinx, NumPy formats supported). A vague docstring produces a vague tool description, which produces an LLM that can't tell when to call it. Treat docstrings as prompt engineering. Same trap as Agentforce's `@InvocableMethod(description=...)`: the docstring is not for humans, it's for the model.

8. **`agent.as_tool()` is not the same as a handoff.** `as_tool()` wraps an agent as a callable sub-tool — control returns to the caller after execution, the sub-agent doesn't take over the conversation. Handoffs are *transfers* of control. Mixing them up is the most common architectural mistake: people reach for handoffs when they actually want sub-tools, and end up with conversations that ping-pong between agents instead of cleanly delegating sub-tasks.

9. **Guardrails only protect the first and last agent in a handoff chain.** Input guardrails fire only for the entry agent; output guardrails fire only for whichever agent produces the final output. Mid-chain agents are unguarded. If you need per-agent validation, that's per-agent guardrail wiring, not a free runtime property.

## When to choose OpenAI Agents SDK

- The workload is genuinely **multi-agent with handoffs** — specialist routing, triage-then-deep-dive, multi-step workflows where each step wants its own tight system prompt and tool list. Handoffs are the differentiator; if you're not using them, you're paying for primitives you don't need.
- Your team is **on the OpenAI stack** — using GPT-4.x / GPT-5 / o-series, comfortable with Responses API, OK with traces landing in the OpenAI dashboard.
- You need **OpenAI's hosted tools** — web search, file search, code interpreter, image gen, computer use — and want them invoked from inside an agent loop without reimplementing them.
- You want a **thin, Python-native harness** with minimal new vocabulary. The SDK leans hard on standard Python (decorators, type hints, Pydantic) instead of inventing new abstractions.
- You're building **voice / realtime agents**. The SDK ships a voice pipeline and the realtime-API integration is first-class.

## When *not* to choose OpenAI Agents SDK

- **Provider-agnostic from day one** → LangGraph or a thinner harness. The `litellm` escape hatch works but you give up the hosted-tools advantage and accept second-class status for non-OpenAI providers.
- **Simple ReAct single-agent loop with skill files** → Claude Agent SDK. If your "multi-agent" is really one agent with a long tool list, the OpenAI Agents SDK's handoff machinery is overhead you'll never use.
- **Graph / state-machine workflows with checkpoint-and-resume, human-in-the-loop pauses, durable execution** → LangGraph. The Runner is a loop, not a state machine; there's no first-class checkpoint/resume semantic.
- **Salesforce-resident, CRM-grounded** → Agentforce. Not even close in that footprint.
- **Heavy structured deterministic workflows where the LLM is one node among many** → LangGraph or a Temporal-style durable workflow with LLM activities. The OpenAI SDK assumes the LLM is *driving* the loop.

## Atlan integration shape

When integrating with Atlan as a context layer, two patterns apply cleanly to the OpenAI Agents SDK:

- **Function tools wrapping `pyatlan`** — `@function_tool def search_assets(query: str) -> list[AssetRef]: ...` exposes targeted Atlan reads/writes to the agent. The SDK's automatic schema inference (`inspect` + `griffe` + Pydantic) means docstring quality on these wrappers is the tool definition the LLM sees. Treat the docstring as prompt engineering, not Javadoc.
- **Atlan MCP server as a tool source** — the SDK has MCP client support; pointing it at an Atlan-hosted MCP server gives the agent a governed surface over Atlan metadata without bespoke wrappers per call. Good fit when the agent needs broad metadata read access; less ergonomic for narrow, high-frequency lookups.

For bulk metadata reads inside an activity, the lakehouse (MDLH via Snowflake/DuckDB) is faster and cheaper than per-call pyatlan; wrap a SQL helper as a function tool rather than letting the agent issue many small pyatlan calls in a loop.

## The "is this just Swarm in a suit" question

Fair question. Swarm (the October 2024 educational release) introduced the handoff abstraction and the "many small agents, one Runner" idea. The Agents SDK kept those bones and added: production-grade tracing, the guardrails system, typed `output_type` with Pydantic, sessions with multiple backends, the hosted tool integrations (web search, code interpreter, file search, computer use), the voice pipeline, the `litellm` adapter, MCP support, and the AgentKit/Builder relationship. Swarm was a teaching framework with a clever idea. The Agents SDK is what you'd build if that idea actually had to ship and the customer support team had to debug it at 2am.

The continuity is real — same primitive, same Runner posture, same "let the LLM decide who's next" philosophy. The difference is operational maturity. If a teammate says "we're just doing Swarm," they're describing the architecture; if they say "we're on the Agents SDK," they're describing the runtime.

## Maturity snapshot (mid-2026)

- **Origin**: Swarm (October 2024, educational/experimental) → OpenAI Agents SDK (early 2025, production-promoted) → continued evolution through 2025-2026 alongside the Responses API and AgentKit/Agent Builder.
- **AgentKit / Agent Builder relationship**: AgentKit is OpenAI's higher-level no-code/low-code agent builder (closer to Agentforce's Builder in posture). The Python SDK is the **pro-code substrate** AgentKit builds on; agents authored in AgentKit can be exported to or interop with SDK-defined agents. If you start in the SDK, AgentKit is a deploy/UI surface available later; if you start in AgentKit, the SDK is the escape hatch when you outgrow the builder.
- **Ecosystem**: Production usage at OpenAI itself (ChatGPT agent mode, Operator-class workloads), broad third-party adoption, the most active "multi-agent with handoffs" community as of mid-2026.
- **Stability**: Core primitives (Agent, Runner, Tool, Handoff, Guardrail) are stable. The handoff-history-management story (`nest_handoff_history`) is still labeled beta as of mid-2026 — expect tuning here.
- **Honest assessment**: the cleanest harness in this category if your use case fits the multi-agent-handoff shape and you're OK with the OpenAI gravity well. If either of those isn't true, the alternatives are stronger.

The fair framing: **OpenAI Agents SDK is to multi-agent handoffs what Claude Agent SDK is to single-agent ReAct.** Tight, opinionated, productive, with a clear failure mode when the use case doesn't match the primitive bet.
