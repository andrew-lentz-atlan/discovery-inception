---
title: Fabricated citations (slug hallucination in synthesizer steps)
category: anti-patterns
status: validated
last_updated: 2026-05-29
source_findings:
  - findings/09-iteration-receipts-from-atlan-se-copilot.md
source_external: []
applies_when:
  workloads: [synthesizer-step, multi-step-aggregation, audit-trail-generation]
  constraints: [citation-required, pattern-library-references]
contradicts: []
related:
  - anti-patterns/definitions-without-context
snapshot_date: 2026-05-29
---

# Fabricated citations (slug hallucination in synthesizer steps)

A step that aggregates upstream JSON into prose invents plausible-looking entry slugs that don't resolve to real files. The model isn't lying — it's pattern-matching what a citation "should" look like in context, and emitting that pattern even when no concrete upstream slug grounds it.

Two real examples from the same inception run, both in `design_rationale.md` (step 5c):

| Cited slug | Reality |
|---|---|
| `architectures/inner-pipeline` | Real entry exists at `skill-design/inner-pipeline` — category was hallucinated |
| `harnesses/langraph-deep-dive` | No such entry; the real one is `langgraph-deep-dive` (extra `g`). Pure typo-style fabrication |
| `harnesses/cortex-agents-deep-dive` | No such entry; the real one is `cortex-deep-dive`. Model fabricated a more specific variant based on the title content |

All three slugs *look* like they could exist. Markdown renderers don't error on broken links. Citation counters that don't verify against the filesystem treat fabricated citations as real lift. **Silent fabrication is the failure mode.**

## How it happens

Three mechanisms identified, in increasing order of subtlety:

1. **Free-form synthesis.** The synthesizer prompt says "cite specific patterns" but doesn't constrain WHICH patterns are valid. The model fills the cite slot with whatever slug feels right.

2. **Title-to-slug derivation.** When a deep-dive's title contains the product name (e.g., *"Snowflake Cortex Agents / Cortex Analyst — Builder's Deep Dive"*), the model derives the slug by snake-casing the title's leading subject. Result: `cortex-agents-deep-dive` instead of the actual `cortex-deep-dive`.

3. **Category cross-confusion.** When two categories have similar shapes (e.g., `architectures/` and `skill-design/`), the model places an entry in the category that "fits the body shape" of the citation, not the category where the file actually lives. `inner-pipeline` lives at `skill-design/` because it describes how to structure a SKILL.md body; cited as `architectures/inner-pipeline` because the synthesizer is talking about architecture.

## Why it matters

Three downstream consequences:

1. **Builders following the breadcrumbs hit dead ends.** A reviewer reading the design_rationale clicks the cited entry and gets 404. Worse, they may not check, and quietly assume the entry exists — internalizing a name that turns into the wrong reference later.

2. **Citation-count metrics inflate.** Naive citation counters (regex on `patterns/X/Y` patterns without file-existence checks) credit fabricated slugs as lift. The reported "20 citations to patterns content" might be 15 real + 5 fabricated. The lift looks bigger than it is.

3. **It's a use-case-mismatch signal.** Hallucinated slugs are not random — they cluster on use cases where the patterns library doesn't quite fit. A model with a confident pattern-anchored response cites real slugs. A model that's stretching cites slugs that *should* exist for this use case but don't. The fabrication rate is itself a "you have a gap in your patterns" signal that's otherwise invisible.

## How to prevent it

### Prompt-level (synthesizer step)

**Hard rule: citations come ONLY from upstream JSON, verbatim.** When a synthesizer prompt aggregates outputs from prior proposers, restrict citations to slugs that appear by exact match in:

- `selected_pattern_slug` fields
- `rejected_alternatives[].slug` fields
- Any explicit `patterns/...` paths in `rationale` fields
- The harness rationale's `pattern_slugs_cited` array (or equivalent)

If the model wants to make a point that no upstream slug supports, it must describe the concept in prose without a citation. This is the structural-impossibility approach — fabricated slugs become structurally impossible because the prompt forbids any slug not seen in the input.

### Verifier-level (tooling)

Citation counters MUST verify against the filesystem:

```python
for cat, slug in citations:
    entry_path = patterns_dir / cat / f"{slug}.md"
    if entry_path.exists():
        real_cites[key] += 1
    else:
        hallucinated_cites[key] += 1  # surface separately
```

Counting them separately surfaces the fabrication rate as a quality signal rather than burying it in the total.

### Pattern-library-level (when fabrication is signal)

When the same fabricated slug appears across multiple runs, the model is telling you "this entry *should* exist." Examples worth treating as backlog signals:

- Multiple sessions cite `architectures/graph-state-machine` even though no such entry exists → write the entry
- Multiple sessions cite `architectures/inner-pipeline` even though the entry lives at `skill-design/inner-pipeline` → consider creating a redirect or moving the entry

## Provenance

This anti-pattern was extracted from the P&G FHC iteration documented in findings/09. The first compare_inception run reported 20 → 20 citation parity between main and the patterns-deepening branch, which looked like no lift. After fixing the citation verifier to check file existence, the real number was 20 → 15 — actual citation count *dropped*, with 5 of the "new" citations being fabricated. The fabrication count is itself an honest signal that this use case (analyst-flavored data-resident workload) doesn't anchor as cleanly to our existing patterns as the SE co-pilot use case does.

## Hard rule for synthesizer prompts

Synthesizer prompts (steps that produce design_rationale, summary docs, audit trails, etc.) must:

1. **Forbid free-form citation.** "Cite only slugs that appear verbatim in the upstream JSON inputs."
2. **List concrete forbidden hallucination examples** in the prompt itself when known (e.g., "do NOT cite `langraph-deep-dive` — the entry is `langgraph-deep-dive`").
3. **Allow concept references without citations** as the escape hatch. "If a concept feels relevant but no upstream slug supports it, describe it in prose without a citation."
