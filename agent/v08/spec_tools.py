"""v0.8 mega-agent spec tools — SELF-CONTAINED (no longer chains through v0.6/v0.7).

These are the read/reflect tools the v0.8 mega-agent calls mid-conversation to
introspect on the structured discovery state:

  - get_current_spec_state()  -> full snapshot (phase, topics+facts, gaps, theory)
  - get_checklist_progress()  -> canonical-topic coverage + ready check
  - synthesize_my_thinking()  -> run the synthesizer; update working theory
  - find_tensions()           -> adversarial review for implicit contradictions

History note: these first three used to live in agent/v06/spec_tools.py and be
re-exported up through v0.7 to here. That chain made v0.6/v0.7 *live* (not the
dead research iterations they appeared to be) and hid a real bug: when Issue A
folded TopicEntry's parallel facts[]/sources[] arrays into list[FactRecord],
get_current_spec_state's `zip(t.facts, t.sources)` broke — and it's a tool the
mega-agent calls every discovery turn. Consolidating the live tools here makes
v0.8 self-contained, fixes the FactRecord reader, and lets v0.6/v0.7 finally
retire to archive/.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from openai import AsyncOpenAI

from agent.schemas import TensionsResult
from agent.state import (
    BEDROCK_ADVISORY_TOPICS,
    CANONICAL_CHECKLIST_TOPICS,
    DiscoverySession,
    MULTI_INSTANCE_REQUIREMENTS,
    evaluate_checklist,
)


# ---------------------------------------------------------------------------
# Read tools — pure functions over session state, returned as strings the
# mega-agent reads. CHEAP (no LLM call).
# ---------------------------------------------------------------------------

def get_current_spec_state(session: DiscoverySession) -> str:
    """Full snapshot — phase, topics + facts (with provenance), gaps, theory."""
    spec = session.spec
    out: list[str] = []
    out.append(f"Phase: {spec.phase}")
    out.append("")
    out.append("Topics + facts so far:")
    if not spec.topics:
        out.append("  (none yet — no concrete answers recorded)")
    else:
        for t in spec.topics:
            bedrock = " [BEDROCK]" if t.bedrock_reached else ""
            out.append(f"  {t.topic} ({len(t.facts)} fact(s)){bedrock}:")
            # FactRecord-aware (Issue A): each fact carries source + optional
            # artifact provenance. Show the artifact id when present so the
            # mega-agent can attribute facts to their source on the fly.
            for fr in t.facts:
                prov = f" (from {fr.artifact_id})" if fr.artifact_id else ""
                out.append(f"    - [{fr.source}]{prov} {fr.content}")
            if t.superseded_facts:
                out.append("    superseded:")
                for sf in t.superseded_facts:
                    out.append(f"      ~ {sf}")
    if spec.gaps:
        out.append("")
        out.append("Flagged gaps (for downstream FDE follow-up):")
        for g in spec.gaps:
            out.append(f"  - {g.question}")
            out.append(f"    why: {g.why_it_matters}")
    if spec.working_theory:
        wt = spec.working_theory
        out.append("")
        out.append(f"Working theory (confidence={wt.confidence}):")
        out.append(f"  framing: {wt.one_line_framing}")
        if wt.candidate_framings:
            out.append("  candidate framings:")
            for cf in wt.candidate_framings:
                out.append(f"    - {cf}")
        if wt.open_questions:
            out.append("  open questions that would sharpen the theory:")
            for q in wt.open_questions:
                out.append(f"    - {q}")
        out.append(f"  sharpest disconfirmer: {wt.sharpest_disconfirmer}")
    return "\n".join(out)


def get_checklist_progress(session: DiscoverySession) -> str:
    """Phase + checklist coverage. The model uses this to decide breadth vs depth."""
    spec = session.spec
    checklist = evaluate_checklist(spec)
    topics_by_name = {t.topic: t for t in spec.topics}

    out: list[str] = []
    out.append(f"Phase: {spec.phase}")
    out.append("")
    out.append("Canonical-topic coverage:")
    for topic in CANONICAL_CHECKLIST_TOPICS:
        n_required = MULTI_INSTANCE_REQUIREMENTS.get(topic, 1)
        entry = topics_by_name.get(topic)
        n_have = len(entry.facts) if entry else 0
        ok = n_have >= n_required
        marker = "✓" if ok else "·"
        out.append(f"  {marker} {topic}: {n_have} fact(s) (need {n_required})")
    out.append("")
    out.append("Bedrock (advisory — surfaced for visibility, not blocking ready):")
    for topic in BEDROCK_ADVISORY_TOPICS:
        entry = topics_by_name.get(topic)
        ok = entry is not None and entry.bedrock_reached
        marker = "✓" if ok else "·"
        out.append(f"  {marker} bedrock_on_{topic}")
    out.append("")
    out.append(
        f"Hard requirements remaining: {len([m for m in checklist.missing if 'advisory' not in m])}"
    )
    out.append(f"Ready to declare? {checklist.ready}")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# synthesize_my_thinking — the lazy tool that invokes the synthesizer sub-agent
# ---------------------------------------------------------------------------

async def synthesize_my_thinking(
    client: AsyncOpenAI,
    session: DiscoverySession,
    run_synthesizer_call: Callable,
) -> str:
    """Invoke the synthesizer sub-agent on the current state.

    Reads the customer's latest message + the full structured spec + prior
    theory + priors. Updates session.spec.working_theory in place (appending
    the prior theory to theory_history) and returns the new theory as a string.
    """
    from agent.orchestrator import (
        load_prompt,
        _spec_state_summary,
        _relevant_priors,
    )

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

    new_theory, _duration_ms, _model = await run_synthesizer_call(
        client=client,
        prompt=synth_prompt,
    )

    if session.spec.working_theory is not None:
        session.spec.theory_history.append(session.spec.working_theory)
    session.spec.working_theory = new_theory
    session.save()

    return new_theory.model_dump_json(indent=2)


# ---------------------------------------------------------------------------
# find_tensions — the lazy tool that invokes the tensions sub-agent (v0.8+)
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
        for fr in topic.facts:
            all_facts.append((topic.topic, fr.content, fr.source))
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
# OpenAI tool schemas — the four mega-agent tools
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_current_spec_state",
            "description": (
                "Get the full current state of the discovery spec — current phase, "
                "all topics with their recorded facts (and which artifact each came "
                "from), flagged gaps, and the last stored working theory (if any). "
                "CHEAP read of structured state. Use this to orient yourself on "
                "what's been recorded so far without triggering a synthesis call."
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
    """v0.8 dispatcher: get_current_spec_state + get_checklist_progress +
    synthesize_my_thinking + find_tensions. Self-contained — no v0.6/v0.7."""

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
