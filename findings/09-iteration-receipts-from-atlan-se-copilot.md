# Iteration receipts from atlan-se-copilot — what real runs taught us

**Status:** Five sub-findings from a single real-world build. n=1 use case, multiple iterations across two paths.
**Date:** 2026-05-29
**Repo:** https://github.com/andrew-lentz-atlan/discovery-inception
**Sessions:** `atlan-se-copilot` Path A (v1 → v2 → v3 iterative) and Path B (one-shot with consolidated facts)

---

## TL;DR

First serious external use of discovery-inception on a real Atlan build (an SE copilot agent). Ran two paths against the same problem: Path A iterated three times feeding feedback through `PriorIterationFeedback`; Path B consolidated all constraints up-front and ran once. **Path B produced a measurably better starter agent** — and the comparison surfaced five things that hadn't been visible from synthetic scripts.

1. **Calibrated confidence is bidirectional.** It rises when ambiguity gets eliminated, falls when feedback expands the design space, and rises again when constraints arrive coherent vs. sequentially.
2. **Anchoring lives in spec history, not the inception cache.** `--force` clears the inception cache but doesn't clear the conversational journey baked into `spec.md` — and that history is what the inception phase reads.
3. **Iterate at the spec/chat-fill layer, not at the inception layer.** The Loop-2 feedback channel is real but it's for evaluation-driven refinement, not constraint completion. Constraint completion belongs upstream.
4. **Deterministic post-processors are now a load-bearing pattern.** Four of them in production after this run (Mermaid sanitizer, distill snap-slot clarification, lenient JSON parser, topic canonicalization). The pattern is firming up: prompts can't reliably guarantee LLM output shape; regex post-processors close the gap.
5. **`PriorIterationFeedback` is dual-purpose.** Designed for post-build evaluation feedback, it also works as a mid-iteration context injection channel — same schema, same routing semantics.

This is the first finding written from the receipts of a real run, not from a controlled experiment. The patterns are noisier but the lessons are harder to dismiss.

---

## What we ran

Single use case: build a starter agent for Atlan's SE team that triages customer questions, pulls context from Atlan's metadata, and drafts response artifacts. Real customer-specific information involved (which is why the artifacts themselves stay private — see the gitignored leak guardrail in `ecf7cd5`).

**Path A (iterative):**
- v1 — discovery from artifacts + chat fill → inception
- v2 — `PriorIterationFeedback` with corrections from v1 review → inception (`--force`)
- v3 — `PriorIterationFeedback` with additional context that was newly remembered during v2 review → inception (`--force`)

**Path B (one-shot):**
- All constraints from v1 + v2 + v3 reviews consolidated into a single chat-fill pass
- Single inception run

Both paths landed on the same architectural classification ("orchestrated multi-skill agent on Claude Agent SDK"). Path B got there cleaner, with higher confidence and a tighter skill cut.

---

## Finding 1 — calibrated confidence is bidirectional

The interesting thing about confidence over the three Path A iterations wasn't that it went up or down — it was that it went **up, then down, then up**, and each direction was telling.

| | v1 | v2 | v3 | Path B |
|---|---|---|---|---|
| Final theory confidence | medium | high | medium | high |
| Number of skills proposed | 5 | 4 | 6 | 4 |
| Citations to spec history | 11 | 18 | 14 | 21 |

**v1 → v2: confidence rose because feedback eliminated ambiguity.** The v1 spec was hedged on whether the agent should draft or just retrieve. v2's feedback nailed it to "draft response artifacts the SE reviews before sending." Ambiguity-elimination → narrower design space → higher confidence.

**v2 → v3: confidence fell because feedback expanded the design space.** v3's feedback added two newly-remembered constraints: "SE should be able to swap drafting tone per customer" and "needs to handle multi-product threads." Both legitimate, both added new dimensions the model now had to cover without dropping prior commitments. More dimensions → more skills proposed → higher chance one of them is mis-cut → lower confidence.

**Path B vs Path A v3: confidence rose when the same constraints arrived coherent vs. sequential.** Path B saw all of v1's, v2's, and v3's constraints simultaneously — the model could weigh them against each other before settling on a skill cut. Path A v3 saw them serially, anchored on the v1 framing, and had to retrofit the new constraints into a structure that wasn't built for them.

The implication: **confidence is a signal about the spec's coherence, not its richness.** A spec with more constraints isn't necessarily a higher-confidence spec — it depends on whether the constraints arrived in a form the model could integrate.

---

## Finding 2 — anchoring lives in spec history, not the inception cache

Going into v2, the assumption was that `--force` would let inception reconsider freely. It didn't. The v1 classification (one of the skills was framed as "session-scoped state holder" which was a v1-era reading) persisted into v2 and v3's reasoning. Even with `--force` clearing the inception cache, the model kept citing back to that framing.

The reason became obvious in hindsight: **`--force` clears the inception cache, but it doesn't clear `spec.md`.** And `spec.md` is what the inception phase reads. The conversational journey — including the questions asked, the user's answers, and the working theory the synthesizer crystallized — is all there. The model wasn't anchored on stale inception output; it was anchored on the spec.md's own framing of the problem.

This is structurally analogous to LLM hallucination from in-context documents: the model trusts what's in its context window over its own re-reasoning. The fix isn't a bigger hammer at the inception layer — it's regenerating the spec from a clean chat-fill pass.

This bled into the Path B decision. Path B isn't just "one-shot is cheaper" — it's "if you want to genuinely re-evaluate, regenerate the spec."

---

## Finding 3 — iterate at the spec/chat-fill layer, not the inception layer

