"""Regression: LinkedIn collect must fail fast when headless browser is missing."""

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
    monkeypatch.setattr("research_log.today_local", lambda: "2026-09-10")
    monkeypatch.setattr("research_log.has_research", lambda _day: False)
    monkeypatch.setattr("track_readiness.ready_track_ids", lambda _op: ["ai-engineer"])
    monkeypatch.setattr("track_store.resolve_track", lambda t: t or "ai-engineer")
    monkeypatch.setattr("table_window.load_window", lambda: (datetime.now(TZ), datetime.now(TZ)))
    monkeypatch.setattr("table_window.save_window", lambda **_: None)
    md = tables / "applications-2026-09-10-full.md"
    monkeypatch.setattr("table_paths.applications_table_path", lambda: md)
    monkeypatch.setattr("table_paths.applications_table_for_day", lambda _day: md)
    return tmp_path


def test_missing_headless_browser_blocks_linkedin_before_collect(research_env, monkeypatch):
    from daily_research import run_daily_research
    from research_log import load_research_run

    calls: list[str] = []

    def mock_run_step(cmd, *, step_key, steps, errors, **kwargs):
        calls.append(step_key)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("daily_research._run_step", mock_run_step)
    monkeypatch.setattr("browser_session.headless_chromium_ready", lambda: False)

    result = run_daily_research(since="7d")
    assert result["ok"] is False
    assert "patchright install chromium" in result["message"]
    assert "linkedin_collect" not in calls
    assert "linkedin_jobs_collect" not in calls
    assert "discover:ai-engineer" not in calls
    assert load_research_run()["running"] is False


def test_table_only_skips_headless_browser_preflight(research_env, monkeypatch):
    from daily_research import run_daily_research

    calls: list[str] = []

    def mock_run_step(cmd, *, step_key, steps, errors, **kwargs):
        calls.append(step_key)
        if step_key == "generate_table":
            json_path = research_env / "applications" / "applications-2026-09-10-full.json"
            json_path.write_text('{"jobs": []}', encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("daily_research._run_step", mock_run_step)
    monkeypatch.setattr("browser_session.headless_chromium_ready", lambda: False)

    result = run_daily_research(table_only=True, since="7d")
    assert result["ok"] is True
    assert "generate_table" in calls
