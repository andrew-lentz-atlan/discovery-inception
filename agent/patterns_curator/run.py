"""Patterns Curator — ingest pipeline (full).

Reads a source artifact (a findings doc, an external research URL, a builder
report) and produces a draft pattern entry for the patterns/ knowledge base.

Six steps:
  1. classify_source       — what kind of pattern is this? (category + body shape)
  2. extract_pattern       — distill the source into structured pattern content
  3. draft_frontmatter     — YAML fields including applies_when, related, contradicts
  4. draft_body            — body-shape-templated markdown
  5. overlap_check         — TriageReport: create new / extend existing / contested
  6. validate              — deterministic frontmatter + reference integrity check

Drafter-not-publisher: the curator never writes to canonical `<slug>.md`.
Output lands as `.draft.md`, `.update.md`, `.contested.md`, or `.triage.md`
depending on the triage decision — humans review before promotion.

Convergence-not-fragmentation: when overlap_check is uncertain between
`create_new` and `update_existing`, it prefers `update_existing`. Adding
a near-duplicate entry is the worst outcome.

Usage:
    uv run python -m agent.patterns_curator.run \\
        --source findings/08-cheap-cascade-gpt4o-mini-doesnt-pan-out.md
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

from agent.patterns_curator.schemas import (  # noqa: E402
    AppliesWhen,
    BodyShape,
    ExtractedPattern,
    IngestRunReport,
    PatternCategory,
    PatternEntry,
    PatternFrontmatter,
    PatternStatus,
    SourceClassification,
    TriageReport,
)

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
MODEL = os.environ.get("CURATOR_MODEL", "claude-haiku-4-5")


# ---------------------------------------------------------------------------
# Plumbing (mirrors intake/run.py for consistency)
# ---------------------------------------------------------------------------

def _client() -> AsyncOpenAI:
    base_url = os.environ.get("LITELLM_BASE_URL", "").strip()
    api_key = os.environ.get("LITELLM_API_KEY", "").strip()
    if not base_url or not api_key:
        raise RuntimeError(
            "LITELLM_BASE_URL and LITELLM_API_KEY must be set in .env"
        )
    return AsyncOpenAI(base_url=base_url, api_key=api_key)


def load_prompt(name: str, **substitutions: str) -> str:
    """Load a prompt file from prompts/ and {KEY}-substitute."""
    text = (PROMPTS_DIR / name).read_text()
    for key, value in substitutions.items():
        text = text.replace("{" + key + "}", value)
    return text


def parse_json_response(content: str) -> dict | list:
    """Pull JSON out of a model response, tolerating ```json fences."""
    s = (content or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
    return json.loads(s)


async def call_step(
    client: AsyncOpenAI,
    *,
    user_prompt: str,
    output_model: type[BaseModel],
    max_tokens: int = 2048,
    temperature: float = 0.2,
) -> BaseModel:
    """One LLM call → validated Pydantic instance.

    Same shape as intake/run.py::call_step. We deliberately do NOT pass
    response_format={"type": "json_object"} — Claude follows the prompt's
    "output JSON only" instructions reliably without the structured-output
    flag, and the LiteLLM proxy is more reliable that way.
    """
    response = await client.chat.completions.create(
        model=MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[
            {
                "role": "system",
                "content": (
                    "You produce JSON output exactly as instructed by the user. "
                    "Output only the JSON object — no prose, no markdown fences, "
                    "no preamble or commentary. Begin your response with `{` and "
                    "end with `}`."
                ),
            },
            {"role": "user", "content": user_prompt},
        ],
    )
    raw = response.choices[0].message.content or ""
    if not raw.strip():
        raise ValueError(
            f"{output_model.__name__}: empty response from model. "
            f"finish_reason={response.choices[0].finish_reason!r}"
        )
    try:
        data = parse_json_response(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{output_model.__name__}: could not parse JSON — {exc}\n"
            f"Raw content (first 1200 chars):\n{raw[:1200]}"
        ) from exc
    try:
        return output_model.model_validate(data)
    except Exception as exc:
        raise ValueError(
            f"{output_model.__name__}: parsed JSON but validation failed — {exc}\n"
            f"Parsed JSON: {json.dumps(data, indent=2)[:1200]}\n"
            f"Raw content (first 1200 chars):\n{raw[:1200]}"
        ) from exc


# ---------------------------------------------------------------------------
# Step 1: classify_source — IMPLEMENTED
# ---------------------------------------------------------------------------

async def step_classify_source(
    client: AsyncOpenAI, source_text: str
) -> SourceClassification:
    """Classify the incoming source: what category + body shape it should become."""
    prompt = load_prompt("01_classify_source.md", SOURCE_TEXT=source_text)
    return await call_step(
        client,
        user_prompt=prompt,
        output_model=SourceClassification,
        max_tokens=1024,
    )


# ---------------------------------------------------------------------------
# Step 2: extract_pattern
# ---------------------------------------------------------------------------

async def step_extract_pattern(
    client: AsyncOpenAI,
    source_text: str,
    classification: SourceClassification,
) -> ExtractedPattern:
    """Distill source into structured pattern content. Body-shape-aware."""
    prompt = load_prompt(
        "02_extract_pattern.md",
        SOURCE_TEXT=source_text,
        TARGET_CATEGORY=classification.target_category,
        BODY_SHAPE=classification.body_shape,
        CANDIDATE_TITLE=classification.candidate_title,
        CANDIDATE_SLUG=classification.candidate_slug,
    )
    return await call_step(
        client,
        user_prompt=prompt,
        output_model=ExtractedPattern,
        max_tokens=4096,
    )


# ---------------------------------------------------------------------------
# Step 3: draft_frontmatter
# ---------------------------------------------------------------------------

async def step_draft_frontmatter(
    client: AsyncOpenAI,
    classification: SourceClassification,
    extracted: ExtractedPattern,
    source_filename: str,
    today: str,
) -> PatternFrontmatter:
    """Populate YAML frontmatter. applies_when / related / contradicts are
    LLM-decided; the rest is mostly deterministic from upstream outputs."""
    existing = _summarize_existing_entries()
    prompt = load_prompt(
        "03_draft_frontmatter.md",
        CLASSIFICATION_JSON=classification.model_dump_json(indent=2),
        EXTRACTED_PATTERN_JSON=extracted.model_dump_json(indent=2),
        SOURCE_FILENAME=source_filename,
        EXISTING_ENTRIES=existing,
        TODAY=today,
    )
    fm = await call_step(
        client,
        user_prompt=prompt,
        output_model=PatternFrontmatter,
        max_tokens=2048,
    )
    # Defensive: enforce the deterministic-from-upstream fields even if the
    # LLM drifted (it should not, but the prompt says these are decided).
    fm.title = classification.candidate_title
    fm.category = classification.target_category
    fm.last_updated = today
    return fm


# ---------------------------------------------------------------------------
# Step 4: draft_body
# ---------------------------------------------------------------------------

class _BodyOnly(BaseModel):
    body_md: str


async def step_draft_body(
    client: AsyncOpenAI,
    extracted: ExtractedPattern,
    frontmatter: PatternFrontmatter,
    body_shape: BodyShape,
) -> str:
    """Render the markdown body. Returns the body_md string only — the
    final entry is assembled (frontmatter + body) by the pipeline."""
    prompt = load_prompt(
        "04_draft_body.md",
        BODY_SHAPE=body_shape,
        TITLE=frontmatter.title,
        EXTRACTED_PATTERN_JSON=extracted.model_dump_json(indent=2),
        FRONTMATTER_JSON=frontmatter.model_dump_json(indent=2),
    )
    result = await call_step(
        client,
        user_prompt=prompt,
        output_model=_BodyOnly,
        max_tokens=8192,
    )
    return result.body_md


# ---------------------------------------------------------------------------
# Step 5: overlap_check → TriageReport
# ---------------------------------------------------------------------------

async def step_overlap_check(
    client: AsyncOpenAI,
    new_title: str,
    new_category: PatternCategory,
    new_body_shape: BodyShape,
    new_slug: str,
    new_frontmatter: PatternFrontmatter,
    new_body_md: str,
) -> TriageReport:
    """Decide whether the new draft creates a fresh entry, extends an
    existing one, or contradicts an existing one. Drafter-not-publisher:
    this report routes the output file; it never edits canonical entries."""
    existing_bundle = _bundle_existing_entries()
    prompt = load_prompt(
        "05_overlap_check.md",
        NEW_TITLE=new_title,
        NEW_CATEGORY=new_category,
        NEW_BODY_SHAPE=new_body_shape,
        NEW_SLUG=new_slug,
        NEW_FRONTMATTER_JSON=new_frontmatter.model_dump_json(indent=2),
        NEW_BODY_MD=new_body_md,
        EXISTING_ENTRIES_BUNDLE=existing_bundle,
    )
    return await call_step(
        client,
        user_prompt=prompt,
        output_model=TriageReport,
        max_tokens=4096,
    )


# ---------------------------------------------------------------------------
# Step 6: validate (deterministic; no LLM)
# ---------------------------------------------------------------------------

def step_validate(
    frontmatter: PatternFrontmatter,
    body_md: str,
    extracted: ExtractedPattern,
) -> tuple[list[str], list[str]]:
    """Deterministic frontmatter + content checks. No LLM call.

    Returns (errors, warnings). Errors should block ratification (the file
    still writes as a .draft/.update so the human can see what failed).
    Warnings are surfaced but non-blocking.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Required frontmatter fields
    if not frontmatter.title or len(frontmatter.title.strip()) < 5:
        errors.append("frontmatter.title is missing or implausibly short")
    if not frontmatter.last_updated:
        errors.append("frontmatter.last_updated is empty")
    elif not re.match(r"^\d{4}-\d{2}-\d{2}$", frontmatter.last_updated):
        errors.append(f"frontmatter.last_updated '{frontmatter.last_updated}' must be YYYY-MM-DD")

    # applies_when must have at least one workload OR one constraint
    aw = frontmatter.applies_when
    if not (aw.workloads or aw.constraints):
        warnings.append("frontmatter.applies_when has empty workloads AND constraints — entry will be hard to filter on")

    # validated status requires at least one empirical receipt
    if frontmatter.status == "validated" and not extracted.empirical_receipts:
        errors.append(
            "frontmatter.status='validated' but extracted.empirical_receipts is empty — "
            "downgrade to 'experimental' or add receipts before promoting"
        )

    # Body must start with `# <title>` to match existing convention
    body_lines = body_md.strip().splitlines()
    if not body_lines or not body_lines[0].startswith("# "):
        errors.append("body must start with `# <title>` heading")
    elif body_lines[0][2:].strip().lower() != frontmatter.title.lower():
        warnings.append(
            f"body's H1 heading does not match frontmatter.title "
            f"('{body_lines[0][2:].strip()}' vs '{frontmatter.title}')"
        )

    # Body length sanity check — 200 chars is suspiciously short
    if len(body_md.strip()) < 200:
        warnings.append(f"body is implausibly short ({len(body_md.strip())} chars) — likely truncated upstream")

    # Mermaid block balance (if any)
    mermaid_opens = len(re.findall(r"```mermaid", body_md))
    mermaid_closes_after = re.findall(r"```\s*$", body_md, flags=re.MULTILINE)
    total_fences = len(re.findall(r"^```", body_md, flags=re.MULTILINE))
    if total_fences % 2 != 0:
        errors.append(f"unbalanced code fences in body ({total_fences} ``` markers; should be even)")
    if mermaid_opens > 0 and mermaid_opens > len(mermaid_closes_after):
        warnings.append(
            f"{mermaid_opens} mermaid blocks open, {len(mermaid_closes_after)} closing fences detected — verify diagrams render"
        )

    # related: / contradicts: should point at existing entries
    all_slugs = _existing_slug_index()
    for ref_field, ref_list in [("related", frontmatter.related), ("contradicts", frontmatter.contradicts)]:
        for ref in ref_list:
            # Accept "<category>/<slug>" or just "<slug>"
            if "/" in ref:
                category_part, slug_part = ref.split("/", 1)
                full = f"{category_part}/{slug_part.replace('.md', '')}"
            else:
                full = ref.replace(".md", "")
            if not any(full.endswith(f"/{s}") or full == s for s in all_slugs):
                warnings.append(f"frontmatter.{ref_field}[]='{ref}' doesn't match any existing entry slug — broken reference")

    return errors, warnings


