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

from agent.inception.schemas import (  # noqa: E402
    ArchitectureProposal,
    DesignRationale,
    EvalSeed,
    FeedbackTargetStep,
    JudgeHarness,
    OrchestratorStub,
    PriorIterationFeedback,
    ProposedSkill,
    RuntimeProposal,
    SkillMdContent,
    SkillProposalResult,
    WorkloadClassification,
)

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


PATTERNS_DIR = PROJECT_ROOT / "patterns"


def feedback_block(feedback: PriorIterationFeedback | None, step: FeedbackTargetStep) -> str:
    """Format the prior-iteration-feedback section for a specific sub-agent's prompt.

    Each sub-agent only sees feedback items that target its own step, PLUS
    the session-level free_text_lessons (which apply as background to every
    step). When feedback is absent or doesn't target this step, returns a
    passive line — keeps the prompt's behavior unchanged from a first-run
    inception.

    Per plans/10's Loop 2 design: feedback is treated as constraints, not
    advisory. The sub-agent's prompt makes the constraint nature explicit.
    """
    if not feedback or (not feedback.items and not feedback.free_text_lessons):
        return (
            "## Prior iteration feedback\n\n"
            "*(No prior iteration feedback — this is the first inception run for this spec.)*"
        )

    items_for_step = [i for i in feedback.items if i.targets_step == step]
    has_lessons = bool(feedback.free_text_lessons.strip())

    if not items_for_step and not has_lessons:
        return (
            "## Prior iteration feedback\n\n"
            "*(Prior iteration feedback exists but doesn't target this step. Continue with default reasoning.)*"
        )

    next_iter = feedback.iteration + 1
    lines = [
        "## Prior iteration feedback",
        "",
        f"This is inception iteration **{next_iter}** for this spec. The previous output "
        f"(iteration {feedback.iteration}) was tried by a builder. Treat the feedback below "
        "as **constraints**, not suggestions.",
        "",
    ]

    if items_for_step:
        lines.append(f"### Feedback targeting your step ({step})")
        lines.append("")
        for item in items_for_step:
            lines.append(f"**[{item.feedback_type}]** *{item.decision}*")
            lines.append("")
            lines.append(item.detail)
            lines.append("")

    if has_lessons:
        lines.append("### Session-level lessons (apply across all steps)")
        lines.append("")
        lines.append(feedback.free_text_lessons.strip())
        lines.append("")

    if feedback.source:
        lines.append(f"*Source:* {feedback.source}")
        lines.append("")

    lines.append("**Rules for incorporating this feedback:**")
    lines.append("")
    lines.append("- `wrong_for_this_use_case` items MUST NOT be repeated without explicit justification in your rationale.")
    lines.append("- `worked_with_modification` — the modification IS the right answer. Propose the modified version directly.")
    lines.append("- `missing` items MUST be addressed in this iteration's output.")
    lines.append("- `worked_as_proposed` items confirm the previous decision; keep them.")
    lines.append("- Session-level lessons apply as background context regardless of which decision they target.")
    return "\n".join(lines)


