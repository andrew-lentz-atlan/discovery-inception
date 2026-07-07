# agent/inception — the inception agent

Closes the loop on the project's name: discovery extracts tacit context into a spec; **inception** turns that spec into a concrete starter agent design — proposed skills, architecture, runtime, plus a scaffolded `agent_starter/` directory the human builder can iterate on.

The inception agent is the second half of the project's name (`discovery-inception`): discovery produces a structured spec; inception turns that spec into an actionable starter design.

## Status

Pipeline is **feature-complete** for starter generation as of the current commit.

| Step | Sub-agent | State |
|---|---|---|
| 1 | `workload_classifier` | shipped |
| 2 | `skill_proposer` | shipped |
| 3 | `architecture_proposer` | shipped |
| 4 | `runtime_proposer` | shipped |
| 5 | `scaffold_writer` (6 sub-steps: SKILL.md per skill / orchestrator.py / design_rationale.md / eval/questions.json / eval/judge.py / architecture.md) | shipped |
| 6 | critics for steps 2 + 3 | deferred (advisory; lower priority) |

Plus **intra-session feedback**: the pipeline accepts a `--prior-feedback <path>` argument; each sub-agent's prompt gains a "Prior iteration feedback" section that the model treats as constraints. Used to iterate a starter design within a session based on builder feedback on the previous output.

## Pipeline

```
DiscoverySpec (spec.md + RoleContext) (+ optional BoundedContext for Atlan catalog priming)
                              │
       optional: prior_feedback for re-runs (Loop 2)
                              ▼
              workload_classifier
                              │
                              ▼
              skill_proposer  ──→  orchestrator_level_concerns
                                   + atlan_context_layer  (always produced)
                              │
                              ▼
              architecture_proposer  ──→  selected pattern + add-ons
                                                (consults patterns/architectures/)
                              │
                              ▼
              runtime_proposer  ──→  selected harness + model
                                          (consults patterns/harnesses/)
                              │
                              ▼
              scaffold_writer (6 parallel/sequential sub-steps)
                              │
                              ▼
              agent_starter/   ← portable artifact for the builder
                ├── README.md
                ├── architecture.md          (2 Mermaid diagrams + summary)
                ├── design_rationale.md      (audit trail with citations)
                ├── orchestrator.py          (ReAct loop + tool stubs + TODOs)
                ├── skills/<name>/SKILL.md   (per skill, Anthropic skill format)
                ├── eval/questions.json      (10-15 seed questions)
                ├── eval/judge.py            (LLM-as-judge harness scaffold)
                └── meta/                    (upstream pydantic outputs)
```

Each sub-agent is a single prompt + single Pydantic output, modeled on `intake/` and `agent/patterns_curator/`. `scaffold_writer` runs its 6 sub-steps mostly in parallel; `step 5e` depends on `step 5d` so it's sequential after the gather.

Note the BoundedContext **input** is optional, but the pipeline's Atlan **output** is not: step 2's result always includes the `atlan_context_layer` recommendation (a required schema field) — an Atlan context repo as the portable home for the agent's static scaffold (thin tenant → seed it), plus the live-access surface(s) (MCP / MDLH / SDK) routed by the Atlan posture facts captured in discovery (`atlan_integration_posture`). Steps 3/4/5c don't receive the raw spec prose, so this typed field is how the Atlan decision travels downstream.

## Workload axes (step 1's classification)

The workload classifier emits six structured axes. These are the filters the downstream proposers use against `patterns/`.

| Axis | Values | Why it matters |
|---|---|---|
| `interaction_shape` | conversational, query-response, batch, streaming | Determines which architectures are candidates |
| `latency_sensitivity` | real-time, near-real-time, tolerant | Rules out adversarial-decomposition for sub-second targets |
| `decision_complexity` | deterministic, rule-based, judgment-heavy | Drives skill granularity; judgment-heavy → inner-pipeline skills |
| `data_intensity` | light, moderate, heavy | Pushes toward data-shaping patterns (`patterns/anti-patterns/truncated-data-summary`) |
| `multi_step_or_single_step` | single, multi | Single-step → one tool call; multi → loop or chain |
| `state_shape` | stateless, session-scoped, long-horizon | Long-horizon → durable execution (LangGraph); stateless → simpler harnesses |

## CLI

```bash
# Run the full pipeline + materialize agent_starter/
uv run python -m agent.inception.run \
    --spec-md path/to/spec.md \
    --role-context path/to/role_context.json \
    --output-dir path/to/agent_starter/

# Run steps 1-4 only (no scaffold materialization)
uv run python -m agent.inception.run \
    --spec-md path/to/spec.md \
    --role-context path/to/role_context.json

# Re-run with prior iteration feedback (Loop 2)
uv run python -m agent.inception.run \
    --spec-md path/to/spec.md \
    --role-context path/to/role_context.json \
    --output-dir path/to/agent_starter/ \
    --prior-feedback path/to/feedback.json
```

The `--spec-md` should point at a discovery agent's spec output (typically `sessions/<session_id>/spec.md`). The `--role-context` should point at an intake pipeline's RoleContext output (typically `skills/<role-id>/context.json` — gitignored).

`--runtime {python,langgraph}` selects the orchestration substrate: `python` (default) is the hand-rolled reference engine with `meta/` resume; `langgraph` runs the same `step_*` contract on the `StateGraph` adapter in `graph.py` (always a fresh run) and produces the same outputs — validated A/B, `findings/10`. The default is overridable via the `INCEPTION_RUNTIME` env var.

## Validation

The pipeline has been validated on a real customer use case (a CPG brand-analytics agent). Held against an independent reference implementation by a builder who shipped a similar agent and scored 97/100 on LLM-as-judge eval, our inception output independently:

- Classified the workload identically across all six axes
- Proposed a matching skill decomposition (4 skills, one finer than the reference)
- Selected the same architecture (single-agent ReAct with tools)
- Selected the same runtime + model (Claude Agent SDK + claude-opus-4-7)
- Additionally surfaced a recommended add-on (adversarial-decomposition for quality gating) that the reference implementation didn't have but the spec's orchestrator-level concerns explicitly called for

The empirical reference is at https://github.com/bladata1990/pg-brand-analyst-agent (public). The customer-specific validation artifacts (spec, RoleContext, manual skill design comparison) live locally, not in this repo.

## Files

- `__init__.py`
- `README.md` — this file
- `schemas.py` — Pydantic models for every sub-agent's output
- `prompts/` — one prompt per sub-agent, plus 5 for scaffold_writer's sub-steps
- `run.py` — CLI entry point + the reference (`python`) pipeline orchestration
- `graph.py` — LangGraph `StateGraph` orchestration adapter (same `step_*` contract; selected via `--runtime langgraph`)
- `sample_feedback/` — example feedback files for Loop 2 testing (gitignored; local-only)
