# Three architectures, one discovery agent: mega vs chained vs hybrid

**Status:** Research note. n=1 use case, one 5-turn script. Read accordingly.
**Date:** 2026-05-05
**Repo:** https://github.com/andrew-lentz-atlan/discovery-inception
**Comparison artifact:** [`agent/baselines/results/scope_creep_5turn_ABC__20260505_150559.md`](../agent/baselines/results/scope_creep_5turn_ABC__20260505_150559.md)

---

## TL;DR

Building a discovery agent (interviews a customer, produces a structured spec for a builder), we compared three architectures empirically — same model, same priors, same customer script, different orchestration:

- **A — Chained:** five small task-scoped sub-agents per turn (triage → distill → synthesizer → why-prober → probe-generator). Decomposition all the way down. The system we'd been building (v0.5).
- **B — Mega-agent baseline:** one strong-prompted LLM call per turn that bakes in everything the chain encodes structurally.
- **C — Hybrid:** small extractor sub-agents produce structured state on each turn; one mega-agent runs the conversation as a single call with spec-introspection tools (`get_current_spec_state`, `get_working_theory`, `get_checklist_progress`).

Headline result on one 5-turn deterministic script:

| | A (chained) | B (mega) | C (hybrid) |
|---|---|---|---|
| Wins on conversation quality (subjective) | 0/5 | 2/5 | **3/5** |
| Total wall time | 75s | **16s** | 85s |
| Tokens (mega-call only) | n/a | 14K | 38K |
| Structured spec produced | ✓ | ✗ | ✓ |
| Spec-tool invocations | n/a | n/a | 4 |

The honest finding: **decomposition is not load-bearing for *conversation quality*. It IS load-bearing for *structured deliverables*. The hybrid recovers both at a token-cost premium.**

This contradicts our pre-test hypothesis. It supports a refined one: the right level of decomposition depends on what you're trying to produce — prose vs structure.

n=1. Treat as a starting hypothesis, not a conclusion.

---

## What we were testing

The central architectural question: **does decomposition into small task-scoped sub-agents produce a better discovery agent than a single strong-prompted LLM call?**

The hypothesis going in was yes — because decomposition lets each sub-agent specialize, lets us route to the cheapest sufficient model per step, and produces an inspectable per-step trace. Frontier-model harnesses (Claude Code, Cursor) inject huge amounts of context per turn; we believed a chain of focused calls would beat that even at small-model scale.

We had no direct comparison. The chained agent worked — produced sharp probes, caught failure modes, iterated cleanly when prompts were edited — but we hadn't measured it against the obvious baseline: *same model, same priors, single strong prompt*.

So we built one. Then we built a hybrid.

---

## The setup

**Customer script (deterministic, agent-agnostic).** 5 turns chosen to exercise different patterns:

1. Concrete opening: *"We want to reduce time-to-first-value from 90 days to 30."*
2. Relevance pushback: *"explain how these questions help me build the agent."*
3. Dense structured content: 100-word multi-agent system breakdown (CSM, CSA, IE, Support, SoCo).
4. Concrete success criteria: *"priority connectors in, metadata bootstrapped, success plan complete."*
5. Long case study: 200-word scope-creep walkthrough with ~10 embedded facts.

Each customer turn is identical across systems — they don't depend on what the agent asked previously.

**Three systems**, each given the same `claude-haiku-4-5` model, the same RoleContext priors (our intake-side Solutions Consultant context.json), and the same use-case seed:

- **A — Chained:** v0.5 architecture. Five sub-agents per turn: triage labels the customer's message; distill captures concrete facts; synthesizer updates a working theory; why-prober tries to reach bedrock (phase 2); probe-generator picks the next probe. Orchestrator is dumb code; conversation is structurally driven.
- **B — Mega-agent:** single LLM call per turn with a 10K-character system prompt that bakes in everything the chain encodes structurally — *"do breadth before depth," "every question must justify itself," "use customer vocabulary," "don't grind whys past bedrock,"* etc. The strongest single-prompt baseline we could write.
- **C — Hybrid:** extractor sub-agents (triage, distill, synthesizer) update structured state per turn; mega-agent runs the conversation as a single call with three tools available (`get_current_spec_state`, `get_working_theory`, `get_checklist_progress`). The mega-agent is in charge of the conversation; extractors run as a structured-output skill underneath.

The comparison driver runs all three concurrently per turn. Customer messages are identical across systems. Auto-collected metrics: latency, response length, customer-vocabulary mirror count, generic-SaaS-language count, rationale-cue presence, mega-agent token usage. Per-turn quality assessed subjectively from verbatim transcripts.

---

## Results

### Quantitative

