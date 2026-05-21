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
    ArchitectureDiagram,
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

    Feedback is treated as constraints, not advisory. The sub-agent's prompt
    makes the constraint nature explicit.
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
    (lookup_pattern(filter)).
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
    max_retries: int = 3,
) -> BaseModel:
    """One LLM call → validated Pydantic instance, with retry/backoff.

    Critical for scaffold_writer steps (OrchestratorStub, SkillMdContent,
    DesignRationale, JudgeHarness) which embed Python source as JSON-
    escaped strings — verbose, occasionally exceeds the configured
    max_tokens, and truncates mid-string. When that happens we detect
    `finish_reason == 'length'` and double max_tokens for the retry
    (capped at 24576 so a single call can't run away). The same logic
    handles transient empty responses and malformed JSON.

    Three attempts total; 0.75s × attempt backoff.
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
        try:
            data = parse_json_response(raw)
        except json.JSONDecodeError as exc:
            last_error = ValueError(
                f"{output_model.__name__}: could not parse JSON on attempt {attempt+1} "
                f"(finish_reason={finish_reason!r}) — {exc}\n"
                f"Raw content (first 600 chars):\n{raw[:600]}"
            )
            # Truncation: bump max_tokens for the retry (cap at 24576).
            if finish_reason == "length" and current_max_tokens < 24576:
                current_max_tokens = min(current_max_tokens * 2, 24576)
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
        max_tokens=12288,  # Python source for N skills + imports + loop scaffold. Embedded source as JSON string is verbose; call_step auto-bumps on truncation, but raising the floor saves a retry on real-world 6+ skill agents.
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


async def step_generate_architecture_diagram(
    client: AsyncOpenAI,
    workload: WorkloadClassification,
    skills: SkillProposalResult,
    architecture: ArchitectureProposal,
    runtime: RuntimeProposal,
) -> ArchitectureDiagram:
    """Generate a Mermaid-rendered architecture.md.

    Step 5f. Runs in parallel with 5a-5d (no inter-dependencies — consumes
    only the upstream Pydantic outputs). Produces two diagrams + a 2-paragraph
    summary that a builder can skim in 30s to understand the agent's shape
    before reading orchestrator.py + N SKILL.md files.

    Architecture-aware: the prompt is given the selected pattern's slug so
    the diagram shape matches the runtime behavior (single-agent-react =
    ReAct loop; chained-pipeline = linear; adversarial-decomposition =
    producer+critic).
    """
    prompt = load_prompt(
        "05f_architecture_diagram.md",
        SELECTED_ARCHITECTURE_SLUG=architecture.selected_pattern_slug,
        WORKLOAD_JSON=workload.model_dump_json(indent=2),
        SKILLS_JSON=skills.model_dump_json(indent=2),
        ARCHITECTURE_JSON=architecture.model_dump_json(indent=2),
        RUNTIME_JSON=runtime.model_dump_json(indent=2),
    )
    return await call_step(
        client,
        user_prompt=prompt,
        output_model=ArchitectureDiagram,
        max_tokens=4096,  # 2 mermaid diagrams + 2-paragraph summary
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

    # ---- 0. Persist meta/ FIRST (deterministic; no LLM cost) ----
    # The four upstream LLM steps' outputs (workload classification, skill
    # proposal, architecture, runtime) are already computed by the time
    # scaffold_writer runs. Dumping them to disk upfront means a downstream
    # 5a–5d failure no longer wastes those four LLM calls — a retry can read
    # them back, and even if no retry happens the FDE still has the four
    # decision artifacts to work from.
    print("  [5*] writing meta/ artifacts upfront (deterministic, pre-LLM)...")
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
    print("       ✓ meta/ (6 artifacts persisted before risky LLM steps)")

    # ---- 1. Run 5a/5b/5c/5d/5f in parallel; tolerate per-sub-step failures ----
    # Without return_exceptions=True, any one sub-step failure (truncation on
    # OrchestratorStub, JSON-escape glitch on SkillMdContent, etc.) tanks the
    # whole parallel gather and we lose the successful outputs of the others.
    # With it, each sub-step lands or fails independently; partial scaffolds
    # are useful (skills/ written even if orchestrator.py failed, etc.) and
    # the response surfaces what was missed.
    #
    # 5f (architecture diagram) joins the parallel gather since it depends on
    # the same four upstream outputs everyone else does. 5e (judge harness)
    # still runs sequentially after 5d since it needs eval_seed.
    print(f"  [5a/5b/5c/5d/5f] generating SKILL.md × {len(skills.skills)} + orchestrator + rationale + eval seed + architecture diagram (parallel)...")
    skill_md_tasks = [
        step_generate_skill_md(client, skill, workload, architecture, runtime, role_context_json)
        for skill in skills.skills
    ]
    results = await asyncio.gather(
        asyncio.gather(*skill_md_tasks, return_exceptions=True),
        step_generate_orchestrator_stub(client, skills, architecture, runtime),
        step_generate_design_rationale(client, workload, skills, architecture, runtime, spec_md),
        step_generate_eval_seed(client, workload, skills, architecture, spec_md, role_context_json),
        step_generate_architecture_diagram(client, workload, skills, architecture, runtime),
        return_exceptions=True,
    )

    scaffold_errors: list[str] = []

    # 5a — skill MDs (per-skill tolerance)
    skill_md_results: list[SkillMdContent] = []
    skill_md_raw = results[0]
    if isinstance(skill_md_raw, BaseException):
        scaffold_errors.append(f"all skill_md generation failed: {type(skill_md_raw).__name__}: {str(skill_md_raw)[:200]}")
    else:
        for skill_obj, content in zip(skills.skills, skill_md_raw):
            if isinstance(content, BaseException):
                scaffold_errors.append(
                    f"skills/{skill_obj.name}/SKILL.md: {type(content).__name__}: {str(content)[:200]}"
                )
                continue
            skill_md_results.append(content)
            skill_dir = output_dir / "skills" / content.skill_name
            skill_dir.mkdir(exist_ok=True)
            (skill_dir / "SKILL.md").write_text(content.skill_md)
            print(f"       ✓ skills/{content.skill_name}/SKILL.md")

    # 5b — orchestrator stub
    stub: OrchestratorStub | None = None
    if isinstance(results[1], BaseException):
        scaffold_errors.append(f"orchestrator.py: {type(results[1]).__name__}: {str(results[1])[:200]}")
        _write_orchestrator_stub_fallback(output_dir, skills, architecture, runtime, str(results[1])[:300])
        print("       ! orchestrator.py failed; wrote stub with TODO. See file for details.")
    else:
        stub = results[1]
        (output_dir / stub.filename).write_text(stub.orchestrator_py)
        print(f"       ✓ {stub.filename} (imports: {len(stub.imports_needed)}, env vars: {len(stub.env_vars_needed)})")

    # 5c — design rationale
    rationale: DesignRationale | None = None
    if isinstance(results[2], BaseException):
        scaffold_errors.append(f"design_rationale.md: {type(results[2]).__name__}: {str(results[2])[:200]}")
        _write_design_rationale_fallback(output_dir, workload, skills, architecture, runtime, str(results[2])[:300])
        print("       ! design_rationale.md failed; wrote stub aggregating upstream Pydantic outputs.")
    else:
        rationale = results[2]
        (output_dir / "design_rationale.md").write_text(rationale.rationale_md)
        print("       ✓ design_rationale.md")

    # 5d — eval seed (judge harness depends on this)
    eval_seed: EvalSeed | None = None
    if isinstance(results[3], BaseException):
        scaffold_errors.append(f"eval/questions.json: {type(results[3]).__name__}: {str(results[3])[:200]}")
        print("       ! eval/questions.json failed; eval seed unavailable for judge harness.")
    else:
        eval_seed = results[3]
        (output_dir / "eval" / "questions.json").write_text(eval_seed.model_dump_json(indent=2))
        print(f"       ✓ eval/questions.json ({len(eval_seed.questions)} seed questions)")

    # 5f — architecture diagram (independent of 5a-5d; runs in same parallel gather)
    diagram: ArchitectureDiagram | None = None
    if isinstance(results[4], BaseException):
        scaffold_errors.append(f"architecture.md: {type(results[4]).__name__}: {str(results[4])[:200]}")
        _write_architecture_diagram_fallback(output_dir, skills, architecture, runtime, str(results[4])[:300])
        print("       ! architecture.md failed; wrote a deterministic fallback (no diagrams, just a list).")
    else:
        diagram = results[4]
        (output_dir / "architecture.md").write_text(_render_architecture_md(diagram, architecture, runtime))
        print(f"       ✓ architecture.md (2 mermaid diagrams + summary, {architecture.selected_pattern_slug})")

    # ---- 2. judge harness (depends on eval_seed; skipped if 5d failed) ----
    judge: JudgeHarness | None = None
    judge_error: str | None = None
    if eval_seed is None:
        judge_error = "skipped: step 5d (eval seed) failed; no eval_seed available"
        print("  [5e] eval/judge.py SKIPPED (no eval seed from 5d; will need manual seed + judge).")
        scaffold_errors.append("eval/judge.py: skipped because 5d eval seed failed")
    else:
        print("  [5e] generating eval/judge.py (LLM-as-judge harness)...")
        try:
            judge = await step_generate_judge_harness(
                client, workload, skills, runtime, eval_seed, role_context_json
            )
            (output_dir / "eval" / "judge.py").write_text(judge.judge_py)
            print(
                f"       ✓ eval/judge.py ({len(judge.dimensions)} scoring dimensions, "
                f"judge model: {judge.judging_model_recommended})"
            )
        except Exception as exc:
            judge_error = f"{type(exc).__name__}: {str(exc)[:300]}"
            stub_judge = (
                '"""LLM-as-judge harness for this agent.\n\n'
                "Auto-generation of this file failed during inception. The eval seed\n"
                "(eval/questions.json) is still present and usable. To regenerate the\n"
                "judge harness, re-run inception or write one by hand following the\n"
                "pattern in patterns/skill-design/inner-pipeline.md §judge-harnesses.\n\n"
                f"Failure: {judge_error}\n"
                '"""\n\n'
                "raise NotImplementedError(\n"
                '    "Judge harness was not generated during scaffold. "\n'
                '    "Regenerate via inception or implement by hand against eval/questions.json."\n'
                ")\n"
            )
            (output_dir / "eval" / "judge.py").write_text(stub_judge)
            scaffold_errors.append(f"eval/judge.py: {judge_error}")
            print(
                f"       ! eval/judge.py generation failed; wrote stub. Error: {judge_error[:120]}"
            )

    # ---- 3. starter README — deterministic, assembled from whatever landed ----
    print("  [5*] writing starter README.md...")
    readme = _starter_readme(
        skill_md_results=skill_md_results,
        stub=stub,
        architecture=architecture,
        runtime=runtime,
    )
    (output_dir / "README.md").write_text(readme)
    print("       ✓ README.md")

    if scaffold_errors:
        print()
        print(f"  ! scaffold completed with {len(scaffold_errors)} non-fatal error(s):")
        for err in scaffold_errors:
            print(f"     - {err[:160]}")

    return {
        "output_dir": str(output_dir),
        "skills_written": [c.skill_name for c in skill_md_results],
        "orchestrator_filename": stub.filename if stub else "(generation failed; see stub)",
        "imports_needed": stub.imports_needed if stub else [],
        "env_vars_needed": stub.env_vars_needed if stub else [],
        "rationale_length": len(rationale.rationale_md) if rationale else 0,
        "eval_questions": len(eval_seed.questions) if eval_seed else 0,
        "judge_dimensions": judge.dimensions if judge else [],
        "judge_generation_error": judge_error,  # None on success; str on graceful failure
        "architecture_diagram_generated": diagram is not None,
        "scaffold_errors": scaffold_errors,
        "meta_artifacts": 6,
    }


