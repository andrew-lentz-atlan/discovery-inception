"""Multi-artifact ingest pipeline — the artifact-first entry point.

This is the new first-class flow for discovery-inception. Replaces the
implicit assumption that every session starts with a blank slate by
treating the common case ("I have a call transcript and some docs")
as the primary entry point.

What it does, end to end:

  1. Run intake on each artifact in parallel → N RoleContexts.
  2. Merge the N RoleContexts → one combined RoleContext on disk.
  3. Run fact_extractor on each artifact in parallel → N FactExtractionResults.
  4. Initialize a DiscoverySession with the combined RoleContext as priors;
     populate the spec with the extracted facts.
  5. Render gap_list.md — the deterministic "here's what we still need
     to know" artifact the FDE acts on (either chat-fills herself or
     runs a discovery session against).

What it explicitly does NOT do:

  - Stream artifacts live (Granola-style real-time ingest). Out of scope
    for this pass — designed for "after the call, before the next call."
  - Auto-trigger discovery. The output is the spec + gap_list; the FDE
    decides whether to chat-fill or run a session.
  - Cross-artifact contradiction resolution. If artifact A says "100 ops/day"
    and artifact B says "1000 ops/day", both facts land in the spec under
    the same topic; downstream tension-detection (or the FDE) reconciles.

Usage:
    uv run python -m agent.ingest \\
        --use-case-seed "build SoCo agent for onboarding at TechCo" \\
        --artifact intake/sources/call-transcript.txt \\
        --artifact intake/sources/runbook.md \\
        --artifact intake/sources/slack-thread.md \\
        --role-id soco-techco

Outputs a session under sessions/<session_id>/ containing:
    session.json     — the DiscoverySession state (priors + spec + facts)
    spec.md          — human-readable spec snapshot
    gap_list.md      — what to ask next, ordered
    artifacts/<n>/   — copies of the original artifacts for traceability
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

from agent.artifacts import Artifact, normalize_artifact  # noqa: E402
from agent.orchestrator import call_sub_agent, load_prompt  # noqa: E402
from agent.schemas import (  # noqa: E402
    DiscoverySpec,
    DistilledFact,
    FactExtractionResult,
)
from agent.state import (  # noqa: E402
    ALL_CANONICAL_TOPICS,
    CANONICAL_CHECKLIST_TOPICS,
    TECHNICAL_TOPICS,
    DiscoverySession,
    MULTI_INSTANCE_REQUIREMENTS,
    topic_concern_thread,
)
from intake.run import run_intake  # noqa: E402
from intake.schemas import RoleContext, Unknown, Workflow  # noqa: E402


SKILLS_DIR = PROJECT_ROOT / "skills"
SESSIONS_DIR = PROJECT_ROOT / "sessions"

# Per-artifact extraction may run several facts; cap so a degenerate
# extraction doesn't flood the spec on one call. 50 is generous —
# real call transcripts cluster at 8–20 facts each.
MAX_FACTS_PER_ARTIFACT = 50


# ---------------------------------------------------------------------------
# Step 1: Multi-artifact intake (parallel)
# ---------------------------------------------------------------------------


async def run_intake_all(
    artifact_paths: list[Path],
    use_case_seed: str | None,
    artifacts_by_path: dict[Path, Artifact],
) -> tuple[list[RoleContext], list[tuple[Path, str]]]:
    """Run intake.run_intake on each artifact in parallel.

    Per-artifact failures are tolerated — non-role-shaped artifacts
    (knowledge-graph schemas, sample data files, dashboards) often have
    nothing for intake to extract and surface as empty `{}` JSON that
    fails Pydantic validation. Those failures must NOT crash the whole
    multi-artifact ingest; fact extraction may still succeed on the
    same artifacts (they're rich in technical-thread facts even when
    they have no role-level structure).

    Returns (successful_contexts, failures) where failures is a list of
    (path, error_summary) for caller-side logging.

    use_case_seed is propagated as the `--use-case` orientation to each
    artifact's intake call — keeps the role extractor anchored on the agent
    being built rather than drifting to the role most named in each file.
    """
    if not artifact_paths:
        return [], []

    async def _one(path: Path) -> RoleContext:
        # Source already normalized via the artifact seam in run_ingest; intake
        # consumes the universal normalized_text. (A rich modality's
        # structured_observations would be consumed here too once an extractor
        # produces them — see agent/artifacts.py.)
        artifact = artifacts_by_path[path]
        return await run_intake(
            artifact_text=artifact.normalized_text,
            source_filename=artifact.source_name,
            use_case=use_case_seed,
        )

    results = await asyncio.gather(
        *[_one(p) for p in artifact_paths],
        return_exceptions=True,
    )
    successes: list[RoleContext] = []
    failures: list[tuple[Path, str]] = []
    for path, result in zip(artifact_paths, results):
        if isinstance(result, BaseException):
            failures.append((path, _summarize_intake_failure(result)))
        else:
            successes.append(result)
    return successes, failures


def _summarize_intake_failure(exc: BaseException) -> str:
    """Compress noisy Pydantic-validation errors into a single-line diagnosis.

    The common case — an artifact that classifies as 'other' and yields an
    empty `{}` extraction — produces a 6-line Pydantic error block. Collapse
    that into 'not role-shaped (extraction yielded empty result)' so the
    warnings list stays readable. Other failure shapes pass through with a
    short head of the original message.
    """
    msg = str(exc)
    if "ExtractionResult" in msg and ("role_name" in msg or "role_summary" in msg) and (
        "Field required" in msg or "input_value={}" in msg or "Parsed JSON: {}" in msg
    ):
        return "not role-shaped (extraction yielded empty result; fact extraction still ran)"
    # Default: type + first 140 chars, one line.
    head = msg.splitlines()[0] if msg else ""
    return f"{type(exc).__name__}: {head[:140]}"


# ---------------------------------------------------------------------------
# Step 2: Merge RoleContexts
# ---------------------------------------------------------------------------


def merge_role_contexts(contexts: list[RoleContext], role_id: str) -> RoleContext:
    """Combine N RoleContexts into one.

    Merge policy (deliberately simple — we'd rather lose some signal than
    silently invent reconciliation rules):
      - role_name: the most-frequent value across inputs; first one wins on tie.
      - role_summary: longest non-empty summary.
      - primary_outcomes / unwritten_rules / source_artifacts: union, dedupe by string equality.
      - typical_workflows / decision_criteria / escalation_paths / common_edge_cases:
        concatenate; dedupe by (name + first-step) key where applicable.
      - domain_vocabulary: dict union; first definition wins on conflict.
      - flagged_unknowns: union, dedupe by field.
      - confidence_per_field: average per key.

    Per-file provenance is preserved by listing all source_artifacts; the
    spec downstream surfaces source filename next to each captured fact.
    """
    if not contexts:
        raise ValueError("merge_role_contexts: no contexts to merge")
    if len(contexts) == 1:
        return contexts[0]

    # role_name — most common; ties go to first.
    names = [c.role_name for c in contexts if c.role_name]
    role_name = max(set(names), key=names.count) if names else contexts[0].role_name

    # role_summary — longest non-empty.
    summaries = [c.role_summary for c in contexts if c.role_summary]
    role_summary = max(summaries, key=len) if summaries else ""

    # Simple unions with dedup.
    def _union(values: list[list[str]]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for v_list in values:
            for v in v_list:
                key = v.strip()
                if key and key not in seen:
                    seen.add(key)
                    out.append(v)
        return out

    primary_outcomes = _union([c.primary_outcomes for c in contexts])
    unwritten_rules = _union([c.unwritten_rules for c in contexts])
    source_artifacts = _union([c.source_artifacts for c in contexts])

    # Structured list merges — dedupe by name.
    def _dedupe_named(items: list[Any]) -> list[Any]:
        seen: set[str] = set()
        out: list[Any] = []
        for x in items:
            key = (getattr(x, "name", None) or getattr(x, "trigger", None) or "").lower().strip()
            if not key:
                out.append(x)
                continue
            if key in seen:
                continue
            seen.add(key)
            out.append(x)
        return out

    workflows = _dedupe_named([w for c in contexts for w in c.typical_workflows])
    decisions = _dedupe_named([d for c in contexts for d in c.decision_criteria])
    escalations = _dedupe_named([e for c in contexts for e in c.escalation_paths])
    edge_cases = [ec for c in contexts for ec in c.common_edge_cases]

    # Vocabulary — first definition wins on key conflict.
    vocab: dict[str, str] = {}
    for c in contexts:
        for term, defn in (c.domain_vocabulary or {}).items():
            if term not in vocab:
                vocab[term] = defn

    # Flagged unknowns — dedupe by field.
    seen_fields: set[str] = set()
    flagged: list[Unknown] = []
    for c in contexts:
        for u in c.flagged_unknowns:
            key = u.field.lower().strip()
            if key not in seen_fields:
                seen_fields.add(key)
                flagged.append(u)

    # Confidence — average per key across contexts that scored it.
    conf_acc: dict[str, list[float]] = {}
    for c in contexts:
        for k, v in (c.confidence_per_field or {}).items():
            conf_acc.setdefault(k, []).append(v)
    confidence = {k: sum(vs) / len(vs) for k, vs in conf_acc.items()}

    # target_use_case — take the most-frequent (should be identical when called
    # with a use-case seed; defensive).
    use_cases = [c.target_use_case for c in contexts if c.target_use_case]
    target_use_case = (
        max(set(use_cases), key=use_cases.count) if use_cases else None
    )

    return RoleContext(
        role_name=role_name,
        role_summary=role_summary,
        primary_outcomes=primary_outcomes,
        typical_workflows=workflows,
        decision_criteria=decisions,
        escalation_paths=escalations,
        domain_vocabulary=vocab,
        common_edge_cases=edge_cases,
        unwritten_rules=unwritten_rules,
        confidence_per_field=confidence,
        flagged_unknowns=flagged,
        source_artifacts=source_artifacts,
        target_use_case=target_use_case,
    )


# ---------------------------------------------------------------------------
# Step 3: Fact extraction per artifact (parallel)
# ---------------------------------------------------------------------------


async def extract_facts_from_artifact(
    client: AsyncOpenAI,
    artifact_text: str,
    use_case_seed: str,
) -> FactExtractionResult:
    """Run the fact_extractor sub-agent on one artifact."""
    prompt = load_prompt(
        "08_fact_extractor.md",
        USE_CASE_SEED=use_case_seed,
        ARTIFACT_TEXT=artifact_text,
    )
    result, _ms, _model = await call_sub_agent(
        client,
        sub_agent="distill",  # reuse the distill model slot — same task class (extract structured facts from prose)
        user_prompt=prompt,
        output_model=FactExtractionResult,
        max_tokens=4096,
    )
    # Cap absurd extractions defensively.
    if len(result.facts) > MAX_FACTS_PER_ARTIFACT:
        result.facts = result.facts[:MAX_FACTS_PER_ARTIFACT]
    return result


async def extract_facts_all(
    client: AsyncOpenAI,
    artifact_paths: list[Path],
    use_case_seed: str,
    artifacts_by_path: dict[Path, Artifact],
) -> tuple[list[tuple[Path, list[DistilledFact]]], list[tuple[Path, str]]]:
    """Extract facts from each artifact in parallel; tolerate per-artifact failures.

    Same resilience pattern as run_intake_all — one artifact's extraction
    failing must not block the others. Returns (successes, failures).
    """

    async def _one(path: Path) -> tuple[Path, list[DistilledFact]]:
        # Already normalized via the artifact seam; extract from normalized_text.
        artifact = artifacts_by_path[path]
        result = await extract_facts_from_artifact(client, artifact.normalized_text, use_case_seed)
        return (path, result.facts)

    results = await asyncio.gather(
        *[_one(p) for p in artifact_paths],
        return_exceptions=True,
    )
    successes: list[tuple[Path, list[DistilledFact]]] = []
    failures: list[tuple[Path, str]] = []
    for path, result in zip(artifact_paths, results):
        if isinstance(result, BaseException):
            failures.append((path, _summarize_intake_failure(result)))
        else:
            successes.append(result)
    return successes, failures


# ---------------------------------------------------------------------------
# Step 4: Populate the session + spec
# ---------------------------------------------------------------------------


def artifact_id_for(index: int, path: Path) -> str:
    """The stable per-artifact id: matches the stored copy filename under
    sessions/<id>/artifacts/ (see run_ingest's copy loop). Keeping the id and
    the on-disk copy name identical means a fact's `artifact_id` is a direct
    pointer to the preserved source — provenance you can actually follow."""
    return f"{index:02d}_{path.name}"


def build_session(
    use_case_seed: str,
    role_id: str | None,
    merged_role_context: RoleContext | None,
    facts_per_artifact: list[tuple[Path, list[DistilledFact]]],
    artifact_ids: dict[str, str] | None = None,
) -> DiscoverySession:
    """Create a fresh DiscoverySession; record facts with provenance; persist.

    `artifact_ids` maps a source Path (as string) to its stable artifact_id —
    computed once in run_ingest so the id matches the preserved copy filename.
    When absent (e.g. a direct unit-test caller), facts are recorded without an
    artifact_id, which is the same as live-discovery provenance.
    """
    spec = DiscoverySpec(use_case_seed=use_case_seed, role_id=role_id)
    session = DiscoverySession(spec=spec)

    # Record every extracted fact WITH its source artifact. The source Path is
    # no longer discarded here (it used to be `for _path, facts in ...`): each
    # fact now carries which artifact it came from, so a downstream consumer can
    # trace "this unwritten rule came from 02_screen-recording.txt".
    for path, facts in facts_per_artifact:
        aid = (artifact_ids or {}).get(str(path))
        for fact in facts:
            session.record_fact(fact, artifact_id=aid)

    # If RoleContext flagged unknowns, surface them as session gaps so the
    # gap_list and downstream discovery see them as questions to fill. We
    # don't dedup against existing topics here — flagged unknowns are
    # explicitly things the artifact didn't say, which is exactly what
    # belongs in gaps.
    if merged_role_context:
        from agent.schemas import FlaggedGap

        for u in merged_role_context.flagged_unknowns:
            session.flag_gap(
                FlaggedGap(
                    question=u.probe_suggestion or u.field,
                    why_it_matters=u.why_it_matters,
                    gap_type="untriaged",
                )
            )

    session.save()
    return session


# ---------------------------------------------------------------------------
# Step 5: Render the gap list (deterministic; no LLM)
# ---------------------------------------------------------------------------


def render_gap_list(
    session: DiscoverySession,
    role_context: RoleContext | None,
    artifact_paths: list[Path],
) -> str:
    """Render gap_list.md — the FDE-facing "what we still need to know" artifact.

    Three sections:

      1. Captured facts summary — what the ingest already covered, by topic
         (so the FDE knows what NOT to ask).
      2. Canonical-topic gaps — what's still missing from the conceptual +
         technical canonical checklists. The FDE either chat-fills these
         or schedules a discovery session.
      3. Source-flagged unknowns — explicit gaps the intake stage flagged
         in the artifacts themselves (the things the artifacts told us
         they didn't know).

    Output is markdown the FDE reads top to bottom. The order in section 2
    matters: load-bearing canonical topics (desired_outcome, success_metric,
    decision_point) come first.
    """
    spec = session.spec
    topic_facts: dict[str, list[str]] = {}
    for t in spec.topics:
        topic_facts.setdefault(t.topic, []).extend(fr.content for fr in t.facts)

    lines: list[str] = []
    lines.append(f"# Gap list — `{spec.use_case_seed}`")
    lines.append("")
    lines.append(f"**Session:** `{session.session_id}`")
    if artifact_paths:
        lines.append(f"**Artifacts ingested:** {len(artifact_paths)}")
        for p in artifact_paths:
            lines.append(f"  - `{p.name}`")
    n_facts = sum(len(f) for f in topic_facts.values())
    lines.append(f"**Facts captured:** {n_facts} across {len(topic_facts)} topics")
    lines.append("")

    # ---- Section 1: what we already know ----
    lines.append("## What the artifacts already told us")
    lines.append("")
    if not topic_facts:
        lines.append("*(none — no facts extracted from the artifacts. The ingest fact-extractor returned an empty list. Either the artifacts contained no use-case facts, or the extraction missed them — sample the artifacts directly to decide.)*")
        lines.append("")
    else:
        for thread_label, thread_topics in (
            ("Conceptual", CANONICAL_CHECKLIST_TOPICS),
            ("Technical", TECHNICAL_TOPICS),
        ):
            covered = [t for t in thread_topics if t in topic_facts]
            if not covered:
                continue
            lines.append(f"### {thread_label}")
            for topic in covered:
                lines.append(f"- `{topic}` — {len(topic_facts[topic])} fact(s) captured")
            lines.append("")
        # Custom topics (not in either canonical set)
        custom = [
            t for t in topic_facts
            if topic_concern_thread(t) == "other"
        ]
        if custom:
            lines.append("### Other captured topics")
            for topic in custom:
                lines.append(f"- `{topic}` — {len(topic_facts[topic])} fact(s) captured")
            lines.append("")

    # ---- Section 2: canonical-topic gaps ----
    lines.append("## What's still missing — load-bearing canonical topics")
    lines.append("")
    lines.append(
        "These are the canonical topics the inception pipeline expects in the spec. "
        "Where the artifacts didn't supply them, the FDE either chat-fills the answer "
        "(if known) or sets up a discovery session to ask."
    )
    lines.append("")

    def _emit_topic_gap(topic: str, *, required: int) -> None:
        n = len(topic_facts.get(topic, []))
        if n >= required:
            return
        thread = topic_concern_thread(topic)
        thread_label = thread.title()
        lines.append(
            f"- **[{thread_label}] `{topic}`** — need {required}, have {n}."
        )

    # Conceptual gaps first, then technical.
    for topic in CANONICAL_CHECKLIST_TOPICS:
        _emit_topic_gap(topic, required=MULTI_INSTANCE_REQUIREMENTS.get(topic, 1))
    for topic in TECHNICAL_TOPICS:
        _emit_topic_gap(topic, required=1)

    lines.append("")

    # ---- Section 3: source-flagged unknowns ----
    if role_context and role_context.flagged_unknowns:
        lines.append("## What the source artifacts flagged as unknown")
        lines.append("")
        lines.append(
            "These are explicit *\"we don't have data on this yet\"* statements "
            "the intake step picked up. They're already in the session's flagged "
            "gaps; surfaced here as an FDE checklist."
        )
        lines.append("")
        for u in role_context.flagged_unknowns:
            lines.append(f"- **{u.field}**")
            lines.append(f"  - Why it matters: {u.why_it_matters}")
            if u.probe_suggestion:
                lines.append(f"  - Probe: {u.probe_suggestion}")
            lines.append("")

    # ---- Footer: what to do next ----
    lines.append("---")
    lines.append("")
    lines.append("## What to do next")
    lines.append("")
    lines.append(
        "- **You know the answer to a gap?** Use `submit-turn --no-probe` to chat-fill it. "
        "The fact gets captured; the agent doesn't generate a follow-up question (saves "
        "cost + keeps your flow uninterrupted when you're filling multiple gaps in a row):"
    )
    lines.append("")
    lines.append(
        f"  `uv run python -m agent.cli submit-turn --no-probe --session-id {session.session_id} "
        f"--message \"<your answer phrased as if the customer said it>\"`"
    )
    lines.append("")
    lines.append(
        "- **The gap needs a real customer answer?** Schedule a follow-up; "
        "when ready, the same session resumes with the artifacts + already-captured facts "
        "as priors. Discovery's mega-agent will skip what's covered and focus on the gaps."
    )
    lines.append("")
    lines.append(
        f"- **Enough captured to scaffold?** `uv run python -m agent.cli finalize "
        f"--session-id {session.session_id}` produces spec.md + spec.json; pass that to the inception pipeline."
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


async def run_ingest(
    use_case_seed: str,
    artifact_paths: list[Path],
    role_id: str | None = None,
    save_role_context: bool = True,
) -> dict[str, Any]:
    """Run the full multi-artifact ingest pipeline.

    Returns a dict summarizing what happened (session_id, n_facts, etc).
    """
    if not artifact_paths:
        raise ValueError("run_ingest: at least one --artifact is required")

    # Validate + normalize up front so we fail fast. Directories and missing
    # files surface clean errors; everything else goes through the artifact
    # seam (agent/artifacts.py), which dispatches to a per-modality extractor
    # and produces a normalized Artifact. Normalizing ONCE here (rather than
    # re-reading in each downstream pass) matters for expensive future
    # extractors — a screen-recording extractor shouldn't transcribe 3x.
    artifacts_by_path: dict[Path, Artifact] = {}
    for p in artifact_paths:
        if not p.exists():
            raise FileNotFoundError(
                f"Artifact not found: {p}\n"
                f"Pass an absolute or relative path to a readable artifact."
            )
        if p.is_dir():
            raise IsADirectoryError(
                f"Artifact path is a directory, not a file: {p}\n"
                f"Pass each artifact as a separate --artifact <file>. "
                f"To ingest every file in a directory, expand it in shell first: "
                f"`for f in {p}/*; do … --artifact \"$f\"; done` (or similar)."
            )
        # normalize_artifact raises UnsupportedModalityError for binary / unknown
        # modalities, with an actionable message (the old "convert PDFs first"
        # case, now extended to "register an ArtifactExtractor for this modality").
        artifact = normalize_artifact(p)
        if not artifact.normalized_text.strip():
            raise ValueError(
                f"Artifact is empty: {p}\n"
                f"Skipping empty files would silently shrink the corpus, so we error "
                f"loudly instead. Remove the --artifact flag for this file, or fill it."
            )
        artifacts_by_path[p] = artifact

    client_base_url = os.environ.get("LITELLM_BASE_URL", "").strip()
    client_api_key = os.environ.get("LITELLM_API_KEY", "").strip()
    if not client_base_url or not client_api_key:
        raise RuntimeError(
            "LITELLM_BASE_URL and LITELLM_API_KEY must be set in .env"
        )
    client = AsyncOpenAI(base_url=client_base_url, api_key=client_api_key)

    try:
        # Step 1: intake on each artifact (parallel; per-artifact failures
        # are tolerated — non-role-shaped artifacts often have nothing to
        # extract and shouldn't tank the run).
        print(f"→ Step 1: intake on {len(artifact_paths)} artifact(s) (parallel)...")
        role_contexts, intake_failures = await run_intake_all(
            artifact_paths, use_case_seed, artifacts_by_path
        )
        if intake_failures:
            print(
                f"   ! {len(intake_failures)} of {len(artifact_paths)} artifact(s) "
                f"didn't produce a role context (not role-shaped, or extraction "
                f"failed). Fact extraction still runs on them."
            )
            for path, err in intake_failures:
                print(f"     - {path.name}: {err[:120]}")

        # Step 2: merge.
        merged = (
            merge_role_contexts(role_contexts, role_id or "ingest")
            if role_contexts
            else None
        )
        if merged:
            print(
                f"   merged into one RoleContext: "
                f"{len(merged.domain_vocabulary)} vocab terms, "
                f"{len(merged.unwritten_rules)} unwritten rules, "
                f"{len(merged.flagged_unknowns)} flagged unknowns."
            )
        else:
            print("   no role contexts produced — proceeding with stub priors.")

        # Step 3: fact extraction (parallel; same per-artifact tolerance).
        print(f"→ Step 2: fact extraction on {len(artifact_paths)} artifact(s) (parallel)...")
        facts_per_artifact, fact_failures = await extract_facts_all(
            client, artifact_paths, use_case_seed, artifacts_by_path
        )
        total_facts = sum(len(f) for _, f in facts_per_artifact)
        print(f"   {total_facts} fact(s) extracted across {len(facts_per_artifact)} artifact(s).")
        if fact_failures:
            print(f"   ! {len(fact_failures)} artifact(s) failed fact extraction:")
            for path, err in fact_failures:
                print(f"     - {path.name}: {err[:120]}")

        # Stable artifact ids, computed ONCE so the fact's artifact_id matches
        # the preserved copy filename below. Keyed by str(path) for the
        # build_session lookup.
        artifact_ids = {
            str(p): artifact_id_for(i, p) for i, p in enumerate(artifact_paths)
        }

        # Step 4: build the session + record facts (with provenance).
        print("→ Step 3: building session + recording facts...")
        session = build_session(
            use_case_seed=use_case_seed,
            role_id=role_id,
            merged_role_context=merged,
            facts_per_artifact=facts_per_artifact,
            artifact_ids=artifact_ids,
        )

        # Step 5: persist artifacts + merged RoleContext + gap_list.md.
        # The copy filename here MUST match artifact_id_for() above so each
        # fact's artifact_id resolves to a real file in artifacts/.
        session_dir = session.session_dir
        artifacts_dir = session_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        for i, p in enumerate(artifact_paths):
            target = artifacts_dir / artifact_id_for(i, p)
            shutil.copyfile(p, target)

        if merged and save_role_context and role_id:
            target_role_dir = SKILLS_DIR / role_id
            target_role_dir.mkdir(parents=True, exist_ok=True)
            (target_role_dir / "context.json").write_text(merged.model_dump_json(indent=2))
            print(f"   wrote merged RoleContext → skills/{role_id}/context.json")

        gap_md = render_gap_list(session, merged, artifact_paths)
        (session_dir / "gap_list.md").write_text(gap_md)
        print(f"   wrote gap_list.md → {(session_dir / 'gap_list.md').relative_to(PROJECT_ROOT)}")

        # Also dump a quick spec.md preview for inspection (re-renderable later).
        from agent.mcp_server.server import _render_spec_markdown

        (session_dir / "spec.md").write_text(_render_spec_markdown(session))

        response: dict[str, Any] = {
            "ok": True,
            "session_id": session.session_id,
            "use_case_seed": use_case_seed,
            "role_id": role_id,
            "n_artifacts": len(artifact_paths),
            "n_artifacts_intake_succeeded": len(role_contexts),
            "n_artifacts_facts_succeeded": len(facts_per_artifact),
            "n_facts_captured": total_facts,
            "n_topics_covered": len({t.topic for t in session.spec.topics}),
            "n_flagged_unknowns": len(session.spec.gaps),
            "session_dir": str(session_dir.relative_to(PROJECT_ROOT)),
            "gap_list_path": str((session_dir / "gap_list.md").relative_to(PROJECT_ROOT)),
            "spec_md_path": str((session_dir / "spec.md").relative_to(PROJECT_ROOT)),
            "next_step_hint": (
                f"Read sessions/{session.session_id}/gap_list.md. "
                f"Chat-fill answers via submit-turn, or run discovery against the gaps."
            ),
        }
        if intake_failures or fact_failures:
            response["warnings"] = []
            for path, err in intake_failures:
                response["warnings"].append(
                    f"intake skipped on {path.name}: {err[:200]}"
                )
            for path, err in fact_failures:
                response["warnings"].append(
                    f"fact extraction failed on {path.name}: {err[:200]}"
                )
        return response
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Ingest one or more artifacts (call transcripts, docs, slack threads, runbooks) "
            "into a discovery session. Produces a populated spec + a gap_list.md the FDE "
            "acts on (chat-fill or schedule discovery)."
        )
    )
    parser.add_argument(
        "--use-case-seed",
        required=True,
        help="One-line description of what the customer wants to build.",
    )
    parser.add_argument(
        "--artifact",
        action="append",
        required=True,
        type=Path,
        help=(
            "Path to one artifact (markdown, txt, etc.). Repeat for multiple artifacts. "
            "All artifacts are processed in parallel; their facts are merged into one session."
        ),
    )
    parser.add_argument(
        "--role-id",
        default=None,
        help=(
            "Optional slug for the role context. When set, the merged RoleContext is "
            "written to skills/<role_id>/context.json so the discovery agent can find it "
            "by id on follow-up sessions."
        ),
    )
    args = parser.parse_args()

    result = asyncio.run(run_ingest(
        use_case_seed=args.use_case_seed,
        artifact_paths=[p.resolve() for p in args.artifact],
        role_id=args.role_id,
    ))
    print()
    print("─" * 70)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
