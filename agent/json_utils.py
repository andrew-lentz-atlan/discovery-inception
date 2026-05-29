"""Lenient JSON parsing for LLM-emitted output.

Strict json.loads rejects two error classes the model emits sporadically:
  - Trailing commas before `]` or `}` — `["a", "b",]` — valid in JSON5 / JS /
    Python but invalid in strict JSON. The model has been trained on lots of
    code that allows them, so it occasionally emits them.
  - Missing commas between adjacent object fields — `{"a": 1 "b": 2}` — a
    common typo class the model has seen in error messages.

Both have surfaced as inception scaffold-writer failures during real runs
(OrchestratorStub trailing comma; UnwrittenRulesResult missing delimiter).
Same root cause; different specific syntax.

This module exposes `parse_json_lenient(text)` which:
  1. Tries strict json.loads first (fast path; works on most outputs).
  2. On failure, applies deterministic regex-based fixes for the two
     known-correctable error classes and retries.
  3. Re-raises the original error if no fix succeeded.

The fixes are conservative — they only insert/remove commas in positions
where JSON syntax requires/forbids them. They don't try to repair more
exotic syntax errors (unclosed strings, malformed nesting, etc.) because
those are signal that the output is corrupt enough to warrant a retry,
not a repair.

Sibling to the Mermaid sanitizer + the distill snapping fix: deterministic
post-processors on LLM output that catch what prompts can't reliably
guarantee. Codified in findings/09.
"""
from __future__ import annotations

import json
import re
from typing import Any


# Matches the end of a JSON value (string, number, true/false/null, closing
# bracket/brace) followed by whitespace+newline+whitespace, followed by a
# quoted key + colon. That's exactly the pattern of two adjacent object
# fields with a missing comma between them.
_MISSING_COMMA_BETWEEN_FIELDS = re.compile(
    r'("(?:[^"\\]|\\.)*"|\d+(?:\.\d+)?|\]|\}|true|false|null)'  # end of a value
    r'(\s*\n\s*)'                                                # whitespace + newline
    r'("(?:[^"\\]|\\.)*"\s*:)'                                   # quoted key + colon
)


# Matches a trailing comma before `]` or `}`. Conservative: requires only
# whitespace between the comma and the closing bracket so we don't
# accidentally rewrite legitimate commas in deeper structures.
_TRAILING_COMMA = re.compile(r",(\s*[\]\}])")


def _strip_fences(text: str) -> str:
    """Strip ```json ... ``` or ``` ... ``` fences that LLMs sometimes
    wrap output in despite the prompt asking for raw JSON. Idempotent."""
    s = text.strip()
    if s.startswith("```"):
        # Drop the opening fence line (```json or ```)
        s = s.split("\n", 1)[1] if "\n" in s else s
        # Drop the trailing fence
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


def parse_json_lenient(text: str) -> Any:
    """Parse JSON, tolerating common LLM-emitted syntax errors.

    Strategy:
      1. Strip markdown fences if present (idempotent).
      2. Try strict json.loads.
      3. On failure, apply deterministic fixes — trailing commas and
         missing-comma-between-fields — and retry.
      4. Re-raise the original error if no fix succeeded.

    Raises json.JSONDecodeError on unrecoverable malformations.
    """
    stripped = _strip_fences(text)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as primary_error:
        # Apply both fixes (order matters: missing-comma first, then trailing-comma
        # in case the trailing-comma fix uncovers a missing-comma case)
        candidate = _MISSING_COMMA_BETWEEN_FIELDS.sub(r"\1,\2\3", stripped)
        candidate = _TRAILING_COMMA.sub(r"\1", candidate)
        if candidate != stripped:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
        # Couldn't recover; re-raise the primary error so the caller sees
        # the original syntax problem (not a downstream effect of our patching).
        raise primary_error
