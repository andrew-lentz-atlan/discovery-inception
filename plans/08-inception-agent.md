# 06 — Inception Agent

**Status:** design — not yet built.
**Depends on:** `05-technical-thread-discovery.md` (richer spec), `06-atlan-context-integration.md` (bottom-up context), `07-patterns-knowledge-base.md` (decision-time knowledge).
**Closes the loop:** this is the "inception" half of discovery-inception that the name has been promising since day one.

---

## The problem this fixes

The discovery agent (with the technical thread on, with Atlan context primed) produces a spec.md that captures the conceptual + technical bounded context of a use case. Today, that spec gets handed to a human builder, who manually does the next several days of work:

- Reading the spec, extracting which skills the agent needs
- Deciding the architectural shape (single-agent loop / chained / planning-first / adversarial)
- Picking the runtime (Anthropic SDK / LangGraph / Pydantic AI / Deep Agents)
- Scaffolding the actual code — SKILL.md files, orchestrator stub, eval harness

Each of those decisions is doable by hand. They were all done by hand for the P&G case study. They're also all **procedural enough to be automated** — every one is the kind of thing that a small focused agent could draft, with a human reviewing rather than authoring.

That's inception. It's the half of the project the name has been promising since day one — *plant the agent design into the team's hands as something they can build forward from.* Without it, "agent that helps build other agents" stalls at the spec; with it, the spec becomes a starting agent design in minutes instead of days.

**The honest economic claim:** inception produces a 75/100 starter, not a 97/100 final. The 75 → 97 work is what the human builder iterates through, the same way Bala did. The win isn't that inception is as good as a human. The win is that the human's iteration time becomes 10× shorter because they're correcting a real candidate, not starting from a spec.

---

## Architecture

```
DiscoverySpec (spec.md + technical context)  +  BoundedContext (from Atlan)
                              │
                              ▼
                ┌─────────────────────────────┐
                │ workload_classifier         │
                │ — what shape of work is     │
                │   this? conversational?     │
                │   query-response? batch?    │
                │   long-horizon?             │
                └──────────────┬──────────────┘
                               │
                               ▼
              ┌────────────────────────────────┐
              │ skill_proposer ── skill_critic │   ← adversarial pair
              │ — reads decisions + workflow   │
              │   + gaps; proposes N skills    │
              │   with provenance              │
              └──────────────┬─────────────────┘
                             │
                             ▼
         ┌─────────────────────────────────────────┐
         │ architecture_proposer ── arch_critic    │   ← knows workload + skills
         │ — consults patterns/architectures/      │
         │ — names candidates, picks one + reason  │
         │ — specifies bake-off variables          │
         └──────────────┬──────────────────────────┘
                        │
                        ▼
         ┌──────────────────────────────────────────┐
         │ runtime_proposer                         │
         │ — consults patterns/harnesses/           │
         │ — matches arch shape to harness          │
         │ — estimates cross-runtime calibration    │
         └──────────────┬───────────────────────────┘
                        │
                        ▼
         ┌──────────────────────────────────────────┐
         │ scaffold_writer                          │
         │ — SKILL.md files per skill (provenance)  │
         │ — orchestrator stub                      │
         │ — eval question seed (10–15 questions)   │
         │ — LLM-as-judge harness scaffold          │
         └──────────────┬───────────────────────────┘
                        │
                        ▼
            agent_starter/                ← portable artifact ready for builder iteration
                ├── skills/
                │   ├── <skill-1>/SKILL.md
                │   └── ...
                ├── orchestrator.py
                ├── eval/
                │   ├── questions.json
                │   └── judge.py
                ├── README.md             ← how to run, where it'll fail, what to fix first
                └── design_rationale.md   ← every decision + the pattern that justified it
```

Six sub-agents, plus three optional critics. Each is one prompt + one Pydantic output type. The orchestration looks structurally similar to discovery: small focused calls, structured intermediates, deterministic close-out.

---

## Per-sub-agent design

### `workload_classifier`

**Inputs:** spec.md (conceptual + technical sections), BoundedContext.

**Outputs:** structured classification along several axes:
- `interaction_shape`: conversational | query-response | batch | streaming
- `latency_sensitivity`: real-time | near-real-time | tolerant
- `decision_complexity`: deterministic | rule-based | judgment-heavy
- `data_intensity`: light | moderate | heavy
- `multi_step_or_single_step`: single | multi
- `state_shape`: stateless | session-scoped | long-horizon

