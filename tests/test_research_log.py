"""Tests for local research-day log."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def research_log_tmp(tmp_path, monkeypatch):
    log = tmp_path / "state" / "research-log.json"
    run = tmp_path / "state" / "research-run.json"
    history = tmp_path / "state" / "ingestion-history.json"
    monkeypatch.setattr("research_log.LOG_PATH", log)
    monkeypatch.setattr("research_log.RUN_PATH", run)
    monkeypatch.setattr("research_log.INGESTION_HISTORY_PATH", history)
    monkeypatch.setattr("research_log.ROOT", tmp_path)
    return log


def test_mark_and_has_research(research_log_tmp):
    from research_log import has_research, mark_research_day

    assert not has_research("2026-09-07")
    mark_research_day("2026-09-07", job_count=10)
    assert has_research("2026-09-07")


def test_ingestion_history_backfill(research_log_tmp):
    from research_log import ensure_ingestion_history_migrated, last_ingestion_completed_at, mark_research_day

    mark_research_day("2026-09-09", job_count=10)
    hist = ensure_ingestion_history_migrated()
    assert len(hist["entries"]) == 1
    assert last_ingestion_completed_at() is not None


def test_ingestion_history_appends_each_run(research_log_tmp):
    from research_log import load_ingestion_history, mark_research_day

    mark_research_day("2026-09-10", job_count=5)
    mark_research_day("2026-09-10", job_count=8)
    entries = load_ingestion_history()["entries"]
    assert len(entries) == 2
    assert entries[-1]["job_count"] == 8


def test_ingestion_window_without_prior(research_log_tmp):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from research_log import default_ingestion_since, ingestion_window_meta, load_ingestion_history, save_ingestion_history

    save_ingestion_history(load_ingestion_history())
    now = datetime(2026, 9, 10, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    meta = ingestion_window_meta(now=now)
    assert meta["ingestion_has_prior"] is False
    assert meta["ingestion_since"] == "7d"
    assert default_ingestion_since(now=now) == "7d"


def test_ingestion_window_since_last_completion(research_log_tmp):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from research_log import default_ingestion_since, ingestion_window_meta, load_log, mark_research_day, save_log

    completed = "2026-09-09T14:41:57.038173-03:00"
    from research_log import save_ingestion_history

    mark_research_day("2026-09-09", job_count=10)
    log = load_log()
    log["days"]["2026-09-09"]["completed_at"] = completed
    save_log(log)
    save_ingestion_history({"entries": [{"day": "2026-09-09", "completed_at": completed, "job_count": 10}], "version": 1})
    now = datetime(2026, 9, 10, 11, 48, tzinfo=ZoneInfo("America/Sao_Paulo"))
    meta = ingestion_window_meta(now=now)
    assert meta["ingestion_has_prior"] is True
    assert meta["ingestion_last_day"] == "2026-09-09"
    assert meta["ingestion_last_at"] == completed
    assert meta["ingestion_since"] == completed
    assert default_ingestion_since(now=now) == completed


def test_stale_run_detection(research_log_tmp, monkeypatch):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from research_log import clear_stale_research_run, research_run_is_stale, start_research_run

    monkeypatch.setattr("research_log.STALE_RUN_MINUTES", 1)
    stale = (datetime.now(ZoneInfo("America/Sao_Paulo")) - timedelta(minutes=5)).isoformat()
    run_path = research_log_tmp.parent / "research-run.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text(
        f'{{"running": true, "day": "2026-09-07", "step": "linkedin_jobs_collect", '
        f'"started_at": "{stale}", "updated_at": "{stale}", "version": 1}}\n',
        encoding="utf-8",
    )
    assert research_run_is_stale() is True
    assert clear_stale_research_run() is True
    start_research_run("2026-09-07")


def test_research_run_progress(research_log_tmp):
    from research_log import finish_research_run, research_run_status, set_research_step, start_research_run

    start_research_run("2026-09-07")
    status = research_run_status()
    assert status["running"] is True
    assert status["step"] == "starting"

    set_research_step("linkedin_collect")
    assert research_run_status()["step"] == "linkedin_collect"

    finish_research_run(ok=True, message="done")
    done = research_run_status()
    assert done["running"] is False
    assert done["ok"] is True
    assert done["message"] == "done"


def test_list_snapshot_days_includes_pending_today(research_log_tmp, tmp_path, monkeypatch):
    from applications_ui_data import list_snapshot_days
    from research_log import mark_research_day
    from table_paths import APPLICATIONS_TABLES_DIR

    monkeypatch.setattr("table_paths.APPLICATIONS_TABLES_DIR", tmp_path / "applications")
    monkeypatch.setattr("applications_ui_data.APPLICATIONS_TABLES_DIR", tmp_path / "applications")
    monkeypatch.setattr("research_log.today_local", lambda: "2026-09-07")
    app_dir = tmp_path / "applications"
    app_dir.mkdir(parents=True)

    mark_research_day("2026-09-06", job_count=2)
    (app_dir / "applications-2026-09-06-full.md").write_text("# x", encoding="utf-8")
    (app_dir / "applications-2026-09-06-full.json").write_text('{"jobs": [{}, {}]}', encoding="utf-8")

    days = list_snapshot_days()
    assert [d["day"] for d in days] == ["2026-09-07", "2026-09-06"]
    assert days[0]["pending"] is True
    assert days[1]["pending"] is False


def test_list_snapshot_days_only_researched(research_log_tmp, tmp_path, monkeypatch):
    from applications_ui_data import list_snapshot_days
    from research_log import mark_research_day
    from table_paths import APPLICATIONS_TABLES_DIR

    monkeypatch.setattr("table_paths.APPLICATIONS_TABLES_DIR", tmp_path / "applications")
    monkeypatch.setattr("applications_ui_data.APPLICATIONS_TABLES_DIR", tmp_path / "applications")
    monkeypatch.setattr("research_log.today_local", lambda: "2026-09-06")
    app_dir = tmp_path / "applications"
    app_dir.mkdir(parents=True)

    mark_research_day("2026-09-06", job_count=2)
    (app_dir / "applications-2026-09-06-full.md").write_text("# x", encoding="utf-8")
    (app_dir / "applications-2026-09-06-full.json").write_text('{"jobs": [{}, {}]}', encoding="utf-8")
    (app_dir / "applications-2026-09-07-full.md").write_text("# y", encoding="utf-8")

    days = list_snapshot_days()
    assert [d["day"] for d in days] == ["2026-09-06"]


def test_remove_research_day_clears_history_and_snapshots(research_log_tmp, tmp_path, monkeypatch):
    from research_log import has_research, load_ingestion_history, mark_research_day, remove_research_day
    from table_paths import APPLICATIONS_TABLES_DIR

    monkeypatch.setattr("table_paths.APPLICATIONS_TABLES_DIR", tmp_path / "applications")
    monkeypatch.setattr("applications_ui_data.APPLICATIONS_TABLES_DIR", tmp_path / "applications")
    app_dir = tmp_path / "applications"
    app_dir.mkdir(parents=True)

    mark_research_day("2026-09-10", job_count=3)
    (app_dir / "applications-2026-09-10-full.md").write_text("# today", encoding="utf-8")
    (app_dir / "applications-2026-09-10-full.json").write_text('{"jobs": []}', encoding="utf-8")
    assert has_research("2026-09-10")
    assert len(load_ingestion_history()["entries"]) == 1

    remove_research_day("2026-09-10")
    assert not has_research("2026-09-10")
    assert load_ingestion_history()["entries"] == []
    assert not (app_dir / "applications-2026-09-10-full.md").exists()
    assert not (app_dir / "applications-2026-09-10-full.json").exists()


def test_repair_spurious_snapshot_days(research_log_tmp, tmp_path, monkeypatch):
    from research_log import mark_research_day, repair_spurious_snapshot_days
    from table_paths import APPLICATIONS_TABLES_DIR

    monkeypatch.setattr("table_paths.APPLICATIONS_TABLES_DIR", tmp_path / "applications")
    monkeypatch.setattr("applications_ui_data.APPLICATIONS_TABLES_DIR", tmp_path / "applications")
    app_dir = tmp_path / "applications"
    app_dir.mkdir(parents=True)

    mark_research_day("2026-09-06")
    (app_dir / "applications-2026-09-06-full.md").write_text("# ok", encoding="utf-8")
    (app_dir / "applications-2026-09-07-full.md").write_text("# stray", encoding="utf-8")
    (app_dir / "applications-2026-09-07-full.json").write_text("{}", encoding="utf-8")

    removed = repair_spurious_snapshot_days()
    assert removed == ["2026-09-07"]
    assert not (app_dir / "applications-2026-09-07-full.md").exists()
    assert (app_dir / "applications-2026-09-06-full.md").exists()
