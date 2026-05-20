# 10 — Feedback Loop and Knowledge Promotion

**Status:** design — not yet built.
**Closes the loop on:** `plans/08-inception-agent.md` (per-session iteration) + `plans/07-patterns-knowledge-base.md` (cross-session knowledge accumulation).
**Implements:** the compounding mechanism that makes "agent that helps build other agents" get *better over time*, not just faster.

---

## The two loops

There are two distinct feedback loops in the system, operating at different scopes and cadences. They share infrastructure but have different goals.

```
  ┌──────────────────────────────────────────────────────────────────┐
  │                                                                  │
  │   Loop 1 — Per-session iteration (tight, scope: one agent)       │
  │                                                                  │
  │   inception → agent_starter → builder iterates → feedback →      │
  │       inception (re-runs with feedback) → improved starter → ... │
  │                                                                  │
  │   Goal: a better next-pass starter for THIS agent.               │
  │   Cadence: minutes to days within one build session.             │
  │   Output stays session-scoped — does not leak to other agents.   │
  │                                                                  │
  └──────────────────────────────────────────────────────────────────┘

                            ↓  (after N sessions)

  ┌──────────────────────────────────────────────────────────────────┐
  │                                                                  │
  │   Loop 2 — Cross-session knowledge promotion (slow, scope: all)  │
  │                                                                  │
  │   accumulated session feedback → curator detects recurrence →    │
  │       candidate pattern → human-or-curator review → promoted     │
  │       to patterns/ → consumed by ALL future inception runs       │
  │                                                                  │
  │   Goal: improve future inception runs by capturing generalized   │
  │   lessons.                                                       │
  │   Cadence: weekly / monthly / on-demand.                         │
  │   Output is the knowledge wiki — sharpens the system globally.   │
  │                                                                  │
  └──────────────────────────────────────────────────────────────────┘
```

The two loops MUST be separate. Reasons:
- Per-session feedback is often specific ("we skipped the Atlan step because the customer was offline that day") and should NEVER generalize
- Cross-session promotion needs evidence of recurrence to avoid promoting noise into the global knowledge base
- The promotion threshold is the load-bearing decision: too low and the patterns library gets polluted; too high and learnings get lost

---

## Loop 1 — Per-session feedback shape

### What gets captured

Feedback comes in two modalities:

**Implicit feedback (cheap, automatic):**

The delta between what inception scaffolded and what the builder shipped. If inception proposed 4 skills and the final agent has 3, that's signal. If inception picked single-agent ReAct and the final agent uses chained-pipeline, that's signal. If inception's eval seed had 12 questions and the final test set has 30, that's signal.

This requires the builder to either:
- Edit the `agent_starter/` directory in place (we observe the diff), OR
- Submit the final agent back to inception with a "compare against starter" command

Either path produces a `delta_report.md`: structured comparison of starter vs final, with the salient differences flagged.

**Explicit feedback (cheaper to act on, requires builder effort):**

Annotations on the `design_rationale.md` file. Each decision in that file is reviewable; the builder marks decisions as:
- `worked_as_proposed` — no change needed
- `worked_with_modification` — kept the decision but adjusted: $description
- `wrong_for_this_use_case` — replaced entirely: $what_we_did_instead, $why
- `missing` — should have been considered but wasn't: $description

Plus a free-text `lessons_learned.md` field at the session level for things that don't fit the decision-by-decision grain.

### How inception consumes feedback in a subsequent run

When inception re-runs against the same `DiscoverySpec` with feedback present, the workflow_classifier and proposer sub-agents get one additional input: the structured feedback from the previous iteration.

```python
inception_session.run(
    spec=discovery_spec,
    bounded_context=atlan_context,
    prior_iteration_feedback=feedback_v1,  # NEW
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

Treat these as constraints when producing this iteration's output. Do not
repeat decisions marked "wrong for this use case" without explicit
justification. Address each "missing" item.
```

This is per-session priors — the same shape as how discovery consumes RoleContext priors from intake. The mechanism is well-understood.

### What stays session-scoped (never promotes)

These signals DO NOT cross the session boundary:

| Signal | Why it doesn't generalize |
|---|---|
| "We skipped Atlan integration because the customer's tenant was down that day" | One-off operational reality, not a design lesson |
| "This brand voice didn't sound right" | Customer-specific, not architectural |
| "The CFO wanted a different report format" | Stakeholder preference, not generic |
| "We had to swap the LLM model because of budget" | Resource constraint, not pattern |

