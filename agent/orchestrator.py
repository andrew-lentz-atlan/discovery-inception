"""Orchestrator — runs the per-turn pipeline.

Two-phase design (v0.5):

  Phase 1 — lay_of_the_land:
      triage → (if concrete: distill) → probe_generator (breadth-first)
      Why-prober is OFF. Goal: cover canonical topics with at least one fact
      each before drilling. Trust the customer; don't immediately challenge.

  Phase 2 — drilling:
      triage → (if concrete: distill → why_prober) → probe_generator
      Why-prober is ON. Goal: target bedrock on the highest-value topics.
      Phase advances automatically once ~5 of 8 canonical topics have a fact.

This is sequential decomposed LLM calls — same architectural shape as the
intake pipeline, just stateful and conversational. NO orchestration framework
on purpose. The orchestrator is dumb code; each sub-agent is one tightly-
scoped prompt with one Pydantic output type.

Stop-condition checking is deterministic Python, not an LLM call.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel

from agent.schemas import (
    ChecklistResult,
    DistilledFact,
    FlaggedGap,
    Probe,
    TriageResult,
    WhyProbeResult,
    WorkingTheory,
)
from agent.state import (
    CANONICAL_CHECKLIST_TOPICS,
    DiscoverySession,
    Turn,
    TurnEvent,
    evaluate_checklist,
    should_advance_phase,
)

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# Model selection per sub-agent. Cheap-cascade applied internally:
# triage and why-prober are tight classifications; probe_generator does the
# heavy lifting and could benefit from a stronger model later. v0: same
# model everywhere for simplicity. Per-step override via env var.
DEFAULT_MODEL = os.environ.get("DISCOVERY_AGENT_MODEL", "claude-haiku-4-5")
SUB_AGENT_MODELS = {
    "triage": os.environ.get("DISCOVERY_TRIAGE_MODEL", DEFAULT_MODEL),
    "distill": os.environ.get("DISCOVERY_DISTILL_MODEL", DEFAULT_MODEL),
    "why_prober": os.environ.get("DISCOVERY_WHY_PROBER_MODEL", DEFAULT_MODEL),
    "synthesizer": os.environ.get("DISCOVERY_SYNTHESIZER_MODEL", DEFAULT_MODEL),
    "probe_generator": os.environ.get("DISCOVERY_PROBE_MODEL", DEFAULT_MODEL),
}


# ---------------------------------------------------------------------------
# LLM call helper (mirrors intake/run.py shape)
# ---------------------------------------------------------------------------

def load_prompt(name: str, **substitutions: str) -> str:
    text = (PROMPTS_DIR / name).read_text()
    for key, value in substitutions.items():
        text = text.replace("{" + key + "}", value)
    return text


def parse_json_response(content: str) -> dict | list:
    s = (content or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
    return json.loads(s)


async def _call_sub_agent_once(
    client: AsyncOpenAI,
    *,
    sub_agent: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
) -> tuple[str, str, int]:
    """One raw LLM call. Returns (raw_text, model, duration_ms).

    The JSON-output instruction is bundled into the user prompt (not split
    into a system prompt) because LiteLLM-via-Bedrock-Claude occasionally
    ignores the user content when the system prompt is short and
    instructional — the model interprets the system prompt as the "real"
    instruction and responds with stock "please provide inputs" prose
    instead of classifying the user message. Single user prompt avoids
    the ambiguity.
    """
    model = SUB_AGENT_MODELS[sub_agent]
    full_prompt = (
        f"{user_prompt}\n\n"
        f"---\n"
        f"Output ONLY a valid JSON object matching the schema above. "
        f"Begin your response with `{{` and end with `}}`. "
        f"No prose, no markdown fences, no preamble, no commentary — JSON only."
    )
    started = time.perf_counter()
    response = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[
            {"role": "user", "content": full_prompt},
        ],
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    raw = response.choices[0].message.content or ""
    return raw, model, duration_ms


async def call_sub_agent(
    client: AsyncOpenAI,
    *,
    sub_agent: str,
    user_prompt: str,
    output_model: type[BaseModel],
    max_tokens: int = 2048,
    temperature: float = 0.0,
    max_retries: int = 3,
) -> tuple[BaseModel, int, str]:
    """One LLM call → validated Pydantic instance. Returns (result, ms, model).

    Retries on transient response failures up to `max_retries` times.

    Known failure modes worth retrying on:
      - Empty response from the proxy
      - Model returns prose like "I'm ready to triage. Please provide..."
        instead of the JSON the prompt asked for. This happens occasionally
        with LiteLLM-via-Bedrock-Claude — the proxy or model ignores the
        user message under some conditions. Always recovers on retry.
      - Malformed JSON

    Aggregates duration_ms across retries so the metrics reflect the
    actual wall-time cost.
    """
    import asyncio
    last_error: Exception | None = None
    total_duration_ms = 0
    model = SUB_AGENT_MODELS[sub_agent]

    for attempt in range(max_retries + 1):
        if attempt > 0:
            # Brief backoff before retry — gives the proxy time to recover
            # from transient issues and reduces concurrent-call pressure.
            await asyncio.sleep(0.75 * attempt)
        raw, model, duration_ms = await _call_sub_agent_once(
            client,
            sub_agent=sub_agent,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        total_duration_ms += duration_ms

        if not raw.strip():
            last_error = ValueError(f"{sub_agent}: empty response on attempt {attempt+1}")
            continue
        try:
            data = parse_json_response(raw)
        except json.JSONDecodeError as exc:
            last_error = ValueError(
                f"{sub_agent}: could not parse JSON on attempt {attempt+1} — "
                f"{exc}\nRaw (first 400 chars): {raw[:400]}"
            )
            continue
        try:
            result = output_model.model_validate(data)
            # Success path — return below for clean indentation
            return result, total_duration_ms, model
        except Exception as exc:
            last_error = ValueError(
                f"{sub_agent}: parsed JSON but validation failed on attempt {attempt+1} — "
                f"{exc}\nParsed: {json.dumps(data, indent=2)[:400]}"
            )
            continue

    # Exhausted retries — raise the last error we hit
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"{sub_agent}: unreachable — exhausted retries with no error captured")


# ---------------------------------------------------------------------------
# Helpers for prompt context
# ---------------------------------------------------------------------------

def _topic_summary(session: DiscoverySession) -> str:
    if not session.spec.topics:
        return "(no topics yet)"
    lines = []
    for t in session.spec.topics:
        bedrock = " [BEDROCK]" if t.bedrock_reached else ""
        pending = f" [pending:{len(t.pending_questions)}]" if t.pending_questions else ""
        lines.append(f"- {t.topic} ({len(t.facts)} fact(s)){bedrock}{pending}")
    return "\n".join(lines)


def _spec_state_summary(session: DiscoverySession) -> str:
    parts = [f"Phase: {session.spec.phase}", _topic_summary(session)]
    if session.spec.gaps:
        parts.append("\nFlagged gaps (for downstream FDE):")
        for g in session.spec.gaps:
            parts.append(f"- {g.question} (why: {g.why_it_matters})")
    return "\n".join(parts)


def _last_probe_text(session: DiscoverySession) -> str:
    for m in reversed(session.messages[:-1]):  # exclude the customer turn we just added
        if m.role == "agent":
            return m.content
    return "(this is the first turn — no prior probe)"


def _last_probe_target_topic(session: DiscoverySession) -> str | None:
    """Look up the target_topic from the most recent probe-generator output.

    Used to thread target_topic from probe → distill so the next answer gets
    classified under the topic the agent was actually asking about.
    """
    for turn in reversed(session.turns[:-1]):
        for event in reversed(turn.events):
            if event.sub_agent == "probe_generator":
                return event.output.get("target_topic") or None
    return None


def _previous_turn_was_relevance_challenge(session: DiscoverySession) -> bool:
    if len(session.turns) < 2:
        return False
    prev = session.turns[-2]
    for event in prev.events:
        if event.sub_agent == "triage":
            return event.output.get("label") == "relevance_challenge"
    return False


def _last_probe_customer_rationale(session: DiscoverySession) -> str | None:
    """Find the most recent probe-generator output and return its
    customer_facing_rationale. None if no prior probe or legacy probe.

    DO NOT fall back to the internal `rationale` field — it's pipeline
    language often referring to the user in third person, and surfacing it
    verbatim reads like talking about them behind their back.
    """
    for turn in reversed(session.turns[:-1]):
        for event in reversed(turn.events):
            if event.sub_agent == "probe_generator":
                rationale = event.output.get("customer_facing_rationale")
                if rationale:
                    return rationale
                return None
    return None


# ---------------------------------------------------------------------------
# Priors loader — wires RoleContext into the agent's working context
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = PROJECT_ROOT / "skills"


def _load_role_context(role_id: str | None) -> dict | None:
    """Load the RoleContext skill's context.json, or None if not configured."""
    if not role_id:
        return None
    path = SKILLS_DIR / role_id / "context.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _relevant_priors(session: DiscoverySession, topic_hint: str | None) -> str:
    """Render priors slices relevant to the current turn.

    v0.5 strategy: load the RoleContext and surface the parts most likely to
    be load-bearing for the agent's vocabulary and probing. Specifically:
      - role_summary (always, brief)
      - domain_vocabulary (always — drives vocabulary mirroring)
      - unwritten_rules (always — what experienced practitioners do)
      - flagged_unknowns (always — gaps the customer has likely already named)

    We keep this compact so every prompt doesn't pay for the full RoleContext.
    Topic-by-topic filtering is a v1 refinement.
    """
    rc = _load_role_context(session.spec.role_id)
    if rc is None:
        return "(no priors configured for this session)"
    parts: list[str] = []
    summary = rc.get("role_summary")
    if summary:
        parts.append(f"Role summary: {summary}")

    vocab = rc.get("domain_vocabulary") or {}
    if vocab:
        parts.append("\nDomain vocabulary (use the customer's terms when probing):")
        for term, definition in list(vocab.items())[:20]:
            parts.append(f"- {term}: {definition}")

    rules = rc.get("unwritten_rules") or []
    if rules:
        parts.append("\nUnwritten rules from priors (what the role actually does):")
        for r in rules[:8]:
            parts.append(f"- {r}")

    gaps = rc.get("flagged_unknowns") or []
    if gaps:
        parts.append("\nGaps the priors already flagged (don't re-ask the customer for things the priors flag — probe deeper):")
        for g in gaps[:6]:
            q = g.get("field") or g.get("probe_suggestion") or ""
            why = g.get("why_it_matters") or ""
            parts.append(f"- {q} — {why}")

    return "\n".join(parts) if parts else "(priors loaded but empty)"


