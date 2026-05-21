---
title: Definitions Without Context
category: anti-patterns
status: validated
last_updated: 2026-05-20
source_findings: []
source_external:
  - https://github.com/bladata1990/pg-brand-analyst-agent  (README §2)
applies_when:
  workloads: [multi-skill-with-classification, structured-extraction-with-taxonomy, root-cause-diagnosis]
  constraints: [orchestrator-narrates-after-classification]
contradicts: []
related: [truncated-data-summary]
---

# Definitions Without Context

When a sub-agent or skill classifies into a taxonomy and passes only the **label** (not the definition) upstream to an orchestrator that then reasons about the classification — the orchestrator hallucinates to fill the gap.

The fix is structural: every classification result must carry its category definition with it. Don't return `{label: "BCA_Competitive"}`; return `{label: "BCA_Competitive", definition: "competitor IYA > 100 required; without it, share transfer is BCA_Distribution"}`.

## Detect when

- Orchestrator's prose makes claims about category contents not in the input data
- Swapping the model (frontier → mid-tier) changes the narrative significantly (frontier was filling the definition gap from training data)
- Same skill output produces different downstream narratives across runs (stochastic hallucination)
- Classifier skill returns only `{label: "X"}` and downstream LLM narrates about X

## Don't worry about when

- Category names are self-explanatory (e.g., "red" / "blue") — labels are sufficient
- Output is structured-only (no prose generation downstream)
- Single-agent loop where the classifier and narrator are the same LLM call (definition is in context already)

## Key gotchas

- **Cost of the fix is trivial.** A few hundred extra tokens per call. Don't optimize them away.
- **The pattern applies to any taxonomy.** ICD-10 codes, risk-severity tiers, sentiment categories — anywhere downstream prose interprets the label.
- **Source the definitions from a knowledge layer (Atlan glossary, ontology server) at runtime**, not from the system prompt. Updating the definition then changes behavior without code changes.

## Empirical anchor

Bala's P&G Brand Analyst Agent. Early versions returned only BCA category labels; the orchestrator hallucinated competitor promotional activity to fill the gap. Fix: return `result["bca_framework"] = bca` alongside the diagnosis labels. **Judge score: 87 → 97.** Single structural change, 10-point quality jump on a 100-point LLM-as-judge eval.

Origin: documented by Bala (P&G Brand Analyst Agent README §2, *"bca_framework must reach the orchestrator"*).
