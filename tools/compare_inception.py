#!/usr/bin/env python3
"""compare_inception.py — Compare inception output across two git refs of patterns/.

Runs `agent.cli inception` twice against the same session — once with
patterns/ at ref A, once at ref B — and reports the deltas: confidence
numbers, citation counts to patterns/ entries, design_rationale length,
skill cut, scaffold quality.

The inception CODE stays at the current checkout (no branch switching);
only the patterns/ directory is swapped via the `PATTERNS_DIR` env var.
That isolates the comparison to pure patterns/ changes — if you want
to test prompt or code changes too, swap branches between runs manually.

Usage:
    python tools/compare_inception.py \\
        --session-id sess_abc123 \\
        --ref-a main \\
        --ref-b feature/patterns-deepening-v1

    # Re-render report without re-running inception (useful when iterating
    # on a new entry — you saved the ref-a baseline once, then run with
    # --skip-ref-a to only re-run ref-b):
    python tools/compare_inception.py --session-id sess_abc --ref-b ... --skip-ref-a

Outputs:
    .compare_inception/<ref-a-slug>/   ← agent_starter for ref A
    .compare_inception/<ref-b-slug>/   ← agent_starter for ref B
    .compare_inception/<ref-a-slug>/_patterns/  ← extracted patterns/ for ref A
    .compare_inception/<ref-b-slug>/_patterns/  ← extracted patterns/ for ref B

Both `.compare_inception/` and all its children are gitignored.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Shell + git helpers
# ---------------------------------------------------------------------------


def sh(cmd: str, *, cwd: Path | None = None, check: bool = False, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        cwd=cwd or PROJECT_ROOT, check=check, env=env,
    )


def git_short_sha(ref: str) -> str:
    return sh(f"git rev-parse --short {ref}").stdout.strip()


def extract_patterns_at_ref(ref: str, dest: Path) -> None:
    """Materialize patterns/ at the given git ref into dest/. Uses `git archive`
    so the current working tree is untouched."""
    dest.mkdir(parents=True, exist_ok=True)
    # Clear any prior contents
    for child in dest.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    # Pipe `git archive` into tar to extract just the patterns/ subtree
    cmd = f"git archive {ref} patterns/ | tar -x -C {dest.parent} && mv {dest.parent}/patterns/* {dest}/ && rmdir {dest.parent}/patterns 2>/dev/null || true"
    result = sh(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"git archive failed for ref={ref}: {result.stderr}")


# ---------------------------------------------------------------------------
# Inception invocation
# ---------------------------------------------------------------------------


def run_inception(session_id: str, output_dir: Path, patterns_dir: Path) -> dict[str, Any]:
    """Run inception against the session, with PATTERNS_DIR pointing at the
    extracted patterns. Forces fresh upstream LLM calls (no resume cache)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PATTERNS_DIR"] = str(patterns_dir.resolve())

    cmd = (
        f"uv run python -m agent.cli inception "
        f"--session-id {session_id} "
        f"--force "
        f"--output-dir {output_dir}"
    )
    print(f"  → PATTERNS_DIR={env['PATTERNS_DIR']}")
    print(f"  → {cmd}")
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, cwd=PROJECT_ROOT, env=env,
    )
    if result.returncode != 0:
        print(f"  ! inception failed (stderr tail):")
        print(result.stderr[-1500:])
        return {"ok": False, "returncode": result.returncode}
    # Last JSON object in stdout is the result dict
    stdout = result.stdout
    last_brace = stdout.rfind("}")
    first_brace = stdout.rfind("{", 0, last_brace) if last_brace > -1 else -1
    if first_brace == -1:
        return {"ok": False, "stderr": "could not locate JSON in stdout"}
    try:
        return json.loads(stdout[first_brace : last_brace + 1])
    except json.JSONDecodeError as exc:
        return {"ok": False, "stderr": f"JSON parse: {exc}"}


# ---------------------------------------------------------------------------
# Artifact extraction
# ---------------------------------------------------------------------------


def load_artifacts(output_dir: Path) -> dict[str, Any]:
    """Pull the comparable fields out of an agent_starter/ directory."""
    art: dict[str, Any] = {}

    # Confidence numbers from meta/
    for step_num, label, filename in [
        (1, "workload", "01_workload_classification.json"),
        (3, "architecture", "03_architecture_proposal.json"),
        (4, "runtime", "04_runtime_proposal.json"),
    ]:
        path = output_dir / "meta" / filename
        if path.exists():
            try:
                data = json.loads(path.read_text())
                art[f"{label}_confidence"] = data.get("confidence")
            except Exception:
                art[f"{label}_confidence"] = None

    # design_rationale.md stats + citations
    dr = output_dir / "design_rationale.md"
    if dr.exists():
        text = dr.read_text()
        art["design_rationale_chars"] = len(text)
        art["design_rationale_lines"] = len(text.splitlines())
        # Match `patterns/<category>/<slug>` (with or without .md)
        # AND `<category>/<slug>.md` inside backticks (the citation style we use)
        citations = re.findall(r"(?:patterns/|`)([a-z][a-z\-]+)/([a-z0-9][a-z0-9\-]+)(?:\.md)?(?:`|\s)", text)
        cite_counts: dict[str, int] = {}
        for cat, slug in citations:
            key = f"{cat}/{slug}"
            cite_counts[key] = cite_counts.get(key, 0) + 1
        art["citations"] = cite_counts
        art["total_citations"] = sum(cite_counts.values())

    # architecture.md
    ar = output_dir / "architecture.md"
    if ar.exists():
        art["architecture_chars"] = len(ar.read_text())

    # orchestrator.py
    orch = output_dir / "orchestrator.py"
    if orch.exists():
        art["orchestrator_lines"] = len(orch.read_text().splitlines())

    # eval/judge.py
    judge = output_dir / "eval" / "judge.py"
    if judge.exists():
        art["judge_lines"] = len(judge.read_text().splitlines())

    # Skills
    skills_dir = output_dir / "skills"
    if skills_dir.exists():
        skill_names = sorted(d.name for d in skills_dir.iterdir() if d.is_dir())
        art["skills"] = skill_names
        art["skill_count"] = len(skill_names)

    return art


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def _delta(a: float | None, b: float | None) -> str:
    if a is None or b is None:
        return "—"
    d = b - a
    return f"{'+' if d >= 0 else ''}{d:.2f}"


