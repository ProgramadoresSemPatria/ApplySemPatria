"""Coverage for dm_chat, dm_apply helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dm_apply import (  # noqa: E402
    collect_candidates,
    is_applied_skip,
    message_body,
    pretty_role,
    profile_url_for,
)
from dm_chat import (  # noqa: E402
    _abs_linkedin_url,
    classify_header,
    latest_header_is_recent,
)


def test_classify_header():
    assert classify_header("Today") == "recent"
    assert classify_header("Monday") == "recent"
    assert classify_header("Jan 15") == "older"
    assert classify_header("random") == "other"


def test_latest_header_is_recent():
    ok, header, reason = latest_header_is_recent(["Jan 10", "Today"])
    assert ok is True
    ok2, _, _ = latest_header_is_recent(["Jan 10", "Feb 1"])
    assert ok2 is False


def test_abs_linkedin_url():
    assert _abs_linkedin_url("/in/foo").startswith("https://www.linkedin.com")
    assert _abs_linkedin_url("https://linkedin.com/in/foo").startswith("https://")


def test_pretty_role():
    assert pretty_role("Ai Engineer") == "AI Engineer"


def test_is_applied_skip():
    assert is_applied_skip({"company": "Jeeves AI"}) is True
    assert is_applied_skip({"company": "Fresh Startup"}) is False


def test_message_body_default(dm_registry_job=None):
    job = {
        "source": "linkedin_posts",
        "role": "Ai Engineer",
        "apply_url": "https://example.com/apply",
    }
    profile = {"dm_message_template": "Hi about {role}"}
    body = message_body(job, profile)
    assert "AI Engineer" in body


def test_profile_url_for():
    job = {"recruiter_profile_url": "https://www.linkedin.com/in/recruiter/"}
    assert profile_url_for(job) == job["recruiter_profile_url"]


def test_collect_candidates_table_only(monkeypatch):
    from datetime import datetime

    job = {
        "track": "ai-engineer",
        "source": "linkedin_posts",
        "company": "Acme",
        "role": "AI Engineer",
        "url": "https://www.linkedin.com/posts/x",
        "recruiter_profile_url": "https://www.linkedin.com/in/recruiter/",
        "discovered_at": datetime.now().isoformat(),
    }
    monkeypatch.setattr("dm_apply.load_registry", lambda: {"jobs": [job]})
    monkeypatch.setattr("dm_apply.filter_jobs_by_track", lambda jobs, tid: jobs)
    monkeypatch.setattr("dm_apply.needs_recruiter_connect", lambda j: True)
    monkeypatch.setattr("table_window.table_since", lambda: datetime.fromisoformat("2020-01-01T00:00:00"))
    monkeypatch.setattr("linkedin_posts_merge.sort_jobs_by_recency", lambda xs: xs)
    out = collect_candidates(table_only=True, limit=0, track_id="ai-engineer")
    assert len(out) == 1


@pytest.mark.asyncio
async def test_dm_chat_thread_headers_mock():
    from dm_chat import read_thread_headers

    page = MagicMock()
    inner = MagicMock()
    inner.inner_text = AsyncMock(return_value="Today\nHello there")
    page.locator.return_value.first = inner
    headers = await read_thread_headers(page)
    assert isinstance(headers, list)


@pytest.mark.asyncio
async def test_open_message_thread_success():
    from dm_chat import open_message_thread

    page = MagicMock()
    page.evaluate = AsyncMock()
    page.goto = AsyncMock()
    loc = MagicMock()
    loc.count = AsyncMock(return_value=1)
    loc.first = loc
    loc.get_attribute = AsyncMock(return_value="/messaging/compose/new/")
    page.locator = MagicMock(return_value=loc)
    page.get_by_role = MagicMock(return_value=loc)

    composer = MagicMock()
    composer.count = AsyncMock(return_value=1)

    with patch("dm_chat.pause_poll", AsyncMock()):
        with patch("dm_chat.dismiss_blocking_dialogs", AsyncMock()):
            with patch("dm_chat.drift_mouse", AsyncMock()):
                with patch("dm_chat.human_click", AsyncMock()):
                    with patch("dm_chat.pause_page_settle", AsyncMock()):
                        with patch("dm_chat._composer_visible", AsyncMock(return_value=True)):
                            ok = await open_message_thread(page)
    assert ok is True


@pytest.mark.asyncio
async def test_send_message_dry_run():
    from dm_chat import send_message

    page = MagicMock()
    with patch("dm_chat._composer_visible", AsyncMock(return_value=True)):
        ok, note = await send_message(page, "Hello", send=False)
    assert ok is True
    assert "DRY" in note


@pytest.mark.asyncio
async def test_inspect_thread_mock():
    from dm_chat import inspect_thread

    page = MagicMock()
    page.evaluate = AsyncMock()
    with patch("dm_chat.open_message_thread", AsyncMock(return_value=True)):
        with patch("dm_chat.read_thread_headers", AsyncMock(return_value=["Today"])):
            with patch("dm_chat.human_scroll", AsyncMock()):
                with patch("dm_chat.pause_human", AsyncMock()):
                    result = await inspect_thread(page)
    assert result["opened"] is True
    assert result["recent"] is True
