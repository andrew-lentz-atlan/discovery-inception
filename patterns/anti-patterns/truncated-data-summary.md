---
title: Truncated Data Summary
category: anti-patterns
status: validated
last_updated: 2026-05-20
source_findings: []
source_external:
  - https://github.com/bladata1990/pg-brand-analyst-agent  (README §3)
applies_when:
  workloads: [llm-interprets-query-results, time-series-analysis, signal-detection-from-multi-row-data]
  constraints: [token-budget-matters, signal-may-be-temporally-localized]
contradicts: []
related: [definitions-without-context]
---

# Truncated Data Summary

When an LLM interprets multi-row query results (especially time series), passing raw rows with a simple `rows[:N]` truncation silently hides the signal that matters. The signal — a step-change at week 20, an anomalous spike, a missing data point — gets cut off by the slice before the LLM ever sees it.

The fix: compute a structured `data_summary` *before* the interpretation LLM call. Preserve the **entity-of-interest's full series**. Aggregate everything else.

## Detect when

- LLM-based interpretation of query results returning many rows
- A `rows[:N]` or `limit N` cap exists between the query and the interpretation call
- The thing you're trying to detect is temporally localized (a spike, a step-change, a regime shift) and could fall outside the truncation window
- Synthetic tests with a known embedded signal fail intermittently — sometimes the signal lands in the kept rows, sometimes it doesn't

## Don't worry about when

- Interpretation is on aggregates that don't depend on individual rows (avg, count, top-K)
- Result set is small enough to fit in full
- Signal is detectable from any random subsample (rare; check before assuming)

## Key gotchas

- **Truncating the focal entity defeats the point.** If the focal series is too large, downsample carefully (every Nth, rolling windows) — never random slice.
- **Over-aggregating context.** Removing competitor count entirely makes the focal series uninterpretable in relative terms. Aggregate, don't omit.
- **Shape per question type, not as a generic utility.** A "why share changed" question wants temporal detail on focal + competitor averages. A "what's our coverage" question wants different aggregates. Don't reuse one shape across question types.
- **Validate with a ground-truth signal.** Build synthetic test data with a known embedded signal. Confirm the LLM finds it after your aggregation. If not, your aggregation stripped too much.

## The pattern in code

```python
focal_rows = sorted([r for r in rows if r["pg_brand"] == focal], key=lambda r: r["week"])
competitor_avg = {b: mean(shares_by_brand[b]) for b in competitors}

data_summary = {
    "focal_brand": focal,
    "focal_weekly_share": focal_rows,        # ALL rows, no truncation
    "competitor_avg_share": competitor_avg,  # one number per competitor
}
# pass data_summary to interpretation LLM, not raw rows
```

## Empirical anchor

Bala's P&G Brand Analyst Agent. Early `market_share_skill` passed raw rows with `rows[:80]`. With 52 weeks × 5 brands = 260 rows, the truncation dropped most of the focal brand's data. The synthetic week-20 step-change in Gain's share decline (embedded as ground truth) was hidden in the truncated rows. Fix: structured `data_summary` with all 52 focal-brand weekly rows + aggregated competitor shares. Combined with the `definitions-without-context` fix, agent moved from sub-90 to 97/100 on LLM-as-judge.

Origin: documented by Bala (P&G Brand Analyst Agent README §3, *"data_summary, not raw rows"*).
