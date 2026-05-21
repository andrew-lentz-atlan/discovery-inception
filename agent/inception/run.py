"""Inception agent — the half of discovery-inception that turns a spec
into a starter agent design.

Current scope: step 1 (workload_classifier) is implemented. Downstream
sub-agents (skill_proposer + critic, architecture_proposer + critic,
runtime_proposer, scaffold_writer) are stubbed.

Usage:
    uv run python -m agent.inception.run \\
        --spec-md path/to/spec.md \\
        --role-context skills/<role-id>/context.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

from agent.inception.schemas import SkillProposalResult, WorkloadClassification  # noqa: E402

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
MODEL = os.environ.get("INCEPTION_MODEL", "claude-haiku-4-5")


# ---------------------------------------------------------------------------
# Plumbing (same shape as intake/run.py and agent/patterns_curator/run.py)
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
    text = (PROMPTS_DIR / name).read_text()
    for key, value in substitutions.items():
        text = text.replace("{" + key + "}", value)
    return text


def parse_json_response(content: str) -> dict | list:
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
# Step 1: workload_classifier — IMPLEMENTED
# ---------------------------------------------------------------------------

async def step_workload_classifier(
    client: AsyncOpenAI,
    spec_md: str,
    role_context_json: str,
) -> WorkloadClassification:
    """Classify the workload's interaction shape, latency sensitivity, etc."""
    prompt = load_prompt(
        "01_workload_classifier.md",
        SPEC_MD=spec_md,
        ROLE_CONTEXT_JSON=role_context_json,
    )
    return await call_step(
        client,
        user_prompt=prompt,
        output_model=WorkloadClassification,
        max_tokens=2048,
    )


# ---------------------------------------------------------------------------
# Steps 2-6: STUBS
# ---------------------------------------------------------------------------

async def step_skill_proposer(
    client: AsyncOpenAI,
    workload: WorkloadClassification,
    spec_md: str,
    role_context_json: str,
) -> SkillProposalResult:
    """Propose the agent's skills given workload + spec + RoleContext."""
    prompt = load_prompt(
        "02_skill_proposer.md",
        WORKLOAD_CLASSIFICATION_JSON=workload.model_dump_json(indent=2),
        SPEC_MD=spec_md,
        ROLE_CONTEXT_JSON=role_context_json,
    )
    return await call_step(
        client,
        user_prompt=prompt,
        output_model=SkillProposalResult,
        max_tokens=8192,
    )


async def step_skill_critic(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError(
        "skill_critic: adversarially reviews skill_proposer's draft."
    )


async def step_architecture_proposer(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError(
        "architecture_proposer: filters patterns/architectures/ by workload axes; "
        "picks one + justifies; specifies bake-off variables."
    )


async def step_architecture_critic(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError(
        "architecture_critic: reviews architecture_proposer's choice."
    )


async def step_runtime_proposer(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError(
        "runtime_proposer: matches architecture to a harness from patterns/harnesses/; "
        "estimates cross-runtime calibration cost."
    )


async def step_scaffold_writer(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError(
        "scaffold_writer: produces the agent_starter/ directory with SKILL.md files, "
        "orchestrator stub, eval seed, LLM-as-judge harness, design_rationale.md."
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

async def run_inception(spec_md: str, role_context_json: str) -> dict:
    """Run the inception pipeline.

    Currently runs step 1 only. Downstream steps will be added in subsequent
    iterations.
    """
    client = _client()
    try:
        print("→ Step 1/6: workload_classifier...")
        classification = await step_workload_classifier(
            client, spec_md, role_context_json
        )
        print(f"   interaction_shape:        {classification.interaction_shape}")
        print(f"   latency_sensitivity:      {classification.latency_sensitivity}")
        print(f"   decision_complexity:      {classification.decision_complexity}")
        print(f"   data_intensity:           {classification.data_intensity}")
        print(f"   multi_step_or_single:     {classification.multi_step_or_single_step}")
        print(f"   state_shape:              {classification.state_shape}")
        print(f"   confidence:               {classification.confidence:.2f}")
        print(f"   rationale:                {classification.rationale}")
        if classification.open_questions:
            print(f"   open_questions ({len(classification.open_questions)}):")
            for q in classification.open_questions:
                print(f"     - {q}")

        print()
        print("→ Step 2/6: skill_proposer...")
        proposal = await step_skill_proposer(
            client, classification, spec_md, role_context_json
        )
        print(f"   skills proposed:        {len(proposal.skills)}")
        for i, s in enumerate(proposal.skills, 1):
            shape = s.suggested_body_shape
            decisions = ", ".join(s.owned_decisions) or "—"
            print(f"   [{i}] {s.name}  ({shape})")
            print(f"       purpose:    {s.purpose}")
            print(f"       decisions:  {decisions}")
            if s.provenance.role_context_decisions:
                print(f"       provenance (decisions): {s.provenance.role_context_decisions}")
        if proposal.orchestrator_level_concerns:
            print(f"   orchestrator-level concerns: {len(proposal.orchestrator_level_concerns)}")
            for c in proposal.orchestrator_level_concerns:
                print(f"     - {c}")
        print(f"   rationale:              {proposal.rationale}")
        print(f"   granularity_argument:   {proposal.granularity_argument}")

        print()
        print("→ Steps 3-6: NOT YET IMPLEMENTED.")
        print("   Next: architecture_proposer will consume the workload + skills to filter")
        print("   patterns/architectures/ and pick an architectural shape with citation.")

        return {
            "classification": classification.model_dump(),
            "skill_proposal": proposal.model_dump(),
            "next_step": "step_architecture_proposer (not yet implemented)",
        }
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inception agent — turn a discovery spec into a starter agent design."
    )
    parser.add_argument(
        "--spec-md",
        required=True,
        type=Path,
        help="Path to the spec.md produced by the discovery agent.",
    )
    parser.add_argument(
        "--role-context",
        required=True,
        type=Path,
        help="Path to the RoleContext JSON produced by the intake pipeline.",
    )
    args = parser.parse_args()

    spec_path: Path = args.spec_md.resolve()
    rc_path: Path = args.role_context.resolve()

    if not spec_path.exists():
        raise SystemExit(f"spec.md not found: {spec_path}")
    if not rc_path.exists():
        raise SystemExit(f"role-context not found: {rc_path}")

    spec_md = spec_path.read_text()
    role_context_json = rc_path.read_text()

    result = asyncio.run(run_inception(spec_md, role_context_json))

    print()
    print("─" * 70)
    c = result["classification"]
    print(f"Workload classified as: {c['interaction_shape']} / "
          f"{c['decision_complexity']} / {c['data_intensity']}")


if __name__ == "__main__":
    main()
