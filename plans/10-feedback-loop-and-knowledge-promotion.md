# 10 — Feedback Loops and Knowledge Promotion (both stages)

**Status:** design — partial (inception's per-session loop is roughly built; the other two loops are designed but not implemented).
**Closes the loop on:** `plans/05-technical-thread-discovery.md`, `plans/06-atlan-context-integration.md`, `plans/07-patterns-knowledge-base.md`, `plans/08-inception-agent.md`.
**Implements:** the compounding mechanism that makes "agent that helps build other agents" get *better over time*, not just faster.

---

## The three loops

The project has two stages — **discovery** and **inception** — each with its own per-session tight feedback loop, plus a shared cross-stage slow loop through the patterns library. Three loops total, operating at different scopes and cadences.

```
  ┌─────────────────────────────────────────────────────────────────────┐
  │                                                                     │
  │   Loop 1 — Discovery iteration (tight, scope: one spec)             │
  │                                                                     │
  │   intake → discovery → spec.md + outstanding_questions              │
  │              ↑                       │                              │
  │              │   if Qs unresolved:   │                              │
  │              │   - follow-up session │                              │
  │              │   - chat gap-filling  │                              │
  │              │   - new transcript ───┘                              │
  │              │   (1-3 iterations)                                   │
  │              │                                                      │
  │              └─ spec gate ─→ INCEPTION                              │
  │                                                                     │
  │   Goal: a spec good enough that inception can produce a defensible  │
  │   starter from it. Cadence: minutes (chat fill) to days (follow-    │
  │   up sessions). Stays session-scoped.                               │
  │                                                                     │
  └─────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────┐
  │                                                                     │
  │   Loop 2 — Inception iteration (tight, scope: one agent)            │
  │                                                                     │
  │   spec → inception → agent_starter → builder iterates → feedback    │
  │                          ↑                                  │       │
  │                          │  (1-3 iterations)                │       │
  │                          └─────────────────────────────────-┘       │
  │                                                                     │
  │   Goal: a better next-pass starter for THIS agent. Cadence: hours   │
  │   to days. Output stays session-scoped — does not leak to other     │
  │   agents.                                                           │
  │                                                                     │
  └─────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────┐
  │                                                                     │
  │   Loop 3 — Cross-stage knowledge promotion (slow, scope: all)       │
  │                                                                     │
  │   accumulated discovery + inception feedback → patterns_curator     │
  │   detects recurrence → candidate pattern → review → promoted to     │
  │   patterns/ → consumed by BOTH stages' proposer sub-agents          │
  │                                                                     │
  │   Goal: improve future runs at BOTH stages by capturing             │
  │   generalized lessons. Cadence: weekly / monthly / on-demand.       │
  │   The patterns library is the cross-stage connective tissue.       │
  │                                                                     │
  └─────────────────────────────────────────────────────────────────────┘
```

The three loops MUST be separate. Reasons:

- Per-session feedback (loops 1 + 2) is often specific (*"we skipped the Atlan step because the customer's tenant was down that day"*) and should NEVER generalize. Stays inside its session.
- Cross-stage promotion (loop 3) needs evidence of recurrence to avoid promoting noise into the global knowledge base.
- Each loop's cadence is different. Conflating them produces a system where every minor session signal pollutes the global knowledge.
- The promotion threshold is the load-bearing decision: too low → patterns library gets polluted; too high → learnings get lost.

There is intentionally **no direct API between discovery and inception for feedback**. If inception reveals discovery missed something, the signal flows through loop 3 (patterns library) — not through a backchannel that would force discovery to re-run on a single inception's complaint. This makes cross-stage learnings explicit and audit-trail visible, and prevents one builder's idiosyncrasy from rewriting discovery for everyone.

---

## Loop 1 — Discovery iteration

### What gets captured

Discovery's per-session output is `spec.md` + `outstanding_questions.md` (per `plans/05-technical-thread-discovery.md`'s `gap_reporter` + `context_gap_proposer`). When the spec has too many open questions to gate to inception, discovery iterates:

**Three iteration modes:**

