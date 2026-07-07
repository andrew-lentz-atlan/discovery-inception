"""Routing + input-resolution contract of `tool_run_inception` (MCP server).

The tool is the user-facing dispatch layer over the two inception engines:
the hand-rolled oracle (`agent.inception.run.run_inception`, default) and
the LangGraph adapter (`agent.inception.graph.run_inception_graph`,
runtime="langgraph"). Under test — with both engines faked, no LLM:

  - engine routing + the `engine` field in the summary
  - default output_dir slug (role_id vs session_<sid>)
  - the finalize-first guard when spec.md is missing
  - malformed spec dict must NOT block inception (spec_structured
    degrades to None; the digest is additive, never required)

The tool imports the engines INSIDE the function body, so monkeypatching
them on their home modules (agent.inception.run / agent.inception.graph)
is what the call-time `from ... import ...` resolves.
"""
from __future__ import annotations

import json

import agent.inception.graph as graph_mod
import agent.inception.run as run_mod
import agent.mcp_server.server as srv

# Minimal result dict matching what the engines return for steps 1-4 —
# enough for tool_run_inception's summary builder (workload / architecture /
# runtime lines; scaffold_output None skips the scaffold summary block).
FAKE_RESULT = {
    "classification": {
        "interaction_shape": "conversational",
        "decision_complexity": "judgment-heavy",
        "data_intensity": "light",
    },
    "skill_proposal": {"skills": []},
    "architecture_proposal": {"selected_pattern_slug": "single-agent-react"},
    "runtime_proposal": {
        "selected_runtime": "LangGraph",
        "selected_model_family": "claude-haiku-4-5",
    },
    "scaffold_output": None,
    "next_step": "n/a",
}


def _patch_dirs(monkeypatch, tmp_path):
    sessions = tmp_path / "sessions"
    skills = tmp_path / "skills"
    sessions.mkdir()
    skills.mkdir()
    monkeypatch.setattr(srv, "SESSIONS_DIR", sessions)
    monkeypatch.setattr(srv, "SKILLS_DIR", skills)
    return sessions, skills


def _patch_engines(monkeypatch):
    """Fake both engines; record the kwargs each was called with."""
    calls: dict[str, list[dict]] = {"python": [], "langgraph": []}

    async def fake_run_inception(**kwargs):
        calls["python"].append(kwargs)
        return dict(FAKE_RESULT)

    async def fake_run_inception_graph(**kwargs):
        calls["langgraph"].append(kwargs)
        return dict(FAKE_RESULT)

    monkeypatch.setattr(run_mod, "run_inception", fake_run_inception)
    monkeypatch.setattr(graph_mod, "run_inception_graph", fake_run_inception_graph)
    return calls


def _write_session(sessions_dir, sid, spec: dict, *, spec_md: bool = True):
    sdir = sessions_dir / sid
    sdir.mkdir()
    if spec_md:
        (sdir / "spec.md").write_text("# spec brief\n")
    (sdir / "session.json").write_text(json.dumps({"session_id": sid, "spec": spec}))
    return sdir


# ---------------------------------------------------------------------------
# (a) default runtime → oracle engine
# ---------------------------------------------------------------------------


async def test_default_runtime_dispatches_to_python_oracle(tmp_path, monkeypatch):
    sessions, _ = _patch_dirs(monkeypatch, tmp_path)
    calls = _patch_engines(monkeypatch)
    _write_session(sessions, "sess_a", {"use_case_seed": "brand analytics"})

    res = await srv.tool_run_inception("sess_a")

    assert res["ok"] is True
    assert res["engine"] == "python"
    assert len(calls["python"]) == 1
    assert calls["langgraph"] == []

    kwargs = calls["python"][0]
    assert kwargs["spec_md"] == "# spec brief\n"
    assert kwargs["force_fresh"] is False
    assert kwargs["prior_feedback"] is None
    # A well-formed spec dict produces a structured digest string (here the
    # no-extra-signal sentinel, since the spec has no bounded_context).
    assert isinstance(kwargs["spec_structured"], str)

    # Summary lines assembled from the engine result
    assert res["workload"] == "conversational / judgment-heavy / light"
    assert res["architecture"] == "single-agent-react"
    assert res["runtime"] == "LangGraph + claude-haiku-4-5"
    # No role_id and no priors on disk → stub role context, flagged as such.
    assert "stub" in res["role_context_source"]


