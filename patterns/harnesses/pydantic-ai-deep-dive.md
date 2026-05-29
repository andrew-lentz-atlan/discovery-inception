---
title: Pydantic AI — Builder's Deep Dive
category: harnesses
status: draft
last_updated: 2026-05-29
source_external:
  - https://pydantic.dev/docs/ai/overview/ — official overview (fetched 2026-05-29)
  - https://pydantic.dev/docs/ai/core-concepts/agent/ — Agent runtime semantics (run/run_sync/run_stream, retries, ModelRetry)
  - https://pydantic.dev/docs/ai/tools-toolsets/tools/ — function tools, @agent.tool vs @agent.tool_plain, griffe-based docstring parsing
  - https://pydantic.dev/docs/ai/integrations/logfire/ — built-in OpenTelemetry-based observability
  - https://pydantic.dev/docs/ai/mcp/overview/ — MCP client + server support
  - https://github.com/pydantic/pydantic-ai — version cadence and release history
applies_when:
  workloads: [structured-output-as-contract, fastapi-resident-agents, type-safe-tool-pipelines, python-first-data-agents]
  constraints: [team-on-python-3.11-plus, pydantic-already-in-stack, structured-output-load-bearing, willing-to-pin-pydantic-ai-version]
contradicts: []
related: [harnesses/landscape-2026-may, architectures/single-agent-react, decision-guides/what-kind-of-agent-are-you-building]
snapshot_date: 2026-05-29
---

# Pydantic AI — Builder's Deep Dive

Pydantic AI is the agent framework from the team that built Pydantic itself — the validation library underneath the OpenAI, Anthropic, and Google Python SDKs. The pitch is direct: bring the "FastAPI feeling" to LLM agents. In practice that means **the Pydantic schema is the load-bearing primitive** — not the prompt, not the graph, not the orchestrator. Tool signatures are types. Outputs are types. Dependencies are types. The agent loop exists to mediate between an LLM and a typed contract, and when the contract fails to hold, the framework knows what to do about it.

This entry exists because the landscape survey can't carry the depth needed to decide for or against Pydantic AI on a specific use case. The structured-output retry loop, the `deps_type` injection pattern, the model-agnostic provider shim, Logfire's role as a native (but optional) observability layer — these matter, and they don't fit a row in a comparison table. It's also younger than LangChain and LangGraph, and the ecosystem reflects that.

## The four primitives

Every Pydantic AI agent is built from four typed primitives:

| Primitive | What it is |
|---|---|
| **`Agent[DepsType, OutputType]`** | The generic agent class. Both type parameters are load-bearing — they flow into every tool, validator, and result. |
| **`deps_type`** | A dataclass (or any container) of dependencies — DB clients, HTTP sessions, API keys, business-logic services — that gets injected on every run via `RunContext.deps`. |
| **`output_type`** | A Pydantic model (or `bool`, `str`, `int`, `list[Foo]`, union types, etc.) that the framework forces the model to satisfy. Validation failure triggers automatic retry with the error fed back to the model. |
| **`tools`** | Python functions registered via `@agent.tool` (with `RunContext` injection) or `@agent.tool_plain` (no context). Type hints become the JSON schema; docstrings become tool descriptions, parsed via griffe in Google/NumPy/Sphinx format. |

Underneath: **system prompts can be static or dynamic** (`@agent.system_prompt` decorator on a function that reads `ctx.deps`). The agent run is ordinary `await agent.run(...)`, blocking `agent.run_sync(...)`, or `async with agent.run_stream(...)` for token-by-token streaming with mid-stream structured validation.

## The reasoning model

