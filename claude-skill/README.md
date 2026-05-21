# Claude skill — discovery-inception setup + test

A one-file skill colleagues drop into their Claude installation to test discovery-inception without reading any docs. The skill handles clone, deps, credentials, multi-artifact ingest, chat-fill of known gaps, and optional live interview for the gaps that need a real customer answer.

## What it does

When a user invokes the skill (e.g., *"test discovery-inception — I've got two call transcripts and a runbook for a renewal-risk agent"*), Claude:

1. Looks for an existing clone of the repo, OR clones it fresh to a path of the user's choice
2. Runs `uv sync` for dependencies
3. Checks for `.env` with LiteLLM creds; prompts if missing
4. Captures the use case + collects artifacts (any combination of transcripts, runbooks, JDs, slack threads, docs)
5. Runs **multi-artifact ingest** (`agent.cli ingest`) — produces a populated `DiscoverySession` with facts captured + a `gap_list.md` the FDE acts on
6. Walks the user through closing the gaps in whichever mode fits each gap:
   - **Chat-fill** (`submit-turn --no-probe`) — FDE answers a known gap; fast (~5s); no follow-up question generated
   - **Interview** (`submit-turn`) — FDE plays customer for gaps that need a real answer; ~15s/turn; mega-agent produces the next probe
7. On the user's "wrap up" signal, runs the deterministic close-out synthesis and exports `spec.md` + `spec.json`
8. Surfaces the rendered spec and asks for feedback

## Why artifact-first

Most real flows start with *something* — a call transcript, a runbook, an internal doc. Discovery-as-interview is still here as the fallback mode for when the user truly has nothing, but the first-class path is now:

```
artifacts → ingest → gap_list.md → chat-fill known gaps → interview unknown gaps → spec.md
```

The chat-fill mode is the load-bearing UX win. An FDE who was on the call knows the answer to most gaps. Chat-fill captures their answer as fact (the FDE's job is to decide what's fact) without making them ask the customer or play a fake interview turn.

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

If you have artifacts in hand, mention them up front — the skill will treat ingest as the first move:

> Use the discovery-inception skill — I've got a transcript from yesterday's scoping call with FinCo about a renewal-risk agent, plus our CSM team runbook. Want to turn those into a spec.

Or, if you genuinely have nothing:

> Use the discovery-inception skill — I want to do a fresh interview for a SoCo agent at TechCo. No artifacts, just the use case.

The skill picks up from there.

## What this is NOT

- **Not the MCP server.** That's at `agent/mcp_server/` and gives ongoing in-Claude availability of the discovery tools after a one-time config edit. The skill is the *first-test* path; the MCP server is the *daily-use* path. The skill mentions MCP in its last phase as an upgrade option if the user wants it.
- **Not a permanent agent installation.** The skill is just instructions for Claude. Each session that invokes the skill drives a fresh discovery; no state persists outside the `sessions/` directory in the repo.

## When things go wrong

- **uv not installed** — install from https://docs.astral.sh/uv/getting-started/installation/ and re-invoke.
- **Credentials wrong** — the skill writes whatever you paste into `.env`. If discovery requests start failing with auth errors, edit `$REPO/.env` directly.
- **Skill not detected** — confirm the file is at `~/.claude/skills/discovery-inception.md` and your Claude has been restarted. Some clients require `/skills reload` or similar.
- **The agent's questions are weird** — that's data. Tell Andrew what was weird about them. The whole point of distributing this is to find where the architecture generalizes vs breaks.
