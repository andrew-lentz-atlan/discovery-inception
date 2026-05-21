"""Patterns Curator — ingest pipeline (skeleton).

Reads a source artifact (a findings doc, an external research URL, a builder
report) and produces a draft pattern entry for the patterns/ knowledge base.

Current scope: step 1 (classify_source) is implemented. Steps 2-5 are
stubbed; implementing them is the next iteration of this pipeline.

Usage:
    uv run python -m agent.patterns_curator.run \\
        --source findings/05-v08-probe-sharpener-and-tensions.md
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

from agent.patterns_curator.schemas import (  # noqa: E402
    SourceClassification,
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
# Steps 2-5: STUBS (raise NotImplementedError)
# ---------------------------------------------------------------------------

async def step_extract_pattern(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError(
        "step_extract_pattern is not yet implemented. "
        "Next iteration of the curator will extract use_when / dont_use_when / "
        "gotchas / empirical_receipts / code_excerpts / survey_items per the body shape."
    )


async def step_draft_frontmatter(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError(
        "step_draft_frontmatter is not yet implemented. "
        "Will populate the standardized YAML fields including applies_when, contradicts, related."
    )


async def step_draft_body(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError(
        "step_draft_body is not yet implemented. "
        "Will compose the body using the body_shape selected in step 1."
    )


async def step_validate(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError(
        "step_validate is not yet implemented. "
        "Will check for required frontmatter fields, summary, and (for validated status) "
        "at least one empirical receipt."
    )


# ---------------------------------------------------------------------------
# Pipeline (currently terminates after step 1 + emits classification only)
# ---------------------------------------------------------------------------

async def run_ingest(source_text: str, source_filename: str) -> dict:
    """Run the curator's ingest pipeline against one source artifact.

    Currently runs step 1 only and emits the classification. Steps 2-5 will
    be implemented in subsequent iterations.
    """
    client = _client()
    try:
        print("→ Step 1/5: classify_source...")
        classification = await step_classify_source(client, source_text)
        print(f"   source_type:      {classification.source_type}")
        print(f"   target_category:  {classification.target_category}")
        print(f"   body_shape:       {classification.body_shape}")
        print(f"   candidate_title:  {classification.candidate_title}")
        print(f"   candidate_slug:   {classification.candidate_slug}")
        print(f"   confidence:       {classification.confidence:.2f}")
        print(f"   rationale:        {classification.rationale}")

        print()
        print("→ Steps 2-5: NOT YET IMPLEMENTED. Returning classification only.")

        result = {
            "source_filename": source_filename,
            "classification": classification.model_dump(),
            "draft_path": f"patterns/{classification.target_category}/{classification.candidate_slug}.draft.md",
            "next_step": "step_extract_pattern (not yet implemented)",
            "today": date.today().isoformat(),
        }
        return result
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
    print(f"Classification: {result['classification']['target_category']} / {result['classification']['body_shape']}")
    print(f"Proposed draft path: {result['draft_path']}")
    print(f"(when steps 2-5 ship, the draft markdown will be written here)")


if __name__ == "__main__":
    main()