# ---------------------------------------------------------------------------
# Existing-entries helpers (used by step 3 + step 5)
# ---------------------------------------------------------------------------

def _existing_slug_index() -> set[str]:
    """Return set of all existing pattern slugs (filename stems, no .md)."""
    out: set[str] = set()
    patterns_dir = PROJECT_ROOT / "patterns"
    if not patterns_dir.exists():
        return out
    for path in patterns_dir.rglob("*.md"):
        if path.name.endswith(".draft.md") or path.name.endswith(".update.md") \
                or path.name.endswith(".contested.md") or path.name.endswith(".triage.md"):
            continue
        if path.name in {"README.md", "SKILL.md", "_index.md", "_log.md"}:
            continue
        out.add(path.stem)
    return out


def _summarize_existing_entries() -> str:
    """One-line summary per existing entry, for step 3's `related`/`contradicts` decision."""
    patterns_dir = PROJECT_ROOT / "patterns"
    if not patterns_dir.exists():
        return "(patterns/ directory not found)"
    lines: list[str] = []
    for category_dir in sorted(patterns_dir.iterdir()):
        if not category_dir.is_dir() or category_dir.name.startswith("."):
            continue
        for path in sorted(category_dir.iterdir()):
            if not path.name.endswith(".md") or path.name.endswith((".draft.md", ".update.md", ".contested.md", ".triage.md")):
                continue
            if path.name in {"README.md", "SKILL.md", "_index.md", "_log.md"}:
                continue
            # Extract title + first content paragraph
            text = path.read_text()
            title = path.stem
            body_summary = ""
            m = re.search(r"^title:\s*(.+)$", text, flags=re.MULTILINE)
            if m:
                title = m.group(1).strip()
            # First paragraph after the H1
            body_match = re.search(r"^#\s+.+\n+(.+?)(?:\n\n|\Z)", text, flags=re.MULTILINE | re.DOTALL)
            if body_match:
                body_summary = body_match.group(1).strip().replace("\n", " ")[:160]
            lines.append(f"`{category_dir.name}/{path.stem}` — {title} — {body_summary}")
    return "\n".join(lines) if lines else "(no existing entries yet)"


