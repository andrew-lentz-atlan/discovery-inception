# discovery-inception

A two-stage agent system for **building other agents**.

**Discovery** turns unstructured customer context — call transcripts, screen recordings, event logs, runbooks, docs, slack threads, optionally a live conversation — into a structured spec. **Inception** turns that spec into a starter agent design: proposed skills, architecture, runtime, memory, scaffolded code, and an eval harness. The goal isn't a 100/100 agent on the first pass; it's to compress the human builder's iteration from weeks to days by handing them a defensible candidate to react to.

It's the top-down complement to bottom-up tools (metadata scans, RAG, descriptions). Bottom-up tools see what's already documented. Discovery-inception extracts the part that lives only in senior practitioners' heads — decision rules, anti-goals, unwritten patterns — and turns it into something an agent can read.

## Pipeline

```
DISCOVERY — gather context from many sources          INCEPTION — spec → starter agent design
──────────────────────────────────────────           ─────────────────────────────────────────
inputs (none authoritative on its own):               reads the spec + the patterns/ knowledge
  transcripts · screen recordings · events ·            base, then makes an explicit, cited call on:
  docs · slack · a live interview                        · workload class  (what kind of agent)
        │                                                · skills          (the cut, w/ provenance)
        ▼                                                · architecture    (ReAct / pipeline / …)
  ingest → facts (each tagged w/ its source)             · runtime         (off-the-shelf framework + model)
  → gap_list.md → chat-fill what you know /              · memory          (kind + store + write/retrieve policy)
    interview what you don't                             · eval seed + judge harness
        │                                                       │
        ▼                                                       ▼
  spec.md + spec.json  ──────────────────────────────────▶  agent_starter/
                                                            ├── orchestrator.py
                                                            ├── design_rationale.md   (every choice, cited)
                                                            ├── skills/<name>/SKILL.md
                                                            └── eval/{questions.json, judge.py}

  patterns/ — the knowledge base feeding inception's decisions:
  architectures · harnesses · anti-patterns · decision-guides · skill-design
```

**Discovery is multi-point on purpose** — no single source gives you the "why." Logs show what a practitioner did; recordings and interviews surface why. The ingest pipeline runs intake + fact extraction in parallel across every artifact you hand it (any modality, via a pluggable extractor seam), tags each fact with the source it came from, and writes a `gap_list.md` of what's covered vs. missing. The FDE chat-fills gaps they know (~5s/fact); the interview-mode agent handles gaps that need a real customer answer (~15s/turn). Hybrid is the common case.

**Inception is a deterministic projection of the spec.** Once the spec is settled, one CLI call (`agent.cli inception --session-id <id>`, ~3–5 min) runs the proposer chain — workload class → skills → architecture → runtime → memory → scaffold — and writes a complete `agent_starter/` with a `design_rationale.md` that cites a `patterns/` entry for every decision. Five sub-agents per discovery turn; six in the inception pipeline; a separate curator agent maintains the knowledge base. Structured Pydantic output at every step; full per-step trace; no black box.

## Repository layout

```
discovery-inception/
├── agent/                       — orchestrator + sub-agents (v0.8 is live)
│   ├── v08/                     the live discovery agent
│   ├── inception/               spec → starter agent design (full pipeline + intra-session feedback)
│   ├── artifacts.py             the modality adapter seam (Artifact + ArtifactExtractor registry)
│   ├── patterns_curator/        knowledge-base maintainer (ingest / promote / audit)
│   ├── mcp_server/              MCP runtime — wired to v0.8
│   ├── baselines/               run_v08_solo + the live mega-agent
│   └── cli.py                   CLI runtime
│
├── intake/                      priors pipeline (artifact → RoleContext)
├── patterns/                    knowledge base (architectures, anti-patterns, skill-design, harnesses, decision-guides)
├── findings/                    empirical research notes (the receipts; cited from patterns/)
├── tests/                       provenance, artifact-seam, and spec-tools regression tests
├── tools/                       compare_inception.py (A/B inception across patterns refs)
├── skill/                       v1.0 packaging design (the portable skill-bundle contract)
├── claude-skill/                installable Claude skill (the curl distribution — how most people run it)
├── archive/research-iterations/ frozen v0.5–v0.7 + their baselines (kept as receipts; not live)
│
├── ROADMAP.md · CHANGELOG.md    what's shipped + what's next
└── README.md                    this file
```

