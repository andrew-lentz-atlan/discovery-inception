# agent/patterns_curator — the patterns/ knowledge-base curator agent

Companion agent to discovery-inception. Maintains the `patterns/` knowledge base via three operations: **ingest**, **query**, **lint**. Inspired by Karpathy's LLM-maintained wiki gist (https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

## Status

**Skeleton.** This directory has the scaffolding (schemas, prompts, run.py) but only the `ingest` operation's first step (`classify_source`) is implemented at this stage. Other steps are stubbed; `query` and `lint` operations are not yet built.

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
- `schemas.py` — Pydantic models for the intermediate step outputs and the final draft entry
- `prompts/` — one prompt per pipeline step
- `run.py` — CLI entry point
