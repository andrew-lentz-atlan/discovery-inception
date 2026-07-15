---
title: Inner Pipeline (Multi-LLM-Call Skill)
category: skill-design
status: validated
last_updated: 2026-05-20
source_findings: []
source_external:
  - https://github.com/bladata1990/pg-brand-analyst-agent  (skills/market_share_skill.py)
applies_when:
  workloads: [skill-with-data-source-access, llm-generated-sql-then-interpret, structured-output-from-multi-step-reasoning]
  constraints: [skill-needs-its-own-mini-llm-flow, single-shot-llm-insufficient]
contradicts: []
related: [truncated-data-summary, definitions-without-context, architectures/single-agent-react]
---

# Inner Pipeline (Multi-LLM-Call Skill)

A skill that is itself a small pipeline of LLM calls, not a single call. The skill fetches context, runs an LLM call to generate something structured (often SQL or a plan), executes the structured artifact, validates, and runs a second LLM call to interpret the results. The outer agent (single-agent ReAct loop, typically) sees the skill as a single tool — internally it's a multi-step pipeline doing its own reasoning.

This is how the three skills in the public brand-analytics reference build (https://github.com/bladata1990/pg-brand-analyst-agent) are constructed. Each skill is a mini-pipeline. The outer Anthropic SDK loop is the orchestrator.

## The pattern

```
┌─ skill: market_share_analyzer ────────────────────────────────┐
│                                                                │
│  1. fetch_schema(table)               from Databricks         │
│  2. fetch_metric_definitions          from Atlan glossary      │
│  3. resolve_canonical_entity_values   from Databricks          │
│                                                                │
│  4. LLM call #1 ───→ generate SQL given (schema +              │
│                       metric definitions + canonical values)   │
│                                                                │
│  5. execute_sql(generated_sql)        on Databricks            │
│  6. validate_results (retry once with correction prompt)       │
│                                                                │
│  7. compute_data_summary              shape data for LLM #2    │
│                                                                │
│  8. LLM call #2 ───→ interpret data_summary, return            │
│                       structured findings JSON                 │
│                                                                │
│  return structured_findings + supporting_context               │
└────────────────────────────────────────────────────────────────┘
```

Two LLM calls inside one skill, with structured data shaping between them. The outer agent treats this as a single tool invocation.

## Canonical example (excerpted from Bala's `market_share_skill.py`)

```python
def analyze_market_share(brand, market, question, ...) -> dict:
    # Steps 1-3: fetch context (deterministic, no LLM)
    schema      = describe_table("default.aos")
    aos_metrics = get_metric_definitions("AOS")
    canonical   = resolve_entity_values("default.aos", brand, market, category)

    # Step 4: LLM #1 generates SQL given the assembled context
    sql_prompt = f"""You are a Databricks SQL expert...
        {schema}
        Metric definitions: {aos_metrics}
        Use these EXACT string values: pg_brand='{canonical["brand"]}' ..."""

    for attempt in range(2):
        raw_sql = complete(system="...", user=sql_prompt)
        sql = extract_sql(raw_sql)
        rows = query(sql)
        if validate_brand_in_rows(rows, canonical["brand"]):
            break
        # Step 6: retry with correction prompt citing the failure
        sql_prompt += f"\n\nPREVIOUS ATTEMPT FAILED: {len(rows)} rows but brand not found..."

    # Step 7: shape data_summary BEFORE the interpretation LLM
    data_summary = {
        "focal_brand": canonical["brand"],
        "focal_weekly_share": [...all 52 weeks of focal brand...],
        "competitor_avg_share": {...aggregated...},
    }

    # Step 8: LLM #2 interprets the structured summary
    interpret_prompt = f"""Analyze this and return JSON: {data_summary}"""
    result = extract_json(complete(system="...", user=interpret_prompt))
    return result
```

The outer agent sees `analyze_market_share(brand, market, ...)` — one tool. Inside: 8 steps, 2 LLM calls, deterministic validation between them.

## Variants

- **Two-LLM-call** (Bala's shape): generator → executor → interpreter. The most common variant.
- **Generator-with-retry**: single LLM call but with an explicit retry loop driven by deterministic validation. Useful when output is structured (SQL, JSON, code) and validation is cheap.
- **Generator + critic**: producer LLM emits a draft; critic LLM scores. If critic flags below threshold, regenerate. (This is `architectures/adversarial-decomposition.md` applied at skill granularity rather than at the conversational layer.)
- **Multi-source merge**: fetch from N data sources in parallel; LLM merges into one structured output. Useful when no single source has the full answer.

## Why the inner pipeline, not just a fatter outer agent?

Three forces push knowledge inside the skill rather than back up to the outer agent:

1. **Context locality.** The schema, metric definitions, and canonical entity values are only relevant for THIS skill's reasoning. Pushing them up to the outer agent's context bloats every other tool call too.
2. **Validation runs deterministically between LLM calls.** The retry-with-correction pattern (step 6) works because Python code can check whether the focal brand appears in results. Adding that step to the outer agent's ReAct loop would require either custom tool definitions or trusting the outer model to retry — both fragile.
3. **Output shape stays stable.** The outer agent expects a structured result. If the skill's reasoning ever leaks (e.g., the interpretation LLM emits prose instead of JSON), the inner pipeline's `extract_json` fence catches it before it reaches the outer agent.

## Anti-pattern callouts

Two adjacent anti-patterns this pattern must avoid:

- **`anti-patterns/truncated-data-summary.md`** — step 7 (compute `data_summary`) must preserve the entity-of-interest's full series. Lazy `rows[:N]` between steps 5 and 8 silently hides signal.
- **`anti-patterns/definitions-without-context.md`** — when this skill returns classifications (e.g., a BCA category label), the definitions of those classifications must travel with the result, not just the labels. Outer agent narrates downstream and will hallucinate without the definitions.

Both anti-patterns are documented in Bala's repo as before/after empirical receipts. The combined fix moved his agent from sub-90 to 97/100 on LLM-as-judge.

## Cost / latency profile

Each inner LLM call adds latency. For Bala's two-LLM-call market-share skill:

- Steps 1-3 (deterministic fetches): 1-3s
- LLM #1 (SQL generation): 3-8s on Claude Opus 4.7
- Step 5 (SQL execution): varies by query, often 1-5s
- Steps 6-7 (validation + reshape): <1s
- LLM #2 (interpretation): 3-8s

Total skill latency: ~10-25s per invocation. The outer agent's loop typically invokes 4-6 skills, so end-to-end is 30-90s. Faster models (Haiku, GPT-5.4-mini) cut LLM-call time roughly in half.

The tradeoff: more LLM calls = more cost + latency, but also more structured intermediate state = better reliability and easier debugging. Pick this pattern when the alternative is a single fatter LLM call that has to do everything in one shot — that fatter call usually loses on quality.

## Empirical anchor

The three skills (`market_share_skill`, `root_cause_skill`, `report_skill`) in the public brand-analytics reference build are all inner pipelines. The agent scored 97/100 on independent LLM-as-judge eval. Without the inner-pipeline structure — specifically without the structured `data_summary` between SQL execution and interpretation — the worked example shows the LLM missed a step-change signal embedded in the synthetic ground truth. The pattern is load-bearing for this class of workload (LLM-interpreted query results against a relational data source).

Origin: documented in the reference build's source files `skills/market_share_skill.py` and `skills/root_cause_skill.py` (https://github.com/bladata1990/pg-brand-analyst-agent).
