# Discovery spec: we want a Sales Pipeline Analyst agent (Cortex Analyst flavor) at TechCo so RevOps, AE managers, VP of Sales, and CFO can ask plain-language questions about pipeline state and trust the answers

**Session:** `sess_aa0de4a3f5bc`
**Role priors:** `sales-pipeline-analyst-techco`
**Phase at close:** `drilling`
**Working theory confidence:** `medium`

## Working theory

> A Sales Pipeline Analyst agent that answers plain-language questions about pipeline state, forecast accuracy, and deal risk by querying Snowflake and Salesforce, auto-flags renewal deals with low NPS for CS handoff, applies documented slip-rate patterns (procurement, segment-specific variance), and escalates forecast synthesis and deal-risk scoring to Lisa or RevOps when proprietary model judgment is required.

**Alternative framings the data could also support:**
- Autonomous analyst with hard gates — the agent answers pipeline questions directly, blocks forecast answers for low-NPS renewals until CS clears them, applies documented rules (procurement flag, segment slip rates) uniformly, and only escalates when Lisa's proprietary discount formula or segment-variance approval is needed.
- Hybrid analyst with per-deal escalation — the agent answers standard pipeline questions and flags risks (low NPS, procurement), but escalates to Lisa for approval before applying segment-specific slip-rate variance to any individual deal or forecast adjustment, treating her judgment as a required gate rather than a reference layer.
- Reporting layer with manual forecast synthesis — the agent surfaces pipeline state, applies hard rules (NPS-CS gate, procurement flag), and flags deals at risk, but routes all forecast synthesis, variance reconciliation, and deal-risk scoring to Lisa or RevOps rather than combining signals itself into a forecast answer.

**Open questions that would sharpen this theory:**
- When the agent flags a renewal deal as 'low NPS, CS review required,' does it hold that deal out of the forecast entirely until CS responds with explicit clearance, or does it include it with a 'pending CS clearance' caveat and let the forecaster decide whether to count it?
- For the 70% procurement slip-rate pattern and any segment-specific variance Lisa has documented, does the agent apply these uniformly to all deals matching the criteria, or must Lisa review and approve the application per-deal or per-segment before the agent can use it in a forecast answer?

**Sharpest disconfirmer** (what would prove this theory wrong):

> If the agent cannot reliably join Gainsight NPS data to Salesforce renewal opportunities in real time, or if CS does not have a defined SLA to respond to NPS-flagged deals within the forecast lock window, then the NPS-CS gate becomes a manual workflow rather than an automated rule, and the agent cannot prevent the 3–5 renewal misses per quarter that the customer expects it to prevent.

## Captured topics + facts

### `desired_outcome`
- **[stated]** Sales pipeline analyst agent that lets RevOps, sales leadership, and CFO query pipeline state in plain language—'where is coverage thin in EMEA strategic next quarter,' 'what's our real Q4 commit,' 'which deals are likely to slip'—without writing SQL or pinging the analyst. Built on Cortex Analyst, sitting on top of Snowflake sales views.
- **[stated]** CFO / Finance wants recognized revenue with confidence intervals — not point estimates. Wants to see the agent's reasoning, especially when it disagrees with the AE's stated number. Finance trusts transparent uncertainty over confident wrong answers. Example: 'this quarter's forecast is $42M ± $4M with 80% confidence, here's why we're discounting the AE numbers' rather than '$42M' with no caveats.

### `persona`
- **[stated]** Four distinct personas consume pipeline and forecast data: RevOps analysts (need deep slice-and-dice), AE managers (need team coverage broken out by sub-region), VP of Sales (need forecast confidence intervals, not point estimates), and CFO's office (need recognized revenue, not reported ARR). Each persona has views that actively hurt morale or cause compliance issues if shown to the wrong audience.
- **[stated]** Sales Managers need a 'where is my team thin' view broken out by sub-region, with specific AE names and territory risk status tied to their own direct reports only. They want to know which territories are at risk of missing quota. Access must be hierarchy-enforced — if a Sales Manager asks for org-wide worst performer data, the agent refuses and surfaces the reporting-line boundary as the reason.

### `current_pain`
- **[stated_overrides_prior]** Salesforce is the source of truth for opportunities, but it's not the source of reality. What's in Salesforce isn't what's actually closing. Snowflake has cleaned models nightly. We also pull Gong activity and Outreach sequence data.
- **[stated]** About 8% of 'new logo' deals in Salesforce are actually expansions or renewals recoded as new business because AEs get higher commission on new logo vs expansion. The agent needs to cross-check parent account ID + customer-since date to catch the recoding.

### `forecast_inflation_pattern`
- **[stated]** Q4 stage-3 deals run about 30% inflated because AEs push deals out to look better at end-of-Q3 QBR; this adjustment is modeled into internal conservative forecast by Sales Strategy
- **[stated]** When an AE marks a deal 'high confidence' two weeks before end of quarter, the deal almost always does NOT close. Real high-confidence happens 4-6 weeks out. Close rate by 'days from EOQ when high-confidence flag was set' shows a U-shaped curve. This pattern repeats every quarter.
- **[stated]** After Q3 miss, ran manual analysis and identified 14 distinct predictable patterns. 8 already mentioned today. 6 smaller patterns: deals with primary contact changes in last 30 days have unreliable close dates; multi-product deals close at higher win rates than single-product but have longer cycles by 18 days on average.

