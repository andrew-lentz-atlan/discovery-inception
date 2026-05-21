# Step 4: Draft Body

You produce the markdown body for a pattern entry. The frontmatter is already drafted (you'll see it in inputs). The body shape was chosen in step 1; the content was extracted in step 2. Your job: render the extracted content into the markdown shape that matches existing entries.

## Output style

- **First content under the H1 title is a 3-6 sentence opener** — the `summary` field from step 2, rendered as prose. No bullet preamble. This is what an agent reads first.
- **Every line earns its place.** No ceremony, no padding, no recapitulation of the cited source. If the source already says it, link to the source — don't restate.
- **Match the existing entries' tone.** Direct, present-tense, no marketing voice, no exclamation points. *"Use when X. Don't use when Y."* not *"You should consider using this powerful pattern when..."*.
- **No emojis. No first-person plural ("we"). No filler transitions ("Furthermore," "In addition,").**
- **Inline code uses backticks**, e.g., `single-agent-react`. Code blocks use triple-backtick fences with language tags.

## Body shape templates

Use the template that matches `{BODY_SHAPE}`. Adapt slightly if the content demands; preserve the section ordering.

### `operational-decision` (most common)

```markdown
# <title>

<3-6 sentence opening paragraph — the summary>

## Use when

- <bullet>
- ...

## Don't use when

- <bullet>
- ...

## Key gotchas

- **<Short name>.** <one-sentence description>
- **<Short name>.** <one-sentence description>

## Empirical anchor

<one paragraph citing the empirical receipts; ideally one substantive paragraph, not a bullet list>

Origin: <one-sentence attribution>.
```

### `code-pattern`

```markdown
# <title>

<3-6 sentence opening paragraph>

## The pattern

<short narrative or ASCII diagram showing the shape>

## Canonical example

<one or two code blocks excerpted from the source, with minimal annotation between them>

## Variants

- **<variant name>**: <one-sentence description>
- ...

## Anti-pattern callouts

<cross-references to anti-patterns/ entries this pattern explicitly avoids>

## Key gotchas

- **<Short name>.** <description>
- ...

## Empirical anchor

<paragraph citing receipts>

Origin: <attribution>.
```

### `comparative-survey`

```markdown
# <title>

<3-6 sentence opening that frames the survey>

## The N, summarized

| # | Item | What it is | The one gotcha that bites |
|---|---|---|---|
| 1 | ... | ... | ... |
| 2 | ... | ... | ... |
| ... | ... | ... | ... |

## The few that actually matter for most decisions

<paragraph naming the load-bearing subset and why>

## Decision tree (when to pick which)

1. **<criterion>:** <recommendation>
2. ...

## Cross-cutting observation

<paragraph on the higher-order pattern that emerges across the items>

## When to revisit

| Trigger | Action |
|---|---|
| ... | ... |
```

### `theoretical`

```markdown
# <title>

<3-6 sentence opening>

## Premises

- <foundational assumption>
- ...

## Implications

- <what follows from the premises>
- ...

## Open questions

- <question the framework doesn't answer>
- ...

## Empirical anchor

<paragraph>
```

### `historical`

```markdown
# <title>

<3-6 sentence opening>

## Trajectory

<narrative arc from origin to present>

## What came before

<paragraph on the prior state>

## What it enabled

<paragraph on the consequences>

## Empirical anchor

<paragraph citing the historical record>
```

### `open-questions`

```markdown
# <title>

<3-6 sentence opening>

## Open questions

1. <question 1>
2. <question 2>
3. ...

## What we'd test

- <experimental approach to each question>

## Current best guesses

<paragraph on the working hypothesis for each question>
```

## Cross-reference handling

If `frontmatter.related` includes other entries, weave a sentence or two into the body where the relationship is naturally surfaced (typically in the Cross-cutting observation, Anti-pattern callouts, or Empirical anchor sections). Use the format `[<slug>](../<category>/<slug>.md)` for the link.

If `frontmatter.contradicts` is non-empty, the body should explicitly name the contradicted entry (e.g., *"This pattern contradicts `anti-patterns/cheap-cascade-orchestrator-compensation` — the receipts there showed +67% cost; we believe those receipts no longer hold because..."*).

## Inputs

### Body shape (CHOSE THE TEMPLATE ABOVE BY THIS)
`{BODY_SHAPE}`

### Title
`{TITLE}`

### Extracted content (from step 2)
```json
{EXTRACTED_PATTERN_JSON}
```

### Frontmatter (already drafted in step 3)
```json
{FRONTMATTER_JSON}
```

## Output

Return ONLY a JSON object with a single field `body_md`:

```json
{
  "body_md": "<full markdown body, ready to paste under the YAML frontmatter>"
}
```

The body should START with the `# <title>` line — your renderer prepends the frontmatter; you don't need to.

Do NOT wrap `body_md` in a markdown fence. Just the raw markdown content as a JSON string with appropriate `\n` escapes.
