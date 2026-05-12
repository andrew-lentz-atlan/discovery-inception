# v0.7 vs v0.6 at 25 turns: savings hold (not compound), quality lead widens

**Status:** Research note follow-up. n=1 conversation, 25-turn script. Read accordingly.
**Date:** 2026-05-12
**Repo:** https://github.com/andrew-lentz-atlan/discovery-inception
**Comparison artifact:** [`agent/baselines/results/scope_creep_25turn_v06_vs_v07__20260512_134816.md`](../agent/baselines/results/scope_creep_25turn_v06_vs_v07__20260512_134816.md)

---

## TL;DR

Re-ran v0.6 vs v0.7 on a 25-turn script (covering opening goal, dense org content, personas, decision logic, anti-goals, escalations, risks, current state, scope-creep case study, contradictions, redirects, hedges, two relevance pushbacks, an out-of-scope-for-counterparty answer, an off-topic riff, and end-to-end success criteria).

Headline numbers:

| Metric | v0.6 | v0.7 |
|---|---|---|
| Wall time | 363.8s | **335.2s (-7.9%)** |
| Extractor calls | 62 | **44 (-29%)** |
| Mega input tokens | 273.9K | **241.8K (-11.7%)** |
| Mega output tokens | 3,446 | **7,425 (2.2x)** |
| Synthesizer invocations | 17 (eager) | **1 (on-demand)** |
| Customer-vocab terms | 69 | **85 (+23%)** |
| Detected rationale | 3/25 | **20/25** |

**The hypothesis the long run was meant to test** — *"v0.7's lazy-synth savings will compound over a long conversation"* — was wrong on direction. The savings **hold consistently** at 8-16% input tokens, not compound. Both architectures grow linearly per turn; v0.7 just grows at a slightly lower slope.

**What I didn't predict** — v0.7's quality advantage *widens* over the long conversation. The most striking number is rationale-detection: 20/25 turns for v0.7 vs 3/25 for v0.6. v0.7's free-form prompt produces markedly more consultative conversational behavior (playbacks, signposted reasoning, explicit rationale) across the whole arc, not just on showcase turns.

---

## The headline finding: cost savings hold, quality lead grows

### Cumulative cost progression