| Metric | A (chained) | B (mega) | C (hybrid) |
|---|---|---|---|
| Total wall time | 75 s | **16 s** | 85 s |
| Avg per turn | 15 s | **3.3 s** | 17 s |
| Customer-vocab terms (5 turns sum) | 13 | 10 | 9 |
| Generic SaaS-org terms (lower=better) | 0 | 0 | 0 |
| Detected rationale | 1/5 | 1/5 | 1/5 |
| Tokens (mega-call only) | n/a | 14K | 38K |
| Spec-tool invocations | n/a | n/a | 4 |
| Structured spec produced | ✓ | ✗ | ✓ |

### Qualitative — per-turn winners (my read of verbatim transcripts)

| Turn | What it tested | Winner | Why |
|---|---|---|---|
| 1 | concrete opening | **C** | *"What are the 2–3 biggest time sinks in the first 30 days that, if eliminated or sped up, would move the needle most on getting from 90 days to 30?"* — pivoted to current_pain, time-bound, naive-on-purpose. Sharper than A's overlong enumeration or B's good-but-generic alternative. |
| 2 | relevance pushback | **C** | C explicitly named four candidate agent shapes with tradeoffs (*"builder / coordinator / customer-facing / copilot"*) and asked which one was closest. B's response was rich but didn't enumerate candidates. A's was canned (architecturally constrained by the relevance-challenge short-circuit). |
| 3 | dense structured content | **B** | B nailed the synthesis in two sentences (*"SoCo is the orchestrator, not the executor — that changes everything"*) and asked a sharp time-anchor question (90→30 days from contract sign or CSM handoff?). A produced the full strawman with 3 framings (also good, just slower). C used the working_theory tool but the response was thinner. |
| 4 | concrete success criteria | **C** | C used `get_checklist_progress`, then asked *"of those three deliverables — priority connectors, metadata bootstrapped, success plan complete — which today is the biggest bottleneck eating 60 days?"* Best framing because it pivots `success_metric` → `current_pain` leveraging the customer's exact phrasing. |
| 5 | long case study | **B** | B explicitly named *"you just gave me a decision point, not a question"* + extracted the 5-point checklist + played the working theory back ("Here's my working theory…"). The synthesis move at exactly the right moment. A's triage misclassified the case study as `meta` and asked a generic question. C's response was decent but didn't capture the rich content. |

**Score: C 3, B 2, A 0.**

---

## What surprised us

**The decomposed chain (A) did not win a single turn.** This was unexpected. Going in we believed decomposition would produce sharper questions because each sub-agent specializes. In practice the chain was constrained by its own structure — when triage misfired (turn 5 labeling a 200-word case study as `meta`), the entire pipeline downstream lost the content. The single-point-of-failure at the front of the pipeline turned out to be a real cost decomposition didn't compensate for. Architecturally A also had short-circuits (relevance-challenge canned response, strawman-once-per-session) that made specific turns worse, not better.

**The single mega-prompt (B) was much closer to "good enough" than we expected.** Given a strong system prompt that bakes in the same rules we encoded structurally — breadth-before-depth, theory-anchored probes, customer vocabulary mirroring, relevance justification — Haiku followed instructions well enough to produce competitive-quality conversations 3-5x faster than the decomposed chain. Notably B did this without producing structured output: everything it "knows" lives in conversational history.

**The hybrid (C) was the actual winner — but at a token-cost premium.** C's mega-agent invokes spec-introspection tools when grounding helps. The tool-calling iterations accumulate context, pushing total input tokens 2.7x above B's. Latency is comparable to A.

**The model used the tools naturally, without being prompted to.** C invoked `get_checklist_progress` before turns 1 and 4 (oriented before asking), `get_working_theory` after turn 3 (checked theory after dense content), and skipped tools entirely on turns 2 (relevance challenge) and 5 (case study synthesis). The model decided when grounding would help; we just made grounding available.

---

## What this implies

**For our project specifically:** the architectural thesis "decomposition is the skill" needs revision. The right thesis is more like:

> Decomposition is load-bearing where structured output, per-step debuggability, or per-step model selection are required. It is NOT load-bearing where conversational fluency is the deliverable — a strong-prompted single agent matches or beats decomposed orchestration on prose generation.

**For agent design more broadly:** "how big should an agent be?" probably has a use-case-specific answer, not a universal one. The pattern that worked best here — small extractors producing structured state + a single conversational agent that can READ that state via tools — is the *inversion* of the chained pattern. The conversational agent is in charge; the extractors are skills it can lean on. **"Skill as a tool, not as orchestrator."**

This maps to how human experts work: the FDE running a discovery call is one person driving the conversation, drawing on a structured mental model they update in their head. They don't have a "decomposed sub-self" handing them next questions. The hybrid architecture mirrors that: one fluent agent + a structured grounding it can consult.

**It also resolves the "skills vs chain of agents" debate at the framing level.** Skills get a bad rap when they're framed as *one big mega-model orchestrating 100 tasks*. They look good when they're framed as *small specialists assisting a focused conversational agent*. The architectural difference between "mega-model + skills" and "hybrid (one big agent + small helpers)" is who's in charge — and on this evidence, having a fluent single agent in charge of the conversation beats having an orchestrator trying to compose decomposed prose.

---

