# Fact extractor

You are reading one artifact (a call transcript, a meeting note, a slack thread, a runbook, a discovery doc) and extracting every concrete fact about the use case below.

The use case the customer wants to build:
**{USE_CASE_SEED}**

## Your job

Read the artifact and emit a list of `DistilledFact`s — one per atomic fact. A fact is a concrete, time-bound, testable statement the artifact contains. Distill it; do NOT quote verbatim. Each fact gets:

- A `topic` — a snake_case slug. Prefer the canonical topics below when one fits. If none fit, mint a fresh slug (the curator/normalizer will reconcile later).
- A `content` — your distillation of what the artifact says about that topic. One sentence; concrete, testable.
- A `source` — always `"stated"` for facts extracted from artifacts.

## Canonical topics

**Conceptual thread:**
- `desired_outcome` — the measurable end state the agent should produce
- `success_metric` — how success is measured (concrete, time-bound)
- `anti_goal` — what the agent should NOT do
- `current_pain` — a specific moment that hurts today
- `persona` — who the agent is for, with concrete attributes
- `decision_point` — a judgment moment the agent will face
- `escalation_rule` — when and how the agent hands off
- `risk` — what could go wrong

**Technical thread:**
- `tech_stack` — SDKs / frameworks / runtimes the team is committed to
- `data_sources` — where data physically lives (warehouses, tables, APIs)
- `semantic_layer` — Cortex / dbt / hand-rolled SQL / none
- `existing_context` — what's already in Atlan or equivalent
- `runtime_target` — where the agent eventually runs + infra constraints
- `governance_constraints` — must-use / can't-use / compliance
- `data_freshness` — real-time / daily / weekly / batch
- `identity_model` — per-user auth / service account / OAuth / etc.

## Extraction rules

1. **Multiple facts per topic are fine.** If the artifact contains three distinct decision points, emit three facts on `decision_point`.
2. **Distill, don't quote.** Reframe in concrete terms. *"They have a 99.9% SLA"* not *"Joe said 'yeah we run at three nines'"*.
3. **Skip noise.** Greetings, scheduling, meta-talk about the call format itself — don't extract.
4. **Skip the customer's questions about you.** Only extract facts about THEIR use case, not the FDE's process.
5. **Don't infer beyond the artifact.** If the artifact doesn't say it, don't write it. Other artifacts and discovery will catch the rest.
6. **No padding.** Emit fewer high-quality facts rather than many fluffy ones. Empty list is acceptable if the artifact genuinely has no use-case content (e.g., a scheduling email).

## Artifact

```
{ARTIFACT_TEXT}
```

## Output

Return a JSON object with one field `facts` — a list of DistilledFact objects:

```json
{
  "facts": [
    {
      "topic": "desired_outcome",
      "content": "<one-sentence distillation>",
      "source": "stated"
    },
    ...
  ]
}
```

If the artifact contains no use-case facts, return `{"facts": []}`.
