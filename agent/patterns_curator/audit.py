"""Patterns Curator — audit operation (Loop 3's hygiene partner).

Distinct from `ingest` (one source → one draft) and `promote` (cross-
session signals → candidate patterns). The audit operation periodically
scans the existing wiki for hygiene issues that accumulate over time:

  - Frontmatter violations (deterministic)
  - Broken references (deterministic)
  - Fence imbalance (deterministic)
  - Staleness (deterministic; `last_updated` / `snapshot_date` past threshold)
  - Source-hash drift (deterministic; if `source_hash` is set, re-hash the
    source if reachable and flag if it's changed)
  - Semantic duplicates (LLM call — convergence principle violated)
  - Semantic contradictions (LLM call — two entries make opposing claims)

Two-phase pattern from theafh's wiki_auto_shaper:
  1. Assess — collect findings
  2. Fix — stage `.repair.md` proposals for the actionable findings

Auto-resolution is NOT in scope. The audit drafts proposed fixes; a human
reviews and decides. Same drafter-not-publisher principle as ingest.

Output:
  patterns/.audit_runs/<timestamp>/
    report.md       — human-readable findings
    report.json     — machine-readable findings
    <slug>.repair.md  — one per actionable finding (deferred MVP; first pass
                        just produces the report, repair drafting is stubbed
                        for now)

Usage:
    uv run python -m agent.patterns_curator.audit
    uv run python -m agent.patterns_curator.audit --staleness-days 90
    uv run python -m agent.patterns_curator.audit --skip-semantic
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

from agent.patterns_curator.run import call_step, load_prompt  # noqa: E402
from agent.patterns_curator.schemas import (  # noqa: E402
    AuditFinding,
    AuditRunReport,
)


PATTERNS_DIR = PROJECT_ROOT / "patterns"
AUDIT_RUNS_DIR = PATTERNS_DIR / ".audit_runs"

# Staleness defaults. Both can be overridden via CLI.
DEFAULT_STALENESS_DAYS = 90
DEFAULT_SURVEY_STALENESS_DAYS = 60  # survey entries date faster


# ---------------------------------------------------------------------------
# Helpers — discover entries, parse frontmatter
# ---------------------------------------------------------------------------


def _iter_canonical_entries() -> list[tuple[str, str, Path]]:
    """Yield (category, slug, path) for every canonical entry.

    Skips drafts, candidates, contested, triage, repair files, READMEs,
    indexes, logs. Returns the durable wiki — what audit reasons about.
    """
    out: list[tuple[str, str, Path]] = []
    if not PATTERNS_DIR.exists():
        return out
    for category_dir in sorted(PATTERNS_DIR.iterdir()):
        if not category_dir.is_dir() or category_dir.name.startswith("."):
            continue
        for path in sorted(category_dir.iterdir()):
            if not path.name.endswith(".md"):
                continue
            if path.name.endswith((".draft.md", ".update.md", ".contested.md", ".triage.md", ".repair.md", ".reference.md")):
                continue
            if path.name in {"README.md", "SKILL.md", "_index.md", "_log.md"}:
                continue
            out.append((category_dir.name, path.stem, path))
    return out


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Naïve YAML-frontmatter splitter. Returns (frontmatter_dict, body).

    Only handles the conventions used in our patterns/ entries (top-level
    scalars + simple lists + the applies_when nested dict). Doesn't handle
    arbitrary YAML.
    """
    if not text.startswith("---\n"):
        return {}, text
    end_match = re.search(r"\n---\n", text[4:])
    if not end_match:
        return {}, text
    fm_text = text[4 : 4 + end_match.start()]
    body = text[4 + end_match.end():]

    fm: dict[str, Any] = {}
    current_key: str | None = None
    current_list: list[str] | None = None
    in_applies_when = False
    aw_subkey: str | None = None

    for raw_line in fm_text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line.startswith("  - ") and current_list is not None and not in_applies_when:
            current_list.append(line[4:].strip())
            continue
        if line.startswith("    - ") and in_applies_when and aw_subkey is not None:
            fm.setdefault("applies_when", {}).setdefault(aw_subkey, []).append(line[6:].strip())
            continue
        if line.startswith("  ") and in_applies_when:
            # subkey within applies_when
            sub_match = re.match(r"^  (\w+):\s*(.*)$", line)
            if sub_match:
                aw_subkey = sub_match.group(1)
                rest = sub_match.group(2).strip()
                fm.setdefault("applies_when", {}).setdefault(aw_subkey, [])
                if rest == "[]":
                    pass  # empty list explicit
                continue
        # Top-level
        in_applies_when = False
        m = re.match(r"^(\w+):\s*(.*)$", line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        if key == "applies_when":
            in_applies_when = True
            current_key = key
            current_list = None
            fm["applies_when"] = {"workloads": [], "constraints": []}
            continue
        if value == "[]":
            fm[key] = []
            current_list = None
        elif value == "":
            fm[key] = []
            current_list = fm[key]
        elif value.startswith("[") and value.endswith("]"):
            # Inline YAML list syntax: `key: [a, b, c]`. Our existing entries
            # use this form for short related/contradicts lists. Split on
            # commas, strip whitespace + quotes.
            inner = value[1:-1].strip()
            if not inner:
                fm[key] = []
            else:
                fm[key] = [item.strip().strip("'\"") for item in inner.split(",")]
            current_list = None
        else:
            fm[key] = value
            current_list = None
    return fm, body


# ---------------------------------------------------------------------------
# Deterministic findings
# ---------------------------------------------------------------------------


def deterministic_audit(
    today_iso: str,
    staleness_days: int,
    survey_staleness_days: int,
) -> list[AuditFinding]:
    """All non-LLM checks. Frontmatter integrity, references, fences,
    staleness, source-hash drift (if source file is reachable)."""
    findings: list[AuditFinding] = []
    all_slugs = {f"{cat}/{slug}" for cat, slug, _ in _iter_canonical_entries()}
    today_dt = datetime.strptime(today_iso, "%Y-%m-%d").date()

    for category, slug, path in _iter_canonical_entries():
        sluglabel = f"{category}/{slug}"
        text = path.read_text()
        fm, body = _split_frontmatter(text)

        # Frontmatter required fields
        for required_field in ("title", "category", "status", "last_updated"):
            if not fm.get(required_field):
                findings.append(
                    AuditFinding(
                        severity="error",
                        kind="frontmatter_violation",
                        slug=sluglabel,
                        description=f"required frontmatter field missing: `{required_field}`",
                        proposed_fix=f"add `{required_field}: <value>` to the YAML frontmatter",
                    )
                )

        # last_updated format
        lu = fm.get("last_updated")
        if lu and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(lu)):
            findings.append(
                AuditFinding(
                    severity="warning",
                    kind="frontmatter_violation",
                    slug=sluglabel,
                    description=f"last_updated `{lu}` is not YYYY-MM-DD format",
                    proposed_fix="reformat to YYYY-MM-DD",
                )
            )

        # validated status w/ no empirical receipts (heuristic — check body for "Empirical anchor")
        if fm.get("status") == "validated" and "Empirical anchor" not in body and "empirical anchor" not in body.lower():
            findings.append(
                AuditFinding(
                    severity="warning",
                    kind="frontmatter_violation",
                    slug=sluglabel,
                    description="status: validated but no `Empirical anchor` section in body — receipts may be missing",
                    proposed_fix="either add an Empirical anchor section, or downgrade status to experimental",
                )
            )

        # References (related + contradicts)
        for ref_field in ("related", "contradicts", "superseded_by"):
            ref_list = fm.get(ref_field) or []
            if isinstance(ref_list, str):
                ref_list = [ref_list]
            for ref in ref_list:
                if "/" in ref:
                    full = ref.replace(".md", "")
                else:
                    full = ref.replace(".md", "")
                if full and not any(s == full or s.endswith(f"/{full}") for s in all_slugs):
                    findings.append(
                        AuditFinding(
                            severity="warning",
                            kind="reference_broken",
                            slug=sluglabel,
                            description=f"`{ref_field}[]` contains `{ref}` which doesn't resolve to any existing entry",
                            proposed_fix=f"either fix the ref to point at an existing entry, or remove it",
                        )
                    )

        # Fence balance
        n_fences = len(re.findall(r"^```", body, flags=re.MULTILINE))
        if n_fences % 2 != 0:
            findings.append(
                AuditFinding(
                    severity="error",
                    kind="fence_imbalance",
                    slug=sluglabel,
                    description=f"body has {n_fences} ``` markers (odd; should be even)",
                    proposed_fix="locate the unclosed fence and add the closing ```",
                )
            )

        # Staleness
        threshold = survey_staleness_days if fm.get("category") == "harnesses" or "snapshot_date" in fm else staleness_days
        if lu:
            try:
                lu_dt = datetime.strptime(str(lu), "%Y-%m-%d").date()
                days_old = (today_dt - lu_dt).days
                if days_old > threshold:
                    findings.append(
                        AuditFinding(
                            severity="info",
                            kind="stale",
                            slug=sluglabel,
                            description=f"last_updated is {days_old} days ago (threshold {threshold})",
                            proposed_fix=(
                                "re-read the source(s); if content still holds, bump last_updated. "
                                "if outdated, edit or mark deprecated."
                            ),
                        )
                    )
            except ValueError:
                pass  # bad date already flagged above

        # Source-hash drift — only checkable if `source_findings` points at a local file
        source_hash = fm.get("source_hash")
        source_findings = fm.get("source_findings") or []
        if source_hash and source_findings:
            source_path = PROJECT_ROOT / str(source_findings[0])
            if source_path.exists():
                current_hash = hashlib.sha256(source_path.read_text().encode("utf-8")).hexdigest()[:16]
                if current_hash != source_hash:
                    findings.append(
                        AuditFinding(
                            severity="info",
                            kind="source_hash_drift",
                            slug=sluglabel,
                            description=(
                                f"source file has changed since this entry was ingested "
                                f"(recorded hash {source_hash}, current {current_hash})"
                            ),
                            proposed_fix=(
                                f"re-ingest the source with `agent.patterns_curator.run --source "
                                f"{source_findings[0]}` and review the resulting `.update.md`"
                            ),
                        )
                    )

    return findings


