# 03 — Stages Deep Dive

Per-stage detail for the four pipeline stages downstream of the CaaS intake. Read this when you're designing prompts or implementing stages.

For each stage: **purpose, inputs, outputs, hard parts, prompting notes, sub-agents**.

---

## Stage 1 — First Principles

### Purpose
Get to the bedrock of *why* this agent should exist. Not what it does. Not how it works. Why.

### Inputs
- A user-supplied fuzzy goal ("I want an agent that reduces churn")
- Optional: a `RoleContext` skill from CaaS intake (gives the system priors about the role this agent will augment/replace)

### Outputs
- `FirstPrinciplesOutput` — see schema in `01-architecture.md`
- Specifically: `why_now`, `desired_outcome` (measurable), `anti_goal` (explicit non-goal), `success_metric`, `current_pain_named`

### Hard parts
- Customers default to feature-language, not outcome-language. "We want an agent that auto-replies to emails" is feature; "We want to reduce response time on tier-2 tickets by 50%" is outcome. The stage has to consistently push from feature to outcome.
- The "why now" question is uncomfortable. Customers often don't have a real answer beyond "AI is hot." Push past that. If "why now" returns "because everyone is doing it," that's a flag — the use case isn't grounded yet.
- Anti-goals are weirdly hard to elicit. "What should this agent NOT do?" gets blank looks. Better framing: "If a junior employee was doing this job, what would you be most worried they'd mess up?" Or: "What would you NOT trust this agent to handle without a human?"

### Prompting notes
- Force concrete language. Reject hedge words ("kind of," "a bit," "potentially"). If the customer hedges, ask back.
- Time-bound everything. Deadlines, frequencies, durations.
- One question at a time. Multi-question prompts get half-answered.
- Small Gemma will template if asked open-ended. Better to ask narrow probes: "Name one specific moment in the last week when this problem hurt." Concrete examples beat abstractions.

### Sub-agents
- **Goal sharpener.** Takes the fuzzy goal, asks 1-2 questions to convert feature-language to outcome-language.
- **Why-prober** (shared with Stage 2). Pushes the chain until bedrock or 3-deep, whichever comes first.
- **Anti-goal extractor.** Different prompt. Looks for fears/risks/no-go zones rather than wants.

---

## Stage 2 — Gap Iteration (the loop)

### Purpose
The heart of the system. Take the rough output from Stage 1 and iteratively probe until the spec is dense enough for the validator to declare ready.

### Inputs
- `FirstPrinciplesOutput` from Stage 1
- `RoleContext` skill (if available) for pattern-recognition priors
- Cumulative `DiscoverySpec` (grows with each iteration)

### Outputs
- A populated `DiscoverySpec` covering: persona, decision journey, tool inventory, escalation rules, risks, plus uncertainty markers and a bedrock log
- The bedrock log is critical for downstream review. It shows, per topic, how deep the why-chain went and what the terminal answer was.

### Hard parts
- **"Gap" is fuzzier than you'd think.** Not just "field is empty." Also: vague, contradictory, untested, templatey, missing-the-why. The gap-finder needs to be opinionated about each of these.
- **Models are confidently wrong.** The gap-finder must be biased hard toward "we still need to ask." Default to paranoid.
- **Loop termination.** Without a hard cap, the system will loop forever (or stop too early). Need both: max iterations AND validator-declared "ready."
- **State management.** Each iteration adds to the spec. Need to track what's been probed already so we don't ask the same question twice.

### Prompting notes
- Each gap detector should look at one *type* of gap, not all of them. A gap-finder that's "looking for vagueness AND contradictions AND missing escalation paths" will be diluted. Specialized > generalized.
- Probe generation should be specific to the gap. "Vagueness about timing" → "What's the latency budget for this decision? Is it real-time, batch, or human-paced?" Pre-canned probe templates per gap type.
- BS detection in-conversation: standard sharpening questions like "How would you know if this were wrong?" "Have you actually seen this happen, or are you assuming?" "Give me a specific recent example." Use these as probe variants.
- The why-prober is its own sub-agent and should be reused.

### Sub-agents
- **Gap finder.** Reads current spec, returns list of gaps with type tags (vague/contradictory/untested/templatey/missing-why).
- **Probe generator.** Takes a gap and produces 1-3 sharp follow-up questions specific to that gap type.
- **Why-prober (shared with Stage 1).** For any captured statement, generates the next "why" question. If the next why is a tautology, mark that topic as bedrock.
- **Specificity scorer.** Scores statements on: concrete (named entities, numbers), verified (seen vs asserted), distinguishing (rules anything out vs applies to anyone). Two of three failing = flag.
- **Adversarial reviewer.** Re-reads the whole spec with one prompt: "What's the strongest argument that this discovery is incomplete?" Forces concrete remaining-gaps surfacing.

### Loop structure
```
while iterations < MAX and not validator_says_ready:
    gaps = gap_finder(current_spec)
    if no gaps and adversarial_reviewer finds nothing: break
    for gap in gaps:
        probes = probe_generator(gap)
        ask user(probes)
        update spec with answers
    update bedrock_log
```

