# solutions-consultant-gold

Gold-reference `RoleContext` for the Atlan Solutions Consultant role.

Produced by hand-running the 6-step intake pipeline through a stronger model than `claude-haiku-4-5` (used Sonnet/Opus tier in a separate session) on **2026-05-03**, before the proxy was available to test the production pipeline. This serves as the **eval baseline** every future Haiku run is compared against.

## What this is for

- **Quality benchmark.** When we run `intake/run.py` for real on `claude-haiku-4-5` via the LiteLLM proxy, diff the output against this. Big divergence on `flagged_unknowns` or `unwritten_rules` quality? The smaller model isn't keeping up. Expected divergence on field-level wording — that's fine.
- **Regression detection.** When we change a prompt, re-run intake and diff against this. If the diff makes things measurably worse, revert.
- **Onboarding doc.** New eyes reviewing the project can read this to see what "good output" looks like for a job-description-style artifact.

## What this is NOT

- The final spec. This is *priors* for the discovery agent to probe — the `flagged_unknowns` is the more important half. The `RoleContext` itself will be enriched conversationally during the actual discovery pipeline.
- A pinned target. Tomorrow's Haiku run might surface a better extraction for some fields. If it does, update this gold reference.
- An assertion that this output is perfect. See `prompt-feedback.md` for the known weaknesses identified during this hand-run (notably: vocabulary normalizer over-inferred CSA/CSM, unwritten-rules included one restatement, primary_outcomes thin).

## Run details

- **Date:** 2026-05-03
- **Model:** Sonnet/Opus tier (separate Claude session, not the production pipeline)
- **Source artifact:** `source/sc-role.md` — Atlan Solutions Consultant role definition (~450 tokens)
- **Pipeline version:** Pre-fix prompts (the contradiction in step 3 vocab and the conservative-bias gap in step 4 were identified by this run and patched after)

## Comparing future runs

```bash
uv run python -m scripts.compare_runs \
  --gold skills/solutions-consultant-gold/context.json \
  --candidate skills/solutions-consultant/context.json
```

(See `scripts/compare_runs.py` once it's written.)
