# 03 — Technical-Thread Discovery

**Status:** design — not yet built.
**Depends on:** the v0.8 discovery agent + intake / priors pipeline (both shipped).
**Pairs with:** `06-atlan-context-integration.md` (where the technical thread reads from).
**Feeds:** `08-inception-agent.md` (which requires the technical half of the spec to produce defensible starter designs).

---

## The problem this fixes

The discovery agent is good at pulling the *conceptual* half of a use case: who the user is, what their pain is, what success looks like, what the anti-goals are, where ownership lives. Five iterations of empirical validation (`findings/01–05`) say that.

It is silent on the *technical* half: what stack the team has standardized on (Cortex / ADK / Anthropic SDK / LangGraph / Pydantic AI), where the data physically lives (Databricks / Snowflake / BigQuery / Postgres), what semantic layer sits on top (Cortex Analyst / dbt / hand-rolled SQL), what already exists as documented context, what the runtime constraints are, and where the eventual agent has to deploy.

That silence didn't matter when the project's deliverable was a conceptual spec for a human builder to interpret. It matters now that:

1. The downstream consumer is going to be an **inception agent** (`08-inception-agent.md`) that proposes skills + architecture + runtime. Those proposals are unfounded without technical context.
2. The customer-side reality is that most teams have constraints — *"we already standardized on Vertex AI" / "the data only flows through Databricks" / "the agent has to run inside AgentCore."* Producing a starter that ignores those constraints is worse than not producing one.
3. The empirical case study (P&G) showed exactly this gap: the priors agent on the Gong scoping call captured the workflow well but missed the BCA framework, the canonical table names (`default.aos` / `default.ddm`), and the chosen runtime (Anthropic SDK). All of that lived in Atlan / Bala's pipeline doc / the customer's internal tooling, not in the transcript.

A discovery that doesn't ask the technical questions is a discovery that produces a half-spec. Half-specs are why "agent that helps build other agents" stalls at translating tacit knowledge — without the technical scaffold, the next step has nothing to land on.

---

## The two concern threads, made explicit

| Conceptual (today) | Technical (NEW) |
|---|---|
| `persona` | `tech_stack` — frameworks / SDKs / models the team is committed to |
| `current_pain` | `data_sources` — warehouses, tables, schemas, freshness |
| `success_metric` | `semantic_layer` — Cortex Analyst / dbt / hand-rolled / none |
| `anti_goal` | `existing_context` — what's already cataloged in Atlan or elsewhere |
| `decision_point` | `runtime_target` — where the agent deploys; infra constraints |
| `escalation_rule` | `governance_constraints` — must-use / can't-use / compliance |
| `workflow_process` | `data_freshness` — real-time / daily / weekly |
| `approval_scope` | `identity_model` — per-user / service-account / OAuth |

These are not add-on questions tacked on at the end. They're a **parallel concern thread** the mega-agent maintains alongside the conceptual one — interleaved naturally in the conversation, surfaced based on what's already known and what the customer's last answer touched on.

The headline behavioral change: **the agent only asks technical questions whose answers aren't already known.** If the Atlan integration (`06-atlan-context-integration.md`) returned a populated bounded context with table schemas and glossary terms, the mega-agent skips redundant probes and only fills gaps. If no Atlan context is available, the technical thread runs hot.

---

## Schema additions

`DiscoverySpec.topics` already supports arbitrary topic names. The new canonical technical topics get added to the checklist evaluator so phase advancement and gap reporting work the same way they do for conceptual topics.

Canonical technical topics (initial list, evolves):

```python
TECHNICAL_TOPICS = [
    "tech_stack",
    "data_sources",
    "semantic_layer",
    "existing_context",
    "runtime_target",
    "governance_constraints",
    "data_freshness",
    "identity_model",
]
```

`Fact` records gain an optional `technical_asset_references: list[str]` field. When a captured fact mentions a specific table, framework, table column, glossary term, or system — those references get tagged. Example:

```
Fact: "The analyst queries Trade Panel data weekly via Databricks SQL"
  technical_asset_references: ["table:default.ddm", "warehouse:Databricks"]
```

This tagging enables the close-out step (`context_gap_proposer`) to scan facts for technical assets that aren't yet established in the bounded context — feeding into Atlan-write-back when that pathway exists (`04`, deferred section).

---

## Sub-agent additions

Three new sub-agents in the discovery pipeline. They follow the same single-prompt-one-Pydantic-output discipline as the existing extractor / synthesizer / sharpener.

### `atlan_context_probe` (session-start)

**When it runs:** once, at session start, before the first customer turn.

**Inputs:** `use_case_seed`, `role_id`, optional list of glossary / repo / schema scope arguments (see `06-atlan-context-integration.md` for the I/O contract).

**Outputs:** structured `BoundedContext` summary — what tables / glossary terms / lineage / business definitions exist in the customer's Atlan tenant relevant to this use case. Plus a `known_gaps` list identifying obvious holes in what was returned.

**Effect on the mega-agent:** primes the system prompt with a "what's already established" section. Reduces redundant questioning.

### `tech_thread_tracker` (per-turn)

**When it runs:** every turn, alongside `triage` / `distill`.

**Inputs:** customer message + current `DiscoverySpec`.

**Outputs:** for each captured fact, the list of technical assets it references (tables, columns, frameworks, systems). Optionally suggests a follow-up tech-thread probe if the customer mentioned a technical asset that isn't yet captured.

**Effect:** keeps the technical concern alive across the conversation without requiring the mega-agent to track it explicitly.

### `context_gap_proposer` (close-out)

**When it runs:** at session close, after the final synthesizer.

**Inputs:** complete `DiscoverySpec`, all captured `technical_asset_references`, the original `BoundedContext` from session start.

