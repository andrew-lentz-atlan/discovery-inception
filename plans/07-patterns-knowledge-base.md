# 05 — Patterns Knowledge Base

**Status:** design — not yet built.
**Inspired by:** Karpathy's LLM-maintained wiki gist (https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).
**Pairs with:** `08-inception-agent.md` (the primary consumer).
**Also feeds:** the discovery agent's mega-agent (runtime lookup of decision-time patterns).

---

## The problem this fixes

The discovery-inception project has been accumulating opinions for six months. Five `findings/` docs encode hard-won architectural lessons. The system prompts encode those lessons as baked-in instructions. The harness team's research doc captures the state of the field at a point in time. Bala's repo documents five empirical lessons from one customer build. None of this is queryable from inside the agent.

When inception (`06`) needs to propose an architecture, it has to either (a) re-derive the reasoning from scratch each time or (b) consume opinions baked into its prompt — which means whoever wrote that prompt made the decisions for it. The first wastes compute and produces inconsistency. The second creates **context debt**: opinions encoded six months ago that don't update when the field shifts.

The fix is the same fix Bala used at the customer level: **knowledge that informs decisions lives outside the prompts, in a queryable substrate that can be updated independently.** Bala called it Atlan-as-runtime-knowledge. We're building the same pattern for agent-design knowledge.

---

## The principle

**Prompts encode invariants. Knowledge bases encode opinions.**

| Belongs in prompts | Belongs in retrievable knowledge |
|---|---|
| Role / persona / what the sub-agent is | "When to use single-agent ReAct vs planning-first" |
| Output format / schema contract | "How to design skills with one-question-one-data-source mapping" |
| Basic discipline (be specific, cite sources) | "BCA framework definitions must travel WITH the diagnosis (Bala's lesson)" |
| Anti-hallucination guardrails | "Adversarial decomposition pattern is load-bearing for structured extraction" |
| Output formatting rules | Empirical findings, framework comparisons, best practices |

The dividing line is *change rate*. Invariants change at the same rate as the system's core architecture (rarely). Opinions change at the rate of the field (constantly). Putting opinions in prompts is the same anti-pattern as hardcoding config — it works until something changes.

---

## What the substrate looks like

A new top-level directory in the repo: **`patterns/`**.

```
patterns/
├── README.md                       — the curator's instructions to readers (humans + agents)
├── _index.md                       — auto-generated; lists every entry with status + last-updated
├── _log.md                         — audit trail of ingests, edits, lints, deprecations
├── architectures/
│   ├── single-agent-react.md
│   ├── chained-pipeline.md
│   ├── adversarial-decomposition.md
│   ├── planning-first.md
│   ├── role-based-crew.md
│   ├── hierarchical-orchestrator.md
│   └── swarm.md
├── harnesses/
│   ├── claude-agent-sdk.md
│   ├── openai-agents-sdk.md
│   ├── pydantic-ai.md
│   ├── deep-agents.md
│   ├── langgraph.md
│   ├── crewai.md
│   ├── google-adk.md
│   ├── microsoft-agent-framework.md
│   ├── strands.md
│   ├── smolagents.md
│   ├── llamaindex-agentworkflow.md
│   ├── mastra.md
│   ├── pi-dev.md
│   ├── openharness.md
│   └── claude-managed-agents.md
├── skill-design/
│   ├── single-llm-call.md
│   ├── inner-pipeline.md           ← Bala's pattern
│   ├── one-question-one-source.md  ← Bala's heuristic
│   ├── stateful-vs-stateless.md
│   ├── adversarial-review.md
│   └── routing-as-orchestrator-vs-skill.md
├── decision-guides/
│   ├── conversational-vs-query-response.md
│   ├── batch-vs-interactive.md
│   ├── single-vs-multi-agent.md
│   ├── when-to-use-mcp-vs-direct-tool.md
│   ├── when-to-invoke-synthesis.md
│   ├── tension-detection-triggers.md
│   └── thread-balance-conceptual-vs-technical.md
├── anti-patterns/
│   ├── eager-synthesis.md
│   ├── definitions-without-context.md   ← Bala's bca_framework lesson
│   ├── truncated-data-summary.md        ← Bala's data_summary lesson
│   ├── opinion-baked-in-prompt.md       ← this whole doc, in pattern form
│   ├── recency-bias-in-synthesis.md
│   ├── role-anchoring-on-meta-artifact.md ← our priors-agent finding
│   └── prompt-flavor-portability-blindness.md
└── lessons-from-builders/
    ├── bala-bca-framework-must-travel.md
    ├── bala-data-summary-not-raw-rows.md
    ├── bala-resolve-entity-values.md
    ├── bala-sql-retry-with-correction-prompt.md
    └── bala-domain-knowledge-in-context-layer.md
```

