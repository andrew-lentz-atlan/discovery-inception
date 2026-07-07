"""Partial-failure tolerance contract of `step_scaffold_writer`.

The scaffold step runs 5 LLM sub-steps (5a skill MDs × N, 5b orchestrator,
5c design rationale, 5d eval seed, 5f architecture diagram) in one
`asyncio.gather(return_exceptions=True)`, then 5e (judge) sequentially.
The contract under test: any single sub-step failing must NOT tank the
others — the successful artifacts still land on disk, a fallback is written
where one exists, and the failure is surfaced in `scaffold_errors` + the
return dict. meta/ (6 deterministic artifacts) is written BEFORE any LLM
sub-step so even a crash preserves the four upstream decisions.

All LLM sub-steps are monkeypatched as module globals on agent.inception.run
(they resolve at call time inside step_scaffold_writer) — no LLM calls.
"""
from __future__ import annotations

import json

import pytest

import agent.inception.run as run_mod
from agent.inception.run import step_scaffold_writer

from conftest import (
    FakeClient,
    make_architecture,
    make_architecture_diagram,
    make_design_rationale,
    make_eval_seed,
    make_judge_harness,
    make_orchestrator_stub,
    make_runtime,
    make_skill_md,
    make_skill_proposal,
    make_workload,
)

# The full return-dict shape of step_scaffold_writer. Asserted in every
# non-crashing test so a key rename/removal breaks loudly here.
EXPECTED_KEYS = {
    "output_dir",
    "skills_written",
    "orchestrator_filename",
    "imports_needed",
    "env_vars_needed",
    "rationale_length",
    "eval_questions",
    "judge_dimensions",
    "judge_generation_error",
    "architecture_diagram_generated",
    "scaffold_errors",
    "meta_artifacts",
}

META_FILES = {
    "01_workload_classification.json",
    "02_skill_proposal.json",
    "03_architecture_proposal.json",
    "04_runtime_proposal.json",
    "spec_consumed.md",
    "role_context_consumed.json",
}


def _patch_generators(
    monkeypatch,
    *,
    fail_skill_md_for: set[str] = frozenset(),
    fail_orchestrator: bool = False,
    fail_rationale: bool = False,
    fail_eval_seed: bool = False,
    fail_diagram: bool = False,
    fail_judge: bool = False,
):
    """Install all six generator fakes on the run module. Each either returns
    a minimal valid model or raises, per the flags."""

    async def fake_skill_md(client, skill, workload, architecture, runtime, role_context_json):
        if skill.name in fail_skill_md_for:
            raise ValueError(f"boom in skill_md for {skill.name}")
        return make_skill_md(skill.name)

    async def fake_orchestrator(client, skills, architecture, runtime):
        if fail_orchestrator:
            raise ValueError("boom in orchestrator stub")
        return make_orchestrator_stub()

    async def fake_rationale(client, workload, skills, architecture, runtime, spec_md):
        if fail_rationale:
            raise ValueError("boom in design rationale")
        return make_design_rationale()

    async def fake_eval_seed(client, workload, skills, architecture, spec_md, role_context_json):
        if fail_eval_seed:
            raise ValueError("boom in eval seed")
        return make_eval_seed()

    async def fake_diagram(client, workload, skills, architecture, runtime):
        if fail_diagram:
            raise ValueError("boom in diagram")
        return make_architecture_diagram()

    async def fake_judge(client, workload, skills, runtime, eval_seed, role_context_json):
        if fail_judge:
            raise ValueError("boom in judge")
        return make_judge_harness()

    monkeypatch.setattr(run_mod, "step_generate_skill_md", fake_skill_md)
    monkeypatch.setattr(run_mod, "step_generate_orchestrator_stub", fake_orchestrator)
    monkeypatch.setattr(run_mod, "step_generate_design_rationale", fake_rationale)
    monkeypatch.setattr(run_mod, "step_generate_eval_seed", fake_eval_seed)
    monkeypatch.setattr(run_mod, "step_generate_architecture_diagram", fake_diagram)
    monkeypatch.setattr(run_mod, "step_generate_judge_harness", fake_judge)


