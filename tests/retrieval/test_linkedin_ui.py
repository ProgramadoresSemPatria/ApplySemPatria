"""AsyncMock coverage for linkedin_ui profile affordances."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from linkedin_ui import (  # noqa: E402
    click_connect_on_main,
    click_easy_apply_button,
    connect_locator_on_main,
    dismiss_premium_modal,
    has_connect_on_main,
    has_more_on_top_card,
    more_menu_has_connect,
    wait_for_profile_top_card,
)


def _connect_node():
    node = MagicMock()
    node.is_visible = AsyncMock(return_value=True)
    node.get_attribute = AsyncMock(return_value="Invite Jane to connect")
    node.inner_text = AsyncMock(return_value="Connect")
    return node


@pytest.mark.asyncio
async def test_connect_locator_on_main_finds_button():
    page = MagicMock()
    scope = MagicMock()
    scope.count = AsyncMock(return_value=1)
    loc = MagicMock()
    loc.count = AsyncMock(return_value=1)
    loc.nth = MagicMock(return_value=_connect_node())
    scope.locator = MagicMock(return_value=loc)
    scope.get_by_role = MagicMock(return_value=loc)
    with patch("linkedin_ui.profile_action_scopes", return_value=[scope]):
        with patch("linkedin_ui._connect_locator_candidates", return_value=[loc]):
            node = await connect_locator_on_main(page)
    assert node is not None


@pytest.mark.asyncio
async def test_has_connect_on_main():
    with patch("linkedin_ui.connect_locator_on_main", AsyncMock(return_value=_connect_node())):
        assert await has_connect_on_main(MagicMock()) is True
    with patch("linkedin_ui.connect_locator_on_main", AsyncMock(return_value=None)):
        assert await has_connect_on_main(MagicMock()) is False


@pytest.mark.asyncio
async def test_click_connect_on_main():
    node = _connect_node()
    with patch("linkedin_ui.connect_locator_on_main", AsyncMock(return_value=node)):
        with patch("linkedin_ui.human_click", AsyncMock()) as click:
            ok = await click_connect_on_main(MagicMock())
    assert ok is True
    click.assert_awaited()


@pytest.mark.asyncio
async def test_has_more_on_top_card():
    page = MagicMock()
    section = MagicMock()
    section.get_by_role = MagicMock(return_value=MagicMock(count=AsyncMock(return_value=1)))
    with patch("linkedin_ui.main_profile_section", return_value=section):
        assert await has_more_on_top_card(page) is True


@pytest.mark.asyncio
async def test_more_menu_has_connect():
    page = MagicMock()
    more = MagicMock()
    more.count = AsyncMock(return_value=1)
    menuitem = MagicMock()
    menuitem.count = AsyncMock(return_value=1)
    menuitem.nth = MagicMock(
        return_value=MagicMock(
            get_attribute=AsyncMock(return_value="Invite to connect"),
            inner_text=AsyncMock(return_value="Connect"),
        )
    )
    page.get_by_role = MagicMock(return_value=menuitem)
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    section = MagicMock()
    section.get_by_role = MagicMock(return_value=more)
    with patch("linkedin_ui.has_connect_on_main", AsyncMock(return_value=False)):
        with patch("linkedin_ui.main_profile_section", return_value=section):
            with patch("linkedin_ui.human_click", AsyncMock()):
                with patch("linkedin_ui.pause_poll", AsyncMock()):
                    ok = await more_menu_has_connect(page)
    assert ok is True


@pytest.mark.asyncio
async def test_wait_for_profile_top_card():
    page = MagicMock()
    with patch("linkedin_ui.has_connect_on_main", AsyncMock(return_value=True)):
        assert await wait_for_profile_top_card(page, timeout_ms=100) is True


@pytest.mark.asyncio
async def test_dismiss_premium_modal():
    page = MagicMock()
    dialog = MagicMock()
    dialog.count = AsyncMock(return_value=1)
    dialog.first = dialog
    dismiss_btn = MagicMock()
    dismiss_btn.count = AsyncMock(return_value=1)
    dialog.locator = MagicMock(return_value=dismiss_btn)
    filtered = MagicMock()
    filtered.count = AsyncMock(return_value=1)
    filtered.first = dialog
    page.locator = MagicMock(return_value=MagicMock(filter=MagicMock(return_value=filtered)))
    with patch("linkedin_ui.human_click", AsyncMock()):
        ok = await dismiss_premium_modal(page)
    assert ok is True


@pytest.mark.asyncio
async def test_click_easy_apply_button():
    page = MagicMock()
    loc = MagicMock()
    loc.count = AsyncMock(return_value=1)
    page.locator = MagicMock(return_value=loc)
    page.get_by_role = MagicMock(return_value=loc)
    with patch("linkedin_ui.dismiss_blocking_dialogs", AsyncMock(return_value=[])):
        with patch("linkedin_ui.wait_for_job_detail_ready", AsyncMock(return_value=True)):
            with patch(
                "linkedin_ui._click_first_visible",
                AsyncMock(return_value={"clicked": True, "strategy": "test"}),
            ):
                result = await click_easy_apply_button(page)
    assert result.get("clicked") is True
