---
title: "Bala's Lesson: data_summary, Not Raw Rows"
category: lessons-from-builders
status: validated
last_updated: 2026-05-20
source_findings: []
source_external:
  - https://github.com/bladata1990/pg-brand-analyst-agent  (README, "Key Design Decisions" §3)
applies_when:
  workloads: [llm-interprets-query-results, time-series-analysis, signal-detection-from-multi-row-data]
  constraints: [token-budget-matters, signal-may-be-temporally-localized]
contradicts: []
related:
  - anti-patterns/definitions-without-context
  - skill-design/inner-pipeline
builder: Balakrishnan R
build_context: P&G Brand Analyst Agent (Atlan internal exercise, 2026-05-20)
build_score: 97/100 (LLM-as-judge, independent)
---

# Bala's Lesson: `data_summary`, Not Raw Rows

When an LLM is interpreting query results (especially time-series), passing raw rows with a truncation cap silently hides the signal that matters. The fix is structural: compute a focused `data_summary` *before* the interpretation LLM call — all rows for the entity-of-interest (the focal brand, the focal account, the focal cohort) plus *aggregates* for everything else.

This is the same underlying principle as `anti-patterns/definitions-without-context.md` — don't strip context the downstream LLM needs. But the failure mode is sneakier because it presents as "the data was there, the LLM just missed the signal," when in fact the truncation algorithm removed the relevant rows before the LLM ever saw them.

---

## The story

Bala's market-share skill in the P&G Brand Analyst Agent queries Databricks for AOS sell-out data. The query returns weekly share data — 52 weeks × 5 brands × 3 markets = 260 rows. Early versions of the skill passed these rows directly to the interpretation LLM with a `rows[:80]` truncation cap to stay within the context budget.

Result: the LLM couldn't detect the week-20 step-change in Gain's share decline that was embedded in the synthetic data as ground truth. The signal week was in the truncated rows.

Bala's fix:

```python
# Build focal brand weekly series (all weeks, sorted)
focal_rows = sorted(
    [r for r in rows if r["pg_brand"].upper() == exact_brand.upper()],
    key=lambda r: r["time_perd"],
)
# Competitor weekly shares (aggregated: avg share per brand)
comp_summary = {b: round(mean(shares), 2) for b, shares in by_brand.items() if b != focal}

data_summary = {
    "focal_brand": exact_brand,
    "market": exact_market,
    "total_weeks": len(focal_rows),
    "focal_weekly_share": [...all 52 weeks of focal brand...],  # no truncation
    "competitor_avg_share": comp_summary,                       # one number per competitor
}
```