# ---------------------------------------------------------------------------
# The per-turn pipeline
# ---------------------------------------------------------------------------

async def run_turn(
    client: AsyncOpenAI,
    session: DiscoverySession,
    customer_message: str,
) -> tuple[Turn, ChecklistResult]:
    """Execute one customer-turn → agent-turn round trip.

    Mutates the session and persists it on every event. Returns the turn
    envelope and the deterministic checklist result.
    """
    turn = session.start_turn(customer_message)
    session.save()

    last_probe = _last_probe_text(session)
    last_target_topic = _last_probe_target_topic(session)
    topic_summary = _topic_summary(session)

    # ---- Step 1: Triage ----
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

    # ---- Short-circuit: relevance_challenge ----
    if triage.label == "relevance_challenge":
        is_consecutive = _previous_turn_was_relevance_challenge(session)

        if not is_consecutive:
            last_rationale = _last_probe_customer_rationale(session)
            if last_rationale:
                response = (
                    f"Fair pushback. Here's why I asked: {last_rationale} "
                    f"If that doesn't hold up for what you're trying to build, "
                    f"tell me and I'll drop the line and pick a different angle."
                )
            else:
                response = (
                    "Fair pushback. I can't articulate clean reasoning for "
                    "that question, which means it probably wasn't earning "
                    "its place. Let me skip it — what's the part of the "
                    "agent's behavior you most want to nail down first?"
                )
            session.end_turn(turn, response)
            session.save()
            return turn, evaluate_checklist(session.spec)

        # Consecutive challenge → abandon and pivot via probe-generator hint.
        rejected_question = last_probe
        pivot_hint = (
            f"(LINE ABANDONED) The customer rejected this prior probe as irrelevant "
            f"after I tried to explain it: \"{rejected_question[:200]}\" "
            f"Pick a fundamentally different angle from a different missing checklist "
            f"item — do NOT re-ask in the same neighborhood. Open the new probe with "
            f"explicit acknowledgment that you're moving on (e.g., 'Got it — moving "
            f"on. Different question:'). Choose a topic not adjacent to the rejected one."
        )
    else:
        pivot_hint = ""

    # ---- Step 2 (conditional): Distill, then Why-prober (phase 2 only) ----
    last_distilled: DistilledFact | None = None
    why_result: WhyProbeResult | None = None

    distill_routes = ("concrete", "concrete_off_topic", "out_of_scope_for_counterparty")
    if triage.label in distill_routes:
        # Pick target topic to hint to distill:
        #  - concrete_off_topic: triage's inferred_topic
        #  - out_of_scope_for_counterparty: triage's inferred_topic if set, else last probe's
        #  - concrete: the last probe's target_topic (so distill stays on track)
        if triage.label == "concrete_off_topic":
            target_topic = triage.inferred_topic or "(unspecified)"
        elif triage.label == "out_of_scope_for_counterparty":
            target_topic = triage.inferred_topic or last_target_topic or "(unspecified)"
        else:
            target_topic = last_target_topic or "(inferred)"

        relevant_priors = _relevant_priors(session, target_topic)

        distill_prompt = load_prompt(
            "02_distill.md",
            LAST_PROBE=last_probe,
            TARGET_TOPIC=target_topic,
            CUSTOMER_MESSAGE=customer_message,
            RELEVANT_PRIORS=relevant_priors,
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

        # ---- Auto-flag gap if customer hit a knowledge boundary ----
        if triage.label == "out_of_scope_for_counterparty":
            who = triage.escalation_target or "the right counterparty"
            gap = FlaggedGap(
                question=(
                    f"{last_probe} (rationale required at the {who} level — this "
                    f"counterparty doesn't have visibility)"
                ),
                why_it_matters=(
                    "This question came up in discovery but the current "
                    "counterparty cannot answer it; an FDE will need to "
                    f"escalate to {who} to close the loop."
                ),
                related_topic=last_distilled.topic if last_distilled else last_target_topic,
                gap_type="missing_why",
            )
            session.flag_gap(gap)
            session.save()

        # ---- Synthesizer — runs in BOTH phases after a fact lands ----
        # Produces a WorkingTheory that the probe-generator anchors to.
        # Without this layer, probes are topic-anchored (checklist-filling)
        # not theory-anchored (consultative). The Synthesizer is what makes
        # the difference between playbook discovery and real FDE work.
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
        # Snapshot the prior theory before overwriting
        if session.spec.working_theory is not None:
            session.spec.theory_history.append(session.spec.working_theory)
        session.spec.working_theory = new_theory
        session.save()

        # ---- Why-prober — only in phase 2 ----
        # Phase 1 is breadth-first; we don't drill. Skip the call entirely.
        # Phase 2 is drilling; run the why-prober on the topic we just landed.
        if session.spec.phase == "drilling":
            entry = session.find_topic(last_distilled.topic)
            if (
                entry is not None
                and not entry.bedrock_reached
                and triage.label != "out_of_scope_for_counterparty"
            ):
                why_prompt = load_prompt(
                    "03_why_prober.md",
                    TOPIC=last_distilled.topic,
                    LATEST_FACT=last_distilled.content,
                    WHY_CHAIN_SO_FAR=json.dumps(entry.why_chain),
                )
                why_result, ms, model = await call_sub_agent(
                    client,
                    sub_agent="why_prober",
                    user_prompt=why_prompt,
                    output_model=WhyProbeResult,
                    max_tokens=1024,
                )
                turn.events.append(
                    TurnEvent(
                        sub_agent="why_prober",
                        input_summary=f"probing topic={last_distilled.topic} (phase=drilling)",
                        output=why_result.model_dump(),
                        duration_ms=ms,
                        model=model,
                    )
                )
                if why_result.bedrock_reached:
                    session.declare_bedrock(last_distilled.topic, why_result)
                session.save()

    # ---- Step 3: Phase advance (after fact recording, before probe gen) ----
    if should_advance_phase(session.spec):
        session.spec.phase = "drilling"
        session.save()
        # Surface a phase-advance event in the trace for visibility.
        turn.events.append(
            TurnEvent(
                sub_agent="phase_advance",
                input_summary="lay_of_the_land threshold met",
                output={"new_phase": "drilling"},
                duration_ms=0,
                model=None,
            )
        )

    # ---- Step 4: Stop-condition checklist (deterministic) ----
    checklist = evaluate_checklist(session.spec)

    # ---- Strawman moment ----
    # First time we have a non-trivial theory (one_line_framing isn't the
    # explicit "too early" marker AND confidence > low), present the theory
    # to the customer for confirmation/disconfirmation rather than asking
    # another probe. High-signal "no, actually..." reactions come from this.
    if (
        not session.spec.strawman_shown
        and session.spec.working_theory is not None
        and "(too early" not in session.spec.working_theory.one_line_framing.lower()
        and session.spec.working_theory.confidence in ("medium", "high")
    ):
        theory = session.spec.working_theory
        framing_lines = [
            f"Here's what I'm hearing — let me play it back so you can tell me if I'm reading the shape right:",
            f"",
            f"**Working theory:** {theory.one_line_framing}",
        ]
        if theory.candidate_framings:
            framing_lines.append("")
            framing_lines.append("Other shapes this could be (less likely from what you've said):")
            for f in theory.candidate_framings[:3]:
                framing_lines.append(f"- {f}")
        framing_lines.append("")
        framing_lines.append(
            "Does that match what you're trying to build, or am I missing something? "
            "If part of that is wrong, the wrong part is the most useful thing you can tell me."
        )
        response = "\n".join(framing_lines)
        session.spec.strawman_shown = True
        turn.events.append(
            TurnEvent(
                sub_agent="strawman",
                input_summary=(
                    f"first non-trivial theory at confidence={theory.confidence}"
                ),
                output={"surfaced_theory": theory.one_line_framing},
                duration_ms=0,
                model=None,
            )
        )
        session.end_turn(turn, response)
        session.save()
        return turn, checklist

    # ---- Step 5: Probe generator ----
    why_prober_slot = (
        pivot_hint
        if pivot_hint
        else (json.dumps(why_result.model_dump(), indent=2) if why_result else "(none)")
    )
    working_theory_slot = (
        session.spec.working_theory.model_dump_json(indent=2)
        if session.spec.working_theory is not None
        else "(no theory yet — first turn or no concrete answer recorded)"
    )
    probe_prompt = load_prompt(
        "04_probe_generator.md",
        TRIAGE_LABEL=triage.label,
        PHASE=session.spec.phase,
        CUSTOMER_MESSAGE=customer_message,
        USE_CASE_SEED=session.spec.use_case_seed,
        SPEC_STATE_SUMMARY=_spec_state_summary(session),
        CHECKLIST_MISSING=json.dumps(checklist.missing, indent=2),
        WHY_PROBER_OUTPUT=why_prober_slot,
        WORKING_THEORY=working_theory_slot,
        RELEVANT_PRIORS=_relevant_priors(session, None),
    )
    probe, ms, model = await call_sub_agent(
        client,
        sub_agent="probe_generator",
        user_prompt=probe_prompt,
        output_model=Probe,
        max_tokens=768,
    )
    turn.events.append(
        TurnEvent(
            sub_agent="probe_generator",
            input_summary=f"phase={session.spec.phase} checklist_missing={len(checklist.missing)}",
            output=probe.model_dump(),
            duration_ms=ms,
            model=model,
        )
    )

    session.end_turn(turn, probe.question)
    session.save()
    return turn, checklist
