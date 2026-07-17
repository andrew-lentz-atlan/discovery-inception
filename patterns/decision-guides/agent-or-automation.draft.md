---
title: Agent or automation? The gate before the taxonomy
category: decision-guides
status: draft
last_updated: 2026-07-16
source_findings: []
source_external:
  - "Anthropic — Building Effective Agents (the workflows-vs-agents distinction: workflows orchestrate LLMs through predefined code paths; agents direct their own processes and tool usage)"
applies_when:
  workloads: [any]
  constraints: [pre-classification, use-case-intake]
contradicts: []
related:
  - decision-guides/what-kind-of-agent-are-you-building
  - decision-guides/framework-or-hand-roll
  - anti-patterns/wrong-class-architecture
snapshot_date: 2026-07-16
---

# Agent or automation? The gate before the taxonomy

A large fraction of "build me an agent" requests describe an **automation with
an AI step**: a deterministic trigger → transform → action flow in which one
step benefits from a model call (classify, extract, draft, summarize). No
loop, no runtime tool choice, no judgment-dependent stop condition. Building
an agent for that workload buys nondeterminism, an eval burden, higher
latency, and a harder debugging story — to do a job a workflow engine does
reliably for a fraction of the cost. The inverse error is quieter but
compounding: forcing genuinely open-ended work into a workflow produces an
ever-growing thicket of conditional branches that approximate judgment badly.

This is the gate question asked **before** the five-class taxonomy
(`what-kind-of-agent-are-you-building.md`): the taxonomy classifies agents;
this entry decides whether the workload is an agent at all. The distinction
follows the now-standard framing: a **workflow/automation** orchestrates model
calls through *predefined code paths*; an **agent** *directs its own process*
— it decides at runtime which action to take next based on intermediate
results. LLM-as-step versus LLM-as-controller.

## The decision procedure

Run in order; the first decisive answer routes.

1. **Can the full flow be drawn as a flowchart at design time?** Every
   branch enumerable, every step's inputs known before running. → **Automation.**
   An LLM call inside a box ("classify the ticket," "draft the reply") does
   not make the flowchart an agent — the *path* is still fixed.
2. **Is the trigger an event or schedule rather than a conversation?**
   Record created, file landed, Monday 9am. → Lean automation. Conversational
   triggers lean agent (turn-taking implies runtime adaptation), but a
   chat-initiated fixed pipeline is still an automation with a chat front end.
3. **Is the branching bounded and stable?** A handful of enumerable cases
   that change rarely → automation with conditional steps. Branching that
   grows with every new edge case is the tell in the other direction (see
   failure modes).
4. **Does any part require iterating with tools until a judgment-based stop
   condition?** "Search, read, decide whether that's enough, search
   differently" — runtime action selection, open-ended inputs, quality gates
   the model itself must judge. → **Agent** (or an agent *step* inside an
   automation — see hybrids).
5. **Does a human approval gate carry the judgment?** If the only
   "judgment" in the flow is a human clicking approve, the machine part is an
   automation. Human-in-the-loop does not make a workflow an agent.

## Hybrids are the common landing zone

The output of this gate is rarely a pure verdict:

- **Automation with an agent step** — a fixed pipeline where one stage is
  genuinely open-ended (research this account, triage this incident). The
  pipeline stays deterministic; the agentic stage is contained, evaluable,
  and independently replaceable.
- **Agent that invokes automations as tools** — the agent owns judgment and
  sequencing; well-understood procedures (provision X, file Y) are exposed to
  it as single deterministic tools rather than re-derived step by step.

Both hybrids follow the same principle that governs orchestration substrates
(`framework-or-hand-roll.md` and the runtime-portability findings): **match
each layer's mechanism to how predictable that layer's path is** — determinism
where the shape is known, agency where it is not.

## Failure modes, both directions

**Agent-where-automation-suffices:** per-run token cost on a task with a known
path; nondeterministic output where identical output was the requirement; an
eval harness built to verify what a workflow would have guaranteed by
construction; multi-second latency on a millisecond transform; and debugging
that requires reading transcripts instead of a step log. The tell: the
agent's "decisions" are the same every run.

**Automation-where-an-agent-was-needed:** the branch thicket — a workflow
that grows a new conditional every sprint to approximate a judgment call;
brittle extractors re-tuned for every input variant; escalation queues filling
with cases the flow can't express. The tell: the workflow's maintenance log
is a list of edge cases, and each fix narrows rather than generalizes.

## Consequences of the verdict

- **Automation** → the implementation question becomes workflow tooling
  (the organization's existing engine first — workflow/iPaaS platforms,
  scheduler-plus-script, or a data platform's native automation — evaluated
  like any framework choice per `framework-or-hand-roll.md`), with the AI
  step specced as a single well-typed model call: schema-validated output,
  retry policy, and a fallback path. Skip the agent taxonomy entirely.
- **Agent or hybrid** → proceed to `what-kind-of-agent-are-you-building.md`
  with the automation-shaped substeps noted as candidates for deterministic
  tools, not skills.

## Hard rules for pipelines consuming this entry

1. **The gate is asked first, and the answer is recorded.** A workload
   classification that assigns an agent class without stating why the
   workload isn't an automation is incomplete — "not an automation because
   <which question failed>" is one required line.
2. **"Automation" is a valid, complete recommendation.** A design whose
   honest output is "this is a workflow with one LLM step; here is the step's
   contract" is a success, not a failed agent design.
3. **Hybrid designs name the boundary.** Which stages are deterministic,
   which stage is agentic, and what contract crosses the boundary — an
   unmarked mix inherits the failure modes of both.

## Empirical anchor

None yet — this entry ships as the codified gate, with validation expected
from applying it to incoming build requests: the prediction to test is that a
material fraction of "agent" specs route to automation or hybrid, and that
routed-to-automation builds show lower cost and defect rates than agent
builds of the same workloads. A companion survey of automation tooling
(selection criterion: platforms actually present at customer organizations,
by industry adoption) is the natural follow-on entry; until it exists, tool
selection falls back to `framework-or-hand-roll.md` reasoning.
