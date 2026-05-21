# Skills v2 — derived from oriented RoleContext

**Status:** design only — for the P&G F&HC agent-building exercise.
**Provenance:** every skill traces back to specific entries in [`context.json`](./context.json) (the oriented RoleContext produced by the priors agent).
**Comparison arm:** sits alongside Skills v1 (manual derivation from raw Gong transcript + Excalidraw) for empirical evaluation.

---

## The cut: 4 skills + an orchestrator-level concern

| # | Skill | Purpose | Data source |
|---|---|---|---|
| 1 | `question_parser` | Parse natural-language question into structured query | Atlan metadata (market defs, brand hierarchies) + brand config |
| 2 | `market_share_analyzer` | "What happened" — quantify the share shift at chosen granularities | AOS (Databricks/BigQuery) |
| 3 | `root_cause_analyzer` | "Why it happened" — identify drivers (price, distribution, shelf, display) | Trade Panel, Decon, HHP (Databricks/BigQuery) |
| 4 | `narrative_report` | Compose findings into executive HTML in P&G analyst voice | None (synthesizer) |
| — | *Analysis Path Routing* | **Orchestrator-level** — decides which skills to call and in what order based on findings | n/a — agent loop concern |

This is 1 skill finer than Bala's 3-skill cut (`market_share`, `root_cause`, `report`). The added skill is `question_parser`, which is justified empirically below.

---

## Per-skill specification with RoleContext provenance

### 1. `question_parser`

**Purpose:** Take a raw natural-language question (e.g. *"Why did Gain lose share at Target?"*) and produce a structured query object the downstream skills can act on. Owns the ambiguity-resolution step.

**Inputs:**
- `question` (string)

**Outputs:**
```
{
  "brand": "Gain",
  "market_def_candidates": ["Total Target", "DCOM Target", "In-Store Target"],
  "market_def_resolved": "Total Target" | null,     # null when ambiguous; caller asks for clarification
  "ambiguity_flags": ["channel"],                    # what's still unresolved
  "time_context": "last 13 weeks" | null,
  "granularity_hint": "brand" | "sub-brand" | "form/size",
  "channel_hint": "online" | "in-store" | null
}
```

**Owns decisions from RoleContext:**
- Decision #1: Market Selection (`is_judgment: False` — rule-based)

**Provenance — this skill exists because:**
- `typical_workflows[0].steps[0]` — "Parse the question to extract brand, retailer/market, and time context"
- Decision criterion *Market Selection* with explicit rules:
  > *"If question mentions 'online' or 'digital', select DCOM market variant"*
  > *"Default to 'Total [Retailer]' if no channel specified"*
- Gap #12 (Question Parsing Ambiguity Resolution) — "Target could map to five different market definitions"
- Vocabulary terms: `Market Definition`, `DCOM`, `AOS`

