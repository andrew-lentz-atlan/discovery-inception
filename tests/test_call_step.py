"""Retry core of `call_step` (agent/inception/run.py) — no LLM.

call_step is the one funnel every inception LLM call goes through, and its
retry ladder is what makes the scaffold sub-steps (which embed Python source
as JSON strings) survivable:

  - truncated output (`finish_reason == "length"`) → retry with DOUBLED
    max_tokens, capped at 24576
  - empty response → plain retry (no token bump)
  - JSON that parses but fails Pydantic validation → plain retry
  - retries exhausted → raise the LAST error, which must name the output
    model and the attempt

The client is a shape-faithful fake of AsyncOpenAI's
`.chat.completions.create`; each test asserts against the captured call
kwargs. The 0.75s×attempt backoff is stubbed out via the run module's
`asyncio` reference so the suite stays fast.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

import agent.inception.run as run_mod
from agent.inception.run import call_step


class TinyOut(BaseModel):
    value: str


def _resp(content: str, finish_reason: str = "stop") -> SimpleNamespace:
    """One canned chat-completions response (the attribute shape call_step reads)."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )
        ]
    )


class _FakeCompletions:
    def __init__(self, responses: list[SimpleNamespace]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


def _fake_client(responses: list[SimpleNamespace]):
    completions = _FakeCompletions(responses)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return client, completions


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    """Stub the retry backoff. Patches the run module's `asyncio` reference
    (not the global asyncio module) so nothing else is affected."""

    async def instant_sleep(_seconds):
        return None

    monkeypatch.setattr(
        run_mod, "asyncio", SimpleNamespace(sleep=instant_sleep, gather=asyncio.gather)
    )


# ---------------------------------------------------------------------------
# (a) Truncation → max_tokens doubles on retry, capped at 24576
# ---------------------------------------------------------------------------


async def test_truncation_doubles_max_tokens_on_retry():
    # Unclosed string = unrecoverable by the lenient parser → JSONDecodeError.
    client, completions = _fake_client(
        [
            _resp('{"value": "trunc', finish_reason="length"),
            _resp('{"value": "ok"}'),
        ]
    )

    result = await call_step(
        client, user_prompt="p", output_model=TinyOut, max_tokens=2048, max_retries=1
    )

    assert result.value == "ok"
    assert [c["max_tokens"] for c in completions.calls] == [2048, 4096]


async def test_truncation_bump_is_capped_at_24576():
    client, completions = _fake_client(
        [
            _resp('{"value": "trunc', finish_reason="length"),
            _resp('{"value": "trunc', finish_reason="length"),
            _resp('{"value": "ok"}'),
        ]
    )

    result = await call_step(
        client, user_prompt="p", output_model=TinyOut, max_tokens=16384, max_retries=2
    )

    assert result.value == "ok"
    # 16384 → min(32768, 24576) = 24576 → already at cap, stays put.
    assert [c["max_tokens"] for c in completions.calls] == [16384, 24576, 24576]


# ---------------------------------------------------------------------------
# (b) Empty response → plain retry, no token bump
# ---------------------------------------------------------------------------


async def test_empty_response_retries_without_token_bump():
    client, completions = _fake_client(
        [
            _resp("   "),
            _resp('{"value": "ok"}'),
        ]
    )

    result = await call_step(
        client, user_prompt="p", output_model=TinyOut, max_tokens=2048, max_retries=1
    )

    assert result.value == "ok"
    assert len(completions.calls) == 2
    # The empty branch never doubles — that's reserved for length-truncation.
    assert [c["max_tokens"] for c in completions.calls] == [2048, 2048]


# ---------------------------------------------------------------------------
# (c) Valid JSON, invalid schema → retry
# ---------------------------------------------------------------------------


async def test_validation_failure_retries_then_succeeds():
    client, completions = _fake_client(
        [
            _resp('{"wrong_field": 1}'),  # parses fine, fails TinyOut validation
            _resp('{"value": "ok"}'),
        ]
    )

    result = await call_step(
        client, user_prompt="p", output_model=TinyOut, max_retries=1
    )

    assert result.value == "ok"
    assert len(completions.calls) == 2


# ---------------------------------------------------------------------------
# (d) All attempts fail → raises the informative last error
# ---------------------------------------------------------------------------


async def test_exhausted_retries_raises_informative_error():
    client, completions = _fake_client(
        [
            _resp('{"value": "trunc', finish_reason="length"),
            _resp(""),
        ]
    )

    with pytest.raises(ValueError) as excinfo:
        await call_step(
            client, user_prompt="p", output_model=TinyOut, max_retries=1
        )

    msg = str(excinfo.value)
    # Names the output model and the (last) failing attempt so a scaffold
    # failure log is actionable without re-running.
    assert "TinyOut" in msg
    assert "attempt 2" in msg
    assert len(completions.calls) == 2  # max_retries=1 → exactly 2 attempts