These stay in the session's feedback records (useful for that session's next iteration; ignored by the cross-session loop).

---

## Loop 2 — Cross-session knowledge promotion

### The promotion mechanism

After feedback accumulates across many sessions, the `patterns_curator` agent (defined in `07-patterns-knowledge-base.md`) runs a periodic **promotion pass**:

```
1. Read all session feedback artifacts (delta_report.md + lessons_learned.md)
   across recent N sessions
2. Cluster by topic / decision-area / sub-agent affected
3. For each cluster:
   a. Is it specific or generic?  (LLM call with strict prompt)
   b. Is the signal recurring?     (count occurrences across distinct sessions)
   c. Does an existing pattern already cover it?
4. Generate candidate pattern entries for clusters that are
   generic + recurring + uncovered
5. Surface candidates for review (humans, or eventually a meta-curator agent)
6. Reviewed candidates get committed to patterns/ as new entries with
   status: experimental
7. After M more validating sessions, experimental gets promoted to validated
```

The threshold for "recurring" is the critical knob. Initial proposal: **a signal needs to appear in ≥3 distinct sessions before becoming a candidate pattern.** This is intentionally conservative — false promotions pollute the global knowledge base, and once a pattern is in `patterns/` it influences every future inception run. Better to miss real signal than to promote noise.

### The specific-vs-generic classifier

This is the riskiest sub-agent in the entire system. It decides what crosses from session-scoped to global. Its job: read a feedback snippet and decide whether the lesson it teaches is:

- **Specific** — only applies to one customer / one domain / one weird situation → discard, stay session-scoped
- **Workload-shape generic** — applies to all agents with similar workload (e.g., "for query-response agents, the data_summary pattern matters") → promote to patterns
- **Architecture-generic** — applies to all agents using a particular architectural choice (e.g., "for single-agent ReAct with multi-skill orchestration, definitions must travel with diagnoses") → promote to patterns
- **Domain-generic** — applies to all agents in a particular domain (e.g., "for P&G analyst agents, BCA framework is the canonical classification") → promote to patterns *for that domain* (sub-folder)
- **Skill-design-generic** — applies to any skill of a particular shape → promote to patterns/skill-design/

The classifier's prompt should heavily lean toward **specific** when ambiguous. Its hard rule: *if you can't articulate the workload shape / architecture / domain that this lesson applies to, it's not generic enough.* That forces explicit categorization, which forces specificity in the pattern that would be created.

### Example — promotion in action (counterfactual against Bala's lessons)

If we'd had this loop running and Bala had submitted feedback after building his P&G agent, here's how each of his 5 documented lessons would have flowed:

| Bala's lesson | Specific or generic? | Promoted? | Pattern entry |
|---|---|---|---|
| `bca_framework` must travel with diagnosis to orchestrator | Architecture-generic (applies to any multi-skill agent where the orchestrator reasons about classifications) | Yes (after recurrence) | `patterns/skill-design/definitions-must-travel-with-labels.md` |
| `data_summary` not raw rows | Skill-design-generic (applies to any skill that runs LLM interpretation on query results) | Yes | `patterns/anti-patterns/truncated-data-summary.md` |
| `resolve_entity_values` before SQL gen | Skill-design-generic (applies to any LLM-generated SQL against a database with case-sensitive strings) | Yes | `patterns/skill-design/canonical-entity-resolution.md` |
| SQL retry with correction prompt | Skill-design-generic | Yes | `patterns/skill-design/sql-retry-with-correction-prompt.md` |
| Domain knowledge in Atlan, not prompts | Workload-shape generic (applies to any agent that reasons about evolving domain concepts) | Yes — this is the same principle that's now `patterns/anti-patterns/opinion-baked-in-prompt.md` | (merges into existing) |

All 5 generalize. None are P&G-specific. After 3 sessions had reported similar lessons (Bala + two others building similar agents), each would have been promoted to patterns and consumed by every subsequent inception run.

The compounding effect: by the time the 10th agent build happens, inception's first-pass output reflects all the lessons learned from builds 1-9. The 10th builder starts much closer to 97/100 than the 1st builder did.

---

## Anti-patterns the loop has to avoid

### Over-promotion

Single-session signal → promoted to global pattern → every future inception output incorporates a one-customer quirk → systematic miscalibration across all builds.

