---
name: discovery-inception
description: |
  Set up and run discovery-inception — a two-stage agent system for
  building other agents. Stage 1 (discovery) is an artifact-first
  context-ingestion product that turns call transcripts, runbooks, docs,
  and (optionally) a live conversation into a structured spec. Stage 2
  (inception) turns that spec into a complete starter agent design:
  proposed skills, selected architecture, runtime + model selection,
  scaffolded orchestrator code, evaluation seed, and judge harness.
  Use when the user asks to test, try, or use discovery-inception, OR
  when the user says they have a call/transcript/doc they want to turn
  into an agent spec, OR when they want to figure out what an agent build
  for some use case would look like, OR when they have a spec and want a
  starter agent scaffolded. The skill handles repo cloning, dependency
  install, credential setup, multi-artifact ingest, chat-fill of gaps the
  FDE already knows the answer to, optional live discovery interview for
  the gaps that need a real customer answer, and the inception pipeline
  that produces the starter agent. Final deliverable is a spec.md + an
  agent_starter/ directory the user can iterate on.
---

# discovery-inception — install, set up, and run end-to-end

You are guiding the user through discovery-inception, a two-stage system for building agents:

- **Discovery** turns unstructured customer context (call transcripts, docs, runbooks, slack threads) into a structured spec. Conversational "interview the customer" mode is still available but is **not** the first thing the user does — most real flows start with artifacts in hand.
- **Inception** turns that spec into a complete starter agent design — proposed skills, selected architecture (e.g. single-agent ReAct vs chained pipeline), runtime + model selection, scaffolded orchestrator code, eval seed, judge harness. Six sub-agents run end-to-end; takes 3–5 minutes.

The full happy path is:

```
artifacts → ingest → gap_list.md → chat-fill known gaps
                                  → (optional) interview unknown gaps
                                  → finalize → spec.md + spec.json
                                  → inception → agent_starter/
```

Most colleagues testing for the first time will want to run the full pipeline. Some will stop at spec.md. Either is valid; lead the user through Phases 1–5 first, then ask if they want to continue into Phase 6 (inception).

Two entry shapes for the discovery half:

| Shape | When the user picks this |
|---|---|
| **Artifact-first (recommended default)** | The user has *anything* in hand — a transcript, a runbook, an internal doc, a slack thread, even just a pasted email. Even one artifact is enough to start. |
| **Interview-first (fallback)** | The user has zero artifacts and wants to interview a person (themselves playing customer, OR a real customer). |

The artifact-first flow takes the artifacts → produces facts + a gap list → the FDE either chat-fills the gaps they know, or runs a live discovery against the gaps that need a real answer. Most flows are a hybrid: ingest, chat-fill what's known, interview what isn't.

Repo: https://github.com/andrew-lentz-atlan/discovery-inception

Walk the user through the phases below. Don't skip — if the user already did some setup, verify cleanly before assuming.

---

## Phase 0 — Read the room

Before any commands, parse the user's initial message for:

- **A use case** (*"churn-prediction agent at FinCo"*) — confirm or refine
- **Mentions of artifacts** (*"I have the call transcript"*, *"here's the JD"*, *"we ran two scoping sessions"*) — note the count; you'll collect them in Phase 3
- **Path preferences** for the repo
- **An Atlan tenant they want primed** (e.g., *"I want this to read from our `ces.atlan.com` glossary"*)

If any of those are present, note them and don't re-ask in later phases.

---

## Phase 1 — Repo setup (one-time)

1. Check the common locations for an existing clone:

   ```bash
   for d in ~/Desktop/discovery-inception ~/code/discovery-inception ~/discovery-inception ~/projects/discovery-inception; do
     if [ -d "$d/.git" ]; then echo "FOUND: $d"; break; fi
   done
   ```

2. If found, ask: *"I see a clone at `<path>`. Use that, or clone fresh?"* Default to using what's there.

3. If not found, ask where to clone (default `~/Desktop/discovery-inception`), then clone and pin to the latest released tag so the user gets a known-good version:

   ```bash
   git clone https://github.com/andrew-lentz-atlan/discovery-inception.git <path>
   cd <path>
   latest_tag=$(git tag -l 'v*' --sort=-v:refname | head -1)
   if [ -n "$latest_tag" ]; then
     echo "checking out $latest_tag"
     git checkout "$latest_tag"
   fi
   ```

   If the user already had a clone, offer to update them to the latest tag.

4. From now on, refer to the chosen path as `$REPO`. Every Bash command in subsequent phases should `cd "$REPO"` first.

5. Run dependency sync:

   ```bash
   cd "$REPO" && uv sync
   ```

   ~30 seconds the first time. Surface any errors verbatim.

---

## Phase 2 — Credentials

