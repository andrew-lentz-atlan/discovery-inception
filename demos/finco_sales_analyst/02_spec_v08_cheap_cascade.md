# Discovery spec: we want a Sales Pipeline Analyst agent (Cortex Analyst flavor) at TechCo so RevOps, AE managers, VP of Sales, and CFO can ask plain-language questions about pipeline state and trust the answers

**Session:** `sess_f341af4dfaa3`
**Role priors:** `sales-pipeline-analyst-techco`
**Phase at close:** `drilling`
**Working theory confidence:** `low`

## Working theory

> We want a Sales Pipeline Analyst agent that allows RevOps, AE managers, VP of Sales, and CFO to ask plain-language questions about pipeline state and trust the answers.

**Alternative framings the data could also support:**
- workflow executor — the agent autonomously analyzes pipeline data and generates reports based on user queries.
- coordinator — the agent guides users through the process of querying and interpreting pipeline data while they perform the analysis.
- copilot — the agent assists users on demand by providing insights, summaries, and recommendations based on pipeline data.
- customer-facing chatbot — the agent interacts directly with users to answer their questions about pipeline state in real-time.

**Open questions that would sharpen this theory:**
- What specific types of plain-language questions do you envision users asking the agent about the pipeline state?
- Should the agent automatically flag deals for manual review based on risk assessments, or should it simply provide insights for users to act on?
- How do you define trust in the answers provided by the agent, and what metrics would indicate that trust is achieved?

**Sharpest disconfirmer** (what would prove this theory wrong):

> If users report that the agent's answers are frequently inaccurate or untrustworthy, it would indicate a failure in the agent's design.

## Captured topics + facts

### `desired_outcome`
- **[stated]** We want a sales pipeline analyst agent at TechCo. The goal is RevOps, sales leadership, and the CFO can query pipeline state in plain language — 'where is coverage thin in EMEA strategic next quarter,' 'what's our real Q4 commit,' 'which deals are likely to slip' — without writing SQL or pinging me directly.
- **[stated]** CFO / Finance: they want recognized revenue with confidence intervals — not point estimates. They want to see the agent's reasoning, especially when it disagrees with the AE's stated number. Finance trusts transparent uncertainty over confident wrong answers.
- **[stated]** I leave this with a clear enough picture that a builder doesn't have to come back to me with a hundred follow-up questions to ship v1. The unwritten patterns we discussed — the Q4 inflation, the procurement signal, the manager intervention, the renewal masquerade, the rep-comparison anti-goal, the contract-vs-cash gap — those have to be in the spec or the build is starting blind.

