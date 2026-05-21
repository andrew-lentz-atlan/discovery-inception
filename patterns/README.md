# patterns/

Curated knowledge base of agentic patterns: architectures, skill-design choices, anti-patterns, harness comparisons, decision guides. Externalizes design opinions out of agent prompts and into a versioned, queryable substrate.

**Inspired by:** Karpathy's LLM-maintained wiki gist (https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

## Why this directory exists

Prompts encode invariants. This directory encodes opinions. When the field shifts, entries update; prompts stay stable. Contrast with the prior pattern where opinions baked into prompts went stale silently.

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

### Mandatory

- **YAML frontmatter** with `title`, `category`, `status`, `last_updated`, `applies_when`, and source citations. The frontmatter is what makes entries queryable; missing fields break query behavior.
- **One-paragraph summary** as the body opener. First thing an agent reads.
- **Files named by content, not by source.** A lesson from builder X goes in the topical category by what it teaches. Attribution lives in `source_external:` frontmatter + optional one-line credit in the body.
- **Empirical receipts for `validated` status.** Without at least one cited finding or external source, status defaults to `experimental`.

### Suggested defaults

- **Operational-decision body template** (the shape used by the seeded entries): summary → Use when → Don't use when → Key gotchas → Empirical anchor. Suits architectures, anti-patterns, decision-guides. Use as a starting template; deviate when the content warrants.
- **One file per entry by default.** A `.reference.md` companion exists only when there's substantive content that genuinely doesn't fit the primary file AND isn't already in the cited source. Most entries won't have one.

### Principle, not rule: length

Every line earns its place. No ceremony, no padding, no recapitulation of content that lives in the cited source. A simple pattern might be 30 lines; a pattern with real implementation complexity, nuanced applicability, or multiple variants might warrant 100+. **Length follows the content, not the other way around.** The discipline is what NOT to include, not how many lines to hit.

### Principle, not rule: body shape

Different kinds of knowledge get different body shapes. The operational-decision template above suits the seeded entries because they're about *when to use what*. Other knowledge types need other shapes:

| Knowledge type | Body shape that fits |
|---|---|
| Architecture / anti-pattern / decision-guide | Use when / Don't use when / Gotchas / Empirical anchor *(the default template)* |
| Comparative survey (e.g., "15 harnesses compared") | Tables + per-item analysis + cross-cutting observations |
| Theoretical / first-principles | Premises / Implications / Open questions |
| Historical retrospective | Trajectory / What came before / What it enabled |
| Code-pattern (skill-design with implementation example) | Pattern / Code / Variants / Anti-pattern callouts |
| Open-questions entry | Question list / What we'd test / Current best guesses |

When authoring (or when the curator authors), pick the shape that fits the knowledge. The frontmatter stays standardized; the body adapts.

## Status semantics

| status | meaning |
|---|---|
| `validated` | Empirically supported; default choice for that decision |
| `experimental` | Promising but single-source evidence or anecdotal |
| `deprecated` | Once valid, now superseded — kept readable for traceability. Follow `superseded_by:` pointer |

## Adding entries (for now, by hand)

1. Pick the category subfolder by what the entry teaches
2. Write the YAML frontmatter first (forces specificity about applicability)
3. Body: pick the shape that fits the knowledge (default template suits most operational-decision entries)
4. Add a `.reference.md` companion only if justified
5. Append a row to `_index.md`
6. Append a dated entry to `_log.md`

When the `patterns_curator` agent ships, steps 1–4 become automated from source materials; humans review before commit.