def _bundle_existing_entries() -> str:
    """Full content of all existing entries, for step 5's overlap check.

    Each entry is shown with slug, category, frontmatter, body. Bounded — we
    skip drafts / candidates / templates / READMEs.
    """
    patterns_dir = PROJECT_ROOT / "patterns"
    if not patterns_dir.exists():
        return "(no patterns/ directory found)"
    chunks: list[str] = []
    for category_dir in sorted(patterns_dir.iterdir()):
        if not category_dir.is_dir() or category_dir.name.startswith("."):
            continue
        for path in sorted(category_dir.iterdir()):
            if not path.name.endswith(".md") or path.name.endswith((".draft.md", ".update.md", ".contested.md", ".triage.md")):
                continue
            if path.name in {"README.md", "SKILL.md", "_index.md", "_log.md"}:
                continue
            chunks.append(
                f"### Entry: `{category_dir.name}/{path.stem}`\n\n{path.read_text()}"
            )
    return "\n\n---\n\n".join(chunks) if chunks else "(no existing entries yet)"


# ---------------------------------------------------------------------------
# Output assembly + file write
# ---------------------------------------------------------------------------

def _render_frontmatter_yaml(fm: PatternFrontmatter) -> str:
    """Serialize PatternFrontmatter to YAML matching the existing entries'
    convention (hand-formatted, not generic yaml.dump — preserves field order
    and the conventions we settled on)."""
    lines: list[str] = ["---"]
    lines.append(f"title: {fm.title}")
    lines.append(f"category: {fm.category}")
    lines.append(f"status: {fm.status}")
    lines.append(f"last_updated: {fm.last_updated}")
    if fm.source_findings:
        lines.append("source_findings:")
        for s in fm.source_findings:
            lines.append(f"  - {s}")
    else:
        lines.append("source_findings: []")
    if fm.source_external:
        lines.append("source_external:")
        for s in fm.source_external:
            lines.append(f"  - {s}")
    else:
        lines.append("source_external: []")
    lines.append("applies_when:")
    if fm.applies_when.workloads:
        lines.append("  workloads:")
        for w in fm.applies_when.workloads:
            lines.append(f"    - {w}")
    else:
        lines.append("  workloads: []")
    if fm.applies_when.constraints:
        lines.append("  constraints:")
        for c in fm.applies_when.constraints:
            lines.append(f"    - {c}")
    else:
        lines.append("  constraints: []")
    if fm.contradicts:
        lines.append("contradicts:")
        for c in fm.contradicts:
            lines.append(f"  - {c}")
    else:
        lines.append("contradicts: []")
    if fm.related:
        lines.append("related:")
        for r in fm.related:
            lines.append(f"  - {r}")
    else:
        lines.append("related: []")
    if fm.superseded_by:
        lines.append("superseded_by:")
        for s in fm.superseded_by:
            lines.append(f"  - {s}")
    if fm.snapshot_date:
        lines.append(f"snapshot_date: {fm.snapshot_date}")
    if fm.source_hash:
        lines.append(f"source_hash: {fm.source_hash}")
    lines.append("---")
    return "\n".join(lines)


