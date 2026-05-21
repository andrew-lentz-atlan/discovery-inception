# discovery-inception

A two-stage agent system for **building other agents**.

**Discovery** extracts tacit context from a customer (or an artifact, or a transcript) into a structured spec. **Inception** turns that spec into a starter agent design — proposed skills, architecture, runtime, scaffolded code. The goal isn't to ship a 100/100 agent on the first pass; it's to compress the human builder's iteration time from weeks to days by giving them a defensible candidate to react to.

The project is the top-down complement to bottom-up tools (metadata scans, RAG, descriptions). Bottom-up tools see what's already documented. Discovery-inception extracts the part that lives only in senior practitioners' heads — decision rules, anti-goals, unwritten patterns — and turns it into something an agent can read.

## Try it (one curl)

```bash
curl -fsSL https://raw.githubusercontent.com/andrew-lentz-atlan/discovery-inception/main/claude-skill/SKILL.md \
    -o ~/.claude/skills/discovery-inception.md
```

Restart Claude Code / Desktop, then: *"Use the discovery-inception skill — I want to test it for a renewal-risk agent for our CSM team at FinCo."* Claude clones the repo, sets up dependencies, drives the discovery interview turn-by-turn, exports `spec.md`.

For ongoing use across many sessions: install the MCP server (see [`agent/mcp_server/README.md`](agent/mcp_server/README.md)).
For terminal / scripting: CLI via `agent/cli.py`.

## Pipeline

```
DISCOVERY                                              INCEPTION
intake → discovery → spec + RoleContext               inception ← prior_feedback (optional)
                            │                              │
                            ▼                              ▼
                   spec.md + spec.json              agent_starter/
                                                    ├── orchestrator.py
                                                    ├── design_rationale.md
                                                    ├── skills/<name>/SKILL.md
                                                    ├── eval/questions.json
                                                    └── eval/judge.py

                                  ▲                        ▲
                                  └────── patterns/ ───────┘
                                       (knowledge wiki:
                                        architectures,
                                        anti-patterns,
                                        skill-design patterns,
                                        harness landscape,
                                        decision guides)
```

Five sub-agents per discovery turn; six sub-agents in the inception pipeline; a separate patterns curator agent maintains the knowledge base. The orchestrator is ~500 lines of plain Python with structured Pydantic outputs at every step. No framework opinions; full per-step trace; no black box.

See [`ROADMAP.md`](ROADMAP.md) for what's shipped and what's coming next.

## Repository layout

```
discovery-inception/
├── agent/                       — orchestrator + sub-agents
│   ├── v05/ v06/ v07/ v08/      research iterations (v0.8 is the live one)
│   ├── inception/               the inception agent (full pipeline + intra-session feedback)
│   ├── patterns_curator/        knowledge-base maintainer (skeleton + classify-source)
│   ├── mcp_server/              MCP runtime — wired to v0.8
│   └── cli.py                   CLI runtime
│
├── intake/                      priors pipeline (artifact → RoleContext)
├── patterns/                    knowledge wiki (architectures, anti-patterns, skill-design, harnesses, decision-guides)
├── skill/                       v1.0 packaging design (skill bundle contract)
├── claude-skill/                installable Claude skill (the curl distribution)
│
├── findings/                    empirical research notes (the architectural receipts; cited from patterns/)
│
├── ROADMAP.md                   what's shipped + what's coming next
└── README.md                    this file
```

Everything else is gitignored — generated outputs (intake's priors, discovery's sessions, inception's `agent_starter/`), customer-specific artifacts (transcripts, scoping calls), and our internal design docs (`docs/internal/`) live locally only.

## A note on framework choice

We didn't use LangChain / LangGraph / CrewAI / AutoGen. At research stage, framework opinions about orchestration would have entangled with the architectural variables we were measuring. We use boring libraries (OpenAI SDK, Pydantic, FastAPI, MCP SDK) and a hand-rolled orchestrator. The architectural findings are framework-independent — anyone can re-implement on LangGraph with the skill bundle (prompts + schemas + orchestration spec) as the contract.

## Where to read deeper

| If you want to... | Read this |
|---|---|
| **See what's shipped + what's coming next** | [`ROADMAP.md`](ROADMAP.md) |
| **See empirical receipts behind every architectural choice** | [`findings/01-architecture-comparison.md`](findings/01-architecture-comparison.md) → [`findings/05-v08-probe-sharpener-and-tensions.md`](findings/05-v08-probe-sharpener-and-tensions.md). The rest of `findings/` is reachable from there. |
| **Understand the inception pipeline** | [`agent/inception/README.md`](agent/inception/README.md) |
| **Understand the knowledge wiki** | [`patterns/README.md`](patterns/README.md) + [`patterns/SKILL.md`](patterns/SKILL.md) |
| **Understand the v1.0 portable-bundle contract** | [`skill/README.md`](skill/README.md) |