### `signal_interpretation`
- **[stated]** Staleness is stage-dependent. A discovery-stage deal at 21 days is healthy exploration; a negotiation-stage deal at 21 days is dead. Current data model treats them identically but business reality is opposite. Every quarter someone asks for 'stale deals' and the question is unanswerable without stage context.

### `forecast_confidence`
- **[stated]** If any director-or-above has logged a call or email on a deal in the last 14 days, set close-date confidence to zero for those 14 days. Manager intervention signals the deal is being saved or killed; the AE's listed close date is meaningless during that window.
- **[stated]** Any deal with someone whose title contains 'Procurement,' 'Sourcing,' 'Vendor Management,' or 'Commercial Operations' in the buying committee will slip at least one quarter beyond the AE's predicted close date. 70% slip rate on procurement-involved deals at average $1.2M ARR. Contact roles in Salesforce capture this signal.
- **[stated]** On the procurement signal pattern — confident it exists but medium-high confidence on the exact 70% slip rate magnitude. Observed across maybe 200 deals. Should track with the agent in production and update the magnitude as we get more data.

### `escalation_rule`
- **[stated_overrides_prior]** Procurement-involved deals have a 70% slip rate of at least one quarter, but the exact discount formula applied to these deals is maintained in a spreadsheet by Lisa and not known in closed form by this respondent.
- **[stated]** Never show individual-rep performance comparisons in views shared outside that rep's direct reporting line. Per-rep analysis is allowed for the rep's own manager only. Comparative views must be gated by reporting hierarchy. This is non-negotiable due to HR and legal risk — two incidents in past 18 months (one lawyer letter, two AEs departed).
- **[stated]** Mid-Market pipeline coverage should be 3.5x forecast minimum; Strategic should be 5x minimum due to larger deal sizes and higher slip rates. Below these thresholds, auto-flag with 'coverage gap in segment X' prompt. Above 8x in either segment also flags — indicates stale unqualified deals. Both lower and upper bounds trigger escalation.
- **[stated]** If a deal $500K+ in ARR slips two quarters in a row, alert goes to both the AE's direct manager AND the CFO's office, not just RevOps. For Tier-1 strategic accounts, the EBR lead sees forecast changes before the AE does.
- **[stated]** Renewal deals where customer NPS in past 90 days is under 30 should auto-flag for Customer Success handoff before forecasting. Renewal status is suspect until CS weighs in. This is a hard rule not enforced today because NPS lives in Gainsight and is not connected to Salesforce.

Superseded:
  - [was stated] Strategic accounts inflate quarterly (especially Q3 and Q4), Mid-Market accounts inflate monthly. When pipeline reports collapse both into a single 'overall pipeline' view, the different rhythms get obscured and inflation patterns become invisible to decision-makers.

### `risk`
- **[stated]** Agent reports inflated Q4 number with confidence to CFO for board guidance without understanding Q4 inflation patterns, procurement slips, or manager-intervention signals — CFO uses it and we're wrong at scale. Raw Salesforce number reported as fact when it shouldn't be trusted.

### `data_governance`
- **[stated]** EU deals have stricter data restrictions: no cross-region data sharing, no individual-name disclosures in summaries shared with non-EU consumers. Use the `region` field in Salesforce as a gate before generating any summary or recommendation. If a US-based CFO requests 'show me the top 10 deals in EMEA,' return aggregates only or refuse based on the asker's clearance.
- **[stated]** AEs see only their own pipeline, stage progression, and suggested next moves on their dashboard. They never see peer rankings, peer win rates, or comparative views with other AEs. Comparative analysis stays one layer up with managers.

### `arr_definition`
- **[stated]** Reported ARR is what the AE stated at deal close (in Salesforce amount field). Recognized revenue is what Finance can collect this quarter after ramps, billing cadences, and channel splits. They diverge 8-15% on multi-year deals, up to 25% on multi-year multi-product deals with channel involvement. CFO wants recognized revenue; AEs report stated ARR. Agent must pick a side and be explicit about which.
- **[stated]** Year-1 ARR is what hits THIS year's number. Year-2 and Year-3 commitments are pipeline for FUTURE quarters. Don't take Salesforce TCV at face value—it conflates committed future revenue with current bookings. Disaggregate by year using the join of opportunity to revenue_schedule.
- **[stated]** Channel partners account for about 22% of deals and are co-sold. Reported ARR in Salesforce is the AE's number, but recognized revenue is split with the channel — typically 70/30 or 80/20 depending on partner tier. Channel_partner boolean in Salesforce is about 85% correct. Booking-vs-revenue gap can be 20-30% on channel deals alone.

### `revenue_definition_governance`
- **[stated]** Default to recognized revenue for CFO, finance, or board reporting audiences. Default to reported ARR for AE-facing dashboards, incentive comp, or sales contests. Surface a 'this is the AE number, finance shows X' note when the two diverge by more than 10%.

