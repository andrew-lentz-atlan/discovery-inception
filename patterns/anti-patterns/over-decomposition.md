---
title: Over-decomposition (too many skills)
category: anti-patterns
status: validated
last_updated: 2026-05-29
source_findings:
  - findings/09-iteration-receipts-from-atlan-se-copilot.md
source_external: []
applies_when:
  workloads: [conversational-agent, co-pilot, task-agent]
  constraints: [skill-proposer-output, multi-skill-decomposition]
contradicts: []
related:
  - decision-guides/what-kind-of-agent-are-you-building
  - skill-design/inner-pipeline
  - anti-patterns/definitions-without-context
snapshot_date: 2026-05-29
---

# Over-decomposition (too many skills)

A skill cut with 10+ skills for a workload that should have 4–6, where the extras represent **synthetic granularity** — splitting one judgment into multiple skills because the proposer lacks a coherent organizing principle. Each extra skill adds orchestration overhead, dilutes the agent's reasoning across more boundaries, and produces SKILL.md files that overlap in purpose.

## How it shows up

A typical signature, from a real atlan-se-copilot iteration:

- `account_context_synthesizer` ✓
- `stage_readiness_assessor` ✓
- `call_prep_generator` ✓
- `bespoke_demo_planner` ✓
- `material_gap_and_risk_flagger` ✓
- `stage_transition_recommender` ✓
- ...plus four more skills that decompose what should be sub-steps of the above into independent skills:
  - `stakeholder_identifier` (should be inside `account_context_synthesizer`)
  - `tech_stack_extractor` (same)
  - `historical_outcome_analyzer` (should be inside `stage_readiness_assessor`)
  - `escalation_path_resolver` (should be inside `material_gap_and_risk_flagger`)

The proposer is treating *every distinct sub-task* as a skill rather than identifying the natural skill boundaries. The result is 10 skills where 6 would do the job better.

## Why it happens

Two failure modes converge:

1. **Missing taxonomy anchor.** Without knowing the workload's class (co-pilot, task agent, conversational, etc.), the proposer has no template for "how many skills does an X-class agent typically have." It then errs toward more skills, on the implicit assumption that more decomposition is always more rigorous.

2. **Reasoning by enumeration, not by responsibility.** The proposer lists every distinguishable verb in the spec and turns each into a skill. But many verbs are *steps inside one responsibility*, not separate responsibilities. "Extract tech stack" + "synthesize account state" + "identify stakeholders" are all sub-steps of a single responsibility — building a unified view of the account. That's one skill with internal structure, not three skills.

## Why it matters

Each extra skill costs:

- **Orchestrator complexity.** More skills = more routing decisions for the LLM. Routing latency scales with skill count.
- **Eval surface area.** Each skill needs its own SKILL.md, judge harness dimension, eval seeds. 10 skills = 10× the maintenance.
- **Architectural confusion.** Over-decomposed agents push complexity from inside-the-skill (where it's natural and testable in isolation) to between-skills (where it's harder to reason about). Inter-skill state passing breeds bugs.
- **Cited evidence weakens.** The provenance field of each skill must point to ≥2 RoleContext sources. When the proposer is grasping for skills, the provenance becomes thin — citing one workflow step as the entire justification for a skill.

## When to drop a skill (the test)

Apply these three filters in order:

1. **Provenance test.** Does this skill cite ≥2 distinct RoleContext sources (decision_criteria, workflow steps, primary_outcomes, flagged_unknowns)? If not, it's not a real skill — it's a sub-step. Fold into the nearest parent skill.

2. **Owned-decision test.** Does this skill own at least one `is_judgment: true` decision from `decision_criteria`? If the skill is purely mechanical (extract X from Y), it probably belongs inside another skill's body, not as a peer.

3. **Class-fit test.** Does the count match the class's typical cardinality?

   - **Chatbot:** 1–3 skills (search/answer)
   - **Conversational agent:** 3–6 skills (gather + reason + answer + cite)
   - **Task agent:** 3–8 skills (parse → fetch → analyze → compose → emit)
   - **Co-pilot:** 4–7 skills (one per primary helper action in the host tool)
   - **Autonomous worker / claw:** 5–12 skills (decompose; durability and observability matter more)

   If you're at 10+ skills for a chatbot or conversational agent, something is wrong.

## Counter-pattern

The cure isn't fewer skills — it's the right skills with internal structure. Move complexity *inside* skills using `inner-pipeline` body shapes (see `patterns/skill-design/inner-pipeline.md`) when a skill has multi-step internal work. The result: a 6-skill cut where 2 of those skills have 3-stage internal pipelines is far easier to reason about than a 10-skill cut where every skill is one LLM call.

## Provenance

This anti-pattern was extracted from the atlan-se-copilot iteration documented in findings/09. Specifically: before the workload_classifier was loading `patterns/decision-guides/`, the skill_proposer produced an 11-skill cut for the SE co-pilot use case (see compare_inception runs against `sess_b6b350634626`). After loading the taxonomy and citing the co-pilot class as the organizing principle, the same use case produced a clean 6-skill cut — same coverage, less synthetic granularity. The taxonomy provided the missing anchor.

## Hard rule for skill_proposer prompts

If your output has more than 8 skills, you must:

1. Cite the workload class explicitly in `granularity_argument`
2. Defend each skill past the 8th with the three filters above
3. Surface any skills that *almost* failed a filter as candidates for folding
