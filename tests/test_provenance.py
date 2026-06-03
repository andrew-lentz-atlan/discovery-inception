"""Tests for per-fact provenance (schema v2 — FactRecord).

These are the first project tests. They lock down the two things that would
silently break as the fact store fills with real customer sessions:

  1. New facts carry provenance (artifact_id + provenance_unit).
  2. Pre-v2 sessions on disk (parallel facts[]/sources[] arrays) migrate
     cleanly into list[FactRecord] via the TopicEntry model_validator.

The migration is the load-bearing one: if it regresses, every pre-v2 session
on disk becomes undeserializable, which is exactly the retrofit-pain the
provenance refactor exists to prevent.
"""
from __future__ import annotations

from agent.schemas import (
    SPEC_SCHEMA_VERSION,
    DiscoverySpec,
    DistilledFact,
    FactRecord,
    TopicEntry,
)
from agent.state import DiscoverySession


# ---------------------------------------------------------------------------
# New-shape construction + recording
# ---------------------------------------------------------------------------


def test_spec_stamps_current_schema_version():
    spec = DiscoverySpec(use_case_seed="test agent")
    assert spec.schema_version == SPEC_SCHEMA_VERSION
    assert SPEC_SCHEMA_VERSION == 2


def test_record_fact_carries_artifact_provenance():
    session = DiscoverySession(spec=DiscoverySpec(use_case_seed="x"))
    fact = DistilledFact(
        topic="current_pain",
        content="reports take 3 days",
        source="stated",
        provenance_unit="line 42",
    )
    session.record_fact(fact, artifact_id="00_transcript.txt")

    stored = session.spec.topics[0].facts[0]
    assert isinstance(stored, FactRecord)
    assert stored.content == "reports take 3 days"
    assert stored.source == "stated"
    assert stored.artifact_id == "00_transcript.txt"
    assert stored.provenance_unit == "line 42"


def test_live_discovery_fact_has_no_artifact_id():
    """A fact recorded without an artifact_id (live conversation) keeps it None.
    The absence IS the signal that the fact is conversation-sourced."""
    session = DiscoverySession(spec=DiscoverySpec(use_case_seed="x"))
    session.record_fact(DistilledFact(topic="risk", content="vendor lock-in", source="stated"))
    assert session.spec.topics[0].facts[0].artifact_id is None
    assert session.spec.topics[0].facts[0].provenance_unit is None


def test_stated_overrides_prior_supersedes_with_provenance_marker():
    session = DiscoverySession(spec=DiscoverySpec(use_case_seed="x"))
    session.record_fact(
        DistilledFact(topic="ops", content="100 ops/day", source="inferred_from_priors"),
        artifact_id="00_runbook.txt",
    )
    # An override moves the prior fact to superseded_facts with a marker.
    session.record_fact(
        DistilledFact(topic="ops", content="1000 ops/day", source="stated_overrides_prior")
    )
    entry = session.spec.topics[0]
    assert len(entry.facts) == 1
    assert entry.facts[0].content == "1000 ops/day"
    assert len(entry.superseded_facts) == 1
    # Marker preserves both the old source-kind and its artifact provenance.
    assert "inferred_from_priors" in entry.superseded_facts[0]
    assert "00_runbook.txt" in entry.superseded_facts[0]
    assert "100 ops/day" in entry.superseded_facts[0]


# ---------------------------------------------------------------------------
# Migration: pre-v2 parallel-array shape → FactRecord
# ---------------------------------------------------------------------------


def test_migrates_pre_v2_parallel_arrays():
    old = {
        "topic": "current_pain",
        "facts": ["reports take 3 days", "manual reconciliation"],
        "sources": ["stated", "inferred_from_priors"],
        "superseded_facts": [],
        "bedrock_reached": False,
        "why_chain": [],
        "pending_questions": [],
    }
    entry = TopicEntry.model_validate(old)
    assert len(entry.facts) == 2
    assert all(isinstance(f, FactRecord) for f in entry.facts)
    assert entry.facts[0].content == "reports take 3 days"
    assert entry.facts[0].source == "stated"
    assert entry.facts[1].source == "inferred_from_priors"
    # Pre-v2 facts genuinely had no provenance — migration is honest about it.
    assert entry.facts[0].artifact_id is None
    assert entry.facts[0].provenance_unit is None


def test_migration_tolerates_missing_or_short_sources():
    """Old data with a sources array shorter than facts (or absent) must not
    crash — default the missing source-kind to 'stated'."""
    short = {"topic": "t", "facts": ["a", "b", "c"], "sources": ["stated"]}
    entry = TopicEntry.model_validate(short)
    assert [f.source for f in entry.facts] == ["stated", "stated", "stated"]

    none_sources = {"topic": "t", "facts": ["only one"]}
    entry2 = TopicEntry.model_validate(none_sources)
    assert entry2.facts[0].source == "stated"


def test_empty_topic_survives_migration():
    entry = TopicEntry.model_validate({"topic": "desired_outcome", "facts": [], "sources": []})
    assert entry.facts == []


def test_new_shape_passes_through_untouched():
    """FactRecord-shaped data (list[dict] with content/source) must NOT be
    re-migrated — the validator only fires on list[str] facts."""
    new = {
        "topic": "t",
        "facts": [
            {"content": "x", "source": "stated", "artifact_id": "00_a.txt", "provenance_unit": "t=1:03"}
        ],
    }
    entry = TopicEntry.model_validate(new)
    assert entry.facts[0].artifact_id == "00_a.txt"
    assert entry.facts[0].provenance_unit == "t=1:03"


