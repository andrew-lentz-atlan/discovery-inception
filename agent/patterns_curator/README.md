# agent/patterns_curator — the patterns/ knowledge-base curator agent

Companion agent to discovery-inception. Maintains the `patterns/` knowledge base via four operations: **ingest**, **promote**, **query**, **lint**. Inspired by Karpathy's LLM-maintained wiki gist (https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

## Status

**`ingest` is a skeleton** (step 1 implemented; steps 2-5 stubbed). **`promote` is shipping** (Loop 3 from plans/10 — cross-session knowledge promotion). `query` and `lint` are not yet built.

## Why this exists

The `patterns/` directory holds curated knowledge about agentic architectures, skill designs, anti-patterns, harnesses, decision guides. Without a curator, every new entry has to be hand-authored — high friction, inconsistent, slow.

The curator agent ingests source materials (findings docs, external research, builder reports) and produces draft pattern entries that match the gold-standard shape established in Phase 1 (`patterns/` seed entries authored 2026-05-20).

## Operations

### `ingest <source>`

Takes one source artifact (markdown file, URL, or repo path) and produces a draft pattern entry. The draft goes through several deterministic steps:

1. **classify_source** — what kind of pattern does this source teach? Returns target `category` (architectures / anti-patterns / skill-design / harnesses / decision-guides), `body_shape` (operational-decision / code-pattern / comparative-survey / theoretical / historical / open-questions), and a confidence.
2. **extract_pattern** — pull out the rule, when it applies, when it doesn't, gotchas, empirical receipts. *(stub)*
3. **draft_frontmatter** — populate the standardized YAML fields. *(stub)*
4. **draft_body** — write the body using the appropriate body shape. *(stub)*
5. **validate** — does the draft have a frontmatter, summary, and (for `validated` status) at least one empirical receipt? *(stub)*

Drafts are written to `patterns/<category>/<slug>.draft.md` for human review before promotion to the canonical filename.

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

### `query <filter>` *(not yet built)*

Query the knowledge base by structured filter. Surfaces matching entries for an agent at decision time. Will be wired up after ingest is mature.

### `lint` *(not yet built)*

Periodic review for staleness, contradictions, duplicates, orphaned receipts. Will be wired up after ingest is mature.

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
