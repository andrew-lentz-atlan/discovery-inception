# Patterns Audit Log

Append-only record of additions, edits, status changes, and deprecations. Hand-maintained during the gold-standard seed; will be auto-appended by the `patterns_curator` agent once it ships.

---

## 2026-05-20

- **CREATE** `patterns/README.md` — initial scaffold
- **CREATE** `patterns/_index.md` — initial scaffold
- **CREATE** `patterns/_log.md` — this file
- **CREATE** `patterns/architectures/adversarial-decomposition.md` (gold-standard seed; status: validated; source: findings/05)
- **CREATE** `patterns/architectures/single-agent-react.md` (gold-standard seed; status: validated; sources: findings/01 + Bala's empirical choice)
- **CREATE** `patterns/architectures/chained-pipeline.md` (gold-standard seed; status: deprecated; source: findings/01 — kept readable as the rejected alternative)
- **CREATE** `patterns/anti-patterns/definitions-without-context.md` (gold-standard seed; status: validated; source: Bala's `bca_framework must travel` lesson)
- **CREATE** `patterns/lessons-from-builders/bala-data-summary-not-raw-rows.md` (gold-standard seed; status: validated; source: Bala's `data_summary not raw rows` lesson)

**Notes on this batch:**
- Authored by hand (Claude in conversation with Andrew) as the Phase 1 gold-standard pass per `plans/07-patterns-knowledge-base.md`.
- These are the empirical reference set the `patterns_curator` agent will be validated against in Phase 2.
- Initial coverage skews toward architectures and Bala's lessons because those have the strongest existing source material (findings/05 and Bala's repo). Harnesses + decision-guides come in Phase 3 when the curator ingests at scale.
