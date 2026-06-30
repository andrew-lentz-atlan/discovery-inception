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


# Matches an annotation-after-value pattern the model emits when it's
# trying to add a docstring-style note to a JSON value, e.g.:
#   "metrics": ["string"] (optional customer-provided metrics)
#   "flags": [{"id": "string"}] (optional)
# That's a comment in JS-style syntax — invalid in strict JSON.
#
# Conservative: requires the value to end in `]` or `}` (composite closers
# that can never appear inside an open JSON string), followed by whitespace
# and a parenthesized expression. We strip the annotation, preserving the
# value. False-positive risk is low because `]/}` outside a string position
# is always a structural token.
#
# Surfaced from SkillProposalResult during atlan-se-copilot inception runs
# after the patterns-deepening branch added harness deep-dives with embedded
# Python dict literals in their code samples (the model started mimicking
# that annotation style). Codified in findings/09 as the fourth instance of
# the deterministic-post-processor pattern.
_TRAILING_ANNOTATION = re.compile(r"([\]\}])\s+\([^)]*\)")


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
        # Apply all three fixes (order matters: missing-comma first so we
        # see all field boundaries; trailing-annotation second since it
        # strips the annotation that would otherwise be inside a missing
        # comma; trailing-comma last in case earlier fixes uncovered one)
        candidate = _MISSING_COMMA_BETWEEN_FIELDS.sub(r"\1,\2\3", stripped)
        candidate = _TRAILING_ANNOTATION.sub(r"\1", candidate)
        candidate = _TRAILING_COMMA.sub(r"\1", candidate)
        if candidate != stripped:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
        # 'Extra data': a valid JSON value followed by trailing content — the model
        # appended a second block or commentary after the closing brace (the most
        # common structured-output failure when output isn't schema-enforced).
        # raw_decode parses the leading value and ignores the rest. Try it on the
        # cleaned candidate and the raw stripped text. Only RETURNS on success, so
        # it can't regress any input the strict path already handled.
        for attempt_text in (candidate, stripped):
            try:
                obj, _end = json.JSONDecoder().raw_decode(attempt_text.lstrip())
                return obj
            except json.JSONDecodeError:
                continue
        # Couldn't recover. If the env var DISCOVERY_DUMP_BAD_JSON is set,
        # write the raw content to that path so we can inspect what shape
        # the model emitted. Lets us iterate on the parser without
        # repeatedly running expensive inception calls just to see the bad
        # output. The dump is overwrite-on-each-failure (1 file per process).
        import os
        dump_path = os.environ.get("DISCOVERY_DUMP_BAD_JSON")
        if dump_path:
            try:
                from pathlib import Path
                Path(dump_path).write_text(stripped)
            except Exception:
                pass
        # Re-raise the primary error so the caller sees the original syntax
        # problem (not a downstream effect of our patching).
        raise primary_error
