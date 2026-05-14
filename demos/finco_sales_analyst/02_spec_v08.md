# Discovery spec: we want a Sales Pipeline Analyst agent (Cortex Analyst flavor) at TechCo so RevOps, AE managers, VP of Sales, and CFO can ask plain-language questions about pipeline state and trust the answers

**Session:** `sess_483c55604289`
**Role priors:** `sales-pipeline-analyst-techco`
**Phase at close:** `drilling`
**Working theory confidence:** `medium`

## Working theory

> A natural-language agent that answers ad-hoc pipeline and forecast questions from RevOps, AE managers, VP Sales, and CFO by querying Snowflake-modeled Salesforce data, surfacing data quality issues proactively, and escalating variance or anomalies that exceed named thresholds to the right stakeholder.

**Alternative framings the data could also support:**
- Query responder — agent answers plain-language questions about pipeline state (coverage, win rate, cycle length, stage progression) by translating to SQL against Snowflake, returning tables/charts to Tableau or Slack, with no autonomous action or escalation logic
- Analyst copilot — agent answers questions AND proactively monitors for data quality issues and forecast variance, surfacing anomalies to RevOps or leadership via alert/summary, but does not auto-escalate or trigger workflows
- Forecast governance agent — agent answers questions, monitors data quality and variance continuously, auto-escalates when thresholds are breached (e.g., variance >±10%, stage-skip rate >5%), and routes to VP/CFO or manager based on severity and role
- QBR and forecast-cycle orchestrator — agent answers questions, monitors continuously, escalates anomalies, AND drives quarterly forecast preparation workflow (collects bottom-up submissions, compares to top-down baseline, flags discrepancies, coordinates forecast lock approval)

**Open questions that would sharpen this theory:**
- When the agent detects a data quality issue (e.g., 15 deals with backward stage movement, or 8 close-date changes >30 days), does it auto-escalate to RevOps with a summary, or does it wait for a human to query and discover the issue?
- Does the agent participate in the monthly forecast lock workflow (e.g., collecting rep submissions, comparing to statistical baseline, flagging outliers for VP review), or is forecast lock a human-driven process that the agent only reports on after the fact?
- For the 70% procurement-slip rate on $1.2M ARR deals — does the agent need to surface this pattern proactively (e.g., 'procurement deals are slipping 70% this quarter, vs. 15% baseline'), or only when a manager asks 'why are we missing forecast'?

**Sharpest disconfirmer** (what would prove this theory wrong):

> If the customer says the agent should never take autonomous action (no auto-escalation, no workflow triggering, only respond to explicit questions), then the agent is a query responder, not a governance or orchestration agent, and the entire escalation_rule and proactive monitoring logic collapses.

## Captured topics + facts

### `desired_outcome`
- **[stated]** Sales pipeline analyst agent that lets RevOps, sales leadership, and CFO query pipeline state in plain language—'where is coverage thin in EMEA strategic next quarter,' 'what's our real Q4 commit,' 'which deals are likely to slip'—without writing SQL or pinging the analyst. Built on Cortex Analyst, sitting on top of Snowflake sales views.
- **[stated]** Finance wants recognized revenue with confidence intervals, not point estimates. They want to see the agent's reasoning when it disagrees with AE stated numbers. Finance prefers transparent uncertainty over confident wrong answers — e.g., '$42M ± $4M with 80% confidence, here's why we're discounting the AE numbers' rather than a bare '$42M' point estimate.
- **[stated]** If the agent had caught those three patterns in the Q4 example, it would have flagged the dashboard as 'high uncertainty' and recommended a $3M-$5M discount with reasoning. The CFO would have presented a $13-15M forecast with the patterns named explicitly — and we'd have hit the actual number with a known story.

### `persona`
- **[stated]** Four distinct personas consume pipeline and forecast data with different needs: RevOps analysts want deep slice-and-dice capability; AE managers want team coverage broken out by sub-region; VP of Sales wants forecast confidence intervals not point estimates; CFO's office wants recognized revenue not reported ARR. Showing the wrong view to the wrong audience actively hurts morale or causes compliance issues.
- **[stated]** AEs hate seeing peer comparisons. SDRs hate seeing ARR forecasting — they don't care, it's not their job. Sales Managers hate seeing roll-up summaries that don't break out by sub-region because their bonus structure is sub-regional and rolled-up views feel like they obscure their team's wins. CFOs hate seeing reported ARR because it overstates collectibility.

