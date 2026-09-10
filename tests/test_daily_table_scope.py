"""Regression: each research day table includes only that day's discovered roles."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

TZ = ZoneInfo("America/Sao_Paulo")


def _job(*, company: str, discovered_at: str, source: str = "linkedin_posts") -> dict:
    return {
        "source": source,
        "url": f"https://www.linkedin.com/posts/{company.lower().replace(' ', '-')}-activity",
        "role": "Ai Engineer",
        "company": company,
        "filter_result": "eligible",
        "discovered_at": discovered_at,
        "location_note": "LATAM",
    }


@pytest.fixture
def registry_jobs():
    return [
        _job(company="Yesterday Co", discovered_at="2026-09-09T10:00:00-03:00"),
        _job(company="Today Co", discovered_at="2026-09-10T14:30:00-03:00"),
        _job(company="Board Today", discovered_at="2026-09-10T09:00:00-03:00", source="himalayas"),
        _job(company="Old Co", discovered_at="2026-09-08T12:00:00-03:00"),
    ]


def test_job_discovered_on_day_local_tz():
    from table_window import job_discovered_on_day

    job = _job(company="X", discovered_at="2026-09-10T23:30:00-03:00")
    assert job_discovered_on_day(job, "2026-09-10") is True
    assert job_discovered_on_day(job, "2026-09-09") is False


def test_collect_jobs_for_ui_daily_scope(registry_jobs):
    from applications_ui_data import collect_jobs_for_ui

    with patch("applications_ui_data.load_registry", return_value={"jobs": registry_jobs}):
        today = collect_jobs_for_ui(research_day="2026-09-10")
        yesterday = collect_jobs_for_ui(research_day="2026-09-09")

    today_companies = {c["company"] for c in today}
    yesterday_companies = {c["company"] for c in yesterday}

    assert today_companies == {"Today Co", "Board Today"}
    assert yesterday_companies == {"Yesterday Co"}
    assert "Old Co" not in today_companies
    assert "Old Co" not in yesterday_companies


def test_generate_daily_table_excludes_other_days(registry_jobs, tmp_path: Path):
    from generate_applications import generate
    from table_window import day_bounds

    out = tmp_path / "applications-2026-09-10-full.md"
    start, _ = day_bounds("2026-09-10")

    reg = {"jobs": registry_jobs}
    with patch("generate_applications.load_registry", return_value=reg), patch(
        "applications_ui_data.load_registry", return_value=reg
    ):
        counts = generate(
            research_day="2026-09-10",
            linkedin_since=start,
            board_since=start,
            output=out,
        )

    rows = counts["linkedin_eligible_rows"] + counts["linkedin_review_rows"] + counts["board_rows"]
    assert rows == 2
    snap = tmp_path / "applications-2026-09-10-full.json"
    assert snap.exists()
    import json

    payload = json.loads(snap.read_text())
    assert payload.get("research_day") == "2026-09-10"
    assert payload.get("table_mode") == "daily"
    companies = {j["company"] for j in payload["jobs"]}
    assert companies == {"Today Co", "Board Today"}


def test_save_window_for_day_persists_research_day(tmp_path, monkeypatch):
    from table_window import WINDOW_PATH, load_research_day, save_window_for_day

    win = tmp_path / "table-window.json"
    monkeypatch.setattr("table_window.WINDOW_PATH", win)
    save_window_for_day("2026-09-10")
    assert load_research_day() == "2026-09-10"
    data = __import__("json").loads(win.read_text())
    assert data["mode"] == "daily"
    assert data["research_day"] == "2026-09-10"