1. Check whether `$REPO/.env` exists with `LITELLM_BASE_URL` and `LITELLM_API_KEY`:

   ```bash
   if [ -f "$REPO/.env" ] && grep -q "LITELLM_BASE_URL" "$REPO/.env" && grep -q "LITELLM_API_KEY" "$REPO/.env"; then
     echo "creds present"
   else
     echo "creds missing"
   fi
   ```

2. If missing, prompt:

   > To run discovery-inception you need Atlan LiteLLM proxy credentials.
   > - **`LITELLM_BASE_URL`** is `https://llmproxy.atlan.dev`
   > - **`LITELLM_API_KEY`** is your personal proxy key. Get it from the Atlan LiteLLM admin, or DM Andrew if you don't have one yet.
   >
   > Paste your API key and I'll write the `.env` for you.

3. Once provided, write the `.env`:

   ```bash
   cat > "$REPO/.env" <<'EOF'
   LITELLM_BASE_URL=https://llmproxy.atlan.dev
   LITELLM_API_KEY=<user_provided_key>
   EOF
   ```

   Verify: `python -c "from dotenv import dotenv_values; v=dotenv_values('$REPO/.env'); assert v.get('LITELLM_API_KEY'); print('ok')"`

---

## Phase 3 — Use case + artifact collection + Atlan context

1. **Confirm the use case** (one-line description of what the customer wants to build):

   > What use case are we working on? One line, e.g. *"a SoCo coordinator agent for new-customer onboarding at TechCo"* or *"a renewal-risk agent for our CSM team at FinCo"*.

2. **Always ask about Atlan context** (this is load-bearing — most agents being built will eventually read from a customer's Atlan tenant; priming discovery with what's already cataloged sharpens probes immediately):

   > Quick context-priming question: do you have an Atlan tenant we should prime discovery from? Naming the tenant + scope lets discovery skip questions Atlan already knows the answer to (glossary terms, table schemas, lineage, ownership, governance tags, business domains).
   >
   > Three answers work:
   > - **Yes, here are the details:** name the tenant (e.g. `ces.atlan.com`) + at least one of: glossary name, list of table QNs, list of DataDomain names. If you can paste an `ATLAN_API_KEY` with read scope right now, even better; if not, name the scope anyway and we'll surface the gap in the gap list.
   > - **Yes but I don't have credentials handy right now:** we'll proceed without it; you can re-run later with `--atlan-tenant`.
   > - **No tenant for this use case** (e.g., prospect / pre-sale / generic exploration): we'll proceed with the artifact-first flow and the technical thread will probe via questioning.
   >
   > Which?

   If the user provides Atlan creds, append to `.env`:

   ```bash
   cat >> "$REPO/.env" <<'EOF'
   ATLAN_BASE_URL=https://<their-tenant>
   ATLAN_API_KEY=<their_atlan_api_key>
   EOF
   ```

   Capture whatever they named (tenant + glossary + tables + domains) so the ingest command in step 4 can pass them as flags. If they only name partial scope (tenant + glossary but no tables), still pass what they have — partial scope priming is better than none.

3. **Collect artifacts** — this is the recommended path:

   > Do you have any artifacts to feed in? Things that count:
   > - Call transcripts (raw text or paraphrased notes)
   > - Job descriptions for the role this agent augments
   > - Runbooks, playbooks, success-plan templates
   > - Slack threads
   > - Customer-facing docs about the workflow
   > - Even a paragraph you pasted from a Granola summary
   >
   > Paste each one inline, OR give me file paths. Even one artifact is enough to start.
   >
   > *If you genuinely have nothing*, say "no artifacts" and we'll go to interview-first mode.