**Why split from `market_share_analyzer`** (vs Bala's cut, where this is implicit):
The RoleContext surfaces Market Selection as a *judgment-loaded* decision with named ambiguity cases. Separating it makes the ambiguity-handling testable in isolation and lets the orchestrator decide whether to ask the user for clarification vs run dual-path analysis (gap #12).

**Atlan integration:** This skill reads Atlan metadata to resolve market definitions (which `Total Target` table corresponds to "Target") and brand hierarchies (which granularities are valid for which brands).

---

### 2. `market_share_analyzer`

**Purpose:** Run "what happened" — query AOS to compute weekly brand share at the chosen granularity levels. Identify the signal week. Quantify the shift and where it went (competitor gainers).

**Inputs:** structured query from `question_parser`

**Outputs:**
```
{
  "granularities_analyzed": ["category", "category-manufacturer", "category-manufacturer-brand"],
  "signal_week": "2026-W14",
  "share_trend": [...],                  # weekly time series per granularity
  "magnitude_of_shift": -2.3,            # share points
  "competitor_gainers": [{"name": "Persil", "shift": +1.8}, ...],
  "above_the_line_context": {...},       # category + retailer trends
  "below_the_line_context": {...}        # brand-specific moves
}
```

**Owns decisions from RoleContext:**
- Decision #2: Product Granularity Selection (`is_judgment: True`)

**Provenance — this skill exists because:**
- `typical_workflows[0].steps[1]` — "Run market share analysis at multiple granularities (category, category-manufacturer, category-manufacturer-brand)"
- `typical_workflows[0].steps[2]` — "Analyze above-the-line and below-the-line context"
- Decision criterion *Product Granularity Selection*:
  > *"For Gain: do not use sub-brand attribute (not available)"*
  > *"For Tide: use sub-brand attribute when relevant"*
- `primary_outcomes[0]` — "Diagnose why a brand's market share increased or decreased at a specific retailer or market"
- Gaps that constrain its design: #5 (brand-specific ordering), #6 (above/below-the-line triggers), #7 (multi-granularity stopping)
- Vocabulary terms: `AOS`, `Granularity`, `Market Share Analysis`, `Category Manufacturer`

**Output structure mirrors Bala's `market_share_skill`** — but with explicit above/below-the-line decomposition because the RoleContext surfaced that as a distinct concern.

**Atlan integration:** Uses Atlan-managed table definitions for `AOS` and Atlan vocabulary for brand product hierarchies.

---

### 3. `root_cause_analyzer`

**Purpose:** Run "why it happened" — given the share shift, query diagnostic data sources (Trade Panel, Decon, HHP) to identify drivers across price, distribution, shelf, display.

**Inputs:** market share findings from `market_share_analyzer` + question context

**Outputs:**
```
{
  "drivers": [
    {"category": "distribution", "metric": "ACV %", "change": -3.1, "interpretation": "..."},
    {"category": "price", "metric": "avg unit price", "change": +0.45, "interpretation": "..."},
    {"category": "shelf", ...},
    ...
  ],
  "business_view_used": "VBB" | "DCOM" | "<brand-specific>",
  "data_sources_queried": ["Trade Panel", "Decon"],
  "metric_lineage_traversed": [...]   # which metrics were chased upstream
}
```

**Owns decisions from RoleContext:**
- Decision #3: Business View Selection (`is_judgment: True`)
- Decision #4: Diagnostic Data Source Selection (`is_judgment: True`)

**Provenance — this skill exists because:**
- `typical_workflows[0].steps[3]` — "Select appropriate business view (VBB, DCOM, or brand-specific)"
- `typical_workflows[0].steps[4]` — "Query Trade Panel, Decon, or other diagnostic data sources to identify root causes"
- Decision criteria *Business View Selection* and *Diagnostic Data Source Selection*
- Vocabulary terms: `Decon`, `DCOM`, `VBB`, `Diagnostic Data Source`, `Metric Lineage`, `DPSM`, `HHP`
- Gaps that constrain its design: #4 (metric lineage depth), #8 (data source selection rules), #11 (central vs OU ownership), #18 (conflicting metrics)

**Maps cleanly to Bala's `root_cause_skill`** but is more explicit about owning the data-source-routing decisions.

**Atlan integration:** Uses Atlan's metric lineage to traverse from high-level metrics (ACV) down to root causes (distribution points, price rotations). This is the most Atlan-dependent skill — it can't function without the lineage graph.

---

### 4. `narrative_report`

**Purpose:** Compose findings from skills 2 and 3 into an executive-ready HTML report in P&G analyst voice.

**Inputs:** market share findings + root cause findings + original question

**Outputs:**
- HTML report with sections:
  - Executive Summary
  - Market Context (above-the-line)
  - Brand Performance (below-the-line)
  - Root Cause Analysis
  - Recommendations (scope TBD — see gap #14)

**Owns no RoleContext-named decisions** but owns voice + structure.

**Provenance — this skill exists because:**
- `typical_workflows[0].steps[5]` — "Generate HTML narrative report with findings and recommendations"
- `primary_outcomes[1]` — "Produce executive-ready narrative reports"
- Unwritten rule #5: *"ensure the voice and language match how that organization's analysts would naturally speak about the business, not generic analytical language"*
- Gaps that constrain its design: #3 (P&G voice definition), #13 (report sections + order), #14 (recommendation scope), #15 (persona-specific variations)

**Maps cleanly to Bala's `report_skill`.**

**Atlan integration:** None directly — synthesizer skill.

---

## The orchestrator-level concern: Analysis Path Routing

**Why this isn't a skill:**

The RoleContext's 5th decision criterion is *Analysis Path Routing*:

> *"Not all questions follow a linear path. Some questions require analyzing multiple product granularities in parallel. Some require above-the-line (market context) and below-the-line (brand-specific) analysis. Agent should navigate dynamically based on insights from each step, not execute all 16 AOS queries by default."*

This is **architectural**, not a skill. The agent's main loop (whatever architecture we pick — single-agent ReAct, chained pipeline, or adversarial-decomposed) is what decides:
- When to call `market_share_analyzer` once vs at multiple granularities
- When to skip directly from `market_share_analyzer` → `narrative_report` (e.g., for purely descriptive questions)
- When to loop back into `root_cause_analyzer` with additional granularity hints if the initial pass was inconclusive

In the bake-off (3 architectures × same skills), this routing concern is **what materially differs between architectures** — sequential chain has no routing, single-agent ReAct does dynamic routing, planning-first does upfront routing. That's the architectural variable to test, holding skills constant.

---

## Comparison vs Bala's 3-skill cut

| | Bala (v0) | v2 (this) |
|---|---|---|
| Skill count | 3 | 4 |
| Provenance per skill | Implicit (from intuition) | Explicit (RoleContext entries cited) |
| Question parsing | Bundled into `market_share_skill` | Separate `question_parser` — owns ambiguity flagging |
| Routing decisions | Live inside skills | Routing extracted to orchestrator level |
| Empirical anchor | LLM-as-judge score (~20→97/100) | Same eval + traceability to source artifact |

**Whether v2 outperforms Bala's cut is the open question.** It might:
- Win on traceability (every skill defends itself against the RoleContext)
- Win on ambiguity handling (gap #12 cases handled explicitly)
- Lose on simplicity (4 skills + orchestrator routing has more moving parts than 3 skills)
- Be a wash on output quality (LLM-as-judge probably can't distinguish)

The empirical comparison is the bake-off step. **If v2 doesn't win on LLM-as-judge score, the defensible claim is "v2 is more traceable, not necessarily more accurate"** — which is still useful for maintenance and audit, but not a quality claim.

---

## Open design questions (filtered from the 21 flagged gaps)

These gaps directly affect skill design and need answers before implementation:

| Gap | Affects which skill | Decision needed |
|---|---|---|
| #3 P&G voice | `narrative_report` | Need example reports — sample inputs to anchor voice |
| #4 Metric lineage depth | `root_cause_analyzer` | How many levels to traverse? |
| #5 Brand-specific ordering | `root_cause_analyzer` | Investigation order for Gain vs Tide? |
| #6 Above/below-the-line triggers | `market_share_analyzer` | When to run both? |
| #7 Multi-granularity stopping | `market_share_analyzer` | When to stop drilling? |
| #8 Diagnostic source selection | `root_cause_analyzer` | What question patterns → which source? |
| #12 Question ambiguity resolution | `question_parser` | Ask user, default, or dual-path? |
| #13 Report sections | `narrative_report` | Required sections in order? |
| #14 Recommendation scope | `narrative_report` | Findings only, or actionable recs? |
| #19 OU naming conventions | `question_parser` + `market_share_analyzer` | Where do mappings live? |
| #20 Confidence thresholds | `root_cause_analyzer` + `narrative_report` | What's the minimum confidence to include a finding? |

For the exercise, these get resolved via:
1. **Synthetic data assumptions** — we make defensible defaults and document them
2. **Discovery follow-up** — these are the probes the discovery agent would ask in a live customer interview to fill the gaps (which is exactly what the gap_reporter prompt was designed to produce)

---

## Where v2 differs structurally from v1 (planned)

The v1 baseline (manual derivation from raw artifacts, no RoleContext) is the comparison arm. Expected differences:

| Dimension | v1 (manual) | v2 (from RoleContext) |
|---|---|---|
| Skill count | Likely 3 (matches Bala) | 4 |
| `question_parser` | Probably absent (folded into market_share) | Present (justified by decision criteria + gap #12) |
| Ambiguity handling | Inferred from transcript | Explicit (gap #12 surfaced it) |
| Voice / output spec | Inferred | Constrained by gaps #3, #13, #14 |
| Traceability | "I read the transcript" | Every skill cites RoleContext entries |
| Open questions | Implicit, in head | 21 explicitly flagged with probe suggestions |

The empirical hypothesis: **v2 will be approximately the same quality as v1, but materially more defensible.** Bala's v0 score was 97/100. v2 might be 95-98 on the same eval. The real win is "we can show our work and the reasoning is traceable."

If v2 IS materially better on LLM-as-judge, that's a stronger claim — but it's also possible that the score differences are within noise.

---

## Next steps

1. Decide synthetic-data scope (which brand, which retailer, which time window) — needs separate decision; affects all 4 skills
2. Write SKILL.md files for each of the 4 skills + a manifest
3. Build v1 (manual cut) as the comparison arm
4. Generate ~15 P&G-shaped questions as the eval set
5. Build the 3 architectures on top of v2 skills (per the architecture-bake-off plan)
6. Run LLM-as-judge across the matrix
7. Report
