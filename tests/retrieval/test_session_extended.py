"""Extended browser_session coverage."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from browser_session import (  # noqa: E402
    browser_launch_kwargs,
    headless_chromium_missing_message,
    headless_chromium_ready_for_collect,
    load_cookies,
)


def test_browser_launch_kwargs():
    kw = browser_launch_kwargs(headless=True)
    assert kw.get("headless") is True


def test_load_cookies_invalid_json(tmp_path, monkeypatch):
    path = tmp_path / "cookies.json"
    path.write_text("{bad", encoding="utf-8")
    monkeypatch.setattr("browser_session.COOKIES_PATH", path)
    assert load_cookies() == []


def test_headless_chromium_messages(monkeypatch):
    monkeypatch.setattr("browser_session.headless_chromium_executable", lambda: None)
    msg = headless_chromium_missing_message(for_collect=True)
    assert "Chromium" in msg or "browser" in msg.lower()
    monkeypatch.setattr("browser_session.headless_chromium_executable", lambda: "/fake/chromium")
    with patch("browser_session.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        assert headless_chromium_ready_for_collect() in (True, False)


def test_resolve_chrome_executable_override(monkeypatch, tmp_path):
    from browser_session import browser_mode_label, resolve_chrome_executable

    fake = tmp_path / "Chrome.app" / "Chrome"
    fake.parent.mkdir(parents=True)
    fake.write_text("", encoding="utf-8")
    monkeypatch.setenv("JOBSEARCH_CHROME_EXECUTABLE", str(fake))
    assert resolve_chrome_executable() == str(fake)
    assert "chrome" in browser_mode_label().lower()


def test_browser_launch_kwargs_headed_channel(monkeypatch):
    from browser_session import browser_launch_kwargs

    monkeypatch.delenv("JOBSEARCH_CHROME_EXECUTABLE", raising=False)
    monkeypatch.setenv("JOBSEARCH_BROWSER_CHANNEL", "chrome")
    with patch("browser_session.resolve_chrome_executable", return_value=None):
        kw = browser_launch_kwargs(headless=False)
    assert kw.get("channel") == "chrome"


@pytest.mark.asyncio
async def test_launch_context_ephemeral(monkeypatch, tmp_path):
    from browser_session import close_session, launch_context

    monkeypatch.setenv("JOBSEARCH_EPHEMERAL_BROWSER", "1")
    monkeypatch.setattr("browser_session.PROFILE_DIR", tmp_path / "missing-profile")
    monkeypatch.setattr("browser_session.load_cookies", lambda: [])

    ctx = AsyncMock()
    ctx.close = AsyncMock()
    browser = AsyncMock()
    browser.new_context = AsyncMock(return_value=ctx)
    pw = AsyncMock()
    pw.chromium.launch = AsyncMock(return_value=browser)
    pw.stop = AsyncMock()

    with patch("patchright.async_api.async_playwright") as apw:
        apw.return_value.start = AsyncMock(return_value=pw)
        pw2, br, cx = await launch_context(headless=True, use_profile=False)
    assert cx is ctx
    await close_session(pw=pw2, browser=br, context=cx)
    pw.stop.assert_awaited()


@pytest.mark.asyncio
async def test_close_session_browser_only():
    from browser_session import close_session

    pw = AsyncMock()
    pw.stop = AsyncMock()
    browser = AsyncMock()
    browser.close = AsyncMock()
    await close_session(pw=pw, browser=browser, context=None)
    browser.close.assert_awaited()
