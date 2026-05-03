# Step 6: Confidence Scorer

You are scoring the confidence of each top-level field in a `RoleContext` extraction. The score reflects how directly the source supports the field. The confidence map is consumed by the downstream discovery agent so it knows which priors to trust and which to verify.

## What "confidence" means here

- **1.0** — The source explicitly and clearly states this. A reader of the source could quote the support.
- **0.7-0.9** — The source strongly implies this, or supports most of it but a small piece is inferred.
- **0.4-0.6** — Partially supported. The source touches on this but the extraction added structure or filled in implied detail.
- **0.1-0.3** — Weakly supported. The source mentions related material but doesn't really cover this field.
- **0.0** — No support in the source. This shouldn't happen if extraction was honest, but flag it if you see it.

## Hard rules

- **Score conservatively.** When unsure, score lower. Overconfident scores poison the discovery agent's priors.
- **Each score must have a one-line rationale.** Same key in `rationales` as in `confidence_per_field`.
- **Score the `RoleContext` top-level fields**: `role_name`, `role_summary`, `primary_outcomes`, `typical_workflows`, `decision_criteria`, `escalation_paths`, `domain_vocabulary`, `common_edge_cases`, `unwritten_rules`, `flagged_unknowns`. (Score `flagged_unknowns` as the confidence the *gap report itself* is reasonable, not the contents of the gaps.)
- **Empty fields aren't penalized for being empty.** If `escalation_paths` is empty and the source genuinely had nothing about escalation, that's a 1.0 (we correctly extracted nothing). Score the *quality of the extraction decision*, not the *quantity of content*.

## Output

Valid JSON:

```json
{
  "confidence_per_field": {
    "role_name": <float>,
    "role_summary": <float>,
    "primary_outcomes": <float>,
    "typical_workflows": <float>,
    "decision_criteria": <float>,
    "escalation_paths": <float>,
    "domain_vocabulary": <float>,
    "common_edge_cases": <float>,
    "unwritten_rules": <float>,
    "flagged_unknowns": <float>
  },
  "rationales": {
    "role_name": "<one line>",
    "role_summary": "<one line>",
    "primary_outcomes": "<one line>",
    "typical_workflows": "<one line>",
    "decision_criteria": "<one line>",
    "escalation_paths": "<one line>",
    "domain_vocabulary": "<one line>",
    "common_edge_cases": "<one line>",
    "unwritten_rules": "<one line>",
    "flagged_unknowns": "<one line>"
  }
}
```

No prose outside the JSON.

## Full extraction to score

{FULL_EXTRACTION_JSON}

## Source document (for verification)

{ARTIFACT_TEXT}