async def _run(tmp_path, skill_names=("parse_question", "analyze_share")):
    return await step_scaffold_writer(
        FakeClient(),
        make_workload(),
        make_skill_proposal(skill_names),
        make_architecture(),
        make_runtime(),
        spec_md="# spec\n",
        role_context_json="{}",
        output_dir=tmp_path,
    )


# ---------------------------------------------------------------------------
# (a) Happy path — everything lands
# ---------------------------------------------------------------------------


async def test_happy_path_writes_everything(tmp_path, monkeypatch):
    _patch_generators(monkeypatch)
    result = await _run(tmp_path)

    assert set(result) == EXPECTED_KEYS
    assert result["scaffold_errors"] == []
    assert result["judge_generation_error"] is None
    assert result["architecture_diagram_generated"] is True
    assert result["skills_written"] == ["parse_question", "analyze_share"]
    assert result["orchestrator_filename"] == "orchestrator.py"
    assert result["eval_questions"] == 1
    assert result["judge_dimensions"] == ["accuracy"]
    assert result["meta_artifacts"] == 6

    # Per-skill SKILL.md
    assert (tmp_path / "skills" / "parse_question" / "SKILL.md").exists()
    assert (tmp_path / "skills" / "analyze_share" / "SKILL.md").exists()
    # Top-level artifacts
    assert (tmp_path / "orchestrator.py").read_text() == "# generated orchestrator\n"
    assert (tmp_path / "design_rationale.md").read_text() == "# design rationale\n"
    assert (tmp_path / "architecture.md").exists()
    assert "```mermaid" in (tmp_path / "architecture.md").read_text()
    assert (tmp_path / "README.md").exists()
    # Eval pair
    questions = json.loads((tmp_path / "eval" / "questions.json").read_text())
    assert len(questions["questions"]) == 1
    assert (tmp_path / "eval" / "judge.py").read_text() == "# generated judge\n"
    # meta/ — the 6 deterministic pre-LLM artifacts
    assert {p.name for p in (tmp_path / "meta").iterdir()} == META_FILES


# ---------------------------------------------------------------------------
# (b) Orchestrator stub fails → fallback written, everything else intact
# ---------------------------------------------------------------------------


async def test_orchestrator_failure_writes_fallback_others_intact(tmp_path, monkeypatch):
    _patch_generators(monkeypatch, fail_orchestrator=True)
    result = await _run(tmp_path)

    assert set(result) == EXPECTED_KEYS
    # Fallback orchestrator.py still exists. NOTE: the console message says
    # "wrote stub with TODO" but the fallback file contains no literal "TODO"
    # string — it declares the failure in its docstring and raises
    # NotImplementedError on import. Asserting the actual content.
    fallback = (tmp_path / "orchestrator.py").read_text()
    assert "NotImplementedError" in fallback
    assert "LLM generation failed" in fallback
    assert "boom in orchestrator stub" in fallback

    assert len(result["scaffold_errors"]) == 1
    assert "orchestrator.py" in result["scaffold_errors"][0]
    assert result["orchestrator_filename"] == "(generation failed; see stub)"
    assert result["imports_needed"] == []

    # Every OTHER artifact still landed
    assert (tmp_path / "skills" / "parse_question" / "SKILL.md").exists()
    assert (tmp_path / "skills" / "analyze_share" / "SKILL.md").exists()
    assert (tmp_path / "design_rationale.md").exists()
    assert (tmp_path / "eval" / "questions.json").exists()
    assert (tmp_path / "eval" / "judge.py").exists()
    assert (tmp_path / "architecture.md").exists()
    assert (tmp_path / "README.md").exists()


# ---------------------------------------------------------------------------
# (c) Design rationale fails → fallback path CRASHES (documented bug)
# ---------------------------------------------------------------------------


