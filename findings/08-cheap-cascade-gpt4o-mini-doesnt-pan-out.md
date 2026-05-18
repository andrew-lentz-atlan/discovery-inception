# Cheap-cascade with gpt-4o-mini on sub-agents — DIDN'T pan out

**Status:** Negative result. n=1 use case (same 50-turn TechCo Sales Pipeline Analyst script).
**Date:** 2026-05-18
**Repo:** https://github.com/andrew-lentz-atlan/discovery-inception
**Sessions:** baseline `sess_483c55604289`, cheap-cascade `sess_f341af4dfaa3`

---

## TL;DR

Tested the cheap-cascade hypothesis: sub-agents on `gpt-4o-mini`, mega-agent on `claude-haiku-4-5` (unchanged). Same 50-turn script. **Result: net negative on both cost AND quality.**

The intuition that "extractors are simple, smaller model should be fine" didn't survive contact with reality. The mega-agent compensates for thinner extractor outputs by calling more tools and producing longer responses, which causes its own token usage to balloon 3.2x.

| Metric | Baseline (all Haiku 4.5) | Cheap-cascade |
|---|---|---|
| Wall time | 671s | 613s (-9%) |
| Mega input tokens | 540K | **1,706K (+216%)** |
| Mega output tokens | 8K | 12K (+55%) |
| Mega tool invocations | 6 | **27 (+350%)** |
| Sharpener rewrite rate | 55% | **77%** |
| Final theory confidence | medium | **low** |
| Topics captured | 21 (granular) | 9 (lumpy) |
| Facts captured | 44 | 45 |

**Estimated total cost:**
- Baseline: ~$1.08
- Cheap-cascade: ~$1.81 (+67%)

Cheap on the wrong axis. The sub-agent savings (~$0.45) were swamped by the mega-agent's increased usage (+$1.18).

---

## What we tested

Same v0.8 architecture. Same 50-turn `sales_analyst_50turn.json` script. Only difference:

```bash
DISCOVERY_TRIAGE_MODEL=gpt-4o-mini \
DISCOVERY_DISTILL_MODEL=gpt-4o-mini \
DISCOVERY_SYNTHESIZER_MODEL=gpt-4o-mini \
uv run python -m agent.baselines.run_v08_solo --script ...
```

The `DISCOVERY_SYNTHESIZER_MODEL` env var also routes the **sharpener** and **find_tensions** sub-agents to `gpt-4o-mini` (they currently reuse the synthesizer model slot in v0.8). So effectively: triage, distill, synthesizer, sharpener, tensions all on `gpt-4o-mini`; mega-agent only on `claude-haiku-4-5`.

---

## What actually happened

### The mega-agent compensated for weaker extractor outputs

The most surprising number: **mega-agent input tokens went from 540K → 1.7M**. The mega-agent doesn't directly use the cheaper extractors' output text, so why?

Looking at the trace, two compounding effects:

1. **Mega-agent invoked tools 4.5x more often** (27 vs 6). When the working theory / spec state coming from gpt-4o-mini's synthesizer was thinner, the mega-agent kept calling `get_current_spec_state`, `get_checklist_progress`, `synthesize_my_thinking` to orient. Each tool call inflates the next request's input.

2. **Mega-agent output tokens went from 8K → 12K** — longer responses on average. When the structured context is thinner, the mega-agent fills the gap with more elaborate prose. That elaboration becomes input context for the NEXT turn's call, which feeds the snowball.

