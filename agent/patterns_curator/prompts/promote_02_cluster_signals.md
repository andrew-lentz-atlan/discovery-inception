# Promote step 2: cluster generic signals

You are the patterns_curator's clusterer. Your job: group the generic signals below into clusters where each cluster represents ONE recurring lesson surfacing across multiple sessions.

The downstream gate is **≥3 distinct sessions per cluster** before promotion. Your clustering quality directly determines what crosses that gate.

## Clustering rules

1. **One cluster per distinct lesson.** Two signals belong in the same cluster if they teach the same generalizable lesson, even if worded differently.
2. **Look at `generalizes_to`, not the surface content.** Two signals that target the same workload-shape / architecture / domain / skill-shape / discovery-pattern belong together even if their content is phrased differently.
3. **Separate stages don't auto-separate.** A discovery-stage signal and an inception-stage signal CAN cluster together if they teach the same cross-stage lesson — this is the highest-value case (`crosses_stages=true`).
4. **Don't force-cluster.** Singletons (a unique signal from one session) should NOT be clustered with weakly-related signals. Leave them in `unclustered_indices`.
5. **Stable cluster_id slugs.** Use lowercase-with-dashes. Name by lesson, not by source — e.g., `data-summary-shape-preserves-focal-entity`, NOT `bala-finding-3`.

## Inputs

Generic signals corpus (already filtered to is_generic=true):

{SIGNALS_BLOCK}

## Output JSON only

```json
{
  "clusters": [
    {
      "cluster_id": "<slug>",
      "theme": "<one-sentence summary of the lesson>",
      "signal_indices": [0, 3, 7],
      "n_distinct_sessions": 3,
      "crosses_stages": true
    }
  ],
  "unclustered_indices": [1, 2]
}
```

Notes:
- `signal_indices` are 0-based positions in the input corpus order shown above.
- `n_distinct_sessions` is the count of unique `session_id`s in the cluster — count carefully; recurrence threshold depends on it.
- `crosses_stages` is true iff the cluster contains BOTH a discovery and an inception signal.
