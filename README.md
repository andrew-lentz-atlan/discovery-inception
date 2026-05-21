# discovery-inception

A two-stage agent system for **building other agents**. Discovery extracts tacit context from a customer (or an artifact, or a transcript) into a structured spec. Inception turns that spec into a starter agent design — proposed skills, architecture, runtime, scaffolded code. The goal isn't to ship a 100/100 agent on the first pass; it's to compress the human builder's iteration time from weeks to days by giving them a defensible candidate to react to.

The project is the top-down complement to bottom-up tools (metadata scans, RAG, descriptions). Bottom-up tools see what's already documented. Discovery-inception extracts the part that lives only in senior practitioners' heads — decision rules, anti-goals, unwritten patterns — and turns it into something an agent can read.

## What works today

| Stage | State | Notes |
|---|---|---|
| **Discovery** | v0.8 live | Used end-to-end. Install paths below. Validated empirically (`findings/01–05`). |
| **Intake (priors)** | Live | Produces a `RoleContext` from any artifact (JD, runbook, scoping transcript). Includes a `--use-case` orientation flag for meta-artifacts. |
| **Patterns knowledge base** | 7 seed entries | The agentic-patterns wiki the inception agent consults. Curator agent partial. |
| **Inception** | 2 of 6 sub-agents | `workload_classifier` + `skill_proposer` working. Independently reproduces a hand-derived skill design on the P&G validation case. |
| **Atlan integration, feedback loops** | Designed | See `plans/05`–`10` for the v1.0+ roadmap. |

## Try it (discovery only — inception is still being built)

**Easiest — Claude skill, one curl:**

```bash
curl -fsSL https://raw.githubusercontent.com/andrew-lentz-atlan/discovery-inception/main/claude-skill/SKILL.md \
    -o ~/.claude/skills/discovery-inception.md
```

Restart Claude Code / Desktop, then in any chat: *"Use the discovery-inception skill — I want to test it for a renewal-risk agent for our CSM team at FinCo."* Claude clones the repo, sets up dependencies, drives the discovery interview turn-by-turn, exports `spec.md`.

**Alternatives:**
- MCP server (recommended for ongoing use across many sessions): see [`agent/mcp_server/README.md`](agent/mcp_server/README.md)
- CLI (headless / scripting): see [`agent/cli.py`](agent/cli.py) — `generate-priors` → `start-session` → `submit-turn` → `finalize`

## Architecture in one diagram

```
DISCOVERY (per customer turn)
  ┌─────────────────────────────────────────────────────────────────┐
  │  triage → distill → mega-agent (with 4 tools) → sharpener       │
  │              │            │                          │           │
  │       fact captured   conversational            weak probe      │
  │                       response                  rewritten        │
  └─────────────────────────────────────────────────────────────────┘
                          │
                          ▼ (at session close)
              deterministic synthesizer → spec.md + spec.json

INCEPTION (consumes the spec)
  ┌─────────────────────────────────────────────────────────────────┐
  │  workload_classifier → skill_proposer → architecture_proposer   │
  │                                              │                   │
  │  → runtime_proposer → scaffold_writer → agent_starter/           │
  └─────────────────────────────────────────────────────────────────┘
                          ▲
                          │ consults
                          ▼
                    patterns/ knowledge base
                    (architectures, anti-patterns, skill-design,
                     harnesses, decision-guides — all citation-rich)
```

Five sub-agents per discovery turn; six sub-agents in the inception pipeline; a separate patterns curator agent maintains the knowledge base. Three feedback loops connect everything — see [`plans/10`](plans/10-feedback-loop-and-knowledge-promotion.md).

The orchestrator is ~500 lines of plain Python with structured Pydantic outputs at every step. No framework opinions; full per-step trace; no black box.

## Repository layout

```
discovery-inception/
├── agent/
│   ├── v05/ v06/ v07/ v08/    research iterations (v0.8 is live)
│   ├── inception/             the inception agent (partial)
│   ├── patterns_curator/      the patterns knowledge base maintainer (partial)
│   ├── mcp_server/            MCP runtime — wired to v0.8
│   ├── cli.py                 CLI runtime
│   └── orchestrator.py        v0.5 chained baseline + shared helpers
│
├── intake/                    priors pipeline (artifact → RoleContext)
├── patterns/                  the agentic-patterns knowledge base
├── skill/                     v1.0 packaging target (design)
├── plans/                     design docs (00–04 historical, 05–10 forward roadmap)
├── findings/                  empirical research notes (the architectural receipts)
├── demos/                     reference outputs (what good looks like)
├── claude-skill/              installable Claude skill
└── skills/                    generated RoleContext priors (per role_id)
```

## Where to read next

Three reader paths, depending on what you're trying to understand:

| If you want to... | Read this |
|---|---|
| **Understand what this project does + why it exists** | This README + [`plans/00-vision-and-glossary.md`](plans/00-vision-and-glossary.md) |
| **See empirical receipts behind every architectural choice** | [`findings/01-architecture-comparison.md`](findings/01-architecture-comparison.md) → [`findings/05-v08-probe-sharpener-and-tensions.md`](findings/05-v08-probe-sharpener-and-tensions.md) (the rest of `findings/` is reachable from there) |
| **See what good output looks like** | [`demos/finco_sales_analyst/02_spec_v08.md`](demos/finco_sales_analyst/02_spec_v08.md) — a real spec from a 50-turn run |
| **Understand the v1.0+ roadmap** | [`plans/05-technical-thread-discovery.md`](plans/05-technical-thread-discovery.md) → `plans/06` → … → [`plans/10`](plans/10-feedback-loop-and-knowledge-promotion.md). Six docs; the inception half lives in [`plans/08`](plans/08-inception-agent.md). |
| **Understand the patterns library** | [`patterns/README.md`](patterns/README.md) + [`patterns/SKILL.md`](patterns/SKILL.md). Browse `patterns/architectures/` for examples. |
| **Understand the portable-bundle / runtime separation** | [`skill/README.md`](skill/README.md) — the v1.0 packaging target |

## A note on framework choice

We didn't use LangChain / LangGraph / CrewAI / AutoGen. At research stage, framework opinions about orchestration would have entangled with the architectural variables we were measuring. We use boring libraries (OpenAI SDK, Pydantic, FastAPI, MCP SDK) and a hand-rolled orchestrator. The architectural findings are framework-independent — anyone can re-implement on LangGraph with the skill bundle (prompts + schemas + orchestration spec) as the contract. Full explanation in [`plans/00-vision-and-glossary.md`](plans/00-vision-and-glossary.md).

## A note on the harness

The standalone [andrew-lentz-atlan/harness](https://github.com/andrew-lentz-atlan/harness) is a single-agent ReAct runtime used for the May 4 closed-loop demo proving that structured priors actually shape agent behavior. Discovery-inception built since is a separate runtime — different shape (multi-agent pipeline), same philosophy (no black-box, full trace).

## Status timeline

For the chronological arc of how the project evolved (v0.5 → v0.8 → patterns library → inception), see [`findings/`](findings/) (8 docs in date order). Each finding is one empirical experiment; the timeline is the project's actual research arc.
