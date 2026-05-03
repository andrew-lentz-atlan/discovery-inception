# Step 3: Vocabulary Normalizer

You are extracting and defining domain-specific vocabulary from a workplace role document. This vocabulary will become a glossary the discovery agent uses to align language with the customer.

## What counts as a domain term
- **Internal jargon.** "TAM," "implementation workstream," "go-live," "outcome map." Anything specific to this role / org / industry.
- **Distinguishing labels.** "Tier-1 vs tier-2 customer," "self-serve vs assisted" — terms that subdivide a category meaningfully.
- **Tools / systems referenced by proper name.** "Glean," "Atlan tenant," "Salesforce opportunity record."
- **Process names.** "Bootstrap phase," "Active phase," "MVA."

## What does NOT count
- Generic English ("customer," "team," "deliver"). Skip these.
- Cliches ("best-in-class," "world-class"). Skip.

## Hard rules
- **Define terms in the source's own words** where possible. If the source defines "Solutions Consultant" inline, use that definition. Don't paraphrase if you can quote.
- **Collapse synonyms.** If the source uses "TAM" and "Solutions Consultant" interchangeably, keep one as the canonical term and note the merge in `synonyms_collapsed`.
- **No fabricated definitions.** If the source uses a term but doesn't define it, *include* it (don't skip) but **mark the definition explicitly as inferred** with the prefix `[INFERRED — please confirm]`. Examples:
    - `"CSA": "[INFERRED — please confirm] Likely abbreviation for Customer Solutions Architect, but the source does not define it."`
    - `"CSM": "[INFERRED — please confirm] Customer Success Manager — standard industry term, not defined in source."`
  This is the consulting move: "you mean Customer Success Manager, right?" — flag the gap as a clarifying question rather than pretending the inference is fact. Downstream the discovery agent will probe these.
- **Never** put a fabricated definition in without the `[INFERRED — please confirm]` prefix. If you can't find an explicit definition AND can't make a reasonable inference, skip the term entirely.

## Output

Respond with valid JSON:

```json
{
  "domain_vocabulary": {
    "<canonical term>": "<definition in the source's own words or close paraphrase>",
    ...
  },
  "synonyms_collapsed": [
    "<one-line note per merged synonym group, e.g. 'TAM is used interchangeably with Solutions Consultant; canonicalized to Solutions Consultant'>",
    ...
  ]
}
```

No prose outside the JSON.

## Source document (read for context)

{ARTIFACT_TEXT}

## Already-extracted structure (use to align canonical names)

{EXTRACTION_JSON}
