# patterns/

> ⚠️ **Work in progress — please audit and share opinions.**
>
> This knowledge base is actively being designed. Many entries are marked
> `status: draft` and have been validated against a small number of real
> inception runs (n=2 so far: an SE copilot use case and an analyst copilot use
> case). Critique is more valuable than approval — if an entry's framing
> is wrong, misleading, or missing context, please flag it. If a pattern
> you'd expect to see isn't here, please name it. The whole point of
> externalizing opinions into a versioned substrate is making them
> easier to challenge.
>
> Specifically welcome:
> - Disagreements with the 5-class taxonomy (`decision-guides/what-kind-of-agent-are-you-building`)
> - Pushback on the Atlan context-layer entries (`skill-design/atlan-*`)
> - Counter-examples to the anti-patterns
> - Missing harnesses, missing decision points, missing failure modes
>
> Drop comments inline, raise issues against the repo, or flag in `#bu-ai`.

Curated knowledge base of agentic patterns: architectures, skill-design choices, anti-patterns, harness comparisons, decision guides. Externalizes design opinions out of agent prompts and into a versioned, queryable substrate.

**Inspired by:** Karpathy's LLM-maintained wiki gist (https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

## Why this directory exists

Prompts encode invariants. This directory encodes opinions. When the field shifts, entries update; prompts stay stable. Contrast with the prior pattern where opinions baked into prompts went stale silently.

## Status

**Phase 1 gold-standard seed:** complete (5 hand-authored entries).

**Phase 1 expansion (2026-05-29):** ~17 additional entries staged. Adds per-framework harness deep-dives (Claude Agent SDK, LangGraph, OpenAI Agents SDK, Pydantic AI, Cortex, Genie), the 5-class system taxonomy, 4 new anti-patterns, and 4 Atlan context-layer entries. Most are marked `status: draft` — they pass internal sanity checks against n=2 real inception comparison runs but haven't been audited by peers yet. That's the prompt for the WIP banner above.

Phase 2 shipped the curator's `ingest` operation (plus `promote` and `audit` — see `agent/patterns_curator/README.md`); validating ingest by reproducing these seed entries from their source materials remains the standing target. Phase 3 has the curator ingest the remaining ~20 entries (more harnesses, more anti-patterns, builder lessons, decision guides).

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
- `<category>/<entry>.{draft,update,contested,candidate,triage}.md` — curator working files awaiting human review/promotion (see `agent/patterns_curator/README.md`); not canonical, not listed in `_index.md`

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
| `draft` | Authored, internally sanity-checked, awaiting peer audit. Treat as opinionated-but-unvalidated. Most Phase 1 expansion entries land here. |
| `deprecated` | Once valid, now superseded — kept readable for traceability. Follow `superseded_by:` pointer |

## Adding entries (for now, by hand)

1. Pick the category subfolder by what the entry teaches
2. Write the YAML frontmatter first (forces specificity about applicability)
3. Body: pick the shape that fits the knowledge (default template suits most operational-decision entries)
4. Add a `.reference.md` companion only if justified
5. Append a row to `_index.md`
6. Append a dated entry to `_log.md`

The `patterns_curator` agent's `ingest` now automates steps 1–4 from source materials (output lands as `.draft.md` / `.update.md` / `.triage.md`, never canonical `<slug>.md`); humans review and promote before an entry becomes canonical.
