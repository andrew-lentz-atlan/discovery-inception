"""Patterns Curator — `promote` pipeline (cross-session knowledge promotion).

This is Loop 3 from plans/10. Distinct from `run.py`'s `ingest` pipeline:
- `ingest` reads ONE source document and produces one pattern draft.
- `promote` reads MANY per-session feedback files, clusters recurring signals,
  and produces zero-or-more candidate pattern drafts.

Workflow:

  1. Discover feedback files under sessions/ and agent_starter/feedback/
     (and any --feedback-dir overrides).
  2. Parse each feedback file → FeedbackSignal list (deterministic, no LLM).
  3. For each signal: specific_vs_generic_classifier (LLM, per-signal).
     Drop signals classified as specific.
  4. Cluster generic signals (single LLM call over the whole corpus).
  5. Apply recurrence threshold (≥3 distinct sessions by default).
  6. For each cluster above threshold: check existing patterns for overlap.
     If overlap → mark `duplicate_of_existing`, no draft written.
     Else → draft candidate pattern entry (LLM).
  7. Write each candidate to `patterns/<category>/<slug>.candidate.md`.
     Write the run report to `patterns/.promotion_runs/<timestamp>.json`.

The output is never auto-committed. Humans review `.candidate.md` files
before they're renamed to `.md` (experimental) or revised.

Feedback file format (YAML or JSON; either works):

  session_id: sess_abc
  stage: discovery | inception
  date: YYYY-MM-DD
  worked_as_proposed: ["..."]
  worked_with_modification: [{ item, description }]
  wrong_for_this_use_case: [{ item, what_we_did_instead, why }]
  missing: ["..."]
  lessons_free_text: |
    ...

Naming convention: feedback.yaml or feedback.json living inside a session
or inception-output directory. The discoverer walks recursively.

Usage:
    uv run python -m agent.patterns_curator.promote
    uv run python -m agent.patterns_curator.promote --min-sessions 2 \\
        --feedback-dir agent/inception/sample_feedback
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
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
    FeedbackSignal,
    PatternEntry,
    PromotionCandidate,
    PromotionRunReport,
    SignalClassification,
    SignalCluster,
    SignalClusteringResult,
)


PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
SESSIONS_DIR = PROJECT_ROOT / "sessions"
PATTERNS_DIR = PROJECT_ROOT / "patterns"
INCEPTION_FEEDBACK_DIR = PROJECT_ROOT / "agent" / "inception" / "sample_feedback"

# The recurrence threshold the plan recommends. Configurable via CLI for
# experimental relaxation (e.g. --min-sessions 1 surfaces every cluster for
# audit during early-stage curation).
DEFAULT_MIN_SESSIONS = 3

MODEL = os.environ.get("CURATOR_MODEL", "claude-haiku-4-5")


# ---------------------------------------------------------------------------
# Step 0 — discovery + parsing (deterministic; no LLM)
# ---------------------------------------------------------------------------


def _try_yaml_or_json(text: str) -> dict[str, Any]:
    """Parse YAML if PyYAML is available, else fall back to JSON.

    PyYAML is not a project dependency (deliberately keeping the install
    light). If a session writes feedback.yaml and PyYAML isn't installed,
    we surface a clear error rather than silently skipping the file.
    """
    text = text.strip()
    if not text:
        return {}
    # Try JSON first — JSON is a subset of YAML 1.2 so JSON files parse
    # under either path, but JSON-first means zero dependency on PyYAML
    # when feedback is JSON.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "feedback file is YAML but PyYAML is not installed. "
            "Install with `uv add pyyaml`, or write feedback as JSON."
        ) from exc
    return yaml.safe_load(text) or {}


def discover_feedback_files(roots: list[Path]) -> list[Path]:
    """Walk the given roots looking for feedback.{yaml,yml,json}.

    Order is sorted-by-path for reproducibility — same input layout always
    yields the same signal corpus order, which keeps clustering stable.
    """
    found: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("feedback.*")):
            if path.suffix in {".yaml", ".yml", ".json"}:
                found.append(path)
    return found


def parse_feedback_file(path: Path) -> list[FeedbackSignal]:
    """Read one feedback file and emit the FeedbackSignal list.

    Missing optional fields are tolerated. A file with no actionable signals
    returns an empty list rather than raising — common for session dirs that
    haven't been annotated yet.
    """
    raw = _try_yaml_or_json(path.read_text())
    if not raw:
        return []
    session_id = str(raw.get("session_id") or path.parent.name)
    stage = raw.get("stage") or "discovery"
    if stage not in ("discovery", "inception"):
        stage = "discovery"

    signals: list[FeedbackSignal] = []

    def _add(kind: str, content: str, target_area: str | None = None) -> None:
        if not content or not str(content).strip():
            return
        signals.append(
            FeedbackSignal(
                session_id=session_id,
                stage=stage,  # type: ignore[arg-type]
                kind=kind,  # type: ignore[arg-type]
                content=str(content).strip(),
                target_area=target_area,
            )
        )

    for item in raw.get("worked_as_proposed") or []:
        if isinstance(item, dict):
            _add("worked_as_proposed", item.get("item") or item.get("content") or "",
                 item.get("target_area"))
        else:
            _add("worked_as_proposed", str(item))

    for item in raw.get("worked_with_modification") or []:
        if isinstance(item, dict):
            content = f"{item.get('item','')}: {item.get('description','')}".strip(": ")
            _add("worked_with_modification", content, item.get("target_area"))
        else:
            _add("worked_with_modification", str(item))

    for item in raw.get("wrong_for_this_use_case") or []:
        if isinstance(item, dict):
            content = (
                f"{item.get('item','')}: replaced with {item.get('what_we_did_instead','')} "
                f"because {item.get('why','')}"
            ).strip()
            _add("wrong_for_this_use_case", content, item.get("target_area"))
        else:
            _add("wrong_for_this_use_case", str(item))

    for item in raw.get("missing") or []:
        if isinstance(item, dict):
            _add("missing", item.get("item") or item.get("content") or "", item.get("target_area"))
        else:
            _add("missing", str(item))

    free_text = raw.get("lessons_free_text") or raw.get("lessons_learned") or ""
    if isinstance(free_text, str) and free_text.strip():
        # Split paragraphs into individual lesson signals so each can be
        # classified separately. Aggressive splitting can pollute the corpus;
        # if a session has one big paragraph we treat it as one signal.
        paras = [p.strip() for p in free_text.split("\n\n") if p.strip()]
        for p in paras:
            _add("lesson", p)

    return signals


# ---------------------------------------------------------------------------
# Step 1 — specific_vs_generic_classifier (LLM, per-signal, parallel)
# ---------------------------------------------------------------------------


async def classify_signal(
    client: AsyncOpenAI, signal: FeedbackSignal
) -> SignalClassification:
    prompt = load_prompt(
        "promote_01_classify_signal.md",
        SESSION_ID=signal.session_id,
        STAGE=signal.stage,
        KIND=signal.kind,
        TARGET_AREA=signal.target_area or "(unspecified)",
        CONTENT=signal.content,
    )
    return await call_step(
        client,
        user_prompt=prompt,
        output_model=SignalClassification,
        max_tokens=512,
    )


async def classify_all(
    client: AsyncOpenAI, signals: list[FeedbackSignal], concurrency: int = 4
) -> list[SignalClassification]:
    sem = asyncio.Semaphore(concurrency)

    async def _one(s: FeedbackSignal) -> SignalClassification:
        async with sem:
            return await classify_signal(client, s)

    return await asyncio.gather(*[_one(s) for s in signals])


# ---------------------------------------------------------------------------
# Step 2 — signal_clusterer (LLM, single call over the corpus)
# ---------------------------------------------------------------------------


def _format_signals_block(signals: list[FeedbackSignal], classifications: list[SignalClassification]) -> str:
    lines: list[str] = []
    for i, (sig, cls) in enumerate(zip(signals, classifications)):
        lines.append(
            f"[{i}] session={sig.session_id} stage={sig.stage} kind={sig.kind} "
            f"generic_kind={cls.generic_kind} generalizes_to={cls.generalizes_to!r}\n"
            f"    content: {sig.content}"
        )
    return "\n".join(lines) if lines else "(no signals)"


async def cluster_signals(
    client: AsyncOpenAI,
    signals: list[FeedbackSignal],
    classifications: list[SignalClassification],
) -> SignalClusteringResult:
    if not signals:
        return SignalClusteringResult()
    prompt = load_prompt(
        "promote_02_cluster_signals.md",
        SIGNALS_BLOCK=_format_signals_block(signals, classifications),
    )
    return await call_step(
        client,
        user_prompt=prompt,
        output_model=SignalClusteringResult,
        max_tokens=2048,
    )


# ---------------------------------------------------------------------------
# Step 3 — duplicate-check against existing patterns/ (deterministic)
# ---------------------------------------------------------------------------


def _existing_pattern_slugs() -> set[str]:
    """Return all existing pattern slugs (filename stems) across categories.

    Used as a cheap duplicate-prevention gate: if a candidate slug already
    exists as a real (non-candidate, non-draft) entry, mark the cluster as
    `duplicate_of_existing` rather than overwriting. The semantic-overlap
    case (different slug, same lesson) is handled by humans during review.
    """
    out: set[str] = set()
    if not PATTERNS_DIR.exists():
        return out
    for path in PATTERNS_DIR.rglob("*.md"):
        # Skip drafts / candidates / templates so we don't double-count
        # ourselves on a re-run.
        if path.name.endswith(".draft.md") or path.name.endswith(".candidate.md"):
            continue
        if path.name in {"README.md", "SKILL.md"}:
            continue
        out.add(path.stem)
    return out


# ---------------------------------------------------------------------------
# Step 4 — draft candidate pattern entries (LLM, per-cluster)
# ---------------------------------------------------------------------------


async def draft_candidate(
    client: AsyncOpenAI,
    cluster: SignalCluster,
    signals: list[FeedbackSignal],
    classifications: list[SignalClassification],
    today: str,
) -> PatternEntry:
    """Produce one candidate PatternEntry from a cluster."""
    member_signals = [signals[i] for i in cluster.signal_indices]
    member_cls = [classifications[i] for i in cluster.signal_indices]
    # Pick the dominant generic_kind / generalizes_to from the members.
    # If members disagree, the clusterer was probably wrong; we still
    # produce a candidate but flag the disagreement in the rationale.
    kinds = [c.generic_kind for c in member_cls if c.generic_kind]
    generic_kind = max(set(kinds), key=kinds.count) if kinds else "skill_design"
    gen_to_candidates = [c.generalizes_to for c in member_cls if c.generalizes_to]
    generalizes_to = (
        max(set(gen_to_candidates), key=gen_to_candidates.count)
        if gen_to_candidates
        else cluster.theme
    )

    signals_block_lines: list[str] = []
    for sig in member_signals:
        signals_block_lines.append(
            f"- [{sig.session_id} / {sig.stage} / {sig.kind}] {sig.content}"
        )
    signals_block = "\n".join(signals_block_lines)

    session_ids_block = "\n  - ".join(sorted({s.session_id for s in member_signals}))

    prompt = load_prompt(
        "promote_03_draft_candidate.md",
        CLUSTER_ID=cluster.cluster_id,
        CLUSTER_THEME=cluster.theme,
        GENERIC_KIND=generic_kind,
        GENERALIZES_TO=generalizes_to,
        CROSSES_STAGES=str(cluster.crosses_stages),
        N_DISTINCT_SESSIONS=str(cluster.n_distinct_sessions),
        SIGNALS_BLOCK=signals_block,
        SESSION_IDS_BLOCK=session_ids_block,
        TODAY=today,
    )
    drafted = await call_step(
        client,
        user_prompt=prompt,
        output_model=PatternEntry,
        max_tokens=4096,
    )
    return drafted


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def run_promote(
    feedback_dirs: list[Path],
    *,
    min_sessions: int = DEFAULT_MIN_SESSIONS,
    dry_run: bool = False,
) -> PromotionRunReport:
    """Run the full promote pipeline. Returns a PromotionRunReport.

    `dry_run=True` skips writing any files to disk; the report is the only
    side effect. Useful for previewing what would promote.
    """
    client = _client()
    try:
        # 1. Discover + parse.
        feedback_files = discover_feedback_files(feedback_dirs)
        signals: list[FeedbackSignal] = []
        for path in feedback_files:
            signals.extend(parse_feedback_file(path))
        def _rel(d: Path) -> str:
            try:
                return str(d.relative_to(PROJECT_ROOT))
            except ValueError:
                return str(d)

        print(
            f"→ Found {len(feedback_files)} feedback files in "
            f"{[_rel(d) for d in feedback_dirs]}; "
            f"extracted {len(signals)} signals."
        )

        if not signals:
            return _empty_report(min_sessions)

        # 2. Per-signal classification (parallel).
        print("→ Classifying signals (specific vs generic)...")
        classifications = await classify_all(client, signals)
        n_generic = sum(1 for c in classifications if c.is_generic)
        print(f"   {n_generic}/{len(signals)} classified as generic.")

        generic_signals: list[FeedbackSignal] = []
        generic_classifications: list[SignalClassification] = []
        for sig, cls in zip(signals, classifications):
            if cls.is_generic:
                generic_signals.append(sig)
                generic_classifications.append(cls)

        if not generic_signals:
            print("→ No generic signals to cluster. Done.")
            return _empty_report(min_sessions, n_signals_scanned=len(signals))

        # 3. Cluster generic signals.
        print("→ Clustering generic signals...")
        clustering = await cluster_signals(client, generic_signals, generic_classifications)
        print(f"   {len(clustering.clusters)} clusters detected.")

        # 4. Apply threshold + duplicate-check + draft per cluster.
        existing_slugs = _existing_pattern_slugs()
        today = date.today().isoformat()
        candidates: list[PromotionCandidate] = []

        for cluster in clustering.clusters:
            # Recurrence gate
            if cluster.n_distinct_sessions < min_sessions:
                # Still record the cluster for diagnostics.
                candidates.append(
                    PromotionCandidate(
                        cluster_id=cluster.cluster_id,
                        n_distinct_sessions=cluster.n_distinct_sessions,
                        generic_kind=(
                            generic_classifications[cluster.signal_indices[0]].generic_kind
                            or "skill_design"
                        ),
                        generalizes_to=(
                            generic_classifications[cluster.signal_indices[0]].generalizes_to
                            or cluster.theme
                        ),
                        candidate_pattern=_placeholder_pattern(cluster, today),
                        suggested_path="(below recurrence threshold — no draft written)",
                        promotion_status="below_recurrence_threshold",
                    )
                )
                continue

            # Draft + duplicate check
            print(f"   → Drafting candidate for cluster '{cluster.cluster_id}' "
                  f"({cluster.n_distinct_sessions} sessions)...")
            try:
                pattern = await draft_candidate(
                    client, cluster, generic_signals, generic_classifications, today
                )
            except Exception as exc:
                print(f"     ! Draft failed: {exc}")
                continue

            slug = _slugify(pattern.frontmatter.title) or cluster.cluster_id
            status = "candidate"
            overlap_with: str | None = None
            if slug in existing_slugs:
                status = "duplicate_of_existing"
                overlap_with = slug
            suggested_path = (
                f"patterns/{pattern.frontmatter.category}/{slug}.candidate.md"
            )
            candidates.append(
                PromotionCandidate(
                    cluster_id=cluster.cluster_id,
                    n_distinct_sessions=cluster.n_distinct_sessions,
                    generic_kind=(
                        generic_classifications[cluster.signal_indices[0]].generic_kind
                        or "skill_design"
                    ),
                    generalizes_to=(
                        generic_classifications[cluster.signal_indices[0]].generalizes_to
                        or cluster.theme
                    ),
                    candidate_pattern=pattern,
                    suggested_path=suggested_path,
                    promotion_status=status,
                    overlap_with_existing=overlap_with,
                )
            )

            if status == "candidate" and not dry_run:
                _write_candidate_file(pattern, slug, suggested_path)

        report = PromotionRunReport(
            run_id=f"promo_{uuid.uuid4().hex[:8]}",
            run_at=datetime.now(timezone.utc).isoformat(),
            n_signals_scanned=len(signals),
            n_signals_generic=n_generic,
            n_clusters=len(clustering.clusters),
            n_clusters_above_threshold=sum(
                1 for c in clustering.clusters if c.n_distinct_sessions >= min_sessions
            ),
            recurrence_threshold=min_sessions,
            candidates=candidates,
        )

        if not dry_run:
            _write_run_report(report)

        return report
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client() -> AsyncOpenAI:
    base_url = os.environ.get("LITELLM_BASE_URL", "").strip()
    api_key = os.environ.get("LITELLM_API_KEY", "").strip()
    if not base_url or not api_key:
        raise RuntimeError("LITELLM_BASE_URL and LITELLM_API_KEY must be set in .env")
    return AsyncOpenAI(base_url=base_url, api_key=api_key)


def _slugify(s: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "-" for c in s)
    out = "-".join(p for p in out.split("-") if p)
    return out[:80]


def _placeholder_pattern(cluster: SignalCluster, today: str) -> PatternEntry:
    """Empty PatternEntry used as a placeholder when we record a below-threshold
    cluster — we still need a typed value in `candidate_pattern`."""
    from agent.patterns_curator.schemas import (
        AppliesWhen,
        PatternFrontmatter,
    )

    return PatternEntry(
        frontmatter=PatternFrontmatter(
            title=cluster.theme,
            category="decision-guides",
            status="experimental",
            last_updated=today,
            applies_when=AppliesWhen(),
        ),
        body=f"(Cluster below recurrence threshold — no draft written. "
        f"Theme: {cluster.theme}. {cluster.n_distinct_sessions} session(s).)",
        body_shape="operational-decision",
    )


def _empty_report(min_sessions: int, n_signals_scanned: int = 0) -> PromotionRunReport:
    return PromotionRunReport(
        run_id=f"promo_{uuid.uuid4().hex[:8]}",
        run_at=datetime.now(timezone.utc).isoformat(),
        n_signals_scanned=n_signals_scanned,
        n_signals_generic=0,
        n_clusters=0,
        n_clusters_above_threshold=0,
        recurrence_threshold=min_sessions,
        candidates=[],
    )


def _write_candidate_file(pattern: PatternEntry, slug: str, suggested_path: str) -> None:
    """Render a PatternEntry to <suggested_path> as markdown."""
    target = PROJECT_ROOT / suggested_path
    target.parent.mkdir(parents=True, exist_ok=True)

    fm = pattern.frontmatter
    fm_lines = [
        "---",
        f"title: {fm.title}",
        f"category: {fm.category}",
        f"status: {fm.status}",
        f"last_updated: {fm.last_updated}",
    ]
    if fm.source_findings:
        fm_lines.append("source_findings:")
        for s in fm.source_findings:
            fm_lines.append(f"  - {s}")
    if fm.source_external:
        fm_lines.append("source_external:")
        for s in fm.source_external:
            fm_lines.append(f"  - {s}")
    fm_lines.append("applies_when:")
    fm_lines.append("  workloads:")
    for w in fm.applies_when.workloads:
        fm_lines.append(f"    - {w}")
    fm_lines.append("  constraints:")
    for c in fm.applies_when.constraints:
        fm_lines.append(f"    - {c}")
    if fm.contradicts:
        fm_lines.append("contradicts:")
        for c in fm.contradicts:
            fm_lines.append(f"  - {c}")
    if fm.related:
        fm_lines.append("related:")
        for r in fm.related:
            fm_lines.append(f"  - {r}")
    fm_lines.append("---")

    body = pattern.body or ""
    text = "\n".join(fm_lines) + "\n\n" + body + "\n"
    target.write_text(text)
    print(f"     ✓ Wrote {suggested_path}")


def _write_run_report(report: PromotionRunReport) -> None:
    """Persist the run report for audit trail."""
    runs_dir = PATTERNS_DIR / ".promotion_runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = report.run_at.replace(":", "-").replace("+", "_")
    path = runs_dir / f"{stamp}_{report.run_id}.json"
    path.write_text(report.model_dump_json(indent=2))
    print(f"→ Run report: {path.relative_to(PROJECT_ROOT)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "patterns_curator promote — scan per-session feedback artifacts, "
            "cluster recurring signals, and produce candidate pattern entries."
        )
    )
    parser.add_argument(
        "--feedback-dir",
        action="append",
        type=Path,
        default=None,
        help=(
            "Override the default feedback discovery roots (sessions/ + "
            "agent/inception/sample_feedback/). Repeatable."
        ),
    )
    parser.add_argument(
        "--min-sessions",
        type=int,
        default=DEFAULT_MIN_SESSIONS,
        help=f"Recurrence threshold for promotion (default: {DEFAULT_MIN_SESSIONS}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write any files; print the report only.",
    )
    args = parser.parse_args()

    roots = args.feedback_dir or [SESSIONS_DIR, INCEPTION_FEEDBACK_DIR]
    report = asyncio.run(run_promote(
        feedback_dirs=roots,
        min_sessions=args.min_sessions,
        dry_run=args.dry_run,
    ))

    print()
    print("─" * 70)
    print(
        f"Scanned {report.n_signals_scanned} signals; "
        f"{report.n_signals_generic} generic; "
        f"{report.n_clusters} clusters; "
        f"{report.n_clusters_above_threshold} above the ≥{report.recurrence_threshold}-session threshold."
    )
    print(f"Candidates produced: {len(report.candidates)}")
    for c in report.candidates:
        flag = (
            "candidate"
            if c.promotion_status == "candidate"
            else c.promotion_status
        )
        print(
            f"  - [{flag}] {c.cluster_id} ({c.n_distinct_sessions} sessions) → "
            f"{c.suggested_path}"
        )


if __name__ == "__main__":
    main()
