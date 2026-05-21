# patterns/

Curated knowledge base of agentic patterns: architectures, skill-design choices, anti-patterns, harness comparisons, decision guides. Externalizes design opinions out of agent prompts and into a versioned, queryable substrate.

**Design:** `plans/07-patterns-knowledge-base.md`.
**Inspired by:** Karpathy's LLM-maintained wiki gist.

## Why this directory exists

Prompts encode invariants. This directory encodes opinions. When the field shifts, entries update; prompts stay stable. Contrast with the prior pattern where opinions baked into prompts went stale silently — see `plans/09-context-debt-migration-backlog.md`.

## Status

**Phase 1 (gold-standard seed):** complete — 5 hand-authored entries serving as the reference target for the eventual `patterns_curator` agent.

Phase 2 builds the curator's `ingest` operation and validates it by reproducing these seed entries from their source materials. Phase 3 has the curator ingest the remaining ~20 entries (harnesses, more anti-patterns, builder lessons, decision guides).

## How to consume this directory

- **Agents** (curator, inception sub-agents, mega-agent): read `SKILL.md` for navigation instructions, filtering, and query patterns.
- **Humans** (reviewers, authors, project maintainers): browse entries by category. `_index.md` lists every entry with status + last-updated.

## File layout

- `README.md` — this file (humans)
- `SKILL.md` — agent navigation
- `_index.md` — entry list
- `_log.md` — audit trail
- `<category>/<entry>.md` — knowledge entries (lean, agent-consumable)
- `<category>/<entry>.reference.md` — supplementary content when justified (rare; reserved for substantive non-source-resident detail like deprecation history)

## Authoring conventions

- **Name files by content, not by source.** A lesson from builder X goes in the topical category (`skill-design/`, `anti-patterns/`, etc.) by what it teaches. Attribution lives in `source_external:` frontmatter + optional one-line credit in the body.
- **Lean by default.** Entries target ~30–50 lines. Frontmatter does the structured query work; body does the operational guidance. If a section grows past the lean target, ask whether it belongs in a `.reference.md` companion instead.
- **One file per entry by default.** A `.reference.md` companion exists only when there's substantive content that genuinely doesn't fit the primary file AND isn't already in the cited source.
- **Empirical anchors are mandatory for `validated`.** Without at least one cited finding or external source, status is `experimental`.

## Status semantics

| status | meaning |
|---|---|
| `validated` | Empirically supported; default choice for that decision |
| `experimental` | Promising but single-source evidence or anecdotal |
| `deprecated` | Once valid, now superseded — kept readable for traceability. Follow `superseded_by:` pointer |

## Adding entries (for now, by hand)

1. Pick the category subfolder by what the entry teaches
2. Write the YAML frontmatter first (forces specificity about applicability)
3. Body: one-paragraph summary → Use when → Don't use when → Key gotchas → Empirical anchor
4. Add a `.reference.md` companion only if justified
5. Append a row to `_index.md`
6. Append a dated entry to `_log.md`

When the `patterns_curator` agent ships, steps 1–4 become automated from source materials; humans review before commit.
