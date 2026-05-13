# Discovery spec: we want an early-warning renewal-risk agent for our CSM team at FinCo — surfaces at-risk accounts 60-90 days before renewal so CSMs can intervene

**Session:** `sess_8975c7bb39ab`
**Role priors:** `csm-finco-demo`
**Phase at close:** `drilling`
**Working theory confidence:** `medium`

## Working theory

> A tiered escalation dashboard that surfaces at-risk accounts to CSMs 60-90 days pre-renewal, auto-escalates unacknowledged reds to CSM Manager at 48h, and rolls up team/company trends to leadership — with AE notification on commercial-trigger accounts.

**Alternative framings the data could also support:**
- Passive monitor + alert system — agent watches signals, flags accounts, CSM decides if/when to act; escalations are automatic but intervention is entirely CSM-owned
- Active orchestrator — agent not only flags but suggests next steps (QBR scheduling, renewal conversation talking points, expansion hooks) and tracks CSM response; escalations are both automatic and conditional on CSM inaction
- Workflow executor for escalation only — agent handles the mechanical escalation (routing to CSM Manager, VP, AE) but does not suggest or track CSM interventions; CSM still owns the renewal motion itself

**Open questions that would sharpen this theory:**
- When a CSM sees a red flag on an account, does the agent suggest specific next actions (e.g., 'schedule QBR,' 'pull usage report,' 'loop in AE on expansion'), or does the CSM decide the intervention independently?
- For the 48-hour escalation to CSM Manager, what does 'unacknowledged' mean — the CSM hasn't clicked/viewed the flag, or the CSM hasn't updated the account status or intervention plan?
- Do you want the agent to surface leading indicators (e.g., 'technical sponsor departed,' 'usage down 30%') as separate signals, or only as a composite 'at-risk' score that triggers the flag?

**Sharpest disconfirmer** (what would prove this theory wrong):

> If the CSM tells us they want the agent to execute the renewal conversation itself (e.g., draft talking points, run the call, log outcomes) rather than just flag and escalate, the theory shifts from 'escalation coordinator' to 'renewal workflow executor' — a fundamentally different product.

## Captured topics + facts

### `renewal_risk_escalation`
- **[stated]** 8 enterprise accounts churned last year because CSM didn't flag them as at-risk until the last 30 days. Goal: catch renewal risk 60-90 days early instead of 30 days.

### `leading_indicators`
- **[stated]** Technical sponsor departure in prior 90 days, executive sponsor engagement dropped to zero (no email response, no QBR attendance), product usage off 30-50% from peak, support tickets shifted from feature-request to frustration tone, procurement asking unusual payment questions. At least 3 of these 5 signals present on all 8 churned accounts. None were aggregated anywhere.

### `current_pain`
- **[stated]** Data exists in 4 different systems (Salesforce, data warehouse, Zendesk, NetSuite) but CSM has no workflow that aggregates it. Nobody was looking at the cross-system pattern — everyone was looking at their slice.

### `escalation_rule`
- **[stated]** No calibrated rubric yet. Hypothesis: exec sponsor disengagement + technical sponsor turnover is the highest-signal combo based on worst churn cases observed. Want the agent to learn from outcomes over time rather than pre-defining thresholds.
- **[stated]** Flag account red if 2+ of 5 signals are red AND less than 120 days to renewal. Flag yellow if tech sponsor change OR exec disengagement alone within 60 days of renewal. Agent surfaces both; CSM decides action.
- **[stated]** Support sentiment analysis is not planned for v1. Ship without it; add later. The other 4 signals are high-signal; support sentiment is nuance-tier.
- **[stated]** CSM has a dashboard view of their book of business. At-risk accounts are at the top with status (red/yellow), days to renewal, and the specific signals that triggered the flag. When an account moves to red, the CSM has 48 hours to acknowledge and propose an intervention plan in a structured form. If they don't acknowledge in 48 hours, it auto-escalates to their manager AND the AE on that account. If account stays red for 14 days without progress against the plan, exec sponsor (FinCo VP CS) gets pulled in. CSM owns the relationship throughout — the agent surfaces, it doesn't act.

### `signal_data_source`
- **[stated]** Technical sponsor departure: 'Primary Technical Contact' field on Account record in Salesforce, updated by rep. Exec sponsor disengagement: derived from no exec emails in 60 days + no QBR attendance in last cycle. Usage: warehouse. Support sentiment: requires sentiment analysis on Zendesk tickets (not currently available). Procurement signals: Gong call transcripts.

### `intervention_types`
- **[stated]** Standardize intervention plans with a menu of types: schedule exec sponsor call, deploy a SoCo for technical re-engagement, launch a usage push, escalate to AE for commercial conversation, or other (free text). Each logged with date and outcome for correlation analysis.

### `success_metric`
- **[stated]** Headline metric: fewer than 2 accounts churn per year where the CSM didn't flag them at-risk 60+ days early. Also tracking: percentage of red flags acknowledged in <48 hours (process compliance), percentage of red accounts moved back to green within 30 days (intervention efficacy), and leading indicator of churns that were 'agent surfaced 60+ days out and CSM did something' vs 'agent surfaced and CSM ignored' to identify whether surfacing is working and whether CSM follow-through is the bottleneck.

### `anti_goal`
- **[stated]** Agent should NOT message the customer directly. It should NOT auto-downgrade or upgrade plans. It should NOT make commercial commitments. It should NOT communicate risk to the customer in any form — that's CSM judgment.

### `persona`
- **[stated]** Three personas use the agent: (1) CSM — primary user, has their book of business view, gets red/yellow flags, owns the intervention plan and the customer relationship. (2) CSM Manager — sees their team's at-risk accounts in aggregate, gets escalations after 48 hours of un-acknowledged red. (3) VP Customer Success — sees company-wide rollup with trend lines, gets pulled in on 14-day stuck-red accounts. Plus AE involvement on a per-account basis when commercial conversations are needed but not in the agent UI directly — they get Slack pings or similar.

---

*Generated by discovery-inception v0.7 (lazy synthesis + deterministic close-out).*