### `data_architecture`
- **[stated]** Salesforce is source of truth for opportunities but not source of reality—what's in Salesforce isn't what's actually closing. Snowflake has cleaned models nightly. Also pull Gong activity and Outreach sequence data. Salesforce alone is misleading.
- **[stated]** Staleness is stage-dependent. A discovery deal at 21 days is healthy; a negotiation deal at 21 days is dead. The data model treats them the same, but business reality is opposite. Every quarter someone asks for 'stale deals' and we have to clarify 'stale how?' before the question is answerable.
- **[stated]** Strategic AEs face quarterly coverage pressure from VP board reviews, so Strategic accounts inflate quarterly (especially Q3 and Q4). Mid-Market AEs face monthly pressure from their manager, so Mid-Market accounts inflate monthly. Same total inflation, different rhythms. Current 'overall pipeline' reports collapse both into one view and obscure the patterns.
- **[stated]** Multi-year deals need disaggregation by year—Year-1 ARR hits current year's number, Year-2 and Year-3 are pipeline for future quarters. TCV field conflates committed future revenue with current bookings. Join opportunity to revenue_schedule table to disaggregate by year. At least two vendor analytics tools made this mistake.
- **[stated]** The agent needs to query Snowflake AND read activity data from Gong (separate schema with different join keys). Gong activity reveals manager-intervention signals that Salesforce alone can't see. Most analyst agents are single-source; this one has to cross schemas to be useful.

### `data_source_rule`
- **[stated_overrides_prior]** Salesforce is the source of truth for opportunities. Gong signals (like manager calls) don't override Salesforce stage—they have to agree for the agent to flag it. Also: distinguish between 'Push' (AE-initiated slippage, usually qualification) and 'Pull' (customer-initiated slippage, usually budget).
- **[stated]** The 14 patterns live in a Google Doc that Lisa and the customer keep updated. The agent's library of patterns to evaluate should be loadable from that doc so patterns can be updated without redeploying the agent. These patterns aren't static; they evolve as the business changes.

Superseded:
  - [was stated] Q4 pipeline numbers from Salesforce run 30% high because AEs push deals to stage 3 at end-of-Q3 QBR. Sales Strategy maintains a 30% downward adjustment in the internal conservative forecast to account for this. For 'what's our Q4 pipeline' queries, use the adjusted number, not raw Salesforce sum.
  - [was stated] The agent must pick between 'Reported ARR' (what the AE stated at deal close, in Salesforce amount field) and 'Recognized revenue' (what Finance can actually collect this quarter after ramps, billing cadences, and channel splits). They diverge 8-15% on multi-year deals on average, up to 25% on multi-year multi-product deals with channel involvement. CFO wants recognized revenue; AEs report stated ARR. The agent must be explicit about which definition it's using.

### `risk`
- **[stated]** When an AE marks a deal 'high confidence' two weeks before end of quarter, the deal is almost always NOT closing. It's a sweat signal — they're trying to convince themselves and their manager. Real high-confidence happens 4-6 weeks out. Close rate by 'days from EOQ when high-confidence flag was set' shows a U-shaped curve. This pattern repeats every quarter and isn't in any playbook.
- **[stated]** About 8% of 'new logo' deals in Salesforce are actually expansions or renewals recoded as new business. AEs have incentive to recode because new logo commission is higher than expansion commission. The risk is undetected in standard pipeline reporting. Detection requires cross-checking parent account ID + customer-since date.
- **[stated]** Agent reports inflated Q4 number with confidence to CFO for board guidance without knowing about Q4 inflation patterns, procurement slips, or manager-intervention signals. Raw Salesforce number reported as fact leads to wrong board guidance. Precedent: analyst was fired three years ago for similar error.
- **[stated]** Dashboard reading Salesforce as gospel misses patterns that repeat every quarter: procurement-involved deals AEs claim will close but slip two quarters; Strategic deals logged as active then killed by month-end; deals miscategorized as new logo when they're expansion under different account IDs. Q3 last year: $18M dashboard forecast, $11M actual close, $7M miss that should have been visible in the data with the right lens. The agent should make this failure mode impossible.

### `close_date_confidence_rule`
- **[stated]** If any director-or-above has logged a call or email on a deal in the last 14 days, set close-date confidence to zero for those 14 days. The AE's listed close date is meaningless during that window. Let the dust settle before re-trusting the AE's number.

