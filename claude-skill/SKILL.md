---
name: discovery-inception
description: |
  Set up and test the discovery-inception agent (a chained-agent discovery
  system that interviews a customer to produce a structured spec for an
  AI agent build). Use when the user asks to test, try, or use
  discovery-inception. The user plays CUSTOMER; the discovery agent
  plays the FDE interviewer. The skill handles repo cloning, dependency
  install, credential setup, and drives the discovery interview
  turn-by-turn until the user wraps up. Final deliverable is a spec.md
  the user can hand to a builder.
---

# discovery-inception — install, set up, and run a test discovery session

You are guiding the user through testing the **discovery-inception** agent. The user invoked this skill because they want to either:
- Set up the tool for the first time on their machine, OR
- Run a discovery interview on a use case they're curious about, OR
- Both (which is the common case).

The discovery-inception agent is a chained system that **interviews the customer** to draw out a structured spec a builder can use to scope an AI agent. In this skill flow, **the user plays the customer; the discovery agent plays the Forward Deployed Engineer**.

Repo: https://github.com/andrew-lentz-atlan/discovery-inception

Walk the user through the phases below. Don't skip — if the user already did some setup, verify it cleanly before assuming.

---

## Phase 0 — Quick reading the room

Before any commands, read what the user said. They might have already given you:
- A specific use case ("test it for a churn-prediction agent at FinCo")
- An artifact (a JD or runbook they want to feed in as priors)
- A preference for where to clone the repo

If any of those are present, note them and skip the corresponding prompt later. Otherwise you'll ask when you get there.

---

## Phase 1 — Repo setup (one-time)

1. Check the common locations for an existing clone:
   - `~/Desktop/discovery-inception`
   - `~/code/discovery-inception`
   - `~/discovery-inception`
   - `~/projects/discovery-inception`

   Use Bash to test each:
   ```bash
   for d in ~/Desktop/discovery-inception ~/code/discovery-inception ~/discovery-inception ~/projects/discovery-inception; do
     if [ -d "$d/.git" ]; then echo "FOUND: $d"; break; fi
   done
   ```

2. If found, ask the user: *"I see you already have discovery-inception at `<path>`. Use that, or clone fresh elsewhere?"* Default to using what's there.

3. If not found, ask: *"Where should I clone discovery-inception? Default: `~/Desktop/discovery-inception`."* Then clone and pin to the latest released tag so the user gets a known-good version (not a half-finished reorg on `main`):
   ```bash
   git clone https://github.com/andrew-lentz-atlan/discovery-inception.git <path>
   cd <path>
   # Pin to the latest discovery-inception tag (e.g. v0.8). If git tag has none,
   # it's fine to stay on main — that means the project hasn't tagged a release
   # yet, OR the user explicitly wants bleeding edge.
   latest_tag=$(git tag -l 'v*' --sort=-v:refname | head -1)
   if [ -n "$latest_tag" ]; then
     echo "checking out $latest_tag"
     git checkout "$latest_tag"
   fi
   ```

   If the user already had a clone (step 2), offer to update them to the latest tag too:
   ```bash
   cd "$REPO" && git fetch --tags && latest=$(git tag -l 'v*' --sort=-v:refname | head -1) && [ -n "$latest" ] && git checkout "$latest"
   ```

4. From now on, refer to the chosen path as `$REPO`. Every Bash command in subsequent phases should `cd "$REPO"` first.

5. Run dependency sync:
   ```bash
   cd "$REPO" && uv sync
   ```
   This takes ~30 seconds the first time. Surface any errors to the user.

---

## Phase 2 — Credentials

1. Check whether `$REPO/.env` exists and has both `LITELLM_BASE_URL` and `LITELLM_API_KEY`:
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
   > Paste your API key and I'll write the `.env` for you. (Or paste both lines if you have a non-default base URL.)

3. Once the user provides the key, write the `.env` (use a heredoc to avoid quoting issues):
   ```bash
   cat > "$REPO/.env" <<'EOF'
   LITELLM_BASE_URL=https://llmproxy.atlan.dev
   LITELLM_API_KEY=<user_provided_key>
   EOF
   ```

   Then verify: `python -c "from dotenv import dotenv_values; v=dotenv_values('$REPO/.env'); assert v.get('LITELLM_API_KEY'); print('ok')"`

---

## Phase 3 — Use case capture

1. If the user already named a use case in their initial invocation, confirm it.
   Otherwise ask:
   > What use case do you want to test discovery on? One-line description, e.g. *"we want a SoCo agent for new-customer onboarding at TechCo"* or *"we want a churn-prediction agent for our CSM team at FinCo"*.

2. Ask about priors:
   > Optional but recommended: do you have an artifact (a job description for the role this agent augments, a runbook the role uses, a transcript from a past discovery call, a success-plan template) you want to feed in as priors? Paste it inline or give me a file path. If not, I'll start discovery without priors — the agent will still work but won't mirror domain-specific vocabulary as well.

