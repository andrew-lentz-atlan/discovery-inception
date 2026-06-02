# discovery-inception

A two-stage agent system for **building other agents**.

**Discovery** turns unstructured customer context — call transcripts, runbooks, docs, slack threads, optionally a live conversation — into a structured spec. **Inception** turns that spec into a starter agent design — proposed skills, architecture, runtime, scaffolded code. The goal isn't to ship a 100/100 agent on the first pass; it's to compress the human builder's iteration time from weeks to days by giving them a defensible candidate to react to.

The project is the top-down complement to bottom-up tools (metadata scans, RAG, descriptions). Bottom-up tools see what's already documented. Discovery-inception extracts the part that lives only in senior practitioners' heads — decision rules, anti-goals, unwritten patterns — and turns it into something an agent can read.

## How most people use it

```
artifacts → ingest → gap_list.md → chat-fill known gaps → (optional) interview for unknown gaps → spec.md → inception → agent_starter/
```

Most flows start with *something*: a Granola call summary, a runbook excerpt, an internal scoping doc. The artifact-first ingest pipeline runs intake + fact extraction in parallel across all artifacts you hand it, produces a populated session, and writes a `gap_list.md` showing exactly what's covered and what's still missing. The FDE chat-fills gaps they know the answer to (~5s/fact); the interview-mode discovery agent handles the gaps that need a real customer answer (~15s/turn). Hybrid flows are the common case.

Once the spec is settled, **inception** turns it into a complete starter agent design — proposed skills, selected architecture (single-agent ReAct vs chained pipeline vs adversarial decomposition), runtime + model picks, scaffolded orchestrator code, eval seed, judge harness. Six sub-agents run end-to-end; ~3–5 min. The handoff is one CLI invocation: `agent.cli inception --session-id <id>`.

## Try it (one curl)

```bash
curl -fsSL https://raw.githubusercontent.com/andrew-lentz-atlan/discovery-inception/main/claude-skill/SKILL.md \
    -o ~/.claude/skills/discovery-inception.md
```

Restart Claude Code / Desktop. Then either:

> *"Use the discovery-inception skill — I've got a transcript from yesterday's scoping call with FinCo about a renewal-risk agent. Want to turn it into a spec."*

> *"Use the discovery-inception skill — I want to do a fresh interview for a SoCo agent at TechCo. No artifacts, just the use case."*

Claude clones the repo, installs deps, ingests the artifacts (or starts a fresh interview), drives the gap-fill loop, exports `spec.md`.

## Try it (terminal, no Claude)

```bash
git clone https://github.com/andrew-lentz-atlan/discovery-inception.git
cd discovery-inception && uv sync && cp .env.example .env  # add LiteLLM creds

# Artifact-first (recommended)
uv run python -m agent.cli ingest \
    --use-case-seed "your use case in one line" \
    --artifact /path/to/call-transcript.txt \
    --artifact /path/to/runbook.md \
    --role-id your-role-slug

# Then read gap_list.md, chat-fill answers you know:
uv run python -m agent.cli submit-turn --no-probe \
    --session-id sess_xxx \
    --message "<your answer phrased as if the customer said it>"

# Finalize → produces spec.md + spec.json
uv run python -m agent.cli finalize --session-id sess_xxx

# Inception → turns the spec into a complete starter agent design
# (proposed skills, selected architecture + runtime + model, scaffolded
# orchestrator code, eval seed, judge harness). ~3-5 minutes.
uv run python -m agent.cli inception --session-id sess_xxx
# Output: agent_starter/<role_id_or_session_id>/

# Or interview-only mode if you have no artifacts:
uv run python -m agent.cli start-session --use-case-seed "..."
```

For ongoing use across many sessions: install the MCP server (see [`agent/mcp_server/README.md`](agent/mcp_server/README.md)).
For what's shipped in the current version + where to start: see [`CHANGELOG.md`](CHANGELOG.md).

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

Five sub-agents per discovery turn; six sub-agents in the inception pipeline; a separate patterns curator agent maintains the knowledge base. The orchestrator is ~500 lines of plain Python with structured Pydantic outputs at every step; full per-step trace; no black box. The orchestration layer is hand-rolled because **discovery-inception is itself an ablation experiment** — findings/06-09 measured orchestration-layer variables (sub-agent model choice, context budget, synthesizer timing, sharpener rewrite rate) that stock frameworks would have confounded. The inception output it produces, however, recommends real frameworks for downstream builds — see `patterns/decision-guides/framework-or-hand-roll.md`.

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

## A note on framework choice (our infra vs. our recommendations)

Discovery-inception's own orchestration layer is hand-rolled (OpenAI SDK, Pydantic, FastAPI, MCP SDK + ~500 lines of plain Python). That's because the research phase needed to ablate orchestration-layer variables — sub-agent model choice, context budget, synthesizer timing, sharpener rewrite rate — that stock frameworks (LangChain / LangGraph / CrewAI / AutoGen) would have confounded. Hand-rolling was *required for the experiment*, not a stylistic choice.

That research case is the **narrow exception**, not the rule. Inception's runtime_proposer recommends a real framework for every downstream build it scopes, because the engineering costs of hand-rolling (maintenance burden, cognitive onboarding cost, lost knowledge transfer across builds, weak operational maturity, slow incident response, reviewer illegibility) compound over a system's lifetime — see `patterns/decision-guides/framework-or-hand-roll.md` for the full reasoning.

The architectural findings are framework-independent — the skill bundle (prompts + schemas + orchestration spec) is the contract. Anyone can re-implement on LangGraph or Claude Agent SDK, and discovery-inception's own infrastructure will migrate to a real framework once the research-stage justification expires. The v0.10 backlog includes a discovery-layer migration to Claude Agent SDK + LangGraph hybrid.

## Where to read deeper

| If you want to... | Read this |
|---|---|
| **See what's shipped + what's coming next** | [`ROADMAP.md`](ROADMAP.md) |
| **See empirical receipts behind every architectural choice** | [`findings/01-architecture-comparison.md`](findings/01-architecture-comparison.md) → [`findings/05-v08-probe-sharpener-and-tensions.md`](findings/05-v08-probe-sharpener-and-tensions.md). The rest of `findings/` is reachable from there. |
| **Understand the inception pipeline** | [`agent/inception/README.md`](agent/inception/README.md) |
| **Understand the knowledge wiki** | [`patterns/README.md`](patterns/README.md) + [`patterns/SKILL.md`](patterns/SKILL.md) |
| **Understand the v1.0 portable-bundle contract** | [`skill/README.md`](skill/README.md) |
