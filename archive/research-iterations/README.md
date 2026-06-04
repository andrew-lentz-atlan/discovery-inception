# archive/research-iterations/

Frozen research iterations of the discovery agent. **Nothing here is on the
live path.** The live agent is `agent/v08/` (served via `agent/mcp_server/`,
`agent/cli.py`). These are kept as the empirical receipts behind the
architecture findings in `findings/` — not as runnable code.

## What's here

| Path | What it was |
|---|---|
| `v06/` | v0.6 orchestrator + spec tools — the "mega-agent in charge, extractors as tools" inversion |
| `v07/` | v0.7 — added `synthesize_my_thinking` as a lazy reflect tool |
| `run_comparison.py` | baseline harness comparing earlier versions |
| `run_v06_v07_comparison.py` | v0.6 vs v0.7 head-to-head |
| `run_v07_solo.py` | v0.7 solo baseline run |

v0.5 was already removed before this archival. The current solo baseline,
`run_v08_solo.py`, stays in `agent/baselines/` because it drives the live v0.8.

## Why they moved (2026-06-03)

Two reasons converged:

1. **Ambiguity.** With v05–v08 all under `agent/`, "which file is live?" was a
   real question for anyone new. Only v0.8 is live; the rest are history.

2. **A hidden live dependency + bug.** v0.8's mega-agent spec tools used to
   chain through v0.7 → v0.6 (`get_current_spec_state` and friends were
   *defined* in `v06/spec_tools.py` and re-exported up). That made v0.6/v0.7
   look dead while actually being load-bearing — and it hid a bug: the Issue-A
   FactRecord refactor broke `get_current_spec_state`'s `zip(t.facts,
   t.sources)`, a tool the mega-agent calls every discovery turn. The fix
   consolidated those tools into `agent/v08/spec_tools.py` (self-contained),
   which both repaired the bug and freed v0.6/v0.7 to retire here.

## Runnability

These scripts reference the pre-archival import layout (`from agent.v06...`),
which no longer resolves now that the packages live under `archive/`. They are
**frozen, not runnable as-is** — intentionally. To reproduce an old comparison,
check out a commit from before 2026-06-03. Git history preserves everything.
