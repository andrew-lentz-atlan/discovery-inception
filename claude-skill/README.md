# Claude skill — discovery-inception setup + test

A one-file skill colleagues can drop into their Claude installation to test discovery-inception without reading any docs. The skill itself handles clone, deps, credentials, and drives the discovery interview turn-by-turn.

## What it does

When a user invokes the skill (e.g., *"test discovery-inception for a churn-prediction agent at FinCo"*), Claude:

1. Looks for an existing clone of the repo, OR clones it fresh to a path of the user's choice
2. Runs `uv sync` for dependencies
3. Checks for `.env` with LiteLLM creds, prompts the user if missing
4. Captures the use case and optionally an artifact (JD/runbook/transcript) for priors
5. Generates priors (`agent.cli generate-priors`) if an artifact was provided
6. Starts a discovery session (`agent.cli start-session`)
7. Loops: relays the user's customer message → invokes the agent → shows the response → asks for the next message
8. On the user's "wrap up" signal, runs the deterministic close-out synthesis and exports `spec.md` + `spec.json`
9. Surfaces the rendered spec and asks for feedback

The user plays customer; the discovery agent plays the FDE interviewer.

## Installation (for a colleague trying it for the first time)

**One-liner option:**

```bash
curl -fsSL https://raw.githubusercontent.com/andrew-lentz-atlan/discovery-inception/main/claude-skill/SKILL.md \
    -o ~/.claude/skills/discovery-inception.md
```

Restart Claude Code/Desktop (or run `/skills` if your client auto-detects).

**Manual option:**

1. Download [SKILL.md](./SKILL.md)
2. Copy it to `~/.claude/skills/discovery-inception.md`
3. Restart Claude

## Usage

Just say to Claude:

> Use the discovery-inception skill — I want to test it for [describe your use case].

Claude takes it from there. The skill handles credential setup the first time; subsequent invocations skip the setup phase.

If you also want an artifact ingested for priors, include it (or a path to a file) in your initial message:

> Use the discovery-inception skill — I want to test it for a renewal-risk agent for our CSM team at FinCo. Here's our internal CSM role description: [paste a few paragraphs].

## What this is NOT

- **Not the MCP server.** That's at `agent/mcp_server/` and gives ongoing in-Claude availability of the discovery tools after a one-time config edit. The skill is the *first-test* path; the MCP server is the *daily-use* path. The skill mentions MCP in its last phase as an upgrade option if the user wants it.
- **Not a permanent agent installation.** The skill is just instructions for Claude. Each session that invokes the skill drives a fresh discovery; no state persists outside the `sessions/` directory in the repo.

## When things go wrong

- **uv not installed** — install from https://docs.astral.sh/uv/getting-started/installation/ and re-invoke.
- **Credentials wrong** — the skill writes whatever you paste into `.env`. If discovery requests start failing with auth errors, edit `$REPO/.env` directly.
- **Skill not detected** — confirm the file is at `~/.claude/skills/discovery-inception.md` and your Claude has been restarted. Some clients require `/skills reload` or similar.
- **The agent's questions are weird** — that's data. Tell Andrew what was weird about them. The whole point of distributing this is to find where the architecture generalizes vs breaks.