def test_full_pre_v2_spec_round_trips():
    """A whole pre-v2 DiscoverySpec (no schema_version, parallel arrays)
    deserializes and ends up stamped at the current version."""
    old_spec = {
        "use_case_seed": "legacy agent",
        "role_id": "soco",
        "phase": "drilling",
        "topics": [
            {"topic": "current_pain", "facts": ["slow"], "sources": ["stated"]},
            {"topic": "desired_outcome", "facts": [], "sources": []},
        ],
    }
    spec = DiscoverySpec.model_validate(old_spec)
    assert spec.schema_version == SPEC_SCHEMA_VERSION
    assert spec.topics[0].facts[0].content == "slow"
    assert spec.topics[0].facts[0].artifact_id is None


# ---------------------------------------------------------------------------
# Ingest pipeline glue: build_session threads artifact_id onto every fact
# ---------------------------------------------------------------------------


def test_build_session_threads_artifact_id():
    """build_session must stamp each fact with the artifact it came from,
    keyed by the same id scheme as the preserved copy filename. This is the
    deterministic pipeline glue that the line-352 `_path` discard used to
    drop on the floor."""
    from pathlib import Path

    from agent.ingest import artifact_id_for, build_session

    p1 = Path("/tmp/sources/call-transcript.txt")
    p2 = Path("/tmp/sources/runbook.md")
    facts_per_artifact = [
        (p1, [DistilledFact(topic="current_pain", content="slow reports", source="stated")]),
        (p2, [DistilledFact(topic="tech_stack", content="Snowflake + dbt", source="stated")]),
    ]
    artifact_ids = {str(p1): artifact_id_for(0, p1), str(p2): artifact_id_for(1, p2)}

    session = build_session(
        use_case_seed="x",
        role_id=None,
        merged_role_context=None,
        facts_per_artifact=facts_per_artifact,
        artifact_ids=artifact_ids,
    )

    by_topic = {t.topic: t for t in session.spec.topics}
    assert by_topic["current_pain"].facts[0].artifact_id == "00_call-transcript.txt"
    assert by_topic["tech_stack"].facts[0].artifact_id == "01_runbook.md"


def test_build_session_without_artifact_ids_records_no_provenance():
    """A direct caller that omits the artifact_ids map (e.g. a unit test)
    still works — facts record with artifact_id=None, same as live discovery."""
    from pathlib import Path

    from agent.ingest import build_session

    session = build_session(
        use_case_seed="x",
        role_id=None,
        merged_role_context=None,
        facts_per_artifact=[
            (Path("/tmp/a.txt"), [DistilledFact(topic="risk", content="lock-in", source="stated")])
        ],
    )
    assert session.spec.topics[0].facts[0].artifact_id is None


# ---------------------------------------------------------------------------
# Issue B: structured spec digest — the typed signal prose drops
# ---------------------------------------------------------------------------


def test_spec_digest_falls_back_when_nothing_extra():
    """A spec with no bounded_context and no tensions adds nothing the prose
    doesn't already cover → digest is the fallback sentinel, not empty JSON."""
    import json as _json

    from agent.inception.run import NO_SPEC_STRUCTURED, build_spec_digest

    digest = build_spec_digest(DiscoverySpec(use_case_seed="x"))
    assert digest == NO_SPEC_STRUCTURED
    # Must not be parseable JSON — it's a human-readable sentinel.
    try:
        _json.loads(digest)
        assert False, "fallback should not be JSON"
    except _json.JSONDecodeError:
        pass


def test_spec_digest_carries_bounded_context_and_tensions():
    """The two fields the prose render drops/summarizes are carried in full."""
    import json as _json

    from agent.inception.run import build_spec_digest
    from agent.schemas import WorkingTheory

    spec = DiscoverySpec(
        use_case_seed="x",
        bounded_context={
            "source_tenant": "acme.atlan.com",
            "glossary_terms": ["revenue_net", "churn_rate"],
            "tables": ["orders", "customers"],
        },
    )
    spec.working_theory = WorkingTheory(
        one_line_framing="f",
        sharpest_disconfirmer="d",
        confidence="medium",
        internal_tensions=["real-time vs batch unresolved"],
    )
    parsed = _json.loads(build_spec_digest(spec))
    # Full bounded_context, not just counts — the specific terms are present.
    assert parsed["bounded_context"]["glossary_terms"] == ["revenue_net", "churn_rate"]
    assert parsed["internal_tensions"] == ["real-time vs batch unresolved"]
    assert parsed["schema_version"] == SPEC_SCHEMA_VERSION


def test_spec_digest_with_only_tensions():
    """Tensions alone (no Atlan context) still produce a digest, not fallback."""
    import json as _json

    from agent.inception.run import build_spec_digest
    from agent.schemas import WorkingTheory

    spec = DiscoverySpec(use_case_seed="x")
    spec.working_theory = WorkingTheory(
        one_line_framing="f",
        sharpest_disconfirmer="d",
        confidence="low",
        internal_tensions=["A contradicts B"],
    )
    parsed = _json.loads(build_spec_digest(spec))
    assert parsed["internal_tensions"] == ["A contradicts B"]
    assert parsed["bounded_context"] is None
