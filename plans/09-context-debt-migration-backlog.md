# 07 — Context Debt Migration Backlog

**Status:** durable artifact — tracks prompt-resident opinions that should migrate to `patterns/` over time.
**Owner:** anyone touching the listed prompts inherits a soft obligation to consider migration.
**Updated:** continuously, as prompts get touched and as new patterns get authored.

---

## Why this exists

Per `plans/07-patterns-knowledge-base.md`, the project is shifting toward a principle:

> **Prompts encode invariants. Knowledge bases encode opinions.**

The current discovery-inception prompts violate this in known ways — they have opinions baked in that should live in `patterns/`. We agreed (`05` open-questions section) to:

- **Enforce no new debt** — new prompts get authored against the principle; opinions go to patterns first
- **Migrate lazily** — existing prompts get migrated when they're touched for other reasons, not preemptively

The risk of "lazy migration" is forgetting. This doc is the antidote: a structured backlog that records what migration debt exists, where it lives, and which pattern entry it should migrate into. Whenever someone edits a listed prompt, this doc surfaces the opportunity.

---

## How to use this doc

When editing a prompt:

1. Check the table below — is this prompt listed?
2. If yes, the listed opinions should ideally migrate during your edit. Move the opinion text into the corresponding `patterns/` entry; replace the in-prompt instruction with a reference + a `lookup_pattern()` invocation.
3. If migration is too expensive for the current change, leave the entry. Update `last_visited` if you reviewed it.
4. When you add a new prompt with opinions in it, **add a row here** rather than letting it land silently as new debt.

When authoring a new `patterns/` entry:

1. Check this doc — is there existing prompt-resident opinion that should consolidate into your new entry?
2. If yes, mark the relevant rows as "ready for migration" and link the new pattern.

This is the durable mechanism for not forgetting.

---

## Current backlog

Last full audit: 2026-05-20.

| Prompt file | Opinion baked in | Should migrate to | Priority | Last visited |
|---|---|---|---|---|
| `agent/v08/orchestrator.py` (mega-agent system prompt) | "Use `synthesize_my_thinking` lazily, only when the working theory feels stale" | `patterns/decision-guides/when-to-invoke-synthesis.md` | high | 2026-05-20 |
| `agent/v08/orchestrator.py` (mega-agent system prompt) | "Use `find_tensions` when contradictions surface in captured facts" | `patterns/decision-guides/tension-detection-triggers.md` | high | 2026-05-20 |
| `agent/v08/orchestrator.py` (mega-agent system prompt) | Number-provenance discipline rules | `patterns/skill-design/source-fidelity.md` | medium | 2026-05-20 |
| `agent/v08/orchestrator.py` (mega-agent system prompt) | Tool-use triggers (when to call which tool) | `patterns/decision-guides/tool-invocation-triggers.md` | medium | 2026-05-20 |
| `agent/prompts/05_synthesizer.md` | "Surface internal tensions alongside framing" — entire tension-detection logic baked in | `patterns/architectures/adversarial-decomposition.md` + `patterns/decision-guides/tension-surfacing.md` | high | 2026-05-20 |
| `agent/prompts/06_probe_sharpener.md` | Quality scoring rubric (novelty / extension / provenance / tension) | `patterns/skill-design/adversarial-review.md` + `patterns/decision-guides/probe-quality-scoring.md` | high | 2026-05-20 |
| `agent/prompts/06_probe_sharpener.md` | The "you said X but Y" tic — implicit template that drives the adversarial-contradiction format | `patterns/anti-patterns/sharpener-template-collapse.md` (also a finding waiting to be written) | high | 2026-05-20 |
| `agent/prompts/07_find_tensions.md` | What counts as a tension worth surfacing (vs noise) | `patterns/decision-guides/tension-detection-triggers.md` | medium | 2026-05-20 |
| `intake/prompts/02_extractor.md` | "Use document's own language" — source-fidelity principle | `patterns/skill-design/source-fidelity.md` | low | 2026-05-20 |
| `intake/prompts/02_extractor.md` | "Empty is better than wrong" — anti-hallucination principle | `patterns/anti-patterns/hallucinated-completeness.md` | low | 2026-05-20 |
| `intake/prompts/04_unwritten_rules_sniffer.md` | "Hunt for hedges, anti-patterns, soft handoffs" — tacit-knowledge taxonomy | `patterns/skill-design/tacit-knowledge-extraction.md` | medium | 2026-05-20 |
| `intake/prompts/04_unwritten_rules_sniffer.md` | "Be conservative — false rules more damaging than missed rules" | `patterns/decision-guides/extraction-conservatism.md` | low | 2026-05-20 |
| `intake/prompts/05_gap_reporter.md` | Gap taxonomy (missing inputs / thresholds / actors / failure modes / measurement) | `patterns/skill-design/gap-taxonomy.md` | medium | 2026-05-20 |