async def test_design_rationale_failure_degrades_gracefully(tmp_path, monkeypatch):
    """When step 5c fails, `_write_design_rationale_fallback` writes a
    deterministic design_rationale.md from the upstream Pydantic outputs and the
    REST of the scaffold completes. (This test originally documented a bug: the
    fallback writer read three stale field names — `skill_type`,
    `architecture.rationale`, `runtime.rationale` — raising AttributeError and
    tanking the whole scaffold. Fixed to `suggested_body_shape` /
    `selection_rationale`; this now asserts the graceful contract.)"""
    _patch_generators(monkeypatch, fail_rationale=True)

    result = await _run(tmp_path)

    # Fallback rationale written from upstream data; failure surfaced.
    fallback = (tmp_path / "design_rationale.md").read_text()
    assert "single-agent-react" in fallback
    assert any("design_rationale" in e for e in result["scaffold_errors"])
    # Nothing else is lost: meta/, prior sub-steps, and everything sequenced
    # after the 5c branch all still land.
    assert {p.name for p in (tmp_path / "meta").iterdir()} == META_FILES
    assert (tmp_path / "skills" / "parse_question" / "SKILL.md").exists()
    assert (tmp_path / "orchestrator.py").exists()
    assert (tmp_path / "eval" / "questions.json").exists()
    assert (tmp_path / "architecture.md").exists()
    assert (tmp_path / "README.md").exists()


# ---------------------------------------------------------------------------
# (d) Eval seed fails → judge harness skipped gracefully, no crash
# ---------------------------------------------------------------------------


async def test_eval_seed_failure_skips_judge_gracefully(tmp_path, monkeypatch):
    _patch_generators(monkeypatch, fail_eval_seed=True)
    result = await _run(tmp_path)

    assert set(result) == EXPECTED_KEYS
    assert result["eval_questions"] == 0
    assert result["judge_dimensions"] == []
    assert result["judge_generation_error"] is not None
    assert "skipped" in result["judge_generation_error"]

    # Both eval failures recorded: 5d itself + the 5e skip it caused.
    joined = "\n".join(result["scaffold_errors"])
    assert "eval/questions.json" in joined
    assert "eval/judge.py" in joined
    assert len(result["scaffold_errors"]) == 2

    # Neither eval artifact written (the skip branch writes no judge stub).
    assert not (tmp_path / "eval" / "questions.json").exists()
    assert not (tmp_path / "eval" / "judge.py").exists()

    # The rest of the scaffold is intact.
    assert (tmp_path / "skills" / "parse_question" / "SKILL.md").exists()
    assert (tmp_path / "orchestrator.py").exists()
    assert (tmp_path / "design_rationale.md").exists()
    assert (tmp_path / "architecture.md").exists()
    assert (tmp_path / "README.md").exists()


# ---------------------------------------------------------------------------
# (e) One skill_md fails among several → per-skill tolerance
# ---------------------------------------------------------------------------


async def test_one_skill_md_failure_isolated_from_siblings(tmp_path, monkeypatch):
    _patch_generators(monkeypatch, fail_skill_md_for={"bad_skill"})
    result = await _run(tmp_path, skill_names=("good_a", "bad_skill", "good_b"))

    assert set(result) == EXPECTED_KEYS
    assert result["skills_written"] == ["good_a", "good_b"]

    assert (tmp_path / "skills" / "good_a" / "SKILL.md").exists()
    assert (tmp_path / "skills" / "good_b" / "SKILL.md").exists()
    assert not (tmp_path / "skills" / "bad_skill").exists()

    assert len(result["scaffold_errors"]) == 1
    assert "skills/bad_skill/SKILL.md" in result["scaffold_errors"][0]
    assert "boom in skill_md for bad_skill" in result["scaffold_errors"][0]

    # Failure of one skill didn't disturb the rest of the scaffold.
    assert result["judge_generation_error"] is None
    assert (tmp_path / "orchestrator.py").exists()
    assert (tmp_path / "eval" / "judge.py").exists()
