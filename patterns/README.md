# patterns/ — the agentic patterns knowledge base

> Design: `plans/07-patterns-knowledge-base.md`.

The substrate that externalizes architectural opinions out of agent prompts and into a queryable, versioned, citation-friendly knowledge base. Inspired by Karpathy's LLM-maintained wiki gist.

**The principle this enforces:** prompts encode invariants; this directory encodes opinions. When the field shifts, entries update — prompts stay stable.

---

## Status

**Seeded by hand (gold-standard pass) — 2026-05-20.**

5 entries authored manually by Claude as the empirical reference for what good entries look like. These are the gold standard that the eventual `patterns_curator` agent will be validated against — when the curator ingests the same source materials, does it produce entries that match this reference?

Seed entries:
- `architectures/adversarial-decomposition.md` (from `findings/05`)
- `architectures/single-agent-react.md` (from `findings/01` + Bala's empirical choice)
- `architectures/chained-pipeline.md` (from `findings/01` — the rejected alternative)
- `anti-patterns/definitions-without-context.md` (from Bala's `bca_framework must travel` lesson)
- `lessons-from-builders/bala-data-summary-not-raw-rows.md` (from Bala's truncation lesson)

After Phase 2 (curator build) and Phase 3 (curator ingests the rest), this set grows to ~25 entries.

---

## How to read an entry

Every entry is a markdown file with YAML frontmatter:

```yaml
---
title: Adversarial Decomposition
category: architectures
status: validated              # validated | experimental | deprecated
last_updated: 2026-05-13
source_findings: [findings/05-v08-probe-sharpener-and-tensions.md]
source_external: []
applies_when:
  workloads: [structured-extraction, conversational, quality-critical]
  constraints: []
contradicts: [chained-pipeline]
related: [single-agent-react, skill-design/adversarial-review]
---
```

The **frontmatter** makes entries queryable by agents at decision time. The **body** makes them readable by humans. Every entry must have both.

Body structure:

```markdown
# <Title>

## When to use
[1–3 paragraphs]

## When NOT to use
[1–2 paragraphs]

## Empirical receipts
[citations to findings/ or external research that validate this]

## Implementation gotchas
[bullet points]

## Variants & related patterns
[cross-references]
```

---

## Status values

| Value | Meaning |
|---|---|
| `validated` | Backed by at least one `findings/` doc OR two independent external sources OR observed in production at scale |
| `experimental` | Promising, but evidence is single-source or anecdotal |
| `deprecated` | Once validated, now superseded — kept readable for traceability. New consumers should follow the `superseded_by` pointer |

---

## How to author a new entry

1. Identify a source — a finding, an external doc, a builder lesson
2. Pick the category subfolder
3. Write frontmatter first (forces specificity about applicability)
4. Body sections in the order above
5. Cross-link to related entries; add `contradicts:` for entries that argue the opposite
6. Update `_index.md` to include the new entry
7. Append a row to `_log.md` capturing the addition

When the `patterns_curator` agent ships, steps 1-6 become automated for findings/external sources; humans review before commit.

---

## When to read this directory

- **Building an agent?** Inception's sub-agents will consult these at decision time (per `plans/08-inception-agent.md`). Citing the pattern in your design rationale is encouraged for traceability.
- **Editing a prompt?** Check whether the opinion you're encoding should live here instead of in the prompt (per `plans/09-context-debt-migration-backlog.md`).
- **Authoring a finding?** When the finding validates a pattern that doesn't have an entry yet, write the entry alongside the finding. Findings stay as empirical receipts; entries are the reusable distillations.

---

## Files in this directory

- `_index.md` — auto-discoverable list of all entries with status + last-updated. Regenerated when entries change.
- `_log.md` — audit trail of additions, edits, status changes, deprecations.
- `<category>/<entry>.md` — the actual pattern entries.
- `README.md` — this file.

---

## What this directory does NOT do

- It's not exhaustive. We curate what we use, not what exists. The field has thousands of patterns; we'll have dozens.
- It doesn't replace `findings/`. Findings are empirical receipts; patterns are reusable distillations. Both stay.
- It doesn't auto-update from arbitrary internet content. Sources are vetted.
- It doesn't enforce that every agent decision cites a pattern — strong norm, not hard requirement.
