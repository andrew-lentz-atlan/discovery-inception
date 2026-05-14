# v0.8: probe-sharpener post-processor + tensions surfacing

**Status:** Research note. n=1 use case (TechCo Sales Pipeline Analyst, 50 turns). Same script as v0.7.
**Date:** 2026-05-13
**Repo:** https://github.com/andrew-lentz-atlan/discovery-inception
**Sessions:**
- v0.7: `sess_aa0de4a3f5bc`
- v0.8: `sess_483c55604289`

---

## TL;DR

Four architectural additions in v0.8 designed to push the agent's questioning from B+ to A:

1. **Probe-sharpener post-processor.** Adversarial sub-agent reviews every mega-agent response. Scores it 1-5 on novelty / extension / provenance-pressure / tension-surfacing (max 20). Scores ≤10 = rewrite; 11-15 = ship as-is; 16+ = sharp. The mega-agent's draft is replaced with the rewrite when the sharpener flags it as weak.
2. **Number-provenance discipline in mega prompt.** Explicit rule: when the customer states any number (rate, percentage, count, duration), the next probe MUST pressure-test provenance — *"is that your median, worst-case, who maintains it, when last measured?"*
3. **Tensions detection in synthesizer.** Synthesizer now produces `internal_tensions` alongside the working theory — 0-3 one-sentence statements naming where two prior facts implicitly conflict.
4. **`find_tensions` tool.** Fourth tool the mega-agent can call when it suspects something doesn't add up. Lazy invocation; cheaper than full synthesis.

Re-ran the same 50-turn Sales Pipeline Analyst script on v0.7 and v0.8 head-to-head:

| Metric | v0.7 | v0.8 |
|---|---|---|
| Wall time | 549s | **671s (+22%)** |
| Mega input tokens | 732K | **540K (-26%)** |
| Mega output tokens | 14.4K | **8.0K (-45%)** |
| Topics captured | 22 | 21 |
| Facts captured | 38 | **44 (+16%)** |
| Gaps flagged | 1 | 1 |
| Working-theory candidate framings | 3 | **4** |
| Working-theory internal tensions surfaced | 0 (no field) | **3** |
| Sharpener runs | n/a | 49 / 50 turns |
| Sharpener rewrites | n/a | **27 / 49 (55%)** |
| Sharpener score avg | n/a | 11.6 / 20 |
| Sharpener score range | n/a | 6–19 |

The 55% rewrite rate is the headline. **More than half of v0.7's probes were below the sharpener's "ships as-is" threshold.** The previous version's questioning was genuinely weaker than the rubric considers acceptable.

---

## What's surprising about the cost picture

Going in I expected v0.8 to use *more* tokens because of the added sharpener calls. The opposite happened:

- Sharpener added ~100-150K tokens in additional sub-agent calls (49 invocations × ~2-3K each)
- Mega-agent's own token usage dropped 26% on input, 45% on output
- **Net: roughly flat or slightly less total token cost vs v0.7**

Why? The sharpener's rewrites are tighter than the mega-agent's drafts. When a rewrite replaces the draft in conversation history, subsequent turns load less context. This compounds — the sharpener cuts both directly (the response is shorter) and structurally (future turns see less bloat). Wall time is 22% longer because of sequential sub-agent latency, but token economics are flat.

---

## Per-turn quality (sampled, my read)

Compared two load-bearing turns side by side:

### Turn 14 — Persona-specific must-NOT-knows

Customer: *"AEs hate seeing peer comparisons. SDRs hate seeing ARR forecasting — they don't care, it's not their job. Sales Managers hate seeing roll-up summaries that don't break out by sub-region..."*

**v0.7 probe** (clean playback, listed the personas as a bullet mapping):
> *"So it's not just access control — it's active curation. Let me make sure I have the mapping right: AEs: no peer comparisons. SDRs: no ARR forecasting..."*

