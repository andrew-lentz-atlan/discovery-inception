"""v0.6 hybrid orchestrator.

Per turn:
  1. Extractors run (triage -> distill -> synthesizer) — same decomposed
     sub-agents we built in v0.5, repurposed as a structured-output skill.
     They update the DiscoverySession in place.
  2. Mega-agent runs the conversation as a SINGLE call with tools. The
     model can call get_current_spec_state / get_working_theory /
     get_checklist_progress to orient on its structured progress, then
     emits the response.

Inversion from v0.5: the mega-agent is in charge of the conversation;
extractors run as a skill underneath, not as an orchestrator above.

This trades the strawman/relevance-challenge short-circuits for the
mega-agent's conversational fluency. It keeps decomposition where it
empirically wins (structured spec output) and uses a single strong
prompt where it empirically wins (conversation quality).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from agent.orchestrator import (
    SUB_AGENT_MODELS,
    call_sub_agent,
    load_prompt,
    _relevant_priors,
    _topic_summary,
    _spec_state_summary,
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
from agent.v06.spec_tools import TOOL_SCHEMAS, make_dispatcher


# ---------------------------------------------------------------------------
# v0.6 system prompt — mega-agent + spec read-tools
# ---------------------------------------------------------------------------

V06_SYSTEM_PROMPT_TEMPLATE = """You are an FDE (Forward Deployed Engineer) running a discovery interview for a new AI agent. Your job is to PROBE the customer until their spec is concrete enough that a builder could execute without guessing.

You are not a domain expert. You are a consultant. Naive-on-purpose is your default.

# What you're building toward
The customer wants to build: {USE_CASE_SEED}

You need to draw out a structured spec covering: desired_outcome, success_metric, anti_goal, current_pain, persona, decision_point, escalation_rule, risk.

# Tools you have available
You have access to three read-tools that introspect on the structured discovery state being built behind the scenes. Use them deliberately — especially before deciding what to ask next, when you suspect you've covered something already, or when you want to play the working theory back to the customer.

- **get_current_spec_state()** — full snapshot of phase, topics, facts, gaps, working theory. Use to orient before asking a probe.
- **get_working_theory()** — just the working theory (framing, alternatives, open questions, disconfirmer). Use when you want to pressure-test the theory or play it back.
- **get_checklist_progress()** — phase + which canonical topics still need facts. Use to decide breadth vs depth.

Call them freely. They're free for you and they keep your conversation grounded in what's actually been recorded versus what you remember.

# Two-phase discovery
Phase 1 (lay_of_the_land): cover one fact on each canonical topic FIRST. Do not drill on a single topic until each canonical topic has at least one fact. Drilling early feels contrarian and destroys trust.

Phase 2 (drilling): only AFTER breadth is established, start asking "why" questions to reach bedrock.

If you're uncertain which phase you're in or what you've covered, call `get_checklist_progress()`.

# Working theory
The synthesizer is updating a working theory of what the customer wants built after every customer answer. Read it via `get_working_theory()`. Anchor your probes to the theory: confirm it, disconfirm it, or sharpen one of its open questions. NOT just "fill the next checklist gap."

When the theory is sharp enough (medium+ confidence) AND you haven't yet played it back, STOP probing for one turn and play it back: "Here's what I'm hearing — does that match, or am I missing something?" That's the move that produces high-signal "no, actually..." reactions.

# Every question must justify itself
Before asking, you must be able to answer: "Why does answering this matter for what the customer is trying to build?" — phrased in the customer's own goal terms.

When the customer challenges relevance ("how is this relevant?", "you just keep asking why"), STOP and answer with the rationale in customer-facing terms. If they challenge a SECOND time on the same line, abandon it explicitly ("Got it — moving on. Different question:") and pick a different angle.

# Customer vocabulary
Use the customer's exact terms. The priors below contain the vocabulary you should expect. If they say "S1-S4 sales cycle" do not invent "ops team."

# Style rules
- ONE question per turn. Multi-part questions get half-answered.
- Reject hedge words ("kind of," "maybe," "potentially") in your own questions.
- Time-bound where possible.
- Concrete examples beat abstractions.
- When the customer says "above my paygrade" / "leadership decided" / "I don't have visibility," don't grind — acknowledge, note the gap for FDE follow-up, pivot.
- When the customer gives a long structured answer that doesn't directly answer your probe, acknowledge the off-topic content, then either pursue the new thread or loop back.

# Priors (the customer's role context)
{PRIORS}