Everything else is gitignored — generated outputs (priors, sessions, `agent_starter/`), customer artifacts, and internal design docs (`docs/internal/`) stay local.

## A note on framework choice

Discovery-inception's own orchestration is hand-rolled (OpenAI SDK, Pydantic, FastAPI, MCP SDK + ~500 lines of plain Python) for one reason: the research phase needed to *ablate* orchestration-layer variables — sub-agent model choice, context budget, synthesizer timing, sharpener rewrite rate — that a stock framework (LangChain / LangGraph / CrewAI / AutoGen) would have confounded. Hand-rolling was required for the experiment, not a stylistic choice. `findings/06–09` are the receipts.

**That is the narrow research exception, and it expires at v1.0.** The architecture is framework-independent by design — the skill bundle (prompts + schemas + orchestration spec) is the contract, re-implementable on any harness. **At the v1.0 release, discovery-inception's own runtime will be formalized onto off-the-shelf libraries** (Claude Agent SDK + LangGraph hybrid is the current plan), because outside research the engineering costs of hand-rolling — maintenance, onboarding load, lost cross-build knowledge transfer, weak operational maturity, slow incident response — compound over a system's lifetime. That's the same standard inception holds its own outputs to: its runtime_proposer recommends a real framework for every agent it scopes. See `patterns/decision-guides/framework-or-hand-roll.md`.

## Try it

Most people run it through the **Claude skill** (one curl, then talk to Claude):

```bash
curl -fsSL https://raw.githubusercontent.com/andrew-lentz-atlan/discovery-inception/main/claude-skill/SKILL.md \
    -o ~/.claude/skills/discovery-inception.md
```

Restart Claude Code / Desktop, then say what you want. The skill has three doors:

> **Build** — *"Use discovery-inception — here's a transcript from yesterday's FinCo scoping call; turn it into a starter agent."*

> **Recommend** — *"Use discovery-inception — I'm building a renewal-risk agent; what's a good approach?"* (a quick consultative read from `patterns/`, no scaffold)

> **Audit** — *"Use discovery-inception — here's a scaffold we built and what it does; is this the right path?"*

Claude clones the repo, installs deps, runs the right door, and (for Build) drives the gap-fill loop to a `spec.md` and on into inception. For ongoing use across sessions, install the MCP server (see [`agent/mcp_server/README.md`](agent/mcp_server/README.md)).

<details>
<summary><b>Terminal, no Claude</b> (the underlying CLI)</summary>

```bash
git clone https://github.com/andrew-lentz-atlan/discovery-inception.git
cd discovery-inception && uv sync && cp .env.example .env  # add LiteLLM creds

# Artifact-first (recommended)
uv run python -m agent.cli ingest \
    --use-case-seed "your use case in one line" \
    --artifact /path/to/call-transcript.txt \
    --artifact /path/to/runbook.md \
    --role-id your-role-slug

# Read gap_list.md, then chat-fill answers you know:
uv run python -m agent.cli submit-turn --no-probe \
    --session-id sess_xxx \
    --message "<your answer phrased as if the customer said it>"

# Finalize → spec.md + spec.json
uv run python -m agent.cli finalize --session-id sess_xxx

# Inception → the full starter agent design (~3-5 min) → agent_starter/<id>/
uv run python -m agent.cli inception --session-id sess_xxx

# Or interview-only mode if you have no artifacts:
uv run python -m agent.cli start-session --use-case-seed "..."
```
</details>

## Where to read deeper

| If you want to... | Read this |
|---|---|
| **What's shipped + what's next** | [`ROADMAP.md`](ROADMAP.md) · [`CHANGELOG.md`](CHANGELOG.md) |
| **The empirical receipts behind every architectural choice** | [`findings/01-architecture-comparison.md`](findings/01-architecture-comparison.md) → the rest of `findings/` is reachable from there |
| **The inception pipeline** | [`agent/inception/README.md`](agent/inception/README.md) |
| **The knowledge base** | [`patterns/README.md`](patterns/README.md) + [`patterns/SKILL.md`](patterns/SKILL.md) |
| **The v1.0 portable-bundle contract** | [`skill/README.md`](skill/README.md) |
