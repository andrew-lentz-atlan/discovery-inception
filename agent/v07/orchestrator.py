"""v0.7 orchestrator.

Per turn:
  1. Triage (eager — cheap classification)
  2. Distill (eager, conditional — extracts facts)
  3. Mega-agent (single call with tools):
       - get_current_spec_state    cheap state read
       - get_checklist_progress    cheap state read
       - synthesize_my_thinking    EXPENSIVE: invokes synthesizer skill

Two architectural changes from v0.6:
  - Synthesizer is no longer eager — it's a tool the mega-agent calls
    when it wants to reflect. The mega-agent decides when synthesis
    matters. Saves compute on turns where the agent has enough
    conversational context.
  - Mega-agent's prompt no longer constrains output format. The
    mega-agent is in charge of conversation; structure happens in
    extractors. Asking the mega-agent to "output ONE question, no
    preamble" was contamination — bleeding formatting concerns into
    the conversational agent's job.

These changes compose. With lazy synthesis, when the synthesizer DOES
run, it has access to the full conversation history through the spec
state summary AND the customer's latest message — the same context the
mega-agent has been operating on. The information asymmetry between
the synthesizer and the mega-agent (where synthesizer was reasoning
from a strictly-poorer information set) disappears.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from openai import AsyncOpenAI

from agent.orchestrator import (
    call_sub_agent,
    load_prompt,
    _relevant_priors,
    _topic_summary,
    _last_probe_text,
    _last_probe_target_topic,
)
from agent.schemas import (
    ChecklistResult,
    DistilledFact,
    FlaggedGap,
    TriageResult,
    WorkingTheory,
)
from agent.state import (
    DiscoverySession,
    Turn,
    TurnEvent,
    evaluate_checklist,
    should_advance_phase,
)
from agent.baselines.mega_agent import MegaAgentSession
from agent.v07.spec_tools import TOOL_SCHEMAS, make_v07_dispatcher


# ---------------------------------------------------------------------------
# v0.7 system prompt — free-form mega-agent
# ---------------------------------------------------------------------------

V07_SYSTEM_PROMPT_TEMPLATE = """You are a Forward Deployed Engineer running a discovery interview for a new AI agent. Your job is to PROBE the customer until their spec is concrete enough that a builder could execute without guessing.

You are not a domain expert. You are a consultant. Naive-on-purpose is your default.

# What you're building toward
The customer wants to build: {USE_CASE_SEED}

The conversation should draw out, over time, a structured spec covering: desired outcome, success metric, anti-goal, current pain, persona, decision points, escalation rules, risks.

# How to think about your role
Be a good FDE. That means:
- Cover the lay of the land before drilling on any one thing. Don't grind on whys when you haven't yet established what the customer is even trying to build.
- Mirror the customer's vocabulary. Don't invent generic terms for things they've named specifically.
- Treat their priors as scaffolding, not gospel — probe whether what's written matches what actually happens.
- When the customer hedges, name the gap rather than papering over it.
- When the customer pushes back on whether a question is useful, answer with the rationale tied to their actual goal. Don't dodge.
- One question at a time. Multi-part questions get half-answered.

# Tools available
You have access to three tools — use them as a consultant would step back and think.

- **get_current_spec_state()** — Cheap. Reads structured state: phase, topics + facts recorded so far, flagged gaps, last stored working theory. Call this to orient yourself on what's been captured already so you don't repeat or contradict.

- **get_checklist_progress()** — Cheap. Reads which canonical topics still need facts and the current discovery phase. Useful for deciding breadth vs depth.

- **synthesize_my_thinking()** — EXPENSIVE (3-5 seconds). PAUSE TO REFLECT. Runs the synthesizer skill NOW, producing a fresh structured working theory of what the customer wants built (one-line framing, alternative candidate shapes, open questions, sharpest disconfirmer). Call this when you want to step back and think — particularly:
    - The conversation feels stuck or you're not sure what's most load-bearing to ask next
    - You want to play back a theory to the customer ("here's what I'm hearing — does that match?")
    - You've just gotten new information that should update your mental model
    - You're deciding between several plausible next-question options and want a sharper read
  Don't call this on every turn. Use it deliberately, the way a good consultant pauses to synthesize.

# Priors (customer's role context — use this vocabulary)
{PRIORS}

