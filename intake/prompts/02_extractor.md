# Step 2: Extractor

You are extracting structured information about a workplace role from an unstructured source document. The document is of type `{ARTIFACT_TYPE}`.

{USE_CASE_CONTEXT}

## Hard rules
- **Extract only what the source supports.** If the document doesn't say it, don't include it. Hallucinated content will poison every downstream step.
- **Use the document's own language** for names where possible. If the document calls something a "tier-2 escalation," don't relabel it as "advanced support."
- **Specific over generic.** "Solutions Consultant manages implementation workstreams for enterprise customers" beats "the role works on customer projects." If the source is generic, the extraction should be empty rather than padded.
- **Empty is better than wrong.** If the document gives no escalation paths, return an empty list. Do not invent.
- **Every list field MUST be a JSON array, never a single string.** Even if you have only one item to put in `steps`, `inputs`, `criteria`, or `artifacts_passed`, wrap it as `["the one item"]` — not `"the one item"`. A single string in a list field is a structural error.

## What to extract

Produce a JSON object with these fields. Omit any field that the source doesn't support.

- `role_name` (string, required) — the canonical role name as the source uses it.
- `role_summary` (string, required) — 2-3 sentences on what the role exists to do, written in the source's own framing.
- `primary_outcomes` (list of strings) — measurable success states. If the source says "increase NRR" or "reduce time-to-first-value," capture those literally. If it only describes activities (not outcomes), leave empty.
- `typical_workflows` (list of objects) — named end-to-end flows. Each has:
    - `name` — short noun phrase
    - `purpose` — one sentence on why it exists
    - `trigger` — what initiates it
    - `steps` — ordered steps, as written or directly implied
    - `typical_duration` — only if mentioned
- `decision_criteria` (list of objects) — judgment moments. Each has:
    - `name` — short label
    - `inputs` — what information the role consults
    - `criteria` — rules or heuristics that govern the decision, as stated
    - `is_judgment` — true if criteria are partly subjective; false if rule-based
- `escalation_paths` (list of objects) — when and how the role hands off. Each has:
    - `trigger` — the condition under which escalation happens
    - `handoff_target` — who receives it (role/team name)
    - `artifacts_passed` — what information goes with the handoff
- `common_edge_cases` (list of objects) — non-routine situations. Each has:
    - `description` — what makes this an edge case
    - `handling` — how the role handles it, if stated

## Output format
Respond with **only** valid JSON matching the structure above. No prose, no markdown wrappers.

## Document

{ARTIFACT_TEXT}
