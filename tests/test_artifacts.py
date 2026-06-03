"""Tests for the artifact adapter seam (agent/artifacts.py).

The seam is where new modalities plug in. These lock down the dispatch
contract so that adding a modality later (register one ArtifactExtractor)
can't silently break the text path that every existing session relies on.
"""
from __future__ import annotations

import pytest

from agent.artifacts import (
    Artifact,
    TextExtractor,
    UnsupportedModalityError,
    normalize_artifact,
    register_extractor,
    registered_modalities,
)


def test_text_extractor_handles_common_suffixes():
    ex = TextExtractor()
    for name in ["a.txt", "a.md", "a.csv", "a.json", "a.yaml", "a.log", "transcript"]:
        from pathlib import Path

        assert ex.can_handle(Path(name)), name
    from pathlib import Path

    assert not ex.can_handle(Path("a.pdf"))
    assert not ex.can_handle(Path("a.mp4"))


def test_normalize_text_file_produces_artifact(tmp_path):
    p = tmp_path / "call-transcript.txt"
    p.write_text("Customer: reports take 3 days.\nFDE: noted.")
    art = normalize_artifact(p)
    assert isinstance(art, Artifact)
    assert art.modality == "text"
    assert art.source_name == "call-transcript.txt"
    assert "reports take 3 days" in art.normalized_text
    # Plain text offers no pre-segmented structure beyond the prose.
    assert art.structured_observations == []
    assert art.provenance_units == []


def test_extensionless_file_is_text(tmp_path):
    p = tmp_path / "pasted_notes"
    p.write_text("some pasted meeting notes")
    art = normalize_artifact(p)
    assert art.modality == "text"
    assert art.normalized_text == "some pasted meeting notes"


def test_unsupported_modality_raises_actionable_error(tmp_path):
    p = tmp_path / "deck.pdf"
    p.write_bytes(b"%PDF-1.7 binary junk")
    with pytest.raises(UnsupportedModalityError) as ei:
        normalize_artifact(p)
    msg = str(ei.value)
    # The message must tell the user what to do, not just that it failed.
    assert "deck.pdf" in msg
    assert "extractor" in msg.lower()


def test_binary_content_in_text_suffix_raises(tmp_path):
    """A file that claims a text suffix but holds undecodable bytes is the old
    'binary file?' case — now surfaced as UnsupportedModalityError, not a raw
    UnicodeDecodeError."""
    p = tmp_path / "weird.txt"
    p.write_bytes(b"\xff\xfe\x00\x01\x02 not utf-8 \x80\x81")
    with pytest.raises(UnsupportedModalityError):
        normalize_artifact(p)


def test_register_new_modality_extractor(tmp_path):
    """Adding a modality is implementing one extractor + registering it — the
    seam's whole purpose. Verify a registered extractor takes effect and that
    `front=True` gives it priority over the generic text extractor."""

    class FakeEventsExtractor:
        modality = "events"

        def can_handle(self, path):
            return path.suffix.lower() == ".ndjson"

        def extract(self, path):
            return Artifact(
                source_name=path.name,
                modality="events",
                normalized_text="rendered events",
                structured_observations=[{"event": "click", "t": "0:01"}],
                provenance_units=[{"id": "evt_0", "locator": "0:01"}],
            )

    register_extractor(FakeEventsExtractor())
    assert "events" in registered_modalities()

    p = tmp_path / "stream.ndjson"
    p.write_text('{"event":"click"}')
    art = normalize_artifact(p)
    assert art.modality == "events"
    # A rich modality contributes structured_observations + provenance_units,
    # not just flattened text.
    assert art.structured_observations == [{"event": "click", "t": "0:01"}]
    assert art.provenance_units == [{"id": "evt_0", "locator": "0:01"}]
