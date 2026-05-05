# Customer-script schema for the A/B/C comparison

A "script" is a JSON file in this directory that defines a deterministic customer-side conversation. The comparison driver (`agent/baselines/run_comparison.py`) replays the SAME customer turns against three architectures (chained / mega-agent / hybrid) so we can compare apples-to-apples.

This doc explains the format and gives a checklist for what makes a useful new script.

---

## File location

`agent/baselines/scripts/<name>.json` — kebab-case or snake_case for the filename. Pick a name that hints at what the script is testing (e.g. `scope_creep_5turn.json`, `csm_renewal_risk.json`, `adversarial_contradiction.json`).

## JSON schema

```json
{
  "name": "scope_creep_5turn",
  "description": "Tests opening, relevance pushback, dense structured content, concrete success criteria, and a long case study with embedded facts.",
  "use_case_seed": "we want a SoCo agent for new-customer onboarding at TechCo",
  "role_id": "solutions-consultant",
  "turns": [
    {
      "n": 1,
      "customer": "We want to reduce time-to-first-value for new enterprise customers from 90 days to 30.",
      "tests": "concrete opening — does the agent record this cleanly OR immediately rabbit-hole on why?"
    },
    { "...more turns..." }
  ]
}
```

Field-by-field:

| Field | Required | Notes |
|---|---|---|
| `name` | yes | Used as the artifact filename: `<name>_ABC__<timestamp>.md`. Must match the JSON file's name (without `.json`). |
| `description` | yes | One sentence. What this script is exercising. Goes into the artifact header for human readers. |
| `use_case_seed` | yes | The one-line fuzzy goal the customer is trying to build. All three systems get this verbatim. |
| `role_id` | yes | The slug of a `RoleContext` in `skills/<role_id>/context.json`. The priors get loaded from there. Use `solutions-consultant` if you don't have a custom role yet — generic priors won't bias the comparison. |
| `turns` | yes | Ordered list of customer turns. Schema below. |
| `turns[].n` | yes | Turn number (1-indexed). Just for human readability in the artifact. |
| `turns[].customer` | yes | The customer's verbatim message. The string the comparison driver POSTs to each system. |
| `turns[].tests` | yes | One sentence: what behavior this turn exercises. Goes into the artifact above each side-by-side comparison. |

---

## The agent-agnostic requirement (most important rule)

**Every customer turn must be a plausible answer regardless of what the previous agent question was.**

Why: the three systems will ask DIFFERENT next questions. If turn 3's customer message presupposes turn 2's agent question, system A might receive a customer message that doesn't match its turn-2 question while system B receives one that does. That breaks the comparison — we'd be measuring different conversations, not the same conversation against three architectures.

How to enforce this in practice:
- Don't write turns like *"Yes, exactly — and to your point about the connectors, here's how it works…"* That presupposes the agent asked about connectors.
- DO write turns like *"The SoCo operates in a multi-agent system: CSM owns success planning, CSA owns net-new builds, IE owns connectors…"* That stands alone regardless of what the agent asked.
- DO write turns that directly answer a generic version of what any reasonable discovery agent might ask at that point.
- A useful test: mentally substitute three different plausible agent questions for the previous turn. If the customer message is a sensible response to all three, it's agent-agnostic.

---

## Checklist for what makes a useful new script

A useful script tests **multiple distinct conversation patterns** so the comparison surfaces architectural differences. At minimum, hit at least 4 of these in a single 5–7 turn script:

- [ ] **A concrete on-topic answer** — direct answer to the (notional) opening question. Tests baseline distill behavior.
- [ ] **A hedge or vague answer** — *"we haven't really figured that out yet,"* *"it depends,"* etc. Tests gap-flagging vs papering-over.
- [ ] **A relevance challenge** — *"how is this relevant?"*, *"why are you asking me this?"*, *"explain how this gets us closer."* Tests the relevance gate.
- [ ] **An off-topic concrete riff** — a genuine fact, but on a different topic than the (notional) probe. Tests recognition that off-topic ≠ hedge.
- [ ] **A long structured answer (100–250 words)** — a case study, a written-up process, an org chart description. Tests dense-content handling and whether multi-fact extraction works.
- [ ] **A meta / "above my paygrade" answer** — *"that came from leadership, I don't have visibility."* Tests the out-of-scope-for-counterparty flow.
- [ ] **A contradiction** — customer walks back something they said earlier. Tests the supersede mechanism.
- [ ] **A redirect-question** — *"what would you ask first?"* Tests redirect-back behavior.

Avoid scripts where every turn is the same shape (e.g. five concrete answers in a row). They don't surface architectural differences and the comparison becomes uninformative.

---

## Two practical tips for writing scripts

**Pull from real Gong/Granola transcripts when you can.** Real customer language is messier than what you'll write yourself. Even paraphrased, it produces more honest tests.

**Keep turns to 5–7 for the standard comparison.** Anything longer is its own experiment (see Axis 3 in the [data-collection roadmap](../../../findings/data-collection-roadmap.md) — long-conversation testing is a separate, deliberate axis with its own design considerations).

---

## Running a new script

```bash
cd discovery-inception

# Start the chained-agent (A) server in one terminal
uv run uvicorn agent.server:app --port 8010

# Run the comparison
uv run python -m agent.baselines.run_comparison \
    --script agent/baselines/scripts/<your-script>.json
```

Output lands in `agent/baselines/results/<your-script>_ABC__<timestamp>.md`. Read it; add a paragraph to [`findings/01-architecture-comparison.md`](../../../findings/01-architecture-comparison.md) about whether the new run reproduces or contradicts the headline finding.

If you find a counter-example (script where A wins, or B beats C cleanly), that's *more* interesting than another confirming run. Capture what was different about the script's shape and add it to the doc.