### `escalation_rule`
- **[stated]** Any deal with someone whose title contains 'Procurement,' 'Sourcing,' 'Vendor Management,' or 'Commercial Operations' in the buying committee will slip at least one quarter beyond the AE's predicted close date. 70% slip rate on procurement-involved deals at average $1.2M ARR.
- **[stated]** The exact discount formula for procurement-involved deals is maintained by Lisa in a spreadsheet; the customer knows the pattern exists and rough magnitude but not the closed-form math.
- **[stated]** If a deal $500K+ in ARR slips two quarters in a row, alert goes to BOTH the AE's direct manager AND the CFO's office, not just RevOps. For Tier-1 strategic accounts, the EBR lead sees forecast changes BEFORE the AE does.
- **[stated]** Renewal deals where customer NPS in past 90 days is under 30 should auto-flag for Customer Success handoff before forecasting. Renewal status is suspect until CS weighs in. This is a hard rule not enforced today because NPS lives in Gainsight and hasn't been connected to the forecasting system.
- **[stated]** Sales Managers need hierarchy-based access control. They can see 'where is my team thin' by sub-region with specific AE names, but only for their direct reports. If a manager requests data outside their reporting line (e.g., 'show me the worst performer in the org'), the agent refuses and surfaces the access restriction as the reason.

### `anti_goal`
- **[stated]** NEVER show individual-rep performance comparisons in views shared outside that rep's direct reporting line. Per-rep analysis is allowed FOR the rep's own manager only; comparative views must gate by reporting hierarchy. Two incidents in past 18 months — one lawyer letter, one resulted in two AEs leaving.
- **[stated]** Never auto-update Salesforce fields based on the agent's analysis, even when the agent is right. Audit trail, compliance review, deal-team chain of custody — all break. Recommend; don't execute. Same with auto-sending emails or Slack messages on behalf of an AE. The agent suggests; humans act.
- **[stated]** In the last 5 business days of a quarter, the agent should not make stage-progression recommendations, suggest deals might still close, or surface coverage gap alerts to AEs. The last week is for execution, not agent helpfulness, because there's already enough pressure to fudge data.

### `data_governance`
- **[stated]** EU deals have stricter data restrictions: no cross-region data sharing, no individual-name disclosures in summaries shared with non-EU consumers. Use the `region` field in Salesforce as a gate before generating any summary or recommendation. If a US CFO asks 'show me the top 10 deals in EMEA,' return aggregates only or refuse based on the asker's clearance.
- **[stated]** When the agent surfaces a recommended discount, it must show its work: which patterns triggered the discount, which deals were affected, what the magnitude was per deal. Finance won't trust a black-box number. If a board member asks 'why did we miss by $4M,' the agent's audit trail has to be auditable end-to-end.
- **[stated]** Public-sector deals (DOD, federal agencies, state contracts) flagged as `vertical = 'PUBSEC'` in Salesforce require additional filtering before agent surfaces data: strip agency names, classification levels, and contract numbers from non-cleared audiences.

### `revenue_metric_selection_rule`
- **[stated]** Default to recognized revenue for any view that touches the CFO, finance, or board reporting. Default to reported ARR for any view that touches incentive comp, AE-facing dashboards, or sales contests. Surface a 'this is the AE number, finance shows X' note when they diverge by more than 10%.
- **[stated]** Channel partners account for about 22% of deals and are co-sold. Reported ARR in Salesforce is the AE's number, but recognized revenue is split with the channel—typically 70/30 or 80/20 depending on partner tier. The `channel_partner` boolean in Salesforce is about 85% correct. Channel deals alone can create a 20-30% booking-vs-revenue gap.

### `success_metric`
- **[stated]** Mid-Market needs 3.5x forecast for the quarter to be healthy. Strategic needs 5x because deal sizes are bigger and slip rate is higher. Below those thresholds auto-flag and prompt 'coverage gap in segment X.' Above 8x in either segment is also a flag — usually means stale junk that nobody's qualifying out.
- **[stated]** Agent ships when it can answer five test questions with traceable reasoning: 'What's our real Q4 commit, accounting for the patterns we talked about?' 'Show me deals where management intervention happened in the last two weeks.' 'Which Strategic accounts have procurement-involved deals slipping?' 'What's our actual coverage by sub-region if we discount the inflation appropriately?' 'How does our recognized revenue forecast differ from reported ARR this quarter?'
- **[stated]** v1 success = nailing 6 of 14 patterns with audience-aware metric defaults right. Forecast accuracy improvement from current 78% to 87% is the bar for the CFO. Not perfection, just enough improvement that decisions get better.

