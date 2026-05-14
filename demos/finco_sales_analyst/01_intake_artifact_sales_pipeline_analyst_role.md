# Sales Pipeline Analyst — Role Definition

## Purpose

The Sales Pipeline Analyst provides reporting, forecasting, and analytical support for the Revenue Operations team at TechCo. The role serves as the analytical backbone for sales leadership, ensuring data-driven decision making across the sales organization.

## Reporting line

Reports to the Senior Director of Revenue Operations, with dotted-line accountability to the VP of Sales and the CFO's office for forecast quality.

## Key responsibilities

- **Pipeline reporting:** Produce weekly, monthly, and quarterly pipeline reports for sales leadership. Maintain dashboards in Tableau and Snowflake covering pipeline coverage, win rate, average deal size, sales cycle length, and ramp metrics.
- **Forecasting support:** Partner with Sales Strategy on quarterly forecast preparation. Build and maintain forecasting models that combine bottom-up rep submissions with top-down statistical baselines.
- **Data quality:** Monitor Salesforce data hygiene. Surface issues with deal stage progression, close date integrity, and account assignment.
- **Ad-hoc analysis:** Respond to questions from VPs, Sales Managers, and Finance on deal-level, account-level, and segment-level performance.
- **Operational reviews:** Support QBR preparation by producing the standard deck (pipeline by stage, by segment, by region) and answering follow-up questions from execs during reviews.
- **System administration:** Maintain Salesforce report templates, Snowflake views, and forecasting model parameters.

## Tools and data sources

- **Salesforce** — source of truth for opportunities, accounts, contacts, and activities.
- **Snowflake** — cleaned and modeled sales data, refreshed from Salesforce nightly. Includes `OPPORTUNITY`, `ACCOUNT`, `CONTACT`, `OPP_HISTORY`, and `REVENUE_RECOGNITION` tables.
- **Tableau** — primary reporting and dashboard surface.
- **Outreach + Gong** — activity data, integrated into Salesforce.
- **Internal forecasting model** — proprietary, built and maintained by the Sales Strategy team.

## Metrics tracked

- Pipeline coverage (target: 3x forecast)
- Win rate by stage, by segment, by AE
- Average deal size by segment
- Sales cycle length by stage
- Forecast accuracy at start, mid, and end of quarter
- Opportunity stage progression rates

## Key stakeholders

- VP of Sales (forecast accuracy, coverage health)
- CFO / Finance (recognized revenue forecast)
- Sales Managers (team-level coverage and pipeline health)
- Account Executives (deal-level analysis on request)
- Sales Development Reps (lead-to-opp conversion analysis)

## Process expectations

- Weekly pipeline review with Sales Strategy team (Mondays)
- Monthly forecast lock with Finance (last business day of month)
- Quarterly board pack preparation (final 2 weeks of quarter)
- Ad-hoc support window: response within 24h for VP/CFO requests, 48h for managers

## Qualifications

- 3+ years experience in sales operations, revenue operations, or financial planning at a B2B SaaS company
- Strong SQL skills, proficiency in Tableau or similar BI tools
- Experience with Salesforce reporting and data model
- Familiarity with subscription business model (ARR, MRR, churn, expansion)
- Ability to communicate technical findings to non-technical stakeholders

## Standard tools and frameworks

The role uses industry-standard sales operations frameworks including MEDDIC qualification, pipeline coverage ratios, and stage-weighted forecast methodologies.