**v0.8 probe** (sharpener score: 6 → rewritten):
> *"When an AE manager asks for rolled-up coverage instead of sub-regional, are they asking for their own team's total in isolation, or are they asking for their team's total so they can mentally compare it to peer managers' totals? Because if it's the latter, you've got a collision: they want the rolled-up view to see their wins, but your anti-goal says never show comparative context outside the reporting line."*

The v0.8 version is genuinely sharper — surfaces an implicit tension between the manager's stated desire and the anti-goal that wasn't visible in the customer's own statement. **Sharpener earned its keep on this turn.**

### Turn 30 — The $7M miss case study

Customer dumped 250+ words on a real failure.

**v0.7 probe** (good summary):
> *"That's the story that justifies the whole thing. The agent's job is to make that $7M miss impossible by catching those patterns before they contaminate the forecast..."*

**v0.8 probe** (sharpener score: 10 → rewritten):
> *"You said the CFO used the $18M for board reporting and had to explain a $7M miss. If the agent had instead reported '$11M ± $3M with 70% confidence' that day, does that solve the CFO's problem, or does the board still see a miss because the point estimate was still $3M off? In other words: is the real failure that the dashboard gave a false point estimate, or that it couldn't surface why the $18M was uncertain?"*

The v0.8 version asks a question the customer hadn't asked themselves — *is the failure mode the number or the reasoning?* That's the kind of probe a senior FDE would ask. **Sharpener again clearly improved this.**

### Turn 49 — Closing reflection

Customer: *"What would make this discovery successful from my side: I leave this with a clear enough picture that a builder doesn't have to come back to me with a hundred follow-up questions..."*

**v0.7 probe** (domain-knowledge checklist run-through):
> *"Discovery succeeds if the builder can ship v1 without coming back. Let me do a final check: Domain knowledge captured: ✅ Q4 inflation, ✅ procurement slip signal..."*

**v0.8 probe** (sharpener score: 19 → ships as-is):
> *"You've given me enough that a builder can start. But there are three things that still need to be nailed down with Lisa before the builder can ship v1 without guessing: First: the procurement slip rate interaction. You said 70% slip rate on procurement-involved deals at $1.2M ARR. But you also said Strategic stage-3 deals inflate quarterly while Mid-Market discovery deals inflate monthly..."*

The v0.8 closing surfaces specific tensions that need Lisa's input AND ties them to the procurement signal. More specific than v0.7's checklist. **Ships at score 19** — sharp by the rubric's standards.

---

## Internal tensions — what the synthesizer surfaced

The new `internal_tensions` field on `WorkingTheory` produced 3 tensions at session close:

1. *"Customer flagged that Strategic AEs inflate quarterly while Mid-Market inflate monthly, and that slip rates depend on stage and deal staleness, BUT the 70% procurement-slip rate was stated as a single number across all segments and stages. Either procurement signal is more universal than the other patterns, or it should also be segment-conditioned and we haven't drawn that out."*
2. *"Customer emphasized 'trust the answers' and data governance (Salesforce as source of truth, Snowflake as analytical layer, continuous data quality monitoring) BUT has not specified what constitutes a data quality threshold worth alerting on..."*
3. *"Customer listed 5 escalation rules (forecast variance, data quality issues, deal anomalies, close-date integrity, account assignment) and 3 anti-goals (no auto-update to Salesforce, no autonomous deal..."*

These are real tensions a senior FDE would surface. The fact that they made it into the structured spec means they're now in the artifact for the builder to address. **Tensions surfacing works as designed.**

---

## What didn't change much

- **Tool invocation count was about the same** (2 expensive synth/tensions calls in each run). The mega prompt's explicit triggers ("synth after long answers," "find_tensions after contradictions," etc.) didn't dramatically change behavior. The mega-agent is still conservative about tool use. Cheap state-reads (`get_current_spec_state`, `get_checklist_progress`) went from 4 in v0.7 to 6 in v0.8 — modest improvement.
- **Topic count was roughly equal** (22 vs 21) — coverage breadth held.
- **Working-theory framing** at close became slightly more generic in v0.8. v0.7's framing named specific patterns (procurement, NPS-CS gate, Lisa). v0.8's is broader. Possibly because the sharpener's tension-pushing got the synthesizer thinking at a higher abstraction level. Slight loss; minor.

