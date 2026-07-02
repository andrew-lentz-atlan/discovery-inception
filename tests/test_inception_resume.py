"""Resume-from-checkpoint back-compat + cascade invalidation.

Two contracts under test:

1. `_try_resume_step` degrades gracefully: absent file → None; corrupt JSON or a
   stale-schema checkpoint (e.g. a meta/02 written before `atlan_context_layer`
   became required) → None WITH a printed warning (the caller pays for a fresh
   LLM call and should know why) — never a crash.

2. The cascade rule in `run_inception`: once ANY step runs fresh, every
   downstream step must also run fresh — even if its own checkpoint is valid.
   Without it, a stale meta/02 re-runs fresh while 03/04 resume from proposals
   derived from the OLD skill cut → an internally inconsistent starter, silently.
"""
import json

import agent.inception.run as run_mod
from agent.inception.run import _try_resume_step, run_inception
from agent.inception.schemas import (
    ArchitectureProposal,
    AtlanContextLayer,
    RuntimeProposal,
    SkillProposalResult,
    WorkloadClassification,
)


def _wl() -> WorkloadClassification:
    return WorkloadClassification(
        interaction_shape="conversational",
        latency_sensitivity="tolerant",
        decision_complexity="judgment-heavy",
        data_intensity="light",
        multi_step_or_single_step="multi",
        state_shape="session-scoped",
        confidence=0.8,
        rationale="test",
    )


def _sp() -> SkillProposalResult:
    return SkillProposalResult(
        skills=[],
        rationale="r",
        granularity_argument="g",
        atlan_context_layer=AtlanContextLayer(repo_recommendation="repo", rationale="r"),
    )


def _ap() -> ArchitectureProposal:
    return ArchitectureProposal(
        selected_pattern_slug="single-agent-react",
        selected_pattern_title="Single-Agent ReAct",
        selection_rationale="r",
        confidence=0.8,
    )


def _rp() -> RuntimeProposal:
    return RuntimeProposal(
        selected_runtime="LangGraph",
        selected_model_family="claude-haiku-4-5",
        selection_rationale="r",
        confidence=0.8,
    )


# The shape meta/02_skill_proposal.json had BEFORE atlan_context_layer was added.
OLD_SCHEMA_02 = {
    "skills": [],
    "orchestrator_level_concerns": [],
    "rationale": "old",
    "granularity_argument": "old",
}


# ---------------------------------------------------------------------------
# 1. _try_resume_step matrix
# ---------------------------------------------------------------------------


def test_resume_none_output_dir():
    assert _try_resume_step(None, "01_workload_classification.json", WorkloadClassification) is None


def test_resume_absent_file_silent(tmp_path, capsys):
    assert _try_resume_step(tmp_path, "01_workload_classification.json", WorkloadClassification) is None
    assert "failed to load" not in capsys.readouterr().out


def test_resume_corrupt_json_warns(tmp_path, capsys):
    (tmp_path / "meta").mkdir()
    (tmp_path / "meta" / "01_workload_classification.json").write_text("{not json")
    assert _try_resume_step(tmp_path, "01_workload_classification.json", WorkloadClassification) is None
    assert "failed to load" in capsys.readouterr().out


def test_resume_stale_schema_warns_not_crashes(tmp_path, capsys):
    (tmp_path / "meta").mkdir()
    (tmp_path / "meta" / "02_skill_proposal.json").write_text(json.dumps(OLD_SCHEMA_02))
    assert _try_resume_step(tmp_path, "02_skill_proposal.json", SkillProposalResult) is None
    out = capsys.readouterr().out
    assert "failed to load" in out and "re-running" in out


def test_resume_valid_checkpoint_loads(tmp_path):
    (tmp_path / "meta").mkdir()
    (tmp_path / "meta" / "02_skill_proposal.json").write_text(_sp().model_dump_json())
    loaded = _try_resume_step(tmp_path, "02_skill_proposal.json", SkillProposalResult)
    assert isinstance(loaded, SkillProposalResult)
    assert loaded.atlan_context_layer.repo_recommendation == "repo"


# ---------------------------------------------------------------------------
# 2. Cascade invalidation in run_inception
# ---------------------------------------------------------------------------


class _FakeClient:
    async def close(self):
        pass


def _patch_steps(monkeypatch, calls: list[str]):
    async def fake_wl(*a, **k):
        calls.append("workload_classifier")
        return _wl()

    async def fake_sp(*a, **k):
        calls.append("skill_proposer")
        return _sp()

    async def fake_ap(*a, **k):
        calls.append("architecture_proposer")
        return _ap()

    async def fake_rp(*a, **k):
        calls.append("runtime_proposer")
        return _rp()

    async def fake_scaffold(*a, **k):
        calls.append("scaffold_writer")
        return {"output_dir": "fake", "skills_written": []}

    monkeypatch.setattr(run_mod, "step_workload_classifier", fake_wl)
    monkeypatch.setattr(run_mod, "step_skill_proposer", fake_sp)
    monkeypatch.setattr(run_mod, "step_architecture_proposer", fake_ap)
    monkeypatch.setattr(run_mod, "step_runtime_proposer", fake_rp)
    monkeypatch.setattr(run_mod, "step_scaffold_writer", fake_scaffold)
    monkeypatch.setattr(run_mod, "_client", lambda: _FakeClient())


def _write_meta(tmp_path, *, stale_02: bool):
    meta = tmp_path / "meta"
    meta.mkdir()
    (meta / "01_workload_classification.json").write_text(_wl().model_dump_json())
    (meta / "02_skill_proposal.json").write_text(
        json.dumps(OLD_SCHEMA_02) if stale_02 else _sp().model_dump_json()
    )
    (meta / "03_architecture_proposal.json").write_text(_ap().model_dump_json())
    (meta / "04_runtime_proposal.json").write_text(_rp().model_dump_json())


async def test_stale_02_cascades_to_downstream_fresh_runs(tmp_path, monkeypatch):
    """Valid 01/03/04 + stale 02: step 1 resumes; 2 runs fresh; 3 and 4 must
    ALSO run fresh (cascade) even though their own checkpoints are valid."""
    calls: list[str] = []
    _patch_steps(monkeypatch, calls)
    _write_meta(tmp_path, stale_02=True)

    await run_inception("spec", "{}", output_dir=tmp_path)

    assert calls == [
        "skill_proposer",       # 02 stale → fresh
        "architecture_proposer",  # cascade: valid checkpoint IGNORED
        "runtime_proposer",       # cascade: valid checkpoint IGNORED
        "scaffold_writer",
    ]


async def test_all_valid_checkpoints_resume_everything(tmp_path, monkeypatch):
    """Control: with all 4 checkpoints valid, no decision step re-runs."""
    calls: list[str] = []
    _patch_steps(monkeypatch, calls)
    _write_meta(tmp_path, stale_02=False)

    await run_inception("spec", "{}", output_dir=tmp_path)

    assert calls == ["scaffold_writer"]


async def test_force_fresh_reruns_everything(tmp_path, monkeypatch):
    calls: list[str] = []
    _patch_steps(monkeypatch, calls)
    _write_meta(tmp_path, stale_02=False)

    await run_inception("spec", "{}", output_dir=tmp_path, force_fresh=True)

    assert calls == [
        "workload_classifier",
        "skill_proposer",
        "architecture_proposer",
        "runtime_proposer",
        "scaffold_writer",
    ]
