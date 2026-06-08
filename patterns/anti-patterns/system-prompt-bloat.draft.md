---
title: System-Prompt Bloat: Kitchen-Sink Instructions Degrade Agent Performance
category: anti-patterns
status: draft
last_updated: 2026-06-08
source_findings: []
source_external:
  - Anthropic Code with Claude London — 'Agent Decomposition' workshop (Will, Applied AI)
applies_when:
  workloads:
    - single-agent-react
    - multi-step-task-with-conditional-logic
    - agent-with-evolving-business-rules
  constraints:
    - system-prompt-grown-beyond-one-page
    - performance-regression-in-previously-working-tasks
    - skill-or-retrieval-layer-available
contradicts: []
related:
  - anti-patterns/over-decomposition
  - skill-design/inner-pipeline
  - decision-guides/subagent-vs-skill-tradeoffs
source_hash: fa872cfcab59824c
---

# System-Prompt Bloat: Kitchen-Sink Instructions Degrade Agent Performance

System-prompt bloat occurs when business requirements are progressively appended to the system prompt, growing it to hundreds of lines and degrading agent performance across previously-working tasks. The root cause is context pollution: the model receives information it doesn't need for the current task, leading to confusion and hallucination, especially when conflicting policies accumulate in the same prompt. The fix is progressive disclosure via skills—moving time-conditional business logic, policies, and procedures out of the always-on system prompt into composable skills that Claude loads only when needed.

## Use when

- Agent system prompt has grown past one page and new requirements are being appended as business logic.
- Agent performance is regressing in previously-working areas despite adding new capabilities.
- You notice contradictory instructions or policies coexisting in the system prompt.
- Context window is being consumed by information the agent only needs for specific tasks, not all tasks.

## Don't use when

- System prompt is lean and focused on core, task-agnostic information (values, tone, safety constraints).
- All instructions in the system prompt are genuinely needed regardless of the task.
- Agent has no mechanism to load conditional information (no skill system or retrieval layer available).

## Key gotchas

- **Conflicting policies hide in length.** Two policies grown into different parts of a 400-line prompt can contradict each other; the model gets confused and picks wrong, even when it has the right baseline data.
- **Context pollution actively confuses the model.** Irrelevant instructions waste tokens and degrade reasoning; it's not just inefficiency—it's a performance regression.
- **The easy move is the wrong move.** Appending to the system prompt feels faster than packaging a skill, but it compounds into hallucination and degradation.

## Empirical anchor

Stock Pilot eval (R8, forecasting during promotion month) showed the agent pulling correct baseline (12 units/day) and multiplier (3.1x), then hallucinating the calculation using 1.35x instead; root cause was contradictory policies buried in a ~400-line system prompt. After refactoring—reducing the system prompt from ~400 lines to ~50 lines (ultimately ~15 lines once business logic moved to skills) and applying complementary fixes—the same eval climbed from 62%/83% baseline to ~92%.

Origin: Anthropic Code with Claude London — 'Agent Decomposition' workshop (Will, Applied AI). "Stock Pilot" is the workshop's demo agent, not an internal Atlan system; the eval numbers are from the live workshop run.
