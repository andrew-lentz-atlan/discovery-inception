# Promote step 3: draft a candidate pattern entry

You are the patterns_curator drafting a candidate pattern entry from a recurring cross-session signal cluster. The candidate will be written to `patterns/<category>/<slug>.candidate.md` and reviewed by a human before becoming an entry.

## What to do

Read the cluster + its constituent signals + their generic classification, then produce a **draft pattern entry** matching the conventions used elsewhere in `patterns/`.

The entry must include:

1. **YAML frontmatter** with at minimum: title, category, status (always `experimental` for new candidates), last_updated (`{TODAY}`), source_findings (always empty for promotions), source_external (always empty), applies_when (workloads + constraints), contradicts (best guess), related (best guess).
2. **A body** matching the appropriate `body_shape`. For most promoted patterns this will be `operational-decision` (Use when / Don't use when / Key gotchas / Empirical anchor).
3. **An "Empirical anchor" section** that explicitly cites the recurrence — *"This pattern surfaced as a recurring lesson across N independent sessions (...)."* — and lists the originating session_ids. This citation is THE load-bearing receipt for the pattern.

## Output shape

```json
{
  "frontmatter": {
    "title": "<entry title>",
    "category": "<architectures | anti-patterns | skill-design | harnesses | decision-guides>",
    "status": "experimental",
    "last_updated": "{TODAY}",
    "source_findings": [],
    "source_external": [],
    "applies_when": {
      "workloads": ["<list>"],
      "constraints": ["<list>"]
    },
    "contradicts": [],
    "related": []
  },
  "body": "<full markdown body — use \\n for newlines>",
  "body_shape": "<one of: operational-decision | code-pattern | comparative-survey | theoretical | historical | open-questions>"
}
```

## Body conventions (operational-decision shape)

```
# <Title>

<One-paragraph summary of the pattern + why it matters.>

## Use when

- <bullet>
- <bullet>

## Don't use when

- <bullet>
- <bullet>

## Key gotchas

- **<short name>.** <explanation>
- **<short name>.** <explanation>

## Empirical anchor

This pattern surfaced as a recurring lesson across {N_DISTINCT_SESSIONS} independent
session(s). Originating session_ids:
- {SESSION_IDS_BLOCK}

Cluster theme: {CLUSTER_THEME}
Generalizes to: {GENERALIZES_TO}
```

Use the empirical anchor template verbatim; it makes downstream auditing of promotions auditable.

## Inputs

Cluster ID: {CLUSTER_ID}
Theme: {CLUSTER_THEME}
Generic kind: {GENERIC_KIND}
Generalizes to: {GENERALIZES_TO}
Crosses stages: {CROSSES_STAGES}
Distinct sessions: {N_DISTINCT_SESSIONS}

Constituent signals (each line shows session/stage/kind/content):

{SIGNALS_BLOCK}

## Output JSON only.
