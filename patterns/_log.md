# Patterns Audit Log

Append-only record of additions, edits, status changes, and deprecations. Hand-maintained during the gold-standard seed; auto-appended by the `patterns_curator` agent in Phase 2+.

---

## 2026-05-20 (evening — convention loosening)

Two rules in the previous afternoon refactor were over-prescriptive on second-pass review:

1. **Line-count target (~30–50 lines).** Useful as a forcing function against my own first-pass bloat. Bad as a codified rule — the curator agent could learn "compress to 50 no matter what." Replaced with the principle "every line earns its place" — length follows content, not the other way around. Some entries will be 30 lines; some warranting real complexity will be 100+.

2. **Strict 5-section body template.** Suits operational-decision entries (architectures, anti-patterns, decision-guides), but boxes out comparative surveys, theoretical foundations, historical retrospectives, code-pattern entries, and open-questions entries — all of which are legitimate knowledge types this base should be able to hold. Reframed as a *suggested default template* with explicit alternative shapes named for other knowledge types. Frontmatter stays standardized (queries depend on it); body adapts to what the knowledge actually is.

Specific changes:

- **EDIT** `patterns/README.md` — split authoring conventions into "Mandatory" / "Suggested defaults" / "Principle, not rule" sections. Added a table mapping knowledge types to body shapes. Replaced "~30–50 lines" target with the line-earns-its-place principle.
- **EDIT** `patterns/SKILL.md` — same loosening applied to the agent-facing entry-shape section. Defaults preserved; flexibility explicit.

No existing entries are changed by this update. The 5 seeded entries are operational-decision entries that fit the default template; the loosening is about what's *allowed*, not what's *required*.

---

## 2026-05-20 (afternoon — gold-standard refactor)

Restructure pass on the initial 5 seed entries based on feedback from Andrew. Three problems fixed:

1. **README dual-audience.** The original `README.md` mixed human onboarding with agent navigation instructions. Split into `README.md` (humans, trimmed to ~50 lines) and `SKILL.md` (agent navigation, ~50 lines).
2. **Source-flavored naming.** `lessons-from-builders/bala-data-summary-not-raw-rows.md` encoded the source builder in the filename and category. The curator agent would have pattern-matched "name files by source" as a rule. Fix: renamed the file to `anti-patterns/truncated-data-summary.md` (content-named, topical category). Deleted the `lessons-from-builders/` directory. Attribution to Bala lives in `source_external:` frontmatter and a one-line origin credit in the body.
3. **Dual-purpose entry bodies.** Each entry conflated knowledge (agent payload at decision time) with justification (human-review backstory + empirical receipts). Token waste at every consultation. Fix: trimmed all 5 entries to ~30–50 lines (one-paragraph summary → Use when → Don't use when → Key gotchas → Empirical anchor). Created `chained-pipeline.reference.md` for the one entry with substantive non-source-resident content (deprecation history + where-still-alive). Other 4 entries have no reference companion — source citations in frontmatter do the linking work.

Specific changes:

- **EDIT** `patterns/README.md` — trimmed 119 → ~50 lines; humans-only
- **CREATE** `patterns/SKILL.md` — directory navigation for agents (~50 lines)
- **REWRITE** `patterns/architectures/adversarial-decomposition.md` — 95 → 35 lines
- **REWRITE** `patterns/architectures/single-agent-react.md` — 113 → 40 lines
- **REWRITE** `patterns/architectures/chained-pipeline.md` — 103 → 40 lines
- **CREATE** `patterns/architectures/chained-pipeline.reference.md` — full deprecation history + where the pattern is still alive (extracted from the previous monolithic entry)
- **REWRITE** `patterns/anti-patterns/definitions-without-context.md` — 123 → 35 lines
- **MOVE+RENAME** `patterns/lessons-from-builders/bala-data-summary-not-raw-rows.md` → `patterns/anti-patterns/truncated-data-summary.md` — 148 → 50 lines
- **DELETE** `patterns/lessons-from-builders/` directory (now empty)
- **EDIT** `patterns/_index.md` — reflect new structure
- **EDIT** `patterns/_log.md` — this entry

The refactor preserves the Karpathy LLM-wiki spirit (continuously curated knowledge articles, ingest/query/lint workflow, source-tracked, status-managed) while borrowing the Anthropic skill mechanics (lean primary file, structured frontmatter, optional supplementary reference). The `SKILL.md` filename is reserved for directory-level navigation — pattern entries are knowledge, not invocable capabilities, and don't use that filename.

---

## 2026-05-20 (morning — initial seed)

- **CREATE** `patterns/README.md` (initial scaffold; superseded by afternoon trim)
- **CREATE** `patterns/_index.md` (initial scaffold)
- **CREATE** `patterns/_log.md` (this file)
- **CREATE** `patterns/architectures/adversarial-decomposition.md` (gold-standard seed; from findings/05)
- **CREATE** `patterns/architectures/single-agent-react.md` (gold-standard seed; from findings/01 + Bala's empirical choice)
- **CREATE** `patterns/architectures/chained-pipeline.md` (gold-standard seed, deprecated; from findings/01)
- **CREATE** `patterns/anti-patterns/definitions-without-context.md` (gold-standard seed; from Bala's bca_framework lesson)
- **CREATE** `patterns/lessons-from-builders/bala-data-summary-not-raw-rows.md` (gold-standard seed; superseded the same day by the refactor — see afternoon entry)

Phase 1 of the patterns seed per `plans/07-patterns-knowledge-base.md`. Hand-authored by Claude as the empirical reference set the `patterns_curator` agent will be validated against in Phase 2.
