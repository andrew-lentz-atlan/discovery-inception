# discovery-inception MCP server

Wraps the v0.8 discovery agent + the intake (priors) pipeline as tools Claude Code or Claude Desktop can invoke.

> **Version pinning:** This is the canonical user-facing entry point — the CLI and the Claude skill both drive it. The MCP server is currently wired to `agent.v08.orchestrator` (sharpener + tensions + deterministic close-out). The version every external user sees is whatever `agent/mcp_server/server.py` imports.

**The user plays the CUSTOMER. The discovery agent plays the FDE interviewer.** You feed in a job description / runbook / transcript first to build priors, then drive a discovery interview as the customer, and the final spec gets exported as `spec.md`.

## What you get

Eight tools, two groups:

**Priors (intake):**
- `generate_priors(artifact_text, role_id, source_name?)` — feed in a customer artifact, get a structured RoleContext
- `list_priors()` — what role contexts are available
- `get_priors(role_id)` — inspect one

**Discovery:**
- `start_discovery_session(use_case_seed, role_id?)` — start the interview
- `submit_customer_turn(session_id, message)` — speak as the customer, get the agent's next probe
- `get_session_state(session_id)` — inspect the running spec, topics, working theory
- `finalize_discovery_session(session_id)` — run the deterministic close-out synthesis and export `spec.md` + `spec.json`
- `list_sessions()` — past sessions on disk

## One-time setup

### 1. Clone + sync the repo

```bash
git clone https://github.com/andrew-lentz-atlan/discovery-inception.git
cd discovery-inception
uv sync
```

### 2. Provide LiteLLM creds

Either set them in your shell or copy them to `discovery-inception/.env`:

```bash
LITELLM_BASE_URL=https://llmproxy.atlan.dev
LITELLM_API_KEY=sk-...
```

Same proxy as `experiment/` and `job-search/`.

### 3. Register the MCP server with Claude Code or Desktop

**For Claude Desktop**, edit `~/Library/Application Support/Claude/claude_desktop_config.json` and add:

```json
{
  "mcpServers": {
    "discovery-inception": {
      "command": "uv",
      "args": [
        "--directory", "/absolute/path/to/discovery-inception",
        "run", "python", "-m", "agent.mcp_server"
      ]
    }
  }
}
```

**For Claude Code**, the equivalent in your `~/.claude/mcp-servers.json` or via `/mcp` command. Same shape.

Restart Claude.

### 4. Verify

In your Claude chat:

> Can you call `list_priors` from the discovery-inception MCP server?

If you see existing `solutions-consultant` priors come back, you're wired up.

## Typical workflow

```
You: I want to test discovery on an onboarding agent for TechCo. Here's a 
     job description for the SoCo role: [paste 1-3 paragraphs of JD]

Claude: I'll generate priors first.
        [calls generate_priors with role_id='soco-techco']
        Priors generated. 14 vocabulary terms, 3 unwritten rules, 5 flagged unknowns.

You: Now start a discovery session — I'll play the customer.

Claude: [calls start_discovery_session with use_case_seed and role_id]
        Session started: sess_abc. What's the customer's opening line?

You: We want to reduce time-to-first-value for new enterprise customers 
     from 90 days to 30.

Claude: [calls submit_customer_turn]
        Agent's response: "Good — so we have the headline outcome. Before 
        I drill into what 'first value' means or how you'd measure it, let 
        me map the landscape. When you say 'new enterprise customers,' do 
        you mean customers who just signed with Atlan...?"
        
        Working theory: (low confidence — first turn)
        Missing: success_metric, anti_goal, current_pain, persona, etc.
        
        Your turn.

[continues turn by turn — you answer as customer, agent probes back, 
 working theory updates, checklist fills]

You: I think we've covered enough. Wrap up.

Claude: [calls finalize_discovery_session]
        Spec exported to sessions/sess_abc/spec.md.
        Final theory: "A copilot that helps SoCos route new use cases..."
        Confidence: medium
        12 topics covered, 18 facts, 2 gaps flagged.
```

The `spec.md` is the deliverable. Open it directly or have Claude summarize it.

## Tips for getting useful results

- **Be a realistic customer.** Hedge sometimes. Walk back things you said. Get frustrated and ask "how is this relevant?" The agent has handling for all of those and you'll exercise more of the architecture.
- **Don't dump everything in one turn.** Real discovery is iterative. Let the agent ask follow-ups.
- **Use a real use case if possible.** Synthetic use cases produce synthetic specs. If you have an actual customer agent idea you're thinking about, this is way more useful as a test of "would this actually help me think it through" than a made-up one.
- **Inspect mid-stream.** `get_session_state` shows you what's been captured. If the agent's misreading you, you'll see it in the structured state. Tell the agent it got something wrong — it'll handle the contradiction.

## When things go wrong

**"LITELLM_BASE_URL and LITELLM_API_KEY must be set"** — your `.env` isn't being picked up. Check the `.env` is at `discovery-inception/.env` (not in `agent/` or elsewhere).

**Triage label `meta` on a real customer message** — known intermittent issue with the LiteLLM proxy occasionally returning stock prose. The retry logic recovers most of the time; the fallback labels it `concrete` if retries exhaust. If you see this happen a lot, it's worth a bug report.

**Sessions accumulating in `sessions/`** — they're per-test artifacts. Delete the directory whenever you want a clean slate; nothing in the codebase depends on them being there.

**"I don't know what to ask the customer"** — the discovery agent generates the questions. You play customer. The agent will ask its first question once you submit your opening message via `submit_customer_turn`.

## Feedback

This is alpha. The most useful feedback is: did the architecture generalize to YOUR use case, or did it feel artificial? If it felt artificial, where specifically? Drop notes in `#engineering` or DM Andrew.
