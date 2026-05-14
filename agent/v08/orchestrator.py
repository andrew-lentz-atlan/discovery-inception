"""v0.8 orchestrator.

Per turn:
  1. Triage (eager — cheap classification, retry/fallback as before)
  2. Distill (eager, conditional)
  3. Mega-agent (single call with v0.8 tools: get_current_spec_state,
     get_checklist_progress, synthesize_my_thinking, find_tensions)
  4. PROBE-SHARPENER post-processor (NEW in v0.8) — adversarial review
     of the mega-agent's response. If quality_score < 11, the response
     is replaced with the sharpener's rewrite. Otherwise ships as-is.

Three changes from v0.7:
  - V08_SYSTEM_PROMPT bakes in number-provenance discipline (pressure-test
    any numeric claim the customer states) + concrete tool-use triggers
    (when to invoke synth, when to find tensions, when to check progress).
  - find_tensions added as a fourth tool the agent can call when it
    suspects something doesn't fit.
  - probe_sharpener runs as a post-processor on every mega-agent response,
    catching weak probes before they ship to the customer.

Cost: ~2-3 seconds added per turn for the sharpener. Quality lift is what
we're measuring; if the lift isn't real, the cost isn't justified.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from openai import AsyncOpenAI

from agent.orchestrator import (
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
    SharpenerResult,
    TensionsResult,
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
from agent.v08.spec_tools import TOOL_SCHEMAS, make_v08_dispatcher


# ---------------------------------------------------------------------------
# v0.8 system prompt — adds number-provenance + tool-use triggers
# ---------------------------------------------------------------------------

V08_SYSTEM_PROMPT_TEMPLATE = """You are a Forward Deployed Engineer running a discovery interview for a new AI agent. Your job is to PROBE the customer until their spec is concrete enough that a builder could execute without guessing.

You are not a domain expert. You are a consultant. Naive-on-purpose is your default. The questions a senior consultant asks are those that EXTEND the customer's thinking — not just clarify mechanisms or fill checklists.

# What you're building toward
The customer wants to build: {USE_CASE_SEED}

The conversation should draw out, over time, a structured spec covering: desired outcome, success metric, anti-goal, current pain, persona, decision points, escalation rules, risks.

# Sharpness over coverage
A senior FDE doesn't run through a checklist. They ask questions that produce "oh, I hadn't thought about it that way" moments. Three patterns to lean on:

1. **Pressure-test numeric claims.** If the customer states a number — a rate, percentage, count, duration, magnitude — your next probe MUST ask its provenance. *"Is that 30% your median, your worst-case, or what your CFO uses for conservative planning? Who maintains that number? How was it measured?"* Never accept a number at face value the first time you hear it. Numbers without provenance silently corrupt the spec.

2. **Surface tensions between prior statements.** When the customer says something that's in implicit conflict with what they said earlier, name the tension. *"You said AEs see 'next-best action' but never see comparative views — what does 'best' mean if there's no reference point?"* The customer often hasn't noticed the tension themselves.

3. **Extend, don't clarify.** A weak follow-up asks *"where does the agent get the org chart?"* (mechanism). A sharp follow-up asks *"what did the violating view look like in those two HR incidents — was the rule the comparison itself, or the audience the view reached?"* Mechanism follow-ups produce facts; pattern follow-ups produce insight.

# Tools available and when to use them

You have FOUR tools. Use them deliberately. Concrete triggers below:

- **get_current_spec_state()** — Cheap state read. Use when: you need to remember what's been captured; you suspect you might be repeating a topic; you're answering a relevance challenge and need a quick coverage check.

- **get_checklist_progress()** — Cheap state read. Use when: you're deciding breadth vs depth; you want to check whether you're hitting all canonical topics; you've gone 5+ turns without orienting on coverage.

- **synthesize_my_thinking()** — EXPENSIVE (3-5s). Pause to reflect with full theory rebuild. Use when:
    - The customer just gave a content-rich answer (multi-paragraph, case study, dense org structure)
    - The customer contradicted or walked back something
    - You hit a relevance challenge (need to be playback-ready)
    - You've gone 8+ turns without synthesis (memory check)
    - You're about to play the theory back to the customer

- **find_tensions()** — EXPENSIVE (~3-5s). Focused adversarial scan of captured facts. Use when:
    - You suspect two earlier customer statements don't fit together
    - The customer just stated a rule that has a known exception in their prior statements
    - You're about to declare discovery complete and want to surface anything that doesn't add up
    - The customer states a number that conflicts with a number from earlier

