"""Shared minimal-model factories for the inception test suite.

Mirrors the `_wl/_sp/_ap/_rp` helper pattern established in
tests/test_inception_resume.py (kept self-contained there; new test files
import from here instead of re-duplicating). Every factory builds the
smallest VALID instance of its schema — required fields only, defaults
elsewhere — so tests exercise plumbing, not prompt content.
"""
from __future__ import annotations

from agent.inception.schemas import (
    ArchitectureDiagram,
    ArchitectureProposal,
    AtlanContextLayer,
    DesignRationale,
    EvalQuestion,
    EvalSeed,
    JudgeHarness,
    OrchestratorStub,
    ProposedSkill,
    RuntimeProposal,
    SkillMdContent,
    SkillProposalResult,
    SkillProvenance,
    WorkloadClassification,
)


def make_workload() -> WorkloadClassification:
    return WorkloadClassification(
        interaction_shape="conversational",
        latency_sensitivity="tolerant",
        decision_complexity="judgment-heavy",
        data_intensity="light",
        multi_step_or_single_step="multi",
        state_shape="session-scoped",
        confidence=0.8,
        rationale="test",
    )


def make_skill(name: str = "skill_a") -> ProposedSkill:
    return ProposedSkill(name=name, purpose=f"purpose of {name}", provenance=SkillProvenance())


def make_skill_proposal(skill_names: tuple[str, ...] = ()) -> SkillProposalResult:
    return SkillProposalResult(
        skills=[make_skill(n) for n in skill_names],
        rationale="r",
        granularity_argument="g",
        atlan_context_layer=AtlanContextLayer(repo_recommendation="repo", rationale="r"),
    )


def make_architecture() -> ArchitectureProposal:
    return ArchitectureProposal(
        selected_pattern_slug="single-agent-react",
        selected_pattern_title="Single-Agent ReAct",
        selection_rationale="r",
        confidence=0.8,
    )


def make_runtime() -> RuntimeProposal:
    return RuntimeProposal(
        selected_runtime="LangGraph",
        selected_model_family="claude-haiku-4-5",
        selection_rationale="r",
        confidence=0.8,
    )


# ---- Scaffold sub-step outputs (step 5a-5f fakes return these) ----

def make_skill_md(name: str) -> SkillMdContent:
    return SkillMdContent(skill_name=name, skill_md=f"# {name}\n\nbody\n")


def make_orchestrator_stub() -> OrchestratorStub:
    return OrchestratorStub(
        orchestrator_py="# generated orchestrator\n",
        imports_needed=["anthropic>=0.40"],
        env_vars_needed=["ANTHROPIC_API_KEY"],
    )


def make_design_rationale() -> DesignRationale:
    return DesignRationale(rationale_md="# design rationale\n")


def make_eval_seed() -> EvalSeed:
    return EvalSeed(
        questions=[
            EvalQuestion(id="Q01", question="why?", category="smoke", test_intent="t")
        ],
        coverage_notes="c",
        data_requirements="d",
    )


def make_judge_harness() -> JudgeHarness:
    return JudgeHarness(judge_py="# generated judge\n", dimensions=["accuracy"])


def make_architecture_diagram() -> ArchitectureDiagram:
    return ArchitectureDiagram(
        skill_graph_mermaid="graph TD\n  a --> b",
        execution_flow_mermaid="sequenceDiagram\n  U->>O: q",
        summary_md="two paragraphs",
    )


class FakeClient:
    """Stands in for AsyncOpenAI where only `.close()` is awaited."""

    async def close(self) -> None:
        pass
