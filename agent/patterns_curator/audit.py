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

The deterministic phase is a rule-per-rule lint against patterns/STYLE.md
(the production-entry contract). Each lint finding carries a rule id
(STYLE-1..7), the offending file, and a line number where pinpointable:

  STYLE-2 — status: validated without named evidence (§2); stale drafts (info)
  STYLE-3 — source_findings entries that aren't real findings/ files (§3)
  STYLE-4 — first-person / roadmap voice in entry bodies (§4)
  STYLE-5 — body citations + related/contradicts refs that don't resolve,
            or cite working-suffix files (§5, §7)
  STYLE-6 — frontmatter category != parent directory (§6)

Usage:
    uv run python -m agent.patterns_curator.audit
    uv run python -m agent.patterns_curator.audit --staleness-days 90
    uv run python -m agent.patterns_curator.audit --skip-semantic
    uv run python -m agent.patterns_curator.audit --lint-only   # no LLM, no creds
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


def _iter_canonical_entries(patterns_dir: Path = PATTERNS_DIR) -> list[tuple[str, str, Path]]:
    """Yield (category, slug, path) for every canonical entry.

    Skips drafts, candidates, contested, triage, repair files, READMEs,
    indexes, logs. Returns the durable wiki — what audit reasons about.
    """
    out: list[tuple[str, str, Path]] = []
    if not patterns_dir.exists():
        return out
    for category_dir in sorted(patterns_dir.iterdir()):
        if not category_dir.is_dir() or category_dir.name.startswith("."):
            continue
        for path in sorted(category_dir.iterdir()):
            if not path.name.endswith(".md"):
                continue
            if path.name.endswith((".draft.md", ".update.md", ".contested.md", ".candidate.md", ".triage.md", ".repair.md", ".reference.md")):
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
# Deterministic findings — the STYLE.md lint (patterns/STYLE.md is the
# production-entry contract; rule ids below reference its sections).
# ---------------------------------------------------------------------------

# §7 working suffixes — never citable, never canonical.
WORKING_SUFFIXES = (".draft", ".update", ".contested", ".candidate", ".triage", ".reference", ".repair")

# §4 voice lint — first-person / roadmap phrasing that has no place in an entry.
# NOTE: bare "this/next session" deliberately absent — it's legitimate
# memory-domain vocabulary ("persists to the next session", lifetime table
# cells) and produced only false positives on the first full-KB lint run.
VOICE_RE = re.compile(
    r"\b(my read|my recommendation|we found|we were told|our pipeline"
    r"|queued for next session|deferred to next session)\b",
    re.IGNORECASE,
)

# §5 — every `patterns/<cat>/<name>.md` string in a body must resolve.
BODY_CITATION_RE = re.compile(r"patterns/([A-Za-z0-9_-]+)/([A-Za-z0-9._-]+)\.md")


def _fm_key_line(text: str, key: str) -> int | None:
    """1-based line number of a top-level `key:` line in the frontmatter block."""
    for i, line in enumerate(text.splitlines(), start=1):
        if i > 1 and line == "---":  # end of frontmatter
            return None
        if line.startswith(f"{key}:"):
            return i
    return None


def _body_line_offset(text: str, body: str) -> int:
    """Number of file lines preceding the body (body is a suffix of text)."""
    return text[: len(text) - len(body)].count("\n")