**Use the tools more often than feels natural.** A senior FDE mentally checks their understanding multiple times in a 60-minute conversation. Calling a tool is the equivalent. If you've gone 5+ turns without invoking any tool, that's a signal you're operating on stale memory.

# Hard rules from earlier versions (still apply)

- Cover breadth before depth. Don't drill on why's until each canonical topic has at least one fact.
- Mirror the customer's vocabulary. Their terms, not generic SaaS substitutes.
- Treat priors as scaffolding, not gospel.
- When the customer hedges, name the gap rather than papering over.
- When the customer challenges relevance, answer with the rationale tied to their goal; don't dodge.
- One question per turn.
- When the customer says "above my paygrade," acknowledge, flag for FDE follow-up, pivot — don't grind.

# Priors (customer's role context)
{PRIORS}

# Output
Respond to the customer as a good FDE would. Match the natural rhythm of consultative conversation. Trust your judgment about when to play back a theory, when to drill, when to acknowledge and pivot. The structured spec is being built separately by extractors — your job is the conversation. Don't format anything; free-form prose is fine.
"""


def _build_v08_system_prompt(session: DiscoverySession) -> str:
    return V08_SYSTEM_PROMPT_TEMPLATE.format(
        USE_CASE_SEED=session.spec.use_case_seed,
        PRIORS=_relevant_priors(session, None),
    )


# ---------------------------------------------------------------------------
# Sub-agent call wrappers
# ---------------------------------------------------------------------------

async def _run_synthesizer(client: AsyncOpenAI, prompt: str):
    return await call_sub_agent(
        client,
        sub_agent="synthesizer",
        user_prompt=prompt,
        output_model=WorkingTheory,
        max_tokens=1536,
    )


async def _run_tensions(client: AsyncOpenAI, prompt: str):
    return await call_sub_agent(
        client,
        sub_agent="synthesizer",  # reuse synthesizer model slot for now
        user_prompt=prompt,
        output_model=TensionsResult,
        max_tokens=768,
    )


async def _run_probe_sharpener(
    client: AsyncOpenAI,
    *,
    draft_probe: str,
    draft_rationale: str,
    customer_message: str,
    session: DiscoverySession,
) -> SharpenerResult:
    """Run the probe-sharpener sub-agent on a mega-agent response."""
    # Build recent_facts string
    all_facts: list[tuple[str, str, str]] = []
    for topic in session.spec.topics:
        for fact, source in zip(topic.facts, topic.sources):
            all_facts.append((topic.topic, fact, source))
    recent_facts_lines = [
        f"- [{topic_name}, {source}] {fact}"
        for topic_name, fact, source in all_facts[-10:]
    ]
    recent_facts = "\n".join(recent_facts_lines) if recent_facts_lines else "(no facts captured yet)"

    prompt = load_prompt(
        "06_probe_sharpener.md",
        DRAFT_PROBE=draft_probe,
        DRAFT_RATIONALE=draft_rationale,
        CUSTOMER_MESSAGE=customer_message,
        SPEC_STATE_SUMMARY=_spec_state_summary(session),
        USE_CASE_SEED=session.spec.use_case_seed,
        RECENT_FACTS=recent_facts,
    )
    result, _ms, _model = await call_sub_agent(
        client,
        sub_agent="synthesizer",  # reuse synth model slot
        user_prompt=prompt,
        output_model=SharpenerResult,
        max_tokens=768,
    )
    return result


# ---------------------------------------------------------------------------
# Deterministic session-end synthesis (same as v0.7)
# ---------------------------------------------------------------------------

async def run_final_synthesis(
    client: AsyncOpenAI,
    session: DiscoverySession,
) -> WorkingTheory:
    """Run one final synthesizer pass at session close."""
    prior_theory_json = (
        session.spec.working_theory.model_dump_json(indent=2)
        if session.spec.working_theory
        else "(no prior synthesis this session — this final pass is the first)"
    )
    synth_prompt = load_prompt(
        "05_synthesizer.md",
        USE_CASE_SEED=session.spec.use_case_seed,
        SPEC_STATE_SUMMARY=_spec_state_summary(session),
        CUSTOMER_MESSAGE=(
            "(SESSION-CLOSE SYNTHESIS — the discovery conversation is wrapping up. "
            "Produce a final working theory that integrates everything captured so "
            "far. Don't bias toward the most recent turn; survey the whole arc.)"
        ),
        PRIOR_THEORY=prior_theory_json,
        RELEVANT_PRIORS=_relevant_priors(session, None),
    )
    new_theory, _ms, _model = await call_sub_agent(
        client,
        sub_agent="synthesizer",
        user_prompt=synth_prompt,
        output_model=WorkingTheory,
        max_tokens=1536,
    )
    if session.spec.working_theory is not None:
        session.spec.theory_history.append(session.spec.working_theory)
    session.spec.working_theory = new_theory
    session.save()
    return new_theory


# ---------------------------------------------------------------------------
# Per-turn pipeline (v0.8)
# ---------------------------------------------------------------------------

async def run_v08_turn(
    client: AsyncOpenAI,
    session: DiscoverySession,
    mega_session: MegaAgentSession,
    customer_message: str,
) -> tuple[Turn, ChecklistResult]:
    """v0.8 hybrid: triage + distill eager, mega-agent with 4 tools,
    probe-sharpener post-processor on every response."""
    turn = session.start_turn(customer_message)
    session.save()

    last_probe = _last_probe_text(session)
    last_target_topic = _last_probe_target_topic(session)
    topic_summary = _topic_summary(session)

    # ---- Triage (with fallback) ----
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
            reasoning=f"(triage failed; defaulted to concrete: {str(exc)[:200]})",
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

    # ---- Distill ----
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
                    f"Question came up but the current counterparty can't answer; "
                    f"needs escalation to {who}."
                ),
                related_topic=last_distilled.topic,
                gap_type="missing_why",
            )
            session.flag_gap(gap)
            session.save()

    # ---- Phase advance ----
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

    # ---- Mega-agent (v0.8 system prompt + 4 tools) ----
    mega_session.system_prompt = _build_v08_system_prompt(session)
    dispatch = make_v08_dispatcher(
        session=session,
        client=client,
        run_synthesizer_call=lambda c, p: _run_synthesizer(c, p),
        run_tensions_call=lambda c, p: _run_tensions(c, p),
    )

    started = time.perf_counter()
    draft_response, mega_metrics = await mega_session.turn_with_tools(
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
                "draft_response": draft_response,
                "tool_calls": mega_metrics.get("tool_calls", []),
                "input_tokens": mega_metrics.get("input_tokens"),
                "output_tokens": mega_metrics.get("output_tokens"),
            },
            duration_ms=mega_duration_ms,
            model=mega_metrics.get("model"),
        )
    )

    # ---- Probe sharpener post-processor ----
    # Run on most turns where the mega-agent emitted something probe-shaped.
    # Skip for meta acknowledgments (very short responses) and pure
    # relevance-challenge replies that we don't want to second-guess.
    final_response = draft_response
    sharpener_result: SharpenerResult | None = None

    # Heuristic: skip sharpener if the response is very short (likely just
    # an acknowledgment) or if the mega-agent didn't produce a question.
    has_question = "?" in draft_response
    is_substantive = len(draft_response.strip()) > 80

    if has_question and is_substantive:
        sharpen_started = time.perf_counter()
        try:
            sharpener_result = await _run_probe_sharpener(
                client,
                draft_probe=draft_response,
                draft_rationale="(no separate rationale — mega-agent integrates)",
                customer_message=customer_message,
                session=session,
            )
            sharpen_ms = int((time.perf_counter() - sharpen_started) * 1000)

            turn.events.append(
                TurnEvent(
                    sub_agent="probe_sharpener",
                    input_summary=f"reviewing draft (length={len(draft_response)})",
                    output=sharpener_result.model_dump(),
                    duration_ms=sharpen_ms,
                    model="claude-haiku-4-5",
                )
            )

            # Apply the sharpener's rewrite if quality was weak
            if not sharpener_result.ships_as_is and sharpener_result.rewritten_probe:
                final_response = sharpener_result.rewritten_probe
                # Also update the mega-agent's last assistant message in its
                # conversation history so subsequent turns see the rewritten
                # version, not the draft.
                if mega_session.messages and mega_session.messages[-1]["role"] == "assistant":
                    mega_session.messages[-1]["content"] = final_response
        except Exception as exc:
            # Sharpener failure shouldn't break the turn — ship the draft.
            turn.events.append(
                TurnEvent(
                    sub_agent="probe_sharpener",
                    input_summary="sharpener failed",
                    output={"error": str(exc)[:200], "shipped_as_is": True},
                    duration_ms=0,
                    model=None,
                )
            )

    checklist = evaluate_checklist(session.spec)
    session.end_turn(turn, final_response)
    session.save()
    return turn, checklist