### `success_metric`
- **[stated]** VP of Sales measures success by forecast confidence intervals refreshed weekly (not daily). Weekly cadence reduces noise and anxiety. Also needs week-over-week movement broken out by quarter (this quarter, next quarter, two quarters out) — not by total. Movement to current quarter vs. future quarters are read as different signals.
- **[stated]** Forecast accuracy improvement from 78% to 87% by shipping v1 with 6 of 14 patterns nailed and audience-aware metric defaults right. CFO considers that a win; diminishing returns after 6 patterns.

### `anti_goal`
- **[stated]** Never let the dashboard read Salesforce as gospel without catching the patterns that make forecasts wrong every quarter: procurement deals that slip two quarters but stay claimed as committed, Strategic deals killed after a manager logs a call, and expansion plays double-booked under different account IDs. The agent should make those visibility gaps impossible — surface the data lens that shows why $18M became $11M, not just report the number.

### `forecast_confidence_threshold`
- **[stated]** When the agent's uncertainty exceeds 20% of the headline forecast, refuse to give a single point estimate. Instead, show a range with named drivers of uncertainty. Don't pretend to know things you don't.

### `audit_trail_requirement`
- **[stated]** When the agent surfaces a recommended discount, it must show its work: which patterns triggered the discount, which deals were affected, what the magnitude was per deal. Finance won't trust a black-box number. If a board member asks 'why did we miss by $4M,' the agent's audit trail has to be auditable end-to-end.

### `tool_evaluation`
- **[stated]** Evaluated Clari, Gong Forecast, and internal prototype last year. Clari treats Salesforce as ground truth so inflation issues come through; good at AI-driven forecasting but misses patterns. Gong strong on activity analytics but doesn't connect activity patterns to forecast adjustments. Internal prototype encoded 2 of 14 patterns, not extensible. All three missed the patterns discussed in conversation.

### `agent_readiness_test`
- **[stated]** Five test questions the agent should answer on day one with traceable reasoning: (1) 'What's our real Q4 commit, accounting for the patterns we talked about?' (2) 'Show me deals where management intervention happened in the last two weeks.' (3) 'Which Strategic accounts have procurement-involved deals slipping?' (4) 'What's our actual coverage by sub-region if we discount the inflation appropriately?' (5) 'How does our recognized revenue forecast differ from reported ARR this quarter?' If the agent answers those five with traceable reasoning, it ships.

### `output_format_preference`
- **[stated]** Default to surfacing reasoning before conclusion. Format: 'Here's what I'm seeing: pattern A, pattern B, pattern C. Based on those, my recommended discount is $X. Here's the underlying data.' Not 'forecast is $42M' as the headline. Reasoning-first lets me catch when analysis is wrong; conclusion-first hides errors.

### `forecast_lock_workflow`
- **[stated]** Weekly forecast lock with Finance every Monday afternoon. Lisa and the RevOps analyst sit with the CFO's deputy and lock in the quarterly forecast number for that week. The agent should generate the candidate forecast number with reasoning, let the team interrogate it, then the human-confirmed number gets locked. The agent's number is the starting point, not the final answer.
- **[stated]** In the last 5 business days of a quarter, the agent should not make stage-progression recommendations, suggest deals might still close, or surface coverage gap alerts to AEs. The last week is for execution, not agent helpfulness, because there's already enough pressure to fudge data.

### `pattern_library_configuration`
- **[stated]** The 14 patterns live in a Google Doc that Lisa and the customer maintain. The agent's pattern library should be loadable from that doc so patterns can be updated without redeploying the agent. Patterns evolve as the business changes.

### `weekly_digest_delivery_format`
- **[stated]** Agent should produce a weekly digest for Monday morning before forecast lock. Include: what's changed since last week, deals where patterns have triggered new signals, gap between AE-reported and agent-recommended forecast. Push notification, not pull — if I have to query the agent every week, it won't change my workflow.

### `spec_completeness_standard`
- **[stated]** Discovery success means the builder ships v1 without follow-up questions. The spec must capture unwritten patterns not in the Salesforce schema: Q4 inflation, procurement signal, manager intervention, renewal masquerade, rep-comparison anti-goal, contract-vs-cash gap. Anything obvious from the schema, the builder figures out themselves.

## Flagged gaps for FDE follow-up

- **That's a concrete, measurable predictor — procurement involvement = 70% slip rate, one-quarter minimum. The agent can pull contact roles from Salesforce and flag deals accordingly.

**Quick clarification: when you say "slip at least one quarter," do you mean the deal closes one quarter later than the AE predicted, or one quarter later than the original close date in Salesforce?** Because if an AE predicted close in Q4 and it actually closes in Q1, that's different from a deal that was originally Q3, slipped to Q4, then slipped again to Q1.

And **does that 70% slip rate hold across all segments — Strategic, Mid-Market, SMB — or is it segment-specific?** (rationale required at the Lisa level)**
  - Why it matters: This question came up but the current counterparty can't answer it; needs escalation to Lisa.
  - Related topic: `escalation_rule`

---

*Generated by discovery-inception v0.7 (lazy synthesis + deterministic close-out).*