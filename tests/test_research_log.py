"""Tests for local research-day log."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def research_log_tmp(tmp_path, monkeypatch):
    log = tmp_path / "state" / "research-log.json"
    monkeypatch.setattr("research_log.LOG_PATH", log)
    monkeypatch.setattr("research_log.ROOT", tmp_path)
    return log


def test_mark_and_has_research(research_log_tmp):
    from research_log import has_research, mark_research_day

    assert not has_research("2026-09-07")
    mark_research_day("2026-09-07", job_count=10)
    assert has_research("2026-09-07")


def test_list_snapshot_days_only_researched(research_log_tmp, tmp_path, monkeypatch):
    from applications_ui_data import list_snapshot_days
    from research_log import mark_research_day
    from table_paths import APPLICATIONS_TABLES_DIR

    monkeypatch.setattr("table_paths.APPLICATIONS_TABLES_DIR", tmp_path / "applications")
    monkeypatch.setattr("applications_ui_data.APPLICATIONS_TABLES_DIR", tmp_path / "applications")
    app_dir = tmp_path / "applications"
    app_dir.mkdir(parents=True)

    mark_research_day("2026-09-06", job_count=2)
    (app_dir / "applications-2026-09-06-full.md").write_text("# x", encoding="utf-8")
    (app_dir / "applications-2026-09-06-full.json").write_text('{"jobs": [{}, {}]}', encoding="utf-8")
    (app_dir / "applications-2026-09-07-full.md").write_text("# y", encoding="utf-8")

    days = list_snapshot_days()
    assert [d["day"] for d in days] == ["2026-09-06"]


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