def _render_architecture_md(
    diagram: ArchitectureDiagram,
    architecture: ArchitectureProposal,
    runtime: RuntimeProposal,
) -> str:
    """Wrap the LLM's diagram source in fenced mermaid blocks + header/footer."""
    return (
        f"# Architecture — {architecture.selected_pattern_slug}\n\n"
        f"**Runtime:** {runtime.selected_runtime} + {runtime.selected_model_family}  \n"
        f"**Architecture pattern:** `{architecture.selected_pattern_slug}` ({architecture.selected_pattern_title})\n\n"
        f"{diagram.summary_md.strip()}\n\n"
        f"## Skill graph\n\n"
        f"What skills the agent has and how they relate. Each node shows the skill's name and type (LLM / inner-pipeline / deterministic).\n\n"
        f"```mermaid\n{diagram.skill_graph_mermaid.strip()}\n```\n\n"
        f"## Execution flow (one turn)\n\n"
        f"What happens from the user's input to the agent's response. Conditional branches (escalation gates, retries) are shown where relevant.\n\n"
        f"```mermaid\n{diagram.execution_flow_mermaid.strip()}\n```\n\n"
        f"---\n\n"
        f"*Read [`design_rationale.md`](./design_rationale.md) for the audit trail of why these decisions were made (with citations into `patterns/`).*\n"
    )


