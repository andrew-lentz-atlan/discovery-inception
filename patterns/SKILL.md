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

Example query: "what architecture for a conversational workload where output quality matters?" → filter `category: architectures` + `applies_when.workloads contains conversational` + `applies_when.workloads contains quality-critical` → returns `adversarial-decomposition` + `single-agent-react`.

## Entry shape

Every entry has:

- **YAML frontmatter** — queryable metadata. Always present.
- **One-paragraph summary** — what the pattern is, in plain English.
- **`## Use when`** — bullet list. The decision-time payload.
- **`## Don't use when`** — bullet list. The boundary conditions.
- **`## Key gotchas`** — implementation pitfalls.
- **`## Empirical anchor`** — one paragraph citing supporting evidence (a finding, an external source, both).

Some entries have a `<entry-name>.reference.md` companion with deeper justification — deprecation history, full empirical comparisons, maintenance notes. **Consult only when needed for review or audit.** A `reference:` field in frontmatter signals when one exists.

## Naming conventions

- Files are named by **content**, not by source. A lesson from builder X goes in the topical category by what it teaches (`anti-patterns/truncated-data-summary.md`, not `lessons-from-builders/bala-truncation-lesson.md`).
- Attribution to a source builder lives in `source_external:` frontmatter and optionally a one-line credit in the body. Not the filename.
- `SKILL.md` is reserved for **directory-level navigation skills** (like this file). Pattern entries do not use the `SKILL.md` filename — they are knowledge articles, not skills.

## Status semantics

| status | meaning | retrieval default |
|---|---|---|
| `validated` | Empirically supported; default choice | returned by query |
| `experimental` | Promising but single-source / anecdotal | returned with flag |
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

The `patterns_curator` agent will handle ingest from raw sources (findings/, external research, builder lessons) once it ships. Until then, entries are hand-authored. See `README.md` for the authoring workflow.

If you're an agent encountering a decision that has no covering pattern entry, **emit a candidate** in your output rather than silently making the decision. The curator (or a human) can promote the candidate to a real entry if it generalizes.
