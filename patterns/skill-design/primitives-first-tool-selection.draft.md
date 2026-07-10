---
title: Primitives-First Tool Selection: Code Execution Over Context Loading
category: skill-design
status: draft
last_updated: 2026-06-08
source_findings: []
source_external:
  - Anthropic Code with Claude London — 'Agent Decomposition' workshop (Will, Applied AI)
applies_when:
  workloads:
    - data-heavy-reasoning
    - single-purpose-agent
    - file-system-navigation
    - code-execution-required
  constraints:
    - large-dataset-processing
    - token-efficiency-critical
    - single-team-or-single-agent-scope
    - model-upgrade-stability-required
contradicts: []
related:
  - skill-design/atlan-mcp-integration
  - skill-design/atlan-context-repos
  - decision-guides/subagent-vs-skill-tradeoffs
  - architectures/single-agent-react
source_hash: 17d079aa26d52564
---

# Primitives-First Tool Selection: Code Execution Over Context Loading

Start agent tool selection with human-like primitives—code execution, file-system navigation, web search, to-do lists—before adding custom tools or MCP servers. Code execution is particularly powerful for data-heavy reasoning: instead of loading large datasets into context, let the agent write and run scripts to compute results, dramatically reducing token consumption and latency. MCP should be a last resort, justified only when multiple clients need the same standardized tool collection, not a first instinct. This approach keeps the tool layer stable across model upgrades and avoids the context pollution that comes from premature MCP adoption.

## Use when

- Agent needs to reason over large datasets (CSVs, Excel sheets, logs) — use code execution to compute results instead of loading raw data into context.
- Building a single-purpose agent or a small team of agents with overlapping needs — start with primitives + custom local tools.
- You want to upgrade the underlying model without rewriting the agent's tool layer — primitives remain stable across Claude versions.
- Agent needs file-system navigation, web search, or the ability to write and execute code — these are included by default in Claude Managed Agents.

## Don't use when

- You need tool definitions and governance across many independent clients or organizations — in that case, MCP's standardization is justified.
- The agent's work is lightweight and doesn't involve data processing or file manipulation — primitives may be overkill.
- You're building a one-off prototype and speed-to-first-token matters more than long-term maintainability — custom tools might be faster initially.

## Key gotchas

- **MCP context pollution.** MCP servers can bloat the context window with many tool definitions the model must reason over, increasing latency and cost. Only adopt MCP when multi-client sharing justifies the overhead.
- **Premature MCP adoption.** Teams often reach for MCP first, creating chaotic ecosystems of overlapping servers. Resist this; primitives + custom tools solve most single-agent problems.
- **Not every task benefits from code execution.** The source notes that primitives won't improve things every time—sometimes you'll regress. Measure before and after.
- **Static context loading is expensive for data-heavy work.** Uploading entire CSVs or large datasets into context consumes tokens and reasoning capacity; code execution is more efficient.

## Empirical anchor

Stock Pilot agent (before/after): a task consuming >200,000 tokens dropped dramatically when the agent switched from loading full data into context to using file-system + code-execution primitives. Both cost and execution time decreased. This is one workshop demo, not a broad production study — the speaker explicitly cautioned that primitives won't beat static tools every time. The plausible-on-its-face read: the win is largest for data-heavy workloads where the task is to extract or compute a subset of a large dataset rather than reason over the entire corpus at once.

Origin: Anthropic Code with Claude London — 'Agent Decomposition' workshop (Will, Applied AI).
