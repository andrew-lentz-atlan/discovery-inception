---
title: Adversarial Decomposition
category: architectures
status: validated
last_updated: 2026-05-13
source_findings: [findings/05-v08-probe-sharpener-and-tensions.md]
source_external: []
applies_when:
  workloads: [conversational, structured-extraction, quality-critical]
  constraints: [trust-the-output-over-speed, can-tolerate-2-5s-latency-overhead]
contradicts: []
related:
  - single-agent-react
  - skill-design/adversarial-review
  - skill-design/inner-pipeline
---

# Adversarial Decomposition

A second sub-agent whose job is to be skeptical of the first one's output. Distinct from "split a task across sub-agents" (which is just decomposition). The adversarial pair is specifically a **producer + critic** structure where the critic has authority to replace the producer's output when it scores below threshold.

The pattern is structurally simple. The producer (e.g., a mega-agent generating a conversational probe) emits its draft. A post-processor (the sharpener / critic) scores the draft against a rubric and either ships it as-is or rewrites it. The pair feels like two adversarial reviewers on a draft, except both are LLMs and the rewrite-vs-ship decision is mechanical, not deliberative.

---

## When to use

- **Conversational agents where probe quality matters more than throughput.** Discovery interviews, customer support escalation, executive briefings. Workloads where one weak question loses signal that can't be recovered later.
- **Structured-extraction tasks with judgment dimensions.** Anything where the output has both factual content and rhetorical/structural quality (a research summary, a recommendation, a synthesis).
- **When you have explicit quality dimensions you can score against.** The sharpener pattern relies on a rubric (e.g., novelty / extension / provenance-pressure / tension-surfacing, scored 1-5 each). Without a rubric, the critic has no grounding and degrades to a stylistic preference engine.
- **When you can tolerate 2-5s of latency overhead per turn.** The critic is a real LLM call. In v0.8 of discovery, sharpener added ~3-5s per question-shaped turn.

---

## When NOT to use

- **Pure query-response workloads with a known-good answer shape.** If the producer's output has objective correctness criteria (SQL query, classification label), use a validator (deterministic check) instead of a critic (LLM-as-judge in the production loop).
- **Latency-critical real-time conversation.** Voice interfaces, sub-second response targets. The critic round-trip kills the experience.
- **Single-call shapes where the producer is small enough that rerunning with a sharper prompt costs less than running a separate critic.** If your producer is 200 tokens of output, just iterate on the producer prompt.
- **When the rubric would be subjective enough that the critic disagrees with itself across runs.** If two runs of the critic on the same draft produce different scores, the rubric isn't tight enough yet — fix the rubric before deploying the pattern.

---

## Empirical receipts

`findings/05-v08-probe-sharpener-and-tensions.md`:

- Same 50-turn TechCo Sales Pipeline Analyst script run on v0.7 (no adversarial pair) and v0.8 (with probe-sharpener post-processor).
- Sharpener fired on 49 of 50 turns. **Rewrite rate: 55% (27 of 49).**
- Sharpener score range: 6–19 of 20. Average: 11.6.
- Conclusion: more than half of v0.7's probes were below the sharpener's "ships as-is" threshold. The previous version's questioning was measurably weaker.
- Output quality improvements: facts captured +16% (38 → 44); candidate framings +1; internal tensions surfaced 0 → 3.
- Cost: wall time +22% (549s → 671s). Output token cost actually *dropped* 45% because the sharpened probes were tighter, and the customer's replies were correspondingly tighter.

---

## Implementation gotchas

- **The critic must have authority to replace, not just annotate.** If the critic's score doesn't trigger automatic substitution, the producer's output ships every time and the pattern becomes ceremony.
- **Score-rewrite threshold needs empirical tuning.** v0.8 picked `score ≤ 10 → rewrite`. Too low → noise. Too high → ceremony. The right cut depends on your rubric's resolution.
- **Critic-pattern collapse.** Once a critic finds a template it likes, it tends to rewrite into that template. In v0.8 we observed `"You said X, but you also said Y…"` opening on 26 of 26 sharpener rewrites in one replay run. The critic's prompt needs explicit anti-template language.
- **Critic latency compounds in multi-turn settings.** 3-5s × N turns adds up. For 50-turn sessions, that's a real cost.
- **Critics for the critic.** Don't stack — adversarial pair, not adversarial tree. Two layers is sound; three is over-engineered.
- **Same model family for producer and critic.** Cross-model adversarial pairs (e.g., GPT-4o producer, Claude critic) introduce stylistic disagreements that have nothing to do with quality. Use the same model unless you have strong empirical reason to mix.

---

## Variants & related patterns

- **`skill-design/adversarial-review.md`** — applies the same pattern at the skill level (a skill that produces structured output, with an inline reviewer). Bala uses this implicitly in his root_cause_skill (LLM #1 generates SQL, LLM #2 interprets results — the second is a quality check on the first).
- **`single-agent-react.md`** — the orthogonal architecture choice (no critic). For workloads where the producer-only pattern is sufficient, single-agent is simpler.
- **`skill-design/inner-pipeline.md`** — adversarial pairs are one shape an inner pipeline takes. Other shapes (chain-of-validation, multi-pass refinement) are related but distinct.
- **The Anthropic Claude SDK's `Task` tool** + the Deep Agents `task` pattern both make adversarial decomposition cheap to express — fire a sub-agent with a different prompt that reviews the parent's draft.

---

## Cost / latency profile

For Claude Haiku 4.5 in production (discovery agent's v0.8 deployment):

| Component | Latency contribution | Token contribution |
|---|---|---|
| Producer (mega-agent draft) | 5-8s | varies |
| Critic (sharpener) | 3-5s | ~500 tokens in / ~200 tokens out per turn |
| Rewrite when triggered | +1-2s (replaces draft) | minor |

Roughly: **+30-50% latency, neutral-to-positive on cost** (sharpened probes get tighter customer replies, which cuts downstream tokens).

---

## Maintenance notes

- This entry was promoted from `findings/05` during the gold-standard seed pass. Andrew + Claude authored 2026-05-20.
- Next review: when `findings/NN` documents another adversarial-pair workload or contradicts the threshold guidance.
- The critic-pattern-collapse failure mode observed in the FS Account Director replay (see `agent/baselines/scripts/fs_account_director_replay.json` + working-tree analysis 2026-05-19) should eventually get its own anti-pattern entry: `anti-patterns/critic-template-collapse.md`.
