# intake — the CaaS unstructured-to-structured agent

Takes a single unstructured artifact about a workplace role (job description, runbook, transcript, policy doc) and produces a structured `RoleContext` skill that the downstream discovery agent can use as priors.

This is the first concrete build in the discovery-inception project — the priors-generation pipeline that takes a customer artifact and produces a structured `RoleContext` consumed by the downstream discovery agent.

## Architecture (one paragraph)

Six sequential LLM calls, each with one tightly-scoped prompt and one Pydantic output type. They share the source artifact in their context but produce different slices of the output. No multi-agent orchestration — just a focused pipeline of small focused calls.

```
artifact text
  │
  ▼
1. classify (what kind of doc?)
  ▼
2. extract (workflows, decisions, escalations, edge cases)
  ▼
3. normalize vocabulary (domain terms + synonym merges)
  ▼
4. sniff unwritten rules (heuristics, soft rules, anti-patterns)
  ▼
5. report gaps (what's missing + probe suggestions)
  ▼
6. score confidence (per-field score + rationale)
  ▼
RoleContext written to skills/<role-id>/context.json
```

## Files

- `schemas.py` — Pydantic types. `RoleContext` is the final output; the rest are step intermediates.
- `prompts/0N_*.md` — one prompt per step. Most of the value of this whole tool lives in these files.
- `run.py` — CLI entry point. Loads `.env` from `../harness/`, chains the six steps, writes output.
- `sources/` — artifacts you've fed into the intake (kept alongside their outputs for reproducibility).

## Prerequisites

The harness at `../harness/` must be runnable. That means:
- `llama-server` is up on the URL in `../harness/.env` (default: `http://localhost:8080`)
- `../harness/` has had `uv sync` run (its venv is what we'll use)

## Running it

From inside `discovery-inception/`:

```bash
# Save your artifact text to a file first.
mkdir -p intake/sources
cp /wherever/sc-role.md intake/sources/

# Run the intake. Uses the harness's venv.
cd ../harness
uv run python -m intake.run \
    --artifact ../discovery-inception/intake/sources/sc-role.md \
    --role-id solutions-consultant
```

(The `cd ../harness` matters because that's where the `uv` project lives. The `run.py` adds the harness directory to sys.path so it can import `core.client` etc.)

Output goes to `discovery-inception/skills/<role-id>/`:
- `context.json` — the structured RoleContext
- `source/<artifact-name>` — copy of the input for traceability

## What good output looks like

After running against a real artifact, the `context.json` should:

1. Have a `role_name` and `role_summary` that match the source
2. Populate at least 1-2 `typical_workflows`, 1-2 `decision_criteria` (if the source supports them; empty is OK if it doesn't)
3. Have a non-empty `flagged_unknowns` (≥3 specific gaps with probe suggestions)
4. Have at least one entry in `unwritten_rules` if the source contains any aside-style or example-driven content
5. Have `confidence_per_field` populated with reasonable spreads (don't expect all 1.0s)
6. Be stable across two runs — temperature is 0.2 to keep it close to deterministic

## Iterating on prompts

The whole product is the prompts. To improve quality:

1. Run the intake against a real artifact.
2. Read the output. What's wrong, what's missing, what's hallucinated?
3. Tighten the relevant prompt in `prompts/`. Add concrete rules. Add anti-examples ("do NOT..."). Add forced specificity.
4. Re-run. Confirm regression-free against any prior artifacts you've validated.
5. Repeat.

This is pure prompt engineering. Most of the time on this project will live here.

## Failure modes worth knowing about

- **Hallucinated content.** If the model invents details not in the source, the extractor prompt is too lenient. Tighten "extract only what the source supports."
- **Templatey output.** If escalation paths read like a McKinsey deck, the source genuinely had nothing concrete and the extractor should have left them empty. Tighten "empty is better than wrong."
- **Bad JSON.** Small Gemma sometimes wraps JSON in prose despite the system prompt. The parser strips ```` ```json ```` fences. If parsing still fails, lower temperature further or split the prompt into smaller calls.
- **Unwritten rules sniffer returns nothing.** Either the source genuinely has no asides (formal job descriptions often don't), or the prompt's threshold is too strict. Try running it against a transcript instead — those have far more implicit content.