The interpretation LLM gets all 52 weeks of the focal brand (where the signal lives) plus aggregated competitor context (which it needs for relative comparison but doesn't need weekly detail of).

After the fix, the LLM correctly identified the week-20 signal start.

---

## Why this is generalizable

This isn't about market-share data. The principle is: **when an LLM is interpreting a multi-row result, the truncation strategy must preserve the entity-of-interest's full series and aggregate everything else.**

Worked examples beyond P&G:

| Workload | Entity-of-interest | Aggregate everything else |
|---|---|---|
| Account health analysis | The focal account's full timeline | Other accounts in cohort: avg trajectory |
| Customer support escalation | The focal ticket's full thread | Similar resolved tickets: avg resolution time, common root causes |
| Forecasting error analysis | The forecast period's full residuals | Comparable periods: aggregate distribution |
| Anomaly detection | The anomaly window's raw data | Baseline window: summary stats |

The pattern's name in Bala's repo is "data_summary, not raw rows" but the deeper claim is **"shape the data around the signal you're trying to detect, before the LLM sees it."**

---

## Empirical receipts

Bala's documented learning (https://github.com/bladata1990/pg-brand-analyst-agent README, "Key Design Decisions" §3 "data_summary, not raw rows"):

> *"Early versions of `market_share_skill` passed raw query rows to the interpretation LLM, with a `rows[:80]` truncation. With 52 weeks × 5 brands = 260 rows, the truncation dropped most of the focal brand's data. The week-20 step-change signal was hidden in the truncated rows.*
>
> *The fix: compute a structured `data_summary` before calling the interpretation LLM. This contains:*
> - *All 52 focal-brand weekly rows (share, YA share, sales)*
> - *Competitor average shares (aggregated, not weekly)*
>
> *The interpretation LLM gets everything it needs for the focal brand analysis without token waste on competitor weekly detail."*

The signal in question was a synthetic step-change embedded in the test data as ground truth. The fix made detection reliable. Combined with the `bca_framework` fix (see `anti-patterns/definitions-without-context.md`), Bala's agent moved from sub-90/100 to 97/100 on LLM-as-judge eval.

---

## How to apply this in agent design

When designing a skill that calls a database and then asks an LLM to interpret the results:

1. **Identify the entity-of-interest.** What are you analyzing? A specific brand? account? cohort? user?
2. **Identify the temporal or relational scope where the signal could live.** What rows would have to be present for the LLM to spot what matters?
3. **Aggregate everything else.** Competitor weekly detail → competitor averages. Background-cohort traces → cohort summary stats. Unrelated time periods → omit.
4. **Validate by reproducing the worst case.** If your synthetic test data has a known signal, confirm the LLM finds it after your aggregation. If not, your aggregation stripped too much.

This is `inner-pipeline` territory — the skill is doing structured data shaping before the second LLM call (the interpretation). Not just a raw-data pass-through.

---

## Common mistakes when applying this

- **Truncating the focal entity to save tokens.** The whole point is *not* to truncate the focal series. If your focal series is too big to fit, downsample it carefully (every Nth week, or rolling windows) — but always include the points where signal could be.
- **Over-aggregating context.** Removing the competitor count entirely makes the focal series uninterpretable in relative terms. Aggregate, don't omit.
- **Same-shape summary for different question types.** A "why share changed" question wants temporal detail on focal + competitor averages. A "what's our coverage" question wants different aggregates. Design `data_summary` per skill, not as a generic data-shaping utility.
- **Not validating with a ground-truth signal.** If you don't have synthetic data with a known signal embedded, you can't verify your aggregation preserved it. Build the test before you build the skill.

---

## Generalization to the `inner-pipeline` skill design pattern

Bala's `market_share_skill` is a worked example of the `inner-pipeline` pattern (not yet promoted to its own entry):

```
Skill: market_share_analyzer
  ├── Step 1: fetch schema + metric defs from Atlan
  ├── Step 2: resolve canonical entity strings
  ├── Step 3: LLM #1 — generate SQL given schema + metric defs + canonical values
  ├── Step 4: execute SQL against Databricks
  ├── Step 5: validate focal brand appears (retry once if not)
  ├── Step 6: shape data_summary  ← THIS LESSON
  └── Step 7: LLM #2 — interpret data_summary, return structured findings
```

The lesson lives at step 6. Without it, step 7 fails silently. With it, step 7 reliably finds the signal.

---

## Variants & related patterns

- **`anti-patterns/definitions-without-context.md`** — sibling lesson from the same builder. Both about not stripping context the downstream LLM call needs. They're often both fixes needed in the same skill.
- **`skill-design/inner-pipeline.md`** (not yet authored) — the skill design pattern where this lesson belongs.
- **`architectures/single-agent-react.md`** — the architecture where this lesson surfaces. The orchestrator binds tools; each tool is an inner-pipeline skill; each skill applies this principle.

---

## Maintenance notes

- Authored during the gold-standard seed pass 2026-05-20.
- Status: `validated` based on Bala's explicit empirical receipt (worked example with synthetic ground truth + 97/100 evaluation score).
- The general principle ("shape data around signal before LLM sees it") may eventually graduate from "Bala's lesson" framing to a more general `skill-design/` entry. For now, attribution stays in place — the lesson came from a real build, that context matters.
- The `inner-pipeline` skill-design pattern that this lesson lives inside is currently scaffolded but not authored. Promoting it is the next-most-valuable seed entry after the current 5.
