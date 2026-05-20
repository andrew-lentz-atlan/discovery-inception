# discovery-inception

A chained-agent **discovery system** that interviews a customer to produce a structured spec for a new AI agent build. Inspired by ThoughtWorks Lean Inception, adapted to AI agent design. The tester (or FDE) plays customer; the discovery agent plays Forward Deployed Engineer.

The premise: bottom-up context (metadata scans, RAG, descriptions) and top-down context (interview-derived tacit knowledge) are complementary. Most tools today do bottom-up. This project does **top-down** — the part that only emerges from sitting with a senior practitioner and asking the right questions.

The output is a structured spec.json + human-readable spec.md that downstream consumers (Atlan's CES, a builder, an FDE) use to construct the actual customer agent.

## Status

- **2026-05-13** — v0.8 ships. Probe-sharpener post-processor + tensions surfacing. Beats v0.7 on quality (44 vs 38 facts captured, 4 vs 3 candidate framings, 3 internal tensions surfaced) on the same 50-turn script. [findings/05](findings/05-v08-probe-sharpener-and-tensions.md).
- **2026-05-12** — v0.7 + deterministic close-out. Fixed recency-bias in v0.6's eager synthesis. [findings/04](findings/04-v07-deterministic-closeout.md).
- **2026-05-11** — v0.7 ships. Lazy synthesis + free-form mega-agent. [findings/02](findings/02-v07-lazy-synthesis-and-free-form-output.md).
- **2026-05-05** — v0.6 hybrid + first three-way comparison: chained vs mega-agent vs hybrid. [findings/01](findings/01-architecture-comparison.md).
- **2026-05-04** — Closed loop demo: intake → priors → harness → agent uses priors. The architecture works end-to-end. [demos/closed-loop-sc.md](demos/closed-loop-sc.md).
- **2026-05-03** — Project conceived. Intake pipeline built. First production run on the Solutions Consultant role.

## Try it (three install paths, in order of friction)

### Easiest — Claude skill (one curl)

For colleagues who want to test on their own use case with zero engineering setup:

```bash
curl -fsSL https://raw.githubusercontent.com/andrew-lentz-atlan/discovery-inception/main/claude-skill/SKILL.md \
    -o ~/.claude/skills/discovery-inception.md
```

Restart Claude Code / Desktop, then in any chat:

> *"Use the discovery-inception skill — I want to test it for a renewal-risk agent for our CSM team at FinCo."*

Claude (following the skill) clones the repo, runs `uv sync`, prompts you for LITELLM credentials if needed, captures your use case + optional artifact, drives the discovery interview turn-by-turn, and exports a `spec.md` you could hand to a builder. See [`claude-skill/README.md`](claude-skill/README.md).

### Recommended for ongoing use — MCP server in Claude Code/Desktop

If you'll run discovery on multiple use cases, install the MCP server once and the discovery tools become available across all Claude sessions. See [`agent/mcp_server/README.md`](agent/mcp_server/README.md).

### Headless — CLI

For terminal users or scripting:

```bash
git clone https://github.com/andrew-lentz-atlan/discovery-inception.git
cd discovery-inception && uv sync
# add LITELLM_BASE_URL + LITELLM_API_KEY to .env

uv run python -m agent.cli generate-priors --role-id <slug> --artifact-file <path>
uv run python -m agent.cli start-session --use-case-seed "<one-liner>" --role-id <slug>
# (continue with submit-turn, state, finalize)
```

## Architecture (briefly)

Discovery-inception is an **agent system**, not a single LLM-call wrapper. Per customer turn, five sub-agents run in sequence:

```
customer message
        │
        ▼
  triage  →  distill (if concrete)  →  mega-agent (with tools)  →  sharpener (if probe)
                       │                       │                          │
                       ▼                       ▼                          ▼
                  fact captured       conversational response       weak probe rewritten
                                      (may invoke synthesis,
                                       find_tensions tools)
```

At session close, a deterministic synthesizer runs once over the full conversation to produce the final working theory (closes a recency-bias failure mode we caught in earlier versions — see [findings/04](findings/04-v07-deterministic-closeout.md)).

Each sub-agent has its own focused prompt + structured Pydantic output. They share session state (working theory, captured facts, gaps) maintained by the orchestrator. The orchestrator is ~500 lines of Python — small enough to read in one sitting.

**The deeper architecture explanation** (skill bundle + runtimes + contract) is at [`skill/README.md`](skill/README.md). That's the v1.0 packaging target — separating the durable IP (prompts, schemas, orchestration spec) from the runtime that interprets it.

## Why we didn't use LangChain / LangGraph / CrewAI / AutoGen

At research stage, framework opinions about orchestration would have entangled with the architectural variables we were measuring (decomposed-vs-mega-agent, lazy-vs-eager synthesis, free-form-vs-structured output). Frameworks have orchestration patterns baked in — adopting any of them would have meant our findings were partly findings about *the framework*, not the architecture.

We use proven libraries (OpenAI SDK, Pydantic, FastAPI, MCP SDK, python-dotenv) that do one thing each. We don't use agent frameworks that impose orchestration mental models.

The architectural findings are framework-independent. Anyone wanting to re-implement on LangGraph or another stack can take the patterns directly — the skill bundle (prompts + schemas + orchestration spec) is portable. See `skill/manifest.yaml` for the contract.

## Companion: the harness

The standalone [andrew-lentz-atlan/harness](https://github.com/andrew-lentz-atlan/harness) is a minimal, fully-inspectable LLM agent runtime supporting both LiteLLM and llama-server backends. We used it for the [closed-loop demo](demos/closed-loop-sc.md) on May 4 to prove that structured priors actually shape agent behavior, with full per-step trace as evidence. The discovery agent built since is a **separate runtime** — same "no black-box, full trace" philosophy, but with its own purpose-built orchestrator for multi-agent pipeline shape (the harness is single-agent ReAct shape). They're companion tools that share a philosophy, not nested systems. The harness remains useful as a sandbox for testing arbitrary agents against priors.

## Repository layout

```
discovery-inception/
│
├── agent/                        ← current implementation (v0.8)
│   ├── prompts/                  ← sub-agent system prompts (markdown templates)
│   ├── schemas.py                ← Pydantic models for structured outputs
│   ├── state.py                  ← session state + checklist evaluation
│   ├── v05.. v08/                ← research iterations (v0.8 is current)
│   ├── orchestrator.py           ← v0.5 chained (legacy, kept for comparison)
│   ├── mcp_server/               ← MCP server runtime
│   ├── cli.py                    ← CLI runtime
│   └── baselines/                ← comparison runners + scripts + results
│
├── skill/                        ← v1.0 packaging target (design doc, not yet executed)
│   ├── manifest.yaml             ← runtime contract
│   ├── orchestration.yaml        ← declarative per-turn pipeline
│   └── README.md                 ← contract for compliant runtimes
│
├── intake/                       ← separate pipeline: priors generation from artifacts
│
├── findings/                     ← research notes (the empirical case for v0.8 architecture)
│   ├── 01-architecture-comparison.md
│   ├── 02-v07-lazy-synthesis-and-free-form-output.md
│   ├── 03-v07-25-turn-validation.md
│   ├── 04-v07-deterministic-closeout.md
│   ├── 05-v08-probe-sharpener-and-tensions.md
│   └── data-collection-roadmap.md
│
├── demos/                        ← reference outputs (what good looks like)
│   ├── closed-loop-sc.md         ← May 4 harness demo
│   └── finco_sales_analyst/      ← 50-turn TechCo demo for the CES meeting
│
├── claude-skill/                 ← installable Claude skill (the curl-one-liner option)
│
├── plans/                        ← original design docs (mostly historical now)
├── scripts/                      ← role_to_prompt.py + comparison helpers
└── skills/                       ← generated RoleContext priors (per role_id)
```

## Where to start reading

| Read this | When |
|---|---|
| **[`skill/README.md`](skill/README.md)** | If you want to understand the architecture as a portable system, not as the current research code |
| **[`findings/05-v08-probe-sharpener-and-tensions.md`](findings/05-v08-probe-sharpener-and-tensions.md)** | The most recent research note. Where v0.8 came from. |
| **[`findings/01-architecture-comparison.md`](findings/01-architecture-comparison.md)** | The first big empirical finding. Three architectures, one comparison. |
| **[`demos/finco_sales_analyst/02_spec_v08.md`](demos/finco_sales_analyst/02_spec_v08.md)** | A real spec from a 50-turn discovery run. What the output actually looks like. |
| **[`demos/finco_sales_analyst/03_ces_meeting_handout.md`](demos/finco_sales_analyst/03_ces_meeting_handout.md)** | How discovery-inception's output composes with Atlan's CES pipeline |
| **[`plans/00-vision-and-glossary.md`](plans/00-vision-and-glossary.md)** | The original project framing (`plans/00`–`04`; mostly historical now) |
| **[`plans/05-technical-thread-discovery.md`](plans/05-technical-thread-discovery.md)** | The forward roadmap starts here. Adds a technical/data/context-aware thread to discovery. |
| **[`plans/06-atlan-context-integration.md`](plans/06-atlan-context-integration.md)** | Bidirectional flow with Atlan — read tenant context to skip known questions; capture gaps to feed back |
| **[`plans/07-patterns-knowledge-base.md`](plans/07-patterns-knowledge-base.md)** | The "Karpathy wiki" for agentic patterns. Externalizes opinion out of prompts. |
| **[`plans/08-inception-agent.md`](plans/08-inception-agent.md)** | The inception half — skill / architecture / runtime proposers + scaffold writer |
| **[`plans/09-context-debt-migration-backlog.md`](plans/09-context-debt-migration-backlog.md)** | What's still baked into prompts that should migrate to patterns. Read before touching any prompt. |

## Note on the planning docs

The `plans/` directory holds two distinct things:

- **`plans/00`–`04`** — the original design docs from early May. They're mostly **historical now** — the research findings (`findings/`) reflect what we actually validated, which differs in places from the original plans. Read for project conception; read findings for what we now believe.
- **`plans/05`–`09`** — the v1.0+ roadmap. Five docs covering the forward work: extending discovery with a technical-concern thread, integrating with Atlan as the bottom-up context layer, externalizing prompt opinions into a queryable patterns knowledge base, building the inception half (skill / architecture / runtime proposers), and tracking the context-debt migration backlog. These define the next major version.

The biggest revision in the historical plans: discovery was framed as a four-stage pipeline (First Principles → Gap Iteration → Validator → Build Bridge). The actual v0.8 implementation fuses Stages 1–3 into a single conversational agent with multi-sub-agent extraction. Stage 4 (Build Bridge) is now reframed: it lives in `plans/08-inception-agent.md` as the explicit "agent that helps build other agents" half of the project. See [`demos/finco_sales_analyst/03_ces_meeting_handout.md`](demos/finco_sales_analyst/03_ces_meeting_handout.md) for the CES integration story.
