---
title: Adversarial Decomposition
category: architectures
status: validated
last_updated: 2026-05-13
source_findings: [findings/05-v08-probe-sharpener-and-tensions.md]
source_external: []
applies_when:
  workloads: [conversational, structured-extraction, quality-critical]
  constraints: [tolerates-2-5s-latency-overhead]
contradicts: []
related: [single-agent-react]
---

# Adversarial Decomposition

A producer + critic pair where the critic has authority to **replace** the producer's output when it scores below threshold. Different from generic decomposition: the structure is specifically a draft + reviewer, with rewrite authority and a scoring rubric.

## Use when

- Conversational agents where probe quality > throughput
- Structured extraction with judgment dimensions (not just factual fields)
- You have a quality rubric the critic can score against
- 2–5s latency overhead per producer call is acceptable

## Don't use when

- Pure query-response with deterministic validation available (use a validator, not a critic)
- Sub-second latency targets (voice, real-time UI)
- Producer is small enough that iterating its prompt is cheaper than running a separate critic
- Rubric is subjective enough that the critic disagrees with itself across runs — tighten the rubric first

## Key gotchas

- **Critic must have rewrite authority**, not just annotation. Without substitution, the pattern becomes ceremony.
- **Same model family for producer + critic.** Cross-model adversarial pairs introduce stylistic disagreements unrelated to quality.
- **Watch for critic-template collapse.** Once the critic finds a rewrite template it likes, it tends to reuse it (e.g., always opening with "You said X, but you also said Y…"). Anti-template language in the critic's prompt is required.
- **Empirically tune the rewrite threshold.** Too low → noise. Too high → ceremony.

## Empirical anchor

`findings/05`: same 50-turn discovery script run on v0.7 (no critic) and v0.8 (with probe-sharpener critic). Sharpener fired on 49 of 50 turns; **rewrite rate 55%** (more than half of v0.7's probes scored below the ship-as-is threshold). Output: +16% facts captured, +1 candidate framing, +3 internal tensions surfaced. Cost: wall time +22%; output tokens **−45%** (sharpened probes get tighter customer replies).
