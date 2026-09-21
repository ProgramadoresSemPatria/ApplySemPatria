"""Ingestion since → LinkedIn recency and table posted-time scope."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

TZ = ZoneInfo("America/Sao_Paulo")


def test_infer_period_days_daily_run_uses_past_24h():
    from registry import infer_period_days_from_since

    now = datetime(2026, 9, 21, 10, 0, tzinfo=TZ)
    since = "2026-09-20T16:46:13.006525-03:00"
    assert infer_period_days_from_since(since, now=now) == 1


def test_infer_period_days_multi_day_gap():
    from registry import infer_period_days_from_since

    now = datetime(2026, 9, 20, 16, 0, tzinfo=TZ)
    since = "2026-09-16T14:09:31.696454-03:00"
    assert infer_period_days_from_since(since, now=now) == 5


def test_job_posted_on_or_after_respects_since():
    from registry import job_posted_on_or_after

    since = datetime(2026, 9, 20, 16, 46, tzinfo=TZ)
    old = {
        "posted_at": "2026-09-16T16:52:14.195539-03:00",
        "discovered_at": "2026-09-20T17:00:00-03:00",
    }
    fresh = {
        "posted_at": "2026-09-21T10:00:00-03:00",
        "discovered_at": "2026-09-21T10:05:00-03:00",
    }
    assert job_posted_on_or_after(old, since) is False
    assert job_posted_on_or_after(fresh, since) is True


def test_table_scope_keeps_posted_within_ingestion_since_gap():
    from generate_applications import _job_in_table_scope
    from table_window import day_bounds

    start, _ = day_bounds("2026-09-20")
    job = {
        "source": "linkedin_posts",
        "discovered_at": "2026-09-20T17:00:00-03:00",
        "posted_at": "2026-09-16T16:52:14.195539-03:00",
    }
    log = {
        "days": {
            "2026-09-20": {
                "since": "2026-09-16T14:09:31.696454-03:00",
            }
        },
        "version": 1,
    }
    with patch("research_log.load_log", return_value=log):
        assert _job_in_table_scope(
            job,
            research_day="2026-09-20",
            linkedin_since=start,
            board_since=start,
            linkedin_source=True,
        )


def test_table_scope_excludes_posted_before_daily_ingestion_since():
    from generate_applications import _job_in_table_scope
    from table_window import day_bounds

    start, _ = day_bounds("2026-09-21")
    job = {
        "source": "linkedin_posts",
        "discovered_at": "2026-09-21T14:00:00-03:00",
        "posted_at": "2026-09-16T16:52:14.195539-03:00",
    }
    log = {
        "days": {
            "2026-09-21": {
                "since": "2026-09-20T16:46:13.006525-03:00",
            }
        },
        "version": 1,
    }
    with patch("research_log.load_log", return_value=log):
        assert (
            _job_in_table_scope(
                job,
                research_day="2026-09-21",
                linkedin_since=start,
                board_since=start,
                linkedin_source=True,
            )
            is False
        )


def test_write_linkedin_run_markdown_filters_outside_since(tmp_path):
    from linkedin_posts_merge import write_linkedin_run_markdown

    since = datetime(2026, 9, 20, 16, 46, tzinfo=TZ)
    old = {
        "source": "linkedin_posts",
        "url": "https://www.linkedin.com/posts/old-post/",
        "role": "Ai Engineer",
        "company": "Old Co",
        "posted_at": "2026-09-16T12:00:00-03:00",
        "posted_label": "5d",
        "filter_result": "needs_review",
    }
    fresh = {
        "source": "linkedin_posts",
        "url": "https://www.linkedin.com/posts/fresh-post/",
        "role": "Ai Engineer",
        "company": "Fresh Co",
        "posted_at": "2026-09-21T10:00:00-03:00",
        "posted_label": "2h",
        "filter_result": "needs_review",
    }
    run_path = tmp_path / "linkedin-posts.md"
    write_linkedin_run_markdown(
        run_path,
        since,
        [old, fresh],
        [fresh],
        1,
        "past-24h",
        1,
    )
    text = run_path.read_text()
    assert "Fresh Co" in text
    assert "Old Co" not in text