# ---------------------------------------------------------------------------
# Semantic findings (LLM-driven)
# ---------------------------------------------------------------------------


class _SemanticFindings(BaseModel):
    findings: list[AuditFinding]


async def semantic_audit(
    client: AsyncOpenAI,
    deterministic_findings: list[AuditFinding],
    today: str,
) -> list[AuditFinding]:
    """Run the semantic clustering / contradiction-detection pass over
    the full wiki. One LLM call; the prompt bundles all entries."""
    bundle_chunks: list[str] = []
    for category, slug, path in _iter_canonical_entries():
        bundle_chunks.append(f"### Entry: `{category}/{slug}`\n\n{path.read_text()}")
    bundle = "\n\n---\n\n".join(bundle_chunks) or "(no entries)"

    det_summary = "\n".join(
        f"- [{f.severity}] {f.slug}: {f.kind} — {f.description}"
        for f in deterministic_findings[:30]
    ) or "(no deterministic findings)"

    prompt = load_prompt(
        "audit_semantic_scan.md",
        DETERMINISTIC_FINDINGS=det_summary,
        ALL_ENTRIES_BUNDLE=bundle,
        TODAY=today,
    )
    result = await call_step(
        client,
        user_prompt=prompt,
        output_model=_SemanticFindings,
        max_tokens=4096,
    )
    return result.findings


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _client() -> AsyncOpenAI:
    base_url = os.environ.get("LITELLM_BASE_URL", "").strip()
    api_key = os.environ.get("LITELLM_API_KEY", "").strip()
    if not base_url or not api_key:
        raise RuntimeError("LITELLM_BASE_URL and LITELLM_API_KEY must be set in .env")
    return AsyncOpenAI(base_url=base_url, api_key=api_key)