### `persona`
- **[stated]** There are four distinct personas: RevOps analysts (want deep slice-and-dice), AE managers (want their team's coverage broken out by sub-region), VP of Sales (wants forecast confidence intervals, not point estimates), and CFO's office (wants recognized revenue, not reported ARR). Each persona has views that actively hurt morale or cause compliance issues if shown to the wrong audience.
- **[stated]** Sales Managers need a 'where is my team thin' view broken out by sub-region. Their bonus is sub-regional, not rolled up. They want to know which territories are at risk of missing quota, with names of specific AEs, but ONLY for their direct reports. The agent has to enforce hierarchy-based access.

### `current_pain`
- **[stated]** Salesforce is the source of truth for opportunities, but it's not the source of reality. What's in Salesforce isn't what's actually closing. The agent needs to know that Salesforce alone is misleading.
- **[stated]** Q4 always has about 30% inflation in stage-3 deals because AEs push deals out to look better at the end-of-Q3 QBR.
- **[stated]** When an AE marks a deal 'high confidence' two weeks before end of quarter, the deal is almost always NOT closing. Real high-confidence happens 4-6 weeks out.
- **[stated]** 'Stale' is a stage-aware concept. A discovery-stage deal sitting 21 days is healthy — that's normal exploration. A negotiation-stage deal sitting 21 days is dead. The data model treats them the same; the business reality is opposite. Every quarter someone asks me 'show me stale deals' and I have to ask 'stale how?' before the question is answerable.
- **[stated]** Account-tier inflation has different cadences. Strategic AEs face quarterly coverage pressure because their VP gets quarterly board reviews. Mid-Market AEs face monthly pressure because their manager gets monthly. So Strategic accounts inflate quarterly (especially Q3 and Q4 of each year), Mid-Market inflates monthly. Same total inflation, different rhythms — and our existing reports collapse them into a single 'overall pipeline' view that obscures the patterns.
- **[stated]** Any deal with someone whose title contains 'Procurement,' 'Sourcing,' 'Vendor Management,' or 'Commercial Operations' in the buying committee will slip at least one quarter beyond the AE's predicted close date. The data is sitting in contact roles in Salesforce. We've measured this — it's about 70% slip rate on procurement-involved deals at average $1.2M ARR.
- **[stated]** About 8% of our 'new logo' deals are actually expansions in disguise based on the last analysis I ran.
- **[stated]** The contract-vs-cash gap: when the agent reports ARR, it has to pick a definition. 'Reported ARR' is what the AE stated at deal close — that's what's in Salesforce's amount field. 'Recognized revenue' is what Finance can actually collect this quarter, after factoring in ramps, billing cadences, and channel splits. They diverge by 8-15% on multi-year deals on average, up to 25% on multi-year multi-product deals with channel involvement. CFO wants the second number; AEs report the first. The agent must pick a side and be explicit about which.
- **[stated]** Multi-year deal handling needs careful treatment. Year-1 ARR is what hits THIS year's number. Year-2 and Year-3 commitments are pipeline for FUTURE quarters. Lots of agents take Salesforce's 'TCV' field at face value, which conflates committed future revenue with current bookings. We've seen this mistake from at least two vendor analytics tools we've evaluated. The agent has to disaggregate by year and the data is there if you join opportunity to revenue_schedule.
- **[stated]** About 22% of our deals are co-sold with channel partners. The booking-vs-revenue gap can be 20-30% on those alone.
- **[stated]** The dashboard was wrong by $7M, which should have been visible. The reasons included two procurement-involved deals that slipped two quarters, three Strategic deals that got killed, and two deals misclassified as 'new logo' that were actually expansions. This failure mode should be made impossible.
- **[stated]** After that Q3 miss we ran a manual analysis project to identify which patterns were predictable from the data. We found about 14 distinct ones — the agent's job is to encode all of them so we don't lose them when people leave.
- **[stated]** We evaluated three vendor tools for this last year — Clari, Gong Forecast, and one internal-build prototype. All three missed the patterns we discussed today. Clari is good at AI-driven forecasting but it treats Salesforce as ground truth, so the inflation issues come through. Gong is great at activity analytics but doesn't connect activity patterns to forecast adjustments. Our internal prototype encoded two of the 14 patterns but wasn't extensible. So we know the bar — and we know what's missing in the market.
- **[stated]** Sub-skill needed: the agent needs to know how to query Snowflake AND how to read activity data from Gong (which is in a separate schema with different join keys).
- **[stated]** If Gong data is stale or unavailable, it impacts the risk assessment and subsequent decisions made by the VP and CFO.
- **[stated]** Deals in the public-sector vertical (DOD, federal agencies, state contracts) have stricter access control and disclosure rules. Anything the agent surfaces for those deals must run through an additional filter that strips agency names, classification levels, and contract numbers from non-cleared audiences.
- **[stated]** The agent's library of 'patterns to evaluate' should be loadable from a Google Doc that Lisa and I keep updated, as these patterns aren't static; they evolve as the business changes.

### `success_metric`
- **[stated]** Manager intervention is a strong signal. If any director-or-above has logged a call or email on a deal in the last 14 days, the deal is either being saved or killed by management. The AE's listed close date is meaningless during that window.
- **[stated]** default to recognized revenue for any view that touches the CFO, finance, or board reporting; default to reported ARR for any view that touches incentive comp, AE-facing dashboards, or sales contests; surface a 'this is the AE number, finance shows X' note when they diverge by more than 10%
- **[stated]** Mid-Market needs 3.5x forecast for the quarter to be healthy. Strategic needs 5x because the deal sizes are bigger and the slip rate is higher. Below those thresholds the agent should auto-flag and prompt 'coverage gap in segment X.' Above 8x in either segment is also a flag — usually means stale junk that nobody's qualifying out.
- **[stated]** VP of Sales specifically: she wants forecast confidence intervals refreshed weekly, not daily. Daily updates create noise and anxiety that she doesn't act on. Weekly is enough. She also wants to see week-over-week movement broken out by quarter (this quarter, next quarter, two quarters out) — not by total.
- **[stated]** If the agent had caught those three patterns in the Q4 example, it would have flagged the dashboard as 'high uncertainty' and recommended a $3M-$5M discount with reasoning.
- **[stated]** When the agent's uncertainty exceeds 20% of the headline forecast, it should refuse to give a single point estimate. Instead, show a range with named drivers of uncertainty. 'Don't pretend to know things you don't' is the core rule.
- **[stated]** when the agent surfaces a recommended discount, it must show its work. Which patterns triggered the discount, which deals were affected, what the magnitude was per deal. Finance won't trust a black-box number. If a board member asks 'why did we miss by $4M,' the agent's audit trail has to be auditable end-to-end.
- **[stated]** If the agent answers those five with traceable reasoning, it ships.
- **[stated]** I want the agent to default to surfacing its reasoning before its conclusion. 'Here's what I'm seeing: pattern A, pattern B, pattern C. Based on those, my recommended discount is $X. Here's the underlying data.'
- **[stated]** The CFO is happy if forecast accuracy goes from current 78% to maybe 87%. That's the bar — not perfection, just enough improvement that decisions get better.

### `escalation_rule`
- **[stated]** the exact discount we apply for procurement-involved deals is in a spreadsheet maintained by Lisa; I can flag this as a gap.
- **[stated]** The agent must use the `region` field in Salesforce as a gate before generating any summary or recommendation. If a CFO in the US asks 'show me the top 10 deals in EMEA,' the agent should either return aggregates only or refuse, depending on the asker's clearance.
- **[stated]** if a deal $500K+ in ARR slips two quarters in a row, the alert should go to BOTH the AE's direct manager AND the CFO's office — not just to RevOps.
- **[stated]** Renewal deals where the customer's NPS in the past 90 days is under 30 should auto-flag for Customer Success handoff BEFORE any forecasting.
- **[stated]** The agent should support the workflow — generate the candidate forecast number with reasoning, let us interrogate it, then we lock the human-confirmed number. The agent's number becomes the starting point, not the final answer.
- **[stated]** the agent should produce a weekly digest for me — 'here's what's changed since last week, here are the deals where the patterns have triggered new signals, here's the gap between AE-reported and agent-recommended forecast.'

### `anti_goal`
- **[stated]** NEVER show individual-rep performance comparisons in views shared outside that rep's direct reporting line. This is HR-protected territory.
- **[stated]** never auto-update Salesforce fields based on the agent's analysis, even when the agent is right. Recommend; don't execute.
- **[stated]** Each of those would be a 'critical bug' — the kind of thing where if it ever happened in production we'd pull the agent.
- **[stated]** In the last 5 business days of a quarter, the agent should not make stage-progression recommendations, suggest that a deal might still close, or surface coverage gap alerts to AEs.

### `persona_specific_must_nots`
- **[stated]** AEs hate seeing peer comparisons. SDRs hate seeing ARR forecasting — they don't care, it's not their job. Sales Managers hate seeing roll-up summaries that don't break out by sub-region because their bonus structure is sub-regional and rolled-up views feel like they obscure their team's wins. CFOs hate seeing reported ARR because it overstates collectibility.

### `risk`
- **[stated]** Biggest risk: agent confidently reports an inflated Q4 number and the CFO uses it for board guidance. We had an analyst get fired three years ago for less. If the agent doesn't know about the Q4 inflation patterns, the procurement slips, the manager-intervention signal — and it reports the raw Salesforce number with confidence — that's exactly the failure mode I'm trying to prevent.

### `next_best_action`
- **[stated]** AEs need 'what's the next-best action on each of my open opportunities.' Pure tactical. The agent should NEVER show them peer rankings, peer win rates, or comparative views with other AEs.

## Flagged gaps for FDE follow-up

- **When you say the slip is predictable, does that mean the agent should adjust the close date automatically, or should it flag these deals for manual review based on the risk assessment? How does that impact the VP's and CFO's decision-making differently? (rationale required at the Lisa level)**
  - Why it matters: Question came up but the current counterparty can't answer; needs escalation to Lisa.
  - Related topic: `escalation_rule`

---

*Generated by discovery-inception v0.7 (lazy synthesis + deterministic close-out).*