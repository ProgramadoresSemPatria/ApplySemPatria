"""Coverage for retrieval.pipeline.daily helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from retrieval.pipeline import daily as dp


def test_linkedin_steps_planned():
    assert dp._linkedin_steps_planned(table_only=True, skip_linkedin=False, skip_linkedin_jobs=False) is False
    assert dp._linkedin_steps_planned(table_only=False, skip_linkedin=True, skip_linkedin_jobs=True) is False
    assert dp._linkedin_steps_planned(table_only=False, skip_linkedin=False, skip_linkedin_jobs=True) is True


def test_linkedin_fatal_errors():
    errors = ["LinkedIn collect: timeout", "LinkedIn jobs: fail", "discover: x"]
    fatal = dp._linkedin_fatal_errors(errors, skip_linkedin=False, skip_linkedin_jobs=False)
    assert len(fatal) == 2


def test_resolve_python_prefers_venv(tmp_path, monkeypatch):
    venv_py = tmp_path / ".venv-test" / "bin" / "python"
    venv_py.parent.mkdir(parents=True)
    venv_py.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(dp, "ROOT", tmp_path)
    assert dp._resolve_python() == str(venv_py)


def test_run_step_success(monkeypatch):
    proc = MagicMock()
    proc.poll = MagicMock(side_effect=[0])
    proc.communicate = MagicMock(return_value=("ok\n", ""))
    proc.returncode = 0
    proc.returncode = 0
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: proc)
    monkeypatch.setattr(dp, "set_research_step", lambda *a, **k: None)
    monkeypatch.setattr(dp, "audit_info", lambda *a, **k: None)
    monkeypatch.setattr(dp, "audit_warn", lambda *a, **k: None)
    monkeypatch.setattr(dp, "STEP_HEARTBEAT_SEC", 9999)
    steps: list = []
    errors: list = []
    result = dp._run_step(["echo", "ok"], step_key="generate_table", steps=steps, errors=errors)
    assert result is not None


def test_run_daily_research_table_only(monkeypatch, tmp_path):
    monkeypatch.setattr(dp, "today_local", lambda: "2026-09-10")
    monkeypatch.setattr("table_paths.ensure_table_dirs", lambda: None)
    monkeypatch.setattr(dp, "audit_info", lambda *a, **k: None)
    monkeypatch.setattr("research_log.has_research", lambda _d: False)
    monkeypatch.setattr(dp, "join_research_run", lambda _d: None)
    monkeypatch.setattr(dp, "finish_research_run", lambda **k: None)
    monkeypatch.setattr(dp, "mark_research_day", lambda *a, **k: None)
    monkeypatch.setattr("track_readiness.ready_track_ids", lambda _op: ["ai-engineer"])
    monkeypatch.setattr("track_store.resolve_track", lambda t: t or "ai-engineer")
    out_md = tmp_path / "apps-2026-09-10.md"
    out_json = tmp_path / "apps-2026-09-10.json"
    out_json.write_text('{"jobs": []}', encoding="utf-8")
    monkeypatch.setattr("table_paths.applications_table_for_day", lambda day: out_md)
    monkeypatch.setattr("table_window.save_window_for_day", lambda day: None)
    monkeypatch.setattr("research_log.load_research_run", lambda: {})

    def mock_run_step(cmd, *, step_key, steps, errors, **kwargs):
        import subprocess

        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(dp, "_run_step", mock_run_step)
    result = dp.run_daily_research(table_only=True, skip_linkedin=True, skip_discover=True)
    assert result["ok"] is True
    assert result["day"] == "2026-09-10"