4. **If the user provides artifacts**, write each one to a temp file (so long ones don't shell-escape badly), then run multi-artifact ingest. Pass the Atlan scope flags from step 2 if they named any:

   ```bash
   cd "$REPO" && uv run python -m agent.cli ingest \
       --use-case-seed "<one-line use case>" \
       --role-id "<kebab-case slug, e.g. soco-techco>" \
       --artifact /path/to/artifact-1.txt \
       --artifact /path/to/artifact-2.md \
       # Pass these only if the user named them in step 2:
       --atlan-tenant ces.atlan.com \
       --atlan-glossary Fabric_Care_Analytics \
       --atlan-tables "default.aos,default.ddm"
   ```

   This takes ~30-60 seconds (intake + fact extraction run in parallel per artifact). If Atlan flags were passed, the established-context fetch runs at session start (read-only). The CLI prints JSON with `session_id`, `n_facts_captured`, `n_topics_covered`, `n_flagged_unknowns`, `gap_list_path`. **Capture the `session_id`** — every subsequent command needs it.

5. **Read the gap_list.md** and surface a summary:

   ```bash
   cat "$REPO/sessions/<session_id>/gap_list.md"
   ```

   Tell the user (briefly — don't dump the whole file):

   > Ingested. **<N>** facts captured across **<M>** topics. Gap list at `sessions/<session_id>/gap_list.md`.
   >
   > Covered: [list of topics with at least 1 fact]
   >
   > Missing (still need answers for): [list of canonical topics with 0 facts, by thread]
   >
   > Plus **<K>** source-flagged probes (specific things the artifacts didn't cover but you'd want to ask).
   >
   > How do you want to handle the gaps? Three options:
   > 1. **You answer them yourself** (chat-fill) — fastest, FDE-as-customer
   > 2. **Run a live interview** — for gaps that need a real customer answer
   > 3. **Hybrid** — chat-fill what you know, interview what you don't
   > 4. **Already enough** — finalize and produce spec.md

6. **If the user said "no artifacts"** in step 3, skip ingest and start an interview-only session:

   ```bash
   cd "$REPO" && uv run python -m agent.cli start-session \
       --use-case-seed "<use case>"
   ```

   Capture the `session_id` and go straight to Phase 5 in interview mode.

---

## Phase 4 — Close the gaps

This is the loop. The user picks a mode per turn; you don't have to commit to one for the whole session.

### Chat-fill mode (FDE answers a known gap)

When the user knows the answer to a gap — they were on the call, they wrote the runbook, they've done this 10 times before — they chat-fill it. The fact gets captured; no follow-up question is generated.

```bash
cd "$REPO" && uv run python -m agent.cli submit-turn --no-probe \
    --session-id "<session_id>" \
    --message "<the FDE's answer, phrased as if the customer said it>"
```

The message should be **phrased as if the customer said it** — first-person, concrete. The system treats the FDE's confident answer as fact (`stated` source), same as if the customer had said it in a call. *That's the FDE's job — to decide what's fact.*

Each chat-fill takes ~4-5 seconds. Encourage the user to chain several in a row when filling related gaps.

### Interview mode (the user plays customer, OR a real customer responds)

For gaps where the user genuinely doesn't know the answer, they need to interview someone. Same CLI as before, no `--no-probe`:

```bash
cd "$REPO" && uv run python -m agent.cli submit-turn \
    --session-id "<session_id>" \
    --message "<the customer's response>"
```

Each interview turn takes ~10-20 seconds (mega-agent + probe-sharpener run on top of triage + distill). The agent emits the next question; you relay it verbatim and wait for the user.

**Important framing rule:** if the user is going to a real customer with these questions, the user is the FDE — the conversation in this skill is them filling in answers AFTER the real call. In interview mode here, they play customer for ergonomics; they can switch back to chat-fill once they have an answer.

### Inspect state at any time

The user can ask *"what do we have so far"* or *"what's still missing"* — answer by re-reading `gap_list.md` (it's static from ingest) OR running:

```bash
cd "$REPO" && uv run python -m agent.cli state --session-id "<session_id>"
```

Summarize the working theory + how many canonical topics are covered + remaining gaps.

### When to stop

Stop when one of:
- The user says *"finalize"*, *"wrap up"*, *"we're done"*, etc.
- The `checklist_missing` field is empty or near-empty
- The user explicitly says they want to move to inception

---

## Phase 5 — Finalize and show the spec

1. Run the close-out:

   ```bash
   cd "$REPO" && uv run python -m agent.cli finalize --session-id "<session_id>"
   ```

2. Read the rendered spec:

   ```bash
   cat "$REPO/sessions/<session_id>/spec.md"
   ```

3. Show the user the rendered spec verbatim. Then briefly summarize:

   > Discovery wrapped. Spec at `<path>`. Final working theory confidence: `<level>`. **<N>** topics captured, **<M>** facts, **<K>** gaps flagged for FDE follow-up.
   >
   > The spec.md is what you'd hand to a builder. The spec.json (next to it) is the machine-readable version, used as input to the inception pipeline.

4. Ask whether to continue into inception:

   > Spec captured. Want to keep going and have inception scaffold a starter agent design from it?
   >
   > Inception runs six sub-agents (workload classifier → skill proposer → architecture selector → runtime + model picker → scaffold writer → eval seed + judge harness). Takes 3–5 minutes. Output: a full `agent_starter/<id>/` directory with `orchestrator.py`, `skills/<name>/SKILL.md` files, `design_rationale.md`, an eval seed, and a judge harness.
   >
   > If yes, I'll run it now. If you'd rather stop here and take the spec.md to a builder manually, that's the other half of the product — your call.

5. If the user says yes, proceed to Phase 6. If they want to stop here, ask for feedback:

   > Two things I'd like to know:
   > 1. Did the ingest + gap-fill flow feel substantive, or artificial? Where specifically?
   > 2. Is the spec.md something you'd actually be willing to hand to a builder?
   >
   > Andrew is collecting feedback to iterate.

---

## Phase 6 — Inception (turn the spec into a starter agent)

This is the second half of the product. The discovery spec is the input; the output is a complete starter agent design.

1. Run it:

   ```bash
   cd "$REPO" && uv run python -m agent.cli inception --session-id "<session_id>"
   ```

   Auto-resolves the spec.md + role-context paths from the session id. Optional `--output-dir <path>` to override where the starter lands (default: `agent_starter/<role_id_or_session_id>/`).

   Each step prints progress; the full run takes ~3–5 minutes. The CLI returns JSON with the selected workload axes, architecture, runtime + model, and scaffold output paths.

2. Surface the high-level decisions to the user:

   > Inception finished. Here's what the pipeline picked for this agent:
   > - **Workload:** `<interaction_shape> / <decision_complexity> / <data_intensity>` — the shape of the work the agent will do
   > - **Architecture:** `<selected_pattern_slug>` (e.g. `single-agent-react`, `chained-pipeline`, `inner-pipeline-skill`)
   > - **Runtime:** `<runtime> + <model_family>` (e.g. `claude-agent-sdk + claude-opus-4-7`)
   > - **Scaffold:** `agent_starter/<id>/` — architecture.md + orchestrator.py + N skills + design_rationale.md + eval seed + judge harness

3. Read the key files for the user. **Start with `architecture.md`** — it has two Mermaid diagrams (skill graph + execution flow) that render inline and give the 30-second mental model. Then `design_rationale.md` for the why:

   ```bash
   ls -la "$REPO/agent_starter/<id>/"
   cat "$REPO/agent_starter/<id>/architecture.md"
   cat "$REPO/agent_starter/<id>/design_rationale.md"
   ```

   Walk the user through the architecture diagrams first (they're the fastest way to grok the agent's shape), then the design_rationale.md for the audit trail. Surface the open questions section of the rationale (places where the design has tradeoffs the user should validate).

4. Point them at the rest:

   > The starter is at `agent_starter/<id>/`. Reading order:
   > 1. `architecture.md` — Mermaid diagrams + summary. **Start here** — fastest path to understanding the shape.
   > 2. `design_rationale.md` — why each decision was made, with citations into `patterns/`.
   > 3. `orchestrator.py` — the runnable entry point. Sketch + types; not production-tuned.
   > 4. `skills/<name>/SKILL.md` — one per proposed skill; each one has a prompt template, input/output schemas, and example calls.
   > 5. `eval/questions.json` + `eval/judge.py` — seed eval cases + LLM-as-judge harness for grading the agent's responses.
   >
   > This isn't a working agent yet — it's a defensible starter the builder can pressure-test. The whole point is to compress iteration time from "weeks figuring out what to build" to "days iterating on a candidate design."

5. Ask for feedback:

   > Three things I'd like to know:
   > 1. Did the discovery → spec → inception flow feel cohesive?
   > 2. Is the `agent_starter/<id>/` directory a defensible starting point for a builder, or does it feel hallucinated?
   > 3. Where specifically did the pipeline miscalibrate (e.g. wrong architecture pick, weak skill cut, runtime mismatch)?
   >
   > Andrew is collecting feedback to iterate. Specific gripes are more useful than overall scores.

---

## Phase 7 — Optional: persistent MCP setup

If the user wants discovery-inception always available as MCP tools (so future use cases don't need re-invoking this skill), point them at `$REPO/agent/mcp_server/README.md` for the one-time MCP registration. Don't push this if they just wanted to test once.

---

## Important rules for you (Claude) during this skill

- **The product is two stages: discovery → inception.** If a user asks "what does this do," lead with the full pipeline (artifacts → spec → starter agent), not just the discovery half. Phase 6 is the second half of the product, not an afterthought.
- **Default to artifact-first.** If the user hands you any artifact or mentions one, treat ingest as the first move. Don't drop them into interview mode unless they explicitly say they have nothing.
- **Don't paraphrase or summarize the agent's responses.** Show them verbatim. The structure of the agent's response is part of what the user is evaluating.
- **One turn at a time in interview mode.** Don't try to batch interview turns.
- **Chat-fill batches are fine.** When the FDE is filling several gaps in a row, you can run multiple `submit-turn --no-probe` commands sequentially without showing the placeholder output each time — just confirm at the end how many facts were recorded.
- **Long artifacts → temp files.** If the user pastes a long transcript or runbook, write to a temp file before passing to `--artifact`. Avoids shell-escaping pain.
- **Surface failures cleanly.** If a CLI invocation returns `ok: false`, show the error to the user and stop. Don't silently retry.
- **No need to install the skill into the user's Claude config** — this skill is invoked directly from their current Claude session; it doesn't need to be persistent unless they want it for future sessions.

If anything goes wrong setup-wise (uv missing, permission errors, network failures on the clone), surface the error verbatim and offer to help debug. Don't paper over.
