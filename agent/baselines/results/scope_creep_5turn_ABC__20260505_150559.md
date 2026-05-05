# Comparison: A (chained v0.5) vs B (mega-agent) vs C (v0.6 hybrid)

**Script:** `scope_creep_5turn` — 5-turn deterministic customer script. Tests opening, relevance pushback, dense structured content, concrete success criteria, and a long case study with ~10 embedded facts. Each customer turn is agent-agnostic so both systems see identical input.
**Use case seed:** we want a SoCo agent for new-customer onboarding at TechCo
**Role priors:** `solutions-consultant`
**Run at:** 2026-05-05T15:05:59.561372+00:00

**System definitions:**
- **A** — chained v0.5: 5 sub-agents per turn (triage → distill → synthesizer → why-prober → probe-generator); orchestrator drives the conversation.
- **B** — mega-agent baseline: 1 LLM call per turn with a strong system prompt that bakes in everything the chain encodes structurally.
- **C** — v0.6 hybrid: extractors (triage → distill → synthesizer) run as a structured-output skill; mega-agent runs the conversation as a single call WITH spec-introspection tools (get_current_spec_state, get_working_theory, get_checklist_progress).

## Summary metrics

| Metric | A (chained) | B (mega) | C (hybrid) |
|---|---|---|---|
| Total wall time | 75130ms | 16496ms | 84555ms |
| Avg per turn | 15026ms | 3299ms | 16911ms |
| Customer-vocab terms (sum) | 13 | 10 | 9 |
| Generic SaaS-org terms | 0 | 0 | 0 |
| Detected rationale | 1/5 | 1/5 | 1/5 |
| Tokens (input/output, mega-call only for B and C) | n/a | 13960in/615out | 37920in/814out |

**C — total spec-tool invocations across the script:** 4
  - `get_checklist_progress`: 2
  - `get_current_spec_state`: 1
  - `get_working_theory`: 1

### A (chained) — final structured state

- Phase: `lay_of_the_land`
- Topics covered: 4, total facts recorded: 4
- Working-theory confidence: `medium`
- Working-theory framing:
  > A SoCo agent that keeps the current-phase onboarding (connectors, metadata bootstrap, success plan) unblocked and on track by surfacing state and dependencies across IE, CSA, and CSM — while explicitly holding the boundary on Phase 2 scope (AI governance, contracts, MCP) and routing those requests to the CSM for separate solutioning.
- Candidate framings: 3
- Gaps flagged: 0

### C (hybrid) — final structured state

- Phase: `lay_of_the_land`
- Topics covered: 4, total facts recorded: 4
- Working-theory confidence: `medium`
- Working-theory framing:
  > A SoCo agent that orchestrates the three core onboarding deliverables (priority connectors deployed, metadata bootstrapped for the initial use case, success plan complete) by decomposing each into tasks, proposing role routing, and keeping the SoCo as the decision-maker and validator—while staying disciplined about scope boundaries and escalating Phase 2 requests (like AI governance / data contracts / MCP) to the CSM for future planning.
- Candidate framings: 3
- Gaps flagged: 0

**Note:** B (mega-agent) has NO structured spec — everything it knows lives in conversational history.

## Per-turn side-by-side

### Turn 1
_concrete opening — does the agent record this cleanly OR immediately rabbit-hole on why?_

**Customer:**

> We want to reduce time-to-first-value for new enterprise customers from 90 days to 30.

**A (chained v0.5)** — `18024ms`, vocab `0c/0g`, rationale `False`, triage `concrete`

> When you say you want to compress onboarding from 90 days to 30 days, what does the customer have live and working at day 30 that they don't have today — is it their first data connector pulling live metadata, their first governance policy in place, their first team of users actively searching and using the catalog, or something else?

**B (mega-agent)** — `3531ms`, vocab `0c/0g`, rationale `False`, tokens `2343in/36out`

> What does "first value" mean concretely — is it when they can search for a data asset, when their first connector is live, or something else?

**C (v0.6 hybrid)** — `15855ms` total, vocab `0c/0g`, rationale `False`, triage `concrete`, tools used: get_checklist_progress, get_current_spec_state, mega tokens `7011in/114out`

> What are the 2–3 biggest time sinks in the first 30 days today that, if we could eliminate or speed them up, would move the needle most on getting from 90 days down to 30?

---

### Turn 2
_relevance challenge — does the agent answer with a customer-facing rationale, or silently pivot to a different question?_

**Customer:**

> Before we go further — explain to me how the questions you're asking are going to actually help me build this agent. It feels like youre just asking why why why with no reasoning. how is this getting me closer?

**A (chained v0.5)** — `2239ms`, vocab `1c/0g`, rationale `True`, triage `relevance_challenge`

> Fair pushback. Here's why I asked: For a SoCo agent to know what to prioritize and automate in those first 30 days of onboarding at TechCo, we need to know what 'done' looks like — whether that's a live connector, enriched metadata, or active users — so the agent focuses on the right work. If that doesn't hold up for what you're trying to build, tell me and I'll drop the line and pick a different angle.

