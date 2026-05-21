# Step 3: Draft Frontmatter

You produce the YAML frontmatter for a new pattern entry. Many fields are deterministic from step 1 + step 2 outputs and the source filename — you don't invent them. The fields that require judgment are `applies_when`, `contradicts`, and `related`.

## What's already decided (do NOT alter)

- **title** — `{CANDIDATE_TITLE}` (from step 1)
- **category** — `{TARGET_CATEGORY}` (from step 1)
- **status** — set to `validated` only if `empirical_receipts` from step 2 is non-empty AND those receipts cite a measured outcome (numbers, A/B comparison, judge scores). Otherwise `experimental`.
- **last_updated** — `{TODAY}` (caller injects)
- **source_findings** — if the source filename matches `findings/NN-*.md`, set to `["findings/NN-*.md"]`. Otherwise empty.
- **source_external** — if the source is an external doc/URL/builder report, set to `["<short citation>"]`. Otherwise empty.
- **snapshot_date** — set ONLY for `comparative-survey` body shape (these date faster). Otherwise null.

## What you decide

### `applies_when` — workloads + constraints

Both lists drive how downstream agents (inception's proposers) filter this entry. Be specific, not generic.

- **workloads** — kinds of work where this pattern applies. Examples from existing entries: `query-response`, `single-question-end-to-end`, `conversational`, `multi-agent-with-extractors`, `chained-pipeline-with-orchestrator`, `salesforce-resident-agents`. Use kebab-case slugs.
- **constraints** — situational requirements that make this pattern fit (or rule it out). Examples: `simplicity-prized`, `low-latency-target`, `enterprise-governance-non-negotiable`, `team-on-salesforce`.

Aim for 2-4 entries each. Padding gets ignored downstream; specificity helps.

### `contradicts` — slugs of patterns this one directly conflicts with

Look at the existing entries in `EXISTING_ENTRIES` below. If this new entry is a counter-position to one of them (e.g., a new "cheap-cascade IS worth it" entry would contradict `anti-patterns/cheap-cascade-orchestrator-compensation`), list the slug here as `<category>/<slug>`. Most entries have an empty list — don't force it.

### `related` — slugs of patterns this one references / extends / complements

Same `<category>/<slug>` format. Should reflect actual conceptual relationships, not "everything in the same category." Aim for 1-4 entries.

## Inputs

### From step 1 (classification)
```json
{CLASSIFICATION_JSON}
```

### From step 2 (extracted content)
```json
{EXTRACTED_PATTERN_JSON}
```

### Source filename
`{SOURCE_FILENAME}`

### Existing entries (to inform `related` and `contradicts`)
```
{EXISTING_ENTRIES}
```
(Each line: `<category>/<slug>` — title — one-line summary)

### Today's date
`{TODAY}`

## Output

Return ONLY a JSON object matching `PatternFrontmatter`:

```json
{
  "title": "<from step 1, verbatim>",
  "category": "<from step 1, verbatim>",
  "status": "validated | experimental",
  "last_updated": "{TODAY}",
  "source_findings": ["..."],
  "source_external": ["..."],
  "applies_when": {
    "workloads": ["..."],
    "constraints": ["..."]
  },
  "contradicts": ["..."],
  "related": ["..."],
  "superseded_by": [],
  "reference": null,
  "snapshot_date": null
}
```
