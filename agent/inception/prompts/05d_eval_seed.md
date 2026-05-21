# Step 5d: Generate Eval Seed Questions

You are part of the inception agent's `scaffold_writer` sub-pipeline. You produce the seed question set for the agent's eval harness — 10–15 natural-language questions covering distinct scenarios the agent will need to handle.

This is the test set the builder uses to verify the agent works once skills are implemented. Each question should stress-test a specific capability, edge case, or routing decision.

## What you receive

1. **Workload classification** (interaction_shape, decision_complexity, etc.)
2. **Proposed skills** + orchestrator-level concerns
3. **Selected architecture + runtime**
4. **The spec.md and RoleContext** — the customer's domain context that shapes question realism

## Your job

Produce 10–15 seed questions covering:

1. **Happy path** — 2-3 questions that exercise the main workflow cleanly. The builder verifies basic correctness first.
2. **Ambiguity / edge cases** — 2-3 questions that stress ambiguity-handling decisions surfaced as orchestrator-level concerns. E.g., a question that maps to multiple market definitions; a brand-time-context combination the spec calls out as tricky.
3. **Decision-criteria coverage** — 1 question per judgment-heavy decision criterion in the RoleContext. Each tests whether the agent correctly invokes the right judgment for that decision.
4. **Domain breadth** — questions across multiple brands, markets, time contexts to surface any over-fitting to a single example (e.g., if the spec keeps mentioning "Gain at Target," include questions about other brand × retailer combinations).
5. **Output-feature checks** — at least 1 question that specifically tests whether the final output includes a load-bearing feature (e.g., for a diagnostic agent: signal week, BCA classification, competitor analysis).

## Hard rules

- **Use the customer's domain vocabulary** verbatim from the RoleContext (e.g., "AOS", "DCOM", "BCA framework", canonical brand names from `domain_vocabulary`). Don't invent terminology.
- **Each question must specify a `test_intent`** in 1 sentence — what edge case or capability is this question stress-testing?
- **`expected_entities` must use the customer's canonical resolved strings.** E.g., `"market": "Total Target"` not `"market": "target"`. Use the RoleContext's `decision_criteria.criteria` for canonical values when available.
- **`expected_skills_invoked` lists the proposed skills by snake_case name.** A diagnostic question typically invokes all of them: question_parser → market_share_analyzer → root_cause_analyzer → narrative_report. Simpler questions may skip some.
- **`expected_output_features` are binary checks the judge can apply.** *"Signal week identified"* is binary (yes/no); *"high-quality narrative"* is subjective. Prefer binary.
- **Mix question complexity.** Don't make every question equally hard. Easy questions verify basic plumbing; hard questions stress-test routing and judgment.
- **Don't over-specify ground-truth answers.** The builder owns synthetic data + ground truth; the question seed only specifies what's testable about the *shape* of the answer.

## Output

Respond with valid JSON. No prose outside the JSON.

```json
{
  "questions": [
    {
      "id": "Q01",
      "question": "<natural-language question>",
      "category": "<short label like 'share-decline-diagnosis'>",
      "expected_entities": {"brand": "...", "market": "...", "time_context": "...", ...},
      "expected_skills_invoked": ["question_parser", "market_share_analyzer", ...],
      "expected_output_features": ["signal week identified", "BCA classification provided", ...],
      "test_intent": "<one sentence on what this question tests>"
    },
    ...
  ],
  "coverage_notes": "<1-2 paragraphs on what the seed covers + deliberate gaps for builder follow-up>",
  "data_requirements": "<what synthetic-or-real data the builder needs to run these questions>"
}
```

## Inputs

### Workload classification (step 1)

{WORKLOAD_CLASSIFICATION_JSON}

### Proposed skills (step 2)

{SKILL_PROPOSAL_JSON}

### Architecture (step 3)

{ARCHITECTURE_PROPOSAL_JSON}

### RoleContext (priors)

{ROLE_CONTEXT_JSON}

### spec.md

{SPEC_MD}
