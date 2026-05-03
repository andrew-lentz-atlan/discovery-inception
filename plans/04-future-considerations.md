# 04 — Future Considerations

Parking lot for things that aren't on the critical path for v0 but that we don't want to forget. Read this when you've shipped something and are thinking about what's next.

## Output format: the context repo

We agreed the eventual output of the discovery system is a **context repo**, not a single doc. This is on-thesis with Atlan (structured context layer for an agent, mirroring Atlan's structured context layer for assets — same shape, different domain).

### Proposed shape

```
context_repos/<use-case-id>/
├── manifest.json                    # version, created_at, source_session_id
├── spec.md                          # full markdown brief (human-facing)
├── mva.md                           # the slice the first agent uses
├── skills/
│   ├── role-context/
│   │   ├── context.json             # structured RoleContext
│   │   └── source/                  # original artifacts the customer provided
│   └── domain-glossary/
│       └── terms.json
├── tools/
│   ├── proposed/
│   │   ├── pricing_lookup.py        # scaffold for a tool the agent will need
│   │   └── pricing_lookup.spec.md   # spec for what it should do
│   └── existing/
│       └── allowlist.json           # which existing harness tools the agent uses
├── prompts/
│   ├── system_prompt.md             # base system prompt
│   └── stage_prompts/               # if the agent itself is multi-stage
│       └── ...
├── config.yaml                      # drops directly into harness/config/
├── traces/                          # populated AFTER agent runs (closed loop)
│   └── <run-id>/
│       └── trace.json
└── feedback/                        # gaps surfaced from trace analysis
    └── pending.md
```

### Why this shape works
- **Versionable.** Git-friendly. Every iteration of the discovery output is a commit.
- **Inspectable.** `cat` works on every file. No DB.
- **Composable.** A skill in one repo can be referenced from another. Domain glossaries get reused across agents.
- **Closed-loop friendly.** Traces and feedback live alongside the spec they came from. Easy to see "this gap surfaced from this run."

### What needs to happen to get here
- Stage 4's Build Bridge becomes the producer of this structure.
- A small "context repo writer" tool in the harness.
- Convention agreement on file naming and schemas (Pydantic models exported as JSON Schema).
- Probably a CLI: `discovery-inception render <session-id> --out context_repos/<id>`

### Why this is a future concern
Right now we don't have a working pipeline. The output shape doesn't matter until something is producing structured stage outputs. But the shape informs the design of stage outputs, so worth keeping in mind. The pattern: each stage's Pydantic output object should be renderable into one or more files in this directory tree.

---

## Evaluation strategy

How do we know any of this works? Three layers, in increasing rigor.

### Layer 1: Self-report
After running a session, the user (FDE or customer) self-reports:
- "Did the conversation surface anything you wouldn't have written down on your own?"
- "Did the spec capture the WHY in a way you could defend to your manager?"
- "Were there moments the system caught you being vague?"

Single most valuable signal in v0. If the answer to question 1 is "yes" even once per session, the tool earned its keep.

### Layer 2: Reference comparison
Take a fixed set of fuzzy goals. Run them through:
- **A** — this discovery system
- **B** — a single-prompt control ("Hey Opus, decompose this goal: [goal]")
- **C** — an actual FDE doing it manually

Compare the three on:
- Number of decision points captured
- Number of tools/integrations identified
- Number of escalation rules
- Quality of MVA scoping (would a senior engineer accept the scope?)
- Time spent (for B and C, end-to-end; for A, customer time)

We don't expect A > C. We expect A ≈ B for breadth and A > B for specificity, with A << C in time. That's the value prop.

### Layer 3: Build-and-trace
For 1-2 use cases, actually build the agent the discovery system designed. Run it in production-like conditions. Analyze the traces. Count:
- How many traced failures came from missing context that discovery should have caught?
- How many came from edge cases discovery couldn't have known about?
- How many came from agent quirks (model behavior) unrelated to discovery?

Ratio matters. If 80% of failures trace back to discovery gaps, the discovery system is the bottleneck and we have a clear improvement path. If 80% trace to model behavior, discovery is mature and the bottleneck moved elsewhere.

### Eval cadence
- Layer 1 every session, automatically.
- Layer 2 when prompts materially change (track regressions).
- Layer 3 quarterly, on real builds.

---

## Trace-to-gap analyzer (closing the loop automatically)

In the architecture doc we noted step 4 of the closed loop ("trace analyzer identifies which steps had bad context") is human-driven for v0. Eventually we automate it.

Shape of the future trace analyzer:

```
input: full trace from a harness run + the context repo the agent ran on
    │
    ▼
1. Decision-point classifier
   For each step, was the model decision correct? (uses ground truth
   if available, LLM-as-judge if not)
    │
    ▼
2. Context attribution
   For each wrong decision, what context did the model have at that step?
   Was the context sufficient? If not, what's missing?
    │
    ▼
3. Discovery gap mapper
   For each missing-context finding, map it back to a section of the
   discovery spec. Mark that section as needing re-probing.
    │
    ▼
output: list of discovery gaps to feed back to Stage 2
```

This is itself a multi-stage agent. Probably another instance of the same pattern (decompose + decide + propose). Future research.

---

## Scaling considerations

When this stops being a research artifact and starts being something used by more than one person:

### Multi-tenant
- Discovery sessions per customer org
- Skill library shareable within an org, isolated across orgs
- Permissions model (who can read/edit/delete a context repo)

### Persistence
- Sessions persist (currently in-memory only in `../harness/`)
- Stage outputs persist after each stage (so a crashed session can resume)
- Skills versioned and rollback-able

### Observability
- Trace export to Langfuse/OpenLLMetry
- Per-customer cost tracking (especially relevant if mixing local and frontier models per stage)
- Latency budgets per stage with alerting

### Model routing
- Different stages, different models (already noted in architecture doc)
- Cost-aware routing — drop to local Gemma when commodity will do, escalate to Opus when stuck
- Per-customer model preferences (e.g., privacy-sensitive customers get local-only)

---

## Known prompt weaknesses to address later

Things we noticed during the 2026-05-03 hand-run that produced the SC gold reference, but deliberately did not fix tonight to avoid going down a rabbit hole. Address when an artifact surfaces them more sharply or when we have time to test fixes properly.

### Step 4 — anti-restatement guidance is too soft

The "don't restate the formal stuff" rule in the unwritten-rules sniffer prompt is currently too vague. The 2026-05-03 hand-run produced an unwritten rule (`"Enable customer self-sufficiency..."`) that was a near-verbatim restatement of a formal Core Responsibility bullet in the source. The current prompt language didn't catch it.

**Proposed sharper wording (from agent feedback):** *"Do NOT include rules that are stated as bullets, headings, or section titles in the source. Unwritten rules live in asides, examples, dialogue, or implicit between-the-lines statements. If a rule is also a formal section, it's not unwritten — drop it."*

**Why we didn't apply tonight:** Job descriptions are naturally low on unwritten rules — the substrate isn't there. Sharpening the anti-restatement clause might over-correct and produce empty `unwritten_rules` for *every* JD, which is also not the goal. Test against a transcript or runbook (where there are real asides AND formal sections) before deciding the right balance.

### Step 6 — surface the empty-fields-are-OK rule earlier

The confidence scorer prompt currently puts the "empty fields aren't penalized" rule mid-document. The 2026-05-03 agent suggested moving it to the top of the rules section so the scorer biases away from punishing correct-but-empty extractions from the start. Low-priority cosmetic edit.

### Vocabulary normalizer — over-inference even with the patch

Today's patch (the `[INFERRED — please confirm]` prefix) shifts the *honesty* of inferred terms but doesn't reduce the *rate* at which we infer. If we want to reduce inference, the prompt would need a stronger "skip rather than infer" bias for low-confidence cases. Worth measuring on tomorrow's Haiku run before deciding — it may already self-correct under the new wording.

---

## Adjacent ideas worth thinking about later

- **Continuous discovery.** A session isn't a one-shot. Customers can return to a context repo, add new artifacts, re-trigger gap iteration. Discovery becomes ongoing, not a milestone.
- **Cross-customer skill library.** Patterns we extract from one customer's context (e.g., what a "tier-1 support workflow" looks like) become priors for the next customer. With consent.
- **Discovery as a workflow event.** Plug into Atlan's existing workflow engine. New asset created → trigger discovery for it. New customer onboarded → trigger CaaS intake.
- **Context drift detection.** Re-run discovery periodically against the same role/artifact. Flag if the captured context has shifted (new tools, changed escalation paths). Prompts the customer to update.
- **Adversarial customer.** A "challenger" agent that role-plays a skeptical customer in dry-run mode. Tests how robust the discovery output is to pushback before the real customer sees it.

---

## What's deliberately out of scope (for any future version)

- Replacing the FDE entirely. The honest target is FDE-with-tool > FDE-without > customer-with-tool > customer-alone.
- Building agents that learn from runtime feedback (continual learning). Out of scope without weight updates, which we're not doing.
- A general "all agents" platform. We're tuning hard for one slice. If we ever generalize, we generalize from a specific working version, not from the start.
- Selling this as a standalone product. It's research. If it becomes a product, that's a different conversation entirely with different constraints.