These axes determine which architectures and skill patterns are even candidates. A conversational workload doesn't want a chained pipeline; a batch workload doesn't need streaming; a heavy-data workload pushes toward inner-pipeline skills (Bala's pattern) over single-LLM-call skills.

**Patterns consulted:** `patterns/decision-guides/conversational-vs-query-response.md`, `batch-vs-interactive.md`.

### `skill_proposer` + `skill_critic`

**`skill_proposer` inputs:** workload classification + DiscoverySpec.

**Outputs:** proposed skills, each with:
- Name + purpose
- Inputs / outputs (Pydantic schemas)
- Data sources (from BoundedContext)
- Provenance: which DiscoverySpec entries justified this skill
- Granularity argument: why this is one skill not two, or two not one
- Owned decisions (which `decision_criteria` from the spec this skill encapsulates)

**`skill_critic` inputs:** the proposer's draft + DiscoverySpec.

**Outputs:** an adversarial review:
- Does each skill have one job? (anti-pattern: "god skill" that does many things)
- Does each skill trace to provenance? (anti-pattern: skills invented from intuition)
- Are skills decomposed at the right level? Should some merge? Should some split?
- Are there missing skills the spec implies but the proposer didn't surface?

Same shape as the discovery agent's probe-sharpener. The critic doesn't write the final draft — it produces scoring + suggested edits; the proposer (or human reviewer) decides whether to act.

**Patterns consulted:** `patterns/skill-design/one-question-one-source.md`, `single-llm-call.md`, `inner-pipeline.md`, `adversarial-review.md`.

### `architecture_proposer` + `arch_critic`

**`architecture_proposer` inputs:** workload classification + proposed skills.

**Outputs:**
- Top-3 candidate architectures (from `patterns/architectures/` filtered by workload)
- Selected architecture + justification citing pattern entries
- Rejected alternatives + rationale
- What variables would differ in a bake-off (the empirical-test specification)

The bake-off specification matters. The Andrew thesis from `findings/09` (when written) is: architecture choice is load-bearing and worth empirical validation. Inception should produce both the selected architecture AND the recipe for testing it against alternatives.

**`arch_critic` inputs:** proposer's selection + the workload + the skills.

**Outputs:** review along these axes:
- Does the workload-shape actually fit the selected architecture?
- Have all reasonable candidates been considered?
- Is the rejection reasoning empirical or asserted?
- Has anti-pattern advice been heeded?

**Patterns consulted:** all of `patterns/architectures/` and `patterns/decision-guides/`. This is the most pattern-dense sub-agent.

### `runtime_proposer`

**Inputs:** workload classification + skills + selected architecture + DiscoverySpec.technical_context.

**Outputs:**
- Selected runtime (harness from `patterns/harnesses/`)
- Rationale: why this runtime preserves the architectural shape with the fewest impositions
- Cross-boundary calibration estimate: what porting to one of the alternative runtimes would cost in prompt re-tuning (cite `patterns/anti-patterns/prompt-flavor-portability-blindness.md`)
- Constraints respected: the customer's existing tech-stack commitments from the spec
- Anti-patterns avoided: the runtime choice isn't bending to a constraint that shouldn't apply

**No critic for this one.** Runtime selection is opinion-light once architecture is settled — most opinionated work happens in architecture.

**Patterns consulted:** all of `patterns/harnesses/`.

### `scaffold_writer`

**Inputs:** everything above.

**Outputs:** a complete `agent_starter/` directory:

- **`skills/<skill-name>/SKILL.md`** — Anthropic skill-format file per skill. Includes purpose, inputs, outputs (Pydantic schemas in YAML), example invocation, and a one-paragraph implementation hint that references which `patterns/skill-design/` entry guided the design.
- **`orchestrator.py`** — minimal runnable stub matching the selected architecture. Imports the skills, sets up the agent loop, has TODO markers where customer-specific logic plugs in.
- **`eval/questions.json`** — 10–15 seed questions derived from the use case. For the P&G case, these would be variations on "Why did X lose share at Y?" with different brands, retailers, time periods.
- **`eval/judge.py`** — LLM-as-judge harness scaffold (cite Bala's pattern). Includes the 5 evaluation dimensions: quantitative accuracy, root-cause classification, hallucination check, reasoning quality, actionability.
- **`README.md`** — human-readable: how to run, where the obvious failure modes are, what to iterate on first.
- **`design_rationale.md`** — every decision + the pattern entry that justified it. Auditable. Editable. The thing a builder reads when they want to know *why* something was scaffolded the way it was.

This is where the agent_starter as a portable artifact becomes concrete. Like discovery's spec bundle, it's a deliverable not a process. The builder can take it, drop it into their project, iterate.

---

## How inception consumes patterns

This is the most pattern-dense agent in the system. Every architectural choice cites a pattern. Every skill-design choice cites a pattern. Every runtime choice cites a pattern.

Three integration shapes:

| Shape | Example |
|---|---|
| **Filter-based lookup** | `architecture_proposer` queries `patterns/architectures/` filtered by `applies_when.workloads contains workload_class.interaction_shape` |
| **Citation in output** | Every decision in `design_rationale.md` cites `[patterns/category/entry.md]` — auditable trail |
| **Adversarial-pair consultation** | The critics also consult patterns — anti-patterns specifically. Critic flags "this proposal violates `patterns/anti-patterns/definitions-without-context.md`" |

The consequence: when patterns get updated (lint pass identifies a new anti-pattern, or a new harness ships), inception's behavior updates automatically. No prompt rewrites in inception's sub-agents.

---

## Output contract — what a complete `agent_starter/` looks like

For the P&G case (as a worked example):

```
agent_starter/
├── README.md                              ← "Bring this up against synthetic data first. Calibrate against
│                                            real data. Expect to iterate on the narrative voice in
│                                            report_skill. BCA framework comes from Atlan glossary."
├── design_rationale.md                    ← every choice + pattern citation
├── skills/
│   ├── question_parser/
│   │   ├── SKILL.md                      ← cites patterns/skill-design/one-question-one-source.md
│   │   └── stub.py                       ← function signature, TODO for impl
│   ├── market_share_analyzer/
│   │   └── SKILL.md                      ← cites patterns/skill-design/inner-pipeline.md
│   ├── root_cause_analyzer/
│   │   └── SKILL.md                      ← cites patterns/skill-design/inner-pipeline.md,
│   │                                            patterns/lessons-from-builders/bala-bca-framework-must-travel.md
│   └── narrative_report/
│       └── SKILL.md
├── orchestrator.py                        ← single-agent ReAct (claude-opus-4-7), 4 tools bound
├── eval/
│   ├── questions.json                    ← 12 P&G-shaped questions
│   └── judge.py                          ← LLM-as-judge with 5 dimensions
└── meta/
    ├── spec_consumed.md                  ← which spec.md fed this
    ├── bounded_context_consumed.md       ← which Atlan context fed this
    ├── patterns_consulted.md             ← every pattern cited, with version
    └── alternative_architectures.md      ← the rejected candidates + bake-off recipe
```

**Critical:** the `meta/` directory is part of what makes the artifact defensible. A builder picking this up doesn't just get code — they get the audit trail of how the design was decided. If their iteration leads them to a different architecture, they can read `alternative_architectures.md` and see what the rejected candidates were.

---

## Validating against the P&G ground truth

The P&G case study is the natural validation:

1. Feed inception the oriented RoleContext from the discovery run (`skills/p-and-g-fhc-analyst-oriented/context.json`)
2. Capture inception's `agent_starter/` output
3. Compare against:
   - **Bala's actual implementation** (independent end-to-end build, 97/100 LLM-as-judge score)
   - **My manual v2 design** (`agent_skills_v2.md` derived from the same RoleContext)

Expected outcomes:

| Inception output landed on | Bala built | Manual v2 had |
|---|---|---|
| 4 skills | 3 skills | 4 skills |
| Single-agent ReAct architecture | Single-agent ReAct architecture | Single-agent ReAct architecture |
| Anthropic SDK runtime | Anthropic SDK runtime | Anthropic SDK runtime |
| BCA framework via Atlan | BCA framework via Atlan | (manually identified BCA from Bala's repo) |
| `bca_framework` travels with diagnosis | Yes (cites Bala's lesson) | (manually noted as a key learning) |
| Eval seed questions | (not in Bala's repo) | (referenced as a need) |

If inception's output materially matches Bala's empirical design (without ever seeing Bala's repo) and includes the empirical lessons (via `patterns/lessons-from-builders/`), that's the validation.

If inception diverges in defensible ways (e.g., proposes 4 skills with a `question_parser` separation where Bala used 3), the divergence is the interesting story — *here's where the priors-derived design proposes a different cut, and here's the empirical question of which performs better.*

---

## Open questions

1. **How much should the critic agents pressure-test back into the proposer's loop?** Discovery's probe-sharpener replaces 50% of probes; that's a lot of trust in adversarial review. For inception, we probably want LESS automatic replacement — critics produce review notes, proposer decides. Strong defaults, weak enforcement.
2. **Should `scaffold_writer` produce runnable code or just templates with TODOs?** Lean: runnable on synthetic data with provided judge questions; TODOs for customer-specific impl details (auth, real data, brand voice). The builder boots it and runs end-to-end on day one, then iterates.
3. **What's the right depth of `design_rationale.md`?** Verbose (every decision documented) vs concise (only the load-bearing ones). Lean verbose for v1 — the audit trail is the differentiator. Trim later if it's noise.
4. **How does inception handle ambiguity in the spec?** If the spec says "either Databricks or Snowflake," does inception pick one? Or scaffold for both? Lean: pick the one the BoundedContext suggests is established; if no signal, scaffold for the workload-agnostic case + flag the choice in `design_rationale.md` for builder review.
5. **Should inception have its own discovery flow?** I.e., if the spec is missing critical technical info, does inception ask the user, or fall back to its best guess? Lean: best-guess + flag for v1; loop back to a richer discovery if validation shows guesses are wrong too often.
6. **How does inception evolve as patterns evolve?** The point of patterns is decoupling. As entries change, inception's outputs change. We need versioning visible in outputs — `design_rationale.md` should cite patterns with their version/date, so a builder reading the rationale months later knows what knowledge state produced it.

---

## Implementation sequence

1. **Workload classifier sub-agent** (prompt + schema + step). Validate by feeding it the P&G spec and confirming the classification axes match what a human would say.
2. **Skill proposer sub-agent** (no critic yet — start with single agent). Validate against my manual v2 cut.
3. **Architecture proposer sub-agent** (consume `patterns/architectures/`). Validate against Bala's choice + my manual analysis.
4. **Runtime proposer sub-agent** (consume `patterns/harnesses/`). Validate against Bala's Anthropic SDK choice.
5. **Scaffold writer sub-agent** (most complex; templates + Pydantic + jinja or similar). Validate by running the scaffolded P&G agent on synthetic data; expect 70/100 first-pass score.
6. **Adversarial critics** (skill_critic, arch_critic). Validate by re-running inception with critics on; should reduce errors caught by manual review.
7. **Empirical comparison run** — inception output vs Bala's repo vs my manual v2. Document as `findings/NN-inception-validation-on-pg.md`.

Estimated 1–2 weeks of focused work. Builds on the patterns library (`05`) and assumes the technical-thread discovery (`03`) + Atlan integration (`04`) are producing the richer spec.

---

## What this doesn't do (scope boundaries)

- **Doesn't implement the skills.** Scaffolds with TODO markers. Builder fills in the customer-specific impl.
- **Doesn't fine-tune models.** Agnostic about model family within the constraints the spec captures.
- **Doesn't enforce the bake-off.** Specifies the recipe; doesn't run it. Running the bake-off is a separate workflow.
- **Doesn't write Atlan glossary entries.** That's `context_repo_gaps.md` from discovery (`03`). Inception consumes the gaps but doesn't push them back.
- **Doesn't promise quality above the 75/100 floor.** Specifically claims the win is on *iteration speed*, not on first-pass quality.

---

## The headline economic claim, restated

> Inception produces a 75/100 starter. The human builder iterates that to 97/100 — same way Bala iterated his initial draft to 97. The win is that the iteration starts from a real candidate with documented design rationale, not from a spec + a blank IDE.

Time saved: from "scope a P&G-shaped agent build" being 2–3 weeks of senior engineering work to being 2–3 days of starter-review-and-iteration work. That's the agent that helps build other agents. Not a magic 100/100 generator; a structural acceleration of the existing translation work.