def _write_architecture_diagram_fallback(
    output_dir: Path,
    skills: SkillProposalResult,
    architecture: ArchitectureProposal,
    runtime: RuntimeProposal,
    failure_reason: str,
) -> None:
    """Write a deterministic architecture.md when the LLM diagram step failed.

    No diagrams — just a textual skeleton built from the upstream Pydantic
    outputs. Same information, lossier presentation. Builder can re-run
    inception or hand-draft a mermaid diagram from the skill list.
    """
    skill_lines = "\n".join(
        f"- **`{s.name}`** ({s.suggested_body_shape}): {s.purpose}"
        for s in skills.skills
    )
    body = (
        f"# Architecture — {architecture.selected_pattern_slug} (FALLBACK)\n\n"
        f"**Runtime:** {runtime.selected_runtime} + {runtime.selected_model_family}  \n"
        f"**Architecture pattern:** `{architecture.selected_pattern_slug}` ({architecture.selected_pattern_title})\n\n"
        f"LLM-side generation of the architecture diagram failed in this run. "
        f"This file is a deterministic fallback assembled from the upstream "
        f"Pydantic outputs — same content, no visual diagrams. To regenerate "
        f"diagrams, re-run inception (`agent.cli inception --session-id <sid>` "
        f"— the upstream meta/ checkpoints will skip the LLM cost of steps 1-4).\n\n"
        f"**Failure detail:** {failure_reason}\n\n"
        f"---\n\n"
        f"## Skills\n\n"
        f"{skill_lines}\n\n"
        f"## Where to go next\n\n"
        f"- `orchestrator.py` shows the runtime wiring\n"
        f"- `design_rationale.md` explains why each decision was made (with citations)\n"
        f"- `skills/<name>/SKILL.md` describes each skill's contract\n"
    )
    (output_dir / "architecture.md").write_text(body)


