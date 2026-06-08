# Runtime portability — the same pipeline across three substrates

**Status:** Validated. n=3 runs each for Python + LangGraph; n=1 for Claude Workflow. One use case (SE copilot, `sess_b6b350634626`).
**Date:** 2026-06-03
**Repo:** https://github.com/andrew-lentz-atlan/discovery-inception
**Probe:** `tools/portability_probe.py` (Python leg) + `tools/portability_probe_langgraph.py` (LangGraph leg); Workflow leg via the Claude Code Workflow tool.

---

## TL;DR

We ran the **same** inception slice — classify → propose skills → select architecture — on three orchestration substrates: our hand-rolled Python engine, LangGraph, and Claude Workflows. Same prompts, same patterns, same Pydantic schemas, same model (claude-haiku-4-5 via the same proxy). Only the orchestration glue differed.

**The load-bearing decision — architecture — was identical across all three** (`single-agent-react`, ~0.78–0.82 confidence, same rejected alternatives). **LangGraph was decision-identical to Python on every axis.** The Claude Workflow leg diverged on two classification axes — but the cause was a non-faithful port (prompt delivery), not a runtime limitation, and the architecture still converged.

**The finding:** orchestration substrate is decision-neutral. Build the contract right — prompts + schemas + the output-format system prompt + faithful prompt delivery — and the runtime becomes a swappable adapter. Runtime choice is then a *maintenance-economics* question ("how many adapters do you want to own"), not a *capability* one.

---

## The method (why this is a finding, not an anecdote)

You cannot claim "same across runtimes" without first knowing the **within-runtime variance** — otherwise you can't tell a runtime difference from plain model noise. So the anchor was: run the **same** runtime (Python) three times and measure how much it varies. Cross-runtime difference only counts if it exceeds that band.

The legs were built to differ **only** in the orchestration substrate:
- same rendered prompts (the real patterns baked in)
- same Pydantic schemas
- same model via the same LiteLLM proxy
- same output-format system prompt + lenient-parse + Pydantic validate

---

## The data

| Decision | Python ×3 | LangGraph ×3 | Claude Workflow ×1 |
|---|---|---|---|
| interaction_shape | conversational (×3) | conversational (×3) ✓ | query-response ✗ |
| decision_complexity | judgment-heavy (×3) | judgment-heavy (×3) ✓ | judgment-heavy ✓ |
| state_shape | session-scoped (×3) | session-scoped (×3) ✓ | long-horizon ✗ |
| learns_from_experience | False (×3) | False (×3) ✓ | false ✓ |
| workload confidence | 0.65 (×3) | 0.65 (×3) ✓ | 0.50 ✗ |
| **architecture (selected)** | **single-agent-react (×3)** | **single-agent-react (×3)** ✓ | **single-agent-react** ✓ |
| architecture confidence | 0.78 (×3) | 0.78–0.82 ✓ | 0.80 ✓ |
| rejected alternatives | adv-decomp, chained-pipeline (×3) | same (×3) ✓ | same ✓ |
| skill count | 7 (×3) | 6–7 | 6 |
| skill names | wobble (2/3 runs identical) | wobble (same family) | same family |

### Within-runtime variance (Python ×3): near-zero on decisions
Every classification axis and both confidences were **identical** across the three Python runs. Architecture was identical. The **only** thing that varied was the skill *names* (and count, 6–7) — the granular cut drifts run-to-run even with everything else fixed.

So the variance band on the *decisions* is essentially zero, and the band on *skill naming* is real-but-bounded (same family, ±1 skill).

---

## What it shows (the causal read)

1. **Architecture — the load-bearing decision — is portable, full stop.** `single-agent-react`, same confidence, same rejections, across all three substrates. Zero meaningful variance. The decision that most shapes the downstream build does not care which runtime computes it.

