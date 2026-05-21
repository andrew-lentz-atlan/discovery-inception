---
title: Definitions Without Context
category: anti-patterns
status: validated
last_updated: 2026-05-20
source_findings: []
source_external:
  - https://github.com/bladata1990/pg-brand-analyst-agent  (README, "Key Design Decisions" §2)
applies_when:
  workloads: [multi-skill-with-classification, structured-extraction-with-taxonomy, root-cause-diagnosis]
  constraints: [orchestrator-narrates-after-classification, taxonomy-stored-in-external-knowledge-layer]
contradicts: []
related:
  - lessons-from-builders/bala-data-summary-not-raw-rows
  - skill-design/inner-pipeline
  - architectures/single-agent-react
---

# Definitions Without Context (a.k.a. "Labels Without Their Meaning")

When a sub-agent or skill classifies something into a taxonomy and passes only the **label** (not the **definition**) upstream to an orchestrator that then has to reason about the classification — the orchestrator hallucinates to fill the gap.

The failure mode is invisible until you notice that the orchestrator's narrative makes claims the underlying data doesn't support. It's reasoning from the *name* of the category rather than its *content*.

The fix is structural: every classification result must carry the definition of the category it claimed with it. The orchestrator gets `{label: "BCA_Competitive", definition: "competitor IYA > 100 required; without it, the share transfer is BCA_Distribution"}` — not just `{label: "BCA_Competitive"}`.

---

## Where this happens

The canonical example is Bala's P&G Brand Analyst Agent (https://github.com/bladata1990/pg-brand-analyst-agent), where the root-cause skill classified market-share-shift causes into a 5-category BCA (Business Change Analysis) framework: Distribution, Promotion, Pricing, Assortment, Competitive.

Early versions of the skill returned only the chosen label (`"BCA_Competitive"`) to the orchestrating agent. The orchestrator then wrote the narrative report. Without the definition, it hallucinated competitor promotional activity that did not exist in the underlying Trade Panel data — because *"BCA_Competitive"* sounds like it should mean *"competitor did something active"*.

The actual definition of `BCA_Competitive` (stored in Atlan) says: *"competitor IYA > 100 required; without it, share transfer is BCA_Distribution."* That is, passive share absorption (the competitor gaining share because the focal brand lost shelf space) is *not* BCA_Competitive — it's BCA_Distribution. The orchestrator could not have known this from the label alone.

The fix was returning `bca_framework: {full definitions}` alongside the labels. Bala's score went from 87/100 to **97/100** with this single change.

---

## When this anti-pattern shows up

- **Multi-skill architectures where one skill classifies and another narrates.** The classifier owns the taxonomy; the narrator reads the result. Without the definitions traveling, the narrator only has the labels.
- **Taxonomies with non-obvious decision rules.** If category names are self-explanatory (e.g., "red" vs "blue"), the label-only pattern works. If category names require domain knowledge to interpret (BCA_*, ICD-10 codes, regulatory classifications), the label is insufficient.
- **Orchestrators that have to write prose about classifications.** Anywhere the output is a story rather than a structured record. Prose composition requires understanding what the categories *mean*, not just what they're called.
- **Taxonomies stored in an external knowledge layer** (Atlan glossary, ontology server, config file). The skill fetches the definitions to do its classification; if it doesn't pass them along, the orchestrator has no way to fetch them itself.

---

## Empirical receipts

Bala's documented learning (https://github.com/bladata1990/pg-brand-analyst-agent README, "Key Design Decisions" §2 "bca_framework must reach the orchestrator"):

> *"Early versions returned only the diagnosis labels ('bca_category': 'BCA_Competitive') to the orchestrator. The orchestrator had the label but not the definition, and hallucinated to fill the gap — inventing Tide promotional activity that did not exist in the data.*
>
> *The fix is `result['bca_framework'] = bca` at the end of `root_cause_skill`. Now the orchestrator receives both the diagnosis and the actual definition of each BCA category. When writing the report narrative, it reads the real BCA_Competitive definition ('competitor IYA > 100 required; without it, share transfer is BCA_Distribution') and correctly classifies Tide's share gain as passive absorption rather than active competitive action.*
>
> ***Judge score before this fix: 87/100. After: 97/100.***
>
> *This is a general principle: if the orchestrator needs to reason about a domain concept, it needs the concept definition — not just the conclusion derived from it."*

This is a 10-point quality jump on a 100-point LLM-as-judge scale, from a single structural change. The fix cost ~2 lines of Python. The hallucination it eliminated was the specific failure mode (inventing competitor promo activity) the eval rubric scored on.

---

## How to detect this anti-pattern in your own code

- **Symptom A:** the orchestrator's prose makes claims about category contents that aren't in the input data. If you see "Tide ran an aggressive feature campaign" and the underlying data has no Tide TDP increase, the orchestrator is reasoning from the label, not the data.
- **Symptom B:** swapping the model from frontier to mid-tier changes the orchestrator's narrative significantly. If Claude Opus narrates correctly but Claude Sonnet hallucinates, the label-only pattern is leaning on Opus's internal world model to fill in the missing definitions — that's not robust.
- **Symptom C:** the same skill produces the same structured output but different downstream narratives across runs. Stochastic hallucination filling a definition gap.

**Check:** trace what your classifier skill returns. If it's just `{label: "X"}` or `{label: "X", confidence: 0.9}` and the downstream orchestrator narrates about X — you might have this anti-pattern.

---

## The fix

Always return the taxonomy alongside the classification:

```python
def root_cause_skill(...) -> dict:
    bca_framework = fetch_from_atlan("Business_Change_Analysis")  # all 5 BCA_* definitions
    drivers = classify(...)  # uses bca_framework as context

    return {
        "drivers": drivers,           # the labels
        "bca_framework": bca_framework,  # the definitions
        # ... rest of the result
    }
```

The orchestrator's prompt then has access to the definitions when it writes the narrative.

Cost: a few hundred extra tokens per call (the definitions). Benefit: 10-point quality improvement empirically. Trade is overwhelmingly favorable.

---

## Generalization

This pattern is not specific to BCA or P&G or root-cause analysis. It applies anywhere classification flows into prose generation. Examples beyond Bala's case:

- A diagnosis skill that returns ICD-10 codes — pass the code descriptions alongside
- A risk-scoring skill that returns severity tier (`critical | high | medium | low`) — pass the tier definitions, which are usually load-bearing for downstream prose
- A sentiment-analysis skill that returns category labels — pass the rubric used to assign them

The pattern says: **definitions must travel with labels when prose generation is downstream.**

---

## Variants & related patterns

- **`lessons-from-builders/bala-data-summary-not-raw-rows.md`** — another Bala lesson, also about *what context the orchestrator/interpreter needs*. Both lessons share an underlying principle: don't strip context the downstream LLM call needs.
- **`skill-design/inner-pipeline.md`** — the skill design where this anti-pattern shows up most. Pre-classify inside the skill; return label + definition.
- **`architectures/single-agent-react.md`** — the architecture where this matters most. Single-agent orchestrator reading skill outputs is the canonical case.

---

## Maintenance notes

- Authored during the gold-standard seed pass 2026-05-20.
- Status: `validated` based on Bala's explicit before/after empirical receipt (87 → 97).
- The underlying principle ("downstream reasoning needs upstream context") may eventually graduate to a more general entry once we have 2-3 other empirical cases. For now, this is the canonical example.
- The 10-point judge-score jump should be cited whenever this pattern is referenced — it's the strongest evidence we have that the fix is load-bearing, not aesthetic.
