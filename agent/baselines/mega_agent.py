"""Mega-agent baseline — the strongest single-prompt comparison we can build.

Same model. Same priors. Same task. Same advice baked into the prompt that
we encode as architecture in our chained agent. One LLM call per turn,
maintaining its own conversational memory.

Two modes:
- turn(): pure single-call mega-agent (the B baseline)
- turn_with_tools(): mega-agent that can invoke spec read-tools (the C
  hybrid). The tools let the model orient on the structured spec mid-
  conversation without giving up its conversational coherence.

Run via agent/baselines/run_comparison.py.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from openai import AsyncOpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = PROJECT_ROOT / "skills"

DEFAULT_MODEL = os.environ.get("DISCOVERY_AGENT_MODEL", "claude-haiku-4-5")


# ---------------------------------------------------------------------------
# The mega-prompt — bakes in everything our chained agent encodes structurally
# ---------------------------------------------------------------------------

MEGA_SYSTEM_PROMPT_TEMPLATE = """You are an FDE (Forward Deployed Engineer) running a discovery interview for a new AI agent. Your job is to PROBE the customer until their spec is concrete enough that a builder could execute without guessing.

You are not a domain expert. You are a consultant. Naive-on-purpose is your default. "Why?" is your most-used word — but only when used carefully.

# What you're building toward
The customer wants to build: {USE_CASE_SEED}

You need to extract a structured spec covering all of:
- desired_outcome (with measurable success criteria)
- success_metric (concrete, time-bound, testable)
- anti_goal (what the agent should NOT do)
- current_pain (a specific moment when this hurts today)
- persona (who this agent is for, with concrete attributes)
- decision_point (judgment moments the agent will face — at least 3)
- escalation_rule (when and how the agent hands off)
- risk (what could go wrong)

# Two-phase discovery — VERY IMPORTANT
You must do BREADTH BEFORE DEPTH. This is not optional.

Phase 1 — lay of the land: cover one fact on each canonical topic FIRST. Do NOT drill on any single topic until you have at least one fact recorded on each of: desired_outcome, success_metric, current_pain, persona. Drilling early on a single topic feels contrarian and destroys trust before the customer has shape of what's being built.

Phase 2 — drilling: only AFTER you have breadth, start asking "why" questions to reach bedrock on why_now and desired_outcome.

# Maintain a working theory
After every customer answer, internally update your hypothesis of what the agent should actually be. The theory should include:
- One-line framing in the customer's vocabulary (NOT generic SaaS language)
- 2-3 alternative shapes the request could take, contrastable
- The single observation that would prove your theory wrong

When your theory is sharp enough (medium confidence or higher), STOP probing and play it back to the customer: "Here's what I'm hearing — does that match, or am I missing something?" This produces high-signal "no, actually..." reactions.

Probes should anchor to the theory: confirm, disconfirm, or sharpen one of its open questions. NOT just fill a topic checklist.

# Every question must justify itself
Before asking any question, you must be able to answer: "Why does answering this matter for what the customer is trying to build?" — phrased in the customer's own goal terms.

When the customer challenges relevance ("how is this relevant?", "why are we talking about this?", "you just keep asking why"), STOP and answer with the rationale in customer-facing terms. Do NOT silently pivot to another question. If they challenge a second time, abandon the line entirely and pick a fundamentally different angle, with explicit acknowledgment ("Got it — moving on.").

# Customer vocabulary
Use the customer's exact terms. If they say "S1-S4 sales cycle" do NOT translate to "ops team" or "sales handoff." Mirror their language verbatim where possible. The priors below contain the vocabulary you should expect.

# Handling answer types
- Concrete answer that addresses your question → record it, possibly drill (if phase 2)
- Concrete answer about a different topic than you asked → acknowledge, then either pursue the new thread if higher-value or return to your original
- Hedge / vague / "we haven't figured that out" → flag it as a gap rather than papering over
- Customer says "above my paygrade" / "leadership decided" / "I don't have visibility" → don't grind, acknowledge, flag for FDE follow-up to the right counterparty, pivot
- Customer asks YOU a question → redirect gently, then ask back
- Customer contradicts something they said earlier → ask which is right; don't ignore

# Style rules
- ONE question per turn. Multi-part questions get half-answered.
- Reject hedge words ("kind of," "maybe," "potentially") in your own questions. Model the precision you want from them.
- Time-bound where possible. "Name a specific moment in the last week" beats "tell me about pain points."
- Concrete examples beat abstractions.
- Don't grind whys when the answer is bedrock-level ("that's just how the business works," "compliance requires it"). Move on.

# Priors (the customer's role context — use this vocabulary)
{PRIORS}