def _render_triage_sidecar(triage: TriageReport, source_filename: str) -> str:
    """Human-readable triage report for the .triage.md sidecar file.

    Helps a human auditing the overlap_check decision see what the agent
    considered, what it concluded, and why.
    """
    lines: list[str] = [
        f"# Triage report — ingest of `{source_filename}`",
        "",
        f"**Recommended action:** `{triage.recommended_action}`  ",
        f"**Target:** `{triage.target_category}/{triage.target_slug}`",
        "",
        "## Rationale",
        "",
        triage.rationale,
        "",
    ]
    if triage.extension_candidates:
        lines.append("## Extension candidates")
        lines.append("")
        for c in triage.extension_candidates:
            lines.append(f"### `{c.existing_category}/{c.existing_slug}` (confidence {c.confidence:.2f})")
            lines.append("")
            lines.append(f"**Overlap:** {c.overlap_summary}")
            lines.append("")
            lines.append(f"**Proposed merge:** {c.proposed_merge}")
            lines.append("")
    if triage.contradiction_candidates:
        lines.append("## Contradiction candidates")
        lines.append("")
        for c in triage.contradiction_candidates:
            lines.append(f"### `{c.existing_category}/{c.existing_slug}` (confidence {c.confidence:.2f})")
            lines.append("")
            lines.append(f"**Contradiction:** {c.contradiction_summary}")
            lines.append("")
            if c.reconciliation_options:
                lines.append("**Reconciliation options:**")
                for o in c.reconciliation_options:
                    lines.append(f"- {o}")
                lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline — orchestrates steps 1-6 + writes outputs