**Guardrail:** ≥3 distinct session recurrence threshold. Plus the specific-vs-generic classifier's lean-toward-specific bias.

### Stale promotion

Old promoted patterns persist forever. The field shifts; the pattern becomes wrong; inception keeps outputting it.

**Guardrail:** `patterns/` lint operation (defined in `07`) flags entries > 90 days old as review-needed. Patterns can be marked `deprecated` or replaced by newer entries.

### Feedback gaming

Builders who don't want to iterate write generic "looks good" feedback to skip the loop.

**Guardrail:** Implicit feedback (delta between starter and shipped agent) is captured automatically and doesn't require builder cooperation. Explicit feedback is bonus, not load-bearing.

### Feedback exhaustion

If giving feedback is too painful, builders won't do it. If we ask 20 structured questions, they'll skip.

**Guardrail:** Make feedback OPT-IN and lightweight. The `design_rationale.md` annotations are 1-click ("worked / didn't work / missing"). The free-text field is genuinely optional. The implicit-delta capture happens regardless.

### Anti-knowledge promotion

The opposite of over-promotion: legitimate generic lessons get filtered out because the classifier is too aggressive. Real learnings stay session-scoped and the system doesn't compound.

**Guardrail:** Periodic human audit of *rejected* candidate promotions. If we're consistently rejecting things that should have been promoted, the classifier needs tightening (or its prompt needs adjusting). This is itself a candidate finding to write up.

---

## Where this fits into the existing roadmap

