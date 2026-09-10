"""Daily research must build a day-scoped table, not a cumulative window."""

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
    md = tables / "applications-2026-09-10-full.md"
    monkeypatch.setattr("table_paths.applications_table_for_day", lambda day: tables / f"applications-{day}-full.md")
    monkeypatch.setattr("table_paths.applications_table_path", lambda: md)
    win = tmp_path / "state" / "table-window.json"
    monkeypatch.setattr("table_window.WINDOW_PATH", win)
    return tmp_path


def test_daily_research_generate_uses_research_day(research_env, monkeypatch):
    from daily_research import run_daily_research

    cmds: list[list[str]] = []

    def mock_run_step(cmd, *, step_key, steps, errors, **kwargs):
        cmds.append(cmd)
        if step_key == "generate_table":
            json_path = research_env / "applications" / "applications-2026-09-10-full.json"
            json_path.write_text('{"jobs": []}', encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("daily_research._run_step", mock_run_step)
    monkeypatch.setattr("browser_session.headless_chromium_ready", lambda: True)

    result = run_daily_research(skip_linkedin=True, skip_discover=True, since="7d")
    assert result["ok"] is True
    gen = next(c for c in cmds if "generate_applications.py" in " ".join(c))
    assert "--research-day" in gen
    assert "2026-09-10" in gen
    assert "--linkedin-since" not in gen

    win = __import__("json").loads((research_env / "state" / "table-window.json").read_text())
    assert win["research_day"] == "2026-09-10"
    assert win["mode"] == "daily"