# Your output format
For each turn, output ONLY the next question you would ask the customer. No prose, no preamble, no explanation. Just the question itself, exactly as you'd say it. ONE question, ONE sentence (or two short sentences if needed for context-setting). Do not include the rationale in your output — keep it internal.
"""


def _load_priors(role_id: str | None) -> str:
    """Render the priors the same way our chained agent does."""
    if not role_id:
        return "(no priors configured)"
    path = SKILLS_DIR / role_id / "context.json"
    if not path.exists():
        return "(no priors configured)"
    try:
        rc = json.loads(path.read_text())
    except Exception:
        return "(could not parse priors)"
    parts: list[str] = []
    if rc.get("role_summary"):
        parts.append(f"Role summary: {rc['role_summary']}")
    vocab = rc.get("domain_vocabulary") or {}
    if vocab:
        parts.append("\nDomain vocabulary (use the customer's terms):")
        for term, definition in list(vocab.items())[:20]:
            parts.append(f"- {term}: {definition}")
    rules = rc.get("unwritten_rules") or []
    if rules:
        parts.append("\nUnwritten rules:")
        for r in rules[:8]:
            parts.append(f"- {r}")
    gaps = rc.get("flagged_unknowns") or []
    if gaps:
        parts.append("\nKnown gaps in the priors (probe deeper, don't re-ask):")
        for g in gaps[:6]:
            q = g.get("field") or g.get("probe_suggestion") or ""
            why = g.get("why_it_matters") or ""
            parts.append(f"- {q} — {why}")
    return "\n".join(parts) if parts else "(priors loaded but empty)"


def build_system_prompt(use_case_seed: str, role_id: str | None) -> str:
    return MEGA_SYSTEM_PROMPT_TEMPLATE.format(
        USE_CASE_SEED=use_case_seed,
        PRIORS=_load_priors(role_id),
    )


# ---------------------------------------------------------------------------
# Per-turn execution
# ---------------------------------------------------------------------------

class MegaAgentSession:
    """Maintains conversation history and runs one LLM call per turn.

    Mirror of run_turn() in agent/orchestrator.py — same input/output shape
    so run_comparison.py can call them interchangeably.
    """

    def __init__(self, *, use_case_seed: str, role_id: str | None) -> None:
        self.use_case_seed = use_case_seed
        self.role_id = role_id
        self.system_prompt = build_system_prompt(use_case_seed, role_id)
        self.messages: list[dict] = []
        self.metrics: list[dict] = []

    async def turn(self, client: AsyncOpenAI, customer_message: str) -> tuple[str, dict]:
        """Run one customer turn → agent response.

        Returns (agent_message, metrics_dict).
        """
        self.messages.append({"role": "user", "content": customer_message})
        chat_messages = [
            {"role": "system", "content": self.system_prompt},
            *self.messages,
        ]
        started = time.perf_counter()
        response = await client.chat.completions.create(
            model=DEFAULT_MODEL,
            max_tokens=1024,
            temperature=0.3,
            messages=chat_messages,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        agent_message = response.choices[0].message.content or ""
        self.messages.append({"role": "assistant", "content": agent_message})

        usage = response.usage
        metrics = {
            "duration_ms": duration_ms,
            "input_tokens": usage.prompt_tokens if usage else None,
            "output_tokens": usage.completion_tokens if usage else None,
            "total_tokens": usage.total_tokens if usage else None,
            "model": DEFAULT_MODEL,
        }
        self.metrics.append(metrics)
        return agent_message, metrics

    async def turn_with_tools(
        self,
        client: AsyncOpenAI,
        customer_message: str,
        *,
        tool_schemas: list[dict],
        tool_dispatch: Callable[[str, dict], str],
        max_tool_iterations: int = 4,
    ) -> tuple[str, dict]:
        """Run one customer turn with tool-calling enabled.

        The model can call the provided tools (e.g. get_current_spec_state) to
        orient on the structured spec mid-conversation. Loops until the model
        emits a final assistant message without further tool calls.

        Returns (agent_message, metrics_dict). The metrics_dict includes the
        list of tool calls made during this turn so the trace shows them.
        """
        self.messages.append({"role": "user", "content": customer_message})

        tool_calls_made: list[dict] = []
        total_input_tokens = 0
        total_output_tokens = 0
        n_completion_calls = 0
        started = time.perf_counter()

        for iteration in range(max_tool_iterations):
            chat_messages = [
                {"role": "system", "content": self.system_prompt},
                *self.messages,
            ]
            response = await client.chat.completions.create(
                model=DEFAULT_MODEL,
                max_tokens=1024,
                temperature=0.3,
                messages=chat_messages,
                tools=tool_schemas,
            )
            n_completion_calls += 1
            usage = response.usage
            if usage:
                total_input_tokens += usage.prompt_tokens
                total_output_tokens += usage.completion_tokens

            choice = response.choices[0]
            msg = choice.message

            if msg.tool_calls:
                # Append the assistant message with tool_calls intact so the
                # provider sees the call shape on the next round trip.
                tc_payload = []
                for tc in msg.tool_calls:
                    tc_payload.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    })
                self.messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": tc_payload,
                })
                # Execute each tool, append a tool result message
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except json.JSONDecodeError:
                        args = {}
                    result = tool_dispatch(tc.function.name, args)
                    tool_calls_made.append({
                        "name": tc.function.name,
                        "arguments": args,
                        "result_preview": result[:300],
                    })
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
                continue  # Loop — the model will see tool results and re-respond

            # No tool calls — final response
            agent_message = msg.content or ""
            self.messages.append({"role": "assistant", "content": agent_message})
            duration_ms = int((time.perf_counter() - started) * 1000)
            metrics = {
                "duration_ms": duration_ms,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "total_tokens": total_input_tokens + total_output_tokens,
                "n_completion_calls": n_completion_calls,
                "tool_calls": tool_calls_made,
                "model": DEFAULT_MODEL,
            }
            self.metrics.append(metrics)
            return agent_message, metrics

        # Hit max_tool_iterations without a final response. Return whatever
        # content was last emitted (or a fallback).
        duration_ms = int((time.perf_counter() - started) * 1000)
        fallback = msg.content or "(agent exhausted tool iterations without producing a final question)"
        self.messages.append({"role": "assistant", "content": fallback})
        metrics = {
            "duration_ms": duration_ms,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "total_tokens": total_input_tokens + total_output_tokens,
            "n_completion_calls": n_completion_calls,
            "tool_calls": tool_calls_made,
            "model": DEFAULT_MODEL,
            "tool_loop_exhausted": True,
        }
        self.metrics.append(metrics)
        return fallback, metrics
