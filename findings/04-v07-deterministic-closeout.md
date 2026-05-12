# v0.7 + deterministic session-close synthesis: the missing piece

**Status:** Research note. Same 25-turn script as [`03-v07-25-turn-validation.md`](03-v07-25-turn-validation.md). Same model, same priors. n=1.
**Date:** 2026-05-12
**Repo:** https://github.com/andrew-lentz-atlan/discovery-inception
**Comparison artifact:** [`agent/baselines/results/scope_creep_25turn_v06_vs_v07__20260512_145658.md`](../agent/baselines/results/scope_creep_25turn_v06_vs_v07__20260512_145658.md)

---

## TL;DR

Added one deterministic rule to v0.7: **at session close, run the synthesizer once with the full conversation in scope.** The mega-agent's lazy in-conversation invocation is preserved (its judgment about when to reflect during the call), but the final deliverable is always built deterministically.

Re-ran the 25-turn comparison. v0.7's final working theory recovered cleanly from the recency-bias problem that v0.6 still exhibits. And cost savings strengthened across the board (temperature was also lowered to 0 and retry/fallback added for stability — see "what else changed" below).

| Metric | v0.6 | v0.7 (with close-out) |
|---|---|---|
| Wall time | 482s | **352s (-27%)** |
| Extractor calls | 64 | **44 (-31%)** |
| Customer-vocab terms | 50 | **79 (+58%)** |
| Mega input tokens | 279K | **219K (-21.5%)** |
| Mega output tokens | 3,292 | **6,442 (~2x)** |
| Synthesizer invocations | 18 (eager) | **2** (1 lazy + 1 close-out) |
| Detected rationale | 6/25 | **13/25** |

The single most important number: **v0.7 ran synth twice across 25 turns** (once when the agent decided mid-call, once forced at session close). v0.6 ran synth 18 times eagerly. 9x reduction in synthesizer cost AND a sharper final theory.

---

## The recency-bias failure mode v0.6 still shows

This is the headline qualitative finding. Both runs hit the same script. Compare the final theories:

**v0.6 final framing (after 18 eager syntheses):**
> *"A markdown brief that SoCos can read in 15 minutes to understand the agent's job, decision logic, success metrics, and anti-goals — so a builder can scope v1 without coming back with a hundred questions."*

Drifted into "the agent IS a brief generator" because the late turns of the conversation were about *the output format the customer wants for the discovery brief.* The eager synthesizer ran on those late turns and updated the theory to be about brief generation. By turn 25, v0.6's theory describes the *spec document* the agent will produce, not the *agent itself.*

This is the same failure as v0.6's previous 25-turn run from earlier today. **Reproducible recency bias from eager synthesis.**

**v0.7 final framing (with deterministic close-out):**
> *"A copilot that helps Solutions Consultants route new use cases and make escalation decisions faster by surfacing customer context and decision criteria, while keeping the CSM in the loop and the SoCo in control of the relationship."*

Named the actual job. Three real architectural alternatives as candidate framings (context-gathering assistant / decision-tree guide / guardrail enforcer), three sharp open questions, and this disconfirmer:

> *"If the customer reveals that the real bottleneck is not SoCo decision-making speed but rather lack of technical capacity to execute the work itself (e.g., 'we need the agent to do the implementation work, not just help us route it'), the theory shifts from copilot to workflow executor."*

The single close-out synthesis ran with the full conversation in scope — every fact, every off-topic riff, the contradicted-and-walked-back claim, the dense case studies. It produced a working theory that integrates the whole arc rather than reflecting whatever was most recent.

