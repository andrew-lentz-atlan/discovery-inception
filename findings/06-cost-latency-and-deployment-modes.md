# Cost, latency, and the three deployment modes

**Status:** Back-pocket research note. Captures the cost/latency reality of v0.8 and the product framing for v1.0+. Not an immediate action item; revisit when planning v1.0 productionalization.
**Date:** 2026-05-13
**Repo:** https://github.com/andrew-lentz-atlan/discovery-inception

---

## The constraint to keep in mind

v0.8 runs ~13–17s per customer turn. That's fine for text-based async usage where the user is willing to wait, but it has real implications for productionalization. The most important framing: **latency is the real constraint, not token cost.**

- Per-session cost: ~$0.50 on the 50-turn synthetic run (Haiku throughout). Not the constraint.
- Per-turn latency: 13–17s. Loses user trust on real-time interactive use; fine for async / batch.

---

## Where the time goes (v0.8 per-turn breakdown)

| Step | Typical time | Conditional? |
|---|---|---|
| Triage | 3–4s | always |
| Distill | 2–3s | ~70% of turns |
| Mega-agent (with tool iterations) | 5–8s | always |
| Probe-sharpener | 3–5s | most question-shaped responses |
| `synthesize_my_thinking` (when invoked) | 5–8s | rare (~2/50 turns) |
| `find_tensions` (when invoked) | 3–5s | rare |
| Session.save() I/O | <1s | always |

Steps are mostly **sequential because each depends on the prior step's output.** Triage gates distill; distill updates state the mega-agent reads; sharpener reviews the mega-agent's response.

---

## Optimizations available (no architectural change required)

In rough order of leverage:

| # | Optimization | Saves | Effort |
|---|---|---|---|
| 1 | **Cheap-cascade extractors** — triage/distill on a 1B-class model (Haiku→smaller) | 3–5s/turn | Low: env vars already exist (`DISCOVERY_TRIAGE_MODEL`, etc.) |
| 2 | **Anthropic prompt caching** — system prompt is ~10K chars, identical every turn | 1–2s/turn | Low: ~30 lines of code, supported by LiteLLM |
| 3 | **Skip sharpener when unlikely to help** — tiny pre-classifier predicts when rewrite is needed | 3–5s × 45% of turns | Medium: new classifier + plumbing |
| 4 | **Stream mega-agent response** — show words as they arrive; sharpener runs in parallel | improves perceived latency materially | Medium: streaming API + UI handling |
| 5 | **Speculative parallelism** — triage of turn N runs in parallel with mega-agent of turn N-1 | 1–2s/turn | Medium: async coordination |
| 6 | **History compaction** — summarize older turns into one condensed message | 0.5–1s/turn on long sessions | Low |

**Realistic target with all six:** 5–8 seconds per turn (vs current 13–17s). A 2–3x speedup without architectural change.

That's fast enough for responsive text-based usage. Still not real-time-fast for voice.

---

## The three deployment modes (Andrew's "2.5 modes in 1 packaging" framing)

All three use the same skill bundle (prompts, schemas, orchestration spec) and the same runtime core. They differ only in the **I/O adapter** — what feeds the pipeline and what consumes its output.

### Mode 1 — Post-mortem / transcript-driven (async)

**What:** Take a recorded call transcript (Gong, Zoom, Granola, etc.). Feed each speaker-attributed turn through the pipeline as if it were happening live, but synchronously, all turns processed in sequence. Export final spec.

**Latency relevance:** Irrelevant. Async batch processing. A 30-minute call could process in ~3-5 minutes of compute and that's fine — nobody's watching.

**Use case:** Process historical calls to extract structured discovery insights. Analyze recent calls after the fact. Run the full backlog of last quarter's discovery calls through the pipeline to build a structured knowledge base.

**Feasibility today:** ✅ Highly feasible. Mostly just a wrapper that loops through transcript speaker-turns. The orchestrator and prompts work as-is.

**Effort to build:** ~half-day. Transcript loader + speaker-turn iterator + the same pipeline we already have.

**Strategic value:** This is the LOWEST-RISK, HIGHEST-LEVERAGE first product surface. There are hundreds of recorded customer calls already on hand. Running this on them produces immediate structured value with zero customer-facing risk.

### Mode 2a — Co-pilot (sidebar augmentation, live call)

**What:** Live audio stream → speech-to-text → speaker-attributed turns → pipeline runs on customer turns → sidebar UI updates with working theory, gaps, tensions, suggested-but-not-required next question. The FDE drives the conversation; the agent annotates.

**Latency relevance:** Tolerable up to ~8-10s of staleness because the FDE provides conversational cadence. The agent is NOT generating "the next question on time" — it's maintaining a live state surface the FDE glances at between their own questions.

**Critical reframe:** the agent never speaks in the call. It just annotates. This is the architectural unlock that makes the latency tolerable. If the agent were trying to generate the next probe on the call's cadence, 5-8s lag would make it useless. As a sidebar showing "here's what's been captured, here's what's still open, here's what you might consider asking," 5-8s lag is fine.

