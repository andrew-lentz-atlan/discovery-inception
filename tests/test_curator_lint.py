"""Deterministic STYLE.md lint checks in agent/patterns_curator/audit.py.

Pure-Python: builds a throwaway patterns/ tree under tmp_path and runs
`deterministic_audit` against it — no LLM, no network, no repo state.
Each test targets one lint rule (STYLE-2..6 + the stale-draft note).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agent.patterns_curator.audit import (
    _iter_canonical_entries,
    deterministic_audit,
)

TODAY = "2026-07-15"


def _entry_text(
    *,
    title: str = "Test Entry",
    category: str = "anti-patterns",
    status: str = "draft",
    last_updated: str = "2026-07-01",
    source_findings: str = "[]",
    related: str = "[]",
    body: str = "# Test Entry\n\nA timeless third-person body.\n",
) -> str:
    return (
        "---\n"
        f"title: {title}\n"
        f"category: {category}\n"
        f"status: {status}\n"
        f"last_updated: {last_updated}\n"
        f"source_findings: {source_findings}\n"
        "source_external: []\n"
        "contradicts: []\n"
        f"related: {related}\n"
        "---\n"
        f"{body}"
    )


@pytest.fixture()
def wiki(tmp_path: Path) -> dict[str, Path]:
    """Minimal project root: patterns/ with one category dir + findings/."""
    patterns = tmp_path / "patterns"
    (patterns / "anti-patterns").mkdir(parents=True)
    (patterns / "skill-design").mkdir(parents=True)
    findings = tmp_path / "findings"
    findings.mkdir()
    (findings / "01-real-finding.md").write_text("# a real finding\n")
    return {"root": tmp_path, "patterns": patterns}


def _lint(wiki: dict[str, Path], *, staleness_days: int = 365):
    return deterministic_audit(
        TODAY,
        staleness_days,
        staleness_days,
        patterns_dir=wiki["patterns"],
        project_root=wiki["root"],
    )


def _rules(findings) -> list[str | None]:
    return [f.rule for f in findings]


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------


def test_clean_entry_produces_no_findings(wiki):
    (wiki["patterns"] / "anti-patterns" / "clean-entry.md").write_text(_entry_text())
    assert _lint(wiki) == []


def test_working_suffix_files_are_not_canonical(wiki):
    for suffix in (".draft", ".update", ".contested", ".candidate", ".triage", ".reference", ".repair"):
        (wiki["patterns"] / "anti-patterns" / f"wip{suffix}.md").write_text(_entry_text())
    assert _iter_canonical_entries(wiki["patterns"]) == []
    assert _lint(wiki) == []


# ---------------------------------------------------------------------------
# (a) STYLE-2 — validated must name its evidence
# ---------------------------------------------------------------------------


def test_style2_validated_without_evidence_flagged(wiki):
    path = wiki["patterns"] / "anti-patterns" / "overclaimed.md"
    path.write_text(_entry_text(status="validated"))
    findings = _lint(wiki)
    assert "STYLE-2" in _rules(findings)
    f = next(f for f in findings if f.rule == "STYLE-2")
    assert f.file.endswith("patterns/anti-patterns/overclaimed.md")
    assert f.line == 4  # `status:` line
    assert f.slug == "anti-patterns/overclaimed"


def test_style2_validated_with_empirical_anchor_passes(wiki):
    body = "# T\n\nThesis.\n\n## Empirical anchor\n\nCitation density swung 25→7 across identical runs.\n"
    (wiki["patterns"] / "anti-patterns" / "anchored.md").write_text(
        _entry_text(status="validated", body=body)
    )
    assert "STYLE-2" not in _rules(_lint(wiki))


def test_style2_validated_with_provenance_section_passes(wiki):
    body = "# T\n\nThesis.\n\n## Provenance\n\nMeasured in findings/01.\n"
    (wiki["patterns"] / "anti-patterns" / "provenanced.md").write_text(
        _entry_text(status="validated", body=body)
    )
    assert "STYLE-2" not in _rules(_lint(wiki))


def test_style2_validated_with_real_source_findings_passes(wiki):
    (wiki["patterns"] / "anti-patterns" / "sourced.md").write_text(
        _entry_text(status="validated", source_findings="[findings/01-real-finding.md]")
    )
    assert "STYLE-2" not in _rules(_lint(wiki))


# ---------------------------------------------------------------------------
# (b) STYLE-4 — first-person / roadmap voice
# ---------------------------------------------------------------------------


def test_style4_voice_regex_flags_matched_line(wiki):
    body = (
        "# T\n"
        "\n"
        "A fine sentence.\n"
        "We Found that the orchestrator compensates.\n"
        "My recommendation: the pipeline should add signal X.\n"
    )
    path = wiki["patterns"] / "anti-patterns" / "voicey.md"
    path.write_text(_entry_text(body=body))
    hits = [f for f in _lint(wiki) if f.rule == "STYLE-4"]
    assert len(hits) == 2  # case-insensitive: "We Found" + "My recommendation"
    descriptions = " | ".join(f.description for f in hits)
    assert "We Found that the orchestrator compensates." in descriptions
    # line numbers point at the real file lines (frontmatter is 10 lines)
    lines = path.read_text().splitlines()
    for f in hits:
        assert f.line is not None
        assert f.description.split(": ", 1)[1] in lines[f.line - 1]


def test_style4_all_banned_phrases_match(wiki):
    phrases = [
        "my read", "my recommendation", "we found", "we were told",
        "our pipeline", "queued for next session", "deferred to next session",
    ]
    body = "# T\n\n" + "\n".join(f"Sentence with {p} inside." for p in phrases) + "\n"
    (wiki["patterns"] / "anti-patterns" / "all-voices.md").write_text(_entry_text(body=body))
    hits = [f for f in _lint(wiki) if f.rule == "STYLE-4"]
    assert len(hits) == len(phrases)


def test_style4_clean_voice_not_flagged(wiki):
    body = "# T\n\nThe pipeline compensates. Sessions are stateless. My readings differ.\n"
    (wiki["patterns"] / "anti-patterns" / "quiet.md").write_text(_entry_text(body=body))
    assert "STYLE-4" not in _rules(_lint(wiki))


# ---------------------------------------------------------------------------
# (c) STYLE-6 — category must equal parent directory
# ---------------------------------------------------------------------------


def test_style6_category_directory_mismatch(wiki):
    (wiki["patterns"] / "anti-patterns" / "misfiled.md").write_text(
        _entry_text(category="skill-design")
    )
    findings = [f for f in _lint(wiki) if f.rule == "STYLE-6"]
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert findings[0].line == 3  # `category:` line
    assert "skill-design" in findings[0].description
    assert "anti-patterns" in findings[0].description


# ---------------------------------------------------------------------------
# (d) STYLE-5 — body citations must resolve; working suffixes never citable
# ---------------------------------------------------------------------------


def test_style5_body_citation_unresolved(wiki):
    body = "# T\n\nSee patterns/skill-design/ghost-entry.md for details.\n"
    (wiki["patterns"] / "anti-patterns" / "citer.md").write_text(_entry_text(body=body))
    hits = [f for f in _lint(wiki) if f.rule == "STYLE-5" and f.kind == "reference_broken"]
    assert any("patterns/skill-design/ghost-entry.md" in f.description for f in hits)


def test_style5_body_citation_resolving_passes(wiki):
    (wiki["patterns"] / "skill-design" / "real-entry.md").write_text(
        _entry_text(category="skill-design")
    )
    body = "# T\n\nSee patterns/skill-design/real-entry.md.\n"
    (wiki["patterns"] / "anti-patterns" / "good-citer.md").write_text(_entry_text(body=body))
    assert "STYLE-5" not in _rules(_lint(wiki))


def test_style5_working_suffix_citation_flagged_even_if_file_exists(wiki):
    (wiki["patterns"] / "skill-design" / "wip.draft.md").write_text(
        _entry_text(category="skill-design")
    )
    body = "# T\n\nSee patterns/skill-design/wip.draft.md.\n"
    path = wiki["patterns"] / "anti-patterns" / "draft-citer.md"
    path.write_text(_entry_text(body=body))
    hits = [f for f in _lint(wiki) if f.rule == "STYLE-5"]
    assert len(hits) == 1
    assert "working-suffix" in hits[0].description
    assert hits[0].severity == "error"
    assert hits[0].line == path.read_text().splitlines().index(
        "See patterns/skill-design/wip.draft.md."
    ) + 1


# ---------------------------------------------------------------------------
# (e) STYLE-5 — related: refs must resolve to canonical entries
# ---------------------------------------------------------------------------


def test_style5_related_unresolved(wiki):
    (wiki["patterns"] / "anti-patterns" / "linker.md").write_text(
        _entry_text(related="[no-such-entry]")
    )
    hits = [f for f in _lint(wiki) if f.rule == "STYLE-5"]
    assert len(hits) == 1
    assert "no-such-entry" in hits[0].description
    assert hits[0].line == 9  # `related:` line


def test_style5_related_to_draft_only_file_flagged(wiki):
    # a .draft.md exists but is NOT canonical — the ref must not resolve
    (wiki["patterns"] / "skill-design" / "pending.draft.md").write_text(
        _entry_text(category="skill-design")
    )
    (wiki["patterns"] / "anti-patterns" / "eager-linker.md").write_text(
        _entry_text(related="[pending]")
    )
    assert any(f.rule == "STYLE-5" for f in _lint(wiki))


def test_style5_related_resolving_passes(wiki):
    (wiki["patterns"] / "skill-design" / "target.md").write_text(
        _entry_text(category="skill-design")
    )
    (wiki["patterns"] / "anti-patterns" / "fine-linker.md").write_text(
        _entry_text(related="[target]")
    )
    assert "STYLE-5" not in _rules(_lint(wiki))


# ---------------------------------------------------------------------------
# (f) STYLE-3 — source_findings must be real findings/ files
# ---------------------------------------------------------------------------


def test_style3_fake_findings_path_flagged(wiki):
    (wiki["patterns"] / "anti-patterns" / "fabricated.md").write_text(
        _entry_text(source_findings="[findings/99-invented.md]")
    )
    hits = [f for f in _lint(wiki) if f.rule == "STYLE-3"]
    assert len(hits) == 1
    assert hits[0].kind == "provenance_violation"
    assert hits[0].severity == "error"
    assert "findings/99-invented.md" in hits[0].description
    assert hits[0].line == 6  # `source_findings:` line


def test_style3_external_source_misfiled_as_finding(wiki):
    (wiki["patterns"] / "anti-patterns" / "misfiled-talk.md").write_text(
        _entry_text(source_findings="[https://example.com/talk]")
    )
    assert any(f.rule == "STYLE-3" for f in _lint(wiki))


def test_style3_real_findings_file_passes(wiki):
    (wiki["patterns"] / "anti-patterns" / "honest.md").write_text(
        _entry_text(source_findings="[findings/01-real-finding.md]")
    )
    assert "STYLE-3" not in _rules(_lint(wiki))


# ---------------------------------------------------------------------------
# (g) stale draft — info note tagged STYLE-2
# ---------------------------------------------------------------------------


def test_stale_draft_gets_style2_info_note(wiki):
    (wiki["patterns"] / "anti-patterns" / "old-draft.md").write_text(
        _entry_text(status="draft", last_updated="2026-01-01")
    )
    findings = _lint(wiki, staleness_days=90)
    stale = [f for f in findings if f.kind == "stale"]
    assert len(stale) == 1
    assert stale[0].severity == "info"
    assert stale[0].rule == "STYLE-2"
    assert "draft" in stale[0].description


def test_stale_non_draft_has_no_style_rule(wiki):
    body = "# T\n\nThesis.\n\n## Empirical anchor\n\nMeasured.\n"
    (wiki["patterns"] / "anti-patterns" / "old-validated.md").write_text(
        _entry_text(status="validated", last_updated="2026-01-01", body=body)
    )
    stale = [f for f in _lint(wiki, staleness_days=90) if f.kind == "stale"]
    assert len(stale) == 1
    assert stale[0].rule is None


def test_fresh_draft_not_flagged_stale(wiki):
    (wiki["patterns"] / "anti-patterns" / "new-draft.md").write_text(
        _entry_text(status="draft", last_updated="2026-07-10")
    )
    assert [f for f in _lint(wiki, staleness_days=90) if f.kind == "stale"] == []