Each entry is a markdown file with structured frontmatter:

```yaml
---
title: Adversarial Decomposition
category: architectures
status: validated              # validated | experimental | deprecated
last_updated: 2026-05-13
source_findings: [findings/05-v08-probe-sharpener-and-tensions.md]
source_external: []            # links to external research / blog posts / framework docs
applies_when:
  workloads: [structured-extraction, conversational, quality-critical]
  constraints: []
contradicts: [chained-pipeline]
related: [single-agent-react, skill-design/adversarial-review]
---

# Adversarial Decomposition

## When to use
[1–3 paragraphs]

## When NOT to use
[1–2 paragraphs]

## Empirical receipts
[cite findings/ documents that validate this]

## Implementation gotchas
[bullet points]

## Variants & related patterns
[cross-references to other entries]
```

The frontmatter is what makes entries queryable. The body is what makes them readable.

---

## Three operations (Karpathy's model)

The Karpathy gist names three operations on an LLM-maintained wiki: **ingest**, **query**, **lint**. They map cleanly here.

### Ingest

Pull from a raw source into a new or updated `patterns/` entry. Sources, in priority order:

1. **Our `findings/` docs.** Each validated finding has a one-way promotion path. `findings/05` validated adversarial decomposition; that promotes (entirely or partially) into `patterns/architectures/adversarial-decomposition.md`. Findings remain the empirical receipt; patterns are the reusable distillation.
2. **External research docs.** The harnesses report (~33pp comparing 15 frameworks) becomes ~15 entries under `patterns/harnesses/`. Karpathy posts, framework release notes, MCP spec changes, frontier-model capability announcements — all sources.
3. **Empirical lessons from builders.** Bala's 5 design lessons each become a `patterns/lessons-from-builders/` entry. The next P&G-shaped exercise inherits them.