That's 13 listed opinions across 7 prompts. Not exhaustive — additional opinions exist in `01_triage.md`, `03_distill.md`, `04_synthesizer.md` and others that weren't audited at the listed date. Future audits expand this table.

---

## Migration patterns (how to actually do a migration)

When a prompt edit triggers a migration, the shape is consistent. Two cases:

### Case 1 — Whole-section migration

The prompt has a discrete section that's pure opinion. Move it intact.

```diff
# In agent/v08/orchestrator.py system prompt template:

  ## Your role
  You are the mega-agent for a discovery conversation...

- ## When to invoke synthesize_my_thinking
- Use it only when:
- 1. The conversation has surfaced ~5 new facts since last synthesis
- 2. The customer just gave a strong directional answer that may shift the theory
- 3. ...
+ ## When to invoke synthesize_my_thinking
+ Consult patterns/decision-guides/when-to-invoke-synthesis.md
+ via lookup_pattern("when to invoke synthesize_my_thinking").
+ The patterns entry contains the current decision rules.
```

The deleted prompt text gets dropped into `patterns/decision-guides/when-to-invoke-synthesis.md`'s body (with appropriate structure: when-to-use, when-not-to-use, empirical receipts, etc.).

### Case 2 — Distributed migration

The prompt has opinion threaded through multiple places, not in a discrete section. Migration is messier:

1. Extract every opinion bullet/sentence into the target pattern entry
2. Replace each occurrence with a tighter pointer ("see `patterns/X` for current guidance on Y")
3. Test that the prompt still produces equivalent behavior post-migration (this is the load-bearing check — if behavior drifts, the in-prompt context was doing more than we realized)

### Both cases — the validation step

Every migration is followed by a validation run. Pick a representative test (a script for discovery, a sample artifact for intake) and run it before and after. If outputs are roughly equivalent (specs match in topic count, fact count, theory framing), the migration is clean. If they diverge materially, restore + investigate before merging.

---

## Anti-pattern: silently adding new debt

The hardest part is preventing new debt. Two checks:

1. **Code review heuristic:** *"Does this prompt change add an opinion that might evolve?"* If yes, it should go in `patterns/`, not the prompt. PR template should include a checkbox for this.
2. **Periodic self-audit:** every 3 months, do a pass — read all prompts looking for new bake-ins not in this table. Add them. Estimated cost: 1 hour per audit.

The "new debt" check is more important than the migration speed. Old debt is annoying but bounded; new debt is unbounded.

---

## Status tracking

Once `patterns/` is built and the curator agent is shipping, this doc should evolve into something more automated:

- The curator's `lint` operation could detect prompt-resident opinions automatically (regex for "use X when Y", "default to Z", "prefer A over B" — heuristic for "this smells like an opinion")
- The lint output would feed back into this table
- Migrations completed get logged in `patterns/_log.md`
- This doc eventually becomes a thin index over the curator's structured tracking

For now, manual tracking. Lazy migration. No new debt. Forget nothing.

---

## When to read this doc

- **Before touching any listed prompt** — check whether migration is appropriate during your change
- **Before authoring a new prompt** — make sure new opinions go to patterns, not back here
- **During quarterly audits** — refresh `last_visited` dates; add newly-discovered opinions
- **When patterns gets new entries** — cross-check whether any backlog items should consolidate
- **When onboarding a new contributor** — point them here as the "what's the rule on prompts vs knowledge" reference
