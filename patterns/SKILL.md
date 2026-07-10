---
name: patterns-navigation
description: How to query and consume entries in patterns/ — the agentic patterns knowledge base. Use when reasoning about agent architecture, skill design, harness choice, or known anti-patterns. Entries are knowledge articles, not invocable capabilities.
---

# Navigating patterns/

This directory is a curated knowledge base of agentic patterns. Entries are knowledge articles (what we know about a pattern), not invocable capabilities (how to perform a task). Consult them at decision time; cite them in your output for traceability.

## Structure

```
patterns/
├── architectures/      orchestration shapes (single-agent ReAct, adversarial decomposition, ...)
├── anti-patterns/      failure modes to avoid (with empirical receipts)
├── skill-design/       skill-level patterns (inner pipeline, source fidelity, ...)
├── harnesses/          per-framework analysis (Claude SDK, Pydantic AI, ...)
└── decision-guides/    when-to-use guidance for specific choices
```

## How to query

Filter entries by frontmatter:

- `category` — narrow to one subdirectory
- `status` — default to `validated`; skip `deprecated` unless auditing past decisions
- `applies_when.workloads` — primary filter (e.g., `conversational`, `query-response`, `batch`, `quality-critical`)
- `applies_when.constraints` — secondary filter (e.g., `low-latency-target`, `simplicity-prized`)
- `contradicts` / `related` — traverse the entry graph

Example query: "what architecture for a conversational workload where output quality matters?" → filter `category: architectures` + `applies_when.workloads contains conversational` → returns `single-agent-react` + `adversarial-decomposition` (the latter also carries the `quality-critical` tag, answering the quality half).

## Entry shape

**Always present:**

- **YAML frontmatter** — queryable metadata. The standardized contract.
- **One-paragraph summary** — what the pattern is, in plain English.

**Default body template** (for operational-decision entries — architectures, anti-patterns, decision-guides):

- `## Use when` — the decision-time payload
- `## Don't use when` — boundary conditions
- `## Key gotchas` — implementation pitfalls
- `## Empirical anchor` — one paragraph citing supporting evidence

This template covers the most common kind of pattern entry. Use it as the default starting shape.

**Other body shapes when the knowledge warrants:** comparative surveys use tables + cross-cutting observations; theoretical entries use premises + implications; historical retrospectives use trajectory + what-it-enabled; code-pattern entries use pattern + code + variants. The frontmatter stays the same — the body adapts to what the knowledge actually is.

Some entries have a `<entry-name>.reference.md` companion with deeper justification — deprecation history, full empirical comparisons, maintenance notes. **Consult only when needed for review or audit.** A `reference:` field in frontmatter signals when one exists.

**Length follows content, not a target.** A simple pattern might be 30 lines; a pattern with real complexity might warrant 100+. The discipline is what NOT to include (ceremony, padding, recapitulation of cited sources), not how many lines to hit.

## Naming conventions

- Files are named by **content**, not by source. A lesson from builder X goes in the topical category by what it teaches (`anti-patterns/truncated-data-summary.md`, not `lessons-from-builders/bala-truncation-lesson.md`).
- Attribution to a source builder lives in `source_external:` frontmatter and optionally a one-line credit in the body. Not the filename.
- `SKILL.md` is reserved for **directory-level navigation skills** (like this file). Pattern entries do not use the `SKILL.md` filename — they are knowledge articles, not skills.
- Canonical entries are `<slug>.md`. Files suffixed `.draft.md` / `.update.md` / `.contested.md` / `.candidate.md` / `.triage.md` are curator output awaiting human promotion — not canonical, not in `_index.md`; don't cite them.

## Status semantics

| status | meaning | retrieval default |
|---|---|---|
| `validated` | Empirically supported; default choice | returned by query |
| `experimental` | Promising but single-source / anecdotal | returned with flag |
| `draft` | Authored + internally sanity-checked, awaiting peer audit — opinionated-but-unvalidated | returned with flag |
| `deprecated` | Superseded; kept readable for traceability | excluded unless audit query |

When an entry is `deprecated`, follow its `superseded_by:` pointer to the canonical replacement.

## Citation pattern

When using a pattern to inform a decision, cite it in your output:

```
Decision: single-agent ReAct loop with 4 bound tools.
Rationale: see patterns/architectures/single-agent-react.md.
```

This is the audit trail. It tells a human reviewer (a) what pattern was consulted, (b) when (timestamp from the commit log of the cited entry), and (c) what was known at the time.

## When to add a new entry

The `patterns_curator` agent handles ingest from raw sources (findings/, external research, builder lessons) — it drafts (`.draft.md` / `.update.md` / `.triage.md`), never publishes canonical entries; humans review and promote. Entries can also be hand-authored — see `README.md` for the workflow.

If you're an agent encountering a decision that has no covering pattern entry, **emit a candidate** in your output rather than silently making the decision. The curator (or a human) can promote the candidate to a real entry if it generalizes.
