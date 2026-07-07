"""Deterministic stop-condition + topic-thread logic in agent/state.py.

The load-bearing contract: the CONCEPTUAL checklist (8 canonical topics,
decision_point ×3) is the hard gate for declare_ready; the TECHNICAL topic
thread is advisory — inception wants it, but it must never block readiness.
Also covers the phase-1→2 breadth threshold (5 of 8 canonical topics) and
the concern-thread classifier that splits spec.md rendering.
"""
from __future__ import annotations

from agent.schemas import DiscoverySpec, DistilledFact
from agent.state import (
    CANONICAL_CHECKLIST_TOPICS,
    DiscoverySession,
    MULTI_INSTANCE_REQUIREMENTS,
    PHASE_ADVANCE_THRESHOLD,
    TECHNICAL_TOPICS,
    evaluate_checklist,
    should_advance_phase,
    topic_concern_thread,
)
from agent.v08.spec_tools import get_checklist_progress


def _fact(topic: str, content: str) -> DistilledFact:
    return DistilledFact(topic=topic, content=content, source="stated")


def _session_covering(topics, per_topic_counts=None) -> DiscoverySession:
    """Session with ≥1 fact on each given topic (or the per-topic count)."""
    session = DiscoverySession(spec=DiscoverySpec(use_case_seed="test agent"))
    for topic in topics:
        n = (per_topic_counts or {}).get(topic, 1)
        for i in range(n):
            session.record_fact(_fact(topic, f"{topic} fact {i}"))
    return session


def _fully_covered_session() -> DiscoverySession:
    return _session_covering(
        CANONICAL_CHECKLIST_TOPICS, per_topic_counts=MULTI_INSTANCE_REQUIREMENTS
    )


# ---------------------------------------------------------------------------
# (a) Technical topics are advisory — they must not gate readiness
# ---------------------------------------------------------------------------


def test_ready_with_all_canonical_and_zero_technical_topics():
    session = _fully_covered_session()
    spec = session.spec
    # Precondition: genuinely zero technical coverage.
    assert not any(t.topic in TECHNICAL_TOPICS for t in spec.topics)
    assert MULTI_INSTANCE_REQUIREMENTS["decision_point"] == 3  # 3 decision points

    result = evaluate_checklist(spec)

    assert result.ready is True
    # All hard per-topic items pass...
    assert all(result.items[k] for k in result.items if k.startswith("has_"))
    # ...and whatever remains in `missing` is advisory-only (bedrock), which
    # by contract does not affect `ready`.
    assert all("advisory" in m for m in result.missing)


def test_not_ready_with_only_two_decision_points():
    """Control: the ×3 multi-instance requirement is a hard gate."""
    session = _session_covering(
        CANONICAL_CHECKLIST_TOPICS, per_topic_counts={"decision_point": 2}
    )
    result = evaluate_checklist(session.spec)
    assert result.ready is False
    assert result.items["has_decision_point_x3"] is False
    assert any(m.startswith("decision_point: need 3, have 2") for m in result.missing)


# ---------------------------------------------------------------------------
# (b) topic_concern_thread classification
# ---------------------------------------------------------------------------


def test_topic_concern_thread_maps_every_topic():
    for topic in TECHNICAL_TOPICS:
        assert topic_concern_thread(topic) == "technical", topic
    for topic in CANONICAL_CHECKLIST_TOPICS:
        assert topic_concern_thread(topic) == "conceptual", topic
    assert topic_concern_thread("some_minted_slug") == "other"


# ---------------------------------------------------------------------------
# (c) atlan_integration_posture is a technical topic and is surfaced
# ---------------------------------------------------------------------------


def test_atlan_integration_posture_in_technical_topics_and_progress_output():
    assert "atlan_integration_posture" in TECHNICAL_TOPICS

    session = DiscoverySession(spec=DiscoverySpec(use_case_seed="atlan-native agent"))
    session.record_fact(_fact("atlan_integration_posture", "MCP reachable; MDLH enabled"))

    out = get_checklist_progress(session)
    assert "atlan_integration_posture" in out
    # It renders in the advisory technical section with its fact counted...
    assert "✓ atlan_integration_posture: 1 fact(s)" in out
    # ...and does not make the session ready on its own.
    assert "Ready to declare? False" in out


# ---------------------------------------------------------------------------
# (d) should_advance_phase — breadth threshold at 5 of 8 canonical topics
# ---------------------------------------------------------------------------


def test_should_advance_phase_below_and_at_threshold():
    assert PHASE_ADVANCE_THRESHOLD == 5

    four = _session_covering(CANONICAL_CHECKLIST_TOPICS[:4])
    assert should_advance_phase(four.spec) is False

    five = _session_covering(CANONICAL_CHECKLIST_TOPICS[:5])
    assert should_advance_phase(five.spec) is True


def test_should_advance_phase_counts_only_canonical_topics():
    """4 canonical + a non-canonical topic with facts stays below threshold."""
    session = _session_covering(CANONICAL_CHECKLIST_TOPICS[:4])
    session.record_fact(_fact("tech_stack", "python everywhere"))  # technical thread
    session.record_fact(_fact("minted_slug", "irrelevant to the gate"))
    assert should_advance_phase(session.spec) is False


def test_should_advance_phase_only_fires_in_lay_of_the_land():
    session = _session_covering(CANONICAL_CHECKLIST_TOPICS)  # full coverage
    session.spec.phase = "drilling"
    assert should_advance_phase(session.spec) is False
