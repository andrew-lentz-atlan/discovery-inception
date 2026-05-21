# agent/inception — the inception agent

Closes the loop on the project's name: discovery extracts tacit context into a spec; **inception** turns that spec into a concrete starter agent design — proposed skills, architecture, runtime, plus a scaffolded `agent_starter/` directory the builder can iterate on.

Design: `plans/08-inception-agent.md`.

## Status

**Skeleton + workload_classifier (step 1) shipping.** Six sub-agents are planned per the design doc; only the first is implemented. The others are stubs.

The validation case is the P&G F&HC Brand Analyst exercise. Feed inception the oriented RoleContext at `skills/p-and-g-fhc-analyst-oriented/context.json` + the use_case_seed; compare the produced `agent_starter/` design to (a) my manual v2 cut in `skills/p-and-g-fhc-analyst-oriented/agent_skills_v2.md` and (b) Bala's actual implementation at https://github.com/bladata1990/pg-brand-analyst-agent.

## Pipeline (planned)

```
DiscoverySpec (spec.md + RoleContext) + BoundedContext (Atlan, when available)
                              │
                              ▼
              workload_classifier   ← SHIPPING IN THIS COMMIT
                              │
                              ▼
       skill_proposer ── skill_critic       (adversarial pair)   stub
                              │
                              ▼
   architecture_proposer ── arch_critic     (adversarial pair)   stub
                              │
                              ▼
              runtime_proposer                                    stub
                              │
                              ▼
              scaffold_writer                                     stub
                              │
                              ▼
              agent_starter/   ← portable artifact for the builder
```

Each sub-agent is a single prompt + single Pydantic output, modeled on `intake/` and `agent/patterns_curator/`.

## Step 1 — workload_classifier (shipping)

Reads a DiscoverySpec and emits a structured classification of the workload along six axes:

| Axis | Values | Why it matters |
|---|---|---|
| `interaction_shape` | conversational, query-response, batch, streaming | Determines which architectures are even candidates |
| `latency_sensitivity` | real-time, near-real-time, tolerant | Rules out adversarial-decomposition for sub-second targets, etc. |
| `decision_complexity` | deterministic, rule-based, judgment-heavy | Drives skill granularity; judgment-heavy → inner-pipeline skills |
| `data_intensity` | light, moderate, heavy | Pushes toward data-shaping patterns (`anti-patterns/truncated-data-summary`) |
| `multi_step_or_single_step` | single, multi | Single-step → one tool call; multi → loop or chain |
| `state_shape` | stateless, session-scoped, long-horizon | Long-horizon → durable execution (LangGraph); stateless → simpler harnesses |

The classification is the input to the downstream proposer sub-agents. `architecture_proposer` filters `patterns/architectures/` by `applies_when.workloads` matching these axes. Same for `runtime_proposer` against `patterns/harnesses/`.

## CLI

```bash
uv run python -m agent.inception.run \
    --spec-md path/to/spec.md \
    --role-context skills/<role-id>/context.json
```

Currently runs step 1 only. Future iterations add the rest of the pipeline and produce `agent_starter/` output.

## Files

- `__init__.py`
- `README.md` — this file
- `schemas.py` — Pydantic models
- `prompts/` — one per sub-agent
- `run.py` — CLI entry point
