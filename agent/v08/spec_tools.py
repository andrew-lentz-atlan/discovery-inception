"""v0.8 tools — same v0.7 tools + find_tensions.

find_tensions is the third lazy tool: it runs a focused sub-agent that
surfaces implicit contradictions in captured facts. Distinct from
synthesize_my_thinking (which updates the full theory) because tension
detection is a different cognitive task — adversarial, not constructive.
The agent can call find_tensions when it suspects something doesn't fit
together without having to rebuild the whole theory.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from openai import AsyncOpenAI

from agent.schemas import TensionsResult
from agent.state import DiscoverySession
from agent.v07.spec_tools import (
    get_current_spec_state,
    get_checklist_progress,
    synthesize_my_thinking,
    TOOL_SCHEMAS as V07_TOOL_SCHEMAS,
)


# ---------------------------------------------------------------------------
# find_tensions — the lazy tool that invokes the tensions sub-agent
# ---------------------------------------------------------------------------

async def find_tensions(
    client: AsyncOpenAI,
    session: DiscoverySession,
    run_tensions_call: Callable,
) -> str:
    """Invoke the tensions-detection sub-agent on the current state."""
    from agent.orchestrator import load_prompt, _spec_state_summary

    # Build recent_facts string — last 10 facts in order, with topic + source.
    recent_facts_lines: list[str] = []
    all_facts: list[tuple[str, str, str]] = []
    for topic in session.spec.topics:
        for fact, source in zip(topic.facts, topic.sources):
            all_facts.append((topic.topic, fact, source))
    for topic_name, fact, source in all_facts[-10:]:
        recent_facts_lines.append(f"- [{topic_name}, {source}] {fact}")
    recent_facts = "\n".join(recent_facts_lines) if recent_facts_lines else "(no facts captured yet)"

    working_theory_str = (
        session.spec.working_theory.model_dump_json(indent=2)
        if session.spec.working_theory
        else "(no working theory yet)"
    )

    prompt = load_prompt(
        "07_find_tensions.md",
        SPEC_STATE_SUMMARY=_spec_state_summary(session),
        RECENT_FACTS=recent_facts,
        WORKING_THEORY=working_theory_str,
    )

    result, _ms, _model = await run_tensions_call(client=client, prompt=prompt)
    return result.model_dump_json(indent=2)


# ---------------------------------------------------------------------------
# OpenAI tool schemas — v0.7 tools + find_tensions
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = V07_TOOL_SCHEMAS + [
    {
        "type": "function",
        "function": {
            "name": "find_tensions",
            "description": (
                "Run an adversarial review of all captured facts and surface "
                "implicit contradictions — places where two things the customer "
                "said don't fit together. Returns 0-3 one-sentence tensions; "
                "empty list is the common case. Use this when you suspect "
                "something doesn't add up, after a customer makes contradictory "
                "claims, or before declaring discovery complete. EXPENSIVE "
                "(~3-5 seconds) — call deliberately, not on every turn."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def make_v08_dispatcher(
    session: DiscoverySession,
    client: AsyncOpenAI,
    run_synthesizer_call: Callable,
    run_tensions_call: Callable,
):
    """v0.8 dispatcher: inherits v0.7 tools + adds find_tensions."""

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
            if name == "find_tensions":
                return await find_tensions(client, session, run_tensions_call)
            return f"Error: unknown tool '{name}'."
        except Exception as exc:
            return f"Error executing {name}: {exc}"

    return dispatch