def _write_orchestrator_stub_fallback(
    output_dir: Path,
    skills: SkillProposalResult,
    architecture: ArchitectureProposal,
    runtime: RuntimeProposal,
    failure_reason: str,
) -> None:
    """Write an orchestrator.py stub when the LLM generation failed.

    The stub is honest: it declares the architecture + runtime + skill list
    in a docstring, raises NotImplementedError on import, and points at
    meta/ for the structured upstream outputs the builder can re-fed into
    a fresh inception run or use as the basis for hand-writing the loop.
    """
    skills_list = "\n".join(f"  - {s.name}: {s.purpose[:80]}" for s in skills.skills)
    body = (
        f'"""Orchestrator stub for this agent (LLM generation failed during inception).\n\n'
        f"Selected architecture: {architecture.selected_pattern_slug}\n"
        f"Selected runtime: {runtime.selected_runtime} + {runtime.selected_model_family}\n\n"
        f"Proposed skills (see skills/<name>/SKILL.md for details where written):\n"
        f"{skills_list}\n\n"
        f"LLM-side generation of orchestrator.py failed in this run. Reasons in\n"
        f"meta/04_runtime_proposal.json + meta/03_architecture_proposal.json should\n"
        f"give a builder enough to hand-wire the orchestrator. To re-generate via\n"
        f"the pipeline, re-run `agent.cli inception --session-id <sid>` — the meta/\n"
        f"artifacts are already on disk, so only this step needs to retry.\n\n"
        f"Failure detail: {failure_reason}\n"
        f'"""\n\n'
        f"raise NotImplementedError(\n"
        f'    "Orchestrator stub generation failed during inception. "\n'
        f'    "Re-run `agent.cli inception --session-id <sid>` or hand-wire from meta/."\n'
        f")\n"
    )
    (output_dir / "orchestrator.py").write_text(body)


