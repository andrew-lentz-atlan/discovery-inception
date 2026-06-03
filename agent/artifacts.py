"""Artifact adapter seam — where new modalities plug in.

discovery-inception's semantic core is modality-agnostic: a DistilledFact
doesn't know or care whether it came from a transcript, a runbook, a screen
recording, or an event stream. But the I/O boundary used to be hard-coded to
`Path.read_text()` — UTF-8 text only, binary rejected. That made every new
modality a change to the intake pipeline instead of a change at the edge.

This module is the edge. It defines:

  - Artifact: the normalized contract everything becomes BEFORE intake runs.
    Every modality must produce `normalized_text` (the universal fallback the
    existing text pipeline already knows how to consume); rich modalities MAY
    additionally emit `structured_observations` (pre-segmented higher-signal
    output — e.g. workflow steps with timestamps from a screen recording) and
    `provenance_units` (locators back into the source — {clip_42, "t=14:03"}).

  - ArtifactExtractor: the per-modality adapter protocol. One extractor per
    modality. The text extractor (the only one implemented today) reads UTF-8
    and fills normalized_text. A future screen-recording extractor does the
    heavy lifting at the edge (transcription + OCR + frame captioning, likely
    delegated to dedicated services) and emits structured_observations — the
    core never grows a modality zoo.

  - a registry + normalize_artifact(path): dispatch a source to its extractor.

Adding a modality is: implement one ArtifactExtractor, register it. No change
to intake, fact extraction, or the fact-centric core. That's the whole point.

See docs/internal/research-log.md "Issue C" for the design rationale.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

# Modality is an open string, not a closed Literal, on purpose: registering a
# new extractor shouldn't require editing a type in this file. The text path
# is "text"; future ones are "audio", "video", "image", "events", "conversation".
Modality = str


class UnsupportedModalityError(Exception):
    """Raised when no registered extractor can handle a source.

    Carries a clear, action-oriented message — the failure mode a user hits
    when they pass a .pdf/.mp4 before the extractor for that modality exists.
    """


@dataclass
class Artifact:
    """A source normalized into the shape intake consumes.

    `normalized_text` is the universal fallback — every modality MUST produce
    it, and the existing text intake + fact-extraction pipeline runs on it
    unchanged. The optional fields are how a rich modality contributes more
    than a flattened transcript:

      structured_observations: pre-segmented, higher-signal output the extractor
        derived at the edge. Example for a screen recording: a list of
        {"step": "...", "screen": "...", "t": "14:03"} workflow steps. Intake
        can consume these directly when present (a richer extractor earns its
        keep here); when absent, intake just uses normalized_text. Kept as
        list[dict] for forward-compat — the shape is modality-specific and
        shouldn't be frozen into a closed schema yet.

      provenance_units: locators back into the source — [{"id": "clip_42",
        "locator": "t=14:03"}]. The fact extractor's per-fact `provenance_unit`
        is the fine-grained version; this is the artifact-level inventory of
        addressable units a rich modality exposes.
    """

    source_name: str
    modality: Modality
    normalized_text: str
    structured_observations: list[dict[str, Any]] = field(default_factory=list)
    provenance_units: list[dict[str, str]] = field(default_factory=list)


@runtime_checkable
class ArtifactExtractor(Protocol):
    """One adapter per modality. `can_handle` is the dispatch predicate;
    `extract` does the (possibly heavy, possibly delegated) normalization."""

    modality: str

    def can_handle(self, path: Path) -> bool: ...

    def extract(self, path: Path) -> Artifact: ...


class TextExtractor:
    """The only extractor implemented today. Reads UTF-8 text and fills
    normalized_text; emits no structured_observations (plain text has no
    pre-segmentation to offer beyond the prose itself).

    Handles the text-ish suffixes discovery already accepted, plus extensionless
    files (common for pasted transcripts). Binary files raise UnicodeDecodeError
    on read — normalize_artifact() maps that to a clear UnsupportedModalityError
    so the user learns "no extractor for this modality yet" rather than a stack
    trace.
    """

    modality = "text"
    TEXT_SUFFIXES = frozenset(
        {".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json",
         ".yaml", ".yml", ".log", ".text", ""}
    )

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() in self.TEXT_SUFFIXES

    def extract(self, path: Path) -> Artifact:
        text = path.read_text()  # UnicodeDecodeError on binary → caught by normalize_artifact
        return Artifact(
            source_name=path.name,
            modality=self.modality,
            normalized_text=text,
        )


# The registry. Append-only via register_extractor(); first matching extractor
# wins, so order = priority. Today: text only. A new modality is one entry here.
_REGISTRY: list[ArtifactExtractor] = [TextExtractor()]


def register_extractor(extractor: ArtifactExtractor, *, front: bool = False) -> None:
    """Register a new modality extractor. `front=True` gives it priority over
    extractors already registered (e.g. a specialized .csv extractor that
    should win over the generic TextExtractor for .csv)."""
    if front:
        _REGISTRY.insert(0, extractor)
    else:
        _REGISTRY.append(extractor)


def registered_modalities() -> list[str]:
    """The modalities the pipeline can currently ingest — for diagnostics."""
    return [ex.modality for ex in _REGISTRY]


def normalize_artifact(path: Path) -> Artifact:
    """Dispatch a source to the first extractor that can handle it.

    Raises UnsupportedModalityError with an actionable message when no
    registered extractor matches, or when the matching extractor fails to
    decode the source (the binary-file case the old pipeline rejected inline).
    """
    for extractor in _REGISTRY:
        if extractor.can_handle(path):
            try:
                return extractor.extract(path)
            except UnicodeDecodeError as exc:
                raise UnsupportedModalityError(
                    f"{path} matched the '{extractor.modality}' extractor but isn't "
                    f"valid {extractor.modality} (decode error: {exc}). If this is a "
                    f"PDF / docx / audio / video / image, there's no extractor for "
                    f"that modality yet — convert it to text first, or register an "
                    f"ArtifactExtractor for it (see agent/artifacts.py)."
                ) from exc
    raise UnsupportedModalityError(
        f"No artifact extractor registered for {path.name} (suffix "
        f"{path.suffix or '<none>'!r}). Registered modalities: "
        f"{', '.join(registered_modalities())}. Add an ArtifactExtractor for "
        f"this modality (see agent/artifacts.py) or convert the source to text."
    )