3. If the user provided an artifact, generate priors:
   ```bash
   cd "$REPO" && uv run python -m agent.cli generate-priors \
       --role-id <kebab-case slug from the use case, e.g. 'soco-techco'> \
       --artifact-file <path-or-tempfile>
   ```
   (Or use `--artifact-text` for inline text — but pipe through a temp file for anything longer than a few lines.)

   The CLI prints JSON with `role_id`, `n_vocab_terms`, etc. Surface a brief summary to the user:
   *"Generated priors for `<role_id>`: 14 vocab terms, 3 unwritten rules, 5 flagged unknowns. Stored at `skills/<role_id>/context.json`."*

4. If no artifact, proceed without priors (`role_id` will be `None`).

---

## Phase 4 — Run the discovery interview

1. Start the session:
   ```bash
   cd "$REPO" && uv run python -m agent.cli start-session \
       --use-case-seed "<use_case>" \
       --role-id "<role_id_or_omit>"
   ```
   Capture the `session_id` from the JSON output. **Store this** — every subsequent turn needs it.

2. Set the user's expectations clearly:
   > Session started: `<session_id>`.
   >
   > **You're playing the customer.** I'll relay your message to the discovery agent (which plays the FDE interviewer), then show you the agent's question back. Then you answer as the customer would — naturally, the way you'd answer in a real discovery call. Hedge if it makes sense, push back if a question feels off, walk things back if you misspoke. The agent is designed to handle all of that.
   >
   > What's your opening message as the customer?

3. **Loop** until the user signals they're done:

   a. Take the user's customer message.
   b. Submit it:
      ```bash
      cd "$REPO" && uv run python -m agent.cli submit-turn \
          --session-id "<session_id>" \
          --message "<user_message>"
      ```
      Each turn typically takes 10-20 seconds (extractors + mega-agent).

   c. Parse the JSON output. Show the user:
      - The agent's response (verbatim — don't summarize)
      - The triage label (in a small note: e.g. *"[triage: concrete]"*)
      - If the checklist shrunk meaningfully, mention it (e.g. *"[checklist: 5 of 8 canonical topics now covered]"*)

   d. Ask for the next customer message OR offer to wrap up.

4. The user can also ask you to:
   - **Inspect state**: run `uv run python -m agent.cli state --session-id <id>` and summarize the working theory / topics / gaps. Helpful when they want to know what's been captured before continuing.
   - **Push back on the agent's reading**: if they think the agent misread something, encourage them to *say so to the agent* (as the customer would). The agent has explicit handling for contradictions and relevance challenges.

5. Wrap-up trigger: when the user says *"wrap up,"* *"finalize,"* *"we're done,"* *"that's enough,"* or similar.

---

## Phase 5 — Finalize and show the spec

1. Run the close-out:
   ```bash
   cd "$REPO" && uv run python -m agent.cli finalize --session-id "<session_id>"
   ```

2. The CLI returns JSON with `spec_md_path` and `spec_json_path`. Read the `spec.md`:
   ```bash
   cat "<spec_md_path>"
   ```

3. Show the user the rendered spec. Then briefly summarize:
   > Discovery wrapped. Spec at `<path>`. Final working theory confidence: `<level>`. **<N>** topics captured, **<M>** facts, **<K>** gaps flagged for FDE follow-up.
   >
   > The spec.md is what you'd hand to a builder. The spec.json (next to it) is the machine-readable version.

4. Ask the user for feedback:
   > Two things I'd like to know:
   > 1. Did the interview feel substantive, or artificial? Where specifically?
   > 2. Is the spec.md something you'd actually be willing to hand to a builder?
   >
   > This is alpha — Andrew is collecting feedback to iterate.

---

## Phase 6 — Optional: persistent MCP setup

If the user wants to test more use cases in future sessions WITHOUT re-invoking this skill (i.e., they want discovery-inception always available as MCP tools in their Claude), point them at `$REPO/agent/mcp_server/README.md` for the one-time MCP registration. Don't push this if they just wanted a quick test.

---

## Important rules for you (Claude) during this skill

- **Don't answer the agent's questions for the user.** The user plays the customer — let them answer in their own words. Just relay the agent's question and wait for the user.
- **Don't paraphrase or summarize the agent's responses.** Show them verbatim. The structure of the agent's response (signposting, enumerated alternatives, playbacks) is part of what the user is evaluating.
- **One turn at a time.** Don't try to run multiple turns in a row hoping to speed things up.
- **Surface failures cleanly.** If a CLI invocation returns `ok: false`, show the error to the user and stop. Don't silently retry.
- **Long artifacts** — if the user pastes a long job description or runbook, write it to a temp file before passing to `--artifact-file` rather than embedding inline. Avoids shell-escaping pain.
- **No need to install the skill into the user's Claude config** — this skill is invoked directly from their current Claude session; it doesn't need to be persistent unless they want it for future sessions.

If anything goes wrong setup-wise (uv missing, permission errors, network failures on the clone), surface the error verbatim and offer to help debug. Don't paper over.