---

## The "you said X but you also said Y" pattern

Reading the late-turn v0.8 outputs, a clear pattern emerged: the sharpener's rewrites repeatedly use *"You said X. But you also said Y."* as the entry to a tension. This is the right move on its own — but **it shows up in maybe 40% of late-turn rewrites**, which makes the rhythm feel formulaic over a 50-turn arc.

In a real discovery this would read as the agent having a tic. Two ways to address in a v0.9:

1. **Variation library** in the sharpener prompt — provide 5-6 different opening framings for surfacing tensions, instruct it to vary across turns.
2. **Track recent openers** — give the sharpener visibility into the last 3 probe openings, instruct it to vary.

Cheap to fix. Not load-bearing for the meeting prep, but worth doing before sharing widely.

---

## What this means for the architectural thesis

v0.8 is another data point on what *"decomposition is load-bearing for structured output and quality, not for fluency"* really means in practice. Specifically:

- The mega-agent (one strong prompt, single call) handles fluency. v0.7's mega-agent produced grammatically natural, customer-vocabulary-aligned responses on every turn.
- The sharpener (separate sub-agent, adversarial role) handles quality. v0.7's mega-agent did the *fluency* part well but produced probes that were below the rubric's quality bar 55% of the time. Adding a second pass with a sharper, more focused prompt caught those.
- The tensions detection (separate sub-agent) handles a *specific* cognitive task the mega-agent didn't do naturally. Synthesizer alone never surfaced tensions; with the extension, 3 tensions made it into the final spec.

In all three cases, the win is **adversarial decomposition** — a second sub-agent whose job is to be skeptical of the first one. Not "do part of the task and the rest goes to the next sub-agent" (which was the original v0.5/v0.6 decomposition story), but "do the task and then have someone else check it." That's a different architectural pattern than what we explored in earlier findings.

---

## Honest grade

Going by my own grade scale from yesterday:

- v0.7: B+
- v0.8: **A−**

Not A because: the "you said X but Y" pattern repeats too often and starts to feel tic-y in late turns. The tool-use triggers didn't move the needle much — agent still under-uses expensive tools.

Not A+ because: still no moments where the agent surprises with a *constructive* insight (most rewrites surface tensions in what the customer SAID; very few extend it with a hypothesis the customer didn't volunteer).

But the structural quality lift is real and measurable. 55% of probes were below threshold and got improved. The architecture's working as designed.

---

## Caveats (carrying over from earlier findings)

- **n=1 use case.** Same TechCo Sales Pipeline Analyst script. Doesn't generalize automatically.
- **Single model.** Haiku-4-5 for everything.
- **Subjective per-turn quality assessment.** I (one human) reviewed sampled turns.
- **The customer script was pre-written.** A real customer would be messier; some of v0.8's tension-surfacing depends on customer statements being unambiguous enough that tensions are detectable. Real customers hedge and mumble in ways that hide tensions.

---

## What we'd do next

1. **Variation library for the sharpener** — fix the "you said X but Y" tic. ~30 min.
2. **Run v0.8 on a fundamentally different use case** (axis 1 from the roadmap). Validates the sharpener generalizes off this domain.
3. **Test v0.7 vs v0.8 on a 25-turn or 10-turn script.** This 50-turn comparison showed quality + token wins; want to know whether the same holds at shorter lengths.

---

## Reproducibility

```bash
cd discovery-inception
uv run python -m agent.baselines.run_v08_solo \
    --script agent/baselines/scripts/sales_analyst_50turn.json
```

Output: `sessions/<id>/spec.md` + `spec.json` + `session.json`. The session.json contains every sharpener event with full scores, rewrites, and weakness diagnoses.
