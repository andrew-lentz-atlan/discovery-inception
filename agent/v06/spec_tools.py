"""Spec read-tools — exposed to the mega-agent so it can introspect on
the structured discovery state mid-conversation.

Inversion from v0.5: the mega-agent is in charge of the conversation; the
extractors (triage/distill/synthesizer) run as a SKILL it can lean on,
not as an orchestrator that controls it. These tools are how the model
checks "where am I?" against the running spec.

Three tools intentionally — each one tightly scoped:
- get_current_spec_state()    -> full snapshot
- get_working_theory()        -> the theory only (one_line + framings + open_qs)
- get_checklist_progress()    -> phase + which canonical topics still need facts
"""
from __future__ import annotations

import json
from typing import Any, Callable

from agent.state import (
    BEDROCK_ADVISORY_TOPICS,
    CANONICAL_CHECKLIST_TOPICS,
    DiscoverySession,
    MULTI_INSTANCE_REQUIREMENTS,
    evaluate_checklist,
)


# ---------------------------------------------------------------------------
# Tool implementations — each takes a session, returns a string for the model
# ---------------------------------------------------------------------------

def get_current_spec_state(session: DiscoverySession) -> str:
    """Full snapshot — phase, topics + facts, gaps, theory."""
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
            for f, s in zip(t.facts, t.sources):
                out.append(f"    - [{s}] {f}")
            if t.superseded_facts:
                out.append("    superseded:")
                for f in t.superseded_facts:
                    out.append(f"      ~ {f}")
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


def get_working_theory(session: DiscoverySession) -> str:
    """Theory only — for when the model wants to focus on hypothesis state."""
    wt = session.spec.working_theory
    if wt is None:
        return "(no working theory yet — no concrete answer recorded so far)"
    return wt.model_dump_json(indent=2)


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
# OpenAI tool schemas + dispatcher
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_current_spec_state",
            "description": (
                "Get the full current state of the discovery spec — current phase, "
                "all topics with their recorded facts, flagged gaps, and the working "
                "theory (framing, candidate framings, open questions, disconfirmer). "
                "Use this to orient yourself on what you've learned so far. Especially "
                "useful before deciding whether to drill on a topic or pivot to a "
                "missing one."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_working_theory",
            "description": (
                "Get just the current working theory of what the customer wants built — "
                "the one-line framing, alternative candidate framings, open questions "
                "that would sharpen it, and the sharpest disconfirmer. Use this when "
                "you want to anchor a probe to the theory or play it back."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_checklist_progress",
            "description": (
                "Get the canonical-topic coverage checklist: which canonical topics "
                "(desired_outcome, success_metric, anti_goal, current_pain, persona, "
                "decision_point, escalation_rule, risk) have facts recorded, which "
                "are still missing, and the current phase. Use this to decide breadth "
                "vs depth — if you're in lay_of_the_land and missing 3+ canonical "
                "topics, a breadth probe is the right next move."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def make_dispatcher(session: DiscoverySession) -> Callable[[str, dict], str]:
    """Bind the session into a name->tool dispatcher for one conversation."""
    handlers = {
        "get_current_spec_state": lambda _args: get_current_spec_state(session),
        "get_working_theory": lambda _args: get_working_theory(session),
        "get_checklist_progress": lambda _args: get_checklist_progress(session),
    }

    def dispatch(name: str, args: dict[str, Any]) -> str:
        handler = handlers.get(name)
        if handler is None:
            return f"Error: unknown tool '{name}'."
        try:
            return handler(args)
        except Exception as exc:
            return f"Error executing {name}: {exc}"

    return dispatch
