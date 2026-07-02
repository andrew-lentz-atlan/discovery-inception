"""Tests for parse_json_lenient — the recovery path for the common syntax
errors LLMs emit when output isn't schema-enforced."""
import json

import pytest

from agent.json_utils import parse_json_lenient


def test_clean_json_passes_through():
    assert parse_json_lenient('{"ok": true, "n": 3}') == {"ok": True, "n": 3}


def test_strips_markdown_fences():
    assert parse_json_lenient('```json\n{"x": 1}\n```') == {"x": 1}


def test_recovers_trailing_comma():
    assert parse_json_lenient('{"a": 1, "b": 2,}') == {"a": 1, "b": 2}


def test_recovers_trailing_annotation():
    # e.g. `"tags": ["a"] (optional)` — annotation after a closing bracket
    assert parse_json_lenient('{"tags": ["a"] (optional)}') == {"tags": ["a"]}


def test_recovers_extra_data_second_block():
    # The observed inception flake: a valid object followed by a second block.
    # raw_decode parses the leading value and ignores the rest.
    raw = '{"a": 1, "b": [2, 3]}\n\n{"trailing": "junk"}'
    assert parse_json_lenient(raw) == {"a": 1, "b": [2, 3]}


def test_recovers_fenced_plus_trailing_prose():
    raw = '```json\n{"x": 1}\n```\nHere is why I chose that: blah blah.'
    assert parse_json_lenient(raw) == {"x": 1}


def test_recovers_object_then_prose_no_fence():
    raw = '{"selected": "single-agent-react", "confidence": 0.8}\nThe rationale is...'
    assert parse_json_lenient(raw) == {"selected": "single-agent-react", "confidence": 0.8}


def test_extra_data_does_not_corrupt_string_content():
    # Regression: the raw_decode fallback must try the PRISTINE text before the
    # regex-mutated candidate. The annotation regex isn't string-aware — mutated-
    # first stripped "(per the spec)" from INSIDE this string value.
    raw = '{"purpose": "shape rows into arrays [] (per the spec) before scoring"}\nDone.'
    assert parse_json_lenient(raw) == {
        "purpose": "shape rows into arrays [] (per the spec) before scoring"
    }


def test_extra_data_plus_annotation_still_recovers_via_candidate():
    # Pristine raw_decode fails (annotation breaks the object mid-parse), so the
    # mutated candidate must still be tried second: annotation stripped, then
    # raw_decode ignores the trailing prose.
    raw = '{"tags": ["a"] (optional)}\nextra prose'
    assert parse_json_lenient(raw) == {"tags": ["a"]}


def test_unrecoverable_raises():
    with pytest.raises(json.JSONDecodeError):
        parse_json_lenient("not json at all {{{")