Ingest is an agent operation: a `patterns_curator` agent reads the source, drafts a structured entry, presents it for review, and writes it (with `status: experimental` if the source is single-evidence; `status: validated` if it's drawn from a findings document with empirical receipts).

### Query

Agents read entries at decision points. Three retrieval shapes:

| Retrieval shape | Caller | Example |
|---|---|---|
| **By structured filter** | inception's `architecture_proposer` | `applies_when.workloads contains 'query-response'` → returns top 3 architectural candidates |
| **By free-text search** | discovery's mega-agent (mid-conversation) | "look up pattern for handling customer hedging" → returns matching entries |
| **By citation** | any agent writing output | embed `[ref: patterns/architectures/adversarial-decomposition.md]` in the output for traceability |

Query is exposed as a tool (`lookup_pattern(query | filter)`) the agents can call. The tool returns the front-matter + body of the top-N matches.

### Lint

Periodic (or on-demand) review for staleness, contradictions, and duplicates. The `patterns_curator` agent does the linting:

| Lint check | What it flags |
|---|---|
| **Staleness** | Entries with `last_updated` > N days (default 90); especially in fast-moving categories like `harnesses/` |
| **Contradictions** | Two entries with overlapping `applies_when` but opposite recommendations, neither marked `contradicts:` of the other |
| **Duplicate coverage** | Two entries that ought to merge (same pattern under different names) |
| **Orphaned receipts** | Entries claiming `source_findings: [...]` but the cited finding doesn't exist or was deprecated |
| **Pattern-prompt drift** | Patterns whose `last_updated` is much newer than the prompts that should consume them — implies migration debt |

Lint runs produce an audit report. Some findings auto-resolve (regenerate from updated source); others require curator review.

---

## The patterns curator (companion agent)

This is the agent flow Andrew asked about — the maintenance side.

```
                    raw sources
              (findings/, external research,
               builder reports, framework docs)
                          │
                          ▼
                  ┌───────────────┐
                  │ patterns_     │  ← reads sources, drafts entries
                  │ curator       │
                  └───────────────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
          ingest        query        lint
              │           │           │
              ▼           ▼           ▼
     [new/updated     [serves to    [flags issues
       entries]      agents at      to humans]
                     decision time]
```

**Why a companion agent and not an integrated step:**

- Update cadence is independent of discovery / inception sessions. We don't want to slow either down to re-validate the knowledge base on every run.
- The curator's prompts and workflow are different — it's reading documents to produce structured entries, not interviewing customers or proposing skills. Different concerns, different lifecycle.
- It can run on a schedule (nightly lint), on a webhook (new finding committed → ingest), or on-demand (human says "add Pi to the harnesses").

**Could it be a separate repo?** Open question. Arguments for:

- The curator has its own dependencies (markdown parsing, link checking, possibly Atlan integration for cross-reference)
- The `patterns/` artifact has consumers beyond discovery-inception — anyone building agents wants to read it
- A separate repo lets the patterns library evolve independently of the agent flow

Arguments against:

- Two repos doubles the maintenance burden during early iteration
- The curator's prompts share a lot with inception's prompts (both reason about agent patterns)
- Adding the second repo before patterns has stabilized is premature

**Decision: start in the same repo.** Move to a separate repo only if (a) the `patterns/` library grows beyond ~50 entries with active churn, OR (b) we have at least one external consumer.

---

## Adoption-lever framing

Patterns living in our repo, consumed via a tool exposed only through our agents, has a side effect Andrew called out: **it forces people who want this knowledge to use our agents to get it.** That's an adoption lever for discovery-inception and (eventually) inception. People build their own agents → they want field-tested architectural advice → the easiest way to get it is to drive our agent → they end up building with our tooling.

Compare to publishing patterns as a Markdown blog: people would read them but might not connect them to our agent. Compare to putting patterns in Atlan: cleaner architecturally but adds tenant dependency for what's currently an open-knowledge problem.

For now, the lever is repo-resident + tool-mediated.

---

## How patterns get consumed by existing agents

### By discovery's mega-agent

Today, the v0.8 mega-agent's system prompt has baked-in opinions about when to invoke `synthesize_my_thinking`, when to invoke `find_tensions`, and what makes a strong probe. Migration path:

1. Each baked-in opinion gets a corresponding `patterns/decision-guides/` entry
2. The mega-agent gains a new tool: `lookup_pattern(query)`
3. The system prompt loses the baked-in opinion but gains "When deciding [X], consult patterns/decision-guides/[entry]"
4. Empirically validate: does the agent perform as well with lookup as with baked-in?
5. Roll forward (migrate the next opinion) only if validation passed

Lazy migration; preserves working behavior; lets us measure each change.

### By inception (`06`)

Inception is a fresh consumer. It can be designed to use patterns from day one — every architectural proposal cites a `patterns/architectures/` entry; every skill-design choice cites a `patterns/skill-design/` entry; every harness recommendation cites a `patterns/harnesses/` entry. The output of inception is itself partly traceability metadata, with cite-by-pattern as a first-class concept.

### By humans

Patterns are readable markdown. A developer asks "what's the right architecture for query-response work?" — they read `patterns/decision-guides/conversational-vs-query-response.md`. The agents and the humans consume the same artifact.

---

## Versioning and staleness

| Concern | Mechanism |
|---|---|
| Entries go stale | `last_updated` field. Curator's lint flags entries > 90 days old (configurable per category). |
| Field evolves (new harness, new model, deprecated framework) | New entry created; old one optionally marked `deprecated`; both stay in repo for historical traceability. |
| Contradicted by new evidence | `status: deprecated` + add `superseded_by` field pointing to the replacement entry. |
| Old entries that are still informative | Stay `validated` until evidence contradicts them. Age alone isn't deprecation. |
| Different opinions for different contexts | Two entries with non-overlapping `applies_when` — explicit, by design. Curator's lint surfaces overlap as a flag, not as an error. |

**A key principle:** deprecated entries don't get deleted. They stay readable so anyone tracing a past decision can see the knowledge state at the time the decision was made. The `_log.md` (audit trail) records when entries moved from one status to another.

---

## Implementation sequence

1. Create `patterns/` directory with `README.md`, `_index.md` template, and `_log.md` template
2. Define the structured frontmatter schema (Pydantic class in the codebase; serialized as YAML in entries)
3. Seed initial entries — promote our existing findings into patterns:
   - `findings/01-architecture-comparison.md` → `patterns/architectures/chained-pipeline.md` + `single-agent-react.md` + `adversarial-decomposition.md` (the three contenders)
   - `findings/04-v07-deterministic-closeout.md` → `patterns/architectures/lazy-plus-deterministic-synthesis.md`
   - `findings/05-v08-probe-sharpener-and-tensions.md` → `patterns/skill-design/adversarial-review.md`
   - `findings/06-cost-latency-and-deployment-modes.md` → `patterns/decision-guides/three-deployment-modes.md`
   - `findings/08-cheap-cascade-gpt4o-mini-doesnt-pan-out.md` → `patterns/anti-patterns/naive-cheap-cascade.md`
4. Seed the harnesses bucket from the team's harness research doc (15 entries)
5. Seed the builder-lessons bucket from Bala's repo (5 entries)
6. Build the `patterns_curator` agent (separate sub-pipeline; `agent/patterns_curator/` or similar)
7. Expose `lookup_pattern(query)` as a tool — first to inception (built greenfield with this dependency), later to discovery (via migration)
8. Add the lint workflow (manual trigger first; automate later)

Estimated 1–2 weeks of focused work. Seeding entries is most of it; the curator agent is roughly the same shape as the intake / discovery agents (single-prompt sub-agent pipeline).

---

## What this doesn't do (scope boundaries)

- **Doesn't promise comprehensiveness.** Initial seed = ~30 entries. Field has thousands of patterns. We curate what we use, not what exists.
- **Doesn't replace findings/**. Findings are empirical receipts; patterns are reusable distillations. Both stay.
- **Doesn't auto-update from arbitrary internet content**. Sources are vetted: our own findings, named external docs, named builder reports. No web-crawling agents.
- **Doesn't enforce that every agent decision cites a pattern**. Strong norm, not hard requirement. Decisions that don't fit any existing pattern should produce candidate patterns (via ingest), not be forced into a wrong one.

---

## Open questions

1. **Single repo or eventual split?** Start single, split when justified by external consumption.
2. **Structured filter syntax for queries?** YAML-ish (`{workloads: query-response}`) vs SQL-ish vs natural-language? Lean structured-with-fallback (`lookup_pattern(filter={workloads: 'query-response'}, fallback_query="best architecture for ad-hoc analyst questions")`).
3. **How are patterns versioned in git?** Standard git history is probably enough — `last_updated` matches the commit timestamp. Don't over-engineer.
4. **What's the minimum evidence for `status: validated`?** Lean: needs at least one cited finding OR at least two cited external sources. `experimental` for everything else.
5. **Does the curator agent need its own findings/ track?** Probably yes — when we learn that ingest mis-categorizes things, or lint produces false positives, those are findings about the curator itself.
6. **How do we prevent the curator from being a single point of failure?** It should be runnable by humans too — every operation it does is also doable by hand. The agent accelerates; it doesn't gate.

---

## Concrete next steps after design approval

1. Create `patterns/` with stub README + index + log
2. Promote findings 01, 04, 05, 06, 08 into patterns entries (5 entries — empirical receipts intact)
3. Seed harnesses bucket from the team's harness research (15 entries — one per harness)
4. Seed builder-lessons from Bala's 5 lessons (5 entries)
5. Total initial seed: ~25 entries — enough that the curator + inception can be built and tested against a non-trivial corpus
6. Build `patterns_curator` skeleton with just the `ingest` operation. Validate by feeding it `findings/05` and confirming the resulting entry roughly matches what we'd write by hand.
7. Add `lookup_pattern` tool. Validate by feeding inception's `architecture_proposer` (when built) and confirming it consults patterns rather than guessing.
8. Defer `lint` until we have ~50 entries and at least one observed contradiction.
