# agent/patterns_curator — the patterns/ knowledge-base curator agent

Companion agent to discovery-inception. Maintains the `patterns/` knowledge base via four operations: **ingest**, **promote**, **query**, **lint**. Inspired by Karpathy's LLM-maintained wiki gist (https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

## Status

**`ingest` is shipping** (all 6 steps: classify → extract → frontmatter → body → overlap_check → validate, with output routing to `.draft.md` / `.update.md` / `.contested.md` / `.triage.md` based on the triage decision). **`promote` is shipping** (Loop 3 from plans/10 — cross-session knowledge promotion). **`audit` is shipping** (deterministic lint + semantic clustering for drift detection). `query` (interactive retrieval) is not yet built — humans currently read the wiki directly or browse via `_index.md`.

## Why this exists

The `patterns/` directory holds curated knowledge about agentic architectures, skill designs, anti-patterns, harnesses, decision guides. Without a curator, every new entry has to be hand-authored — high friction, inconsistent, slow.

The curator agent ingests source materials (findings docs, external research, builder reports) and produces draft pattern entries that match the gold-standard shape established in Phase 1 (`patterns/` seed entries authored 2026-05-20).

## Operations

### `ingest <source>`

```bash
uv run python -m agent.patterns_curator.run \
    --source findings/08-cheap-cascade-gpt4o-mini-doesnt-pan-out.md
```

Takes one source artifact and produces a draft pattern entry. Six steps:

1. **classify_source** — what kind of pattern does this source teach? Returns target `category` (architectures / anti-patterns / skill-design / harnesses / decision-guides), `body_shape` (operational-decision / code-pattern / comparative-survey / theoretical / historical / open-questions), candidate title + slug, confidence.
2. **extract_pattern** — body-shape-aware extraction. Pulls summary, use_when, dont_use_when, gotchas, empirical_receipts, code_excerpts, survey_items as appropriate for the body shape.
3. **draft_frontmatter** — populates YAML fields. Most are deterministic from steps 1-2; `applies_when`, `related`, `contradicts` are LLM-decided. `source_hash` (SHA256 of source) is added for audit-time drift detection.
4. **draft_body** — body-shape-templated markdown rendering. Six templates (one per body shape) keep entries structurally consistent with existing ones.
5. **overlap_check** — runs after the body is drafted, produces a `TriageReport`. Surfaces extension candidates (existing entries this should merge into) and contradiction candidates (existing entries this directly opposes). **Convergence-not-fragmentation**: when uncertain, prefers `update_existing` over `create_new`.
6. **validate** — deterministic lint (frontmatter required fields, date format, fence balance, reference integrity, body length sanity, status-vs-receipts consistency).

**Output routing** (from triage decision):

| Action | Where it lands |
|---|---|
| `create_new` | `patterns/<category>/<slug>.draft.md` (+ `.triage.md` sidecar if any overlap surfaced) |
| `update_existing` | `patterns/<category>/<existing_slug>.update.md` + `.triage.md` (proposed merge into the existing entry, diff against original) |
| `contested` | `patterns/<category>/<existing_slug>.contested.md` + `.triage.md` (direct contradiction with existing entry, both versions side-by-side for human reconciliation) |
| `needs_human_review` | `<slug>.triage.md` only (no draft — analysis surfaced for human decision) |

Drafter-not-publisher: the curator never writes to canonical `<slug>.md`. Humans review the draft / update / contested file and promote when ready.

### `promote` (Loop 3 — cross-session knowledge promotion)

Distinct from `ingest`: where ingest reads ONE source and produces ONE draft, promote reads MANY per-session feedback artifacts and produces zero-or-more candidate drafts based on **recurrence**.

```
uv run python -m agent.patterns_curator.promote
uv run python -m agent.patterns_curator.promote --min-sessions 2 --dry-run
uv run python -m agent.patterns_curator.promote \
    --feedback-dir agent/inception/sample_feedback \
    --feedback-dir sessions/
```

Pipeline (per plans/10):

1. **discover + parse** — scan `sessions/` and `agent/inception/sample_feedback/` (or the dirs given via `--feedback-dir`) for `feedback.{yaml,yml,json}` files; extract atomic `FeedbackSignal`s.
2. **classify** — `specific_vs_generic_classifier` (per-signal, parallel). Specific lessons stay session-scoped and drop here. Generic ones survive.
3. **cluster** — `signal_clusterer` groups generic signals across sessions by theme. Cross-stage clusters (discovery + inception teach the same lesson) are flagged.
4. **threshold** — `≥3` distinct sessions per cluster by default (configurable via `--min-sessions`). Below-threshold clusters are recorded for diagnostics but don't promote.
5. **duplicate-check** — slug match against existing pattern entries. Semantic overlap is left for human review.
6. **draft** — produces a candidate `PatternEntry` per surviving cluster, written to `patterns/<category>/<slug>.candidate.md`. Empirical anchor cites the originating session_ids.

Outputs:
- `patterns/<category>/<slug>.candidate.md` per promoted cluster (review + rename to `.md` to ratify).
- `patterns/.promotion_runs/<ts>.json` audit-trail report (gitignored).

The recurrence threshold + the lean-toward-specific classifier bias are the two guardrails against over-promotion: single-session quirks never reach `patterns/`.

### `audit`

```bash
uv run python -m agent.patterns_curator.audit
uv run python -m agent.patterns_curator.audit --staleness-days 60
uv run python -m agent.patterns_curator.audit --skip-semantic
```

Periodic hygiene pass. Two phases:

1. **Deterministic** — frontmatter integrity, broken references (`related:` / `contradicts:` / `superseded_by:` pointing at non-existent entries), fence imbalance, staleness (`last_updated` past threshold), source-hash drift (if `source_hash` is set and the source file is reachable + has changed since ingest, flag for re-ingest).
2. **Semantic** (LLM call) — clusters entries by lesson, flags duplicates ("API best practices" vs "SDK best practices" — different names, same content) and contradictions (two entries making opposing claims). Convergence principle as the explicit bias — false positives are worse than false negatives.

Output: `patterns/.audit_runs/<timestamp>/report.md` (human) + `report.json` (machine). Drafter-not-publisher: audit never edits canonical entries; produces a findings list for human review.

### `query <filter>` *(not yet built)*

Query the knowledge base by structured filter. Surfaces matching entries for an agent at decision time. Will be wired up after ingest is mature.

## Validation target

The curator's `ingest` operation will be validated by feeding it the source materials behind the gold-standard seed and checking whether its outputs match. Specifically:

- Feed `findings/05` → does the draft match `patterns/architectures/adversarial-decomposition.md`?
- Feed Bala's repo README (or specifically the §2 / §3 sections on his lessons) → do the drafts match `patterns/anti-patterns/definitions-without-context.md` and `patterns/anti-patterns/truncated-data-summary.md`?
- Feed the harness research doc → does the draft match `patterns/harnesses/landscape-2026-may.md`?

A reasonable match is ~80% on structure (right category, right body shape, all required frontmatter fields present, body sections present). Content-equivalence is a stretch goal.

## Files

- `__init__.py`
- `README.md` — this file
- `schemas.py` — Pydantic models for the intermediate step outputs and the final draft entry (covers both `ingest` and `promote`)
- `prompts/` — one prompt per pipeline step. Prefix `promote_*.md` for the cross-session pipeline.
- `run.py` — `ingest` CLI entry point
- `promote.py` — `promote` CLI entry point (Loop 3)
- `audit.py` — `audit` CLI entry point (hygiene + drift detection)