def load_pattern_category(category: str) -> str:
    """Read all primary entries (skip .reference.md) under patterns/<category>/.

    Returns concatenated markdown — each entry preceded by a divider showing
    the slug. Used to bundle pattern context into proposer prompts at runtime.

    Naïve loader; works for the current scale (~3-15 entries per category).
    When patterns/ grows past ~50 entries, swap to a tool-based lookup
    (lookup_pattern(filter)) per plans/07.
    """
    category_dir = PATTERNS_DIR / category
    if not category_dir.is_dir():
        return f"(no patterns/{category}/ directory found)"

    chunks: list[str] = []
    for path in sorted(category_dir.iterdir()):
        if not path.is_file() or not path.name.endswith(".md"):
            continue
        if path.name.endswith(".reference.md"):
            # Reference companions are for human review, not agent payload
            continue
        slug = path.stem
        chunks.append(f"### Pattern: `{category}/{slug}`\n\n{path.read_text()}")
    if not chunks:
        return f"(patterns/{category}/ is empty)"
    return "\n\n---\n\n".join(chunks)


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
    prior_feedback: PriorIterationFeedback | None = None,
) -> WorkloadClassification:
    """Classify the workload's interaction shape, latency sensitivity, etc."""
    prompt = load_prompt(
        "01_workload_classifier.md",
        SPEC_MD=spec_md,
        ROLE_CONTEXT_JSON=role_context_json,
        PRIOR_FEEDBACK=feedback_block(prior_feedback, "workload"),
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
    prior_feedback: PriorIterationFeedback | None = None,
) -> SkillProposalResult:
    """Propose the agent's skills given workload + spec + RoleContext."""
    prompt = load_prompt(
        "02_skill_proposer.md",
        WORKLOAD_CLASSIFICATION_JSON=workload.model_dump_json(indent=2),
        SPEC_MD=spec_md,
        ROLE_CONTEXT_JSON=role_context_json,
        PRIOR_FEEDBACK=feedback_block(prior_feedback, "skills"),
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


async def step_architecture_proposer(
    client: AsyncOpenAI,
    workload: WorkloadClassification,
    skills: SkillProposalResult,
    prior_feedback: PriorIterationFeedback | None = None,
) -> ArchitectureProposal:
    """Pick an architectural shape, citing patterns/architectures/ + workload axes.

    Reads every primary entry under patterns/architectures/ (skipping
    .reference.md companions) and bundles them into the prompt. The model
    surveys candidates, selects one, explicitly rejects the others, and
    surfaces any patterns that should LAYER on top of the selection
    (e.g., adversarial-decomposition on single-agent-react).
    """
    prompt = load_prompt(
        "03_architecture_proposer.md",
        WORKLOAD_CLASSIFICATION_JSON=workload.model_dump_json(indent=2),
        SKILL_PROPOSAL_JSON=skills.model_dump_json(indent=2),
        ARCHITECTURE_PATTERNS=load_pattern_category("architectures"),
        PRIOR_FEEDBACK=feedback_block(prior_feedback, "architecture"),
    )
    return await call_step(
        client,
        user_prompt=prompt,
        output_model=ArchitectureProposal,
        max_tokens=4096,
    )


async def step_architecture_critic(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError(
        "architecture_critic: reviews architecture_proposer's choice."
    )


async def step_runtime_proposer(
    client: AsyncOpenAI,
    workload: WorkloadClassification,
    skills: SkillProposalResult,
    architecture: ArchitectureProposal,
    prior_feedback: PriorIterationFeedback | None = None,
) -> RuntimeProposal:
    """Pick a runtime + model family that preserves the architectural shape.

    Reads patterns/harnesses/ (bundled into the prompt) and the upstream
    steps' outputs. Selects one harness, rejects alternatives, estimates
    cross-boundary calibration cost.
    """
    prompt = load_prompt(
        "04_runtime_proposer.md",
        WORKLOAD_CLASSIFICATION_JSON=workload.model_dump_json(indent=2),
        SKILL_PROPOSAL_JSON=skills.model_dump_json(indent=2),
        ARCHITECTURE_PROPOSAL_JSON=architecture.model_dump_json(indent=2),
        HARNESS_PATTERNS=load_pattern_category("harnesses"),
        PRIOR_FEEDBACK=feedback_block(prior_feedback, "runtime"),
    )
    return await call_step(
        client,
        user_prompt=prompt,
        output_model=RuntimeProposal,
        max_tokens=4096,
    )


async def step_generate_skill_md(
    client: AsyncOpenAI,
    skill: ProposedSkill,
    workload: WorkloadClassification,
    architecture: ArchitectureProposal,
    runtime: RuntimeProposal,
    role_context_json: str,
) -> SkillMdContent:
    """Generate the SKILL.md content for one proposed skill."""
    prompt = load_prompt(
        "05a_skill_md.md",
        PROPOSED_SKILL_JSON=skill.model_dump_json(indent=2),
        WORKLOAD_CLASSIFICATION_JSON=workload.model_dump_json(indent=2),
        ARCHITECTURE_PROPOSAL_JSON=architecture.model_dump_json(indent=2),
        RUNTIME_PROPOSAL_JSON=runtime.model_dump_json(indent=2),
        ROLE_CONTEXT_JSON=role_context_json,
    )
    return await call_step(
        client,
        user_prompt=prompt,
        output_model=SkillMdContent,
        max_tokens=8192,  # SKILL.md content is verbose (frontmatter + multi-section body)
    )


async def step_generate_orchestrator_stub(
    client: AsyncOpenAI,
    skills: SkillProposalResult,
    architecture: ArchitectureProposal,
    runtime: RuntimeProposal,
) -> OrchestratorStub:
    """Generate the orchestrator.py stub matching the selected runtime + architecture."""
    prompt = load_prompt(
        "05b_orchestrator_stub.md",
        ARCHITECTURE_PROPOSAL_JSON=architecture.model_dump_json(indent=2),
        RUNTIME_PROPOSAL_JSON=runtime.model_dump_json(indent=2),
        SKILL_PROPOSAL_JSON=skills.model_dump_json(indent=2),
    )
    return await call_step(
        client,
        user_prompt=prompt,
        output_model=OrchestratorStub,
        max_tokens=8192,  # Python source for N skills + imports + loop scaffold
    )


async def step_generate_design_rationale(
    client: AsyncOpenAI,
    workload: WorkloadClassification,
    skills: SkillProposalResult,
    architecture: ArchitectureProposal,
    runtime: RuntimeProposal,
    spec_md: str,
) -> DesignRationale:
    """Aggregate all upstream decisions into design_rationale.md."""
    prompt = load_prompt(
        "05c_design_rationale.md",
        WORKLOAD_CLASSIFICATION_JSON=workload.model_dump_json(indent=2),
        SKILL_PROPOSAL_JSON=skills.model_dump_json(indent=2),
        ARCHITECTURE_PROPOSAL_JSON=architecture.model_dump_json(indent=2),
        RUNTIME_PROPOSAL_JSON=runtime.model_dump_json(indent=2),
        SPEC_MD=spec_md,
    )
    return await call_step(
        client,
        user_prompt=prompt,
        output_model=DesignRationale,
        max_tokens=12288,  # Audit trail aggregates every prior decision; can be long
    )


async def step_generate_eval_seed(
    client: AsyncOpenAI,
    workload: WorkloadClassification,
    skills: SkillProposalResult,
    architecture: ArchitectureProposal,
    spec_md: str,
    role_context_json: str,
) -> EvalSeed:
    """Generate 10-15 seed questions covering the agent's expected scenarios."""
    prompt = load_prompt(
        "05d_eval_seed.md",
        WORKLOAD_CLASSIFICATION_JSON=workload.model_dump_json(indent=2),
        SKILL_PROPOSAL_JSON=skills.model_dump_json(indent=2),
        ARCHITECTURE_PROPOSAL_JSON=architecture.model_dump_json(indent=2),
        SPEC_MD=spec_md,
        ROLE_CONTEXT_JSON=role_context_json,
    )
    return await call_step(
        client,
        user_prompt=prompt,
        output_model=EvalSeed,
        max_tokens=8192,  # 10-15 structured questions can run long
    )


async def step_generate_judge_harness(
    client: AsyncOpenAI,
    workload: WorkloadClassification,
    skills: SkillProposalResult,
    runtime: RuntimeProposal,
    eval_seed: EvalSeed,
    role_context_json: str,
) -> JudgeHarness:
    """Generate the eval/judge.py source — LLM-as-judge harness."""
    prompt = load_prompt(
        "05e_judge_harness.md",
        WORKLOAD_CLASSIFICATION_JSON=workload.model_dump_json(indent=2),
        SKILL_PROPOSAL_JSON=skills.model_dump_json(indent=2),
        RUNTIME_PROPOSAL_JSON=runtime.model_dump_json(indent=2),
        EVAL_SEED_JSON=eval_seed.model_dump_json(indent=2),
        ROLE_CONTEXT_JSON=role_context_json,
    )
    return await call_step(
        client,
        user_prompt=prompt,
        output_model=JudgeHarness,
        max_tokens=8192,  # judge.py source with N dimension scorers
    )


async def step_scaffold_writer(
    client: AsyncOpenAI,
    workload: WorkloadClassification,
    skills: SkillProposalResult,
    architecture: ArchitectureProposal,
    runtime: RuntimeProposal,
    spec_md: str,
    role_context_json: str,
    output_dir: Path,
) -> dict[str, Any]:
    """Produce the agent_starter/ directory.

    Runs three LLM sub-steps in sequence:
      1. generate_skill_md (one call per proposed skill — parallelized)
      2. generate_orchestrator_stub (one call)
      3. generate_design_rationale (one call)

    Plus deterministic writes:
      - skills/<skill_name>/SKILL.md per skill
      - orchestrator.py
      - design_rationale.md
      - README.md (a small starter readme aggregating setup + structure)
      - meta/ — upstream Pydantic outputs as JSON (audit-trail copies)

    Returns a dict summarizing what was written.
    """
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "skills").mkdir(exist_ok=True)
    (output_dir / "meta").mkdir(exist_ok=True)
    (output_dir / "eval").mkdir(exist_ok=True)

    # ---- 1. Run 5a/5b/5c/5d in parallel (no inter-dependencies) ----
    # 5e depends on 5d (eval seed), so it runs after this gather.
    print(f"  [5a/5b/5c/5d] generating SKILL.md × {len(skills.skills)} + orchestrator + rationale + eval seed (parallel)...")
    skill_md_tasks = [
        step_generate_skill_md(client, skill, workload, architecture, runtime, role_context_json)
        for skill in skills.skills
    ]
    results = await asyncio.gather(
        asyncio.gather(*skill_md_tasks),
        step_generate_orchestrator_stub(client, skills, architecture, runtime),
        step_generate_design_rationale(client, workload, skills, architecture, runtime, spec_md),
        step_generate_eval_seed(client, workload, skills, architecture, spec_md, role_context_json),
    )
    skill_md_results: list[SkillMdContent] = results[0]
    stub: OrchestratorStub = results[1]
    rationale: DesignRationale = results[2]
    eval_seed: EvalSeed = results[3]

    for content in skill_md_results:
        skill_dir = output_dir / "skills" / content.skill_name
        skill_dir.mkdir(exist_ok=True)
        (skill_dir / "SKILL.md").write_text(content.skill_md)
        print(f"       ✓ skills/{content.skill_name}/SKILL.md")

    (output_dir / stub.filename).write_text(stub.orchestrator_py)
    print(f"       ✓ {stub.filename} (imports: {len(stub.imports_needed)}, env vars: {len(stub.env_vars_needed)})")

    (output_dir / "design_rationale.md").write_text(rationale.rationale_md)
    print("       ✓ design_rationale.md")

    (output_dir / "eval" / "questions.json").write_text(eval_seed.model_dump_json(indent=2))
    print(f"       ✓ eval/questions.json ({len(eval_seed.questions)} seed questions)")

    # ---- 2. judge harness (depends on eval_seed) ----
    print("  [5e] generating eval/judge.py (LLM-as-judge harness)...")
    judge = await step_generate_judge_harness(
        client, workload, skills, runtime, eval_seed, role_context_json
    )
    (output_dir / "eval" / "judge.py").write_text(judge.judge_py)
    print(f"       ✓ eval/judge.py ({len(judge.dimensions)} scoring dimensions, judge model: {judge.judging_model_recommended})")

    # ---- 3. meta/ — deterministic copies of upstream Pydantic outputs ----
    print("  [5*] writing meta/ artifacts (deterministic)...")
    (output_dir / "meta" / "01_workload_classification.json").write_text(
        workload.model_dump_json(indent=2)
    )
    (output_dir / "meta" / "02_skill_proposal.json").write_text(
        skills.model_dump_json(indent=2)
    )
    (output_dir / "meta" / "03_architecture_proposal.json").write_text(
        architecture.model_dump_json(indent=2)
    )
    (output_dir / "meta" / "04_runtime_proposal.json").write_text(
        runtime.model_dump_json(indent=2)
    )
    (output_dir / "meta" / "spec_consumed.md").write_text(spec_md)
    (output_dir / "meta" / "role_context_consumed.json").write_text(role_context_json)
    print("       ✓ meta/ (6 artifacts)")

    # ---- 5. starter README — deterministic, assembled from upstream + stub metadata ----
    print("  [5*] writing starter README.md...")
    readme = _starter_readme(
        skill_md_results=skill_md_results,
        stub=stub,
        architecture=architecture,
        runtime=runtime,
    )
    (output_dir / "README.md").write_text(readme)
    print("       ✓ README.md")

    return {
        "output_dir": str(output_dir),
        "skills_written": [c.skill_name for c in skill_md_results],
        "orchestrator_filename": stub.filename,
        "imports_needed": stub.imports_needed,
        "env_vars_needed": stub.env_vars_needed,
        "rationale_length": len(rationale.rationale_md),
        "eval_questions": len(eval_seed.questions),
        "judge_dimensions": judge.dimensions,
        "meta_artifacts": 6,
    }


def _starter_readme(
    skill_md_results: list[SkillMdContent],
    stub: OrchestratorStub,
    architecture: ArchitectureProposal,
    runtime: RuntimeProposal,
) -> str:
    """Deterministic README assembler. No LLM call — pure templating from upstream data."""
    skills_list = "\n".join(
        f"- `skills/{c.skill_name}/SKILL.md`" for c in skill_md_results
    )
    imports_list = "\n".join(f"- `{imp}`" for imp in stub.imports_needed) if stub.imports_needed else "(none listed)"
    env_vars_list = "\n".join(f"- `{var}`" for var in stub.env_vars_needed) if stub.env_vars_needed else "(none listed)"

    return (
        f"# agent_starter/\n\n"
        f"Starter agent design produced by discovery-inception's inception pipeline.\n\n"
        f"**Architecture:** `{architecture.selected_pattern_slug}` — {architecture.selected_pattern_title}  \n"
        f"**Runtime:** {runtime.selected_runtime} + {runtime.selected_model_family}\n\n"
        f"## Read this first\n\n"
        f"This is a STARTER, not a finished agent. The orchestrator's wiring is in place; skill bodies are TODO markers.\n\n"
        f"Expected first-pass quality: ~75/100 on LLM-as-judge eval. The builder iterates from here. Compare with Bala's "
        f"P&G Brand Analyst Agent (https://github.com/bladata1990/pg-brand-analyst-agent) for an empirical receipt of "
        f"what a 97/100 endpoint looks like with the same architectural shape.\n\n"
        f"**Read `design_rationale.md` before iterating.** It explains every decision made, with citations.\n\n"
        f"## Structure\n\n"
        f"```\n"
        f"agent_starter/\n"
        f"├── README.md            ← this file\n"
        f"├── design_rationale.md  ← audit trail (READ FIRST)\n"
        f"├── orchestrator.py      ← runnable stub; skill bodies are TODOs\n"
        f"├── skills/              ← SKILL.md per skill\n"
        f"├── eval/                ← questions.json (seed) + judge.py (LLM-as-judge harness)\n"
        f"└── meta/                ← upstream inception outputs (audit-trail copies)\n"
        f"```\n\n"
        f"## Skills\n\n"
        f"{skills_list}\n\n"
        f"Each SKILL.md has its own purpose, inputs/outputs, implementation guidance, and provenance back to "
        f"the RoleContext entries that justified its existence.\n\n"
        f"## Dependencies\n\n"
        f"### Python packages\n\n"
        f"{imports_list}\n\n"
        f"### Environment variables\n\n"
        f"{env_vars_list}\n\n"
        f"## How to iterate\n\n"
        f"1. Read `design_rationale.md`\n"
        f"2. Read each SKILL.md and implement the skill body (replace the TODO markers)\n"
        f"3. Run the orchestrator end-to-end against synthetic data\n"
        f"4. Add eval questions once the agent boots; an LLM-as-judge harness is the recommended methodology "
        f"(see Bala's repo for the canonical pattern — 5 dimensions: accuracy, root-cause classification, "
        f"hallucination, reasoning quality, actionability)\n"
        f"5. Iterate from initial pass to target quality\n\n"
        f"## Provenance\n\n"
        f"`meta/01_workload_classification.json`, `meta/02_skill_proposal.json`, `meta/03_architecture_proposal.json`, "
        f"`meta/04_runtime_proposal.json` contain the structured outputs of each inception step. `meta/spec_consumed.md` "
        f"and `meta/role_context_consumed.json` are the inputs that produced this starter — useful when comparing iterations "
        f"or running the inception pipeline against a new version of the spec.\n"
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

async def run_inception(
    spec_md: str,
    role_context_json: str,
    output_dir: Path | None = None,
    prior_feedback: PriorIterationFeedback | None = None,
) -> dict:
    """Run the inception pipeline.

    Steps 1-4 always run. Step 5 (scaffold_writer) runs only when output_dir
    is provided — that's the step that materializes the agent_starter/
    directory on disk.

    When `prior_feedback` is provided (Loop 2 per plans/10), each sub-agent's
    prompt gains a "Prior iteration feedback" section that the model treats
    as constraints. Feedback is filtered per-step (workload_classifier sees
    only items targeting 'workload', etc.); session-level free_text_lessons
    apply across all steps.
    """
    client = _client()
    try:
        if prior_feedback:
            print(
                f"→ Loop 2: prior iteration {prior_feedback.iteration} feedback present "
                f"({len(prior_feedback.items)} items, "
                f"{sum(1 for i in prior_feedback.items if i.feedback_type == 'wrong_for_this_use_case')} wrong / "
                f"{sum(1 for i in prior_feedback.items if i.feedback_type == 'missing')} missing). "
                "Sub-agents will consume as constraints."
            )
            if prior_feedback.source:
                print(f"   source: {prior_feedback.source}")
            print()

        print("→ Step 1/6: workload_classifier...")
        classification = await step_workload_classifier(
            client, spec_md, role_context_json, prior_feedback=prior_feedback
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
            client, classification, spec_md, role_context_json, prior_feedback=prior_feedback
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
        print("→ Step 3/6: architecture_proposer...")
        architecture = await step_architecture_proposer(
            client, classification, proposal, prior_feedback=prior_feedback
        )
        print(f"   selected:     {architecture.selected_pattern_slug}  ({architecture.selected_pattern_title})")
        print(f"   confidence:   {architecture.confidence:.2f}")
        print(f"   rationale:    {architecture.selection_rationale}")
        if architecture.rejected_alternatives:
            print(f"   rejected ({len(architecture.rejected_alternatives)}):")
            for r in architecture.rejected_alternatives:
                print(f"     - {r.pattern_slug}: {r.reason}")
        if architecture.candidate_addons:
            print(f"   candidate add-ons ({len(architecture.candidate_addons)}):")
            for a in architecture.candidate_addons:
                print(f"     - {a.pattern_slug} ({a.recommendation}) — addresses: {a.addresses_concern}")
        if architecture.bake_off_variables:
            print(f"   bake-off variables ({len(architecture.bake_off_variables)}):")
            for v in architecture.bake_off_variables:
                print(f"     - {v}")

        print()
        print("→ Step 4/6: runtime_proposer...")
        runtime = await step_runtime_proposer(
            client, classification, proposal, architecture, prior_feedback=prior_feedback
        )
        print(f"   selected:     {runtime.selected_runtime}")
        print(f"   model:        {runtime.selected_model_family}")
        print(f"   confidence:   {runtime.confidence:.2f}")
        print(f"   rationale:    {runtime.selection_rationale}")
        if runtime.rejected_alternatives:
            print(f"   rejected ({len(runtime.rejected_alternatives)}):")
            for r in runtime.rejected_alternatives:
                print(f"     - {r.runtime_name}: {r.reason}")
        if runtime.constraints_respected:
            print(f"   constraints respected: {runtime.constraints_respected}")
        if runtime.constraints_violated:
            print(f"   ⚠ constraints VIOLATED: {runtime.constraints_violated}")
        print(f"   calibration cost:")
        print(f"     same runtime family:        {runtime.calibration_cost.same_runtime_family}")
        print(f"     cross-runtime same provider: {runtime.calibration_cost.cross_runtime_same_provider}")
        print(f"     cross-provider:              {runtime.calibration_cost.cross_provider}")

        if output_dir is None:
            print()
            print("→ Step 5/6: scaffold_writer SKIPPED (no --output-dir provided).")
            print("   Pass --output-dir <path> to materialize agent_starter/.")
            return {
                "classification": classification.model_dump(),
                "skill_proposal": proposal.model_dump(),
                "architecture_proposal": architecture.model_dump(),
                "runtime_proposal": runtime.model_dump(),
                "scaffold_output": None,
                "next_step": "step_scaffold_writer (skipped — provide --output-dir)",
            }

        print()
        print(f"→ Step 5/6: scaffold_writer → {output_dir}")
        scaffold_summary = await step_scaffold_writer(
            client,
            classification,
            proposal,
            architecture,
            runtime,
            spec_md=spec_md,
            role_context_json=role_context_json,
            output_dir=output_dir,
        )

        print()
        print("→ Step 6: critics — NOT YET IMPLEMENTED (advisory; lower priority).")
        print("   Eval question seed + LLM-as-judge harness scaffold deferred to next session.")

        return {
            "classification": classification.model_dump(),
            "skill_proposal": proposal.model_dump(),
            "architecture_proposal": architecture.model_dump(),
            "runtime_proposal": runtime.model_dump(),
            "scaffold_output": scaffold_summary,
            "next_step": "step_critics (not yet implemented) + eval/judge scaffolding (next session)",
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
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "If provided, materializes the agent_starter/ directory at this path "
            "by running step 5 (scaffold_writer). Without this arg, only steps 1-4 "
            "run and their structured outputs are printed/returned."
        ),
    )
    parser.add_argument(
        "--prior-feedback",
        type=Path,
        default=None,
        help=(
            "Optional path to a JSON file matching the PriorIterationFeedback schema. "
            "When provided, each inception sub-agent's prompt gets a 'Prior iteration "
            "feedback' section that the model treats as constraints. Used to re-run "
            "inception with builder feedback on a previous starter. Loop 2 per "
            "plans/10's three-loop architecture."
        ),
    )
    args = parser.parse_args()

    prior_feedback: PriorIterationFeedback | None = None
    if args.prior_feedback is not None:
        feedback_path = args.prior_feedback.resolve()
        if not feedback_path.exists():
            raise SystemExit(f"prior-feedback not found: {feedback_path}")
        prior_feedback = PriorIterationFeedback.model_validate_json(feedback_path.read_text())

    spec_path: Path = args.spec_md.resolve()
    rc_path: Path = args.role_context.resolve()

    if not spec_path.exists():
        raise SystemExit(f"spec.md not found: {spec_path}")
    if not rc_path.exists():
        raise SystemExit(f"role-context not found: {rc_path}")

    spec_md = spec_path.read_text()
    role_context_json = rc_path.read_text()

    result = asyncio.run(
        run_inception(
            spec_md,
            role_context_json,
            output_dir=args.output_dir,
            prior_feedback=prior_feedback,
        )
    )

    print()
    print("─" * 70)
    c = result["classification"]
    print(f"Workload:     {c['interaction_shape']} / {c['decision_complexity']} / {c['data_intensity']}")
    a = result["architecture_proposal"]
    print(f"Architecture: {a['selected_pattern_slug']}")
    r = result["runtime_proposal"]
    print(f"Runtime:      {r['selected_runtime']} + {r['selected_model_family']}")
    if result.get("scaffold_output"):
        s = result["scaffold_output"]
        print(f"Scaffold:     {s['output_dir']} ({len(s['skills_written'])} skills, orchestrator.py, design_rationale.md, meta/)")


if __name__ == "__main__":
    main()