| Turn | v0.7 vs v0.6 input tokens |
|---|---|
| 1 | -13.6% |
| 4 | -30.8% |
| 7 | -24.9% |
| 10 | -17.5% |
| 11 | -15.5% (after v0.7's one synth call) |
| 15 | -8.4% |
| 20 | -16.1% |
| 25 | **-11.7%** |

Stable ~12% savings across the conversation. Same pattern for extractor calls: -29% consistently across the full arc.

### What broke my earlier hypothesis

I claimed v0.7's savings would **compound** because lazy synthesis would skip more turns as the conversation grew. The data shows the savings are **steady**. Why?

Because input tokens grow primarily from the conversation history accumulating, not from synthesizer calls. The mega-agent's context per turn grows roughly linearly regardless of how many synth calls were made — what synthesis adds is one extra LLM call per invocation, not significantly more input context. So skipping synth saves the call cost but doesn't shrink the dominant input-token line.

The right way to frame v0.7's cost advantage: **the agent's costs become driven by its own judgment rather than by orchestration.** v0.6 pays a synth tax every turn whether the agent needs it or not. v0.7 only pays when the agent decides synthesis is worth doing. Across 25 turns, the agent decided once.

That's a different value prop than "compounds over time" — it's "agent self-governs its own context-gathering cost." Arguably more important.

---

## What I didn't predict: quality lead widens at scale

The 5-turn run showed v0.7 winning 4/5 turns on quality. I expected something similar at 25 turns.

What actually happened: **the conversational-quality gap got much wider.** Three specific patterns held across all 25 turns:

**1. Rationale detection: 20/25 vs 3/25.** A simple regex-based metric, but the underlying signal is real — v0.7's responses consistently include explicit reasoning, "here's why I'm asking" framing, and connections back to the customer's stated goal. v0.6 stayed brief and question-only because that's what the prompt asked for.

**2. Output token volume: 7.4K vs 3.4K (2.2x).** v0.7 is producing roughly twice the response content per turn. Not bloat — richer playbacks, enumerated alternatives, structural distillation of dense customer content. The free-form prompt unlocks this without prompting.

**3. Final working theory quality.** This is the most interesting one.

**v0.6 final framing:**
> *"A markdown brief generator that helps the SoCo hand off a structured, builder-ready onboarding plan to the customer and internal teams..."*

**v0.7 final framing:**
> *"An agent that helps SoCos move customers through onboarding faster by automating or coordinating the repetitive work SoCos currently do themselves — but the real constraint (headcount saturation vs. cycle-time bloat) is still unclear, and that changes what 'faster' should optimize for."*

**v0.6's theory drifted to the meta-conversation in late turns.** When the customer talked about output format (turn 24), v0.6's eager synthesizer ran again, the latest content was about briefs, the theory got updated to "a brief generator." Recency bias from running synth every turn.

**v0.7's theory stayed focused on the agent's substantive job AND explicitly flagged the load-bearing ambiguity** (headcount vs cycle-time as the binding constraint). The single deliberate synthesis at the right moment beat 17 incremental syntheses that gradually drifted.

This is a genuinely surprising result: **less-frequent, more-deliberate synthesis produces a sharper final artifact than more-frequent shallow updates.** That's the deeper version of the "skill as a tool" inversion working as intended.

---

## What this means

**v0.7 is the right architecture even more clearly than the 5-turn run suggested.** The 5-turn run showed v0.7 winning on cost AND quality. The 25-turn run shows the quality lead specifically grows with conversation length, while cost savings stay steady. Both true; both matter.

**The lazy-synth pattern's value is more about *agent self-governance of cost* than about *compounding savings*.** v0.7's costs are driven by what the model decides matters. v0.6's costs are driven by orchestration policy. Empirically the model's judgment is more efficient than the policy.

**v0.6's recency bias on the final theory is a real failure mode.** Running the synthesizer eagerly every turn means it weights recent turns equally with foundational ones. By turn 25, when the customer was talking about output format, v0.6's theory had drifted to be about output format. v0.7's single synthesis captured the agent's actual job AND its load-bearing unknowns. **Deliberate synthesis beats continuous synthesis on stability.**

---

## Caveats

- **Still n=1.** Same use case (SoCo onboarding), same priors. The architecture comparison is replicating on a longer instance of the SAME conversation shape, not a different one.
- **Wall-time savings smaller than 5-turn run** (-7.9% vs -22%). Because v0.7 had one expensive synth call (~70s on turn 11) that ate most of the time budget. If the agent invoked synth more often (say 3-4 times), the wall-time advantage would shrink further. Cost advantage in tokens is more robust than in wall-time.
- **Phase advancement diverged.** v0.6 reached `drilling`; v0.7 stayed in `lay_of_the_land`. Worth investigating — they might be counting canonical-topic coverage differently.
- **v0.6 has 17 intermediate theory snapshots; v0.7 has 0.** If incremental progress visualization matters (a sidebar UI showing the spec evolving), v0.6 is richer. v0.7 only has a final theory, not a journey.

---

## What we'd test next

In priority order:

1. **Add a deterministic "synthesize at session end" rule to v0.7** so the final spec quality doesn't depend on the agent invoking synth at the right moment. Currently v0.7's final theory is good *because* the agent happened to synth at turn 11 with rich context — but a session where the agent never invokes synth would produce a thin final spec. A guarantee that synth runs at session close (with the full conversation in context) closes this gap without re-introducing eagerness.
2. **Test v0.7 with model-tier variation** — synthesizer on Haiku, mega-agent on Sonnet. The lazy pattern should pair well with putting frontier capability on the most-called step (the mega-agent) and cheap capability on the rare step (the synthesizer).
3. **Run on a fundamentally different use case** (axis 1 from the data-collection roadmap) — does v0.7's lead generalize off of SoCo onboarding?
4. **Add an "intermediate snapshot trigger"** — a deterministic rule like "run synth at the end of every 5 turns" — to see if there's a middle ground that preserves the intermediate-state visibility v0.6 has without the recency-bias cost.

---

## Reproducibility

```bash
cd discovery-inception
uv run python -m agent.baselines.run_v06_v07_comparison \
    --script agent/baselines/scripts/scope_creep_25turn.json
```

Output: `agent/baselines/results/scope_creep_25turn_v06_vs_v07__<timestamp>.md` with full turn-by-turn verbatim + the cumulative-cost progression table.

To run on a new (or differently-structured) script, see [`agent/baselines/scripts/SCHEMA.md`](../agent/baselines/scripts/SCHEMA.md).