def print_report(ref_a: str, ref_b: str, art_a: dict, art_b: dict) -> None:
    print()
    print("=" * 72)
    print(f"Inception comparison: {ref_a} ({git_short_sha(ref_a)}) vs {ref_b} ({git_short_sha(ref_b)})")
    print("=" * 72)

    # Confidence
    print("\nConfidence")
    print("-" * 72)
    print(f"  {'Step':<14}  {ref_a:>22}  {ref_b:>22}  {'Δ':>6}")
    for name in ("workload", "architecture", "runtime"):
        a = art_a.get(f"{name}_confidence")
        b = art_b.get(f"{name}_confidence")
        print(f"  {name:<14}  {_fmt(a):>22}  {_fmt(b):>22}  {_delta(a, b):>6}")

    # Citations
    print("\nCitations to patterns/ entries in design_rationale.md")
    print("-" * 72)
    cites_a = art_a.get("citations", {})
    cites_b = art_b.get("citations", {})
    all_entries = sorted(set(cites_a) | set(cites_b))
    print(f"  {'Entry':<48}  {ref_a:>8}  {ref_b:>8}")
    for entry in all_entries:
        ca, cb = cites_a.get(entry, 0), cites_b.get(entry, 0)
        marker = ""
        if ca == 0 and cb > 0:
            marker = "  ← new"
        elif ca > 0 and cb == 0:
            marker = "  ← lost"
        elif cb > ca + 1:
            marker = "  ← up"
        print(f"  {entry:<48}  {ca:>8}  {cb:>8}{marker}")
    print(f"  {'TOTAL':<48}  {art_a.get('total_citations', 0):>8}  {art_b.get('total_citations', 0):>8}")

    # Length / depth
    print("\nLength / depth")
    print("-" * 72)
    for label, key in [
        ("design_rationale.md (chars)", "design_rationale_chars"),
        ("design_rationale.md (lines)", "design_rationale_lines"),
        ("architecture.md (chars)", "architecture_chars"),
        ("orchestrator.py (lines)", "orchestrator_lines"),
        ("eval/judge.py (lines)", "judge_lines"),
    ]:
        print(f"  {label:<32}  {_fmt(art_a.get(key)):>14}  {_fmt(art_b.get(key)):>14}")

    # Skill cut
    print("\nSkill cut")
    print("-" * 72)
    skills_a = set(art_a.get("skills", []))
    skills_b = set(art_b.get("skills", []))
    print(f"  count                              {len(skills_a):>14}  {len(skills_b):>14}")
    added = sorted(skills_b - skills_a)
    removed = sorted(skills_a - skills_b)
    if added:
        print(f"  added in {ref_b}: {', '.join(added)}")
    if removed:
        print(f"  removed from {ref_a}: {', '.join(removed)}")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def slug(ref: str) -> str:
    return ref.replace("/", "-")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True, help="Discovery session to run inception against")
    parser.add_argument("--ref-a", default="main", help="Baseline patterns/ ref (default: main)")
    parser.add_argument("--ref-b", required=True, help="Proposed patterns/ ref")
    parser.add_argument(
        "--output-root",
        default=str(PROJECT_ROOT / ".compare_inception"),
        help="Where to write per-ref agent_starter dirs (default: .compare_inception/; gitignored)",
    )
    parser.add_argument("--skip-ref-a", action="store_true", help="Skip ref-a's inception run; re-read its cached artifacts")
    parser.add_argument("--skip-ref-b", action="store_true", help="Skip ref-b's inception run; re-read its cached artifacts")
    args = parser.parse_args()

    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    a_dir = output_root / slug(args.ref_a)
    b_dir = output_root / slug(args.ref_b)

    a_patterns = a_dir / "_patterns"
    b_patterns = b_dir / "_patterns"

    if not args.skip_ref_a:
        print(f"\n→ ref-a ({args.ref_a}): extracting patterns/ and running inception")
        extract_patterns_at_ref(args.ref_a, a_patterns)
        run_inception(args.session_id, a_dir, a_patterns)

    if not args.skip_ref_b:
        print(f"\n→ ref-b ({args.ref_b}): extracting patterns/ and running inception")
        extract_patterns_at_ref(args.ref_b, b_patterns)
        run_inception(args.session_id, b_dir, b_patterns)

    art_a = load_artifacts(a_dir)
    art_b = load_artifacts(b_dir)
    print_report(args.ref_a, args.ref_b, art_a, art_b)


if __name__ == "__main__":
    main()
