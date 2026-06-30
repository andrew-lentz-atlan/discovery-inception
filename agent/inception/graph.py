"""LangGraph orchestration adapter for the inception pipeline.

Ports & adapters: the `step_*` functions in `run.py` ARE the contract (prompts +
schemas + `call_step`, and for scaffolding the fan-out + per-substep tolerance +
file-writing in `step_scaffold_writer`). `run.run_inception` is the hand-rolled
orchestration adapter; this module is the LangGraph adapter. Both call the SAME
`step_*` functions, so the LLM path is byte-identical and an A/B differs ONLY by
the orchestration substrate — the runtime-portability finding (findings/10),
which we reproduced on the production step functions (decision A/B: architecture
identical; the only DIFF was a borderline classification axis the engine flips on
against itself).

Scope (phase 1 + 2): the full decision-and-scaffold pipeline (steps 1-5). The
graph owns the MACRO flow — classify → skills → architecture → runtime → (if
output_dir) scaffold. The scaffold node calls `step_scaffold_writer` wholesale;
its internal 5a-5f fan-out (asyncio.gather with per-substep exception tolerance
and fallback writers) stays inside the function — that's hardened contract logic,
not orchestration glue, so the adapter stays thin.

NOT yet ported: resume/checkpoint (the oracle's `meta/*.json` mechanism — see the
note in research-log on why a native LangGraph checkpointer is deferred) and the
discovery side (the mega-agent ReAct loop). `run_inception` stays the reference
ORACLE: A/B against it, cut over only once it provably matches.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from openai import AsyncOpenAI
from langgraph.graph import StateGraph, START, END

from agent.inception.run import (
    _client,
    PriorIterationFeedback,
    step_workload_classifier,
    step_skill_proposer,
    step_architecture_proposer,
    step_runtime_proposer,
    step_scaffold_writer,
)
from agent.inception.schemas import (
    WorkloadClassification,
    SkillProposalResult,
    ArchitectureProposal,
    RuntimeProposal,
)


class InceptionState(TypedDict, total=False):
    """Graph state. Inputs are set on the initial invoke; each node writes one
    output key (distinct keys → default overwrite reducer is correct, no
    conflicts). The AsyncOpenAI client is captured in the node closures, not the
    state, so nothing un-serializable rides in state (keeps a checkpointer
    addable later without a redesign)."""

    spec_md: str
    role_context_json: str
    spec_structured: str | None
    prior_feedback: PriorIterationFeedback | None
    output_dir: Path | None
    classification: WorkloadClassification
    proposal: SkillProposalResult
    architecture: ArchitectureProposal
    runtime: RuntimeProposal
    scaffold_output: dict[str, Any] | None


def build_inception_graph(client: AsyncOpenAI):
    """Compile the steps-1-5 StateGraph. `client` is captured in the node
    closures so it never enters graph state. The scaffold node only runs when
    `output_dir` is set (conditional edge after `runtime`)."""

    async def classify(state: InceptionState) -> dict:
        c = await step_workload_classifier(
            client,
            state["spec_md"],
            state["role_context_json"],
            prior_feedback=state.get("prior_feedback"),
            spec_structured=state.get("spec_structured"),
        )
        return {"classification": c}

    async def skills(state: InceptionState) -> dict:
        p = await step_skill_proposer(
            client,
            state["classification"],
            state["spec_md"],
            state["role_context_json"],
            prior_feedback=state.get("prior_feedback"),
            spec_structured=state.get("spec_structured"),
        )
        return {"proposal": p}

    async def architecture(state: InceptionState) -> dict:
        a = await step_architecture_proposer(
            client,
            state["classification"],
            state["proposal"],
            prior_feedback=state.get("prior_feedback"),
            spec_structured=state.get("spec_structured"),
        )
        return {"architecture": a}

    async def runtime(state: InceptionState) -> dict:
        r = await step_runtime_proposer(
            client,
            state["classification"],
            state["proposal"],
            state["architecture"],
            prior_feedback=state.get("prior_feedback"),
        )
        return {"runtime": r}

    async def scaffold(state: InceptionState) -> dict:
        summary = await step_scaffold_writer(
            client,
            state["classification"],
            state["proposal"],
            state["architecture"],
            state["runtime"],
            spec_md=state["spec_md"],
            role_context_json=state["role_context_json"],
            output_dir=state["output_dir"],
        )
        return {"scaffold_output": summary}

    def route_after_runtime(state: InceptionState) -> str:
        """Step 5 runs only when an output_dir is provided — same gate as
        run_inception (steps 1-4 always run; scaffold materializes on disk)."""
        return "scaffold" if state.get("output_dir") is not None else END

    g = StateGraph(InceptionState)
    g.add_node("classify", classify)
    g.add_node("skills", skills)
    g.add_node("architecture", architecture)
    g.add_node("runtime", runtime)
    g.add_node("scaffold", scaffold)
    g.add_edge(START, "classify")
    g.add_edge("classify", "skills")
    g.add_edge("skills", "architecture")
    g.add_edge("architecture", "runtime")
    g.add_conditional_edges("runtime", route_after_runtime, {"scaffold": "scaffold", END: END})
    g.add_edge("scaffold", END)
    return g.compile()


async def run_inception_graph(
    spec_md: str,
    role_context_json: str,
    output_dir: Path | None = None,
    prior_feedback: PriorIterationFeedback | None = None,
    spec_structured: str | None = None,
) -> dict:
    """LangGraph adapter for the inception pipeline.

    Mirrors `run.run_inception`'s return shape. Steps 1-4 always run; step 5
    (scaffold) runs only when `output_dir` is provided — identical gating to the
    oracle, so this is a drop-in for either the decisions-only or the full-build
    path.
    """
    client = _client()
    graph = build_inception_graph(client)
    try:
        final = await graph.ainvoke(
            {
                "spec_md": spec_md,
                "role_context_json": role_context_json,
                "spec_structured": spec_structured,
                "prior_feedback": prior_feedback,
                "output_dir": output_dir,
            }
        )
    finally:
        await client.close()

    return {
        "classification": final["classification"].model_dump(),
        "skill_proposal": final["proposal"].model_dump(),
        "architecture_proposal": final["architecture"].model_dump(),
        "runtime_proposal": final["runtime"].model_dump(),
        "scaffold_output": final.get("scaffold_output"),
        "next_step": (
            "langgraph adapter — full pipeline (steps 1-5)"
            if output_dir is not None
            else "langgraph adapter — steps 1-4 (no output_dir → scaffold skipped)"
        ),
    }
