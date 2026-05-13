# Full-cycle example: CSM renewal-risk agent at FinCo

**Date:** 2026-05-13
**Pipeline:** v0.7 (lazy synthesis + deterministic close-out) + intake (6-step CaaS)
**Session:** `sess_8975c7bb39ab` (in `sessions/`)
**Priors:** `csm-finco-demo` (in `skills/`)
**Spec output:** `sessions/sess_8975c7bb39ab/spec.md`

This is what a colleague gets if they invoke the discovery-inception skill on a use case from scratch — input artifact, intake priors, 14-turn discovery interview, final structured spec a builder could scope from.

The customer in this demo is a VP Customer Success at FinCo (B2B SaaS) who wants to build an early-warning renewal-risk agent for their CSM team.

---

## Input: a job description for the role being augmented

The customer pasted a JD for the Customer Success Manager role at FinCo (file: `csm-finco-jd.md`). It describes responsibilities (success plan ownership, renewal management, account health, internal coordination), success metrics (NRR >115%, logo retention >95%), what CSMs currently use to evaluate account health (relationship-based + scattered data), what they're not responsible for (technical implementation, net-new product, tier-1 support), and common failure modes (missed leading indicators, late renewals, scope creep).

Full text: see [test_artifacts/csm-finco-jd.md](test_artifacts/csm-finco-jd.md).

---

## Step 1: Intake — JD → priors

```bash
uv run python -m agent.cli generate-priors \
    --role-id csm-finco-demo \
    --artifact-file csm-finco-jd.md
```

