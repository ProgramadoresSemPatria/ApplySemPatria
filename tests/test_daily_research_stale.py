"""Regression: stuck research runs must not block today's ingestion."""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
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
    monkeypatch.setattr("research_log.STALE_RUN_MINUTES", 1)
    monkeypatch.setattr("table_paths.APPLICATIONS_TABLES_DIR", tables)
    monkeypatch.setattr("research_log.today_local", lambda: "2026-09-09")
    monkeypatch.setattr("research_log.has_research", lambda _day: False)
    monkeypatch.setattr("track_readiness.ready_track_ids", lambda _op: ["ai-engineer"])
    monkeypatch.setattr("track_store.resolve_track", lambda t: t or "ai-engineer")
    monkeypatch.setattr("table_window.load_window", lambda: (datetime.now(TZ), datetime.now(TZ)))
    monkeypatch.setattr("table_window.save_window", lambda **_: None)
    md = tables / "applications-2026-09-09-full.md"
    monkeypatch.setattr("table_paths.applications_table_path", lambda: md)
    monkeypatch.setattr("table_paths.applications_table_for_day", lambda _day: md)
    return tmp_path


def test_stale_running_research_is_cleared(research_env):
    from research_log import load_research_run, research_run_is_stale, start_research_run

    stale_time = (datetime.now(TZ) - timedelta(minutes=30)).isoformat()
    run_path = research_env / "state" / "research-run.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text(
        '{"running": true, "day": "2026-09-09", "step": "linkedin_jobs_collect", '
        f'"started_at": "{stale_time}", "updated_at": "{stale_time}", "version": 1}}\n',
        encoding="utf-8",
    )
    assert research_run_is_stale() is True
    start_research_run("2026-09-09")
    loaded = load_research_run()
    assert loaded["running"] is True
    assert loaded["step"] == "starting"


def test_active_running_research_blocks_restart(research_env):
    from research_log import ResearchRunInProgressError, start_research_run

    start_research_run("2026-09-09")
    with pytest.raises(ResearchRunInProgressError):
        start_research_run("2026-09-09")


def test_linkedin_jobs_timeout_still_completes_table(research_env, monkeypatch):
    from daily_research import run_daily_research
    from research_log import load_research_run

    calls: list[str] = []

    def mock_run_step(cmd, *, step_key, steps, errors, **kwargs):
        calls.append(step_key)
        if step_key == "linkedin_jobs_collect":
            errors.append("linkedin_jobs_collect: timed out after 1s")
            return None
        if step_key == "generate_table":
            json_path = research_env / "applications" / "applications-2026-09-09-full.json"
            json_path.write_text('{"jobs": [{"role": "AI Engineer", "company": "Acme"}]}', encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("daily_research._run_step", mock_run_step)

    result = run_daily_research(skip_linkedin=True, since="7d")
    assert result["ok"] is True
    assert "generate_table" in calls
    assert load_research_run()["running"] is False
    assert any("linkedin_jobs_collect" in w for w in result.get("warnings", []))
