# Top-down discovery for a Sales Pipeline Analyst agent — handout for CES meeting

**Project:** [discovery-inception](https://github.com/andrew-lentz-atlan/discovery-inception)
**Demo case:** Sales Pipeline Analyst Cortex Analyst agent at TechCo
**Session:** `sess_aa0de4a3f5bc` (50 customer turns, 9.1 minutes wall time)

---

## What this is

Discovery-inception is the **top-down complement** to your `bulk-repos-claude` pipeline.

Your `discovery_agent` works bottom-up from a `ColdStartSnapshot` (Atlas metadata). It can infer use cases and propose analyst skeletons from what's *written down*. That's necessary but not sufficient.

This is a synthetic demo of what bottom-up discovery **cannot produce**: structured interview-derived context from a senior practitioner. Patterns, edge cases, anti-goals, and decision rules that exist only in someone's head.

This handout shows the output of running the discovery-inception agent through a 50-turn synthetic interview with a senior RevOps practitioner. The customer turns were pre-written by Andrew to embed 10 specific "novel insights" — facts that would never appear in a wiki, JD, or runbook. Then the actual agent ran a full discovery, generated a structured spec, and ran a deterministic close-out synthesis at session end.

The output is in [`02_spec.md`](./02_spec.md) (human-readable brief) and [`02_spec.json`](./02_spec.json) (machine-readable, would feed your synthesis_agent).

---

## Session at a glance

| Metric | Value |
|---|---|
| Customer turns | 50 |
| Wall time | 9.1 min |
| Mega-agent input tokens | 732K |
| Mega-agent output tokens | 14K |
| Extractor sub-agent calls (triage/distill/synthesizer) | 89 |
| Lazy synthesizer invocations during conversation | 2 |
| Deterministic close-out synthesis | 1 |
| Topics captured (free-form, schema-aligned) | 22 |
| Facts captured | 38 |
| Gaps flagged for follow-up | 1 |
| Working theory confidence at close | medium |

---

## The 10 novel insights captured

Every one of these would be invisible to bottom-up metadata discovery. Each maps to a specific structural decision in the agent build.

| # | Insight (from the interview) | What it would change in a Cortex Analyst build |
|---|---|---|
| 1 | **Q4 stage-3 deals run ~30% inflated** because AEs push deals out to look better at end-of-Q3 QBR. *(Walked back later — 12-15% average, 30% is the conservative-planning case.)* | Discount logic on `current_quarter_pipeline` measure; configurable parameter, not a constant |
| 2 | **"High confidence" two weeks before EOQ is a sweat signal** — close rate by "days from EOQ when high-confidence flag was set" is U-shaped | Custom instruction: deals flagged high-confidence within 14 days of EOQ should be re-ranked, not treated as committed |
| 3 | **Staleness is stage-aware.** 21 days stale in Discovery = healthy; 21 days stale in Negotiation = dead | `is_stale` derived dimension must be a function of (stage, days_since_last_activity), not a global threshold |
| 4 | **Director-or-above call in the last 14 days zeros close-date confidence.** The deal is being saved or killed; the AE's stated close date is meaningless until the dust settles | Filter requiring activity log join to user.title; agent should suppress forecast confidence during the 14-day window |
| 5 | **Account-tier inflation has different cadences.** Strategic AEs face quarterly pressure (their VP gets quarterly reviews); MM AEs face monthly | Reports must NOT collapse Strategic and Mid-Market into a single "overall pipeline" view — cadence rhythms are different |
| 6 | **Procurement signal = 1+ quarter slip, 70% confidence, $1.2M average ARR.** Any deal with someone titled Procurement / Sourcing / Vendor Management / Commercial Operations in contact roles | Derived `procurement_involved` flag (joins `opportunity_contact_role.title`) → custom_instruction: adjust forecast confidence for these deals |
| 7 | **Renewal masquerade: ~8% of "new logo" deals are actually expansions** recoded for comp reasons | Custom instruction: cross-check `parent_account_id` + `customer_since_date` before counting as net-new ARR |
| 8 | **HR-protected anti-goal: NEVER show individual-rep performance comparisons** outside their reporting line. Two incidents in 18 months, one lawyer letter | Hard custom_instruction at the prompt level + verification step on outputs — likely a `verify_no_comparative_views_across_hierarchy` step in the agent's tool chain |
| 9 | **Persona-specific must-NOT-knows.** AEs hate peer comparisons; SDRs hate ARR forecasting (not their job); Managers want sub-regional breakouts (their bonus structure); CFOs hate reported ARR | Persona-aware default queries + view scopes; not one dashboard but four |
| 10 | **Contract-vs-cash gap.** Reported ARR (AE's stated number) diverges from recognized revenue (what Finance can collect) by 8-15% on multi-year deals, up to 25% on multi-year multi-product channel deals | Two distinct measures with audience-aware defaults: `reported_arr` for AE views, `recognized_revenue` for CFO views, with `divergence > 10%` triggering an explanatory note |

---

## How this maps to your `context_repo` structure

Each `BulkSeedBundle` your `synthesis_agent` produces has files like `manifest.json` + `semantic_models/` + `skills/` + `quality_report.md` + `evaluation_summary.md`. Here's how the discovery output maps in:

```
context-repo/
├── manifest.json                  ← (CES-managed)
├── model.yaml                     ← (CES synthesis_agent produces — informed by discovery)
├── semantic_models/               ← (CES)
│   └── ...                        ← (informed by insights 1, 3, 4, 6, 7, 10 above)
├── skills/                        ← (CES)
│   └── ...                        ← (sub-skills informed by insights 4, 6, 8, 9)
├── instructions.md                ← (CES generates — should encode anti-goals from insights 8, 9)
├── test_questions.csv             ← (CES — could be seeded from 5 acceptance questions in spec)
├── evaluation/latest.json         ← (CES simulation engine)
└── discovery/                     ← (NEW — what we'd contribute)
    ├── spec.md                    ← Human-readable interview brief
    ├── spec.json                  ← Machine-readable, schema below
    ├── conversation.json          ← Full audit trail of the discovery interview
    ├── working_theory.md          ← Working hypothesis from synthesis
    ├── flagged_gaps.md            ← Things the interviewee couldn't answer (need escalation)
    └── priors.json                ← The intake-side artifact analysis (what came from the JD)
```

**The integration is purely additive** — no changes to CES's existing artifact format. We push into `discovery/` via the existing `POST /context_repo/{repo_id}/artifacts` API. CES code doesn't need to change to receive these.

What WOULD change CES's behavior: extending the `synthesis_agent`'s prompt to read `discovery/spec.json` when present, as a structured input alongside the cold-start snapshot. That's the proposed integration point.

---

## Spec schema (what `spec.json` looks like)

Top-level shape:
```json
{
  "use_case_seed": "we want a Sales Pipeline Analyst agent ...",
  "role_id": "sales-pipeline-analyst-techco",
  "phase": "drilling",
  "topics": [
    {
      "topic": "forecast_inflation_pattern",
      "facts": [
        "Q4 stage-3 deals run about 30% inflated because AEs push deals out to look better at end-of-Q3 QBR; this adjustment is modeled into internal conservative forecast by Sales Strategy",
        "When an AE marks a deal 'high confidence' two weeks before end of quarter, the deal almost always does NOT close..."
      ],
      "sources": ["stated", "stated"],
      "superseded_facts": [],
      "bedrock_reached": false,
      "why_chain": [],
      "pending_questions": []
    },
    ...
  ],
  "gaps": [
    {
      "question": "...exact discount formula for procurement-involved deals...",
      "why_it_matters": "...question came up but current counterparty can't answer it; needs escalation to Lisa.",
      "related_topic": "escalation_rule",
      "gap_type": "missing_why"
    }
  ],
  "working_theory": {
    "one_line_framing": "A Sales Pipeline Analyst agent that answers plain-language questions about pipeline state...",
    "candidate_framings": ["Autonomous analyst with hard gates...", "Hybrid analyst with per-deal escalation...", "Reporting layer with manual forecast synthesis..."],
    "open_questions": ["When the agent flags a renewal deal as 'low NPS, CS review required'...", "..."],
    "sharpest_disconfirmer": "If the agent cannot reliably join Gainsight NPS data to Salesforce renewal opportunities in real time...",
    "confidence": "medium"
  },
  "theory_history": [...]
}
```

Topics are free-form (the agent picked them based on the conversation), not constrained to a fixed taxonomy. Stage 3 validation (not yet built) would normalize duplicates and align to canonical buckets if needed.

---

## What we'd want to test in your pipeline

Three concrete experiments:

### 1. Does your `synthesis_agent` produce different output when `discovery/` is present?

Run the same `BulkSeedBundle` generation twice:
- **Run A:** Cold-start snapshot only (current behavior). Use TechCo's `SALES_PIPELINE` table metadata.
- **Run B:** Same snapshot + `discovery/spec.json` from this session.

Compare the generated `model.yaml`, `instructions.md`, and `test_questions.csv`. Does Run B have:
- A `procurement_involved` derived flag?
- A stage-aware staleness definition?
- The HR-protected rep-comparison guard in instructions?
- The audience-aware ARR-vs-revenue measure split?

If yes, the top-down lens demonstrably enriches the output. If no, we need to figure out where the integration is dropping the discovery signal.

### 2. Does your simulation engine catch the right test questions?

The 5 acceptance test questions from the spec:
1. *"What's our real Q4 commit, accounting for the patterns we talked about?"*
2. *"Show me deals where management intervention happened in the last two weeks."*
3. *"Which Strategic accounts have procurement-involved deals slipping?"*
4. *"What's our actual coverage by sub-region if we discount the inflation appropriately?"*
5. *"How does our recognized revenue forecast differ from reported ARR this quarter?"*

Put these into the repo's `test_questions.csv`. Run your evaluator (`app/evaluator.py`). Three of these (1, 3, 4) require domain logic that no cold-start snapshot would suggest. Does the synthesis_agent's output handle them, with or without `discovery/` as input? That's the diff.

### 3. Does the `quality_evaluator` flag what's missing?

The flagged gap in this spec is *"exact procurement discount formula — needs escalation to Lisa."* Does CES's quality evaluator surface this as a known unknown? If not, can `discovery/flagged_gaps.md` feed your evaluation_summary.md to make these visible?

---

## What I'd want from this meeting

Three things to figure out together:

1. **Integration shape.** Is the `discovery/` additive-directory pattern the right one? Or would you prefer:
   - A new `repo_type = 'top_down_discovery'` template?
   - A new input port on `discovery_agent` that accepts structured top-down spec alongside the snapshot?
   - Something else?

2. **`synthesis_agent` extension.** If the answer to (1) is "additive directory," would you take a PR extending `synthesis_agent`'s prompt to read `discovery/spec.json` when present? I'd handle producing it; you'd handle the prompt update + tests.

3. **Test plan.** Pick one of the three experiments above. Run it end-to-end on this TechCo demo (or pick a real customer use case). See whether the top-down lens demonstrably improves the synthesis output.

---

## Repo + artifacts

- **discovery-inception:** https://github.com/andrew-lentz-atlan/discovery-inception
- **Demo files:**
  - [`01_intake_artifact_sales_pipeline_analyst_role.md`](./01_intake_artifact_sales_pipeline_analyst_role.md) — the JD that intake processed
  - [`02_spec.md`](./02_spec.md) — discovery output (human-readable)
  - [`02_spec.json`](./02_spec.json) — discovery output (machine-readable, would feed your `synthesis_agent`)
  - [`02_session.json`](./02_session.json) — full conversation trace (audit)
  - [`03_ces_meeting_handout.md`](./03_ces_meeting_handout.md) — this doc