### Strawman provocation (optional inside the loop)
Once per iteration, the system can choose to render a draft artifact (a Persona Card, a Decision Journey diagram, an Anti-Goal Statement) and show it to the customer. The customer's reaction ("no that's wrong because…") is high-signal input. This is the "imperfect output unlocks insight" principle in operation. Use sparingly — every provocation is a turn the customer has to read.

---

## Stage 3 — Documentation Validator

### Purpose
Decide whether the spec is "ready for build" or whether to send it back to Stage 2 for more iteration.

### Inputs
- The current `DiscoverySpec`
- The bedrock log

### Outputs
- `ValidationResult` — `ready: bool`, `confidence: float`, `remaining_gaps: list[Gap]`

### Hard parts
- **The stop condition is the entire job.** "Fully documented" is fuzzy. We need explicit, checkable criteria, AND a quality bar. Otherwise the validator declares victory after one shallow pass.
- **It must be paranoid by design.** Default answer is "not ready." The customer/operator has to be able to override (force-advance to Stage 4) if they're sure, but the validator's instinct should be conservative.
- **Calibration matters.** A validator that says "ready" too often produces bad specs that build bad agents. A validator that says "not ready" too often produces interview fatigue and wastes everyone's time. Aim for the latter at first; loosen later.

### Prompting notes
- Use a checklist. "Does the spec have: (a) a quantitative success metric, (b) at least one named persona, (c) at least 3 decision points with named inputs, (d) explicit escalation rules, (e) at least one risk, (f) bedrock-reached on the why_now and outcome questions?" Each must be true to declare ready.
- For each item, score concreteness/specificity. Empty bullets are not the same as filled bullets.
- Have the validator articulate WHAT'S MISSING when not-ready. The remaining_gaps list feeds back into Stage 2 directly.

### Sub-agents
- **Checklist evaluator.** Goes through the must-have items and scores each.
- **Quality gate.** For each filled item, scores it on the same specificity axes as the gap finder.
- **Confidence aggregator.** Combines per-field scores into an overall confidence number.

---

## Stage 4 — Build Bridge

### Purpose
Translate the validated `DiscoverySpec` into a deployable bundle of artifacts (the "context repo"). This is what the harness will consume to actually run the agent.

### Inputs
- A validated `DiscoverySpec`
- The full bedrock log and uncertainty markers
- The CaaS skill(s) used during discovery

### Outputs
- `ContextRepo` containing:
  - `spec_md` — full markdown brief (for humans)
  - `mva_scope` — the slice the first agent uses (10/10 quality)
  - `proposed_skills` — Atlan-shaped skill objects the agent will need
  - `proposed_tools` — sketches of new tools the agent will need (Python file scaffolds, OpenAPI specs, whatever)
  - `config_yaml` — drops directly into `../harness/config/`
  - `system_prompt_drafts` — first cut at system prompts for each stage of the agent (if the agent itself is multi-stage)

### Hard parts
- **Translating from process language to executable language.** The spec describes what an agent should do. The build bridge proposes how. This is a different cognitive task — needs different prompts, possibly a different model (more reasoning-capable).
- **Knowing what tools to propose.** Often the spec implies tools that don't exist yet ("the agent needs to check our pricing database"). The bridge has to recognize "tool gaps" and propose schemas/sketches even when the underlying integration doesn't exist.
- **Drawing the MVA boundary.** The full spec might have 12 decision points. The MVA might cover 3. The bridge has to decide which 3, and justify it.

### Prompting notes
- Be explicit about the audience. The audience is "an engineer who will read this and build the agent in `../harness/`." Not "the customer." Different vocabulary, different level of abstraction.
- For the MVA scoping, ask: "Of the 12 decisions in this spec, which 3 are highest-volume? Which are lowest-risk? Which are least dependent on judgment? The MVA should cover their intersection."
- The proposed-tools sketches should follow the existing `Tool` ABC pattern from the harness. Don't invent a new tool format — reuse the one we already have.

### Sub-agents
- **MVA scoper.** Picks the slice the first agent will cover.
- **Tool sketcher.** For each implied tool, produces a minimal `Tool`-shaped scaffold.
- **Skill packager.** Renders role-context skills the agent will need at runtime.
- **System prompt drafter.** First-cut system prompts based on the spec.
- **Markdown rendering.** Pulls everything together into a human-readable brief.

---

## Cross-cutting concerns

### Trace nesting
Every sub-agent call within a stage should record to the trace log with stage-id and sub-agent-id metadata. This way the existing Trace tab in the harness can collapse the view by stage and you can drill into "everything Stage 2 did" without scrolling through Stage 1's history.

### Per-stage configurable models
Stage 1 and Stage 4 likely benefit from a more capable model than Stage 2's tight sub-agents. Allow per-stage `model.name` config. v0: probably all the same model, but the architecture should support divergence.

### Conversation state
The user is a participant in Stages 1 and 2 (asked questions, gives answers). Not in Stages 3 and 4 (they run on captured data). UI should reflect that — show "Working…" indicators during 3 and 4, return to chat during 1 and 2.

### Failure modes worth designing for
- **User abandons mid-pipeline.** Persist state per session so they can resume.
- **A sub-agent errors out** (model unavailable, tool failure, malformed response). Catch and route to a graceful fallback per sub-agent. Most should be "log the error, mark that field as uncertain, continue."
- **User contradicts themselves between turns.** Gap finder should detect, ask which is correct, update bedrock log with the contradiction history.
