"""Coverage for shared browser utilities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from human_pacing import jitter_seconds, pause_human  # noqa: E402
from linkedin_ui import CONNECT_BUTTON_NAME_RE, connect_button_name_pattern, is_connect_affordance_label  # noqa: E402


def test_jitter_seconds_range():
    val = jitter_seconds(1.0, spread=0.5, minimum=0.5)
    assert 0.5 <= val <= 2.0


@pytest.mark.asyncio
async def test_pause_human_fast(monkeypatch):
    monkeypatch.setenv("JOBSEARCH_HUMAN_PACING", "0")
    with patch("human_pacing.asyncio.sleep", new=AsyncMock()) as sleep:
        await pause_human(base=10.0)
    sleep.assert_awaited()


def test_connect_button_regex():
    assert CONNECT_BUTTON_NAME_RE.search("Connect")
    assert CONNECT_BUTTON_NAME_RE.search("Invite Maria to connect")


def test_connect_button_name_pattern():
    pat = connect_button_name_pattern()
    assert "connect" in pat.lower()


def test_is_connect_affordance_label():
    assert is_connect_affordance_label("Connect") is True
    assert is_connect_affordance_label("Follow") is False


@pytest.mark.asyncio
async def test_session_load_cookies_missing(tmp_path, monkeypatch):
    from browser_session import load_cookies

    monkeypatch.setattr("browser_session.COOKIES_PATH", tmp_path / "missing.json")
    assert load_cookies() == []


@pytest.mark.asyncio
async def test_drift_mouse_and_scroll():
    page = MagicMock()
    page.viewport_size = {"width": 1280, "height": 900}
    page.mouse.move = AsyncMock()
    page.mouse.wheel = AsyncMock()
    with patch("human_pacing.human_pacing_enabled", return_value=True):
        with patch("human_pacing.asyncio.sleep", new=AsyncMock()):
            from human_pacing import drift_mouse, human_scroll, pause, pause_poll

            await drift_mouse(page)
            await human_scroll(page)
            await pause(1.0)
            await pause_poll()
    page.mouse.move.assert_awaited()


@pytest.mark.asyncio
async def test_human_click_and_fill():
    page = MagicMock()
    page.mouse.move = AsyncMock()
    target = MagicMock()
    target.scroll_into_view_if_needed = AsyncMock()
    target.bounding_box = AsyncMock(return_value={"x": 10, "y": 20, "width": 100, "height": 30})
    target.click = AsyncMock()
    target.fill = AsyncMock()
    target.press_sequentially = AsyncMock()
    locator = MagicMock()
    locator.nth = MagicMock(return_value=target)
    page.viewport_size = {"width": 1280, "height": 900}
    page.mouse.wheel = AsyncMock()
    with patch("human_pacing.human_pacing_enabled", return_value=True):
        with patch("human_pacing.asyncio.sleep", new=AsyncMock()):
            from human_pacing import human_click, human_fill

            await human_click(page, locator, index=0, force=True)
            await human_fill(page, locator, "hello", index=0)
    target.click.assert_awaited()
