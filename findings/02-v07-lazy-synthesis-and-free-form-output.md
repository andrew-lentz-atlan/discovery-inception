# v0.7: lazy synthesis + free-form mega-agent

**Status:** Research note follow-up. Same n=1 use case / 5-turn script as [`01-architecture-comparison.md`](01-architecture-comparison.md). Read accordingly.
**Date:** 2026-05-12
**Repo:** https://github.com/andrew-lentz-atlan/discovery-inception
**Comparison artifact:** [`agent/baselines/results/scope_creep_5turn_v06_vs_v07__20260512_133315.md`](../agent/baselines/results/scope_creep_5turn_v06_vs_v07__20260512_133315.md)

---

## TL;DR

Two architectural intuitions, tested on the same 5-turn script that produced [`01-architecture-comparison.md`](01-architecture-comparison.md):

1. **Lazy synthesizer.** Instead of running the synthesizer eagerly every turn before the mega-agent, expose it as a tool the mega-agent invokes when it wants to reflect. The mega-agent decides when synthesis matters.
2. **Free-form mega-agent output.** Drop the "output ONE question, no preamble" format constraint from the system prompt. Let the mega-agent speak naturally — playbacks, signposted reasoning, enumerated alternatives.

Both changes paid off, and they composed:

| | v0.6 | v0.7 |
|---|---|---|
| Wall time | 83.1s | **65.1s (-22%)** |
| Extractor calls (sum) | 13 | **9 (-31%)** |
| Customer-vocab terms | 9 | **14 (+56%)** |
| Mega input tokens | 37.9K | **27.7K (-27%)** |
| Mega output tokens | 764 | 1,202 |
| Detected rationale | 0/5 | **2/5** |
| Per-turn quality (subjective) | — | **4 wins, 1 slight, 0 losses** |

v0.7 is faster, cheaper, AND higher quality. The lazy-synth pattern produces 3-4x synthesizer-call savings while the free-form prompt unlocks conversational moves the format constraint was actively suppressing.

---

## What we were testing

The asymmetry: in v0.6, the synthesizer (which produces the working theory the mega-agent reads via tools) runs *before* the mega-agent on each turn. The synthesizer sees: customer's latest message + spec state summary + prior theory + priors. The mega-agent sees: the full conversation history including its own prior reasoning. So the synthesizer was reasoning from a strictly-poorer information set than the mega-agent it was supposed to inform.

Hypothesis: if the synthesizer ran on-demand instead of eagerly, it would (a) save compute on turns where the mega-agent doesn't need fresh synthesis, and (b) when it DID run, have access to the same conversation context the mega-agent has — closing the information asymmetry.

Second hypothesis: the v0.6 mega-agent prompt explicitly told the model to *"output ONE final question. No prose, no preamble, no explanation of your reasoning. Just the question."* This was bleeding format requirements into the conversational agent's job. LLMs are good at natural-language interpretation; let the mega-agent speak however a real FDE would. Extraction stays in the extractors, where it belongs.

---

## The setup

Same as [01-architecture-comparison.md](01-architecture-comparison.md): identical 5-turn customer script, identical model (`claude-haiku-4-5`), identical priors (Solutions Consultant RoleContext). Only the architecture changed.

v0.6 vs v0.7 differences:

| | v0.6 | v0.7 |
|---|---|---|
| Triage | eager, every turn | eager, every turn |
| Distill | eager, conditional | eager, conditional |
| Synthesizer | eager, after every fact | **LAZY** — invoked via `synthesize_my_thinking()` tool |
| Mega-agent prompt | "output ONE question, no preamble" | free-form output, no format constraints |
| Tools available | `get_current_spec_state`, `get_working_theory`, `get_checklist_progress` | `get_current_spec_state`, `get_checklist_progress`, **`synthesize_my_thinking`** (replaces `get_working_theory` — actually runs the synthesizer instead of reading stored state) |

---

## Results — per-turn quality

| Turn | What it tested | Winner |
|---|---|---|
| 1 | Concrete opening | **v0.7.** Signposted ("we have the headline. Before I drill into how...") and enumerated 4 concrete alternatives. v0.6 asked a similar but shorter question. |
| 2 | Relevance pushback | **slight v0.7.** Both gave substantive rationales. v0.7's was slightly more product-actionable. |
| 3 | Dense structured content | **v0.7.** Invoked `synthesize_my_thinking` mid-turn, then asked about the decision tree with enumerated candidate criteria. v0.6 asked a single drilling question. |
| 4 | Concrete success criteria | **v0.7.** Played back the three deliverables in the customer's exact language, then asked a binary ("done" vs "started and on track by day 30"). v0.6 asked a generic bottleneck question. |
| 5 | Long case study | **v0.7 decisively.** Extracted the 5-question checklist verbatim, named the pattern (*"exhaust low-cost paths first, protect current milestone, escalate to CSM"*), and asked the inverse question (*"when SHOULD SoCo adjust the plan vs defer?"*). v0.6 abandoned the case study content entirely and pivoted to "what slowed you down." |

**Score: v0.7 wins 4, slight 1, losses 0.**

---

## What surprised us

