# Roadmap

The forward direction for discovery-inception. What's shipped, what's coming next, in concise form. For implementation status of any individual component, check the component's own README.

---

## Shipped

| Capability | What it does |
|---|---|
| **Intake (priors generation)** | Takes a single customer artifact (JD, runbook, scoping transcript) and produces a structured `RoleContext` the discovery agent uses as priors. Six-step batch pipeline; opt-in `--use-case` orientation flag for meta-artifacts. |
| **Discovery (v0.8)** | Multi-turn conversational agent that interviews a customer to produce a structured spec. Five sub-agents per turn (triage / distill / mega-agent with tools / probe-sharpener / lazy synthesizer). Deterministic close-out synthesis at session end. Validated through five empirical iterations (see `findings/`). |
| **Patterns knowledge base** | Curated agentic-design knowledge — architectures, anti-patterns, skill-design patterns, harness landscape, decision guides. Read at runtime by the inception pipeline. |
| **Inception** | Turns a spec into a complete starter agent design. Five sub-agents end-to-end: workload classification → skill proposal → architecture selection → runtime selection → scaffold writer (which itself runs five parallel/sequential sub-steps to produce SKILL.md per skill, orchestrator.py, design_rationale.md, eval seed, judge harness). |
| **Patterns curator** | Maintains the knowledge base via ingest / query / lint operations. Skeleton + step 1 (classify source) shipping. |
| **Intra-session feedback** | Inception accepts `--prior-feedback` so builder feedback on a starter becomes constraints for the next iteration. |
| **Distribution surfaces** | Installable Claude skill (one curl), MCP server runtime, headless CLI. |

---

## Next

In rough priority order:

1. **Discovery technical-thread extension.** Add a parallel concern thread to discovery that asks about data sources, tech stack, semantic layer, runtime targets — the technical context the inception pipeline needs to produce defensible starters. Today discovery covers conceptual concerns well; technical concerns are missing.
2. **Atlan context integration.** Read-side: query the customer's Atlan tenant at discovery session start to establish what's already cataloged (glossary, tables, lineage). Skip redundant questioning. Produce a "what's missing from your context layer" artifact at session close.
3. **Cross-session knowledge promotion.** Aggregate builder feedback across many agent builds. When a lesson recurs across ≥3 sessions, promote it to the patterns knowledge base. Closes the loop from "this build's learnings stayed in this builder's head" to "all future builds inherit accumulated wisdom."
4. **Discovery iteration loop.** When the spec gate criteria aren't met (too many outstanding questions), discovery should iterate — follow-up sessions, chat-based gap-filling, transcript ingest — until the spec is good enough for inception. Mechanism designed; not yet built.
5. **Critics for inception's proposer sub-agents.** Advisory adversarial pairs for skill_proposer and architecture_proposer that pressure-test their drafts against the spec. Lower priority — current pipeline produces defensible outputs; critics are quality-amplification.
6. **v1.0 packaging.** Separate the durable IP (prompts + schemas + orchestration spec) from the runtime that interprets it. Skill bundle becomes portable across runtimes — anyone can re-implement on LangGraph, Pydantic AI, or Deep Agents from the same contract. Contract sketched in `skill/`; implementation pending.

---

## Beyond v1.0

- Live-call deployment surface (sidebar UI; FDE drives the conversation, agent annotates state in real time)
- Voice-input variant (Granola / Otter integration; transcript streamed to discovery in near-real-time)
- Post-mortem mode (run discovery against recorded call transcripts at scale)
- Plugin model for domain-specific knowledge packs (e.g., CPG analytics, financial services, healthcare) layered on top of the generic patterns library