**B (mega-agent)** — `4055ms`, vocab `0c/0g`, rationale `False`, tokens `2427in/255out`

> Fair challenge. Here's the rationale:
> 
> You told me you want to compress onboarding from 90 to 30 days. That's a timeline goal, but I don't yet know what *work* happens in those 30 days or who does it. 
> 
> If I don't know what "first value" concretely is — whether it's a working connector, a searchable glossary, or users actually *using* the platform — I can't tell the agent what to prioritize, what to automate, or when to escalate. The agent will make wrong calls about pacing and handoffs.
> 
> Same with the next 5 questions I'd ask: they're all trying to answer one thing — **what specific sequence of decisions and actions does a Solutions Consultant need to make during onboarding to hit 30 days instead of 90?** Until I have that sequence, I'm building a generic chatbot, not an agent that actually compresses your timeline.
> 
> So the questions aren't "why why why" — they're reverse-engineering the concrete workflow the agent needs to execute. Does that make sense, or do you want me to take a different angle?

**C (v0.6 hybrid)** — `8469ms` total, vocab `3c/0g`, rationale `True`, triage `relevance_challenge`, tools used: none, mega tokens `4023in/395out`

> Fair challenge. Let me be direct.
> 
> Right now I know you want to compress onboarding from 90 to 30 days, but I don't know *what the agent actually does*. There are at least four completely different agents hiding in that goal:
> 
> 1. **An agent that runs the assessment and drafts the Success Plan itself** — the SoCo reviews it. This is a *builder* agent.
> 2. **An agent that keeps the SoCo on track through the assessment workflow** — reminding them what's next, flagging blockers. This is a *coordinator* agent.
> 3. **An agent that talks to the new customer directly** — collects their current state, answers setup questions, reduces SoCo load. This is a *customer-facing* agent.
> 4. **An agent that's just a copilot** — answers questions on demand but doesn't drive anything.
> 
> These have completely different architectures, different data inputs, different success metrics, and different failure modes. A builder can't be built the same way as a coordinator.
> 
> So when I ask "what are the biggest time sinks," I'm trying to figure out *which of these four* solves your actual problem. If the answer is "SoCo spends 40 hours writing the assessment," then we're building #1. If it's "SoCo keeps context-switching between customer calls and Atlan setup," then we're building #2. If it's "customers don't know what to prepare," then we're building #3.
> 
> Without that, I'd just be guessing at the spec, and you'd end up with an agent that doesn't do what you need.
> 
> Does that make sense? And more importantly — which of those four (or something else entirely) is closest to what you're picturing?

---

### Turn 3
_dense structured content — does the agent mirror CSM/CSA/IE/SoCo vocabulary, form a clear working theory, recognize 'coordination and design brain' as the core framing?_

**Customer:**

> The SoCo agent operates in a multi-agent system:
> 
> CSM: Owns success planning and relationship. Feeds SoCo with outcomes and constraints; receives back a concrete implementation plan and progress.
> CSA: Owns net-new or advanced platform solutions (new apps, primitives, patterns). SoCo must exhaust reuse and existing patterns first, then escalate only genuine new-build work to CSA.
> IE: Owns connectors and data-source integrations. SoCo specifies what connections are needed for a project; IE implements.
> Support: Handles break/fix and tickets; SoCo should not become a shadow support queue.
> 
> SoCo is the coordination and design brain of delivery: given a target outcome, they decide what should be handled by the customer, CSM, CSA, IE, or Support, and keep ownership of the solution as a cohesive project.

**A (chained v0.5)** — `16775ms`, vocab `6c/0g`, rationale `False`, triage `concrete_off_topic`