**Lazy synthesis saves more than expected.** v0.7 invoked `synthesize_my_thinking` exactly ONCE across 5 turns — on the dense-content turn where the agent actually needed to step back and structure. v0.6 ran the synthesizer 4 times eagerly. That's 4x the synthesizer-call cost in v0.6 for state the mega-agent never consulted on 3 of those turns.

**Free-form output is doing real work.** v0.7's output tokens are 57% higher than v0.6's (1,202 vs 764). The mega-agent used the freedom to: signpost reasoning, enumerate alternatives in bullets, play back understanding before asking, and capture structural patterns from dense customer content. The v0.6 format constraint wasn't just unnecessary — it was actively suppressing conversational moves that a real consultant would make.

**The information asymmetry closure is real.** When v0.7's synthesizer ran on-demand (turn 3), it had access to the customer's verbatim message + the full conversation history + the structured state, exactly the same context the mega-agent had. The resulting working theory was richer than what v0.6 was pre-baking with thinner inputs.

**Turn 5 is the headline failure mode that v0.7 fixes.** v0.6 had a triage misfire on the long case study in our original A/B/C run (labeled the content `meta`) and dropped 200 words of substantive content. v0.7's free-form mega-agent absorbed and structured the same content directly in its response. **The mega-agent's free-form processing IS a backup against extractor failure modes** — when extractors miss something, the mega-agent's natural-language reasoning over the full conversation can still surface it.

---

## What this implies

**For the project's architecture:** v0.7 is the cleanest realization of the "skill as a tool, not as orchestrator" inversion. The mega-agent is in charge of the conversation; structure happens only when explicitly invoked. The extractor pipeline is genuinely an *optional* skill the mega-agent leans on rather than mandatory pre-computation.

**For agent design more broadly:** there are two principles worth taking from this:

1. **Don't bleed format requirements into the conversational agent.** Let the conversational agent be fluent. Run separate extractors that produce structure FROM the natural-language output. Asking the conversational agent to also produce structured output is a non-trivial cognitive load that degrades the conversation.
2. **Sub-agent invocation should be on-demand, not pre-baked.** Most agent architectures pre-compute "context" before the model's turn (RAG, summarization, planning chains, etc.). The lazy pattern — expose the pre-computation as a tool the model can call — is genuinely better in this experiment because: (a) cost only pays when the model wants it, (b) when invoked the context is fresher, (c) the model uses the tool naturally without being prompted to.

**For Atlan-specific implications:** the inversion ("conversational agent in charge, decomposed skills as tools") matches how skills are framed in Alta's architecture. Skills are governed first-class assets the agent calls; they're not orchestrators. v0.7 is empirically consistent with that direction.

---

## What this updates from [01-architecture-comparison.md](01-architecture-comparison.md)

The original A/B/C comparison found:
- C (hybrid) > B (mega) > A (chained) on quality
- C had a substantial token-cost premium over B (38K vs 14K input tokens)

This follow-up found that **most of C's token-cost premium was avoidable**:
- v0.7 brings the hybrid's input tokens down to 27.7K (still higher than B's 14K, but a 27% reduction from v0.6)
- AND quality goes UP rather than holding
- AND structured output is still produced (just lazily)

The refined architectural recommendation: **use v0.7's shape — lazy synthesis, free-form conversation, decomposed skills as tools — not v0.6's eager-everything pattern.**

---

## Limitations (carrying over from the original)

Same caveats as [01-architecture-comparison.md](01-architecture-comparison.md) plus a new one:

- **n=1 use case still.** Same 5-turn script. The v0.6 vs v0.7 result might not generalize across use cases the same way the C > B > A finding might not.
- **Single model.** Haiku for everything. Per-step model selection still untested.
- **Single human rater (me) on the per-turn winners.** Same risk as before.
- **Intermediate structured state is thinner in v0.7.** v0.6 ends with 4 topics + 3 theory-history snapshots. v0.7 ends with 3 topics + 0 theory-history snapshots because the synthesizer only ran once. If incremental structured-state visibility matters (e.g., a sidebar UI showing the spec growing turn-by-turn), v0.6 is richer. Fixable in v0.7 by running synth once at session end OR adding a deterministic "synthesize after dense turns" rule.

---

## What we'd test next

In priority order:

1. **Run v0.7 on the other scripts** (when we add them — axis 1 from the [data collection roadmap](data-collection-roadmap.md)). Does v0.7's lead over v0.6 hold across different use cases?
2. **Run B vs v0.7.** The pure mega-agent (B) was the cost-leader in the original comparison. Is v0.7's structured-output deliverable worth its remaining token premium over B? Or is structured output the only differentiator?
3. **Test lazy-synthesis on long conversations (axis 3).** v0.7's compression should compound on longer conversations because most turns won't trigger synthesis. Worth measuring.
4. **Add the "synthesize at session-end" deterministic rule.** Closes the intermediate-state gap without re-introducing eager synthesis.

---

## Reproducibility

```bash
cd discovery-inception
uv run python -m agent.baselines.run_v06_v07_comparison \
    --script agent/baselines/scripts/scope_creep_5turn.json
```

Output: `agent/baselines/results/<script>_v06_vs_v07__<timestamp>.md`. No server needed (both architectures run in-process; v0.7 doesn't depend on v0.5's running chained server).

To run on a new script, add a JSON file following [`agent/baselines/scripts/SCHEMA.md`](../agent/baselines/scripts/SCHEMA.md).