| Mode | When to use | Output |
|---|---|---|
| **Follow-up discovery session** | Major gaps; customer time available | New transcript → re-run intake or extend the existing session |
| **Chat-based gap-filling** | Targeted questions; FDE chat with customer | Spec updates inline; specific gaps close one at a time |
| **Transcript ingest** | Customer recorded answers offline | New artifact fed back through intake's `--use-case` orientation |

Each iteration produces a new spec version. The session's history captures: spec v1 → outstanding Qs v1 → iteration mode → spec v2 → outstanding Qs v2 → ... until the gate criteria are met.

### The spec gate

When does the spec gate to inception? Three signals:

1. **Canonical-topic coverage** — the existing checklist (per `agent/state.py`) plus the new technical topics (per `plans/05`) all have at least one fact each
2. **Remaining gaps are not load-bearing for inception** — gaps that the inception agent can scaffold around (open recommendation scope, voice details that need iteration) don't block; gaps that determine architecture (data source choice, runtime constraints) do block
3. **Explicit FDE judgment** — the human running discovery says "good enough"

For v1: gate is human-judged. Later iterations: a small `spec_completeness_classifier` sub-agent reads the spec + outstanding Qs and emits a `gate_state: ready | needs_more` recommendation. Even later: discovery becomes self-aware enough to know when it's done. We don't try to automate this before observing real iteration patterns.

### What stays session-scoped (never promotes)

Discovery feedback that DOES NOT cross the session boundary:

- *"This customer's Atlan tenant was down so we couldn't pull bounded context"* — operational
- *"The CFO joined the call so we had to skip the technical thread for half the conversation"* — meeting-shaped reality
- *"This customer keeps using 'flings' to mean 'pods' which threw the parser"* — customer-specific vocabulary

These stay in the session's history (relevant to that session's next iteration; ignored by loop 3).

### How a re-run consumes prior feedback

When discovery re-runs after a follow-up session or chat-fill, the new turn's mega-agent prompt gains a section:

```
## Prior iteration

You have already had a discovery session on this use case. The previous
session produced:
  - Spec covering: [list of canonical topics + facts captured]
  - Outstanding questions: [list of unresolved Qs]
  - Customer's last position on [each open thread]: ...

Continue the discovery; don't re-ask what's already settled. Focus on
filling the outstanding gaps. Treat the customer's previous answers as
established context.
```

This is the same priors-loading mechanism intake already produces; discovery just consumes a richer set when there's prior session output.

---

## Loop 2 — Inception iteration

### What gets captured

Two modalities (matching the original inception feedback design):

**Implicit feedback (cheap, automatic).** The delta between what inception scaffolded and what the builder shipped. Captured via either:
- Builder edits `agent_starter/` in place, we observe the diff
- Builder submits the final agent back to inception with `inception compare-to-shipped`

Either path produces a `delta_report.md`: structured comparison with salient differences flagged.

**Explicit feedback (cheaper to act on; requires builder effort).** Annotations on `design_rationale.md`:
- `worked_as_proposed`
- `worked_with_modification: $description`
- `wrong_for_this_use_case: $what_we_did_instead, $why`
- `missing: $description`

Plus a free-text `lessons_learned.md` for session-level insights.

### How inception consumes feedback in a subsequent run

When inception re-runs against the same DiscoverySpec with feedback, the workflow_classifier and proposer sub-agents get one additional input — the structured feedback from the previous iteration:

```python
inception_session.run(
    spec=discovery_spec,
    bounded_context=atlan_context,
    prior_iteration_feedback=feedback_v1,
)
```

Each sub-agent's prompt gains a section:

```
## Prior iteration feedback

The previous inception output was tried by a builder. They reported:
  - Decisions that worked as proposed: [...]
  - Decisions that worked with modification: [...]
  - Decisions that were wrong: [...]
  - Missing considerations: [...]
  - Free-text lessons: [...]

Treat these as constraints. Don't repeat decisions marked "wrong" without
explicit justification. Address each "missing" item.
```

### What stays session-scoped

Inception feedback that DOES NOT cross the session boundary:

- *"The customer wanted a different report format than we scaffolded"* — preference, not pattern
- *"We had to swap the LLM model because of budget"* — resource constraint
- *"This particular brand has a non-standard product hierarchy"* — customer-specific
- *"The CFO doesn't trust narrative reports; we replaced with a dashboard"* — stakeholder politics

These remain in the session's history.

---

## Loop 3 — Cross-stage knowledge promotion

### The promotion mechanism

After feedback accumulates across many sessions at BOTH stages, the `patterns_curator` agent (defined in `plans/07`) runs a periodic **promotion pass**:

```
1. Read all session feedback artifacts:
   - Discovery: spec.md histories + outstanding_questions deltas + lessons_learned
   - Inception: delta_report.md + design_rationale annotations + lessons_learned
2. Cluster by topic / decision-area / sub-agent affected
3. For each cluster:
   a. Is it specific or generic?  (specific_vs_generic_classifier sub-agent)
   b. Is the signal recurring?     (count occurrences across distinct sessions, both stages)
   c. Does an existing pattern already cover it?
4. Generate candidate pattern entries for clusters that are
   generic + recurring + uncovered
5. Surface candidates for review (humans, or eventually a meta-curator agent)
6. Reviewed candidates committed to patterns/ as new entries with
   status: experimental
7. After M more validating sessions, experimental → validated
```

The threshold for "recurring" is the critical knob. Initial proposal: **a signal needs to appear in ≥3 distinct sessions before becoming a candidate pattern.** Conservative — false promotions pollute the global knowledge base, and once a pattern is in `patterns/` it influences every future inception AND discovery run.

### Cross-stage learning examples

The patterns library is the connective tissue. Generic lessons flow from one stage's feedback to BOTH stages' future behavior:

