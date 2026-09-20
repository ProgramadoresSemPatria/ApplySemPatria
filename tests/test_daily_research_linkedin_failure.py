"""Regression: LinkedIn collect failure must not mark research as successful."""

from __future__ import annotations

import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

TZ = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def research_env(tmp_path, monkeypatch):
    log = tmp_path / "state" / "research-log.json"
    run = tmp_path / "state" / "research-run.json"
    tables = tmp_path / "applications"
    tables.mkdir(parents=True)
    monkeypatch.setattr("research_log.LOG_PATH", log)
    monkeypatch.setattr("research_log.RUN_PATH", run)
    monkeypatch.setattr("research_log.ROOT", tmp_path)
    monkeypatch.setattr("table_paths.APPLICATIONS_TABLES_DIR", tables)
    monkeypatch.setattr("research_log.today_local", lambda: "2026-09-20")
    monkeypatch.setattr("research_log.has_research", lambda _day: False)
    monkeypatch.setattr("track_readiness.ready_track_ids", lambda _op: ["ai-engineer"])
    monkeypatch.setattr("track_store.resolve_track", lambda t: t or "ai-engineer")
    md = tables / "applications-2026-09-20-full.md"
    monkeypatch.setattr("table_paths.applications_table_for_day", lambda _day: md)
    monkeypatch.setattr("table_paths.applications_table_path", lambda: md)
    win = tmp_path / "state" / "table-window.json"
    monkeypatch.setattr("table_window.WINDOW_PATH", win)
    return tmp_path


def test_linkedin_collect_failure_marks_research_failed(research_env, monkeypatch):
    from daily_research import run_daily_research
    from research_log import has_research, load_research_run

    def mock_run_step(cmd, *, step_key, steps, errors, **kwargs):
        if step_key == "linkedin_collect":
            return subprocess.CompletedProcess(
                cmd,
                1,
                stdout="",
                stderr="patchright install chromium",
            )
        if step_key == "generate_table":
            json_path = research_env / "applications" / "applications-2026-09-20-full.json"
            json_path.write_text('{"jobs": [{"job_key": "x"}]}', encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("daily_research._run_step", mock_run_step)
    monkeypatch.setattr("browser_session.headless_chromium_ready_for_collect", lambda: True)

    result = run_daily_research(since="2026-09-16T14:09:31-03:00")
    assert result["ok"] is False
    assert "LinkedIn ingestion did not complete" in result["message"]
    assert "LinkedIn collect:" in result["message"]
    assert has_research("2026-09-20") is False
    run = load_research_run()
    assert run["running"] is False
    assert run["ok"] is False
    assert run["step"] == "failed"


def test_linkedin_jobs_failure_marks_research_failed(research_env, monkeypatch):
    from daily_research import run_daily_research
    from research_log import has_research

    def mock_run_step(cmd, *, step_key, steps, errors, **kwargs):
        if step_key == "linkedin_jobs_collect":
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="Executable doesn't exist")
        if step_key == "generate_table":
            json_path = research_env / "applications" / "applications-2026-09-20-full.json"
            json_path.write_text('{"jobs": []}', encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("daily_research._run_step", mock_run_step)
    monkeypatch.setattr("browser_session.headless_chromium_ready_for_collect", lambda: True)

    result = run_daily_research(since="2026-09-16T14:09:31-03:00")
    assert result["ok"] is False
    assert "LinkedIn jobs:" in result["message"]
    assert has_research("2026-09-20") is False