# Output format
For each turn, output ONE final question for the customer. No prose preamble, no explanation of your reasoning. Just the question, exactly as you'd say it. ONE question, one or two short sentences. Tool calls do NOT count as your final output — keep calling tools until you're ready to ask the customer something, then emit only that question.
"""


def _build_v06_system_prompt(session: DiscoverySession) -> str:
    return V06_SYSTEM_PROMPT_TEMPLATE.format(
        USE_CASE_SEED=session.spec.use_case_seed,
        PRIORS=_relevant_priors(session, None),
    )


# ---------------------------------------------------------------------------
# Per-turn pipeline
# ---------------------------------------------------------------------------

async def run_v06_turn(
    client: AsyncOpenAI,
    session: DiscoverySession,
    mega_session: MegaAgentSession,
    customer_message: str,
) -> tuple[Turn, ChecklistResult]:
    """v0.6 hybrid: extractors run first, then mega-agent with tools.

    Mutates `session` (extractor outputs) and `mega_session` (conversation
    history). Both are tied to the same logical session — the mega-agent
    sees the conversation, the session holds the structured spec.
    """
    turn = session.start_turn(customer_message)
    session.save()

    last_probe = _last_probe_text(session)
    last_target_topic = _last_probe_target_topic(session)
    topic_summary = _topic_summary(session)

    # ---- Extractor 1: Triage ----
    triage_prompt = load_prompt(
        "01_triage.md",
        LAST_PROBE=last_probe,
        CUSTOMER_MESSAGE=customer_message,
        TOPIC_SUMMARY=topic_summary,
    )
    try:
        triage, ms, model = await call_sub_agent(
            client,
            sub_agent="triage",
            user_prompt=triage_prompt,
            output_model=TriageResult,
            max_tokens=512,
        )
    except Exception as exc:
        triage = TriageResult(
            label="concrete",
            reasoning=f"(triage call failed after retries — defaulted to 'concrete'; error: {str(exc)[:200]})",
            contradicted_topic=None,
            inferred_topic=None,
            escalation_target=None,
        )
        ms, model = 0, "fallback"
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

    # ---- Extractor 2: Distill (only if there's a fact to extract) ----
    last_distilled: DistilledFact | None = None
    distill_routes = ("concrete", "concrete_off_topic", "out_of_scope_for_counterparty")
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

        # Auto-flag gap if customer hit a knowledge boundary
        if triage.label == "out_of_scope_for_counterparty":
            who = triage.escalation_target or "the right counterparty"
            gap = FlaggedGap(
                question=(
                    f"{last_probe} (rationale required at the {who} level)"
                ),
                why_it_matters=(
                    f"This question came up but the current counterparty "
                    f"can't answer it; needs escalation to {who}."
                ),
                related_topic=last_distilled.topic,
                gap_type="missing_why",
            )
            session.flag_gap(gap)
            session.save()

    # ---- Extractor 3: Synthesizer (always runs after a fact lands) ----
    if last_distilled is not None:
        prior_theory_json = (
            session.spec.working_theory.model_dump_json(indent=2)
            if session.spec.working_theory
            else "(no prior theory yet — this is the first synthesis)"
        )
        synth_prompt = load_prompt(
            "05_synthesizer.md",
            USE_CASE_SEED=session.spec.use_case_seed,
            SPEC_STATE_SUMMARY=_spec_state_summary(session),
            CUSTOMER_MESSAGE=customer_message,
            PRIOR_THEORY=prior_theory_json,
            RELEVANT_PRIORS=_relevant_priors(session, None),
        )
        new_theory, ms, model = await call_sub_agent(
            client,
            sub_agent="synthesizer",
            user_prompt=synth_prompt,
            output_model=WorkingTheory,
            max_tokens=1024,
        )
        turn.events.append(
            TurnEvent(
                sub_agent="synthesizer",
                input_summary=f"updating theory after fact on {last_distilled.topic}",
                output=new_theory.model_dump(),
                duration_ms=ms,
                model=model,
            )
        )
        if session.spec.working_theory is not None:
            session.spec.theory_history.append(session.spec.working_theory)
        session.spec.working_theory = new_theory
        session.save()

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

    # ---- Mega-agent conversational call (with tools) ----
    # Sync the mega-agent's system prompt with the current priors-aware shape.
    # (Done once per turn; cheap.)
    mega_session.system_prompt = _build_v06_system_prompt(session)
    dispatch = make_dispatcher(session)

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
