# discovery-inception

A research project to build a **Discovery Inception agent**: a multi-stage AI system that runs structured discovery for new agentic use cases the way a Forward Deployed Engineer would. Inspired by ThoughtWorks Lean Inception, adapted to AI agent design instead of application design.

This directory holds **planning only**. No code yet. Implementation will live alongside or on top of `../harness/` once the design is locked.

## What this project is

> The thing we discovered: filling AI tools with raw context isn't enough. The bottleneck is *decomposition* — translating fuzzy human processes into structured steps a model can execute. That skill has always been the heart of software engineering. The medium just changed.

This project tests that thesis by building the tool that does decomposition for a customer use case, end to end. It is the practical artifact that proves (or disproves) the worldview.

## Where to start

| Read this | When |
|---|---|
| [00-vision-and-glossary.md](plans/00-vision-and-glossary.md) | First. The thesis, design principles, and terminology we landed on. |
| [01-architecture.md](plans/01-architecture.md) | When you want the system shape. Pipeline stages, how it sits on top of `../harness/`, and the closed loop with the trace layer. |
| [02-intake-agent.md](plans/02-intake-agent.md) | When you're ready to build the first concrete piece. This is the smallest scoped experiment that pressure-tests the most novel idea (CaaS). |
| [03-stages-deep-dive.md](plans/03-stages-deep-dive.md) | When you need the per-stage detail. Hard parts, prompting notes, sub-agents per stage. |
| [04-future-considerations.md](plans/04-future-considerations.md) | When you've got an MVP and need to think about output format, evals, scale. Parking lot for things that aren't on the critical path now. |

## Status

- 2026-05-03: Project conceived. Planning docs drafted. No implementation. Next concrete move is the intake agent in [`02-intake-agent.md`](plans/02-intake-agent.md).

## Companion: the harness

- [andrew-lentz-atlan/harness](https://github.com/andrew-lentz-atlan/harness) — a minimal, fully-inspectable LLM agent harness. This is what consumes the `RoleContext` outputs we produce and runs the actual agent. Its trace view is the introspection layer that closes the discovery → build → trace → feedback loop:

```
discovery-inception produces context repo
        │
        ▼
harness consumes it and runs the agent
        │
        ▼
harness's trace tab reveals which steps had bad context
        │
        ▼
feedback patches the discovery output
```

Currently the harness is llama-server-only. The next step (in flight) is to add a LiteLLM proxy backend so anyone with proxy creds can run it without a local model — see `plans/04-future-considerations.md` for the integration plan.
