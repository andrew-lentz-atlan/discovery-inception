"""Gating / threading / oracle-parity for the LangGraph inception adapter.

agent/inception/graph.py is the LangGraph adapter over the SAME step_*
contract run.py's hand-rolled `run_inception` orchestrates. Three things
must hold for the A/B (findings/10) to stay meaningful:

  1. Gating parity — scaffold runs iff output_dir is set (conditional edge
     after `runtime`), and the decision nodes run in the oracle's order.
  2. Threading — the scaffold node receives the SAME objects the upstream
     nodes produced (identity, not copies), plus the caller's output_dir.
  3. Return-shape parity — run_inception_graph's dict keys match
     run_inception's steps-1-4 contract exactly (drop-in replacement).

Step fns are monkeypatched on agent.inception.graph — the node closures
resolve them as module globals at call time.
"""
from __future__ import annotations

import agent.inception.graph as graph_mod
import agent.inception.run as run_mod
from agent.inception.graph import run_inception_graph
from agent.inception.run import run_inception
from agent.inception.schemas import PriorIterationFeedback

from conftest import (
    FakeClient,
    make_architecture,
    make_runtime,
    make_skill_proposal,
    make_workload,
)


def _patch_graph_steps(monkeypatch, calls: list[str], captured: dict):
    """Install fakes on the graph module. Returns the singleton upstream
    objects so tests can assert identity threading."""
    wl = make_workload()
    sp = make_skill_proposal(("skill_a",))
    ap = make_architecture()
    rp = make_runtime()
    scaffold_summary = {"output_dir": "fake", "skills_written": ["skill_a"]}

    async def fake_wl(client, spec_md, role_context_json, **kwargs):
        calls.append("classify")
        captured["classify"] = kwargs
        return wl

    async def fake_sp(client, classification, spec_md, role_context_json, **kwargs):
        calls.append("skills")
        captured["skills"] = kwargs
        return sp

    async def fake_ap(client, classification, proposal, **kwargs):
        calls.append("architecture")
        captured["architecture"] = kwargs
        return ap

    async def fake_rp(client, classification, proposal, architecture, **kwargs):
        calls.append("runtime")
        captured["runtime"] = kwargs
        return rp

    async def fake_scaffold(client, workload, skills, architecture, runtime, **kwargs):
        calls.append("scaffold")
        captured["scaffold"] = {
            "workload": workload,
            "skills": skills,
            "architecture": architecture,
            "runtime": runtime,
            **kwargs,
        }
        return scaffold_summary

    monkeypatch.setattr(graph_mod, "step_workload_classifier", fake_wl)
    monkeypatch.setattr(graph_mod, "step_skill_proposer", fake_sp)
    monkeypatch.setattr(graph_mod, "step_architecture_proposer", fake_ap)
    monkeypatch.setattr(graph_mod, "step_runtime_proposer", fake_rp)
    monkeypatch.setattr(graph_mod, "step_scaffold_writer", fake_scaffold)
    monkeypatch.setattr(graph_mod, "_client", lambda: FakeClient())
    return wl, sp, ap, rp, scaffold_summary


# ---------------------------------------------------------------------------
# (a) No output_dir → decisions only, no scaffold node
# ---------------------------------------------------------------------------


async def test_no_output_dir_runs_decisions_only_in_order(monkeypatch):
    calls: list[str] = []
    _patch_graph_steps(monkeypatch, calls, {})

    result = await run_inception_graph("spec", "{}")

    assert calls == ["classify", "skills", "architecture", "runtime"]
    assert result["scaffold_output"] is None
    assert "steps 1-4" in result["next_step"]


# ---------------------------------------------------------------------------
# (b) output_dir set → scaffold called with the SAME upstream objects
# ---------------------------------------------------------------------------


async def test_output_dir_threads_upstream_objects_into_scaffold(tmp_path, monkeypatch):
    calls: list[str] = []
    captured: dict = {}
    wl, sp, ap, rp, scaffold_summary = _patch_graph_steps(monkeypatch, calls, captured)

    result = await run_inception_graph("spec", "{}", output_dir=tmp_path)

    assert calls == ["classify", "skills", "architecture", "runtime", "scaffold"]
    # Identity, not equality — the exact objects the nodes produced must
    # thread through graph state into the scaffold call.
    got = captured["scaffold"]
    assert got["workload"] is wl
    assert got["skills"] is sp
    assert got["architecture"] is ap
    assert got["runtime"] is rp
    assert got["output_dir"] == tmp_path
    assert got["spec_md"] == "spec"
    assert got["role_context_json"] == "{}"

    assert result["scaffold_output"] is scaffold_summary
    assert "full pipeline" in result["next_step"]


# ---------------------------------------------------------------------------
# (c) Return-dict keys match run_inception's steps-1-4 contract exactly
# ---------------------------------------------------------------------------


async def test_return_shape_parity_with_oracle(monkeypatch):
    # Graph side
    _patch_graph_steps(monkeypatch, [], {})
    graph_result = await run_inception_graph("spec", "{}")

    # Oracle side — same fakes installed on the run module (the oracle's
    # own call-time globals), no output_dir → its steps-1-4 return path.
    async def fake_wl(*a, **k):
        return make_workload()

    async def fake_sp(*a, **k):
        return make_skill_proposal(("skill_a",))

    async def fake_ap(*a, **k):
        return make_architecture()

    async def fake_rp(*a, **k):
        return make_runtime()

    monkeypatch.setattr(run_mod, "step_workload_classifier", fake_wl)
    monkeypatch.setattr(run_mod, "step_skill_proposer", fake_sp)
    monkeypatch.setattr(run_mod, "step_architecture_proposer", fake_ap)
    monkeypatch.setattr(run_mod, "step_runtime_proposer", fake_rp)
    monkeypatch.setattr(run_mod, "_client", lambda: FakeClient())

    oracle_result = await run_inception("spec", "{}")

    expected = {
        "classification",
        "skill_proposal",
        "architecture_proposal",
        "runtime_proposal",
        "scaffold_output",
        "next_step",
    }
    assert set(graph_result) == expected
    assert set(oracle_result) == expected
    assert set(graph_result) == set(oracle_result)
    # Both dump the models — value-level parity for the decision payloads.
    for key in ("classification", "skill_proposal", "architecture_proposal", "runtime_proposal"):
        assert graph_result[key] == oracle_result[key]


# ---------------------------------------------------------------------------
# (d) prior_feedback + spec_structured forwarded to the step fns
# ---------------------------------------------------------------------------


async def test_feedback_and_digest_forwarded_to_steps(monkeypatch):
    calls: list[str] = []
    captured: dict = {}
    _patch_graph_steps(monkeypatch, calls, captured)

    pf = PriorIterationFeedback(iteration=1)
    digest = '{"bounded_context": {"terms": 12}}'

    await run_inception_graph(
        "spec", "{}", prior_feedback=pf, spec_structured=digest
    )

    # Steps 1-3 receive both; step 4 (runtime_proposer) has no
    # spec_structured parameter and must receive only prior_feedback.
    for step in ("classify", "skills", "architecture"):
        assert captured[step]["prior_feedback"] is pf, step
        assert captured[step]["spec_structured"] == digest, step
    assert captured["runtime"]["prior_feedback"] is pf
    assert "spec_structured" not in captured["runtime"]