# Output
Respond to the customer however a good FDE would. Match the natural rhythm of consultative conversation — sometimes a sharp single question is right, sometimes a brief acknowledgment and a pivot, sometimes a play-back of what you're hearing. Trust your judgment. The structured spec is being built separately by extractors — your job is the conversation, not the data structure.
"""


def _build_v07_system_prompt(session: DiscoverySession) -> str:
    return V07_SYSTEM_PROMPT_TEMPLATE.format(
        USE_CASE_SEED=session.spec.use_case_seed,
        PRIORS=_relevant_priors(session, None),
    )


# ---------------------------------------------------------------------------
# Synthesizer call wrapper — passed into the lazy tool
# ---------------------------------------------------------------------------

async def _run_synthesizer(
    client: AsyncOpenAI,
    prompt: str,
) -> tuple[WorkingTheory, int, str]:
    """Wrapper that the lazy tool uses to invoke the synthesizer sub-agent."""
    return await call_sub_agent(
        client,
        sub_agent="synthesizer",
        user_prompt=prompt,
        output_model=WorkingTheory,
        max_tokens=1024,
    )


async def _run_synthesizer_for_tool(client: AsyncOpenAI, prompt: str):
    """Adapter matching the signature spec_tools expects: (client, prompt)."""
    return await _run_synthesizer(client, prompt)


# ---------------------------------------------------------------------------
# Per-turn pipeline
# ---------------------------------------------------------------------------

async def run_v07_turn(
    client: AsyncOpenAI,
    session: DiscoverySession,
    mega_session: MegaAgentSession,
    customer_message: str,
) -> tuple[Turn, ChecklistResult]:
    """v0.7 hybrid: triage + distill eager, synthesizer lazy via tool,
    mega-agent free-form."""
    turn = session.start_turn(customer_message)
    session.save()

    last_probe = _last_probe_text(session)
    last_target_topic = _last_probe_target_topic(session)
    topic_summary = _topic_summary(session)

    # ---- Eager extractor 1: Triage ----
    triage_prompt = load_prompt(
        "01_triage.md",
        LAST_PROBE=last_probe,
        CUSTOMER_MESSAGE=customer_message,
        TOPIC_SUMMARY=topic_summary,
    )
    triage, ms, model = await call_sub_agent(
        client,
        sub_agent="triage",
        user_prompt=triage_prompt,
        output_model=TriageResult,
        max_tokens=512,
    )
    turn.events.append(
        TurnEvent(
            sub_agent="triage",
            input_summary=f"customer_msg={customer_message[:80]!r}",
            output=triage.model_dump(),
            duration_ms=ms,
            model=model,
        )
    )
    session.save()

    # ---- Eager extractor 2: Distill (conditional) ----
    distill_routes = ("concrete", "concrete_off_topic", "out_of_scope_for_counterparty")
    last_distilled: DistilledFact | None = None
    if triage.label in distill_routes:
        if triage.label == "concrete_off_topic":
            target_topic = triage.inferred_topic or "(unspecified)"
        elif triage.label == "out_of_scope_for_counterparty":
            target_topic = triage.inferred_topic or last_target_topic or "(unspecified)"
        else:
            target_topic = last_target_topic or "(inferred)"

        distill_prompt = load_prompt(
            "02_distill.md",
            LAST_PROBE=last_probe,
            TARGET_TOPIC=target_topic,
            CUSTOMER_MESSAGE=customer_message,
            RELEVANT_PRIORS=_relevant_priors(session, target_topic),
        )
        last_distilled, ms, model = await call_sub_agent(
            client,
            sub_agent="distill",
            user_prompt=distill_prompt,
            output_model=DistilledFact,
            max_tokens=512,
        )
        turn.events.append(
            TurnEvent(
                sub_agent="distill",
                input_summary=f"distilling on target_topic={target_topic!r}",
                output=last_distilled.model_dump(),
                duration_ms=ms,
                model=model,
            )
        )
        session.record_fact(last_distilled)
        session.save()

        if triage.label == "out_of_scope_for_counterparty":
            who = triage.escalation_target or "the right counterparty"
            gap = FlaggedGap(
                question=f"{last_probe} (rationale required at the {who} level)",
                why_it_matters=(
                    f"This question came up but the current counterparty "
                    f"can't answer it; needs escalation to {who}."
                ),
                related_topic=last_distilled.topic,
                gap_type="missing_why",
            )
            session.flag_gap(gap)
            session.save()

    # ---- NO eager synthesizer call — it's lazy now ----

    # ---- Phase advance check ----
    if should_advance_phase(session.spec):
        session.spec.phase = "drilling"
        session.save()
        turn.events.append(
            TurnEvent(
                sub_agent="phase_advance",
                input_summary="lay_of_the_land threshold met",
                output={"new_phase": "drilling"},
                duration_ms=0,
                model=None,
            )
        )

    # ---- Mega-agent call (with lazy synthesizer tool) ----
    mega_session.system_prompt = _build_v07_system_prompt(session)

    dispatch = make_v07_dispatcher(
        session=session,
        client=client,
        run_synthesizer_call=lambda client, prompt: _run_synthesizer_for_tool(client, prompt),
    )

    started = time.perf_counter()
    agent_response, mega_metrics = await mega_session.turn_with_tools(
        client,
        customer_message,
        tool_schemas=TOOL_SCHEMAS,
        tool_dispatch=dispatch,
    )
    mega_duration_ms = int((time.perf_counter() - started) * 1000)

    turn.events.append(
        TurnEvent(
            sub_agent="mega_agent",
            input_summary=(
                f"completion_calls={mega_metrics.get('n_completion_calls')}, "
                f"tool_calls={[tc['name'] for tc in mega_metrics.get('tool_calls', [])]}"
            ),
            output={
                "final_response": agent_response,
                "tool_calls": mega_metrics.get("tool_calls", []),
                "input_tokens": mega_metrics.get("input_tokens"),
                "output_tokens": mega_metrics.get("output_tokens"),
            },
            duration_ms=mega_duration_ms,
            model=mega_metrics.get("model"),
        )
    )

    checklist = evaluate_checklist(session.spec)
    session.end_turn(turn, agent_response)
    session.save()
    return turn, checklist