# ---------------------------------------------------------------------------
# (b) runtime="langgraph" → graph engine
# ---------------------------------------------------------------------------


async def test_langgraph_runtime_dispatches_to_graph_adapter(tmp_path, monkeypatch):
    sessions, _ = _patch_dirs(monkeypatch, tmp_path)
    calls = _patch_engines(monkeypatch)
    _write_session(sessions, "sess_b", {"use_case_seed": "x"})

    res = await srv.tool_run_inception("sess_b", runtime="langgraph")

    assert res["ok"] is True
    assert res["engine"] == "langgraph"
    assert len(calls["langgraph"]) == 1
    assert calls["python"] == []
    # The graph adapter has no force_fresh (no resume yet) — not forwarded.
    assert "force_fresh" not in calls["langgraph"][0]


# ---------------------------------------------------------------------------
# (c) default output_dir slug
# ---------------------------------------------------------------------------


async def test_default_output_dir_uses_role_id_slug(tmp_path, monkeypatch):
    sessions, _ = _patch_dirs(monkeypatch, tmp_path)
    calls = _patch_engines(monkeypatch)
    _write_session(sessions, "sess_c", {"use_case_seed": "x", "role_id": "brand_analyst"})

    res = await srv.tool_run_inception("sess_c")

    out = calls["python"][0]["output_dir"]
    assert out.parts[-2:] == ("agent_starter", "brand_analyst")
    assert res["output_dir"] == str(out)


async def test_default_output_dir_falls_back_to_session_slug(tmp_path, monkeypatch):
    sessions, _ = _patch_dirs(monkeypatch, tmp_path)
    calls = _patch_engines(monkeypatch)
    _write_session(sessions, "sess_d", {"use_case_seed": "x"})  # no role_id

    res = await srv.tool_run_inception("sess_d")

    out = calls["python"][0]["output_dir"]
    assert out.parts[-2:] == ("agent_starter", "session_sess_d")
    assert res["output_dir"] == str(out)


async def test_explicit_output_dir_is_respected(tmp_path, monkeypatch):
    sessions, _ = _patch_dirs(monkeypatch, tmp_path)
    calls = _patch_engines(monkeypatch)
    _write_session(sessions, "sess_e", {"use_case_seed": "x", "role_id": "brand_analyst"})
    explicit = str(tmp_path / "elsewhere")

    res = await srv.tool_run_inception("sess_e", output_dir=explicit)

    assert str(calls["python"][0]["output_dir"]) == explicit
    assert res["output_dir"] == explicit


# ---------------------------------------------------------------------------
# (d) missing spec.md → finalize-first guard
# ---------------------------------------------------------------------------


async def test_missing_spec_md_errors_pointing_at_finalize(tmp_path, monkeypatch):
    sessions, _ = _patch_dirs(monkeypatch, tmp_path)
    calls = _patch_engines(monkeypatch)
    _write_session(sessions, "sess_f", {"use_case_seed": "x"}, spec_md=False)

    res = await srv.tool_run_inception("sess_f")

    assert res["ok"] is False
    assert "finalize" in res["error"]
    # Neither engine ran.
    assert calls["python"] == [] and calls["langgraph"] == []


# ---------------------------------------------------------------------------
# (e) malformed spec dict → inception still runs, digest degrades to None
# ---------------------------------------------------------------------------


async def test_malformed_spec_does_not_block_inception(tmp_path, monkeypatch, capsys):
    sessions, _ = _patch_dirs(monkeypatch, tmp_path)
    calls = _patch_engines(monkeypatch)
    # `topics` must be a list — this fails DiscoverySpec.model_validate but
    # still supports the .get() reads (role_id / use_case_seed).
    _write_session(
        sessions,
        "sess_g",
        {"use_case_seed": "x", "role_id": "brand_analyst", "topics": "not-a-list"},
    )

    res = await srv.tool_run_inception("sess_g")

    assert res["ok"] is True
    assert len(calls["python"]) == 1
    # The digest is additive: malformed structured spec → None, never a block.
    assert calls["python"][0]["spec_structured"] is None
    assert "could not build structured spec digest" in capsys.readouterr().out