| Lesson surfaced from | Pattern entry created | Consumed by |
|---|---|---|
| Inception (Bala's `bca_framework` lesson) | `patterns/anti-patterns/definitions-without-context.md` | Both: inception's skill_proposer flags it; discovery's prompts can reference it when capturing taxonomy details |
| Discovery (repeated meta-artifact role-anchoring failures) | `patterns/anti-patterns/role-anchoring-on-meta-artifact.md` (TBD) | Both: discovery's intake learns to flag meta-artifacts upfront; inception learns to ask "was discovery run on a meta-artifact?" when reviewing spec quality |
| Cross-stage (inception scaffolding revealed discovery missed BCA taxonomy) | `patterns/skill-design/taxonomy-must-be-elicited-explicitly.md` (TBD) | Both: discovery's gap_reporter learns to probe for taxonomies; inception's skill_proposer learns to require taxonomies before classification skills |

The third row is the explicit cross-stage path. When inception's feedback consistently surfaces *"discovery should have captured X"* across ≥3 sessions, the curator promotes a pattern that updates discovery's prompts going forward. The path goes through patterns/, not through a direct discovery-stage hook — that forces the lesson to generalize before it propagates.

### The specific-vs-generic classifier

This is the riskiest sub-agent in the entire system. It decides what crosses from session-scoped to global. Its job: read a feedback snippet and decide whether the lesson it teaches is:

- **Specific** — only applies to one customer / one domain / one weird situation → discard, stay session-scoped
- **Workload-shape generic** — applies to all agents with similar workload (e.g., "for query-response agents, the data_summary pattern matters") → promote
- **Architecture-generic** — applies to all agents using a particular architectural choice → promote
- **Domain-generic** — applies to all agents in a particular domain (e.g., "for P&G analyst agents, BCA framework is the canonical classification") → promote *for that domain* (sub-folder)
- **Skill-design-generic** — applies to any skill of a particular shape → promote
- **Discovery-process-generic** (new with the discovery stage in scope) — applies to all discovery sessions of a particular shape (e.g., "meta-artifacts need orientation up front") → promote

The classifier's prompt heavily leans toward **specific** when ambiguous. Its hard rule: *if you can't articulate the workload shape / architecture / domain / discovery-pattern this lesson applies to, it's not generic enough.*

### Example: how Bala's lessons would have flowed (counterfactual)

If we'd had loop 3 running and Bala had submitted feedback after his P&G build:

| Bala's lesson | Specific or generic? | Pattern entry created |
|---|---|---|
| `bca_framework` must travel with diagnosis to orchestrator | Architecture-generic | `patterns/anti-patterns/definitions-without-context.md` (already exists in our seed!) |
| `data_summary` not raw rows | Skill-design-generic | `patterns/anti-patterns/truncated-data-summary.md` (already exists) |
| `resolve_entity_values` before SQL gen | Skill-design-generic | `patterns/skill-design/canonical-entity-resolution.md` (TBD) |
| SQL retry with correction prompt | Skill-design-generic | `patterns/skill-design/sql-retry-with-correction-prompt.md` (TBD) |
| Domain knowledge in Atlan, not prompts | Workload-shape generic | Merges into existing `patterns/anti-patterns/opinion-baked-in-prompt.md` (TBD) |

All 5 generalize. None are P&G-specific. After 3 sessions reporting similar lessons, all 5 would have been promoted — and the 6th P&G-like build would have started near 90/100 instead of Bala's 50→97 climb.

The two seeded entries already in our patterns/ demonstrate the mechanism in advance — we're treating Bala's lessons as the equivalent of a 3-session signal (one extremely detailed source counts as evidence even before the recurrence threshold strictly fires).

---

## Anti-patterns the loops must avoid

### Over-promotion

Single-session signal → promoted to global pattern → every future inception/discovery output incorporates a one-customer quirk → systematic miscalibration across all builds.

**Guardrail:** ≥3 distinct session recurrence threshold. Plus the specific-vs-generic classifier's lean-toward-specific bias.

### Stale promotion

Old promoted patterns persist forever. The field shifts; the pattern becomes wrong; both stages keep outputting it.

**Guardrail:** `patterns/` lint operation (defined in `plans/07`) flags entries > 90 days old as review-needed. Patterns can be marked `deprecated` or replaced by newer entries.

### Feedback gaming

Builders / FDEs who don't want to iterate write generic "looks good" feedback to skip the loop.

**Guardrail:** Implicit feedback (delta between starter and shipped agent; spec v1 vs spec v2 in discovery) is captured automatically. Explicit feedback is bonus, not load-bearing.

### Feedback exhaustion

If giving feedback is too painful, builders skip. If we ask 20 structured questions, they skip.

**Guardrail:** Feedback is OPT-IN and lightweight. 1-click annotations + optional free-text. Implicit-delta happens regardless.

### Anti-knowledge promotion

The opposite of over-promotion: legitimate generic lessons get filtered out because the classifier is too aggressive. Real learnings stay session-scoped; the system doesn't compound.

**Guardrail:** Periodic human audit of *rejected* candidate promotions. If we're consistently rejecting things that should have promoted, the classifier needs tightening. This is itself a candidate finding to write up.

### Cross-stage shortcuts

Inception's feedback creating a direct hook into discovery's prompts, bypassing the patterns library. Tempting for fast fixes; creates entanglement where one builder's idiosyncratic feedback can reshape discovery for everyone.

**Guardrail:** No direct stage-to-stage API. Cross-stage learnings flow through `patterns/` only, with recurrence + classification gates.

### Premature gate automation

Trying to automate the discovery → inception gate before we've seen enough manual iterations to know what "good enough" looks like empirically.

**Guardrail:** Gate is human-judged in v1. Automation only once we have empirical data on what FDEs actually choose as "good enough."

---

## Where this fits into the existing roadmap

| Plan | Role in the three loops |
|---|---|
| `05-technical-thread-discovery` | Produces the discovery-side feedback artifacts (outstanding_questions, spec versions) |
| `06-atlan-context-integration` | Provides the bounded-context input that reduces discovery's need for iteration |
| `07-patterns-knowledge-base` | Hosts the patterns library that is loop 3's substrate |
| `08-inception-agent` | Produces the inception-side feedback artifacts (design_rationale, delta_report, lessons_learned) |
| `09-context-debt-migration-backlog` | Receives auto-flags from loop 3 when promoted patterns overlap with prompt-baked opinions |

This doc is the orchestration layer that ties them together via the feedback shapes and the curator-mediated cross-stage channel.

---

## Implementation sequence

**Loop 2 (inception iteration) — first to build.** Per `plans/08`, the inception sub-agents already accept a `prior_iteration_feedback` parameter; the feedback infrastructure (`agent_starter/feedback/` + `inception compare-to-shipped` CLI + lessons_learned template) ships alongside the scaffold_writer.

**Loop 1 (discovery iteration) — second.** The mechanism is largely already designed in `plans/05` (gap_reporter + outstanding_questions). Add explicit gating logic + prior-session-loading prompt scaffolds.

**Loop 3 (cross-stage promotion) — third, biggest lift.** Build out `patterns_curator`'s `promote` operation per `plans/07`. Add the specific_vs_generic_classifier sub-agent. Run on accumulated feedback after enough sessions exist (probably needs ≥10 builds before the loop produces meaningful candidates).

**Counterfactual validation.** Feed Bala's 5 documented lessons through the promotion mechanism as if they were session feedback. Confirm all 5 cluster, classify as generic, and produce candidate pattern entries that match the seed entries we've already authored.

---

## What this doesn't do (scope boundaries)

- **Doesn't auto-promote without human review.** Initially every promotion gets human eyes. Automated promotion comes once we trust the classifier on accumulated data.
- **Doesn't learn from agent failures in production.** Production-telemetry → patterns is its own future plan. This doc covers builder/FDE feedback during iteration.
- **Doesn't propagate feedback backwards into the same-session agent.** A discovery agent doesn't auto-update its prompts based on a follow-up customer turn. Cross-session learning is exclusively via loop 3.
- **Doesn't replace the curator's other ingest sources.** Findings + external research + builder reports remain primary; cross-stage feedback is a new feeder, not a replacement.

---

## The compounding claim, restated

> Without the three loops: discovery produces decent specs that humans manually shepherd; inception produces decent starters that builders manually iterate. The 1st P&G build, the 10th, and the 100th land at similar quality. Lessons stay in heads or in README files.
>
> With the three loops: every shipped agent feeds lessons back. After 5 sessions, the curator has promoted ~3 cross-stage patterns. After 20, ~10–15. The 20th builder's first-pass output reflects 20 builds of accumulated wisdom and lands at 88/100, not 75. The 20th discovery session asks sharper questions than the 1st because the lessons of 19 prior sessions have updated the prompts (via patterns).
>
> That's the difference between "two tools" and "a system that learns to make better agents." The first is useful. The second is the durable IP this project is trying to build.

---

## Open questions

1. **How long do we keep individual session feedback?** Forever (traceability) vs prune after N months (privacy / data hygiene)? Lean keep-forever with strict scope tagging.
2. **Should the implicit-delta detection be perfect or best-effort?** A builder might refactor heavily and the diff becomes uninterpretable. Lean best-effort — flag suspect deltas for builder annotation rather than failing.
3. **Can builders / FDEs opt out?** Yes — mark sessions `private`. Adds friction to compounding but preserves trust.
4. **Promotion pass cadence?** Weekly initially. Frequent enough to surface fast lessons; infrequent enough that the review queue stays manageable.
5. **How does this interact with `plans/09` context-debt backlog?** Promotions may create patterns that overlap with existing prompt-baked opinions. When that happens, affected backlog entries auto-flag as "high-priority migration."
6. **What if two builders have contradictory feedback on the same decision?** First case: classify session-specific (different contexts). Repeated case: surface explicitly as a candidate decision-guide entry — "depends on X." Forces the global knowledge to capture the conditional.
7. **When does the spec gate (loop 1 → loop 2) get automated?** Only after we've seen enough manual gating to know the right criteria. Probably ≥10 discovery sessions.
8. **Can loop 3 promote patterns that contradict existing patterns?** Yes — that's the `superseded_by:` mechanism in `plans/07`. Old patterns deprecate; new ones take their place. Both stay readable.
