# patterns/ production-entry contract

The standard every entry must meet. The curator's ingest drafts against it, the
audit lints against it, human review rejects against it. An entry that violates
a MUST does not merge; a SHOULD violation needs a stated reason.

Why this exists: the knowledge base is consumed two ways — loaded into the
inception pipeline's prompts (tokens must earn their place) and read by people
outside this project (entries must stand alone). Both consumers get the same
rule: **distilled, generalizable, evidenced content — no project narrative.**

---

## 1. Anatomy

Every entry MUST have frontmatter with: `title`, `category` (matching its
directory — see §6), `status` (see §2), `last_updated`, provenance fields
(§3), `applies_when` (workloads + constraints), `related` (real slugs only).

Body shape: a one-paragraph thesis first (what this entry claims and when it
applies), then the guidance (`Use when` / `Don't use when` or equivalent),
gotchas/failure modes, an `## Empirical anchor` or `## Provenance` section
where receipts exist, and hard rules for the pipeline where applicable.

## 2. Status semantics — the most-violated rule

- **`draft`** — a distillation not yet validated. ALL newly ingested entries
  are drafts, no exceptions. Research quality does not make an entry
  `validated`; use does.
- **`validated`** — MUST name its evidence: a `findings/NN` entry, a measured
  before/after run, or repeated confirmed use in real builds. "The sources were
  good" is not validation.
- **`experimental`** — plausible, deliberately speculative; selectable by the
  pipeline with a flag to the human.
- **`deprecated`** — an explicit rejection; the entry says what superseded it.

The curator MUST NOT self-assign `validated` at ingest time — enforced in
code, not prompt (the drafting model has overclaimed this in every sprint).

## 3. Provenance — anchors, not anecdotes

`findings/` is the episodic store; `patterns/` is the semantic store;
promotion is the consolidation gate between them.

- `source_findings` lists ONLY real `findings/NN-*.md` files.
- `source_external` lists talks/papers/docs with enough identity to locate
  them (author/venue; URL + date where they exist).
- Project-derived receipts are welcome IF they pass the **receipt test**:
  (a) generalizable — a reader outside this project learns from it;
  (b) quantified or concrete; (c) provenance-pointed (cites a findings/ entry
  or names the measurement). "Citation density swung 25→7 across identical
  runs" passes. "A real SE-agent output was called out for X" fails — that is
  narrative, and narrative lives in findings/, not here.
- Never fabricate an origin. If the source is a talk, say the talk; do not
  invent "internal findings."

## 4. Voice — timeless, third-person, self-contained

- **No first person.** "My read," "we found," "our pipeline" — rewrite as
  factual statements. (If the fact is about this product's pipeline, it
  belongs in the pipeline's docs, not a pattern entry.)
- **No roadmap tense.** Entries state what IS. "The pipeline should add
  signal X" goes stale the day X ships; write the resolved rule instead.
- **No project-context-required sentences.** Every sentence must be
  meaningful to a reader who has never seen this repo's history.
- Dated claims carry their date ("as of 2026-06"); surveys carry
  `snapshot_date`.

## 5. Citations

- Every cited entry is a full slug (`patterns/<category>/<name>.md`) that
  resolves to a real file. Inventing or near-missing a slug is the
  `fabricated-citations` anti-pattern.
- NEVER cite working-suffix files (§7). They are not part of the canonical KB.

## 6. Category ↔ directory consistency

Frontmatter `category` MUST equal the entry's parent directory. The audit
lints this. Slugs are kebab-case, descriptive, no redundant category prefix
inside the filename.

## 7. Working-file lifecycle

`.draft.md` (ingested, awaiting audit) → human/audit review → promotion
renames to `<slug>.md` + adds the entry to `_index.md`. Other suffixes:
`.update.md` (proposed change to an existing entry), `.contested.md`
(conflicts with an existing entry), `.candidate.md` (promotion candidate),
`.triage.md` (overlap-analysis sidecar), `.reference.md` (human-review
companion). Working-suffix files are EXCLUDED from the agent payload
(`load_pattern_category`) and from `_index.md` — promotion is the gate to
agent-visibility.

## 8. Review rejection list (what sends an entry back)

1. `validated` without named evidence (§2)
2. Anecdote in the body / narrative provenance (§3)
3. First-person or roadmap voice (§4)
4. A citation that doesn't resolve, or cites a working-suffix file (§5)
5. Category/directory mismatch (§6)
6. A claim a reader can't trace (no receipt, no source, no reasoning)
7. Overlap the triage should have caught (duplicates an existing entry's
   ground without citing or updating it)