def _write_design_rationale_fallback(
    output_dir: Path,
    workload: WorkloadClassification,
    skills: SkillProposalResult,
    architecture: ArchitectureProposal,
    runtime: RuntimeProposal,
    failure_reason: str,
) -> None:
    """Write a deterministic design_rationale.md from the upstream Pydantic
    outputs when the LLM rationale generation failed. Lossier than the
    LLM version but still substantive — captures the four decisions and
    their rationale fields verbatim from the structured outputs.
    """
    parts = [
        "# Design rationale (FALLBACK — LLM aggregation failed)\n",
        "The narrative aggregation of the inception pipeline's decisions failed mid-run. ",
        "This file is assembled deterministically from the four upstream Pydantic outputs. ",
        "For richer prose, re-run inception (the meta/ artifacts are on disk, so a retry ",
        "can pick up where this run failed).\n\n",
        f"**Failure detail:** {failure_reason}\n\n",
        "---\n\n",
        "## Workload classification\n\n",
        f"- Interaction shape: `{workload.interaction_shape}`\n",
        f"- Latency sensitivity: `{workload.latency_sensitivity}`\n",
        f"- Decision complexity: `{workload.decision_complexity}`\n",
        f"- Data intensity: `{workload.data_intensity}`\n",
        f"- Multi-step or single-step: `{workload.multi_step_or_single_step}`\n",
        f"- State shape: `{workload.state_shape}`\n",
        f"- Confidence: `{workload.confidence:.2f}`\n\n",
        f"Rationale: {workload.rationale}\n\n",
        "## Proposed skills\n\n",
    ]
    for s in skills.skills:
        parts.append(f"### `{s.name}`\n\n")
        parts.append(f"**Purpose:** {s.purpose}\n\n")
        parts.append(f"**Type:** {s.skill_type}\n\n")
    parts.append("## Architecture\n\n")
    parts.append(f"- Pattern: `{architecture.selected_pattern_slug}`\n")
    parts.append(f"- Rationale: {architecture.rationale}\n\n")
    parts.append("## Runtime\n\n")
    parts.append(f"- Runtime: `{runtime.selected_runtime}`\n")
    parts.append(f"- Model: `{runtime.selected_model_family}`\n")
    parts.append(f"- Rationale: {runtime.rationale}\n")
    (output_dir / "design_rationale.md").write_text("".join(parts))


