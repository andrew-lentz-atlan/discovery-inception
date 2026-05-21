"""Intake agent — runs the 6-step CaaS pipeline against a single artifact.

Uses the OpenAI SDK pointed at Atlan's LiteLLM proxy (same pattern as
experiment/ and job-search/). claude-haiku-4-5 is the worker model —
small, fast, cheap, and reliable at structured JSON output.

Each step is one LLM call with one tightly-scoped prompt and one Pydantic
output type. They share the source artifact in their context but produce
different slices of the output. No multi-agent orchestration — just a
focused pipeline of small focused calls.

Required env vars (set in your shell or in discovery-inception/.env):
    LITELLM_BASE_URL    Atlan's LiteLLM proxy URL
    LITELLM_API_KEY     Your LiteLLM proxy API key

Usage:
    uv run python -m intake.run \\
        --artifact intake/sources/sc-role.md \\
        --role-id solutions-consultant
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

from intake.schemas import (  # noqa: E402
    ClassificationResult,
    ConfidenceReport,
    ExtractionResult,
    GapReport,
    RoleContext,
    UnwrittenRulesResult,
    VocabularyResult,
)

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
MODEL = "claude-haiku-4-5"


def _client() -> AsyncOpenAI:
    base_url = os.environ.get("LITELLM_BASE_URL", "").strip()
    api_key = os.environ.get("LITELLM_API_KEY", "").strip()
    if not base_url or not api_key:
        raise RuntimeError(
            "LITELLM_BASE_URL and LITELLM_API_KEY must be set "
            "(in your shell or in discovery-inception/.env). "
            "See .env.example for the format."
        )
    return AsyncOpenAI(base_url=base_url, api_key=api_key)


# ---------------------------------------------------------------------------
# Prompt + JSON helpers
# ---------------------------------------------------------------------------

def load_prompt(name: str, **substitutions: str) -> str:
    """Load a prompt file from prompts/ and {KEY}-substitute."""
    text = (PROMPTS_DIR / name).read_text()
    for key, value in substitutions.items():
        text = text.replace("{" + key + "}", value)
    return text


def use_case_orientation(use_case: str | None) -> str:
    """Build the orientation block injected into oriented prompts (steps 2, 4, 5).

    When `use_case` is provided, the block tells the extractor to target the
    persona of the agent's user — not the artifact's speakers / narrators /
    incidentally-named roles. When None, returns a passive line that keeps
    behavior identical to pre-orientation runs (backward compatible).
    """
    if not use_case or not use_case.strip():
        return (
            "## Target use case orientation\n\n"
            "*(No target use case specified — extract the role most clearly "
            "described in the artifact.)*"
        )
    return (
        "## Target use case orientation\n\n"
        "You are extracting priors for an agent being built for this target use case:\n\n"
        f"> {use_case.strip()}\n\n"
        "The artifact you're reading may contain people other than the target user "
        "— e.g., this could be a scoping conversation where the target user isn't "
        "speaking. Extract the persona, workflows, decisions, and rules of the "
        "**target user of the agent**, NOT of the artifact's speakers, narrators, "
        "or roles mentioned in passing.\n\n"
        "If the artifact doesn't contain enough information about the target user, "
        "leave fields empty and flag them in `flagged_unknowns`. Do NOT fill gaps "
        "with details about non-target roles."
    )


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
    max_tokens: int = 4096,
    temperature: float = 0.2,
    max_retries: int = 3,
) -> BaseModel:
    """One LLM call → validated Pydantic instance, with retry/backoff.

    Retries on the failure modes we actually see in the wild:
      - empty response from the proxy (sporadic LiteLLM hiccup)
      - response truncated mid-string (finish_reason='length' — we
        automatically bump max_tokens on the retry so it can fit)
      - malformed JSON
      - parses-as-JSON but doesn't match the schema (rare with Claude
        but still possible)

    Bias is toward shipping a result rather than tanking the whole ingest
    on one transient hiccup. Three attempts; backoff is 0.75s × attempt.

    Note on response_format: we deliberately do NOT pass
    `response_format={"type": "json_object"}`. When LiteLLM proxies that
    OpenAI-shaped param to Claude, it can result in the model returning
    a minimal `{}` instead of following the prompt's schema. Claude
    follows the prompt's "output JSON only" instructions reliably without
    needing the structured-output flag — keep the prompt strict and
    parse with our existing fence-tolerant JSON parser.
    """
    last_error: Exception | None = None
    current_max_tokens = max_tokens

    for attempt in range(max_retries + 1):
        if attempt > 0:
            await asyncio.sleep(0.75 * attempt)
        response = await client.chat.completions.create(
            model=MODEL,
            max_tokens=current_max_tokens,
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
        finish_reason = response.choices[0].finish_reason

        if not raw.strip():
            last_error = ValueError(
                f"{output_model.__name__}: empty response on attempt {attempt+1} "
                f"(finish_reason={finish_reason!r})"
            )
            continue

        # Truncation detection: if the proxy returned finish_reason='length' OR
        # the JSON parse fails AND we have headroom, bump tokens and retry.
        try:
            data = parse_json_response(raw)
        except json.JSONDecodeError as exc:
            last_error = ValueError(
                f"{output_model.__name__}: could not parse JSON on attempt {attempt+1} "
                f"(finish_reason={finish_reason!r}) — {exc}\n"
                f"Raw content (first 600 chars):\n{raw[:600]}"
            )
            if finish_reason == "length" and current_max_tokens < 16384:
                current_max_tokens = min(current_max_tokens * 2, 16384)
            continue

        try:
            return output_model.model_validate(data)
        except Exception as exc:
            last_error = ValueError(
                f"{output_model.__name__}: parsed JSON but validation failed on "
                f"attempt {attempt+1} — {exc}\n"
                f"Parsed JSON: {json.dumps(data, indent=2)[:600]}"
            )
            continue

    if last_error is not None:
        raise last_error
    raise RuntimeError(
        f"{output_model.__name__}: unreachable — exhausted retries with no error"
    )


# ---------------------------------------------------------------------------
# The six steps
# ---------------------------------------------------------------------------

async def step_classify(client: AsyncOpenAI, artifact: str) -> ClassificationResult:
    prompt = load_prompt("01_classifier.md", ARTIFACT_TEXT=artifact)
    return await call_step(
        client, user_prompt=prompt, output_model=ClassificationResult, max_tokens=512
    )


async def step_extract(
    client: AsyncOpenAI,
    artifact: str,
    artifact_type: str,
    use_case: str | None = None,
) -> ExtractionResult:
    prompt = load_prompt(
        "02_extractor.md",
        ARTIFACT_TEXT=artifact,
        ARTIFACT_TYPE=artifact_type,
        USE_CASE_CONTEXT=use_case_orientation(use_case),
    )
    return await call_step(
        client, user_prompt=prompt, output_model=ExtractionResult, max_tokens=8192
    )


async def step_normalize_vocabulary(
    client: AsyncOpenAI, artifact: str, extraction: ExtractionResult
) -> VocabularyResult:
    prompt = load_prompt(
        "03_vocabulary_normalizer.md",
        ARTIFACT_TEXT=artifact,
        EXTRACTION_JSON=extraction.model_dump_json(indent=2),
    )
    return await call_step(
        client, user_prompt=prompt, output_model=VocabularyResult, max_tokens=8192
    )


async def step_sniff_unwritten_rules(
    client: AsyncOpenAI, artifact: str, use_case: str | None = None
) -> UnwrittenRulesResult:
    prompt = load_prompt(
        "04_unwritten_rules_sniffer.md",
        ARTIFACT_TEXT=artifact,
        USE_CASE_CONTEXT=use_case_orientation(use_case),
    )
    return await call_step(
        client, user_prompt=prompt, output_model=UnwrittenRulesResult, max_tokens=3000
    )


async def step_report_gaps(
    client: AsyncOpenAI,
    artifact: str,
    combined: dict,
    use_case: str | None = None,
) -> GapReport:
    prompt = load_prompt(
        "05_gap_reporter.md",
        ARTIFACT_TEXT=artifact,
        COMBINED_EXTRACTION_JSON=json.dumps(combined, indent=2),
        USE_CASE_CONTEXT=use_case_orientation(use_case),
    )
    return await call_step(
        client, user_prompt=prompt, output_model=GapReport, max_tokens=4000
    )


async def step_score_confidence(
    client: AsyncOpenAI, artifact: str, full_extraction: dict
) -> ConfidenceReport:
    prompt = load_prompt(
        "06_confidence_scorer.md",
        ARTIFACT_TEXT=artifact,
        FULL_EXTRACTION_JSON=json.dumps(full_extraction, indent=2),
    )
    return await call_step(
        client, user_prompt=prompt, output_model=ConfidenceReport, max_tokens=2000
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

async def run_intake(
    artifact_text: str,
    source_filename: str,
    use_case: str | None = None,
) -> RoleContext:
    client = _client()
    try:
        if use_case:
            print(f"→ Target use case: {use_case}")
        print("→ Step 1/6: classifying artifact...")
        classification = await step_classify(client, artifact_text)
        print(f"   type={classification.artifact_type} (confidence={classification.confidence:.2f})")
        print(f"   rationale: {classification.rationale}")

        print("→ Step 2/6: extracting structure...")
        extraction = await step_extract(
            client, artifact_text, classification.artifact_type, use_case=use_case
        )
        print(
            f"   role={extraction.role_name}; workflows={len(extraction.typical_workflows)}; "
            f"decisions={len(extraction.decision_criteria)}; "
            f"escalations={len(extraction.escalation_paths)}"
        )

        print("→ Step 3/6: normalizing vocabulary...")
        vocab = await step_normalize_vocabulary(client, artifact_text, extraction)
        print(f"   terms={len(vocab.domain_vocabulary)}; merges={len(vocab.synonyms_collapsed)}")

        print("→ Step 4/6: sniffing unwritten rules...")
        unwritten = await step_sniff_unwritten_rules(client, artifact_text, use_case=use_case)
        print(f"   rules captured: {len(unwritten.rules)}")

        combined = {
            **extraction.model_dump(),
            "domain_vocabulary": vocab.domain_vocabulary,
            "unwritten_rules": unwritten.rules,
        }

        print("→ Step 5/6: reporting gaps...")
        gaps = await step_report_gaps(client, artifact_text, combined, use_case=use_case)
        print(f"   gaps flagged: {len(gaps.flagged_unknowns)}")

        ctx = RoleContext(
            role_name=extraction.role_name,
            role_summary=extraction.role_summary,
            primary_outcomes=extraction.primary_outcomes,
            typical_workflows=extraction.typical_workflows,
            decision_criteria=extraction.decision_criteria,
            escalation_paths=extraction.escalation_paths,
            domain_vocabulary=vocab.domain_vocabulary,
            common_edge_cases=extraction.common_edge_cases,
            unwritten_rules=unwritten.rules,
            flagged_unknowns=gaps.flagged_unknowns,
            source_artifacts=[source_filename],
            target_use_case=use_case,
        )

        print("→ Step 6/6: scoring confidence...")
        confidence = await step_score_confidence(client, artifact_text, ctx.model_dump())
        ctx.confidence_per_field = confidence.confidence_per_field
        print(f"   scored {len(confidence.confidence_per_field)} fields")

        return ctx
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Run intake against a single artifact.")
    parser.add_argument(
        "--artifact",
        required=True,
        type=Path,
        help="Path to the artifact text file (markdown or plain text).",
    )
    parser.add_argument(
        "--role-id",
        required=True,
        help="Slug used for the output directory under --output-dir. e.g. solutions-consultant",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "skills",
        help="Where to write the produced skill (default: discovery-inception/skills).",
    )
    parser.add_argument(
        "--use-case",
        default=None,
        help=(
            "Optional one-liner describing the agent being built. When provided, the "
            "extractor / unwritten-rules sniffer / gap reporter orient toward the target "
            "user of that agent rather than anchoring on whichever role is most "
            "explicitly named in the artifact. Use when the artifact is a meta-document "
            "(scoping call, design doc, transcript) rather than the target user's own "
            "runbook. Example: --use-case \"Brand analyst agent that answers questions "
            "like 'Why did Gain lose share at Target?' using AOS market share data.\""
        ),
    )
    args = parser.parse_args()

    artifact_path: Path = args.artifact.resolve()
    if not artifact_path.exists():
        raise SystemExit(f"Artifact not found: {artifact_path}")

    artifact_text = artifact_path.read_text()
    if not artifact_text.strip():
        raise SystemExit(f"Artifact is empty: {artifact_path}")

    out_dir: Path = (args.output_dir / args.role_id).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "source").mkdir(exist_ok=True)
    shutil.copy(artifact_path, out_dir / "source" / artifact_path.name)

    ctx = asyncio.run(
        run_intake(
            artifact_text,
            source_filename=artifact_path.name,
            use_case=args.use_case,
        )
    )

    out_path = out_dir / "context.json"
    out_path.write_text(ctx.model_dump_json(indent=2))
    print(f"\n✓ Wrote {out_path}")
    print(f"  Source copied to {out_dir / 'source' / artifact_path.name}")


if __name__ == "__main__":
    main()