**Outputs:** `context_repo_gaps.md` — proposed additions to the customer's Atlan tenant. Each gap has:
- The asset (table, glossary term, lineage edge) that was referenced
- Why it matters (which captured fact references it)
- What's missing (definition? schema? owner?)
- A suggested glossary entry or table description

**Effect:** captures the write-back direction structurally even though `04`'s write-back pathway is deferred. The artifact exists; humans (or eventually CES) consume it.

---

## Prompt changes (mega-agent + sharpener)

The mega-agent's system prompt gets a new section: *"Two concern threads — conceptual and technical."* Includes guidance on when to weave a technical question in naturally vs when to defer (e.g., don't ask about runtime targets in turn 1 if the customer just framed the use case at the conceptual level).

The probe-sharpener gets one extension: in addition to the four existing quality dimensions (novelty / extension / provenance / tension), it gains a *thread balance* signal — flagging when the agent has spent N turns on conceptual without surfacing technical (or vice versa).

Both prompt edits are candidates for **patterns-knowledge-base** consumption (`05`) rather than baked-in text — when the rules for thread balancing evolve, they should be a retrievable pattern, not a prompt rewrite.

---

## Behavior under different Atlan-context conditions

The technical thread adapts based on what `atlan_context_probe` returns:

| Atlan returns... | Mega-agent behavior |
|---|---|
| Rich bounded context (tables, glossary, lineage) | Skip 80% of technical probes. Focus on what's NOT yet documented (decision rules, business meaning that isn't in glossary). Reference established names verbatim when probing. |
| Partial bounded context (tables exist but no business definitions) | Probe for definitions, formulas, ownership. Don't re-ask schema. |
| Empty or unavailable | Run full technical-thread probing. Output of `context_gap_proposer` becomes a "here's what should be in your context layer" report. |

The third condition is the bootstrap case — a team that doesn't have anything in Atlan yet. Discovery produces both the spec AND the seed for what they should put in Atlan to enable agentic workflows.

---

## Output additions

The discovery session's deliverables grow from two to three files:

| Today | After |
|---|---|
| `spec.md` (conceptual only) | `spec.md` — now has technical + conceptual sections |
| `session.json` | `session.json` (unchanged) |
| — | `context_repo_gaps.md` (NEW — proposed Atlan additions) |

`spec.md`'s new technical section pulls from the technical topics; the conceptual section is unchanged. Inception's input is the combined `spec.md` + `BoundedContext` (from Atlan, captured at session start).

---

## What this doesn't do (scope boundaries)

This plan does NOT cover:

- **Atlan write-back** — `context_repo_gaps.md` is produced but not pushed to Atlan automatically. That's deferred to a future iteration of `04`.
- **Schema inference from data warehouses directly** — if the customer can't or won't expose Atlan, we don't go around it to read Databricks directly. The technical thread asks the customer instead.
- **Live tool-discovery** — we don't enumerate MCP servers or available tools at session start. That's an inception-time concern (`06`), not discovery-time.
- **Validating that the customer's stated tech stack is actually feasible** — the agent records what they say. Whether `Anthropic SDK + Google ADK at the same time` makes architectural sense is something the inception agent reasons about later.

---

## Empirical validation plan

Once built, validate by:

1. Re-running the P&G case with the technical thread on. Compare the resulting spec to (a) my manual v2 design and (b) Bala's actual implementation. The technical thread should surface the table names, the runtime (Anthropic SDK), and the BCA framework as either captured-from-Atlan or asked-of-the-customer.
2. Running on a clean use case where the team has **no Atlan tenant set up yet** — the technical thread should run hot, surface a meaningful `context_repo_gaps.md`, and the spec's technical section should be populated from probing alone.
3. Running on a use case with **partial Atlan context** (tables documented but no glossary terms) — the agent should defer schema probes and focus on business definitions.

Each of those three is a finding-shaped experiment (`findings/NN-...md`) once executed.

---

## Open questions

1. **Should the technical thread be opt-in via a CLI flag?** The current discovery API is `start-session --use-case-seed "..." --role-id ...`. Adding `--atlan-tenant ...` and `--atlan-scope "..."` enables the thread. When neither is provided, technical thread runs in probe-only mode. Probably yes — explicit is better than implicit.
2. **How does the mega-agent decide when to interleave technical vs conceptual probes?** Heuristic options: alternate, prioritize the thread with the most gaps, follow the customer's last topic, defer technical until phase advances to `drilling`. The right answer is empirical — we test patterns and codify the winner in `patterns/decision-guides/`.
3. **Should `existing_context` be a single topic or split into `existing_tables` / `existing_glossary` / `existing_lineage`?** Lean toward single topic with structured sub-fields, to match how Atlan organizes the bounded context. Revisit after first run.
4. **What's the granularity of `technical_asset_references`?** Just URIs (`table:db.schema.table`, `glossary:Term`) or richer (with usage hints)? Start simple, iterate.

---

## Implementation sequence

1. Add `TECHNICAL_TOPICS` to the checklist evaluator + `technical_asset_references` field to `Fact`
2. Draft prompts for `atlan_context_probe` (will plug into `04`)
3. Draft prompts for `tech_thread_tracker` (per-turn)
4. Draft prompts for `context_gap_proposer` (close-out)
5. Extend mega-agent system prompt with thread-balance guidance (initially baked in; migrate to patterns lookup per `05`)
6. Extend probe-sharpener to include thread-balance signal
7. Update `spec.md` rendering to include technical section
8. CLI flag: `--atlan-tenant`, `--atlan-scope`
9. Validate on P&G case (see *Empirical validation plan*)

Estimated 3–5 days of focused work. Most of the IP is in the prompts.