The above two findings combine into a workflow lesson. `PriorIterationFeedback` exists. It works. It's load-bearing for a real use case (post-build evaluation where you've shipped v1 of your starter agent and want to incorporate operational learning). But it is **not** the right channel for "I forgot to mention X."

The optimal practitioner workflow:

1. **Use chat-fill to surface all constraints up-front.** The interview is designed for this. If you remember something mid-iteration, restart chat-fill, don't loop through inception.
2. **Use Loop 2 / `PriorIterationFeedback` for evaluation feedback.** "Skill X turned out to be wrong because the agent hit case Y we hadn't anticipated" — that's what the feedback channel was built for. Not "I want to add a new constraint."
3. **Use `--force` to regenerate inception artifacts after spec changes.** Not as a mechanism to make inception reconsider from a stale spec.

The architectural reframe: **inception is a deterministic projection of the spec**, not a place where new information enters. New information goes in the spec. Inception just renders it.

---

## Finding 4 — deterministic post-processors are now a load-bearing pattern

This run surfaced four production failures in LLM-output shape that prompts alone couldn't fix. Each one got a deterministic post-processor. The pattern is now codified across the codebase.

| Post-processor | What it fixes | Lives in | Codified by |
|---|---|---|---|
| Mermaid node-label sanitizer | Unquoted hexagon/rectangle labels with `()`, `/`, `:` that GitHub/VSCode renderers reject | `agent/inception/run.py` `_sanitize_mermaid_node_labels` | `c8038c3` |
| Distill snap-slot clarification | Prompt-level fix for "snap to canonical topic" being read as "skip recording the fact" | `agent/prompts/02_distill.md` | `a2b4ee1` |
| Lenient JSON parser | Trailing commas + missing-comma-between-fields that occasionally trip strict `json.loads` | `agent/json_utils.py` | `a57f787` |
| Topic canonicalization (pre-existing) | Synthesizer + distill emitting slight topic-name variants | `agent/topics.py` (pre-existing) | (earlier) |

Each one fits the same shape: the LLM emits output the system expects in a deterministic form, the model gets it mostly right but with a predictable error class, and a small regex / lookup table closes the gap deterministically rather than asking the model to try again.

This is now a deliberate architecture pattern, not a series of one-off bug fixes. The principle: **prompts establish intent; deterministic post-processors enforce shape.** When the gap between intent and shape is regular enough to regex over, regex over it. Reserve retries for output that's actually wrong, not output that's syntactically off.

---

## Finding 5 — `PriorIterationFeedback` is dual-purpose

The original design intent for `PriorIterationFeedback` was post-build evaluation: ship v1, learn things, feed those lessons back. The schema reflects that — `targets_step` lets you scope feedback to a specific inception step, `free_text_lessons` captures qualitative learning.

What this run revealed: **the exact same schema works for mid-iteration context injection.** v2's feedback wasn't "skill 3 was wrong in production" — it was "we forgot to mention the drafting tone constraint, please integrate." Same routing semantics: scope to a step, attach the text. The model handled both the same way.

This is good news (no schema change needed) and a warning (people are going to use it that way whether we intend them to or not). The mitigation isn't to gate the channel — it's to make the alternative (regenerate spec) friction-free enough that practitioners reach for it first.

---

## What this means

### For the workflow doc / skill prompts

The skill should distinguish two iteration modes when it surfaces feedback collection:
- **"I want to add or correct a constraint"** → regenerate chat-fill, then run inception fresh
- **"I want to give post-build evaluation feedback"** → use `PriorIterationFeedback`

Currently the skill conflates these. v0.10 should split them.

### For the patterns workstream

These findings are evidence for the broader architectural argument that **the iteration loop is structurally important**, not just a build convenience. Patterns/ should treat "how do you iterate on this agent" as a first-class concern in every harness deep-dive — LangGraph state checkpointing, Claude Agent SDK ReAct loops, Cortex YAML edits all have different iteration ergonomics.

### For the v1.0 narrative

The defensible claim sharpens:
> *"Inception is a deterministic projection of the spec. Iteration belongs at the spec layer. We tested both — one-shot consolidated constraints beat iterative-with-feedback on the same use case, because the model could weigh constraints against each other coherently rather than retrofit them into a stale framing."*

This is a v1.0-level architectural commitment, not a tactical observation.

### For deterministic post-processors as a pattern

Four instances now, all with the same shape. Worth a short pattern entry in `patterns/cross-cutting/` once Phase 1 of the patterns workstream is up. The principle is reusable: any agent system that consumes LLM output as structured data should have a designated layer for "regex over the regular error classes."

---

## Caveats

- **n=1 use case.** Same atlan-se-copilot build across paths. Confidence direction findings could partly be specific to this problem's constraint shape.
- **Path A and Path B aren't perfectly comparable.** Path B used the union of all constraints discovered during Path A's iterations — so Path A is also doing real work surfacing those constraints, even if the iteration didn't help the final output.
- **Customer-specific content is gitignored.** The artifacts themselves can't go in the repo. Findings here describe the patterns, not the content.
- **`PriorIterationFeedback` dual-use observation is from one user (me).** Other practitioners may use it differently. Worth watching.

---

## What to do with this

1. **Ship the four deterministic post-processors** (already done across `c8038c3`, `a2b4ee1`, `a57f787`).
2. **Update the skill** to distinguish "add a constraint" from "post-build feedback" — v0.10 task.
3. **Promote this finding's deterministic post-processor observation** into a patterns entry once `patterns/cross-cutting/` is established.
4. **Treat iteration ergonomics as a first-class harness comparison axis** in the patterns deep-dives.
5. **Stop using `PriorIterationFeedback` for constraint completion personally** — regenerate the spec instead. Walk the talk before recommending the workflow externally.
