# 01 — Architecture

## The system at a glance

Four sequential stages, each its own specialist agent, plus a starter-kit skill loaded from the customer's own artifacts. The whole thing runs on top of `../harness/` (reusing the agent loop, tool registry, trace log, and config UI we already built).

```
                   ┌────────────────────────────┐
                   │  CaaS INTAKE AGENT         │
   customer  ───►  │  (unstructured → structured│
   artifacts       │   role-context "skill")    │
                   └──────────────┬─────────────┘
                                  │  Role context
                                  │  available as a
                                  │  skill the
                                  ▼  pipeline can call
   ┌──────────────────────────────────────────────────────────────────┐
   │                    DISCOVERY PIPELINE                             │
   │                                                                   │
   │  ┌─────────┐    ┌──────────────┐    ┌──────────┐    ┌─────────┐  │
   │  │ STAGE 1 │ ─► │ STAGE 2       │ ─► │ STAGE 3  │ ─► │ STAGE 4 │  │
   │  │ First   │    │ Gap Iteration │    │ Validator│    │ Build   │  │
   │  │ Princ.  │    │ (loop)        │    │          │    │ Bridge  │  │
   │  └─────────┘    └──────────────┘    └──────────┘    └─────────┘  │
   │                       ▲   │                                       │
   │                       └───┘                                       │
   │                  iterate until validator                          │
   │                  declares "ready for build"                       │
   └────────────────────────────┬──────────────────────────────────────┘
                                ▼
                    ┌────────────────────────┐
                    │  CONTEXT REPO OUTPUT   │
                    │  (specs + skills +     │
                    │   tools + configs)     │
                    └────────────┬───────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │  HARNESS (../harness/)  │
                    │  consumes context repo  │
                    │  runs the agent         │
                    │  produces full traces   │
                    └────────────┬───────────┘
                                 │
                  trace reveals gaps in context
                                 │
                                 ▼
                       feedback to discovery
                       (closed loop)
```

## How it sits on top of `../harness/`

The harness already gives us:

- **Agent loop** (`core/loop.py`) — each stage is an instance of this. Each specialist is a Phase-2-shaped agent with its own system prompt, model params, and tool subset.
- **Tool registry** (`core/tools/registry.py`) — specialists pick from registered tools. Existing: `read_file`, `web_fetch`, `web_search`. New tools the discovery agent might need: `read_artifact` (reads CaaS skill output), `write_spec_section`, `request_user_response`.
- **Trace log** (`core/trace.py`) — already records every request, response, tool call, tool result. We extend this to nest events by stage so traces of multi-stage runs collapse cleanly.
- **Config UI** (`frontend/`) — already supports system prompt swapping. The pipeline definition (which stages, in what order, with what prompts) becomes a new config object on top.
- **HTTP client** (`core/client.py`) — already speaks OpenAI wire format. No changes needed.

What the harness does **not** have today:

1. **Multi-stage pipeline runner.** A wrapper that runs `stage_1 → stage_2 → stage_3 → stage_4`, passes structured state between them, and lets each stage call `run_loop` as a sub-agent. This is the main new code in this project.
2. **Stage-level state contracts.** Each stage produces a Pydantic object that's the input to the next. The contracts make state passing explicit and validated.
3. **Sub-agent spawning.** Some stages (especially Gap Iteration) need to spawn multiple sub-agents in a loop. This is a structured pattern on top of `run_loop`, not a new mechanism.
4. **Nested trace view.** UI tweak so the existing Trace tab can collapse/expand events grouped by stage.

## Pipeline state contract (sketch)

The flow of data from stage to stage:

```python
# After Stage 1 — First Principles
class FirstPrinciplesOutput(BaseModel):
    why_now: str
    desired_outcome: str            # measurable
    anti_goal: str                  # explicit non-goal
    success_metric: str
    current_pain_named: str         # who feels the pain, what does it look like
    confidence: dict[str, float]    # per-field confidence score from validator

# Stage 2 — Gap Iteration produces a richer version of the same shape
# plus persona, decision tree, tool inventory, escalation rules
class DiscoverySpec(BaseModel):
    first_principles: FirstPrinciplesOutput
    persona: PersonaSpec
    decision_journey: list[DecisionPoint]
    tool_inventory: list[ToolSpec]
    escalation_rules: list[EscalationRule]
    risks: list[Risk]
    uncertainty_markers: list[UncertaintyMarker]
    bedrock_log: list[WhyChain]     # so reviewers can see how deep we probed each topic

# Stage 3 — Validator returns either
class ValidationResult(BaseModel):
    ready: bool
    confidence: float
    remaining_gaps: list[Gap]       # non-empty if not ready

# Stage 4 — Build Bridge translates DiscoverySpec to deployable artifacts
class ContextRepo(BaseModel):
    spec_md: str                    # the full markdown brief
    mva_scope: MVADefinition        # the slice the first agent uses
    proposed_skills: list[Skill]    # role context skills, retrieval sketches
    proposed_tools: list[ToolSketch]
    config_yaml: str                # ready to drop into harness config/
```

These types aren't final, but the principle is: **typed state passing between stages.** Each stage's output is a structured object with explicit fields, validated by Pydantic, with confidence/uncertainty marked at the field level.

## The closed loop

The architectural unlock that makes this project different from any "AI for discovery" tool out there:

```
1. Discovery system produces context repo
        │
        ▼
2. Harness consumes context repo and runs the agent
        │
        ▼
3. Harness produces full traces of every step the agent took
        │
        ▼
4. Trace analyzer (future, not in v0) identifies which steps had bad
   context, contradictory tools, missing data, etc.
        │
        ▼
5. Feedback patches the discovery output. New gap, new probe, new spec section.
        │
        └─── back to step 1
```

Most agentic platforms cannot close this loop because they don't own the harness layer. We do, because we built one.

For v0, we don't have to automate step 4. A human can read the trace and decide what to patch in discovery. The point is the loop *exists* and is closeable, even if not fully automated yet.

## Key dependencies between this project and `../harness/`

| Discovery feature | Harness piece it depends on |
|---|---|
| Each stage as a specialist agent | `core/loop.py` (existing) |
| State passing between stages | New: pipeline runner module |
| User-facing chat for in-convo probing | `api/chat.py` (existing, may need streaming-during-stage-transition tweaks) |
| Trace per stage | `core/trace.py` (existing, needs nesting) |
| Per-stage system prompts | `config/presets/` (existing pattern) |
| CaaS skills | New: skill loading mechanism + storage path |
| Output as context repo | New: artifact bundler |

The implementation strategy: extend the existing harness in place, *not* fork. We add the pipeline runner and state contracts on top of the existing primitives. This keeps Phase 1+2 valuable as the foundation rather than competing with this project.

## What we're NOT building in v0

- **Router / planner agent** that picks pipelines dynamically. Linear pipeline only.
- **Automated trace-to-gap analyzer** (step 4 in the closed loop). Human-in-the-loop for now.
- **Multi-customer / multi-tenant config.** One discovery session at a time.
- **Production-grade auth, persistence, scale.** This is a research artifact.
- **Generic agent-building DSL.** Tune prompts hard for one artifact type first.