2. **Pure orchestration substrate is decision-neutral.** LangGraph (a StateGraph) and our imperative Python engine produced **identical decisions on every axis** — the only difference was the same skill-name wobble Python shows against itself. Swapping the orchestration glue changed nothing that matters. This is the cleanest evidence for the thesis.

3. **The Workflow divergence was port-fidelity, not runtime capability.** The Claude Workflow leg diverged on `interaction_shape`, `state_shape`, and confidence — beyond Python's zero-variance band, so the difference is real. But it is explained: that leg's agents *Read the prompt from a file* (paginating a 358K-char prompt) under a minimal schema and a different system-prompt wrapper — i.e. the contract was delivered **unfaithfully**. The contract-faithful leg (LangGraph) matched Python exactly. So the divergence measures *how faithfully you ported*, not *how capable the runtime is*. And even unfaithfully ported, the architecture still converged.

4. **Skill-naming wobble is model nondeterminism, not a runtime property.** It shows up within a single runtime (Python run 2 differed from runs 1 & 3) as much as across runtimes. The skill *count* and *family* are stable; the exact names drift everywhere. Don't attribute it to the substrate.

---

## Rework is minimal but NOT zero — the per-adapter tax

Porting the LangGraph leg surfaced two real gotchas — the honest cost of an adapter:

1. **Provider structured-output constraints.** LangChain's `with_structured_output()` sends a Bedrock-native JSON Schema that **rejects `minimum`/`maximum` on number types** (our `confidence: ge=0/le=1`). The Python engine never hits this — it puts the schema in the *prompt* and Pydantic-validates the response, sending no schema to the model. Fix: handle output the Python way (parse + validate).
2. **The output-format system prompt is part of the contract.** A bare `invoke(prompt)` let the model append trailing prose → "Extra data" JSON parse failures the Python engine never sees, because `call_step` sends a system prompt ("output only the JSON object, begin with `{` end with `}`"). Replicating it fixed it.

Neither is a blocker; both are *carry-the-contract-faithfully* details. That's the precise shape of "minimal rework": the **decisions** port for free, but each adapter makes you re-apply the output-plumbing contract (system prompt, schema-delivery mechanism).

---

## What it means

- **For the v1.0 runtime decision:** runtime choice is not a capability question — all three reproduce the decisions. It's a maintenance-economics question: how many adapters do you want to maintain, weighed against language/stack cost and lock-in (see `docs/internal/research-log.md`'s fork scorecard). The contract — prompts + schemas + lifecycle + the output-format system prompt — is the asset; the runtime is the adapter.
- **For the architecture story:** this is the empirical backing for `patterns/decision-guides/framework-or-hand-roll.md` and the ports-and-adapters stance. "Build the contract right and it ports" is no longer an assertion — it's a measured result, with the within-runtime variance baseline that makes it credible.
- **The honest boundary:** the LOAD-BEARING decision (architecture) is the strongly-portable one. Upstream classification ports too *when the contract is delivered faithfully* (LangGraph proved it); deliver it sloppily and classification can wobble (the Workflow leg). So portability is real but conditional on port fidelity — not a free lunch.

---

## Caveats

- **n=1 on the Workflow leg.** Its divergence is diagnosed (port infidelity), corroborated by LangGraph's clean match, but a faithful Workflow re-run (prompt-as-message, full schema, ×3) would confirm it directly. Worth doing before the v1.0 cutover.
- **One use case** (SE copilot). The architecture for SE is an unusually stable pick (single-agent-react dominates the co-pilot class); a more contested workload might show more cross-runtime spread on architecture. Re-run on the P&G FHC session to test.
- **Slice, not the whole pipeline.** Steps 1–3 (classify/skills/architecture); not the scaffold writer (step 5) or the discovery half. The discovery side (pyatlan, the artifact seam) is the part with the real *language/stack* port cost, separate from this decision-fidelity question.
- **Same model across legs.** This isolates the orchestration substrate — it does NOT test model-portability (Claude vs GPT vs Gemini), which is a different axis.
