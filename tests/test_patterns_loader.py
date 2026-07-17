"""load_pattern_category: curator working files stay out of the agent payload.

Promotion is the gate to agent-visibility. A .draft.md in the payload leaks a
near-canonical name the model cites WITHOUT the suffix, which the citation
verifier then (correctly) flags as a non-existent slug — observed live on the
v1.0.0 pre-flight run."""
import agent.inception.run as run_mod
from agent.inception.run import load_pattern_category


def test_working_suffix_files_excluded(tmp_path, monkeypatch):
    cat = tmp_path / "anti-patterns"
    cat.mkdir(parents=True)
    (cat / "real-entry.md").write_text("# Real entry\ncanonical content")
    (cat / "wip-entry.draft.md").write_text("# Draft\nnot yet promoted")
    (cat / "real-entry.update.md").write_text("# Update proposal")
    (cat / "wip-entry.triage.md").write_text("# Triage sidecar")
    (cat / "other.contested.md").write_text("# Contested")
    (cat / "other.candidate.md").write_text("# Promotion candidate")
    (cat / "real-entry.reference.md").write_text("# Reference companion")
    (cat / "notes.txt").write_text("not markdown")

    monkeypatch.setattr(run_mod, "PATTERNS_DIR", tmp_path)
    payload = load_pattern_category("anti-patterns")

    assert "canonical content" in payload
    assert "Pattern: `anti-patterns/real-entry`" in payload
    for leaked in ("Draft", "Update proposal", "Triage sidecar", "Contested",
                   "Promotion candidate", "Reference companion"):
        assert leaked not in payload


def test_empty_after_exclusion(tmp_path, monkeypatch):
    cat = tmp_path / "skill-design"
    cat.mkdir(parents=True)
    (cat / "only.draft.md").write_text("# Draft only")
    monkeypatch.setattr(run_mod, "PATTERNS_DIR", tmp_path)
    assert "empty" in load_pattern_category("skill-design")