### `forecast_refresh_cadence`
- **[stated]** Weekly forecast confidence interval updates, not daily. Daily creates noise and anxiety with no action. Also wants week-over-week movement broken out by quarter (this quarter, next quarter, two quarters out) — not total. Movement to current quarter vs. future quarters are different signals read differently.

### `ae_dashboard_scope`
- **[stated]** AEs see only their own pipeline, stage progression, and suggested next moves on open opportunities. Never show peer rankings, peer win rates, or comparative views with other AEs. Comparative analysis stays one layer up with managers.

### `predictable_forecast_miss_patterns`
- **[stated]** After Q3 miss, ran manual analysis and identified 14 distinct predictable patterns. 8 already mentioned today. 6 smaller ones include: deals with primary contact changes in last 30 days have unreliable close dates; multi-product deals close at higher win rates than single-product but have longer cycles by 18 days on average.

### `forecast_range_rule`
- **[stated]** When the agent's uncertainty exceeds 20% of the headline forecast, refuse to give a single point estimate. Instead, show a range with named drivers of uncertainty. Core rule: 'Don't pretend to know things you don't.' Surface what's known and unknown more rigorously than the current dashboard does.

### `current_pain`
- **[stated]** Evaluated Clari, Gong Forecast, and internal prototype last year. Clari treats Salesforce as ground truth so inflation issues come through. Gong is strong on activity analytics but doesn't connect activity patterns to forecast adjustments. Internal prototype encoded 2 of 14 patterns and wasn't extensible. None identified the patterns we need.

### `critical_bug`
- **[stated]** Agent reports raw Salesforce Q4 number with no inflation adjustment. Agent shows rep-by-rep comparison to Director outside reporting line. Agent treats reported ARR as recognized revenue for CFO. Agent recommends auto-closing stale deal without escalation.

### `output_format_preference`
- **[stated]** Default to reasoning-first format: surface patterns and analysis before the conclusion. Structure as 'Here's what I'm seeing: pattern A, pattern B, pattern C. Based on those, my recommended discount is $X. Here's the underlying data.' rather than leading with the headline number like 'forecast is $42M'. Reasoning-first lets the RevOps analyst catch when the analysis is wrong; conclusion-first hides errors.
- **[stated]** Weekly digest pushed Monday morning before forecast lock—what's changed since last week, deals where patterns triggered new signals, gap between AE-reported and agent-recommended forecast. Push notification, not pull; if I have to query the agent every week, it won't change my workflow.

### `forecast_lock_workflow`
- **[stated]** Weekly forecast lock with Finance every Monday afternoon. Lisa and the Sales Pipeline Analyst sit with the CFO's deputy and lock in the quarterly forecast number for that week. The agent should generate the candidate forecast number with reasoning, let us interrogate it, then we lock the human-confirmed number. The agent's number becomes the starting point, not the final answer.

### `data_confidence_magnitude`
- **[stated]** We've observed the procurement signal pattern across maybe 200 deals. Confidence in the 70% slip rate is medium-high, but we don't have a research-grade citation for the exact magnitude. Should track this with the agent in production and update the magnitude as we get more data.

### `discovery_success_criteria`
- **[stated]** Discovery is successful when a builder can ship v1 without coming back with a hundred follow-up questions. The spec must capture the unwritten patterns we discussed — Q4 inflation, procurement signal, manager intervention, renewal masquerade, rep-comparison anti-goal, contract-vs-cash gap. Anything obvious from the Salesforce schema, a builder figures out themselves. Discovery's job is to capture what's NOT in the schema.

## Flagged gaps for FDE follow-up

- **You said 70% slip rate on procurement-involved deals at $1.2M ARR. But earlier you flagged that Strategic AEs inflate quarterly while Mid-Market inflate monthly, and that a deal's staleness depends on its stage. Does that 70% procurement slip rate hold the same way across both AE cohorts and across all stages, or does procurement involvement hit Strategic stage-3 deals differently than it hits Mid-Market discovery deals? (rationale required at the Lisa level)**
  - Why it matters: Question came up but the current counterparty can't answer; needs escalation to Lisa.
  - Related topic: `escalation_rule`

---

*Generated by discovery-inception v0.7 (lazy synthesis + deterministic close-out).*