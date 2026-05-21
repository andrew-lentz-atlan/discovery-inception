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
| **Patterns curator** | Maintains the knowledge base via ingest / promote / query / lint. `ingest` step 1 shipping; **`promote` shipping** (cross-session knowledge promotion — reads per-session feedback, classifies generic vs specific, clusters recurring lessons, promotes ≥3-session clusters to `.candidate.md` drafts for human review). |
| **Intra-session feedback** | Inception accepts `--prior-feedback` so builder feedback on a starter becomes constraints for the next iteration. |
| **Discovery technical thread** | Discovery now probes a parallel thread on tech stack / data sources / semantic layer / runtime target / governance / data freshness / identity model alongside the conceptual checklist. `spec.md` renders the two threads in separate sections; the inception pipeline consumes the technical half. |
| **Atlan context integration** | Read-side: discovery primes the mega-agent with the customer's established Atlan context (glossary terms, table schemas, lineage, ownership, governance tags, business domains) at session start. Cataloged definitions land authoritative in the prompt; the technical thread skips what's already known. Graceful degradation when Atlan is unavailable. CLI: `--atlan-tenant`, `--atlan-glossary`, `--atlan-tables`, `--atlan-domains`. |
| **Artifact-first ingest pipeline** | Multi-artifact intake + fact extraction in one command. Hand it N call transcripts / runbooks / docs; it runs intake + fact extraction in parallel per artifact, merges into one `RoleContext`, populates a `DiscoverySession` with captured facts, and writes a `gap_list.md` the FDE acts on. CLI: `agent.cli ingest --artifact A.txt --artifact B.md ...`. |
| **FDE chat-fill mode** | `submit-turn --no-probe` skips the mega-agent's follow-up question while still capturing the FDE's answer as a fact (~3x faster, ~70% cheaper). Designed for closing gaps from `gap_list.md` that the FDE already knows the answer to. |
| **Distribution surfaces** | Installable Claude skill (artifact-first flow, one curl), MCP server runtime, headless CLI. |

---

## Next

In rough priority order:

1. **Discovery iteration loop.** When the spec gate criteria aren't met (too many outstanding questions), discovery should iterate — follow-up sessions, chat-based gap-filling, transcript ingest — until the spec is good enough for inception. Mechanism designed; not yet built.
2. **Atlan write-back path.** Discovery already produces `context_repo_gaps`-shaped candidate terms when the customer references concepts not in their tenant. Next step is the CES-mediated handshake to push reviewed gaps back to Atlan as proposed glossary terms / descriptions / lineage edges. Deferred from the Atlan-integration read-side ship.
3. **Critics for inception's proposer sub-agents.** Advisory adversarial pairs for skill_proposer and architecture_proposer that pressure-test their drafts against the spec. Lower priority — current pipeline produces defensible outputs; critics are quality-amplification.
4. **v1.0 packaging.** Separate the durable IP (prompts + schemas + orchestration spec) from the runtime that interprets it. Skill bundle becomes portable across runtimes — anyone can re-implement on LangGraph, Pydantic AI, or Deep Agents from the same contract. Contract sketched in `skill/`; implementation pending.

---

## Beyond v1.0

- Live-call deployment surface (sidebar UI; FDE drives the conversation, agent annotates state in real time)
- Voice-input variant (Granola / Otter integration; transcript streamed to discovery in near-real-time)
- Post-mortem mode (run discovery against recorded call transcripts at scale)
- Plugin model for domain-specific knowledge packs (e.g., CPG analytics, financial services, healthcare) layered on top of the generic patterns library
