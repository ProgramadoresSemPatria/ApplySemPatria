"""Browser launch helpers for jobs_collect."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from linkedin_jobs_collect import _launch_context, scroll_jobs_results  # noqa: E402


@pytest.mark.asyncio
async def test_launch_context_ephemeral(monkeypatch, tmp_path):
    monkeypatch.setattr("linkedin_jobs_collect.load_cookies", lambda: [{"name": "li_at", "value": "x", "domain": ".linkedin.com"}])
    monkeypatch.setattr("linkedin_jobs_collect.browser_launch_kwargs", lambda headless=True: {})
    monkeypatch.setattr("linkedin_jobs_collect.PROFILE_DIR", tmp_path / "missing")

    ctx = AsyncMock()
    ctx.add_cookies = AsyncMock()
    browser = AsyncMock()
    browser.new_context = AsyncMock(return_value=ctx)
    p = MagicMock()
    p.chromium.launch = AsyncMock(return_value=browser)

    context, stats = await _launch_context(p, use_profile=False)
    assert context is ctx
    assert stats["auth_mode"] == "cookies"
    ctx.add_cookies.assert_awaited()


@pytest.mark.asyncio
async def test_launch_context_profile_fallback(monkeypatch, tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    monkeypatch.setattr("linkedin_jobs_collect.PROFILE_DIR", profile)
    monkeypatch.setattr("linkedin_jobs_collect.load_cookies", lambda: [])
    monkeypatch.setattr("linkedin_jobs_collect.browser_launch_kwargs", lambda headless=True: {})

    ctx = AsyncMock()
    browser = AsyncMock()
    browser.new_context = AsyncMock(return_value=ctx)
    p = MagicMock()
    p.chromium.launch_persistent_context = AsyncMock(side_effect=RuntimeError("locked"))
    p.chromium.launch = AsyncMock(return_value=browser)

    context, stats = await _launch_context(p, use_profile=True)
    assert context is ctx
    assert "profile_launch" in stats["errors"][0]


@pytest.mark.asyncio
async def test_scroll_jobs_results():
    page = MagicMock()
    panel = MagicMock()
    panel.count = AsyncMock(return_value=1)
    panel.evaluate = AsyncMock()
    page.locator = MagicMock(return_value=MagicMock(first=panel))
    with patch("linkedin_jobs_collect.asyncio.sleep", new=AsyncMock()):
        await scroll_jobs_results(page)
    panel.evaluate.assert_awaited()
