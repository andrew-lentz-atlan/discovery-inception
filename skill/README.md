# `skill/` — the v1.0 packaging target (design doc)

This directory contains the **runtime contract** for the discovery-inception agent: the design of what a portable, runtime-independent skill bundle looks like.

> **Status: design doc, not yet executed.** The actual agent is still running through `agent/v08/` for current research and demos. This directory describes the target architecture that v1.0 packaging will produce. Read this if you want to understand where the project is going OR if you're building a runtime that consumes the skill.

---

## The mental model

Discovery-inception isn't a single LLM call wrapped in a skill file (like a "build a deck" skill in Claude Code). It's a **multi-agent system**: 5 focused sub-agents running in sequence per customer turn, with structured state that persists across turns. Quality is materially better than a single-prompt agent (see `findings/`).

That means it needs a runtime. The runtime can be small (~500 lines of Python), but it can't be zero. It has to:

- Load prompts
- Call the LLM for each sub-agent
- Validate structured outputs against schemas
- Maintain session state across turns
- Execute the tools the mega-agent invokes
- Capture per-step trace

A "compliant runtime" is any code that does these six things. Our reference implementation is in `runtimes/` (after v1.0 reorg). Anyone can write another one — in Python, Rust, TypeScript — as long as they satisfy the contract in `manifest.yaml`.

---

## What's in the bundle (target structure)

```
skill/
├── manifest.yaml           ← runtime contract: inputs, outputs, required capabilities
├── orchestration.yaml      ← per-turn pipeline: which sub-agents run, when, with what inputs
├── prompts/                ← markdown templates with {VARIABLE} substitution
│   ├── triage.md
│   ├── distill.md
│   ├── synthesizer.md
│   ├── mega_agent.md       ← what's V08_SYSTEM_PROMPT_TEMPLATE today
│   ├── sharpener.md
│   └── tensions.md
├── schemas/                ← JSON Schema for every structured output
│   ├── triage_result.json
│   ├── distilled_fact.json
│   ├── working_theory.json
│   ├── sharpener_result.json
│   ├── tensions_result.json
│   └── final_spec.json     ← THE OUTPUT CONTRACT (what feeds CES + downstream)
└── tools/                  ← functions the mega-agent can call mid-turn
    ├── get_current_spec_state.py
    ├── get_checklist_progress.py
    ├── synthesize_my_thinking.py
    ├── find_tensions.py
    └── _tool_schemas.json  ← OpenAI tool-call format for all of the above
```

Currently this directory only has the `manifest.yaml`, `orchestration.yaml`, and this README. The prompts, schemas, and tool implementations live in `agent/prompts/`, `agent/schemas.py`, and `agent/v08/spec_tools.py` respectively. The v1.0 reorg will move them here.

---

## The runtime contract (summary — full version in manifest.yaml)

**Inputs:**
- `use_case_seed` — one-line goal (required)
- `role_id` — slug pointing to RoleContext priors (optional)
- `initial_customer_artifact` — raw JD/runbook text for intake (optional)

**Outputs:**
- `spec.json` — structured discovery output
- `spec.md` — human-readable rendering
- `session_trace` — full per-step audit log

**Required runtime capabilities:**
- OpenAI-compatible LLM endpoint with tool calling
- Prompt template substitution (`{VARIABLE}` replacement in markdown)
- Structured output validation (JSON Schema or equivalent)
- Stateful session management across many turns
- Tool execution (Python functions or equivalent)

**Optional:**
- Retry on transient failures (LiteLLM-via-Bedrock occasional flakiness)
- Triage fallback to `concrete` label when retries exhaust

---

## Why this is structured this way

The architectural research that led to v0.8 (`findings/01..05`) produced empirical findings about WHAT works, not how to package it. Those findings are runtime-independent:

- Decomposition is load-bearing for structured output (not conversation)
- Lazy synthesis (model-judged) beats eager synthesis (per-turn)
- Adversarial post-processing catches weak probes
- Free-form mega-agent output beats format-constrained output

