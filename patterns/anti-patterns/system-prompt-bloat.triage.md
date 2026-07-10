# Triage report — ingest of `cwc-system-prompt-bloat.md`

**Recommended action:** `create_new`  
**Target:** `anti-patterns/system-prompt-bloat`

## Rationale

The new draft 'System-Prompt Bloat' addresses a specific anti-pattern (progressive accumulation of business logic in system prompts degrading agent performance) that is distinct from existing anti-pattern entries. While it shares the general category with entries like 'over-decomposition' and 'cheap-cascade-orchestrator-compensation', it targets a different failure mode: the degradation that occurs *within* a single agent's prompt as requirements accumulate, rather than architectural decomposition choices or model-selection tradeoffs. The empirical anchor (Stock Pilot eval showing 62%/83% → ~92% after refactoring from ~400 lines to ~50 lines, then to ~15 lines via skills) is specific to this pattern and does not overlap with the receipts in existing entries. The fix (progressive disclosure via skills) is the same architectural move recommended in 'over-decomposition' and 'decision-guides/subagent-vs-skill-tradeoffs', but the *problem statement* (context pollution from bloat, not over-granularity) is orthogonal.

## Extension candidates

### `anti-patterns/over-decomposition` (confidence 0.65)

**Overlap:** Both entries discuss the problem of splitting work into too many units (over-decomposition discusses too many skills; system-prompt-bloat discusses too much in one prompt). Both recommend moving complexity into skills as the fix. However, the root causes are inverted: over-decomposition is 'too many skills where fewer would do'; system-prompt-bloat is 'too much in the system prompt where skills would do'. The new entry's empirical anchor (performance regression from prompt bloat) is distinct from over-decomposition's anchor (skill-count regression).

**Proposed merge:** Do not merge. The entries address opposite failure modes (too-many-units vs. too-much-in-one-unit) and have distinct empirical receipts. Linking them as 'related' is appropriate; merging would obscure the distinction.

### `anti-patterns/definitions-without-context` (confidence 0.45)

**Overlap:** Both entries flag a failure mode where the orchestrator (or downstream consumer) lacks information needed to reason correctly. System-prompt-bloat describes context pollution (too much irrelevant info); definitions-without-context describes context deprivation (missing definitions). The fixes differ: bloat is solved by moving info *out* of the prompt into skills; definitions-without-context is solved by moving info *into* the result (carrying definitions alongside labels). The failure modes are adjacent but not overlapping.

**Proposed merge:** Do not merge. The entries address opposite information-flow problems (too much vs. too little) and have distinct fixes. A 'related' link is appropriate.
