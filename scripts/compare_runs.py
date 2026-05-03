"""compare_runs — diff a candidate RoleContext against the gold reference.

Surfaces structural and content-level deltas between two `context.json`
files so you can quickly tell whether a prompt change improved or
regressed the intake. Designed to be human-readable, not machine-graded.

Usage:
    uv run python -m scripts.compare_runs \\
        --gold skills/solutions-consultant-gold/context.json \\
        --candidate skills/solutions-consultant/context.json

Output sections:
    - Top-level field counts (gold vs candidate)
    - Per-field added/removed/changed deltas
    - Confidence score deltas
    - flagged_unknowns: gold-only, candidate-only, overlap
    - unwritten_rules: gold-only, candidate-only, overlap
    - Inferred-marker audit (terms with [INFERRED] prefix)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_context(path: Path) -> dict:
    """Read a context.json file and return as a dict."""
    if not path.exists():
        raise SystemExit(f"Not found: {path}")
    return json.loads(path.read_text())


def fmt_count(label: str, gold_n: int, cand_n: int) -> str:
    """Format a 'GOLD: 7  CANDIDATE: 5  Δ -2' line."""
    delta = cand_n - gold_n
    sign = "+" if delta > 0 else ""
    indicator = "✓" if delta == 0 else ("↑" if delta > 0 else "↓")
    return f"  {indicator} {label:30s} gold={gold_n:3d}  candidate={cand_n:3d}  Δ={sign}{delta}"


def section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def subsection(title: str) -> None:
    print()
    print(f"--- {title} ---")


# ---------------------------------------------------------------------------
# Comparators
# ---------------------------------------------------------------------------

LIST_FIELDS = (
    "primary_outcomes",
    "typical_workflows",
    "decision_criteria",
    "escalation_paths",
    "common_edge_cases",
    "unwritten_rules",
    "flagged_unknowns",
)

DICT_FIELDS = ("domain_vocabulary", "confidence_per_field")


def field_counts(ctx: dict) -> dict[str, int]:
    counts = {}
    for f in LIST_FIELDS:
        counts[f] = len(ctx.get(f) or [])
    for f in DICT_FIELDS:
        counts[f] = len(ctx.get(f) or {})
    return counts


def compare_top_level_counts(gold: dict, cand: dict) -> None:
    section("Top-level field counts")
    gc = field_counts(gold)
    cc = field_counts(cand)
    for field in LIST_FIELDS + DICT_FIELDS:
        print(fmt_count(field, gc[field], cc[field]))


def compare_confidence(gold: dict, cand: dict) -> None:
    section("Confidence score deltas")
    g = gold.get("confidence_per_field") or {}
    c = cand.get("confidence_per_field") or {}
    fields = sorted(set(g.keys()) | set(c.keys()))
    for f in fields:
        gv = g.get(f, "—")
        cv = c.get(f, "—")
        if isinstance(gv, (int, float)) and isinstance(cv, (int, float)):
            delta = cv - gv
            sign = "+" if delta >= 0 else ""
            indicator = "↑" if delta > 0.05 else ("↓" if delta < -0.05 else "·")
            print(f"  {indicator} {f:30s} gold={gv:.2f}  cand={cv:.2f}  Δ={sign}{delta:+.2f}")
        else:
            print(f"  ? {f:30s} gold={gv}  cand={cv}")


def compare_set(
    title: str,
    gold_items: list[str],
    cand_items: list[str],
    *,
    truncate: int = 100,
) -> None:
    """Compare two lists of strings as sets — show what's only in each."""
    g = set(gold_items)
    c = set(cand_items)
    only_gold = sorted(g - c)
    only_cand = sorted(c - g)
    overlap = sorted(g & c)

    subsection(title)
    print(f"  overlap:    {len(overlap)}")
    print(f"  gold-only:  {len(only_gold)}")
    print(f"  cand-only:  {len(only_cand)}")
    if only_gold:
        print()
        print("  Items in GOLD but missing from CANDIDATE:")
        for item in only_gold:
            print(f"    - {item[:truncate]}{'…' if len(item) > truncate else ''}")
    if only_cand:
        print()
        print("  Items in CANDIDATE but not in GOLD:")
        for item in only_cand:
            print(f"    + {item[:truncate]}{'…' if len(item) > truncate else ''}")


def compare_unwritten_rules(gold: dict, cand: dict) -> None:
    section("Unwritten rules — set diff")
    compare_set(
        "rules",
        gold.get("unwritten_rules") or [],
        cand.get("unwritten_rules") or [],
        truncate=140,
    )


def compare_flagged_unknowns(gold: dict, cand: dict) -> None:
    section("Flagged unknowns — set diff (by field name)")
    g_fields = [item.get("field", "") for item in (gold.get("flagged_unknowns") or [])]
    c_fields = [item.get("field", "") for item in (cand.get("flagged_unknowns") or [])]
    compare_set("fields", g_fields, c_fields, truncate=80)


def compare_vocabulary(gold: dict, cand: dict) -> None:
    section("Domain vocabulary — set diff (by term)")
    g = gold.get("domain_vocabulary") or {}
    c = cand.get("domain_vocabulary") or {}
    compare_set("terms", list(g.keys()), list(c.keys()), truncate=60)


def audit_inferred_markers(gold: dict, cand: dict) -> None:
    section("Inferred-marker audit ([INFERRED] in domain_vocabulary)")
    for label, ctx in (("gold", gold), ("candidate", cand)):
        vocab = ctx.get("domain_vocabulary") or {}
        inferred = {t: d for t, d in vocab.items() if "[INFERRED" in d}
        print(f"  {label}: {len(inferred)} inferred term(s)")
        for term, definition in sorted(inferred.items()):
            print(f"    - {term}: {definition[:80]}{'…' if len(definition) > 80 else ''}")


def compare_role_summary(gold: dict, cand: dict) -> None:
    section("role_name & role_summary")
    print(f"  role_name (gold)      : {gold.get('role_name')}")
    print(f"  role_name (cand)      : {cand.get('role_name')}")
    if gold.get("role_name") != cand.get("role_name"):
        print("  ⚠ role_name diverges — inspect manually.")
    print()
    print(f"  role_summary (gold)   : {(gold.get('role_summary') or '')[:200]}…")
    print(f"  role_summary (cand)   : {(cand.get('role_summary') or '')[:200]}…")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diff a candidate RoleContext against the gold reference."
    )
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    args = parser.parse_args()

    gold = load_context(args.gold)
    cand = load_context(args.candidate)

    print(f"Gold:      {args.gold}")
    print(f"Candidate: {args.candidate}")

    compare_top_level_counts(gold, cand)
    compare_role_summary(gold, cand)
    compare_confidence(gold, cand)
    compare_vocabulary(gold, cand)
    compare_unwritten_rules(gold, cand)
    compare_flagged_unknowns(gold, cand)
    audit_inferred_markers(gold, cand)

    print()
    print("=" * 72)
    print("Done. Manual review needed for:")
    print("  - Whether candidate's missing items in gold are real regressions")
    print("    or correct conservative behavior on a different artifact.")
    print("  - Whether candidate's new items are genuine improvements")
    print("    or hallucinations the prompt fixes failed to prevent.")
    print("  - Whether confidence scores moved in the expected direction")
    print("    given the prompt changes.")
    print("=" * 72)


if __name__ == "__main__":
    main()