The mega-agent IS the cost center (Claude Haiku 4.5 input is ~6x more expensive per token than gpt-4o-mini's input). When you push more work to it, you pay disproportionately.

### Sharpener caught more weak probes — because probes were weaker

Sharpener rewrite rate: **55% → 77%**. The probes the mega-agent emitted were below the quality threshold more often. The sharpener (also on gpt-4o-mini in this test, possibly contributing to its own quality drift) flagged them more aggressively.

This is the secondary cascade: thinner extractor outputs → mega-agent less anchored → weaker probes → more sharpener rewrites.

### Distill lumped instead of split

gpt-4o-mini's distill behaved differently from Haiku 4.5's. Topic distribution shifted markedly:

**Baseline** (21 topics, granular):
- 5 facts in `data_architecture`, 5 in `escalation_rule`, 4 in `risk`
- Specific topics like `close_date_confidence_rule`, `revenue_metric_selection_rule`, `ae_dashboard_scope`, `forecast_refresh_cadence` minted as facts arrived

**Cheap-cascade** (9 topics, lumpy):
- **17 facts in `current_pain`**, **10 facts in `success_metric`**, 6 in `escalation_rule`
- Few specific topics; gpt-4o-mini lumped facts under canonical buckets aggressively

Both are valid distillation strategies. But the lumping is sometimes inappropriate — "current_pain" with 17 facts likely includes rules, governance constraints, and architecture details that aren't really "pain." Coarser categorization erodes downstream usability of the spec.

### Final theory: thinner

| | Baseline | Cheap-cascade |
|---|---|---|
| Framing | *"A natural-language agent that answers ad-hoc pipeline and forecast questions from RevOps, AE managers, VP Sales, and CFO by querying Snowflake-modeled Salesforce data, **surfacing data quality issues proactively, and escalating variance or anomalies that exceed named thresholds to the right stakeholder.**"* | *"We want a Sales Pipeline Analyst agent that allows RevOps, AE managers, VP of Sales, and CFO to ask plain-language questions about pipeline state and trust the answers."* |
| Confidence | medium | low |

Cheap-cascade's framing basically restates the use_case_seed. Baseline's framing names specifics — proactive surfacing, escalation thresholds, named stakeholders. The synthesizer running on `gpt-4o-mini` didn't produce as sharp a theory.

---

## Why this happened (hypotheses)

Three things plausibly contribute:

1. **Tight coupling between sub-agents and mega-agent grounding.** The synthesizer's working theory is the load-bearing structured input the mega-agent reads via tools. If synth is thin, the mega-agent has no anchor. We didn't appreciate how dependent the mega-agent is on synth quality before this test.

2. **Prompt-tuning is Claude-flavored.** The prompts in `agent/prompts/*.md` were authored and iterated against Claude's interpretation style. gpt-4o-mini may follow the same prompts differently — particularly the synthesizer's "surface internal tensions" instruction, which Claude internalizes naturally but `gpt-4o-mini` seems to interpret more literally.

3. **Different distillation philosophy.** gpt-4o-mini lumps into canonical topics aggressively; Haiku 4.5 splits into specific topics readily. Neither is wrong, but the downstream rendering (spec.md per-topic sections) is much more readable with granular topics.

---

## What this means

### For cheap-cascade as an optimization

**Don't do it naively.** The simple "extractors on a cheaper model, mega-agent on the same model" pattern is **not a win** for this architecture as currently tuned. The sub-agent savings are dwarfed by the mega-agent's compensatory token growth.

### Selective cheap-cascade might still work

If we wanted to try again with targeted scope:
- **Triage** is pure classification — could probably stay on gpt-4o-mini without harm. Marginal savings since triage is only one call per turn.
- **Distill** is structured extraction — gpt-4o-mini's lumping behavior is concerning; needs prompt re-tuning to match Haiku 4.5's behavior.
- **Synthesizer** is the load-bearing one for downstream quality — keep on Haiku 4.5 (or larger).
- **Sharpener** is adversarial review — also load-bearing for probe quality — keep on Haiku 4.5.

Estimated savings of triage-only cheap-cascade: probably negligible. Probably not worth the complexity.

### For the architecture decision to use Haiku 4.5 throughout

**This is now defensible empirically**, not just by default. We tested cheaper, it didn't pan out, here are the receipts. The choice to use Haiku 4.5 uniformly is no longer a casual default — it's the result of one negative experiment.

The defensible v1.0 stance:
> *"We use Claude Haiku 4.5 throughout. Tested cheap-cascade on gpt-4o-mini for sub-agents — the system actually got MORE expensive (mega-agent compensated for thinner extractor outputs by calling 4.5x more tools and producing 3.2x more input tokens). Tight coupling between sub-agents and mega-agent grounding means you can't naively trade extractor quality for cost."*

This contradicts the common intuition that decomposed pipelines should obviously cheap-cascade. They should — but only when the sub-agent outputs are decoupled enough from the main agent's grounding that quality regressions don't cascade. Discovery's architecture has tighter coupling than that intuition assumes.

### For the Glean / Waldo comparison

Our pattern is **role specialization within one model tier** (validated). Their pattern is **model-tier specialization** (small model handles the search loop, frontier handles reasoning). Both work; the choice of which to apply depends on how tightly coupled the sub-tasks are to the main agent's reasoning.

Search-loop tasks (Waldo's domain) are relatively decoupled — the small model can iterate independently, and the frontier model just consumes the final retrieved context. Discovery's structured extraction is more tightly coupled — the mega-agent's conversational quality depends on the structured state being sharp.

---

## Caveats

- **n=1.** Same script, one comparison. Could be noise. Worth re-running on a different script to confirm.
- **gpt-4o-mini is just one cheap option.** GPT-5-nano, Gemini Flash, Llama 3 8B might behave differently. Not blanket-tested.
- **Prompt-tuning matters.** Re-authoring prompts specifically for gpt-4o-mini's quirks might recover most or all of the lost quality. Untested.
- **The sharpener and synthesizer share a model slot in v0.8.** So this test conflates two changes (synth on gpt-4o-mini AND sharpener on gpt-4o-mini). A cleaner test would vary them independently.

---

## What to do with this

1. **Don't ship cheap-cascade in v1.0** without per-sub-agent retesting and prompt re-tuning.
2. **Keep the optimization on the backlog** — it might be recoverable with prompt work — but stop assuming it's free.
3. **The "Haiku 4.5 throughout" architectural choice is now defensible** by experiment, not just convention.
4. **Don't claim model-tier specialization** in any external comm without doing the test more rigorously first.
