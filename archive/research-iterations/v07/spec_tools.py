"""v0.7 tools — same shape as v0.6 spec_tools but with the synthesizer
moved from eager (every turn) to lazy (invoked when the mega-agent calls
the tool).

Three tools:
  - get_current_spec_state()  — cheap read of structured state
  - get_checklist_progress()  — cheap read of coverage
  - synthesize_my_thinking()  — EXPENSIVE: invokes the synthesizer
                                 sub-agent NOW to produce a fresh
                                 WorkingTheory given the current state
                                 + conversation. ~3-5s.

The "skill as a tool" inversion the architecture was always meant to
encode: the mega-agent stays in charge of the conversation; when it
wants to step back and synthesize, it calls a tool that runs the
synthesizer skill. Symmetric with how a human consultant works — they
don't continuously maintain a structured theory; they pause to reflect
when the moment calls for it.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from openai import AsyncOpenAI

from agent.schemas import WorkingTheory
from agent.state import (
    BEDROCK_ADVISORY_TOPICS,
    CANONICAL_CHECKLIST_TOPICS,
    DiscoverySession,
    MULTI_INSTANCE_REQUIREMENTS,
    evaluate_checklist,
)
from agent.v06.spec_tools import (
    get_current_spec_state as v06_get_current_spec_state,
    get_checklist_progress as v06_get_checklist_progress,
)


# ---------------------------------------------------------------------------
# Read-tools — reuse v0.6 implementations (these are pure functions over state)
# ---------------------------------------------------------------------------

get_current_spec_state = v06_get_current_spec_state
get_checklist_progress = v06_get_checklist_progress


# ---------------------------------------------------------------------------
# synthesize_my_thinking — the lazy tool that invokes the synthesizer
# ---------------------------------------------------------------------------

async def synthesize_my_thinking(
    client: AsyncOpenAI,
    session: DiscoverySession,
    run_synthesizer_call: Callable,
) -> str:
    """Invoke the synthesizer sub-agent on the current state.

    Reads everything available: customer's latest message, the full
    structured spec, prior theory, priors, and the conversation history
    indirectly through the spec state summary.

    Updates session.spec.working_theory in place + appends the prior
    theory to theory_history. Returns a stringified representation of
    the new theory for the mega-agent to see.
    """
    # Build the synthesizer prompt by reusing the v0.5 helpers
    from agent.orchestrator import (
        load_prompt,
        _spec_state_summary,
        _relevant_priors,
    )

    # Find the latest customer message in the session's message log.
    customer_message = ""
    for m in reversed(session.messages):
        if m.role == "customer":
            customer_message = m.content
            break

    prior_theory_json = (
        session.spec.working_theory.model_dump_json(indent=2)
        if session.spec.working_theory
        else "(no prior theory yet — this is the first synthesis this session)"
    )
    synth_prompt = load_prompt(
        "05_synthesizer.md",
        USE_CASE_SEED=session.spec.use_case_seed,
        SPEC_STATE_SUMMARY=_spec_state_summary(session),
        CUSTOMER_MESSAGE=customer_message,
        PRIOR_THEORY=prior_theory_json,
        RELEVANT_PRIORS=_relevant_priors(session, None),
    )

    # run_synthesizer_call is supplied by the orchestrator and wraps the
    # standard call_sub_agent flow.
    new_theory, duration_ms, model = await run_synthesizer_call(
        client=client,
        prompt=synth_prompt,
    )

    # Mutate the session — the new theory IS the structured output of the call
    if session.spec.working_theory is not None:
        session.spec.theory_history.append(session.spec.working_theory)
    session.spec.working_theory = new_theory
    session.save()

    return new_theory.model_dump_json(indent=2)


# ---------------------------------------------------------------------------
# OpenAI tool schemas
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_current_spec_state",
            "description": (
                "Get the full current state of the discovery spec — current phase, "
                "all topics with their recorded facts, flagged gaps, and the last "
                "stored working theory (if any). CHEAP read of structured state. "
                "Use this to orient yourself on what's been recorded so far without "
                "triggering a synthesis call."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_checklist_progress",
            "description": (
                "Get the canonical-topic coverage checklist: which topics have "
                "facts recorded, which are still missing, and the current phase. "
                "CHEAP read of structured state. Use this to decide breadth vs depth."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "synthesize_my_thinking",
            "description": (
                "PAUSE TO REFLECT. Runs the synthesizer skill NOW to produce a "
                "fresh working theory of what the customer wants built — including "
                "one-line framing, 2-3 alternative shapes the request could take, "
                "the open questions that would most sharpen the theory, and what "
                "observation would prove it wrong. EXPENSIVE (3-5 seconds) — call "
                "this when you want to step back and think, not on every turn. "
                "Especially useful when: the conversation feels stuck, you want to "
                "play back a theory to the customer, you've just gotten new "
                "information that should update your mental model, or you're "
                "deciding between several next-question options."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def make_v07_dispatcher(
    session: DiscoverySession,
    client: AsyncOpenAI,
    run_synthesizer_call: Callable,
):
    """Bind session + client + synthesizer-runner into an async dispatcher."""

    async def dispatch(name: str, args: dict[str, Any]) -> str:
        try:
            if name == "get_current_spec_state":
                return get_current_spec_state(session)
            if name == "get_checklist_progress":
                return get_checklist_progress(session)
            if name == "synthesize_my_thinking":
                return await synthesize_my_thinking(
                    client, session, run_synthesizer_call
                )
            return f"Error: unknown tool '{name}'."
        except Exception as exc:
            return f"Error executing {name}: {exc}"

    return dispatch