def deterministic_audit(
    today_iso: str,
    staleness_days: int,
    survey_staleness_days: int,
    *,
    patterns_dir: Path = PATTERNS_DIR,
    project_root: Path = PROJECT_ROOT,
) -> list[AuditFinding]:
    """All non-LLM checks — runs without any LLM call. Frontmatter integrity,
    STYLE.md rule lint (status/provenance/voice/citations/category), fences,
    staleness, source-hash drift (if source file is reachable)."""
    findings: list[AuditFinding] = []
    all_slugs = {f"{cat}/{slug}" for cat, slug, _ in _iter_canonical_entries(patterns_dir)}
    today_dt = datetime.strptime(today_iso, "%Y-%m-%d").date()

    for category, slug, path in _iter_canonical_entries(patterns_dir):
        sluglabel = f"{category}/{slug}"
        try:
            rel_file = str(path.relative_to(project_root))
        except ValueError:
            rel_file = str(path)
        text = path.read_text()
        fm, body = _split_frontmatter(text)
        body_offset = _body_line_offset(text, body)

        # Frontmatter required fields (§1)
        for required_field in ("title", "category", "status", "last_updated"):
            if not fm.get(required_field):
                findings.append(
                    AuditFinding(
                        severity="error",
                        kind="frontmatter_violation",
                        slug=sluglabel,
                        description=f"required frontmatter field missing: `{required_field}`",
                        proposed_fix=f"add `{required_field}: <value>` to the YAML frontmatter",
                        rule="STYLE-1",
                        file=rel_file,
                        line=1,
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
                    rule="STYLE-1",
                    file=rel_file,
                    line=_fm_key_line(text, "last_updated"),
                )
            )

        source_findings = fm.get("source_findings") or []
        if isinstance(source_findings, str):
            source_findings = [source_findings]

        # (a) STYLE-2 — validated with no receipts section AND no source_findings.
        # "The sources were good" is not validation; validated MUST name evidence.
        has_receipt_section = bool(
            re.search(r"^##+\s+(Empirical anchor|Provenance)\b", body, flags=re.MULTILINE | re.IGNORECASE)
        )
        if fm.get("status") == "validated" and not has_receipt_section and not source_findings:
            findings.append(
                AuditFinding(
                    severity="warning",
                    kind="frontmatter_violation",
                    slug=sluglabel,
                    description=(
                        "status: validated but no `## Empirical anchor`/`## Provenance` section "
                        "and no source_findings — validated MUST name its evidence (§2)"
                    ),
                    proposed_fix="name the evidence (findings/NN, measured run, confirmed use) or downgrade status",
                    rule="STYLE-2",
                    file=rel_file,
                    line=_fm_key_line(text, "status"),
                )
            )

        # (c) STYLE-6 — frontmatter category must equal the parent directory.
        fm_category = fm.get("category")
        if fm_category and fm_category != category:
            findings.append(
                AuditFinding(
                    severity="error",
                    kind="frontmatter_violation",
                    slug=sluglabel,
                    description=f"frontmatter category `{fm_category}` != parent directory `{category}` (§6)",
                    proposed_fix=f"set `category: {category}` or move the file to `patterns/{fm_category}/`",
                    rule="STYLE-6",
                    file=rel_file,
                    line=_fm_key_line(text, "category"),
                )
            )

        # (f) STYLE-3 — source_findings lists ONLY real findings/NN-*.md files.
        for sf in source_findings:
            sf_clean = str(sf).strip().strip("'\"")
            sf_path = project_root / sf_clean
            if not sf_clean.startswith("findings/") or not sf_path.is_file():
                findings.append(
                    AuditFinding(
                        severity="error",
                        kind="provenance_violation",
                        slug=sluglabel,
                        description=(
                            f"source_findings contains `{sf_clean}` which is not a real findings/ file — "
                            "talks/papers/docs belong in source_external; never fabricate an origin (§3)"
                        ),
                        proposed_fix="move the citation to source_external, or fix the path to a real findings/NN-*.md",
                        rule="STYLE-3",
                        file=rel_file,
                        line=_fm_key_line(text, "source_findings"),
                    )
                )

        # (b) STYLE-4 — first-person / roadmap voice in the body.
        for i, body_line in enumerate(body.splitlines()):
            voice_match = VOICE_RE.search(body_line)
            if voice_match:
                findings.append(
                    AuditFinding(
                        severity="warning",
                        kind="style_violation",
                        slug=sluglabel,
                        description=(
                            f"first-person/roadmap voice `{voice_match.group(0)}` (§4): "
                            f"{body_line.strip()[:160]}"
                        ),
                        proposed_fix="rewrite as a timeless, third-person factual statement",
                        rule="STYLE-4",
                        file=rel_file,
                        line=body_offset + i + 1,
                    )
                )

        # (d) STYLE-5 — body citations must resolve; working-suffix files are never citable.
        for cite in BODY_CITATION_RE.finditer(body):
            cite_cat, cite_name = cite.group(1), cite.group(2)
            cite_line = body_offset + body[: cite.start()].count("\n") + 1
            if cite_name.endswith(WORKING_SUFFIXES):
                findings.append(
                    AuditFinding(
                        severity="error",
                        kind="reference_broken",
                        slug=sluglabel,
                        description=(
                            f"body cites working-suffix file `{cite.group(0)}` — "
                            "working files are not part of the canonical KB (§5, §7)"
                        ),
                        proposed_fix="cite the canonical entry (or drop the citation until promotion)",
                        rule="STYLE-5",
                        file=rel_file,
                        line=cite_line,
                    )
                )
            elif not (patterns_dir / cite_cat / f"{cite_name}.md").is_file():
                findings.append(
                    AuditFinding(
                        severity="error",
                        kind="reference_broken",
                        slug=sluglabel,
                        description=(
                            f"body cites `{cite.group(0)}` which doesn't resolve to a real file — "
                            "the `fabricated-citations` anti-pattern (§5)"
                        ),
                        proposed_fix="fix the slug to an existing entry or remove the citation",
                        rule="STYLE-5",
                        file=rel_file,
                        line=cite_line,
                    )
                )

        # (e) STYLE-5 — related/contradicts/superseded_by must resolve to canonical entries.
        for ref_field in ("related", "contradicts", "superseded_by"):
            ref_list = fm.get(ref_field) or []
            if isinstance(ref_list, str):
                ref_list = [ref_list]
            for ref in ref_list:
                full = ref.replace(".md", "")
                if full and not any(s == full or s.endswith(f"/{full}") for s in all_slugs):
                    findings.append(
                        AuditFinding(
                            severity="warning",
                            kind="reference_broken",
                            slug=sluglabel,
                            description=f"`{ref_field}[]` contains `{ref}` which doesn't resolve to any canonical entry (§5)",
                            proposed_fix="either fix the ref to point at an existing entry, or remove it",
                            rule="STYLE-5",
                            file=rel_file,
                            line=_fm_key_line(text, ref_field),
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
                    file=rel_file,
                )
            )

        # Staleness — (g) a stale `draft` gets a STYLE-2 note: it has sat
        # unvalidated past the threshold (promote, validate, or prune).
        threshold = survey_staleness_days if fm.get("category") == "harnesses" or "snapshot_date" in fm else staleness_days
        if lu:
            try:
                lu_dt = datetime.strptime(str(lu), "%Y-%m-%d").date()
                days_old = (today_dt - lu_dt).days
                if days_old > threshold:
                    is_draft = fm.get("status") == "draft"
                    findings.append(
                        AuditFinding(
                            severity="info",
                            kind="stale",
                            slug=sluglabel,
                            description=(
                                f"last_updated is {days_old} days ago (threshold {threshold})"
                                + ("; entry is still `draft` — unvalidated distillations shouldn't linger (§2)" if is_draft else "")
                            ),
                            proposed_fix=(
                                "re-read the source(s); if content still holds, bump last_updated. "
                                "if outdated, edit or mark deprecated."
                            ),
                            rule="STYLE-2" if is_draft else None,
                            file=rel_file,
                            line=_fm_key_line(text, "last_updated"),
                        )
                    )
            except ValueError:
                pass  # bad date already flagged above

        # Source-hash drift — only checkable if `source_findings` points at a local file
        source_hash = fm.get("source_hash")
        if source_hash and source_findings:
            source_path = project_root / str(source_findings[0])
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
            rule_tag = f"[{f.rule}] " if f.rule else ""
            lines.append(f"### {rule_tag}[{f.kind}] `{f.slug}`")
            if f.file:
                loc = f"{f.file}:{f.line}" if f.line else f.file
                lines.append(f"`{loc}`")
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
    parser.add_argument(
        "--lint-only",
        action="store_true",
        help=(
            "Fast path: run ONLY the deterministic STYLE.md lint — no LLM call, "
            "no API credentials needed. Equivalent to --skip-semantic."
        ),
    )
    args = parser.parse_args()

    report = asyncio.run(run_audit(
        staleness_days=args.staleness_days,
        survey_staleness_days=args.survey_staleness_days,
        skip_semantic=args.skip_semantic or args.lint_only,
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
