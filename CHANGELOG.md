# Changelog

Curated, human-readable record of what's shipped — written for a colleague opening the repo cold and asking *"is this real, where do I start, where do I file feedback?"* Most recent first.

For full git history: `git log`. For active roadmap: [`ROADMAP.md`](ROADMAP.md).

---

## v0.9 — 2026-05-22

**Headline:** The product is artifact-first. `agent.cli ingest` is the new first move; conversational discovery interview is the fallback. Discovery hands off to inception via a single CLI invocation: `agent.cli inception --session-id <sid>`. Both halves of the product are now reachable end-to-end without learning a second invocation pattern.

### What's new since v0.8

**Discovery rebuild.**
- Multi-artifact ingest pipeline: feed N call transcripts + docs + runbooks; produces a populated session with captured facts and a `gap_list.md` the FDE acts on.
- FDE chat-fill mode (`submit-turn --no-probe`): ~3× faster than interview mode for filling known gaps; same engine path, just skips the orchestrator's follow-up question generation.
- Discovery technical-thread MVP: parallel concern thread on tech stack, data sources, semantic layer, runtime target, governance, data freshness, identity model. `spec.md` renders the two threads in separate sections.
- Atlan context integration (read-side): primes the mega-agent with the customer's established glossary terms, table schemas, lineage, ownership, governance tags, business domains. Graceful degradation when Atlan is unavailable. CLI: `--atlan-tenant`, `--atlan-glossary`, `--atlan-tables`, `--atlan-domains`.

**Inception bridge.**
- `agent.cli inception --session-id <sid>` auto-resolves spec.md + role-context paths from the session id. Runs the 6-sub-agent inception pipeline (workload → skills → architecture → runtime → scaffold → critics). Produces `agent_starter/<id>/` with orchestrator.py, proposed skills, design_rationale.md, eval seed, judge harness. ~3–5 min end-to-end.
- `run_inception` exposed as an MCP tool alongside `ingest_artifacts`.
- Resume-from-checkpoint: retries pick up the four upstream LLM-call decisions from `meta/` instead of re-burning them. `--force` to override.

**Patterns knowledge wiki.**
- Cross-session promotion pipeline (`patterns_curator/promote`): reads per-session feedback artifacts, classifies generic-vs-specific, clusters across sessions, promotes ≥3-session clusters to candidate pattern entries.
- New entries: `anti-patterns/cheap-cascade-orchestrator-compensation`, `decision-guides/cost-vs-latency-tradeoffs`. 9 entries total, all 5 categories active.

**Resilience hardening across the pipeline.**
- Per-artifact intake failures isolated (one non-role-shaped JSON no longer tanks a multi-artifact run).
- Long-transcript handling with auto-bumping max_tokens on truncation across both intake and inception sub-agents.
- Inception scaffold_writer landed graceful degradation — partial scaffold outputs survive when any one of steps 5a–5e fails.
- `meta/` upstream checkpoints persisted before risky LLM calls.

**Distribution.**
- Claude skill rewrite: artifact-first as the visible default; Phase 6 walks through inception; frontmatter leads with the full two-stage product framing.
- README rewrite with "How most people use it" + cold-clone terminal flow.
- One-curl install: `curl -fsSL https://raw.githubusercontent.com/andrew-lentz-atlan/discovery-inception/main/claude-skill/SKILL.md -o ~/.claude/skills/discovery-inception.md`.

### Where to start

```bash
# Already have a clone? Pull the v0.9 tag.
git fetch --tags && git checkout v0.9 && uv sync

# Cold clone:
git clone https://github.com/andrew-lentz-atlan/discovery-inception.git
cd discovery-inception && uv sync && cp .env.example .env
# (add LITELLM creds to .env)

# Run the full pipeline on any artifacts you have lying around:
uv run python -m agent.cli ingest \
    --use-case-seed "<one-line use case>" \
    --artifact /path/to/transcript.txt \
    --artifact /path/to/runbook.md \
    --role-id <kebab-case-slug>

# Read sessions/<session_id>/gap_list.md.
# Chat-fill anything you know the answer to:
uv run python -m agent.cli submit-turn --no-probe \
    --session-id sess_xxx \
    --message "<your answer phrased as if the customer said it>"

# When the spec feels complete:
uv run python -m agent.cli finalize --session-id sess_xxx
uv run python -m agent.cli inception --session-id sess_xxx
# Output: agent_starter/<role_id>/
```

Or via the Claude skill: *"Use the discovery-inception skill — I have [a transcript / a doc / nothing] for [your use case]."*

### Known-honest caveats

- **The skill rewrite is new.** If something feels off in the artifact-first flow, that's the most likely place. File specifics.
- **The judge harness (step 5e) occasionally falls back to a stub.** When this happens, the rest of the scaffold lands cleanly; the stub explains the failure. Re-run inception or write a judge by hand against `eval/questions.json`.
- **Inception runs without explicit priors are degraded.** If you ingested without `--role-id`, the RoleContext gets stubbed and the design_rationale is thinner. For the strongest output: ingest with `--role-id`.

### Where to file feedback

DM Andrew, or open an issue. Specific gripes (which step felt artificial, which decision looked hallucinated, which file was missing) are more useful than overall scores.

---

## v0.8 — 2026-05-13

Probe-sharpener + tensions surfacing added to discovery; deterministic close-out synthesis; v0.8 became the live wired version in MCP + CLI + skill. See `findings/05` for the validation receipts.