To preserve those findings as durable IP, the **prompts + schemas + orchestration spec** need to be portable. The runtime is commodity — anyone can write one. The skill bundle is the asset.

This separation also makes the project resilient to changes in the LLM landscape:
- If a new SDK appears (Anthropic SDK overtakes OpenAI's), the runtime changes; the skill bundle doesn't.
- If a new model becomes preferred, just update default_models in manifest.yaml.
- If a downstream consumer wants different output format, they read final_spec.json and transform it; the skill bundle doesn't change.

---

## How a downstream consumer (e.g., CES) uses this

```
1. CES (or any consumer) initiates a discovery session via the runtime
   (could be our MCP server, our CLI, an API call, or a CES-internal
   implementation of the runtime contract).

2. The runtime executes orchestration.yaml turn by turn. Each turn:
     - Reads a customer message
     - Runs triage → distill (conditional) → mega-agent (with tools)
       → probe-sharpener (post-process)
     - Persists structured state

3. Session closes (human or agent-triggered). Runtime executes the
   on_close lifecycle: final synthesis + export.

4. Output: spec.json + spec.md. The consumer (CES, a builder, etc.)
   reads these as input to whatever they're doing next.
```

CES's specific consumption pattern (per the integration discussion):
> CES's bulk-repos-claude pipeline reads our spec.json as an additional input to its synthesis_agent, alongside its existing cold-start metadata snapshot. The synthesis_agent then produces a richer context_repo than it could from metadata alone.

The contract surface CES cares about is `final_spec.json`. The orchestration internals are ours; the output shape is the integration point.

---

## Why our infrastructure is hand-rolled (and yours shouldn't be)

**Short version:** discovery-inception is itself an ablation experiment — findings/06-09 measured orchestration-layer variables (sub-agent model choice, context budget, synthesizer timing, sharpener rewrite rate) that stock frameworks (LangChain / LangGraph / CrewAI / AutoGen) would have confounded. Hand-rolling was *required for the experiment*, not a stylistic preference.

That research case is the narrow exception, not the rule. The skill bundle is **framework-independent by design** — the orchestration_spec is a portable contract you implement on whichever harness fits the consumer's stack. If you're a downstream builder consuming this skill, your default should be a real framework (Claude Agent SDK, LangGraph, OpenAI Agents SDK, Pydantic AI). See `patterns/decision-guides/framework-or-hand-roll.md` for the full reasoning on why.

Specifically: the engineering costs of hand-rolling — maintenance burden, cognitive onboarding cost, lost knowledge transfer across builds, weak operational maturity, slow incident response, reviewer illegibility — compound over a system's lifetime. Framework adoption pays back quickly. Discovery-inception's own infrastructure is migrating as the research-stage justification expires: the inception pipeline already runs on a LangGraph `StateGraph` adapter (`--runtime langgraph`, validated A/B in `findings/10`); the discovery-layer migration is still backlog.

**Long version:** see the README at the project root and `patterns/decision-guides/framework-or-hand-roll.md`.

---

## What this directory will look like at v1.0

```
skill/
├── manifest.yaml           ← (THIS FILE — already drafted)
├── orchestration.yaml      ← (THIS FILE — already drafted)
├── README.md               ← (THIS FILE)
├── prompts/                ← migrated from agent/prompts/
├── schemas/                ← derived from agent/schemas.py (Pydantic → JSON Schema)
└── tools/                  ← migrated from agent/v08/spec_tools.py (self-contained since the v0.6/v0.7 archival)
```

When that migration happens (post-CES meeting):
- `runtimes/core/` becomes the reference implementation of the runtime contract
- `runtimes/cli/`, `runtimes/mcp/`, `runtimes/api/` each wrap `runtimes/core/`
- `agent/v08/` moves to `archive/research-iterations/`, joining `v06/` and `v07/` (already archived there, with a README explaining what each version was)

The findings docs stay. The demos stay. The intake pipeline stays separate. The discovery agent's research code gets archived, the skill bundle becomes the durable artifact.