Pydantic AI implements **ReAct (Reason–Act–Observe) with strict-typed inputs and outputs at every interface**. It's not graph-state-machine reasoning (that's LangGraph's territory) and it's not a vertically-integrated planner-classifier-executor stack (that's Agentforce). The loop is small and Python-shaped:

1. Build the request: instructions + conversation history + tool schemas + `output_type` schema (rendered into the prompt one of three ways: as a forced tool call, as a native JSON-Schema response_format, or as a prompted JSON contract).
2. Call the model.
3. If the model called a tool, validate arguments against the Python signature; on `ValidationError`, feed the error back to the model and let it retry (counted against per-tool retry budget).
4. Execute the tool. If the tool raises `ModelRetry("...")`, feed that message back as a tool-result and retry.
5. If the model produced final output, validate against `output_type`. On `ValidationError`, feed it back; on success, return the `AgentRunResult`.
6. If retries are exhausted, raise `UnexpectedModelBehavior`.

**The Pydantic schema is the structural backbone.** Every interface that touches the LLM — input args, output, errors — passes through validation. This is the entire bet of the framework: if your contracts are strict and your retries are tuned, the agent fails closed and the failure is legible.

A note on the three output modes worth internalizing before reading code:

- **Tool Output (default).** The output schema is presented to the model as a tool, and the model "calls" that tool to produce the answer. Works with virtually every provider that supports function calling. Default for a reason.
- **Native Output.** Uses the provider's native JSON-Schema response format (where supported — OpenAI, Anthropic, etc.). Stronger guarantee that the response will parse, but constrains tool-calling on some providers (notably Gemini, which cannot use tools and Native Output simultaneously).
- **Prompted Output.** Schema is injected into the instructions as text; the model is asked to produce conforming JSON. Most compatible but weakest guarantee. Useful as a fallback for models without strong tool-calling or response_format support.

You opt into a mode via `output_type=NativeOutput(MyModel)` or `output_type=PromptedOutput(MyModel)`. Plain `output_type=MyModel` gets the default.

## The minimum viable agent

```python
from dataclasses import dataclass
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

@dataclass
class Deps:
    customer_db: CustomerDB
    http: httpx.AsyncClient

class SupportReply(BaseModel):
    answer: str
    confidence: float
    escalate: bool

agent = Agent(
    "anthropic:claude-opus-4-7",
    deps_type=Deps,
    output_type=SupportReply,
    instructions="You are a customer support agent. Be concise. Escalate if unsure.",
)

@agent.tool
async def lookup_balance(ctx: RunContext[Deps], customer_id: str) -> float:
    """Return the customer's current account balance in USD."""
    return await ctx.deps.customer_db.balance(customer_id)

@agent.tool
async def open_tickets(ctx: RunContext[Deps], customer_id: str) -> list[str]:
    """List open support ticket IDs for this customer."""
    return await ctx.deps.customer_db.tickets(customer_id, status="open")

result = await agent.run(
    "What's the balance and open tickets for customer 4172?",
    deps=Deps(customer_db=CustomerDB(...), http=httpx.AsyncClient()),
)
print(result.output)  # SupportReply(answer=..., confidence=0.92, escalate=False)
```

That's ~30 lines for a typed, tool-using, validated-output agent against any of ~20 supported providers. The thing it doesn't show — and that you get for free — is the retry loop, the docstring-derived tool descriptions, and the IDE autocomplete that flows from `Agent[Deps, SupportReply]` all the way into `ctx.deps.customer_db`.

## Production patterns

**Dependency injection as the testability seam.** Every external system the agent touches lives on `deps`. In tests, `agent.override(deps=fake_deps)` swaps a fake DB or a recorded-HTTP client; in production, you build the real container once and pass it on every `agent.run(deps=...)`. This is the single biggest reason FastAPI-shop teams reach for Pydantic AI: the testing story matches the testing story they already have for their web app — the same `pytest` fixtures, the same monkeypatched HTTP, the same in-memory test DBs.

**Multi-step tool chains.** Tools can call other code, return Pydantic models, raise `ModelRetry("provide a non-empty query")` to nudge the model with a specific correction message. The framework doesn't ship a graph engine — for cyclic or branching state machines, `pydantic-graph` is the companion package, but most production deployments stay flat ReAct and let the LLM pick the next tool. If you find yourself reaching for "state machine across multiple tool calls with conditional edges," that's the signal you wanted LangGraph.

**Output validators (post-validation hooks).** Beyond Pydantic schema validation, you can register `@agent.output_validator` functions that run *after* the model has produced a candidate output and *before* it's returned. Raising `ModelRetry("the SQL must SELECT, not DROP")` from a validator forces another round-trip. Useful for business-logic invariants Pydantic can't express (e.g. "this query must not include destructive verbs"). Each `ModelRetry` consumes one retry slot.

**Model-agnostic provider selection.** `Agent("openai:gpt-5.2", ...)`, `Agent("anthropic:claude-opus-4-7", ...)`, `Agent("google:gemini-2.5-pro", ...)`, plus DeepSeek, Grok, Cohere, Mistral, Perplexity, Bedrock, Vertex, Ollama, Groq, OpenRouter, Cerebras, Hugging Face. The provider abstraction is real — you can swap models with a string change, with the caveat that **structured-output mode compatibility varies** (see failure modes). The provider-prefix string also lets you point at a custom `OpenAI`-compatible endpoint (LiteLLM proxy, vLLM server, internal gateway) without changing call sites.

**Streaming.** `async with agent.run_stream(...) as stream` yields a `StreamedRunResult` with both token streams and *partial* validated structured output as it arrives. For UIs that need typing-indicators and progressive rendering of structured replies, this is more ergonomic than rolling your own. Note that streaming + structured output is one of the places where provider compatibility bites — older Gemini models and the legacy `OutlinesModel` have streaming constraints.

**Logfire as native (but optional) observability.** Two lines — `logfire.configure(); logfire.instrument_pydantic_ai()` — and every agent run emits OpenTelemetry spans for model requests, tool execution, retries, and validation failures. Logfire itself is OTel-based, following the OpenTelemetry Semantic Conventions for Generative AI, so the data can land in Langfuse, Arize, W&B Weave, or any OTel backend; the Logfire cloud product is optional with a generous perpetual free tier and a self-hostable enterprise tier. **If you don't install logfire, there's no instrumentation overhead at all** — it's a true opt-in. Builders coming from LangSmith will find the trace UI familiar but less LangChain-specific.

**Human-in-the-loop tool approval.** Tools can be flagged as requiring approval before execution. The framework surfaces the pending call, waits for an external signal, then continues. Useful when the agent is permitted to read freely but must pause before mutations (e.g. "agent can `lookup_asset` autonomously, but `update_certification` requires a human OK").

**Durable execution.** As of mid-2026 the framework ships support for preserving agent progress across API failures and restarts — long-running multi-tool runs that survive a worker crash. Less mature than Temporal-backed durability (which the Atlan Application SDK leans on); more comparable to LangGraph's checkpointing model. For genuinely long-horizon work (hours, days), pair Pydantic AI with an external orchestrator rather than relying solely on the built-in durability.

## Failure modes

1. **Pydantic version coupling.** Pydantic AI tracks Pydantic itself. When Pydantic 3 lands, expect a coordinated migration window. Teams pinning to old Pydantic for non-AI reasons will hit conflicts — this is the most common dependency-resolution pain in the wild.

2. **Strict typing has a retry-cost tax.** Every tool call gets argument-validated; every final output gets schema-validated. When the model produces invalid JSON or wrong-shape args, the framework spends a round-trip feeding the error back and re-asking. On weaker models or genuinely ambiguous schemas this can balloon. **Tune retry budgets and watch token spend.** A run that should be 3 tool calls can become 8 when validation keeps failing.

3. **Structured-output mode compatibility varies by provider.** The default ("Tool Output" mode) works almost everywhere. "Native Output" (JSON-Schema response_format) works on OpenAI/Anthropic/etc. but Gemini, per the docs, **cannot use tools at the same time as structured output**. If you switch providers and start seeing weird "no tools called" behavior, this is the first thing to check.

4. **Smaller ecosystem than LangChain/LangGraph.** As of mid-2026 the integrations catalog is narrower — fewer pre-built vector store wrappers, fewer pre-built retrieval chains, fewer community recipes. The MCP escape hatch matters a lot here: anything available as an MCP server is usable via `FastMCPToolset` in ~5 lines, which closes most of the gap.

5. **Younger codebase, faster minor-version cadence.** The 1.x line has shipped 260+ releases since 1.0, with new releases roughly weekly. Most are additive, but expect to pin a version in production and pay attention to release notes — semantic-versioning discipline is good, but the surface area is still moving.

6. **`pydantic-graph` is a separate concern.** If your problem genuinely is a state machine with cycles, branches, and shared state across nodes, you want LangGraph. `pydantic-graph` exists and uses type hints to define nodes, but it's the smaller, less battle-tested option. Don't pick Pydantic AI *because* of graphs — pick it despite needing graphs, and accept that the graph layer is the less mature half.

7. **Tool docstrings are part of the prompt.** Same gotcha as every other tool-using framework: the LLM reads the docstring to decide when to call the tool. Sloppy or missing docstrings cause misrouting. Pydantic AI offers `require_parameter_descriptions=True` to fail loudly when docs are absent — turn this on in CI.

8. **`agent.run_sync` runs the async loop under the hood.** Calling it from inside an existing async context (e.g. a FastAPI route handler) raises. Use `await agent.run(...)` in async code; `run_sync` is for scripts and notebooks. This trips up a lot of first-time users who copy/paste an example out of a notebook into a web handler.

9. **`@agent.tool` vs `@agent.tool_plain` is a real distinction.** `tool` injects `RunContext`; `tool_plain` does not. The framework inspects the signature to decide. If you accidentally write `def my_tool(ctx, x: str)` without typing `ctx` as `RunContext[Deps]`, the schema sent to the model includes `ctx` as a parameter and the LLM tries to fill it in — leading to confusing "the model is hallucinating a `ctx` argument" failures. Always type `ctx: RunContext[Deps]` explicitly.

10. **Per-tool retry budgets accumulate cost silently.** Each tool gets its own retry counter (default 1). Each output validator gets its own. A run that fails on output, retries, then a tool also fails and retries, can quietly burn 4-6× the expected token spend. Set `retries=` explicitly per tool when token cost matters, and watch the Logfire trace to see where the budget is going.

11. **Union output types are seductive and brittle.** `output_type=AnswerA | AnswerB | EscalationNeeded` looks elegant — let the LLM pick the right shape. In practice, models can struggle to discriminate which branch they're meant to fill, especially when shapes overlap. If you find the model frequently picking the wrong branch, collapse to a single output model with a discriminator field (`kind: Literal["answer", "escalation"]`) and let Pydantic's tagged-union support do the work.

12. **Docstring style matters more than people expect.** Pydantic AI parses docstrings via griffe in Google, NumPy, or Sphinx format. If your codebase uses an idiosyncratic docstring style, parameter descriptions silently drop from the schema and the LLM gets a less-informative tool definition. Pick a style, lint for it, and turn on `require_parameter_descriptions=True` to fail loudly when a tool is under-documented.

## When to choose Pydantic AI

- Structured output is the contract — the agent's job is to produce a validated Pydantic model, not a free-text answer.
- Your codebase is already Pydantic-heavy — FastAPI services, data pipelines, `BaseModel`-everywhere shops.
- Type safety and IDE autocomplete are a team value, not a nice-to-have.
- You want model-agnostic provider selection without writing the shim yourself.
- You want OpenTelemetry observability natively, with the option of a hosted UI on top.
- The agent loop is ReAct-shaped (loop until done, no complex branching state).

## When *not* to choose Pydantic AI

- You need a complex graph state machine — **LangGraph** is the better fit; its checkpointing and human-in-the-loop interrupts are more mature.
- You're building enterprise multi-agent orchestration at scale and want the most production-tested option — **OpenAI Agents SDK** has more multi-agent primitives (handoffs, sessions, voice).
- Your agent lives inside Salesforce — **Agentforce**, full stop.
- You only need a single-model Claude agent with skills and computer use — **Claude Agent SDK** is leaner and closer to the model's native posture.
- Your team isn't on Python — Pydantic AI is Python-only as of mid-2026.
- Pydantic is not already in your stack and your data shapes are loose — the type-safety tax outweighs the benefit.

## Atlan integration shape

When integrating with Atlan as a context layer for a Pydantic AI agent, the obvious seams are:

- **`deps_type` as the Atlan-client injection point.** Stand up an `AtlanDeps` dataclass containing the SDK client for writes/lookups and a lakehouse SQL connection (e.g. Snowflake or DuckDB) for bulk metadata reads. Inject once at `agent.run(deps=...)`; every tool gets a typed handle via `ctx.deps`. In tests, swap the same dataclass for a fake.
- **Function tools wrap targeted catalog operations.** `@agent.tool` functions for things like `find_asset_by_qualified_name`, `get_glossary_terms`, `update_certification_status`, each with a Pydantic-validated input model and a strict-typed return. Bulk reads — "all tables in connection X with no description" — are better expressed as parameterized SQL against the lakehouse than as paginated SDK calls; the typed list comes back, the LLM sees a clean structured result instead of pagination scaffolding.
- **MCP for off-the-shelf surface.** Anything the catalog exposes via MCP (or any approved external server) can be added with `FastMCPToolset` rather than hand-wrapped. This keeps the agent's tool surface aligned with the broader MCP ecosystem and avoids re-implementing what's already standardized.
- **Output as the catalog contract.** When the agent's job is to produce structured metadata changes — proposed glossary terms, suggested certifications, lineage edits — model the proposal as a Pydantic class and let `output_type` enforce the shape end-to-end. The "agent produces validated structured proposal → human (or downstream service) applies it via SDK" split keeps the mutation surface narrow and auditable.

None of this is special — it's the same `deps_type` + `@agent.tool` + `output_type` pattern Pydantic AI uses for any external system. That's the point.

## The fair "is Pydantic AI opinionated enough" question

It's a fair question. Pydantic AI sits at an interesting altitude: more opinionated than the OpenAI Python SDK alone (which gives you raw chat-completions and asks you to write your own loop), less opinionated than LangGraph (which hands you a state-machine engine and asks you to model your domain inside it). The opinion it does take is **strong typing as the contract between every component** — which is either exactly what you want, or feels like overhead, depending on the codebase you're coming from.

The right way to compare it to the other harnesses: **Pydantic AI is to agents what FastAPI is to web services.** Same team energy. Same posture — "we noticed nobody else made this feel right, so we built it." Same trade-off — opinionated about type safety, light on opinions about everything else, lets you bring your own domain shape. For Python teams already running FastAPI + Pydantic in production, picking Pydantic AI is the path of least surprise. For teams who don't already think in Pydantic models, the lift is larger than it looks because the framework's value compounds with how much of your domain is already typed.

## Maturity snapshot — mid-2026

Pydantic AI hit 1.0 in late 2024. As of May 2026 it's on the 1.10x line (v1.104.0 on 2026-05-29 per the GitHub release history), ~17k stars, ~2.1k commits, ~260 releases. Backed by the Pydantic company, which also operates the Logfire observability product as the natural monetization layer. **It is younger than LangChain (2022) and younger than LangGraph as a separate framework**, but past the "is this a toy" question — production deployments are common, particularly in FastAPI-heavy Python shops where the type-safety value prop lands hardest.

The trajectory is clear: opinionated, narrow, deeply integrated with the Pydantic ecosystem. It is not trying to be everything to everyone, and the framework benefits from that constraint. The risks are:

- **Ecosystem breadth.** Fewer pre-built integrations than LangChain. MCP narrows the gap but doesn't close it for every use case.
- **Graph maturity.** `pydantic-graph` exists, but is the less-traveled half of the project; LangGraph is the safer choice for genuine state machines.
- **Pydantic version coupling.** When Pydantic 3 lands, expect a coordinated migration; this entry will need a refresh.
- **Bus factor.** A small, focused team is a feature and a risk. The Pydantic company is well-funded and the project is healthy, but the surface area is narrower than LangChain's community ecosystem.

None of these are dealbreakers for the workloads where Pydantic AI shines — they're the predictable shape of a younger, more opinionated framework. If the trade-offs align with the team's posture, they pay for themselves quickly.

## Empirical anchor

There is no published vendor-supplied win-rate or accuracy benchmark for Pydantic AI of the kind Salesforce publishes for Agentforce — Pydantic AI is open-source and lacks the vertically-integrated stack that produces those numbers. The receipts are circumstantial: 17k+ stars, weekly release cadence, Pydantic's own use of it for Logfire-related agent features, and visible uptake in FastAPI/Pydantic-heavy Python shops. The realistic framing is: **if your problem fits the shape — ReAct loop, typed output as the contract, Python-native team — Pydantic AI is a productivity win that gets you to a working agent in tens of lines of code. If the problem shape diverges, one of the other harnesses in the landscape survey will fit better, and that's by design.**

Origin: official Pydantic AI documentation (https://pydantic.dev/docs/ai/), the public GitHub repo, and the structural-output / observability sub-docs cited in the frontmatter. No internal Atlan research doc anchors this entry — all claims trace to public sources as of 2026-05-29.