| Plan | What it provides | How `10` extends it |
|---|---|---|
| `07-patterns-knowledge-base.md` | The patterns library + curator agent (ingest, query, lint) | Adds a new ingest source: cross-session feedback. The curator's existing operations grow a `promote` operation. |
| `08-inception-agent.md` | The inception sub-agents that produce `agent_starter/` | Adds `prior_iteration_feedback` as an optional input to a re-run. Sub-agents consume it as constraint-priors. |
| `05-technical-thread-discovery.md` | Discovery's spec output | No direct change — discovery still produces specs. The feedback loop operates downstream of discovery. |
| `06-atlan-context-integration.md` | Atlan as bottom-up context source | No direct change — feedback is about what the agent *does*, not about what's in Atlan. |
| `09-context-debt-migration-backlog.md` | Migration debt tracking for prompts | No direct change — but the cross-session promotions provide a new feeder for the migration backlog (e.g., if a pattern gets promoted that contradicts something baked into a prompt, the prompt's debt entry becomes higher-priority). |

This doc is genuinely additive — it doesn't change the prior plans' designs, just defines the mechanism by which they all get *better* over time.

---

## Feedback artifact shapes

### Per-session feedback (Loop 1 inputs)

Two files dropped alongside `agent_starter/`:

**`agent_starter/feedback/delta_report.md`** (auto-generated when builder runs `inception compare-to-shipped`):

```yaml
session_id: pg-fhc-2026-05-21
starter_version: v1
shipped_version: post-iteration-3

deltas:
  skill_count:
    starter: 4
    shipped: 3
    note: "question_parser merged into market_share_analyzer"
  architecture:
    starter: single-agent-react
    shipped: single-agent-react
    note: "no change"
  skills_modified:
    - market_share_analyzer:
        changes: ["incorporated resolve_entity_values logic", "added retry-with-correction"]
  skills_removed:
    - question_parser  # merged elsewhere
  skills_added:
    - bca_classifier   # not in starter
  eval_questions:
    starter: 12
    shipped: 47
    note: "expanded coverage across BCA categories"
```

**`agent_starter/feedback/lessons_learned.md`** (free-form, builder-authored):

```markdown
# Lessons from the P&G F&HC build

## What worked from the starter
- Single-agent ReAct architecture was the right choice
- The inner-pipeline skill pattern was exactly right for market_share_analyzer

## What didn't work
- question_parser as a separate skill: too granular, added latency without value
- The eval seed missed BCA-classification questions; had to expand significantly

## What was missing
- The starter didn't surface that diagnoses without definitions cause hallucination
- No retry pattern was included; we had to add it

## Generalizable observations
- For agents that classify into a framework, the classification definitions
  must travel WITH the diagnosis to wherever the orchestrator narrates
- For LLM-generated SQL on string-keyed databases, pre-resolve canonical
  case-exact values
```

### Cross-session feedback (Loop 2 inputs)

The curator agent reads all `feedback/*.md` files across all known sessions. Clustering happens at the curator level; no per-session work needed beyond authoring the above two files.

---

## Implementation sequence

1. **Feedback capture infrastructure**
   - Add `agent_starter/feedback/` directory to scaffold_writer's output (per `08`)
   - Build `inception compare-to-shipped` CLI command — diffs starter vs final, produces `delta_report.md`
   - Template `lessons_learned.md` for builders to fill in

2. **Loop 1 — per-session re-run with feedback**
   - Add `prior_iteration_feedback` parameter to `run_inception()`
   - Update each sub-agent's prompt to consume the feedback section
   - Validate: run inception on P&G case → manually fabricate a feedback file → re-run → confirm output respects feedback

3. **Loop 2 — promotion mechanism**
   - Build the `specific_vs_generic_classifier` sub-agent (single prompt, classification output)
   - Extend `patterns_curator` with a `promote` operation that reads feedback files, clusters, classifies, and surfaces candidates
   - Build the candidate-review workflow (human-in-the-loop initially; later, meta-curator agent)
   - Recurrence-threshold enforcement (≥3 distinct sessions before promotion)

4. **Anti-pattern guardrails**
   - Rejected-promotion audit dashboard (or markdown report) so we can see what didn't promote and decide if the threshold is right
   - Periodic human audit (monthly?) of cross-session feedback to catch missed generalizations

5. **Validation**
   - Counterfactual: feed Bala's 5 documented lessons through the promotion mechanism as if they were session feedback. Confirm all 5 cluster, classify as generic, and produce candidate pattern entries that match what we'd expect.
   - Write this up as `findings/NN-feedback-loop-validation-against-bala-lessons.md` once executed.

Estimated 1–2 weeks for Loop 1 (it's mostly inception sub-agent extensions + a CLI command). Loop 2 is more substantial — 2–3 weeks for the promotion mechanism + validation + initial human-in-the-loop tooling.

---

## What this doesn't do (scope boundaries)

- **Doesn't auto-promote without human review.** Initially, every promotion candidate gets human eyes. Automated promotion is a future iteration once we trust the classifier.
- **Doesn't try to learn from agent failures in production.** This loop covers builder feedback during iteration, not customer-deployed agent telemetry. Production-telemetry → patterns is its own future plan.
- **Doesn't propagate feedback backwards into discovery.** If the inception output suggests discovery missed something, that's a manual signal — the discovery agent doesn't auto-update its prompts based on inception's feedback.
- **Doesn't replace the curator's other ingest sources.** Findings + external research + builder reports remain primary; cross-session feedback is a new feeder, not a replacement.

---

## The compounding claim, made explicit

> Without this loop: inception produces decent starters but doesn't improve from them. The first P&G build is 75/100; the 10th P&G build is also 75/100. Each builder iterates independently; their lessons stay in their heads or in their READMEs.
>
> With this loop: every shipped agent feeds lessons back. After 5 sessions, the curator has promoted ~3 cross-session patterns. After 20 sessions, ~10–15. The 20th builder's first-pass inception output reflects 20 builds of accumulated wisdom and lands at 88/100, not 75.
>
> That's the difference between "agent that produces starters" and "agent that learns to produce better starters." The first is a useful tool. The second is the durable IP the project is trying to build.

---

## Open questions

1. **How long do we keep individual session feedback?** Forever (for traceability) vs prune after N months (privacy / data hygiene)? Lean keep-forever with strict scope tagging.
2. **Should the implicit-delta detection be perfect or best-effort?** A builder might refactor heavily and the diff becomes uninterpretable. Lean best-effort — flag suspect deltas for builder annotation rather than failing.
3. **Can builders opt out?** Yes, they should be able to mark sessions `private` (no feedback flows to the curator). Adds friction to the compounding claim but preserves trust.
4. **What's the right cadence for promotion passes?** Weekly is probably right initially — frequent enough that recent lessons surface quickly; infrequent enough that the curator's review queue stays manageable. Adjust empirically.
5. **How does this interact with the context-debt migration backlog (`09`)?** Promotions might create new patterns that overlap with existing prompt-baked opinions. When that happens, the affected backlog entries get auto-flagged as "high-priority migration." Logical extension of both mechanisms.
6. **What if two builders have contradictory feedback on the same decision?** First case: classify as session-specific (different contexts produced different outcomes). Repeated case: surface the contradiction explicitly as a candidate decision-guide entry — "depends on X". Forces the global knowledge to capture the conditional.