**Use case:** Augment an Atlan FDE during a live customer call. Real-time discovery assistance that doesn't replace the human.

**Feasibility today:** ⚠️ Feasible with the optimizations above (target ~5-8s/turn) PLUS:
- STT integration (Deepgram, Granola, Otter — solved problem, ~1-2s latency)
- Speaker diarization (also solved)
- Sidebar UI (small web app or extension)
- Turn-segmentation logic (heuristic: speaker change + pause threshold)

**Effort to build:** ~1-2 weeks for v1 once Mode 1 is validated.

**Strategic value:** This is the headline demo. A live "Claude/discovery is listening to a real customer call and surfacing structured suggestions for the FDE" is the kind of thing that gets shared widely.

**Risk:** Trust is fragile. One bad suggestion during a real customer call and the FDE never opens the sidebar again. Must be earned by Mode 1's structured-extraction quality first.

### Mode 2b — Text-based autonomous interviewer (current)

**What:** User types a customer message. The agent runs the full pipeline. Agent's question comes back. Loop. THIS IS THE CURRENT v0.8 SHIPPING SHAPE — what the MCP server, CLI, and Claude skill all expose.

**Latency relevance:** Tolerable. Users will wait 13-17s per turn for high-quality output (which the testing has shown). Optimizing to 5-8s would make it much better.

**Use case:** Anyone testing the agent on their own use case. Colleagues evaluating the architecture. Pre-meeting demo prep. Users who don't have a live call to plug into but want to walk through discovery on a use case.

**Feasibility today:** ✅ Shipped. This is what we already have.

**Strategic value:** Critical for VALIDATION (proves the architecture before we invest in Modes 1 or 2a) and INTERNAL TESTING (lets colleagues try discovery without needing a real customer call).

---

## "1 packaging, 2.5 modes" — why this is structurally true

Andrew's framing is right because of how the architecture decomposes:

```
┌─────────────────────────────────────────────────────────────┐
│ skill bundle (durable IP)                                    │
│   - prompts                                                  │
│   - schemas                                                  │
│   - orchestration.yaml                                       │
│   - tools                                                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
                  ┌────────▼────────┐
                  │  runtime core   │  ← interprets orchestration.yaml
                  └────────┬────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐        ┌────▼────┐        ┌────▼────┐
   │ Mode 1  │        │ Mode 2a │        │ Mode 2b │
   │ I/O:    │        │ I/O:    │        │ I/O:    │
   │ transcript      │ STT +   │        │ chat    │
   │ loader → spec   │ sidebar │        │ in/out  │
   └─────────┘        └─────────┘        └─────────┘
```

The pipeline is **the same** across all three modes. What differs is just how customer turns ENTER the pipeline (transcript line, STT-segmented speech, typed text) and how the pipeline's output EXITS (exported spec, sidebar UI update, chat reply).

That means once we have the skill bundle + runtime core, **building a new mode is just writing a new I/O adapter.** Days of work, not months.

---

## Recommended sequencing

Given the strategic value + feasibility crossings:

**Phase A (now-ish):** Continue refining 2b. Get to A-grade on real customer-shaped use cases. Run on 2-3 different domains beyond the SoCo/sales-analyst pairs we've tested.

**Phase B (post-CES meeting):** Build Mode 1. Take 3-5 historical Atlan call recordings → transcripts → process. Produces immediate value (structured specs from real calls) with zero customer-facing risk. Validates that the pipeline works on messy real-world conversation, not just synthetic scripts.

**Phase C (after Mode 1 is real):** Build Mode 2a. By then we have:
- A validated agent on real-call data
- A working pipeline that handles messy customer language
- Empirical experience with what the sidebar should show

Without Phase B's validation, Phase C is high-risk. WITH Phase B, Phase C becomes a (relatively) safe extension because the pipeline has already been tested on real-customer transcripts.

**Phase D (much later):** Real-time autonomous voice interviewer. The agent speaks. Currently not feasible with this architecture without serious simplification. Probably the wrong target anyway — Mode 2a (sidebar augmenting an FDE) is more valuable and more achievable.

---

## Bottom line

- v0.8 latency is the constraint, not cost
- 2-3x speedup is achievable via well-known optimizations without architectural change
- Three deployment modes share one skill bundle + one runtime core, differ only in I/O adapter
- Mode 1 (post-mortem) is the highest-leverage next product surface
- Mode 2a (co-pilot) is the headline product but should be earned by Mode 1's validation
- Mode 2b (current chat agent) is the validation surface — keep refining for testing
- Mode 3 / "agent speaks in real-time" — probably the wrong target

---

## What to do with this doc

This is a back-pocket reference for v1.0 product conversations 3-4 weeks from now. The specific numbers will have drifted by then. The framing — "1 packaging, 2.5 modes; latency is the constraint not cost; cheap-cascade + caching + skip-sharpener get a 2-3x speedup" — is the durable part to remember.