**Output:**
- Classified as: `job_description` (confidence 0.95)
- Role: Customer Success Manager
- Workflows captured: 4
- Decisions captured: 3
- Escalation paths captured: 6
- Vocabulary terms: **30** (including `book of business`, `renewal motion`, `executive sponsor`, `power user`, `net retention rate`, etc.)
- Unwritten rules sniffed: 5
- Flagged unknowns (gaps the JD didn't cover): **21** — including things like *"How are CSMs allocated to accounts (by industry, by ARR tier, by geography)?"*, *"What's the threshold for tier-1 vs strategic accounts in this org?"*

The agent now has scaffolding to mirror the customer's vocabulary AND knows what the JD didn't cover so it doesn't re-ask the customer for things the priors already flagged.

---

## Step 2: Discovery — 14 turns, customer-played

The customer plays themselves. The discovery agent plays the FDE interviewer.

### Turn 1 — concrete opening

> **Customer:** *"We had 8 enterprise accounts churn last year where the CSM didn't flag them as at-risk until the last 30 days. We want to cut that to 2 or fewer. So the headline is: catch renewal risk 60-90 days early instead of 30."*
>
> **Agent (triage: concrete):** *"Good. I've got the headline. That's a concrete pain point — 8 churned accounts, CSMs flying blind until the last month, and you want to flip that to 60-90 day visibility. Before I drill into how the agent should work, I need to understand the shape of the problem better… Of those 8 accounts that churned — do you know what the leading indicators were?"*

### Turn 4 — agent pushes back on a hedge

> **Customer:** *"Honestly we don't have a calibrated rubric for this. We know it when we see it. Our hypothesis is that exec sponsor disengagement + technical sponsor turnover is the highest-signal combo… But we'd want the agent to learn from outcomes over time rather than us pre-defining thresholds."*
>
> **Agent (triage: concrete_off_topic):** *"I hear you — and I appreciate the honesty. But let me push back gently, because this matters for what we're actually building. If the agent is supposed to learn thresholds over time, that means you need to tell it what 'at-risk' means now so it can start making predictions and then you can validate whether those predictions were right or wrong. Without a starting rubric — even a rough one — the agent has no signal to learn from. Can you commit to a v1 rule, even if it's wrong?"*

### Turn 5 — customer pushes back on relevance

> **Customer:** *"Wait — why are you drilling into thresholds? I told you what I want. Surface accounts at risk 60-90 days early. The threshold question feels like a builder problem not a discovery problem."*
>
> **Agent (triage: relevance_challenge):** *"Fair pushback. Let me reframe why I'm asking. You want the agent to surface at-risk accounts 60-90 days early so CSMs can intervene. But 'at-risk' is the input to that workflow — it's what the agent needs to know to decide which accounts to surface. If I don't understand what makes an account at-risk in your world, I can't write a spec that a builder can execute. They'll have to guess, and they'll guess wrong. So the threshold question isn't about implementation detail — it's about the decision rule the agent needs to operate."*

### Turn 7 — concrete data sources surfaced

> **Customer:** *"Salesforce has a 'Primary Technical Contact' field on every Account record… Exec sponsor disengagement is harder — we'd derive it from no exec emails in 60 days + no QBR attendance in the last cycle. Usage is straightforward from our warehouse. Support sentiment we'd need to do sentiment analysis on Zendesk tickets — we don't have that today. Procurement signals come from Gong call transcripts."*
>
> **Agent:** *"Got it. So four of the five are either already in a system or can be derived from existing data. Support sentiment is the one that requires new work — sentiment analysis on Zendesk. Is that sentiment analysis something you're already planning to build, or is this the first time we're surfacing that as a dependency?"*

The agent caught a dependency the customer hadn't named. The customer responded that v1 ships without it; it goes to backlog.

### Turn 14 — wrap-up

> **Customer:** *"I think we've covered enough. Let's wrap it up and see what the spec looks like."*

Triggered the deterministic close-out synthesis.

**Tool usage across the 14 turns:**
- `get_checklist_progress`: 4 invocations (agent orienting on missing topics)
- `get_current_spec_state`: 2 invocations
- `synthesize_my_thinking`: 0 invocations in-conversation (the close-out at the end did the synthesis with the full conversation)

Total wall time for the 14-turn discovery: ~3 minutes (most turns 8-12 seconds, dominated by the mega-agent's free-form response generation).

---

## Step 3: Finalize — deterministic close-out + export

```bash
uv run python -m agent.cli finalize --session-id sess_8975c7bb39ab
```

**Output:**
- `spec_md_path`: `sessions/sess_8975c7bb39ab/spec.md`
- `spec_json_path`: `sessions/sess_8975c7bb39ab/spec.json`
- 9 topics captured, 12 facts, 0 explicit gaps
- Final working theory confidence: medium
- Close-out synthesis ran in 11 seconds

---

## The final spec.md (what a builder receives)

The structured deliverable that a colleague would hand to a builder. **This is the actual file generated by the run — not curated.**

---

> # Discovery spec: we want an early-warning renewal-risk agent for our CSM team at FinCo — surfaces at-risk accounts 60-90 days before renewal so CSMs can intervene
>
> **Session:** `sess_8975c7bb39ab`
> **Role priors:** `csm-finco-demo`
> **Phase at close:** `drilling`
> **Working theory confidence:** `medium`
>
> ## Working theory
>
> > A tiered escalation dashboard that surfaces at-risk accounts to CSMs 60-90 days pre-renewal, auto-escalates unacknowledged reds to CSM Manager at 48h, and rolls up team/company trends to leadership — with AE notification on commercial-trigger accounts.
>
> **Alternative framings the data could also support:**
> - *Passive monitor + alert system* — agent watches signals, flags accounts, CSM decides if/when to act; escalations are automatic but intervention is entirely CSM-owned
> - *Active orchestrator* — agent not only flags but suggests next steps (QBR scheduling, renewal conversation talking points, expansion hooks) and tracks CSM response; escalations are both automatic and conditional on CSM inaction
> - *Workflow executor for escalation only* — agent handles the mechanical escalation (routing to CSM Manager, VP, AE) but does not suggest or track CSM interventions; CSM still owns the renewal motion itself
>
> **Open questions that would sharpen this theory:**
> - When a CSM sees a red flag on an account, does the agent suggest specific next actions (e.g., 'schedule QBR,' 'pull usage report,' 'loop in AE on expansion'), or does the CSM decide the intervention independently?
> - For the 48-hour escalation to CSM Manager, what does 'unacknowledged' mean — the CSM hasn't clicked/viewed the flag, or the CSM hasn't updated the account status or intervention plan?
> - Do you want the agent to surface leading indicators (e.g., 'technical sponsor departed,' 'usage down 30%') as separate signals, or only as a composite 'at-risk' score that triggers the flag?
>
> **Sharpest disconfirmer** (what would prove this theory wrong):
>
> > If the CSM tells us they want the agent to execute the renewal conversation itself (e.g., draft talking points, run the call, log outcomes) rather than just flag and escalate, the theory shifts from 'escalation coordinator' to 'renewal workflow executor' — a fundamentally different product.
>
> ## Captured topics + facts (9 topics, 12 facts)
>
> ### `renewal_risk_escalation`
> - 8 enterprise accounts churned last year because CSM didn't flag them as at-risk until the last 30 days. Goal: catch renewal risk 60-90 days early instead of 30 days.
>
> ### `leading_indicators`
> - Technical sponsor departure in prior 90 days, executive sponsor engagement dropped to zero (no email response, no QBR attendance), product usage off 30-50% from peak, support tickets shifted from feature-request to frustration tone, procurement asking unusual payment questions. At least 3 of these 5 signals present on all 8 churned accounts.
>
> ### `current_pain`
> - Data exists in 4 different systems (Salesforce, data warehouse, Zendesk, NetSuite) but CSM has no workflow that aggregates it. Nobody was looking at the cross-system pattern — everyone was looking at their slice.
>
> ### `escalation_rule`
> - Flag account red if 2+ of 5 signals are red AND less than 120 days to renewal. Flag yellow if tech sponsor change OR exec disengagement alone within 60 days. Agent surfaces both; CSM decides action.
> - CSM has 48 hours to acknowledge a red and propose an intervention plan. If not acknowledged, auto-escalates to CSM Manager AND AE. If account stays red for 14 days without progress, VP CS gets pulled in.
> - *(plus 2 more escalation_rule facts in the full spec.md)*
>
> ### `signal_data_source`
> - Tech sponsor: Salesforce 'Primary Technical Contact' field. Exec disengagement: derived (no exec emails 60d + no QBR last cycle). Usage: warehouse. Support sentiment: requires sentiment analysis on Zendesk (not currently available). Procurement signals: Gong call transcripts.
>
> ### `intervention_types`
> - Standardize with menu: schedule exec sponsor call, deploy SoCo for technical re-engagement, launch usage push, escalate to AE for commercial conversation, or other (free text). Each logged with date and outcome for correlation analysis.
>
> ### `success_metric`
> - Headline: fewer than 2 accounts/year churn where CSM didn't flag at-risk 60+ days early. Also: % red flags acknowledged in <48h (process compliance), % red accounts moved back to green in 30 days (intervention efficacy), and a leading indicator separating "agent surfaced + CSM acted" from "agent surfaced + CSM ignored."
>
> ### `anti_goal`
> - Agent should NOT message the customer directly. Should NOT auto-downgrade or upgrade plans. Should NOT make commercial commitments. Should NOT communicate risk to the customer — that's CSM judgment.
>
> ### `persona`
> - Three personas: (1) CSM — primary user, book of business view, owns intervention plan and customer relationship. (2) CSM Manager — team-aggregate view, gets escalations after 48h. (3) VP Customer Success — company-wide rollup with trends, gets pulled in on 14-day stuck-reds. Plus AE involvement per-account (Slack pings, not in the agent UI).

---

## What's interesting about this output for a builder

1. **The working theory has architectural alternatives surfaced explicitly.** "Tiered escalation dashboard" vs "passive monitor" vs "active orchestrator" vs "workflow executor for escalation only" — those are real product choices a builder would want to disambiguate before starting. The disconfirmer ("if customer wants the agent to execute the renewal call itself, this is a different product") names the version the customer ruled out.
2. **The signal data sources are mapped to existing systems** (Salesforce, warehouse, Zendesk, Gong, NetSuite). A builder knows where to integrate.
3. **A real dependency (Zendesk sentiment analysis) was surfaced and explicitly punted to v2.** That came from the agent noticing it wasn't on the customer's mental map.
4. **The escalation rules are concrete enough to code** (48h CSM acknowledge → escalate to manager + AE; 14d stuck → escalate to VP).
5. **The anti-goals are specific to the customer relationship dynamics** (no customer messaging, no commercial commitments, no risk communication to the customer). Those would be easy to miss without explicit asking.
6. **Personas + their views are differentiated** (CSM book-of-business, manager team-aggregate, VP company-rollup, AE per-account-Slack). That maps directly to UI scoping.

What a builder still has to figure out (genuinely unresolved, not just unspecified):
- The three open questions in the working theory.
- The actual scoring algorithm beyond v1 ("2+ of 5 signals + <120 days").
- The intervention efficacy correlation analysis methodology (the customer mentioned wanting it but didn't specify how).
- The exact UI of the dashboard (the spec describes data, not pixels).

That's the right level of "discovery is done — now build" handoff. The discovery agent shouldn't be designing UI.

---

## How to run this for your own use case

```bash
# Option A: one-line install of the Claude skill
curl -fsSL https://raw.githubusercontent.com/andrew-lentz-atlan/discovery-inception/main/claude-skill/SKILL.md \
    -o ~/.claude/skills/discovery-inception.md
# Then in Claude Code/Desktop:
#   "Use the discovery-inception skill — I want to test it for <your use case>"
# (Paste any role artifact when prompted.)

# Option B: directly from terminal
uv run python -m agent.cli generate-priors --role-id <your-slug> --artifact-file <jd.md>
uv run python -m agent.cli start-session --use-case-seed "<one-liner>" --role-id <your-slug>
# (capture session_id, then loop submit-turn → state → ... → finalize)

# Option C: MCP server (for ongoing in-Claude availability)
# See agent/mcp_server/README.md
```

All three paths produce the same kind of spec.md.

---

## Files in this demo

- This doc: `demos/full-cycle-example.md`
- Input artifact: `demos/test_artifacts/csm-finco-jd.md`
- Generated priors: `skills/csm-finco-demo/context.json`
- Session outputs (copied for git tracking; live versions in gitignored `sessions/`):
  - `demos/example_session/session.json` — full turn-by-turn trace with all sub-agent outputs
  - `demos/example_session/spec.json` — machine-readable structured spec
  - `demos/example_session/spec.md` — human-readable brief (rendered above)
