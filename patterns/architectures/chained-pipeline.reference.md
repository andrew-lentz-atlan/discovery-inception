# chained-pipeline — reference

Supplementary detail for `chained-pipeline.md`. Read when reviewing the deprecation decision, auditing the empirical case, or considering where the pattern still applies in the codebase.

---

## Why this is `deprecated` rather than absent

The pattern itself isn't wrong. The pattern is the right answer for batch extraction (intake's 6-step pipeline runs cleanly to this day). The deprecation is specifically about its use as an **agent-level architecture for conversational workloads** — that's where the empirical case (findings/01) says it loses.

We keep the entry readable so anyone tracing a past decision can see what was considered at the time. Discovery v0.5 was built on this pattern; v0.6+ moved off it. The history is preserved.

## Full empirical case

`findings/01-architecture-comparison.md` (2026-05-05):

The central question: does decomposition into small task-scoped sub-agents produce a better discovery agent than a single strong-prompted LLM call?

Setup: 5-turn deterministic script, same model, same priors, three architectures.

| Variant | Conversation quality wins (subjective, 5 trials) | Wall time | Tokens (mega-call only) | Structured spec produced |
|---|---|---|---|---|
| A — Chained (v0.5) | 0/5 | 75s | n/a (chain) | ✓ |
| B — Mega-only | 2/5 | 16s | 14K | ✗ |
| C — Hybrid | 3/5 | 85s | 38K | ✓ |

Pre-test hypothesis: decomposition wins because each sub-agent specializes and can be routed to the cheapest sufficient model.

Actual result: **decomposition is not load-bearing for conversation quality. It IS load-bearing for structured deliverables.** The hybrid (extractors + mega-agent + tools) recovers both at a token-cost premium.

The refined hypothesis post-test: the right level of decomposition depends on what you're trying to produce — prose vs structure. n=1; treat as a starting hypothesis.

`findings/02-v07-lazy-synthesis-and-free-form-output.md` extended this: even within a chain, running every sub-agent every turn (eager synthesis) wastes compute. Lazy invocation (model decides when to call) won. But once you give the model that decision, you've already left pure-chain — you're in single-agent-with-tools territory.

## Where this pattern is still alive in our codebase

- **`intake/run.py`** — 6-step batch pipeline producing a `RoleContext` from an artifact. Sequential: classify → extract → normalize → sniff-unwritten-rules → report-gaps → score-confidence. This is the canonical "chained pipeline is the right answer" case. Don't replace it with a single-agent loop.
- **The extractor layer in v0.8's hybrid discovery agent** — `triage` → `distill` runs every turn as a deterministic chain. The mega-agent on top is single-agent ReAct. This is the *hybrid* pattern — the chain provides structured state; the mega-agent provides the conversation.

Both are sub-skill or extractor-layer uses. Neither is an agent-level architecture. That's the precise scope of the deprecation: pure chain at the agent level, for conversation.

## Implementation gotchas (full)

- **Smart routing is the slippery slope.** Once one sub-agent decides whether to run another, you're not in pure-chain anymore. Decide explicitly: commit to chain (every step every time) or switch to single-agent-with-tools.
- **Sub-agent failures cascade.** When sub-agent N hallucinates, sub-agent N+1 receives bad input. The chain doesn't self-correct because there's no judge between steps. Build deterministic validators between sub-agents if reliability matters.
- **Trace volume explodes.** N customer turns × M sub-agents per turn = N×M traces. For a 50-turn discovery session, that's hundreds of structured events. Plan trace retention accordingly.
- **Cost stacks.** Each sub-agent is a separate LLM call. Even on cheap models, the multiplier adds up — discovery's v0.5 was ~$0.50 per session, dominated by the per-turn chain count.

## Variants & related patterns

- `single-agent-react.md` — the contradicting pattern. For conversational workloads, this is what to use instead.
- `skill-design/inner-pipeline.md` (not yet authored) — chained pipelines embedded *inside* a single skill (Bala's pattern). Different from chained at the agent level: the chain lives at skill granularity. Alive and well.
- The hybrid (extractors + mega-agent + tools) is the actual winner from findings/01. Not yet promoted to its own entry; referenced widely. Author candidate.

## Maintenance notes

- Authored during the gold-standard seed pass 2026-05-20.
- Status: `deprecated` at the agent level; remains valid at sub-skill level.
- Next review: if a future finding shows the pattern winning on a workload shape we haven't tested, status may upgrade back to `validated` with the narrower applicability.
- Companion entry `hybrid-extractors-plus-mega-agent.md` is queued — currently the hybrid pattern is only described inline here and in `single-agent-react.md`.
