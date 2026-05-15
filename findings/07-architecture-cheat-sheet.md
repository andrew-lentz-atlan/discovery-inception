# Architecture cheat sheet

**Purpose:** back-pocket reference. SparkNotes version of the architecture conversation across the v0.5 → v0.8 research arc + the v1.0 packaging plan. Read in 5 minutes; defend in any meeting.

---

## TL;DR

A **top-down discovery agent** that interviews a customer to produce a structured spec for a new AI agent build. Complements bottom-up metadata scans by capturing tacit knowledge (decision rules, anti-goals, unwritten patterns) that doesn't live in any document. Output is a `spec.json` + `spec.md` that downstream consumers (Atlan's CES, FDEs, builders) read.

Five sub-agents per turn. Multi-agent system, not a single LLM call. Has its own runtime (~500 lines of Python). Outputs portable artifacts that any compliant runtime can produce.

---

## Architecture in 30 seconds

```
customer message
        │
        ▼
  triage → distill (if concrete) → mega-agent (with 4 tools) → sharpener (post-process)
              │                          │                              │
         fact recorded         conversation + tool calls       weak probe rewritten
                                          │
                              can invoke: get_current_spec_state,
                                          get_checklist_progress,
                                          synthesize_my_thinking,
                                          find_tensions

  ─── at session close ───
  deterministic synthesizer runs once over the full conversation → final theory
  export spec.md + spec.json
```

---

## The five research iterations (what each killed)

| Version | What it added | The failure mode it killed |
|---|---|---|
| **v0.5** | Chained sub-agents per turn (triage → distill → synth → why-prober → probe-gen) | Baseline — single mega-agent failed to maintain structured state |
| **v0.6** | Hybrid: extractors preprocess + mega-agent runs conversation with tools | Pure chain orchestration was rigid and conversationally weak |
| **v0.7** | Lazy synth (mega-agent decides when) + free-form output | Eager synth wasted compute; format constraints suppressed conversational moves |
| **v0.7 + close-out** | Deterministic synthesizer at session end | Recency bias — eager synth made final theory drift to latest topic |
| **v0.8** | Probe-sharpener post-processor + internal tensions detection | Mega-agent's probes were weak 55% of the time (no adversarial review) |

**Direction of travel:** each iteration killed a specific failure mode rather than making a "globally smarter" agent. That's how systems get sharper.

---

## The five architectural patterns to name

These are the durable IP. Quote any of them when defending the architecture.

1. **Skill as a tool, not as orchestrator.** The mega-agent is in charge of conversation; decomposed sub-agents are skills it leans on. Inverts the chained pattern.

2. **Adversarial decomposition.** A second sub-agent whose job is to be skeptical of the first one's output. Different from "split a task across sub-agents." (Probe-sharpener reviews mega-agent's output.)

3. **Lazy + deterministic synthesis.** Lazy synthesis (model-judged) for in-conversation reflection. Deterministic close-out for the final spec. Gets quality AND reliability.

4. **Free-form mega-agent, structured extractors.** Don't bleed format requirements into the conversational agent. The mega-agent emits prose; structure happens in extractors.

5. **Skill bundle separable from runtime.** Prompts + schemas + orchestration spec are portable IP. The runtime that executes them is commodity. Multiple runtimes (MCP, CLI, FastAPI, eventually CES-internal) can consume one bundle.

---

## Common questions, crisp answers

**Q: Why not LangChain / LangGraph / CrewAI / AutoGen?**
> Frameworks impose orchestration opinions. At research stage we needed to test which orchestration opinions are right — adopting any framework would have entangled our findings with that framework's defaults. Our orchestrator is ~500 lines; iteration speed across 5 versions mattered. Findings are framework-independent; at v1.0 the skill bundle is portable to any runtime including framework-backed ones if someone wants to write one.

**Q: Why are there two harnesses?**
> The standalone `/harness/` repo was the substrate for the May 4 closed-loop demo proving priors shape agent behavior. The discovery agent built since is its own runtime — multi-agent pipeline shape vs the harness's single-agent ReAct shape. They share a philosophy (no black box, full trace), not a codebase. v1.0 reorg either merges or formally separates them.

**Q: How does this integrate with CES?**
> Discovery runs separately, produces a `spec.json`, hands it to CES's `synthesis_agent` as an additional input alongside their existing cold-start metadata snapshot. Two systems, clean handoff via the spec.json contract. We don't run inside CES; we feed it. They keep ownership of their context-repo generation; we contribute the top-down lens.

**Q: Why didn't you just package it as a Claude skill?**
> A Claude skill is instructions an agent follows in a single conversation. Discovery is a multi-agent system — 5 sub-agents per turn, structured state across many turns. A single Claude conversation can't reliably do all of that. Skills work for "tell Claude how to do X in one conversation." Agent systems need a runtime.

**Q: Is this scalable / production-ready?**
> Patterns are scalable. Current code is research-grade. At v1.0 the skill bundle (prompts + schemas + orchestration spec) becomes a portable artifact; the runtime is commodity. The architectural findings (lazy synth, adversarial decomposition, deterministic close-out, free-form mega-agent) survive any runtime implementation.

**Q: Why custom-built instead of using off-the-shelf?**
> No off-the-shelf agent system gives full per-step trace AND supports the multi-agent pipeline shape we needed. Generic harnesses (Claude Code, Cursor) are opaque about reasoning steps; agent frameworks (LangChain, etc.) impose orchestration patterns. We needed to test architectural variables independently of either. ~500 lines of focused code was the right tool for that.

