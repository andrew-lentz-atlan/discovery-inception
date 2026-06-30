"""LangGraph orchestration adapter for the inception pipeline.

Ports & adapters: the `step_*` functions in `run.py` ARE the contract (prompts +
schemas + `call_step`). `run.run_inception` is the hand-rolled orchestration
adapter; this module is the LangGraph adapter. Both call the SAME `step_*`
functions, so the LLM path is byte-identical and an A/B differs ONLY by the
orchestration substrate — exactly the condition the runtime-portability finding
(findings/10) established as decision-neutral.

Phase 1 scope: the decision core (steps 1-4). The scaffold fan-out (step 5,
5a-5f), checkpoint/resume, and the discovery side stay on `run_inception` for
now. `run_inception_graph` returns the same steps-1-4 dict shape
(`scaffold_output=None`) so callers and the A/B harness can swap adapters freely.

The Python engine (`run_inception`) stays as the reference oracle: port a slice →
A/B against it → only cut over once it provably matches.
"""
from __future__ import annotations

from typing import TypedDict

from openai import AsyncOpenAI
from langgraph.graph import StateGraph, START, END

from agent.inception.run import (
    _client,
    PriorIterationFeedback,
    step_workload_classifier,
    step_skill_proposer,
    step_architecture_proposer,
    step_runtime_proposer,
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
    classification: WorkloadClassification
    proposal: SkillProposalResult
    architecture: ArchitectureProposal
    runtime: RuntimeProposal


def build_inception_graph(client: AsyncOpenAI):
    """Compile the steps-1-4 StateGraph. `client` is captured in the node
    closures so it never enters graph state."""

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

    g = StateGraph(InceptionState)
    g.add_node("classify", classify)
    g.add_node("skills", skills)
    g.add_node("architecture", architecture)
    g.add_node("runtime", runtime)
    g.add_edge(START, "classify")
    g.add_edge("classify", "skills")
    g.add_edge("skills", "architecture")
    g.add_edge("architecture", "runtime")
    g.add_edge("runtime", END)
    return g.compile()


async def run_inception_graph(
    spec_md: str,
    role_context_json: str,
    prior_feedback: PriorIterationFeedback | None = None,
    spec_structured: str | None = None,
) -> dict:
    """LangGraph adapter for inception steps 1-4.

    Mirrors `run.run_inception`'s steps-1-4 return shape (with
    `scaffold_output=None`) so it's a drop-in for callers that only need the
    decisions. Step 5 (scaffold) is intentionally not ported in phase 1.
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
            }
        )
    finally:
        await client.close()

    return {
        "classification": final["classification"].model_dump(),
        "skill_proposal": final["proposal"].model_dump(),
        "architecture_proposal": final["architecture"].model_dump(),
        "runtime_proposal": final["runtime"].model_dump(),
        "scaffold_output": None,
        "next_step": "langgraph adapter — steps 1-4 only (scaffold fan-out not ported)",
    }
