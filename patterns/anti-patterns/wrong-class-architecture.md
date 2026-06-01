---
title: Wrong-class architecture (architecture chosen without anchoring on workload class)
category: anti-patterns
status: validated
last_updated: 2026-05-29
source_findings:
  - findings/09-iteration-receipts-from-atlan-se-copilot.md
source_external: []
applies_when:
  workloads: [any]
  constraints: [multi-step-decision-pipeline, architecture-selection]
contradicts: []
related:
  - decision-guides/what-kind-of-agent-are-you-building
  - architectures/single-agent-react
  - architectures/chained-pipeline
snapshot_date: 2026-05-29
---

# Wrong-class architecture

Picking an architecture by matching its `applies_when.workloads` against the workload axes in isolation, without anchoring on the workload's **class** from the taxonomy first. The architecture proposer surveys patterns, finds 2-3 that overlap with the axes, and picks one — without asking "is this architecture appropriate for the *kind* of agent we're building?"

The taxonomy class encodes architectural defaults that the per-pattern `applies_when.workloads` doesn't fully capture. Skipping the class anchor produces architectures that *technically* satisfy the workload axes but don't fit the class's operational shape.

## How it shows up

Three real failure shapes:

### Shape 1 — co-pilot built as conversational agent

Workload axes: `interaction_shape: conversational`, `decision_complexity: judgment-heavy`, `state_shape: session-scoped`. Architecture chosen: `single-agent-react` with no host-tool integration patterns. Result: an architecture that runs the LLM's reasoning in its own surface, when the use case wanted the LLM to operate *alongside* a human in their existing tool. The conversational axes were right; the **class** (co-pilot) was missed.

### Shape 2 — task agent built as long-running worker

Workload axes: `interaction_shape: batch`, `multi_step_or_single_step: multi`, `latency_sensitivity: tolerant`. Architecture chosen: durable workflow engine (Temporal-style) with cron triggers and persistent state. Result: heavy infrastructure for what is actually a stateless task agent — invoked discretely, completes the job, returns. The "tolerant" latency was about per-task duration, not about cross-invocation memory.

### Shape 3 — claw built as task agent

Workload axes: `interaction_shape: batch`, `decision_complexity: judgment-heavy`, `state_shape: session-scoped`. Architecture chosen: stateless task agent. Result: an agent that needs to remember what it did yesterday (autonomous worker class) is built without durable state, then breaks the first time it runs twice on the same input. The class was missed; the spec hadn't surfaced that "session-scoped" meant cross-invocation, not within-invocation.

## Why it happens

Three mechanisms converge:

1. **`applies_when.workloads` is a lossy signal.** A pattern's `applies_when.workloads: [conversational]` matches BOTH conversational agents and co-pilots and even some task agents. The axes alone don't disambiguate which kind of agent the pattern fits. The class taxonomy adds that disambiguation; `applies_when` doesn't.

2. **Architectures and classes are orthogonal vocabularies.** `single-agent-react` is an architecture. "Co-pilot" is a class. The same architecture can implement multiple classes; the same class can use multiple architectures. The proposer that thinks only in architectures will miss class-level fit.

3. **The proposer has no template for "what architectures fit class X."** Without `patterns/decision-guides/what-kind-of-agent-are-you-building.md` loaded, the proposer matches patterns axis-by-axis. With the taxonomy loaded and cited, the proposer first identifies the class, then filters architectures by class fit, then refines by axes.

## Why it matters

Architectures imply infrastructure. Wrong-class architecture costs:

- **Co-pilot built as conversational** → wrong UX (chat box instead of inline suggestion), wrong evaluation (accuracy instead of acceptance-rate), wrong observability (no host-tool telemetry)
- **Task agent built as worker** → over-infrastructure (Temporal/Dapr for a one-shot job), brittleness (state machinery for state nobody needed), cost (continuous infra for batch work)
- **Claw built as task agent** → under-infrastructure (no durability), correctness bugs (no memory across wakeups), reliability gaps (no recovery posture)

The cheaper mistake is over-engineering (task agent built as worker — wastes infra). The expensive mistake is under-engineering (claw built as task agent — fails in production after weeks of working). Either way, picking by axes alone gives no protection.

## How to prevent it

### Architecture-proposer prompt

Make the class anchor non-optional:

> *"Step 1 of architecture selection is to identify the workload's class from `patterns/decision-guides/what-kind-of-agent-are-you-building.md`. The class determines which architectures are even candidates. Only AFTER class-filtering do you refine by `applies_when.workloads` and the workload axes."*

### Workload classifier coupling

The workload_classifier MUST emit the class in its rationale (cite the taxonomy entry explicitly). When the workload axes are ambiguous between two classes (e.g., looks like co-pilot OR task agent), the classifier should surface BOTH and flag the ambiguity in `open_questions` — never silently pick one and bury the decision.

### Verification

After architecture selection, the proposer should explicitly cross-check:

> *"Given the class is [co-pilot / conversational / task / claw / chatbot], does this architecture's operational shape match the class's typical defaults? If not, what's the specific reason to deviate?"*

This is the audit pass. Either the architecture matches, or there's a defensible reason to override — but the override must be explicit and reasoned.

## Provenance

This anti-pattern was extracted from the atlan-se-copilot iteration documented in findings/09. Before the taxonomy was loaded into the architecture_proposer's context, the proposer for the SE co-pilot use case selected `single-agent-react` purely on axes match — correct architecture, but the design_rationale didn't explain that the choice fit the **co-pilot** class specifically. After the taxonomy was loaded into step 3's prompt, the same use case selected the same architecture but anchored the choice on "co-pilot class" explicitly, with class-driven justification ("the SE drives the work, the agent runs alongside in the host tool, the SE owns approval gates"). The architecture choice was the same; the *reasoning* was qualitatively better, and the downstream skill cut (step 2's later iteration) self-corrected from 11 skills to 6 with the same anchor.

## Hard rule for architecture_proposer

Every architecture selection rationale must:

1. **Identify the workload's class explicitly**, citing `patterns/decision-guides/what-kind-of-agent-are-you-building.md`.
2. **Filter candidate architectures by class fit FIRST**, then by `applies_when.workloads`.
3. **Cross-check the selected architecture against the class's "Typical architectures" list** from the taxonomy entry. If the selection diverges from the typical list, name the specific reason in the rationale.