# ---------------------------------------------------------------------------

async def run_ingest(source_text: str, source_filename: str) -> IngestRunReport:
    """Full ingest pipeline: classify → extract → draft frontmatter → draft body →
    overlap check → validate → write output file(s).

    Output routing (from triage.recommended_action):
      - `create_new`         → patterns/<category>/<slug>.draft.md
      - `update_existing`    → patterns/<category>/<existing_slug>.update.md + .triage.md
      - `contested`          → patterns/<category>/<existing_slug>.contested.md + .triage.md
      - `needs_human_review` → patterns/<category>/<slug>.triage.md ONLY (no draft)
    """
    client = _client()
    today = date.today().isoformat()
    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()[:16]

    try:
        # ---- Step 1: classify_source ----
        print("→ Step 1/6: classify_source...")
        classification = await step_classify_source(client, source_text)
        print(f"   target_category:  {classification.target_category}")
        print(f"   body_shape:       {classification.body_shape}")
        print(f"   candidate_title:  {classification.candidate_title}")
        print(f"   candidate_slug:   {classification.candidate_slug}")
        print(f"   confidence:       {classification.confidence:.2f}")

        # ---- Step 2: extract_pattern ----
        print()
        print("→ Step 2/6: extract_pattern...")
        extracted = await step_extract_pattern(client, source_text, classification)
        n_recipes = (
            (1 if extracted.summary else 0)
            + len(extracted.use_when)
            + len(extracted.dont_use_when)
            + len(extracted.gotchas)
            + len(extracted.empirical_receipts)
            + len(extracted.code_excerpts)
            + len(extracted.survey_items)
        )
        print(f"   extracted {n_recipes} content elements")
        print(f"     use_when={len(extracted.use_when)} dont_use_when={len(extracted.dont_use_when)} "
              f"gotchas={len(extracted.gotchas)} receipts={len(extracted.empirical_receipts)} "
              f"code_excerpts={len(extracted.code_excerpts)} survey_items={len(extracted.survey_items)}")

        # ---- Step 3: draft_frontmatter ----
        print()
        print("→ Step 3/6: draft_frontmatter...")
        frontmatter = await step_draft_frontmatter(
            client, classification, extracted, source_filename, today
        )
        # Attach the source hash + snapshot_date for surveys
        frontmatter.source_hash = source_hash
        if classification.body_shape == "comparative-survey" and not frontmatter.snapshot_date:
            frontmatter.snapshot_date = today
        print(f"   status:           {frontmatter.status}")
        print(f"   applies_when:     workloads={len(frontmatter.applies_when.workloads)} "
              f"constraints={len(frontmatter.applies_when.constraints)}")
        print(f"   related:          {frontmatter.related or '(none)'}")
        print(f"   contradicts:      {frontmatter.contradicts or '(none)'}")

        # ---- Step 4: draft_body ----
        print()
        print("→ Step 4/6: draft_body...")
        body_md = await step_draft_body(client, extracted, frontmatter, classification.body_shape)
        print(f"   body length:      {len(body_md)} chars")

        # ---- Step 5: overlap_check ----
        print()
        print("→ Step 5/6: overlap_check...")
        triage = await step_overlap_check(
            client,
            new_title=classification.candidate_title,
            new_category=classification.target_category,
            new_body_shape=classification.body_shape,
            new_slug=classification.candidate_slug,
            new_frontmatter=frontmatter,
            new_body_md=body_md,
        )
        print(f"   action:           {triage.recommended_action}")
        print(f"   target:           {triage.target_category}/{triage.target_slug}")
        print(f"   extensions:       {len(triage.extension_candidates)}")
        print(f"   contradictions:   {len(triage.contradiction_candidates)}")

        # ---- Step 6: validate ----
        print()
        print("→ Step 6/6: validate (deterministic)...")
        errors, warnings = step_validate(frontmatter, body_md, extracted)
        if errors:
            print(f"   ! {len(errors)} error(s):")
            for e in errors:
                print(f"     - {e}")
        if warnings:
            print(f"   ! {len(warnings)} warning(s):")
            for w in warnings:
                print(f"     - {w}")
        if not errors and not warnings:
            print("   clean")

        # ---- Output file routing ----
        category_dir = PROJECT_ROOT / "patterns" / triage.target_category
        category_dir.mkdir(parents=True, exist_ok=True)

        frontmatter_yaml = _render_frontmatter_yaml(frontmatter)
        full_entry = f"{frontmatter_yaml}\n\n{body_md.strip()}\n"

        triage_sidecar_path: Path | None = None

        if triage.recommended_action == "create_new":
            output_path = category_dir / f"{triage.target_slug}.draft.md"
            output_path.write_text(full_entry)
            if triage.extension_candidates or triage.contradiction_candidates:
                # Surface overlap analysis even on create_new if anything came up
                triage_sidecar_path = category_dir / f"{triage.target_slug}.triage.md"
                triage_sidecar_path.write_text(_render_triage_sidecar(triage, source_filename))

        elif triage.recommended_action == "update_existing":
            output_path = category_dir / f"{triage.target_slug}.update.md"
            output_path.write_text(full_entry)
            triage_sidecar_path = category_dir / f"{triage.target_slug}.triage.md"
            triage_sidecar_path.write_text(_render_triage_sidecar(triage, source_filename))

        elif triage.recommended_action == "contested":
            output_path = category_dir / f"{triage.target_slug}.contested.md"
            output_path.write_text(full_entry)
            triage_sidecar_path = category_dir / f"{triage.target_slug}.triage.md"
            triage_sidecar_path.write_text(_render_triage_sidecar(triage, source_filename))

        else:  # needs_human_review
            output_path = category_dir / f"{triage.target_slug}.triage.md"
            output_path.write_text(_render_triage_sidecar(triage, source_filename))
            triage_sidecar_path = output_path

        rel_output = str(output_path.relative_to(PROJECT_ROOT))
        rel_triage = str(triage_sidecar_path.relative_to(PROJECT_ROOT)) if triage_sidecar_path else None

        print()
        print(f"→ Wrote: {rel_output}")
        if rel_triage and rel_triage != rel_output:
            print(f"        + {rel_triage}")

        return IngestRunReport(
            ok=len(errors) == 0,
            source_filename=source_filename,
            classification_summary=(
                f"{classification.target_category}/{classification.body_shape}/"
                f"{classification.candidate_slug}"
            ),
            triage_action=triage.recommended_action,
            output_path=rel_output,
            triage_path=rel_triage,
            validate_errors=errors,
            validate_warnings=warnings,
        )
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Patterns Curator — ingest a source artifact into a draft pattern entry."
    )
    parser.add_argument(
        "--source",
        required=True,
        type=Path,
        help=(
            "Path to the source artifact (markdown file). The artifact is read in full "
            "and passed to the classify_source step."
        ),
    )
    args = parser.parse_args()

    source_path: Path = args.source.resolve()
    if not source_path.exists():
        raise SystemExit(f"Source not found: {source_path}")

    source_text = source_path.read_text()
    if not source_text.strip():
        raise SystemExit(f"Source is empty: {source_path}")

    result = asyncio.run(run_ingest(source_text, source_filename=source_path.name))

    print()
    print("─" * 70)
    print(json.dumps(result.model_dump(), indent=2))


if __name__ == "__main__":
    main()
