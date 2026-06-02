---
title: Framework or hand-roll? Default is framework
category: decision-guides
status: draft
last_updated: 2026-05-29
source_findings:
  - findings/06-cost-latency-and-deployment-modes.md
  - findings/08-cheap-cascade-gpt4o-mini-doesnt-pan-out.md
  - findings/09-iteration-receipts-from-atlan-se-copilot.md
source_external: []
applies_when:
  workloads: [any-multi-step-agent, any-conversational-agent, any-task-agent, any-co-pilot, any-autonomous-worker]
  constraints: [production-build, prototype-intended-to-ship, team-larger-than-one]
contradicts: []
related:
  - decision-guides/what-kind-of-agent-are-you-building
  - decision-guides/subagent-vs-skill-tradeoffs
  - harnesses/landscape-2026-may
  - harnesses/claude-agent-sdk-deep-dive
  - harnesses/langgraph-deep-dive
  - harnesses/openai-agents-sdk-deep-dive
  - harnesses/pydantic-ai-deep-dive
snapshot_date: 2026-05-29
---

# Framework or hand-roll? Default is framework

Every agent build hits this fork: **use an existing harness (LangGraph, Claude Agent SDK, OpenAI Agents SDK, Pydantic AI, Agentforce, Cortex, Genie, etc.) or write your own orchestrator?**

The default is framework. The legitimate hand-roll case exists but is narrow — it's almost always research, and *only* research where orchestration mechanics are themselves what's being studied. Production builds default to framework, full stop.

This entry exists because today's inception output is neutral on this fork — it presents harnesses as one of several runtime options without making the framework-vs-hand-roll choice explicit. Going to v1.0, that neutrality is wrong: the engineering cost asymmetry is large, well-understood, and worth making the default explicit.

## The engineering costs that justify the default

When you hand-roll an orchestrator, you pay six recurring costs that frameworks amortize:

| Cost | What you pay |
|---|---|
| **Maintenance burden** | Every Python version bump, every upstream LLM SDK API change, every retry-logic edge case — you patch. Framework communities + vendors patch their own infrastructure; you patch yours. The bills come due at every dependency upgrade. |
| **Cognitive onboarding cost** | A new engineer who knows LangGraph or Claude Agent SDK from a prior project ships changes within days. A new engineer joining a bespoke orchestrator reads code for weeks before they can change anything safely. The first hand-rolled agent looks like a project; the second looks like a maintenance commitment. |
| **Knowledge transfer across builds** | Lessons learned on one framework-based agent transfer to the next: debugging techniques, observability conventions, deployment patterns. Each hand-roll is bespoke — lessons don't compound across builds. The team's velocity on agent #5 should be 5× the velocity on agent #1; with hand-rolls it isn't. |
| **Operational maturity** | Frameworks have years of work behind logging, observability, retry handling, deployment patterns, error semantics. Hand-rolls reinvent these — often poorly. The hidden cost is invisible until production: the on-call rotation finds the gaps the framework would have closed. |
| **Decision speed at 2 AM** | Production incidents on framework code mean docs, GitHub issues, Stack Overflow, community Slack, vendor support. Production incidents on hand-rolled code mean you and your `git blame`. Mean time to recovery is materially different. |
| **Reviewer legibility** | A peer reviewing a design that reads "LangGraph + Postgres checkpointer + supervisor pattern" understands the operational shape immediately. Reviewing a hand-rolled orchestrator design requires reading the orchestrator first — every review is a code review of the framework layer, every time. |

These compound. Year 1 of a hand-rolled agent might look like "we ship faster." Year 2 looks like "we're now spending half our agent-team capacity maintaining the orchestrator we wrote in year 1."

## When to hand-roll (the narrow case)

**Only when orchestration mechanics are part of what you're measuring.** If you're ablating sub-agent model choice, mega-agent context budget, synthesizer timing, sharpener rewrite rates, or any other orchestration-layer variable — framework opinions about orchestration would confound the experiment. Hand-rolling is required for these studies because the alternative is no experiment.

**Concrete reference case:** discovery-inception's research phase (findings/06 cost-latency tradeoffs, findings/08 cheap-cascade behavior, findings/09 iteration receipts) hand-rolled a 5-sub-agent orchestrator. We needed to swap sub-agent models independently, measure per-sub-agent token spend, and validate that mega-agent compensation would actually fire when extractor outputs got thinner. Stock frameworks don't let you ablate that finely without forking them. We hand-rolled because the alternative was no experiment.

The signal: if you can't articulate **which orchestration-layer variable you're holding constant and which you're varying**, you're not in the research case — you're hand-rolling for non-research reasons, and the costs above apply.

## When NOT to hand-roll (everything else)

**Production builds.** Customer-facing agents, SLA-bound services, team-maintained codebases. The engineering costs accrue over the lifetime of the system; the framework cost is amortized across the team's career. Always pick a framework.