**Q: Is this slop?**
> No — it's the natural artifact of research that pivoted. Every architectural choice has an empirical receipt in `findings/`. The known technical debt (two harnesses, research-version directories, prompts/schemas not yet in `skill/`) is documented and resolvable at v1.0 packaging. Slop would be making choices without evidence; we have evidence.

---

## Three deployment modes (one packaging)

All three share the same skill bundle + runtime core. They differ only in the **I/O adapter** — what feeds the pipeline, what consumes its output.

| Mode | What | Feasibility | Use case |
|---|---|---|---|
| **1 — Post-mortem** | Recorded call transcript → pipeline → spec | ✅ feasible now (~half-day to build) | Process historical Atlan calls; batch over backlog |
| **2a — Co-pilot sidebar** | Live STT → pipeline → sidebar UI; agent never speaks | ⚠️ feasible with latency optimizations + STT + UI | FDE augmentation during a real call |
| **2b — Text-based autonomous interviewer** | Chat in → pipeline → chat out | ✅ shipped (MCP + CLI + skill) | Direct testing, evaluation, demo |

**Mode 2a's reframe (load-bearing):** the agent never generates "the next question on time." It maintains a sidebar of state — working theory, gaps, tensions, suggested questions — the FDE glances at between their own questions. The FDE provides conversational cadence, so 5–10s of state-update latency is tolerable.

**Mode 3 (agent speaks autonomously on call cadence):** probably the wrong target with this architecture. Mode 2a is more valuable AND more achievable.

---

## Cost + latency reality

- **Per-session cost:** ~$0.50 (Haiku throughout) — not the constraint.
- **Per-turn latency:** 13–17s — the constraint.
- **Realistic optimization target:** 5–8s/turn (2-3x speedup) via cheap-cascade extractors, Anthropic prompt caching, skip-sharpener-when-unlikely-to-help, streaming completions, speculative parallelism, history compaction. **None require architectural change** — just plumbing.

---

## What's debt vs what's defensible

**Defensible (don't apologize for):**
- Architectural choices: empirical receipts in `findings/01–06`
- Custom runtime: justified by research-stage framework independence
- Output contract (`spec.json`): portable, downstream-friendly
- Multi-agent decomposition: validated as load-bearing for structured output

**Real debt (acknowledge openly):**
- Two parallel runtimes (the standalone `/harness/` + the discovery agent's own runtime)
- `v06/`, `v07/`, `v08/` directories will confuse anyone new; v1.0 reorg archives them
- Prompts/schemas/tools currently live under `agent/` not `skill/`; v1.0 moves them
- No optimizations yet (cheap-cascade, prompt caching) — research code prioritized iteration speed

Acknowledging debt openly = credibility. Hiding it = slop.

---

## What v1.0 looks like

```
discovery-inception/
├── skill/                    ← portable IP (designed; not yet executed)
│   ├── manifest.yaml         ← runtime contract
│   ├── orchestration.yaml    ← declarative pipeline
│   ├── prompts/              ← migrated from agent/prompts/
│   ├── schemas/              ← JSON Schema (from Pydantic)
│   └── tools/                ← migrated from agent/v08/spec_tools.py
│
├── runtimes/                 ← multiple implementations of the contract
│   ├── core/                 ← shared library (interprets orchestration.yaml)
│   ├── cli/, mcp/, api/      ← thin entry points wrapping core/
│
├── intake/                   ← separate priors-generation pipeline (unchanged)
├── findings/                 ← research notes (the empirical case)
├── demos/                    ← reference outputs
└── archive/research-iterations/  ← v0.5–v0.8 archived with brief READMEs
```

Plus: cheap-cascade + prompt caching + skip-sharpener optimizations land. CES integration ships (discovery output → CES synthesis_agent).

---

## One-liner for any meeting

> *"Discovery-inception is the top-down complement to bottom-up metadata-driven discovery. A multi-agent system that interviews humans to extract tacit knowledge metadata can't see, validated through 5 research iterations on synthetic data, packaged for portability so any compliant runtime can execute it. Our output is a structured spec that downstream pipelines like CES read as an additional input. The empirical case is in `findings/`; the v1.0 packaging plan is in `skill/`."*

That covers what it is, how it was validated, what's portable, what's still ahead. Use directly when introducing the project; adapt when answering specific questions.

---

## Where to read deeper (if pushed)

| Topic | Source |
|---|---|
| Three architectures compared (mega vs chained vs hybrid) | `findings/01-architecture-comparison.md` |
| Lazy synth + free-form mega-agent | `findings/02-v07-lazy-synthesis-and-free-form-output.md` |
| Long-conversation validation | `findings/03-v07-25-turn-validation.md` |
| Deterministic close-out | `findings/04-v07-deterministic-closeout.md` |
| Adversarial probe-sharpener + tensions | `findings/05-v08-probe-sharpener-and-tensions.md` |
| Cost, latency, deployment modes | `findings/06-cost-latency-and-deployment-modes.md` |
| Runtime contract for v1.0 | `skill/manifest.yaml` + `skill/orchestration.yaml` |
| 50-turn demo (real output) | `demos/finco_sales_analyst/02_spec_v08.md` |
| CES integration framing | `demos/finco_sales_analyst/03_ces_meeting_handout.md` |
