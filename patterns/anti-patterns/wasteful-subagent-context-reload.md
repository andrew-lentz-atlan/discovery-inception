---
title: Wasteful subagent context reload (paying full setup cost every call)
category: anti-patterns
status: draft
last_updated: 2026-05-29
source_findings: []
source_external:
  - Anthropic — "Prompt caching" (https://docs.claude.com/en/docs/build-with-claude/prompt-caching) — cache reads are 0.1x base input price (90% discount); cache writes 1.25x (5m TTL) or 2x (1h TTL); minimum cacheable prefix 1,024–4,096 tokens depending on model; up to 4 cache breakpoints; place breakpoint on the last block that stays identical across requests
  - Anthropic — "Subagents in the SDK" (https://code.claude.com/docs/en/agent-sdk/subagents) — "Each subagent runs in its own fresh conversation. Intermediate tool calls and results stay inside the subagent; only its final message returns to the parent." Subagent's context "starts fresh (no parent conversation) but isn't empty. The only channel from parent to subagent is the Agent tool's prompt string"
  - LangGraph — checkpointer + thread_id mechanics (`InMemorySaver`, `SqliteSaver`, `PostgresSaver`, `AsyncPostgresSaver`); same `thread_id` resumes a session, a new one starts fresh; see `patterns/harnesses/langgraph-deep-dive.md`
  - Observed during the patterns-deepening workstream (2026-05-29): a "research" subagent calling an MCP-based search tool every invocation to repopulate context, even though the queries and results were stable across the session
applies_when:
  workloads: [conversational-agent, co-pilot, autonomous-worker, task-agent-fan-out]
  constraints: [subagent-called-repeatedly, stable-context]
contradicts: []
related:
  - decision-guides/subagent-vs-skill-tradeoffs
  - harnesses/claude-agent-sdk-deep-dive
  - anti-patterns/cheap-cascade-orchestrator-compensation
  - anti-patterns/over-decomposition
snapshot_date: 2026-05-29
---

# Wasteful subagent context reload

A subagent that re-establishes the same context on every invocation is paying for an isolation property it isn't using. The Agent SDK is explicit about the shape: *"Each subagent runs in its own fresh conversation… the only channel from parent to subagent is the Agent tool's prompt string."* That fresh-conversation guarantee is the feature — and the bill. If your subagent's first ~30K tokens are spent re-fetching the same documents, re-loading the same schema, re-running the same searches every time it's invoked, you are paying full setup cost on every call for a context the agent already had two turns ago.

The fix is one of three, in increasing investment: **make it a skill** (no isolation needed → no subagent), **wire prompt caching** (isolation needed, prefix is stable → cache reads are 0.1× base price per Anthropic's docs), or **persist memory** (isolation needed, work compounds → checkpointer-style state across calls).

## How it shows up

Four representative shapes, all real:

### Shape 1 — the MCP-research-loop subagent

A "research" subagent the orchestrator calls every turn. It opens by running 3–6 searches against an MCP-backed knowledge tool (Glean, internal vector store, web search wrapper, doesn't matter which one) to "establish context," then answers the actual sub-question. Same queries, same results, every invocation. Each call costs **~30–80K input tokens just to re-establish what it learned last turn** before it does any new work. Across a 20-turn session, the same 30K context is re-loaded 20 times — ~600K wasted input tokens that prompt caching, at the docs' published 90% cache-read discount, would have cost roughly 60K equivalent.

### Shape 2 — the schema-loading subagent

A subagent that wraps "describe the database" or "fetch the table catalog." Schema changes weekly; the subagent re-fetches the full catalog on every invocation. **~10–50K tokens of schema metadata loaded fresh per call.** The architect's instinct was right (the orchestrator shouldn't be drowning in schema noise) but the implementation made the cost worse, not better: where keeping the schema in the orchestrator's context would have cost N tokens once, the subagent pays N tokens × call-count, with no carry-forward.

### Shape 3 — the semantic-model subagent

For Cortex/Genie-style agents that lean on a curated semantic model, a subagent that loads the full semantic-view YAML every invocation to answer a per-query question. The semantic model is stable across the entire session (often across days), but the subagent's "fresh conversation" property means the YAML is re-read and re-tokenized on every call. The model itself can be 5–20K tokens; loaded 50× over a session is a 250K–1M waste budget.

### Shape 4 — the fan-out search subagent

`N` items processed in parallel; each subagent instance loads the same setup context independently. Cost is **linear in N** when it could have been sublinear. Worth noting that the SDK actively encourages this shape — *"Multiple subagents can run concurrently, dramatically speeding up complex workflows"* — without flagging that the per-call setup cost compounds the same way. Latency wins, token economics lose, and most builders only notice the latency.

Worked example: a code-review orchestrator that fans out to `style-checker`, `security-scanner`, and `test-coverage` subagents. All three load the same project conventions doc (~8K tokens), the same dependency manifest (~3K tokens), and the same recent-diff context (~5K tokens) before doing anything use-case-specific. That's **48K tokens of duplicated setup** across the three subagents on a single review. Wired with prompt caching against a shared prefix (the orchestrator's project conventions block being identical across all three subagent prompts), 32K of those tokens become cache reads at the 0.1× rate; the other 16K — the per-subagent system prompt and the dynamic diff — stay full-price. Net spend drops ~60% on the duplicated portion alone.

## Why it happens

Three mechanisms:

1. **Mistaken "context isolation" reasoning.** The architect thought "I want the search results out of the main conversation" — got that with a subagent, exactly as the docs describe — but didn't notice the search is doing the same work every invocation. The Agent SDK's value-prop sentence (*"a research-assistant subagent can explore dozens of files without any of that content accumulating in the main conversation"*) reads as a clean win only if the exploration is *different* each time. When it's the same exploration repeated, isolation has become cost amplification.

2. **No persisted memory layer wired by default.** Most agent frameworks don't make memory-augmented subagents the easy path. LangGraph's `InMemorySaver` / `SqliteSaver` / `PostgresSaver` checkpointers exist precisely for this — the same `thread_id` resumes prior state — but the developer has to wire the checkpointer at compile time and route the subagent through a thread-scoped invocation; nothing in the framework nudges them toward it. The Claude Agent SDK's subagent primitive **has no built-in cross-invocation memory** at all: each call gets a fresh conversation by design. There is a `resume` API that re-attaches to a prior subagent session, but it's an explicit opt-in builders rarely reach for, and using it correctly requires capturing both `session_id` and `agentId` between calls (most code doesn't).

3. **Prompt caching invisible.** Anthropic's prompt caching gives a **0.1× discount on cache reads** (a 90% reduction) for prefixes ≥1,024–4,096 tokens (model-dependent), with up to **4 cache breakpoints** placed via the `cache_control` field. The mechanic works — but only if the cacheable prefix is structured first and is byte-identical across calls. Most subagent code rebuilds the prompt from scratch every invocation (different timestamps, different prompt-string concatenation order, different formatting), and the breakpoint either lands on a varying block (caches nothing) or misses the 20-block lookback window (caches but never reads). Caching is on, the discount isn't.

## Why it matters

Concrete numbers, drawn from the prompt-caching docs and the shapes above:

- **Token waste compounds.** A subagent re-loading 30K tokens of context, called 20 times in a session, costs **600K extra input tokens per session**. At Haiku 4.5's input price (model dependent), that's tens of cents of pure waste per session; multiplied across thousands of sessions per day in a production deployment, real money. With prompt caching wired correctly the same 600K tokens would have cost ~60K cache-read tokens (the 90% discount) plus a one-time write at 1.25× the base for the 5-minute TTL.
- **Latency is worse than the token cost.** Each re-load is 1–3s of model time on first-pass, even if the tokens themselves were free. **20 calls × 2s = 40s of pure setup latency** per session — most of which the user perceives as "the agent is slow." Cache reads are faster too (the bytes don't get re-tokenized; the KV cache is reused), so wiring caching helps wall-clock as much as cost.
- **Token spend is a fabrication-rate signal.** Wasteful subagents tend to have **weaker grounding** than they should, because they're spending budget on context re-loading instead of reasoning over fresh inputs. The model arrives at its sub-task with the same context-window pressure as a non-reloading subagent would, but the useful-tokens-to-total-tokens ratio is much worse. This compounds with `anti-patterns/silent-tool-fallback`: when the subagent is squeezed on reasoning budget, it leans harder on prior context and is more likely to invent.
- **Cheap-cascade compensation analog.** Just as `anti-patterns/cheap-cascade-orchestrator-compensation` documents that cutting extractor cost can *raise* orchestrator cost, this anti-pattern is the inverse failure: the architect thought adding a subagent would *reduce* orchestrator context load, but the per-call setup cost ate the savings and then some.

## The three fixes (in increasing complexity and investment)

### (a) Make it a skill, not a subagent

If the work doesn't need context isolation, it doesn't need a subagent. A skill called from the orchestrator runs in the orchestrator's context — the loaded data is reusable across the rest of the conversation, the prompt caches naturally (because the orchestrator's prefix is what's stable), and the orchestrator has direct access to what was learned (no summary lossiness from the subagent's `final message` channel).

**When to reach for this:** the subagent's only purpose is logical decomposition ("I want this clearly separated in the code"). That's a code-organization argument, not an isolation argument. Make it a skill, or just a Python function the orchestrator calls.

**See the companion** `decision-guides/subagent-vs-skill-tradeoffs.md` for the 5-row matrix that distinguishes real isolation needs from logical decomposition.

### (b) Wire prompt caching

When the subagent IS justified (true context isolation needed), structure its prompt so the stable prefix can be cached. Per Anthropic's docs:

- Place the cached content **at the prompt's beginning** (tools, system prompt, then dynamic per-call inputs last).
- Put the `cache_control` breakpoint on **the last block that stays identical across requests**, not on the varying block. Putting it on the varying block caches nothing.
- Mind the **20-block lookback window**: if the breakpoint and the prior cache write are more than 20 blocks apart, the read misses. Add a second explicit breakpoint earlier in the prefix if you have a long fan-out.
- Verify the minimum-prefix threshold for your model: **1,024 tokens** for Sonnet 4.5/4.6 and Opus 4/4.1; **4,096 tokens** for Opus 4.5/4.6/4.7 and Haiku 4.5; **2,048 tokens** for Haiku 3.5. Below the threshold, the prompt won't cache at all and `cache_creation_input_tokens` will be 0.
- Use the **1-hour TTL** (2× write cost) when calls are spaced more than 5 minutes apart, otherwise the default 5-minute TTL is fine and writes only cost 1.25× base.

**When to reach for this:** the subagent is justified AND called frequently AND the cacheable prefix is identifiable. Cheapest of the three fixes once the structural requirement is in place.

**What "structured for caching" looks like in practice** (Anthropic SDK example, condensed from the prompt-caching docs):

```python
# Subagent prompt assembly — cacheable structure
system=[
    {
        "type": "text",
        "text": SUBAGENT_ROLE_PROMPT,          # stable across all calls
    },
    {
        "type": "text",
        "text": LOADED_SCHEMA_OR_KNOWLEDGE,    # stable across the session
        "cache_control": {"type": "ephemeral"},# ← breakpoint on last stable block
    },
],
messages=[
    {"role": "user", "content": per_call_question},  # the only varying part
]
```

The breakpoint sits on the schema/knowledge block — the last thing that's identical across invocations. The per-call question is *after* the breakpoint, so it never invalidates the cache. After the first call, `cache_read_input_tokens` will dominate `usage` and the per-call cost collapses.

### (c) Persist memory across invocations

When the subagent needs to *remember what it learned* across calls (not just "the input is the same, cache it" but "carry compounding state forward"), use a memory mechanism.

- **LangGraph:** wire a checkpointer at compile time — `builder.compile(checkpointer=InMemorySaver())` for in-process, `PostgresSaver` / `AsyncPostgresSaver` for production durability, `SqliteSaver` for local dev. Invoke with `config = {"configurable": {"thread_id": "..."}}` — same `thread_id` resumes prior state, new `thread_id` starts fresh. State survives process restarts when the checkpointer is durable.
- **Claude Agent SDK:** no built-in subagent memory. Two options:
  - Use the SDK's `resume` API: capture `session_id` from the `ResultMessage` and `agentId` from the Agent tool result on the first call, then pass `resume: sessionId` and reference the agent ID by name on subsequent calls. Subagent transcripts persist independently of the main conversation and are cleaned up per `cleanupPeriodDays` (default 30).
  - Or roll your own: parent owns a state object, passes the relevant prior-learned summary in the subagent's prompt string each call, the subagent updates it and returns the updated version. Less elegant but works with any harness.
- **Other harnesses:** OpenAI Agents SDK and Pydantic AI lack a first-class checkpointer; both push you toward externalizing state to your own store (the LangGraph deep-dive notes this as a deliberate divergence in opinion).

**When to reach for this:** the subagent's work compounds across calls (it's *learning*, not just *re-running*). If you find yourself summarizing prior subagent outputs to feed into the next subagent call, you've already built a half-broken memory layer — make it real.

## How to prevent during inception

Three rules for the inception pipeline:

1. **Architecture-proposer rule.** When proposing a subagent, name the REASON number it's a subagent (per the five-row matrix in the companion `decision-guides/subagent-vs-skill-tradeoffs.md`). Reject Reason #2 ("logical decomposition felt clean") — convert to skill. The valid reasons are limited (1, 3, 4, 5); treat the burden of proof as on the subagent, not on the skill.

2. **Orchestrator-stub rule.** For every subagent in the proposed `orchestrator.py`, the rationale must answer:
   - *Will this be called more than once per session?*
   - *Does the per-call setup context overlap with prior calls?*
   - *If yes to both: is prompt caching wired, OR is memory persisted, OR is the prefix below the cacheable minimum (in which case promote to skill)?*

   If neither caching nor persistence is wired and the prefix exceeds the cacheable threshold, mark the subagent as a candidate for skill conversion. Annotate the stub with a `# TODO: anti-patterns/wasteful-subagent-context-reload` so the human reviewer sees the question explicitly.

3. **Eval-design rule.** Include a per-subagent **token-budget metric** in the judge harness. A subagent whose **token-per-call doesn't decrease across a session** (i.e., second call costs the same as the first, third call costs the same as the second) is the canary for this anti-pattern. With caching wired correctly, cache_read tokens should dominate after call 2; with memory persisted, the prompt itself should shrink across calls; with neither, token-per-call stays flat and that's the signal.

## Observability

For autonomous workers (claws) and long-running co-pilots specifically, log per-subagent:

- **Token spend per invocation** (broken into cache_read, cache_creation, and uncached input — the three fields Anthropic exposes in `usage`)
- **Cache hit rate** — `cache_read_input_tokens / (cache_read_input_tokens + cache_creation_input_tokens + input_tokens)`. A subagent with a stable prefix should sit ≥0.7 after the first call; below 0.3 sustained is wasteful.
- **Reload frequency** — how often does the subagent re-execute the same MCP query / file read / fetch within a single session
- **Token-per-output ratio** — total input tokens consumed by the subagent divided by useful output tokens it produced. Outliers across subagents are usually wasteful re-loaders.

The canary: **spike in subagent token spend without corresponding output growth**. When this fires, walk the subagent's prompt history and check whether the prefix is identical across calls (cacheable but uncached) or near-identical-but-not-byte-equal (cache-misses from prompt rebuild).

## Provenance

Surfaced during the patterns-deepening workstream's discussion of subagent vs skill design (2026-05-29). Observed shape: a subagent calling an MCP-backed research tool on every invocation to re-establish its context window, when the queries and results were stable across the session. The architectural mistake decomposes cleanly:

1. "We want this work isolated from the main conversation" → reached for subagent (right primitive for the stated requirement)
2. Didn't notice the context was effectively re-fetched per call (the failure)
3. Didn't wire prompt caching because the prefix wasn't structured for it (the second failure)
4. Didn't persist memory because the SDK didn't make it the easy path (the third failure)

Not yet promoted past `draft` because the in-repo session data hasn't been re-run with this anti-pattern in the architecture-proposer's prompt library. Worth promoting to `validated` once a discovery-inception session catches a wasteful-subagent proposal and the proposer either converts it to a skill or annotates the caching/memory requirement.

## Hard rules for inception's orchestrator-stub generator

1. Every subagent in the proposed `orchestrator.py` must cite its reason number (1, 3, 4, or 5) from the five-row matrix in `decision-guides/subagent-vs-skill-tradeoffs.md` — as an inline code comment on the subagent definition (e.g., `# subagent reason: 3 (specialized tool surface)`).
2. If the cited reason is #2 ("logical decomposition felt clean"), convert to skill — subagent is the wrong primitive.
3. If the subagent is called more than once per session AND has a stable prefix that exceeds the model's cacheable minimum (1,024–4,096 tokens depending on model), either wire prompt caching with the breakpoint on the last identical block, OR persist memory via the harness's checkpointer / `resume` mechanism, OR convert to skill. Pick one; the choice must be cited in the stub annotation.
4. Surface **token-per-subagent**, **cache hit rate**, and **reload frequency** metrics in the eval seed so this anti-pattern is observable post-deploy — not just at design time.
