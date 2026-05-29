---
title: Claude Agent SDK — Builder's Deep Dive
category: harnesses
status: draft
last_updated: 2026-05-29
source_external:
  - Anthropic — "Agent SDK overview" (https://docs.claude.com/en/api/agent-sdk → https://code.claude.com/docs/en/agent-sdk)
  - Anthropic — "Subagents in the SDK" (https://code.claude.com/docs/en/agent-sdk/subagents)
  - Anthropic — "Agent Skills in the SDK" (https://code.claude.com/docs/en/agent-sdk/skills)
  - Anthropic — "Modifying system prompts" (https://code.claude.com/docs/en/agent-sdk/modifying-system-prompts)
  - Anthropic — "Claude Code documentation" (https://docs.claude.com/en/docs/claude-code/)
applies_when:
  workloads: [react-tool-use-agents, developer-tooling-agents, codebase-aware-agents, filesystem-resident-agents, internal-automation]
  constraints: [team-on-python-or-typescript, want-claude-code-ux-patterns, comfortable-with-anthropic-as-model-provider, agent-runs-in-your-process]
contradicts: []
related: [harnesses/landscape-2026-may, architectures/single-agent-react, decision-guides/what-kind-of-agent-are-you-building]
snapshot_date: 2026-05-29
---

# Claude Agent SDK — Builder's Deep Dive

The Claude Agent SDK is the library form of Claude Code. Same agent loop, same built-in tools, same skill and subagent semantics, same filesystem-based configuration — exposed as `claude_agent_sdk` (Python) and `@anthropic-ai/claude-agent-sdk` (TypeScript), runnable inside any process you control. As of mid-2026, Claude Code itself is the canonical reference build using this SDK, which means the patterns Anthropic ships in `~/.claude/skills/` and `.claude/` are not aspirational — they are the way the SDK's own most-used product is built.

This entry exists because the landscape survey can't carry the depth needed to actually decide for or against the Agent SDK on a specific use case. The ReAct-loop-as-harness opinion, the subagent context-isolation pitfall, the skills-as-files discovery rules, the `settingSources` trap, the way `excludeDynamicSections` interacts with prompt caching — these matter, and they don't fit a row in a comparison table.

## Where it sits

The SDK is not a graph. It is not a state machine. It is a ReAct loop with first-class tool use, where the loop *is* the harness. You give it a prompt, a set of allowed tools, and optional configuration; it runs `assistant → tool_use → tool_result → assistant → …` until the model decides it's done or a stop condition fires. No nodes, no edges, no checkpointer to wire up — the loop is the product.

The trade is the inverse of LangGraph's: LangGraph hands you the wiring and asks you to model your workflow as a graph; the Agent SDK hands you a finished loop and asks you to express your workflow as **tools, subagents, skills, and system-prompt customization**. If your workflow is naturally "agent with tools that occasionally delegates to specialists," this fits. If your workflow is a deterministic multi-stage pipeline with branching state, LangGraph or a plain orchestrator is the better shape.

It is also explicit about its provider: the model is Claude. Bedrock, Vertex, and Azure Foundry are supported as gateways (`CLAUDE_CODE_USE_BEDROCK=1`, `CLAUDE_CODE_USE_VERTEX=1`, `CLAUDE_CODE_USE_FOUNDRY=1`), but the SDK is not a provider-abstraction layer. If you need to swap to GPT or Gemini behind the same interface, this isn't the right choice — use OpenAI Agents SDK or LangGraph.

## Core primitives

| Primitive | What it is |
|---|---|
| **`query()`** | The entry point. Takes a prompt and `ClaudeAgentOptions`; returns an async iterator of messages. The whole agent loop lives inside this call. |
| **Tools** | Built-in (Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch, Monitor, AskUserQuestion, Agent, Skill) plus any you bring via MCP. Tool execution happens *inside* the SDK process — you don't implement the tool loop. |
| **Subagents** | Specialized child agents invoked via the `Agent` tool. Defined programmatically (`AgentDefinition`) or as `.claude/agents/*.md` files. Each runs in **its own fresh conversation** with its own system prompt and tool subset. |
| **Skills** | Filesystem artifacts at `.claude/skills/<name>/SKILL.md` with YAML frontmatter. Discovered at startup, loaded on demand when their `description` matches the user's request. **No programmatic API to register a skill** — they must live on disk. |
| **CLAUDE.md** | Project memory. Loaded into the *conversation* (not the system prompt) when `settingSources` includes `'project'` or `'user'`. Persistent across all sessions in a project. |
| **Settings / `settingSources`** | Controls which filesystem-based config loads: `'user'` (`~/.claude/`), `'project'` (`.claude/` in cwd and ancestors), or `[]` (none). Defaults to user+project. Set it to `[]` and you silently lose all skills, CLAUDE.md, and filesystem subagents. |
| **Hooks** | Callbacks at lifecycle points: `PreToolUse`, `PostToolUse`, `Stop`, `SessionStart`, `SessionEnd`, `UserPromptSubmit`. Used to validate, log, block, or transform agent behavior in-process. |
| **MCP servers** | External tool servers connected via stdio, SSE, or HTTP. `mcp_servers={"name": {"command": "...", "args": [...]}}`. Each server's tools are merged into the agent's tool list. |
| **Slash commands** | `.claude/commands/*.md` (legacy) or skills with `/<name>` invocation. User-initiated, deterministic kickoffs. |
| **Plugins** | Bundles of skills, agents, hooks, and MCP servers loaded programmatically via the `plugins` option. The packaging unit for portable capability. |

## The reasoning model — ReAct, all the way down

The Agent SDK implements ReAct (Reason → Act → Observe) with the loop owned by the SDK. The model writes a tool call; the SDK executes it and feeds the result back; the model writes the next tool call; loop until the model emits a final assistant message with no `tool_use` block. The contrast with the four other harness families:

| Harness | What runs the loop | How you extend it |
|---|---|---|
| **LangGraph** | A graph you wrote | Add nodes and edges; control flow is explicit |
| **OpenAI Agents SDK** | A loop the SDK owns | Add tools and handoffs; control flow is implicit |
| **Agentforce (Atlas)** | A loop Salesforce owns | Configure topics + actions in Agent Builder |
| **Claude Agent SDK** | A loop the SDK owns | Add tools, subagents, skills, hooks; control flow is implicit |
| **Anthropic Client SDK** | A loop *you* implement | You write the `while response.stop_reason == "tool_use"` |

The Agent SDK and OpenAI Agents SDK are in the same family — opinionated ReAct loops with tool use — and differ mostly in extension primitives (skills + subagents-as-files vs. handoffs + guardrails) and in how tightly they bind to their model provider.

The subagent primitive matters here. **Subagents are not orchestration nodes** — they are isolated ReAct loops the parent agent can delegate to, with their results returned as a single tool result. If your workflow needs deterministic ordering ("first do A, then do B, then do C"), don't model that as subagents — write it in the parent loop's tools or in code outside the SDK. Subagents shine for **context isolation** (the parent doesn't need to see 40 files the subagent read) and **parallel exploration**, not for sequencing.

## Minimum viable agent

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition

async def main():
    options = ClaudeAgentOptions(
        # System prompt: minimal default, with a custom persona layered on
        system_prompt=(
            "You are an incident triage agent. Given a stack trace, identify the "
            "likely root-cause file, summarize the failure mode, and propose a fix. "
            "Always cite file paths and line numbers."
        ),
        # Tools the parent agent can use without prompting for permission
        allowed_tools=["Read", "Glob", "Grep", "Bash", "Agent"],
        # Load project CLAUDE.md and any .claude/skills/ in the repo
        setting_sources=["project"],
        # A specialist subagent for deeper code analysis
        agents={
            "code-inspector": AgentDefinition(
                description=(
                    "Read-only code inspection specialist. Use when a stack trace "
                    "points into application code and you need to understand the "
                    "surrounding logic before proposing a fix."
                ),
                prompt=(
                    "You are a code inspector. Read the file at the cited line, "
                    "examine 30 lines of context above and below, and return a "
                    "concise summary of what the function does, what its callers "
                    "expect, and what could cause the observed failure. "
                    "Do not modify any files."
                ),
                tools=["Read", "Grep", "Glob"],
                model="sonnet",
            ),
        },
        permission_mode="acceptEdits",
        max_turns=20,
    )

    async for message in query(
        prompt=open("incident.txt").read(),
        options=options,
    ):
        if hasattr(message, "result"):
            print(message.result)

asyncio.run(main())
```

Roughly 35 lines, no tool-loop wiring, no LLM-call plumbing, no message-history bookkeeping. The SDK does all of it.

## Production patterns that show up in real Claude Code builds

### Skills as the unit of portable capability

Claude Code's own skill library (the dozens of `~/.claude/skills/*/SKILL.md` entries shipped with the product and via plugins) is the canonical reference for how to author skills:

```markdown
---
name: deep-research
description: |
  Deep research harness — fan-out web searches, fetch sources, adversarially
  verify claims, synthesize a cited report. Use when the user wants a deep,
  multi-source, fact-checked research report on any topic.
allowed-tools: [WebSearch, WebFetch, Read, Write]
---

# Deep Research

(Skill body — instructions, examples, references to companion files in the
same directory…)
```

The `description` is the routing logic — Claude reads every loaded skill's description at session start and decides when to invoke. Sloppy descriptions cause the skill to never trigger. The skill body is loaded *only when triggered* (progressive disclosure), so it can be long without burning context on every session.

Critical: **the `allowed-tools` frontmatter field is honored by the Claude Code CLI but ignored by the SDK.** In the SDK, tool restrictions are controlled by the top-level `allowed_tools` option. This is a real footgun for teams porting CLI workflows into SDK-hosted products.

### Subagent delegation with explicit context

Subagent prompts must be self-contained. The subagent receives:
- Its own `AgentDefinition.prompt`
- The Agent tool's prompt string (what the parent wrote when delegating)
- Project CLAUDE.md (if `settingSources` loads it)
- Tool definitions (inherited or subset)

It does **not** receive:
- The parent's conversation history
- The parent's tool results
- The parent's system prompt
- Preloaded skill content (unless explicitly listed in `AgentDefinition.skills`)

So when the parent delegates, the delegation prompt is the *only* parent → child channel. "Review the file" is useless; "Review `src/auth/login.py` for OAuth-token-handling issues, return findings with line numbers" is what works.

### Hooks for deterministic post-processing

Hooks are how you bolt determinism onto a non-deterministic loop. Real patterns:

- **`PostToolUse`** hook on `Edit|Write` → run a linter or type-checker; on failure, return an error string that the model sees as a tool result and self-corrects
- **`PreToolUse`** hook on `Bash` → match the command against an allowlist before letting it run
- **`Stop`** hook → run a validation pass on the final output; if it fails a schema check, return `{"decision": "block", "reason": "..."}` to push the model back into the loop
- **`UserPromptSubmit`** hook → enrich the user's prompt with context (current branch, recent failures) before the model sees it

This is the SDK's answer to "how do I get structured output from a non-deterministic agent" — wrap the loop with deterministic post-processors, not by trying to force the model into a JSON straitjacket.

### MCP for the long tail of external capability

MCP is a first-class citizen, not a bolt-on. The same `mcp_servers={...}` dict accepts stdio command specs, SSE URLs, or HTTP endpoints; the SDK handles connection lifecycle. Anthropic's bet on MCP as the universal tool protocol means that **every MCP server in the ecosystem is automatically available** to any Agent SDK build — Playwright, Slack, Linear, internal-data servers, vector stores, the lot.

### Settings inheritance and the `.claude/` directory

Filesystem config cascades: `~/.claude/` (user) → `.claude/` walked from cwd up to the repo root (project). For an SDK build, you decide which sources load via `setting_sources`. Defaults are `["user", "project"]`, which match Claude Code CLI behavior. The two real choices:

1. **Lean on user+project** — embrace the filesystem as your config surface. Skills, CLAUDE.md, slash commands, agent files all live in `.claude/`. Same artifacts work in Claude Code CLI and your SDK product.
2. **`setting_sources=[]`** — fully programmatic. Everything passed via `ClaudeAgentOptions`. Use when your agent ships as a binary or container and you don't want filesystem surprises.

Mixing the two ("I want skills but not CLAUDE.md") is awkward — `setting_sources` is the only knob, and it's all-or-nothing per source. Plugins are the workaround when you need scoped control.

### Slash commands as deterministic kickoffs

Skills can be model-invoked (Claude picks them up by description matching) or user-invoked (`/<skill-name>` in the prompt). Slash commands are how you give users a stable, fast path into a specific workflow — no description-matching ambiguity, no chance the model picks the wrong skill. Real Claude Code skills (`/init`, `/review`, `/security-review`, `/verify`) are mostly slash-invoked.

## Failure modes and gotchas

1. **Context window management is your problem.** The SDK doesn't compact automatically inside a session — once the loop fills the context window, you hit `context_length_exceeded`. Mitigations: use subagents to absorb file-reading into isolated contexts; use `max_turns` to cap runaway loops; resume with a fresh session and pass key facts forward.

2. **Subagent context isolation is silent.** If you delegate to a subagent and the subagent doesn't have the information it needs (because the parent didn't pass it in the Agent tool prompt), the subagent will hallucinate or ask the parent — and the parent often doesn't know either. Always treat the delegation prompt as the full brief.

3. **Tool-call loops.** The model can get stuck calling the same tool with slightly different arguments. `max_turns` is the blunt instrument. Better: `PostToolUse` hooks that detect repetition and return guidance ("you've called Read on this file 3 times; the answer is X, move on").

4. **`setting_sources=[]` silently disables skills.** A common bug: someone tightens config for "security," sets `setting_sources=[]`, and now no skill is discoverable. The model behaves correctly but lacks all the capability that lives in the filesystem. Test skill availability explicitly.

5. **`allowed-tools` in SKILL.md frontmatter is CLI-only.** The SDK ignores it. Tool restrictions must be set at the `query()` level. Builders coming from Claude Code CLI hit this on the first port.

6. **Token accounting is per-session and not partitioned by subagent in the same view.** Subagents have their own transcripts on disk but their token usage rolls up to the parent's billing. Cost surprises are usually a subagent running long under a parent that looked cheap.

7. **Structured output requires post-processing.** The SDK does not have a native JSON-mode equivalent. If you need typed output, take the model's final message and parse it (a `Stop` hook is the right place), then either accept or push back into the loop. Don't try to constrain the model with prompt-engineering alone — wrap it with a parser + retry.

8. **The `excludeDynamicSections` cache-sharing optimization is essential for fleets.** Without it, two identical agents running from different cwds get different system prompts (because the preset embeds cwd, OS, shell, git status) and miss the prompt cache. For a fleet of agents in containers, the difference is real money.

9. **Subagents cannot spawn subagents.** Hard limit. If you need three levels of delegation, model it as three sibling subagents from the parent, not as nested.

10. **Built-in tool descriptions live inside the SDK and you can't edit them.** If the model misuses `Bash` or over-uses `Read`, you can shape behavior via system prompt and hooks but you can't rewrite the tool definition. Bring your own tool via MCP if you need control.

11. **Permission modes are blunt.** `default` (prompt for everything), `acceptEdits` (auto-approve edits, prompt for risky ops), `bypassPermissions` (yolo mode), `dontAsk` (deny anything not in `allowed_tools`). For production builds you almost always want `dontAsk` plus an exhaustive `allowed_tools` list.

12. **Determinism is not the SDK's strong suit.** Two runs of the same prompt against the same code will differ. If your use case requires reproducibility (e.g., compliance-grade audit), wrap the SDK in a deterministic pre/post layer and treat the agent's output as advisory, not authoritative.

## When to choose the Claude Agent SDK

- Your workload is **ReAct with rich tool use** — read files, run commands, search the web, call APIs, write back
- You're building **internal developer tooling** and you want Claude Code's UX patterns (skills, slash commands, hooks, project CLAUDE.md) for free
- You want **subagents as a first-class isolation primitive** without writing the orchestration yourself
- Your team is **Python or TypeScript** and you don't want to fight a graph DSL
- You're comfortable committing to Claude as the model provider
- You want **portability between an interactive CLI surface and a programmatic agent** — the same skill and subagent artifacts work in both

## When *not* to choose it

- You need a **graph state machine** with explicit branching, fan-out/fan-in, and durable checkpointing → LangGraph
- Your agent must be **Salesforce-resident** with Trust Layer governance → Agentforce
- You need **enterprise multi-tenant with provider abstraction** and the ability to swap models per tenant → OpenAI Agents SDK or LangGraph
- You're building a **pure data-resident agent** that should run inside the warehouse next to your data and never see external tools → Cortex Agents / Genie (with the usual caveats about their narrower surface)
- You need **provider abstraction** so you can ship to customers who require non-Anthropic models → not the right fit
- You need **reproducibility / determinism** as a hard requirement → wrap with deterministic layers, or pick a non-agent design

## Integration shape with external metadata or knowledge systems

The SDK integrates with external systems primarily through **MCP servers** and **tools-as-skills**. A typical pattern:

- An MCP server exposes your domain APIs (catalog lookups, asset writes, governance reads) as tools the agent can call
- A set of skills under `.claude/skills/` encode the **how-to** for the agent: when to query, what shape of question to ask, what to do with the result
- CLAUDE.md carries project-level conventions (naming, table layout, query patterns) that the agent should respect on every turn

This means the same Atlan/Snowflake/internal-tool integration looks like (a) an MCP server registered in `mcp_servers`, plus (b) one or more skills that teach the agent the right way to use it. The agent itself stays neutral; the integration lives in the MCP+skill bundle. Plugins package this so it's distributable.

For metadata-aware agents specifically, the Agent SDK is well-suited when your agent's job is to *act* on top of metadata you've already curated elsewhere. It's less well-suited as the system-of-record for metadata itself — that belongs in a catalog, and the agent reads/writes through the catalog's MCP server or API.

## Maturity / ecosystem snapshot mid-2026

- Python SDK (`claude-agent-sdk`) and TypeScript SDK (`@anthropic-ai/claude-agent-sdk`) are GA, with weekly-ish releases.
- TypeScript SDK bundles the Claude Code native binary as an optional dependency — install one package, get the runtime.
- Authentication: API key direct, Bedrock, Vertex, Azure Foundry, Claude Platform on AWS (`CLAUDE_CODE_USE_ANTHROPIC_AWS=1` with workspace ID). Subscription-based usage (Pro/Team/Enterprise) draws from a separate monthly Agent SDK credit pool starting June 2026.
- Plugin ecosystem: Anthropic ships first-party plugins (deep-research, code-review, verify, skill-creator, schedule, loop, claude-api, run, init) and the marketplace for third-party plugins is operational.
- MCP ecosystem: 1000+ public servers, plus the well-known platform integrations (GitHub, Slack, Linear, Notion, Stripe, AWS, GCP, Snowflake, Databricks).
- Managed Agents (Anthropic-hosted runtime) is the production-deployment path for teams that don't want to operate the runtime themselves — same agent design moves over with mostly-config changes.
- The largest install base for the Agent SDK is **Claude Code itself**, which means every UX pattern in the docs has been load-tested by hundreds of thousands of developers in production. That's the strongest signal in the SDK's favor.

## The honest framing

If LangGraph is "I'll wire the agent graph myself" and Agentforce is "Salesforce will run the agent for me," the Claude Agent SDK is **"Anthropic will run the loop, you bring the tools and the skills."** It's the most opinionated of the code-first frameworks about *how* an agent should work — single ReAct loop, subagents for isolation, skills for capability, hooks for determinism — and that opinion happens to be the one that built Claude Code. For workloads that look like Claude Code (codebase-aware, tool-rich, human-in-the-loop or close to it), the SDK is the shortest path to a working agent. For workloads that don't, the opinion gets in the way and a different harness is the right call.
