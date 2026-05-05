# Data-collection roadmap for the architecture-comparison finding

The headline finding from [`01-architecture-comparison.md`](01-architecture-comparison.md) — *"hybrid (extractor skills + conversational mega-agent) beats both pure chained and pure mega; decomposition is load-bearing for structured output, not for conversation quality"* — was produced from **n=1 use case, one 5-turn script**. We treat it as a starting hypothesis, not a conclusion.

This doc is the prioritized list of validation work that would either strengthen or kill that hypothesis. It exists so future-us (or a teammate) can pick it up without re-deriving the priorities.

---

## Six axes, ranked by signal-to-effort

### 🥇 Axis 1 — More scripts, different shapes *(start here when we resume)*

**What.** 2–3 additional 5-turn customer scripts covering different use cases:
- CSM renewal-risk discovery (different role priors)
- Technical-incident discovery (different conversation rhythm)
- Contract-negotiation discovery (different decision shape)
- Onboarding for a different vertical (e.g., FinTech vs SaaS)

**Why.** Directly attacks the n=1 critique. Either reproduces C > B > A (strengthens the claim) or surfaces a counter-example (sharpens it). Either outcome is high-signal.

**Effort.** ~1–2 hours per script (writing it + running it). The harness is already built — just add JSON files to `agent/baselines/scripts/`. Schema doc at [`agent/baselines/scripts/SCHEMA.md`](../agent/baselines/scripts/SCHEMA.md).

**Risk if skipped.** The entire architectural finding lives or dies on one anecdotal run. This is the most important next step.

---

### 🥈 Axis 2 — Cheap-cascade test

**What.** Run the same 3-way comparison but with extractors on Haiku and the conversational mega-agent on Sonnet (or Opus). Set via environment variables already wired into `agent/orchestrator.py`:

```bash
DISCOVERY_TRIAGE_MODEL=claude-haiku-4-5 \
DISCOVERY_DISTILL_MODEL=claude-haiku-4-5 \
DISCOVERY_SYNTHESIZER_MODEL=claude-haiku-4-5 \
DISCOVERY_AGENT_MODEL=claude-sonnet-4-6 \
uv run python -m agent.baselines.run_comparison ...
```

**Why.** The original "decomposition is the skill" thesis was specifically about per-step model selection — running cheap models on easy steps and frontier on hard. We never tested it. If C's lead **widens** under cheap-cascade, decomposition's value reasserts at the cost dimension. If results stay the same, the model-selection argument is empirically thin.

**Effort.** ~30 minutes — env vars + a re-run.

---

### 🥉 Axis 3 — Long conversation (20–30 turns)

**What.** A single script that runs to 20–30 turns. Real discovery calls are 30–60 minutes; 5 turns is sample-of-conversation, not full conversation.

**Why.** Tests a hypothesis we wrote in the limitations section but didn't measure: B (mega-agent) accumulates context linearly with no compression; C can periodically compress conversation history into the structured spec the extractors maintain. The hypothesis was *"B will drift on long conversations; C will compound its advantage from compression."* Currently unmeasured.

**Effort.** Writing a 30-turn script is real work (2–3 hours). Running it is fast. Capturing meaningful drift requires the script to escalate complexity, not just repeat the same beats.

---

### Axis 4 — Multi-rater quality scoring

**What.** Have 2–3 humans rate each turn independently against a small rubric (vocabulary mirroring, theory anchoring, relevance justification, conversational fluency). Replace the single-rater subjective winner with averaged scores.

**Why.** The strongest methodological weakness of the current finding is "this was one person's read." Multi-rater reduces single-rater bias and produces an inter-rater agreement score that itself is signal.

**Effort.** The eng work is trivial (extract verbatim transcripts to a shared spreadsheet/form). Coordination with other humans is the friction. Probably bundle this with axis 1 — rate the new scripts as they come in.

---

### Axis 5 — Real Gong recordings *(highest production-relevance)*

**What.** Take 3–5 historical discovery call recordings, transcribe them, run through C in intake mode (treating each speaker turn as a customer message). Compare the structured outputs to what the FDE actually produced manually (success plan, deal notes, follow-ups).

**Why.** This is what would convince anyone at Atlan that the finding generalizes from synthetic to real. It also doubles as the production demo of Option C (post-hoc conversation intake — see the "what's the most useful version" thread).

**Effort.** The eng work is small once we have transcripts (transcription + treating transcript turns as `run_v06_turn` inputs). The gate is **privacy/legal clearance** — we'd need explicit clearance to process recordings outside any standard workflow. Pursue clearance in parallel with the simpler axes above.

---

### Axis 6 — Adversarial / messy scripts

**What.** Customer behaviors we haven't tested: contradicting themselves mid-conversation, backtracking, going on tangents that don't return, getting interrupted by other priorities, being hostile, refusing to answer, talking past the agent.

**Why.** Real customers behave like this. Synthetic clean scripts may flatter the mega-agent's pattern-matching. Adversarial scripts test where structural enforcement (the chained pattern's strength) might re-emerge as load-bearing.

**Effort.** ~2 hours per script. Cleanest to write them in batches paired with axis 1.

---

## Suggested order if we come back

1. **Axis 1** — moves us from n=1 to n=3–4 fastest. Most defensible against the obvious objection.
2. **Axis 2** — cheap, hits the original thesis directly, worth running before claiming anything publicly about decomposition + cost.
3. **Axis 5** — pursue privacy clearance in parallel; production-relevance unlock once cleared.
4. **Axes 3, 4, 6** — when there's bandwidth or a specific need.

---

## What "done enough" looks like

We don't need to run every axis to draw a stronger conclusion. The current finding flips from *"interesting one-off"* to *"defensible architectural claim"* if any of the following land:

- **Axis 1 produces n=3+ runs and the C > B > A ordering reproduces** on at least 2 of the 3 (one counter-example is fine and informative; consistent counter-examples kill the claim).
- **Axis 5 produces structured specs from real Gong recordings** that an FDE rates as "I would have written something similar" or better. That's ecological validity in one shot.
- **Axis 2 shows decomposition's cost story holds** under cheap-cascade — i.e., A and C still produce similar quality but at notably lower per-turn cost than B.

Any one of these is a meaningful update. Two of them and the finding is in pretty solid shape.

---

## What this doc is NOT

- It's not a commitment to do all six axes.
- It's not the canonical finding — that's [`01-architecture-comparison.md`](01-architecture-comparison.md). This is the *roadmap for what would test that finding more rigorously*.
- It's not a deadline-driven plan. We come back when there's reason to.

When we do come back, this is the on-ramp.
