"""Regression tests for the v0.8 mega-agent spec tools.

These cover the tools the mega-agent calls during a live discovery turn —
get_current_spec_state / get_checklist_progress. There was NO test coverage
here before, which is exactly why the Issue-A FactRecord refactor silently
broke get_current_spec_state (`zip(t.facts, t.sources)` after `sources` was
removed) — the crash only fired on a live discovery turn, which the inception
and ingest validations never exercised. These lock the FactRecord-correct
behavior so it can't regress again.
"""
from __future__ import annotations

from agent.schemas import DiscoverySpec, DistilledFact
from agent.state import DiscoverySession
from agent.v08.spec_tools import get_checklist_progress, get_current_spec_state


def _session_with_facts() -> DiscoverySession:
    session = DiscoverySession(spec=DiscoverySpec(use_case_seed="brand analytics agent"))
    # An artifact-sourced fact (carries provenance) and a live-discovery fact.
    session.record_fact(
        DistilledFact(topic="current_pain", content="reports take 3 days", source="stated"),
        artifact_id="00_transcript.txt",
    )
    session.record_fact(
        DistilledFact(topic="desired_outcome", content="self-serve answers", source="stated")
    )
    return session


def test_get_current_spec_state_renders_factrecords_without_crashing():
    """The exact regression: this used to zip(t.facts, t.sources) and raise
    AttributeError once sources was folded into FactRecord."""
    out = get_current_spec_state(_session_with_facts())
    assert "reports take 3 days" in out
    assert "self-serve answers" in out
    assert "current_pain" in out
    # Artifact-sourced fact shows its provenance; live fact doesn't.
    assert "(from 00_transcript.txt)" in out


def test_get_current_spec_state_empty_session():
    out = get_current_spec_state(DiscoverySession(spec=DiscoverySpec(use_case_seed="x")))
    assert "none yet" in out


def test_get_checklist_progress_works_with_factrecords():
    out = get_checklist_progress(_session_with_facts())
    # current_pain + desired_outcome each have 1 fact → reflected in coverage.
    assert "current_pain" in out
    assert "desired_outcome" in out
    assert "fact(s)" in out


def test_get_current_spec_state_after_pre_v2_migration():
    """A session loaded from a pre-v2 on-disk shape (parallel arrays) must
    render too — migration produces FactRecords with null provenance, and the
    tool must handle that (no '(from ...)' suffix)."""
    old = {
        "use_case_seed": "legacy",
        "topics": [
            {"topic": "risk", "facts": ["vendor lock-in"], "sources": ["stated"]},
        ],
    }
    session = DiscoverySession(spec=DiscoverySpec.model_validate(old))
    out = get_current_spec_state(session)
    assert "vendor lock-in" in out
    assert "(from" not in out  # migrated facts have no artifact_id