**Prototypes intended to ship.** The "we'll rewrite it later" plan rarely happens. The prototype becomes the production system more often than anyone admits. If there's a real possibility this code will be in front of users in 12 months, treat it as production today. Pick a framework.

**Pre-production POCs for stakeholders.** Frameworks are not a barrier to demo velocity in 2026 — they reduce it. A LangGraph or Claude Agent SDK starter scaffolds in 30 minutes; the same agent hand-rolled in plain Python with custom state management is a week. Hand-rolling for "speed" is a 2024 reflex that hasn't been true for a year.

**Anything operated by a team larger than one.** Bus factor. The hand-rolled orchestrator has exactly one expert: whoever wrote it. The framework has a community. Even if your team is just two engineers, that's enough to make the cognitive onboarding cost compound.

## "But the framework can't do what we need" — anti-rationale

This rationale is almost always wrong. Three failure modes hide behind it:

1. **The design is wrong, not the framework.** If LangGraph + checkpointers + interrupts + custom nodes + tool use can't model the workflow, the workflow probably isn't decomposed correctly. Fix the design.

2. **The wrong framework was evaluated.** Most "framework can't do X" claims come from evaluating one framework. The 6 major harnesses (Claude Agent SDK, LangGraph, OpenAI Agents SDK, Pydantic AI, plus Agentforce/Cortex/Genie for resident workloads) cover the design space well enough that ONE of them fits virtually every production agent shape — see `harnesses/landscape-2026-may.md`.

3. **The custom-build instinct is engineering ego, not constraint.** It feels better to build than to learn someone else's primitives. The 2 AM incident response cost is the cure.

Verify before accepting "framework can't do X":
- Have you read the framework's docs for the specific feature you think is missing?
- Have you searched GitHub issues for similar use cases?
- Have you evaluated more than one framework?
- Have you asked someone who's shipped a similar agent on the framework?

If the answer to any of these is no, "framework can't do X" is not yet a justified rationale.

## Class-by-class framework defaults

Cross-reference with `decision-guides/what-kind-of-agent-are-you-building.md`:

| Class | Default framework choice | Notes |
|---|---|---|
| **Chatbot** | Pydantic AI or direct LLM API | No real orchestration needed; structured-output schemas suffice |
| **Conversational agent** | Claude Agent SDK or LangGraph | Claude Agent SDK if Anthropic stack is fine; LangGraph if richer state/branching is needed |
| **Task agent** | Pydantic AI for type-safe pipelines; LangGraph for branching workflows | Hand-roll *only* if running structured ablation experiments on the pipeline shape |
| **Co-pilot** | Claude Agent SDK | Canonical fit per `harnesses/claude-agent-sdk-deep-dive.md` |
| **Autonomous worker (claw)** | LangGraph + durable execution (Postgres checkpointer) | Memory + heartbeat + recovery patterns are first-class in LangGraph |

For workloads that live inside a data plane:
- Salesforce-resident → Agentforce
- Snowflake-resident with narrow analyst Q&A → Cortex (with the limitations noted in `harnesses/cortex-deep-dive.md`)
- Databricks-resident with BI Q&A → Genie (with the limitations in `harnesses/genie-deep-dive.md`)

These defaults are starting points, not mandates. The runtime_proposer should refine per workload — but the refinement is *which* framework, never *whether* to use one.

## Hard rule for inception's runtime_proposer

When inception's runtime_proposer evaluates harnesses for a workload, it should:

1. **Default to framework selection.** Hand-rolling is not on the candidate list unless the workload is explicitly a research/ablation experiment where orchestration mechanics are the variable being studied.

2. **If "hand-roll" appears in any rejection rationale**, the proposer must articulate which orchestration-layer variable is being held constant and which is being varied. If it can't, hand-rolling is unjustified for this workload.

3. **If a candidate framework "can't do" something the workload needs**, the proposer must enumerate which OTHER frameworks were evaluated and what specifically they couldn't do either. A single-framework rejection is not yet a justified "framework can't" claim.

4. **The runtime_proposal output must name the framework explicitly** in `selected_runtime`. Never `selected_runtime: "hand-rolled"` or `selected_runtime: "custom"` unless the workload classification confirms research/ablation status.

## Provenance

This entry was authored after the discovery-inception research phase (findings/06-09) closed and the system moved toward v1.0 product framing. The hand-rolled orchestrator that powered the research was justified by the research itself — once orchestration mechanics were settled, the justification expired for new work. This entry captures the policy that should apply to every new agent build downstream of inception, and to discovery-inception's own future infrastructure once a v0.10 migration is scheduled.

The recursive proof point worth noting: **the only legitimate justification we have for our own hand-rolled orchestrator is the research case described above.** When inception ships v1.0 to SE/CES teams, the recommendations it produces will land on frameworks — and discovery-inception's own infrastructure should be on a framework too, on whatever schedule the v0.10 migration plan settles.