> Here's what I'm hearing — let me play it back so you can tell me if I'm reading the shape right:
> 
> **Working theory:** An agent that acts as the SoCo's coordination and design brain — taking a customer outcome, deciding which work goes to CSM/CSA/IE/Support, and keeping ownership of the solution as a cohesive project.
> 
> Other shapes this could be (less likely from what you've said):
> - decision engine — the agent receives a customer outcome and recommends the right routing (CSM owns this, IE owns that, escalate to CSA if net-new); SoCo validates and executes the routing decision
> - workflow orchestrator — the agent manages the multi-agent handoffs themselves (tells IE what connectors to build, tells CSA when to engage, tells Support when to take a ticket); SoCo monitors and intervenes
> - SoCo's internal copilot — the agent assists the SoCo in real-time during customer calls or planning sessions (suggests routing options, flags when reuse is possible, surfaces best practices for similar outcomes); SoCo makes all routing calls
> 
> Does that match what you're trying to build, or am I missing something? If part of that is wrong, the wrong part is the most useful thing you can tell me.

**B (mega-agent)** — `1975ms`, vocab `4c/0g`, rationale `False`, tokens `2880in/75out`

> Got it — SoCo is the orchestrator, not the executor. That changes everything.
> 
> So when you say "reduce time-to-first-value from 90 to 30 days," is that 30 days from when the CSM hands SoCo a Success Plan outcome, or 30 days from contract signature?

**C (v0.6 hybrid)** — `21693ms` total, vocab `1c/0g`, rationale `False`, triage `concrete_off_topic`, tools used: get_working_theory, mega tokens `9865in/130out`

> This is much sharper. So the SoCo is the *decision-maker* — they own which work goes where and when. The agent's job is to make that decision-making faster and more reliable.
> 
> When a new customer outcome lands with the SoCo, what does the SoCo actually have to *decide* in those first 30 days that currently takes the most time or creates the most friction?

---

### Turn 4
_concrete success criteria — does the agent recognize this as the actual scoreboard and use the customer's exact deliverable language ('priority connectors', 'success plan')?_

**Customer:**

> Success looks like: priority connectors are in (the ones aligned in presales), metadata is bootstrapped for the initial use case, and the success plan is complete. Those are the three deliverables.

**A (chained v0.5)** — `17748ms`, vocab `2c/0g`, rationale `False`, triage `concrete_off_topic`

> When a priority connector deployment gets delayed or metadata bootstrap stalls, does the SoCo reach out to the Implementation Engineer or CSA to unblock it, or does the agent need to actively flag it and suggest next steps?

**B (mega-agent)** — `2683ms`, vocab `1c/0g`, rationale `False`, tokens `3000in/39out`

> When you say "metadata is bootstrapped," what does that concretely mean — is it classifications applied, a glossary seeded, lineage mapped, or something else?

**C (v0.6 hybrid)** — `18164ms` total, vocab `3c/0g`, rationale `False`, triage `concrete_off_topic`, tools used: get_checklist_progress, mega tokens `11044in/87out`

> Of those three deliverables — priority connectors in, metadata bootstrapped, success plan complete — which one today is the biggest bottleneck that's eating up the 60 days you're trying to cut?

---

### Turn 5
_long narrative with ~10 embedded facts — does the agent capture multiple structural insights (anti_goal: don't expand SOW; decision_point: 5-question checklist; escalation_rule: SoCo+CSM huddle then CSM-led discovery; persona: governance champion) or does it grab one and miss the rest?_

**Customer:**

> Mid-onboarding for a large FS customer, during a working session the governance champion said: 'We just saw your AI governance / data contracts / MCP capabilities in the docs. Can you help us design and implement that now as part of this rollout?'
> 
> Context: current SoCo project was scoped around core onboarding (connectors, catalog, personas/access, a few priority domains). AI governance / contracts / MCP had only been discussed as 'future / Phase 2'.
> 
> Instead of diving in, the SoCo treated it as scope creep: acknowledged the idea, drew a boundary, explicitly reframed as Phase 2, looped in the CSM. They walked through a checklist offline: is it required to hit the current value metric? no. is it in the SOW? no. is there a self-serve path? yes (Atlan U/docs). does it need solutioning? yes. is there budget and focus to do it now without jeopardizing the rollout? no.
> 
> Conclusion: do not expand the in-flight project. CSM owns a new 'AI governance & contracts - Phase 2' initiative. The SoCo stays focused on the currently scoped delivery.

**A (chained v0.5)** — `20344ms`, vocab `4c/0g`, rationale `False`, triage `concrete_off_topic`

> When the IE, CSA, and CSM are working on the three current deliverables—connectors, metadata bootstrap, and success plan—what's the single biggest thing that typically blocks progress or creates rework during an onboarding like this?

**B (mega-agent)** — `4252ms`, vocab `5c/0g`, rationale `True`, tokens `3310in/210out`

> I'm going to pause and play back what I'm hearing, because this is a critical moment.
> 
> You just gave me a *decision point* — not a question. You showed me the exact judgment SoCo needs to make when a customer asks for something mid-project: scope creep or legitimate pivot?
> 
> And you walked me through the *decision logic*: required for current value metric? in SOW? self-serve path exist? need solutioning? budget/focus available?
> 
> Here's my working theory: **SoCo's job is to keep the 30-day onboarding on track by making fast, principled scope decisions — knowing when to say yes (escalate to CSA or CSM), when to say no (defer to Phase 2), and when to say "you can self-serve this."**
> 
> The agent needs to recognize those moments and apply that checklist.
> 
> Does that match what you're building, or am I overstating it?

**C (v0.6 hybrid)** — `20374ms` total, vocab `2c/0g`, rationale `False`, triage `concrete_off_topic`, tools used: none, mega tokens `5977in/88out`

> Got it — that's a concrete example of the SoCo making a routing and prioritization decision under pressure in real time. The agent's job is to help the SoCo make that call faster and with more confidence.
> 
> When that governance champion asked the question mid-session, what information or checklist would have helped the SoCo decide *immediately* instead of having to loop offline with the CSM?

---