## Limitations

**n=1 use case.** One discovery script, one role (Solutions Consultant), one customer-domain (TechCo SoCo onboarding). The findings might not hold on use cases with different shapes — regulatory discovery, technical-bug discovery, contract negotiation. We expect the *direction* generalizes (hybrid > pure chain on conversation; pure mega misses structure) but the magnitudes might differ.

**Single model.** All three architectures used `claude-haiku-4-5`. The cheap-cascade thesis (Haiku for triage, Sonnet for synthesis, etc.) was not tested. It's plausible decomposition wins more clearly when each sub-agent runs on the cheapest sufficient model rather than uniformly on Haiku. The hybrid might also widen its quality lead with better models on the conversational call.

**Subjective quality assessment.** Vocabulary mirroring is auto-counted; the per-turn winners are one human's read of verbatim transcripts. A rigorous evaluation would have multiple raters or a scoring rubric.

**Synthetic customer.** The script was hand-written by someone who knows the domain well. A real customer would be messier — incomplete sentences, mid-thought pivots, backtracking, jargon mismatches. Behavior under that kind of input is not in this comparison.

**Token-cost premium for C is substantial** (38K vs 14K) and we haven't tried to optimize. Aggressive history pruning, selective tool exposure, or compressing the spec back into the agent's context periodically could plausibly reduce C's costs to closer parity with B without hurting quality. Untested.

**Architecture-specific failure modes weren't stress-tested.** A's triage misfire on turn 5 happened once. We don't know whether it happens 1% or 30% of the time. Same for B's hypothetical drift on long conversations (>10 turns) and C's tool-use behavior under adversarial scripts.

**Conversation length capped at 5 turns.** Real discovery calls run 30-60 minutes. B's context grows linearly; the hybrid can periodically compress history into the structured spec (which extractors maintain). The gap between B and C may widen significantly with conversation length, but we haven't measured.

---

## Open questions

1. **Does the hybrid pattern generalize to other agent jobs?** Coding agents, customer-support, writing assistants — does the inversion ("conversational agent in charge, decomposed skills underneath") win on those too, or does the right architecture differ by task?
2. **Can the cost premium of the hybrid be eliminated?** Tool-call iterations accumulate context. Can the model do most of its work with one spec-state read at the start of a turn rather than mid-turn iterations? Could the extractor outputs be auto-injected into the system prompt instead of fetched via tools?
3. **Where does the chained pattern still win?** We didn't find a turn where A beat both B and C in this run. There may be use cases (multi-counterparty discovery, multi-day discovery, adversarial customers) where strict structural enforcement of the conversation flow produces meaningfully better behavior.
4. **What happens on a 30-turn conversation?** Mega-agent context grows linearly; the hybrid can compress periodically. Does the gap widen with length? At what point does pure mega start to drift?
5. **Does per-step model selection change the picture?** What if extractors run on Haiku and the conversational mega-agent runs on Sonnet? Does C's quality lead extend, or does B catch up?
6. **Is the "skill as a tool" framing the right model for skills broadly?** This experiment suggests skills work better when called BY a focused agent than when carried by a single mega-model. If that generalizes, it's a real claim about how to compose skills in agent systems.

---

## Reproducibility

Full comparison artifact (turn-by-turn verbatim outputs, all metrics): [`agent/baselines/results/scope_creep_5turn_ABC__20260505_150559.md`](../agent/baselines/results/scope_creep_5turn_ABC__20260505_150559.md).

To reproduce:

```bash
cd discovery-inception

# 1. Start the chained agent (A) server in one terminal
uv run uvicorn agent.server:app --port 8010

# 2. In another terminal, run the comparison
uv run python -m agent.baselines.run_comparison \
    --script agent/baselines/scripts/scope_creep_5turn.json
```

Output goes to `agent/baselines/results/<script_name>_ABC__<timestamp>.md`.

To run additional scripts, add a JSON file to `agent/baselines/scripts/` following the schema in `scope_creep_5turn.json` (`use_case_seed`, `role_id`, `turns: [{n, customer, tests}]`). Each customer turn must be agent-agnostic — i.e., a plausible answer regardless of what the previous probe was — so all three systems see identical input.

---

## What we'd test next

Order of priority if we extend this:

1. **Run on 2-3 more scripts.** Different use cases (e.g., a CSM renewal-risk discovery; a technical-bug discovery). Validates that the C > B > A ordering generalizes.
2. **Run a 20-30 turn script.** Tests context-length behavior and whether the hybrid's compression advantage materializes.
3. **Cheap-cascade test.** Run extractors on Haiku and the conversational mega-agent on Sonnet. Re-run the comparison.
4. **Optimize C's token cost.** Auto-inject spec state into the system prompt instead of mid-turn tool calls. Measure quality loss vs token saved.
5. **Real customer transcripts.** Take 3-5 historical Gong recordings, transcribe, run them through extractors as the post-hoc "intake" mode. Compare structured outputs to what an FDE would have produced manually.