**The architectural pattern:** in-conversation synthesis is lazy (model's judgment); close-out synthesis is deterministic (guaranteed coverage). Best of both.

---

## Cumulative cost progression — now showing real compounding

The earlier 25-turn run showed savings *holding* but not compounding. This run shows **early-conversation savings up to -46.9%**, gradually stabilizing to -22-28% by the end:

| Turn | v0.7 vs v0.6 input tokens |
|---|---|
| 1 | -15.4% |
| 4 | -46.0% (peak) |
| 6 | -46.9% |
| 10 | -36.0% |
| 15 | -24.6% |
| 20 | -25.9% |
| 25 | **-21.5%** |

Why the difference vs the earlier run? Most likely **temperature=0** (vs 0.2 before) reduced model variance — both architectures produce more consistent responses, so the per-turn costs are tighter and the synth-call overhead of v0.6 stands out more clearly. The retry/fallback added during this iteration also avoided the abort-on-flaky-triage problem.

Either way: the v0.7 cost story is now substantially stronger than the earlier 25-turn measurement.

---

## What else changed in this iteration

Three changes happened in parallel with the deterministic-close-out feature:

1. **`call_sub_agent` got retry logic** (up to 4 attempts with backoff). LiteLLM-via-Bedrock-Claude occasionally returns stock "I'm ready to triage. Please provide inputs..." prose instead of the JSON we requested. Retries with brief delay recover from this transient failure mode.
2. **Temperature dropped from 0.2 to 0** for all sub-agent calls. Sub-agents are doing classification/extraction tasks where determinism is preferred over creativity. The mega-agent's main call stays at the higher temperature for conversation fluency.
3. **System prompt merged into user prompt** for sub-agent calls. Previously the "output JSON only" instruction was a system message; the proxy seemed to occasionally treat the system message as the actual task and the user content as unspecified context. One unified user message removes that ambiguity.
4. **Triage gets a graceful fallback** (default to `concrete` label if retries exhaust). Better to mislabel one turn than abort a 25-turn comparison.

All of these are pure robustness changes — they don't change what the architectures DO, they just make them complete the conversation without aborting on flaky API behavior. None of them favor v0.6 or v0.7.

---

## What this means for v1.0

The deterministic close-out closes the last meaningful gap between v0.7 and "production-ready discovery agent."

Specifically: before this rule, v0.7 had a real risk that a session would end with a thin or stale working theory (if the agent never invoked synth mid-conversation, OR if the mid-conversation synth got stale because of subsequent context). With the rule, the final theory is *guaranteed* to be built from the full conversation. v0.6's pattern produces a final theory too — but at the cost of running synth 18 times AND with recency-bias issues. v0.7's pattern gives you the same guarantee at 1/9th the synthesis calls AND with better theory quality.

**The v0.7 architecture is now: lazy in-conversation synthesis (model judgment) + deterministic close-out synthesis (guaranteed coverage) + free-form conversation + decomposed extractors as tools.** That's the production shape.

---

## Limitations (carrying over and adding)

Carryover from previous notes:
- **n=1 use case.** Same SoCo onboarding script. Doesn't tell us this generalizes.
- **Single model.** Per-step model selection still untested.
- **Single human rater (me) on the qualitative per-turn winners.**

New:
- **Multiple changes in parallel** (deterministic close-out + retry + temp drop + prompt merge). The recovered cost savings (-21.5% input tokens) probably isn't attributable solely to the close-out rule. The next clean test would isolate them: run v0.7 with EVERY change EXCEPT close-out, then add close-out. We didn't do that here.
- **Triage fallback obscures a real proxy issue.** The LiteLLM-via-Bedrock occasional "please provide inputs" failure mode is now hidden by the fallback. We should investigate whether this happens in production-shaped calls too, not just our benchmark. Worth its own thread.

---

## What we'd test next

1. **Test on a different use case.** Same axis 1 from the [data-collection roadmap](data-collection-roadmap.md). Until we run on a CSM renewal-risk discovery or similar, "v0.7 wins" is anchored to SoCo onboarding specifically.
2. **Try cheap-cascade.** Synthesizer on Haiku, mega-agent on Sonnet. The lazy pattern should pair well with putting frontier capability on the most-called step.
3. **Investigate the LiteLLM proxy flakiness.** The "please provide inputs" stock response on otherwise valid prompts is a real proxy-side issue. Worth a small reproduction and conversation with the LiteLLM team or whoever owns the proxy.

---

## Reproducibility

```bash
cd discovery-inception
uv run python -m agent.baselines.run_v06_v07_comparison \
    --script agent/baselines/scripts/scope_creep_25turn.json
```

Output: `agent/baselines/results/scope_creep_25turn_v06_vs_v07__<timestamp>.md` includes summary metrics, per-turn cumulative cost progression, per-turn side-by-side transcripts, and (for v0.7) the deterministic close-out's contribution flagged separately.

For the deterministic close-out implementation, see `agent/v07/orchestrator.py:run_final_synthesis()`. For the retry/fallback machinery, see `agent/orchestrator.py:call_sub_agent()`.
