---
title: Silent tool fallback (LLM invents data when tools fail)
category: anti-patterns
status: validated
last_updated: 2026-05-29
source_findings: []
source_external:
  - Observed in real customer agent deployments at multiple SaaS data platforms (2025-2026)
applies_when:
  workloads: [any-tool-using-agent, conversational-agent, task-agent, co-pilot]
  constraints: [agent-uses-external-data-tools, customer-trust-load-bearing]
contradicts: []
related:
  - anti-patterns/truncated-data-summary
  - anti-patterns/definitions-without-context
  - skill-design/inner-pipeline
snapshot_date: 2026-05-29
---

# Silent tool fallback

When a tool call fails, returns empty, or returns malformed data, the agent fabricates plausible-looking content to fill the gap instead of surfacing the failure. The agent's response *looks* successful — same shape, same confidence, same prose voice — but the data is invented. The user has no signal that the answer came from a hallucination rather than from real data.

This is the most dangerous failure mode for any tool-using agent that customers will trust. Worse than the agent erroring out (because the error never surfaces). Worse than the agent saying "I don't know" (because nothing is admitted unknown). Worse than the agent stopping (because the agent confidently *continues*).

## How it shows up

Four representative shapes, all observed in production:

### Shape 1 — empty result, hallucinated content

```python
def get_top_assets_by_usage(workspace_id: str) -> list[Asset]:
    results = atlan.search.basic(...)
    return results  # may return [] on transient failure or auth issue
```

Agent receives `[]`, prompt says "summarize the top assets by usage," agent generates:

> *"The most-used assets in your workspace are `customer_360_dim` (12,400 queries last 30 days), `orders_fact` (8,920), `product_catalog` (6,310). Most usage comes from the analytics team."*

All fabricated. The numbers, the names, the attribution. The agent inferred what the answer "should look like" from the prompt's framing and the tool's output schema.

### Shape 2 — tool error, agent retries via memory

```
Tool: search_assets failed (401 invalid_token)
Agent: tries the tool 2 more times, all fail
Agent (silently): "I'll answer from what I learned earlier in this conversation"
Agent (to user): "Your `orders` table has the following columns: id, customer_id, amount, status, created_at..."
```

The agent had a schema query result from 20 turns ago in its context. When the live tool failed, it fell back to that stale cached context — without telling the user the data is stale or that the live query failed. The user gets data that *was* true but may no longer be.

### Shape 3 — partial result, agent extrapolates

A tool returns 3 of an expected ~20 records (because of pagination, rate limit, or schema drift). The agent's prompt told it to "summarize all the matches." Instead of paginating or surfacing the truncation, the agent generates a summary that implies it saw all 20 — describing patterns, percentages, distributions — from data it didn't actually see.

This is the cross-product with `anti-patterns/truncated-data-summary`: silent fallback amplifies the truncation problem because the agent doesn't even *try* to surface that data was truncated.

### Shape 4 — schema mismatch, agent reshapes silently

A tool returns data in a slightly different shape than expected (renamed field, missing optional field, type change). The agent's prompt expected `revenue` but got `gross_revenue`. The agent silently maps one to the other, or fabricates a `revenue` value derived from other fields, without noting the schema gap.

## Why it happens

Three mechanisms:

1. **The agent's "do my best" reflex outweighs its "say I don't know" instinct.** Modern LLMs are trained to be helpful. When a tool returns empty or fails, the path of least resistance is to fill the gap from prior context or general knowledge. Refusing to answer feels like a worse outcome than guessing — but it isn't, when the customer can't tell the difference.

2. **Tool failures are often soft.** A tool that returns `[]` looks structurally identical to a tool that "ran and found nothing." Neither raises an exception. The agent has to be explicitly told to distinguish these — most prompts don't.

3. **Skills don't always validate.** A skill that wraps `search_assets()` and naively returns the result list passes downstream consumers a successful-looking but empty payload. The validation layer that says "if the tool returned empty in a context where empty is unexpected, surface the gap" doesn't exist by default.

## Why it matters

The customer impact is asymmetric. A confident hallucination has the same cost as a real answer to *produce*, but it destroys trust on detection in a way a real answer can't restore. One detected fabrication makes the customer second-guess every prior answer they trusted. The ratio is something like 1:50 — one fabrication erodes ~50 real answers' worth of trust.

For Atlan-internal agents that interact with customer data, this is especially load-bearing. SE/CES teams building agents on top of customer data infrastructure cannot ship agents that silently invent metadata facts. The customer will notice exactly once, and the project dies.

## How to prevent it

### Skill-design layer

Every skill that wraps a tool must implement **failure-surfacing**:

```python
def get_top_assets_by_usage(workspace_id: str) -> SkillResult:
    try:
        results = atlan.search.basic(...)
    except AuthError as e:
        return SkillResult.error(
            reason="auth_failed",
            user_facing="I can't access the workspace right now (auth error). "
                        "Surfacing this so you know the answer below isn't grounded."
        )
    if not results:
        return SkillResult.empty(
            reason="no_matches",
            user_facing="The search returned zero results. This may mean the workspace "
                        "is empty, or my query was wrong. Confirming this is the answer "
                        "you expected before continuing."
        )
    return SkillResult.ok(data=results)
```

The skill *always* returns a typed result with explicit `empty` and `error` cases. The agent's downstream prompt knows how to surface these — never silently filling the gap.

### Prompt-design layer

Agent system prompts must include an explicit failure-surfacing rule:

> *"If a tool returns empty, errors, or returns a result you can't interpret, you MUST surface this to the user explicitly. Say "the tool returned no results" or "the tool call failed" — never substitute prior context or general knowledge for a tool's live answer. If the user wants you to answer from memory anyway, they will ask. Default to surfacing the gap."*

### Eval-design layer

Judge harnesses must include a **fabrication-detection** dimension that compares the agent's claim against the actual tool outputs in the trace:

> *"For each factual claim in the agent's response, can the claim be grounded in a specific tool output captured in the trace? If yes, claim is grounded (score = 1). If no, claim is potentially fabricated (score = 0)."*

This is the only way to detect silent fallback at scale. Spot-checking individual sessions catches some cases but misses the systematic ones. An eval that compares claims-to-traces catches the failure mode reliably.

### Observability layer

For autonomous workers (claws) where no human is reviewing each turn, log **tool-failure rates** as a first-class metric. A spike in tool failures with no corresponding spike in user-facing "I couldn't get the data" messages means silent fallback is active. The ratio between tool failures and user-facing surface-the-gap messages should be ~1:1; if it's 1:0, you have a silent fallback problem.

## Provenance

This anti-pattern doesn't yet have a direct discovery-inception session that surfaced it — included here proactively because it's the most-observed agent failure mode in production deployments across the SaaS data infrastructure space (Atlan, Snowflake, Databricks, Atlan customers). The pattern is well-established outside this codebase; this entry captures the structural prevention story.

Worth promoting to `validated` status once a discovery-inception session catches an agent design that would be vulnerable to this and the architecture_proposer rejects the design with this entry as the citation.

## Hard rules for tool-using agent designs

1. **Every skill must return typed results with explicit empty/error cases.** No skill returns a raw tool result list without classification.
2. **The agent's system prompt must include a failure-surfacing rule.** Default-to-surface, not default-to-fill.
3. **The eval harness must include fabrication detection.** Claims-vs-traces comparison; not a separate eval, but a dimension of the main judge.
4. **For claws, monitor tool-failure-to-user-surface ratios as a first-class metric.** Drift here is the canary.