def _starter_readme(
    skill_md_results: list[SkillMdContent],
    stub: OrchestratorStub | None,
    architecture: ArchitectureProposal,
    runtime: RuntimeProposal,
) -> str:
    """Deterministic README assembler. No LLM call — pure templating from upstream data."""
    skills_list = (
        "\n".join(f"- `skills/{c.skill_name}/SKILL.md`" for c in skill_md_results)
        if skill_md_results
        else "(skill generation failed — see scaffold_errors)"
    )
    imports_list = (
        "\n".join(f"- `{imp}`" for imp in stub.imports_needed)
        if (stub and stub.imports_needed)
        else "(none listed)"
    )
    env_vars_list = (
        "\n".join(f"- `{var}`" for var in stub.env_vars_needed)
        if (stub and stub.env_vars_needed)
        else "(none listed)"
    )

    return (
        f"# agent_starter/\n\n"
        f"Starter agent design produced by discovery-inception's inception pipeline.\n\n"
        f"**Architecture:** `{architecture.selected_pattern_slug}` — {architecture.selected_pattern_title}  \n"
        f"**Runtime:** {runtime.selected_runtime} + {runtime.selected_model_family}\n\n"
        f"## Read this first\n\n"
        f"This is a STARTER, not a finished agent. The orchestrator's wiring is in place; skill bodies are TODO markers.\n\n"
        f"Expected first-pass quality: ~75/100 on LLM-as-judge eval. The builder iterates from here. For an empirical receipt of "
        f"what a 97/100 endpoint looks like with this architectural shape, see the public reference build at "
        f"https://github.com/bladata1990/pg-brand-analyst-agent.\n\n"
        f"**Reading order:**\n"
        f"1. `architecture.md` — Mermaid diagrams + 2-paragraph summary. 30-second overview of the agent's shape.\n"
        f"2. `design_rationale.md` — why each decision was made, with citations into `patterns/`. Read before iterating.\n"
        f"3. `skills/<name>/SKILL.md` per skill — start with the one whose body you're about to implement.\n\n"
        f"## Structure\n\n"
        f"```\n"
        f"agent_starter/\n"
        f"├── README.md            ← this file\n"
        f"├── architecture.md      ← Mermaid diagrams (READ FIRST)\n"
        f"├── design_rationale.md  ← audit trail (READ SECOND)\n"
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
        f"1. Read `architecture.md` for the 30-second mental model\n"
        f"2. Read `design_rationale.md` for the audit trail\n"
        f"3. Read each SKILL.md and implement the skill body (replace the TODO markers)\n"
        f"4. Run the orchestrator end-to-end against synthetic data\n"
        f"5. Add eval questions once the agent boots; an LLM-as-judge harness is the recommended methodology "
        f"(see the canonical pattern — 5 dimensions: accuracy, root-cause classification, "
        f"hallucination, reasoning quality, actionability)\n"
        f"6. Iterate from initial pass to target quality\n\n"
        f"## Provenance\n\n"
        f"`meta/01_workload_classification.json`, `meta/02_skill_proposal.json`, `meta/03_architecture_proposal.json`, "
        f"`meta/04_runtime_proposal.json` contain the structured outputs of each inception step. `meta/spec_consumed.md` "
        f"and `meta/role_context_consumed.json` are the inputs that produced this starter — useful when comparing iterations "
        f"or running the inception pipeline against a new version of the spec.\n"
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _try_resume_step(
    output_dir: Path | None,
    filename: str,
    model_cls: type[BaseModel],
) -> BaseModel | None:
    """Try to load a checkpointed Pydantic output from `output_dir/meta/`.

    Returns the parsed model on success, None when the file is absent or
    fails to parse. Used to skip steps 1-4 on retries when a previous
    inception run already checkpointed the upstream LLM outputs to disk.

    Resume is opt-in by file existence — no flag needed. If you want a
    fresh run, delete the meta/ directory (or pass --force on the CLI).
    """
    if output_dir is None:
        return None
    path = output_dir / "meta" / filename
    if not path.exists():
        return None
    try:
        return model_cls.model_validate_json(path.read_text())
    except Exception:
        return None


async def run_inception(
    spec_md: str,
    role_context_json: str,
    output_dir: Path | None = None,
    prior_feedback: PriorIterationFeedback | None = None,
    force_fresh: bool = False,
) -> dict:
    """Run the inception pipeline.

    Steps 1-4 always run. Step 5 (scaffold_writer) runs only when output_dir
    is provided — that's the step that materializes the agent_starter/
    directory on disk.

    Resume from checkpoint: when `output_dir` is provided AND
    `force_fresh=False`, each of steps 1-4 checks for a corresponding
    `meta/<step>.json` artifact from a prior run and loads it instead of
    re-calling the LLM. A previous step-5 crash that wasted nothing thanks
    to this — retries pay zero LLM cost for the four upstream decisions.
    To force a clean re-run (e.g., the spec changed), pass `force_fresh=True`
    or delete `output_dir/meta/`.

    `prior_feedback` (intra-session iteration): each sub-agent's prompt
    gains a "Prior iteration feedback" section. Feedback presence forces
    fresh upstream LLM calls — checkpoints from before the feedback would
    bake in the rejected decisions.
    """
    client = _client()

    # Feedback runs always re-execute upstream — the whole point is the
    # constraints flow into those sub-agents.
    effective_force = force_fresh or (prior_feedback is not None)

    try:
        if prior_feedback:
            print(
                f"→ Loop 2: prior iteration {prior_feedback.iteration} feedback present "
                f"({len(prior_feedback.items)} items, "
                f"{sum(1 for i in prior_feedback.items if i.feedback_type == 'wrong_for_this_use_case')} wrong / "
                f"{sum(1 for i in prior_feedback.items if i.feedback_type == 'missing')} missing). "
                "Sub-agents will consume as constraints; checkpoints will be bypassed."
            )
            if prior_feedback.source:
                print(f"   source: {prior_feedback.source}")
            print()

        # ---- Step 1: workload classifier (with resume check) ----
        classification = (
            None if effective_force
            else _try_resume_step(output_dir, "01_workload_classification.json", WorkloadClassification)
        )
        if classification is not None:
            print("→ Step 1/6: workload_classifier  [resumed from meta/01_workload_classification.json]")
        else:
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
        proposal = (
            None if effective_force
            else _try_resume_step(output_dir, "02_skill_proposal.json", SkillProposalResult)
        )
        if proposal is not None:
            print(f"→ Step 2/6: skill_proposer  [resumed from meta/02_skill_proposal.json]")
        else:
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
        architecture = (
            None if effective_force
            else _try_resume_step(output_dir, "03_architecture_proposal.json", ArchitectureProposal)
        )
        if architecture is not None:
            print(f"→ Step 3/6: architecture_proposer  [resumed from meta/03_architecture_proposal.json]")
        else:
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
        runtime = (
            None if effective_force
            else _try_resume_step(output_dir, "04_runtime_proposal.json", RuntimeProposal)
        )
        if runtime is not None:
            print(f"→ Step 4/6: runtime_proposer  [resumed from meta/04_runtime_proposal.json]")
        else:
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
            "inception with builder feedback on a previous starter."
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