def _render_report_md(report: AuditRunReport) -> str:
    """Human-readable audit report."""
    lines: list[str] = [
        f"# Audit run — {report.run_at}",
        "",
        f"**Run id:** `{report.run_id}`  ",
        f"**Entries scanned:** {report.n_entries_scanned}  ",
        f"**Findings:** {report.n_findings} ({report.n_errors} errors, {report.n_warnings} warnings, {report.n_info} info)",
        "",
    ]
    if not report.findings:
        lines.append("Wiki is clean — no findings.")
        return "\n".join(lines)

    # Group by severity
    for severity in ("error", "warning", "info"):
        bucket = [f for f in report.findings if f.severity == severity]
        if not bucket:
            continue
        lines.append(f"## {severity.title()}s ({len(bucket)})")
        lines.append("")
        for f in bucket:
            lines.append(f"### [{f.kind}] `{f.slug}`")
            if f.also_affects:
                lines.append(f"**Also affects:** {', '.join(f'`{s}`' for s in f.also_affects)}")
            lines.append("")
            lines.append(f.description)
            lines.append("")
            if f.proposed_fix:
                lines.append(f"**Proposed fix:** {f.proposed_fix}")
                lines.append("")
    return "\n".join(lines)


async def run_audit(
    *,
    staleness_days: int = DEFAULT_STALENESS_DAYS,
    survey_staleness_days: int = DEFAULT_SURVEY_STALENESS_DAYS,
    skip_semantic: bool = False,
) -> AuditRunReport:
    """Run the audit pipeline. Writes a report under
    `patterns/.audit_runs/<timestamp>/` and returns the structured report."""
    today_iso = date.today().isoformat()
    started = datetime.now(timezone.utc).isoformat()

    print("→ Phase 1/2: deterministic scan (frontmatter, refs, fences, staleness, source-hash)...")
    det_findings = deterministic_audit(today_iso, staleness_days, survey_staleness_days)
    print(f"   {len(det_findings)} deterministic finding(s)")

    semantic_findings: list[AuditFinding] = []
    if skip_semantic:
        print("→ Phase 2/2: semantic scan SKIPPED (--skip-semantic)")
    else:
        print("→ Phase 2/2: semantic scan (duplicate + contradiction detection)...")
        client = _client()
        try:
            semantic_findings = await semantic_audit(client, det_findings, today_iso)
        finally:
            await client.close()
        print(f"   {len(semantic_findings)} semantic finding(s)")

    all_findings = det_findings + semantic_findings

    report = AuditRunReport(
        run_id=f"audit_{uuid.uuid4().hex[:8]}",
        run_at=started,
        n_entries_scanned=len(_iter_canonical_entries()),
        n_findings=len(all_findings),
        n_errors=sum(1 for f in all_findings if f.severity == "error"),
        n_warnings=sum(1 for f in all_findings if f.severity == "warning"),
        n_info=sum(1 for f in all_findings if f.severity == "info"),
        findings=all_findings,
        staged_repairs=[],  # repair-drafting stubbed for v1
    )

    # Persist report
    AUDIT_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = started.replace(":", "-").replace("+", "_")
    run_dir = AUDIT_RUNS_DIR / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.md").write_text(_render_report_md(report))
    (run_dir / "report.json").write_text(report.model_dump_json(indent=2))

    print()
    print(f"→ Report: {run_dir.relative_to(PROJECT_ROOT)}/report.md")
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="patterns_curator audit — periodic hygiene scan of the patterns/ wiki."
    )
    parser.add_argument(
        "--staleness-days",
        type=int,
        default=DEFAULT_STALENESS_DAYS,
        help=f"Flag entries whose last_updated is older than this. Default: {DEFAULT_STALENESS_DAYS}.",
    )
    parser.add_argument(
        "--survey-staleness-days",
        type=int,
        default=DEFAULT_SURVEY_STALENESS_DAYS,
        help=(
            f"Lower threshold for survey-shaped entries (harnesses/, snapshot_date present) "
            f"since they date faster. Default: {DEFAULT_SURVEY_STALENESS_DAYS}."
        ),
    )
    parser.add_argument(
        "--skip-semantic",
        action="store_true",
        help="Skip the LLM-based semantic clustering pass. Use when you only want deterministic checks.",
    )
    args = parser.parse_args()

    report = asyncio.run(run_audit(
        staleness_days=args.staleness_days,
        survey_staleness_days=args.survey_staleness_days,
        skip_semantic=args.skip_semantic,
    ))

    print()
    print("─" * 70)
    print(
        f"Scanned {report.n_entries_scanned} entries; "
        f"{report.n_findings} finding(s): "
        f"{report.n_errors} errors / {report.n_warnings} warnings / {report.n_info} info"
    )


if __name__ == "__main__":
    main()
