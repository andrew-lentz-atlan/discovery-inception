# Step 4: Unwritten Rules Sniffer

You are looking for the **most valuable extractions** in this whole intake process: the implicit heuristics, soft rules, and informal norms that shape how the role actually operates. These are the things experienced practitioners do automatically that the formal sections rarely capture.

## What you're looking for

Hunt for statements that suggest:

1. **Conditional defaults.** "We usually do X unless Y." "Default to X." "When in doubt, prefer Y over Z." Look for "when," "unless," "by default," "typically," "we tend to," "usually."
2. **Cultural rules of thumb.** "When it's 50/50, the customer wins." "Speed matters more than perfect." "Always loop in <person> on <thing>."
3. **Anti-patterns.** Things the document says NOT to do, especially as asides. "Don't go to engineering with X without trying Y first."
4. **Severity / priority hints.** Things that signal what matters most when things conflict. "If you have to drop something, drop X before Y."
5. **Soft handoff rules** that aren't formal escalation paths. "Pull <role> in early on accounts over $X."

## Where to look
- Asides and parenthetical remarks
- Examples and stories ("for instance," "last quarter we had...")
- The unwritten-feeling statements in policy docs ("we believe in...")
- In transcripts: things that get said in dialogue but never appear in formal sections
- Phrases like "as a rule," "typically," "in practice," "our philosophy is," "we always," "we never"

## Hard rules

- **Each rule must be supported by a quote from the source.** Include the candidate quote in `candidate_quotes` for verification. If you can't find a supporting quote, don't include the rule.
- **Be conservative — false rules are more damaging than missed rules.** If a statement could be either a rule or a one-off, lean toward exclusion. If you're hesitating about whether something qualifies as an "unwritten rule," that hesitation is the answer: leave it out. Empty `rules` is a fine outcome — formal documents (especially job descriptions and policy docs) often have few or no genuine asides, and that's correct behavior, not a failure.
- **Don't restate the formal stuff.** If the source has a section called "Escalation Policy" with rules, those go in `escalation_paths` (already extracted). Unwritten rules are the ones that aren't in formal sections — they live in asides, examples, dialogue, or implicit between-the-lines statements.

## Output

Valid JSON:

```json
{
  "rules": [
    "<rule, stated in operational language. Example: 'On joint customer calls, defer to the sales lead on commercial questions, but own the technical depth without checking in.'>",
    ...
  ],
  "candidate_quotes": [
    "<verbatim quote from source supporting the corresponding rule above>",
    ...
  ]
}
```

The two lists must have the same length: rule N is supported by quote N.

No prose outside the JSON.

## Source document

{ARTIFACT_TEXT}
