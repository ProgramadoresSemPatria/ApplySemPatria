"""Extended coverage for linkedin copy_link module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from linkedin_post_copy_link import (  # noqa: E402
    backfill_missing_chunk_urls_via_copy_link,
    copy_post_link_for_author,
    copy_post_link_from_card,
    install_copy_link_hook,
    is_copyable_post_url,
    normalize_copied_post_url,
    read_captured_copy_text,
    resolve_chunk_post_url_via_copy_link,
)


def test_is_copyable_post_url():
    assert is_copyable_post_url("https://www.linkedin.com/posts/user_activity-123/") is True
    assert is_copyable_post_url("https://lnkd.in/abc") is True
    assert is_copyable_post_url("") is False
    assert is_copyable_post_url("https://www.linkedin.com/search/results/content/?keywords=x") is False


def test_normalize_copied_post_url_posts_permalink():
    url = "https://www.linkedin.com/posts/user_activity-123"
    out = normalize_copied_post_url(url)
    assert out.endswith("/")


def test_normalize_copied_post_url_empty_and_non_linkedin():
    assert normalize_copied_post_url("") == ""
    assert normalize_copied_post_url("https://example.com/x") == ""


def test_normalize_copied_post_url_curl_resolves_posts(monkeypatch):
    def fake_run(cmd, **kwargs):
        class R:
            stdout = "location: https://www.linkedin.com/posts/acme_ai-engineer-activity-1/\n"
            stderr = ""
            returncode = 0

        return R()

    monkeypatch.setattr("subprocess.run", fake_run)
    url = normalize_copied_post_url("https://lnkd.in/short")
    assert "/posts/" in url


@pytest.mark.asyncio
async def test_install_copy_link_hook():
    page = MagicMock()
    page.add_init_script = AsyncMock()
    await install_copy_link_hook(page)
    page.add_init_script.assert_awaited()


@pytest.mark.asyncio
async def test_read_captured_copy_text():
    page = MagicMock()
    page.evaluate = AsyncMock()
    assert await read_captured_copy_text(page) == ""


@pytest.mark.asyncio
async def test_copy_post_link_from_card_via_urn():
    card = MagicMock()
    card.get_attribute = AsyncMock(return_value="urn:li:activity:123456")
    page = MagicMock()
    url = await copy_post_link_from_card(page, card)
    assert "feed/update" in url or "activity" in url


@pytest.mark.asyncio
async def test_copy_post_link_from_card_menu_flow(monkeypatch):
    card = MagicMock()
    card.get_attribute = AsyncMock(return_value=None)

    overflow = MagicMock()
    overflow.count = AsyncMock(return_value=1)
    overflow.click = AsyncMock()

    def card_locator(_sel: str) -> MagicMock:
        wrapper = MagicMock()
        wrapper.first = overflow
        return wrapper

    card.locator = card_locator

    page = MagicMock()
    page.context.grant_permissions = AsyncMock()
    copy_btn = MagicMock()
    copy_btn.count = AsyncMock(return_value=1)
    copy_btn.click = AsyncMock()
    page.get_by_text.return_value.first = copy_btn
    page.evaluate = AsyncMock(return_value="https://www.linkedin.com/posts/user_activity-999/")
    page.keyboard.press = AsyncMock()

    monkeypatch.setattr(
        "linkedin_post_copy_link.normalize_copied_post_url",
        lambda u, **k: u if u else "",
    )
    monkeypatch.setattr(
        "linkedin_post_copy_link.is_copyable_post_url",
        lambda u: bool(u),
    )
    with patch("linkedin_post_copy_link.asyncio.sleep", new=AsyncMock()):
        url = await copy_post_link_from_card(page, card)
    assert "posts" in url


@pytest.mark.asyncio
async def test_copy_post_link_for_author_empty():
    page = MagicMock()
    assert await copy_post_link_for_author(page, "") == ""


@pytest.mark.asyncio
async def test_copy_post_link_for_author_success(monkeypatch):
    page = MagicMock()
    btn = MagicMock()
    btn.count = AsyncMock(return_value=1)
    btn.click = AsyncMock()
    page.locator.return_value.first = btn

    menu = MagicMock()
    menu.wait_for = AsyncMock()
    menu.get_by_text.return_value.first.count = AsyncMock(return_value=1)
    menu.get_by_text.return_value.first.click = AsyncMock()
    page.locator.return_value.last = menu
    page.evaluate = AsyncMock(side_effect=["", "https://www.linkedin.com/posts/x_activity-1/"])
    page.keyboard.press = AsyncMock()

    monkeypatch.setattr(
        "linkedin_post_copy_link.normalize_copied_post_url",
        lambda u, **k: u,
    )
    with patch("linkedin_post_copy_link.asyncio.sleep", new=AsyncMock()):
        url = await copy_post_link_for_author(page, "Jane Doe")
    assert "posts" in url


@pytest.mark.asyncio
async def test_resolve_chunk_post_url_delegates():
    page = MagicMock()
    with patch(
        "linkedin_post_copy_link.copy_post_link_for_author",
        AsyncMock(return_value="https://www.linkedin.com/posts/a/"),
    ) as mock_copy:
        url = await resolve_chunk_post_url_via_copy_link(page, "Author")
    assert url.endswith("/")
    mock_copy.assert_awaited()


@pytest.mark.asyncio
async def test_backfill_missing_chunk_urls():
    page = MagicMock()
    chunks = ["chunk1", "chunk2"]
    urls: list[str] = ["", ""]
    with patch(
        "linkedin_post_copy_link.copy_post_link_for_author",
        AsyncMock(return_value="https://www.linkedin.com/posts/filled/"),
    ):
        filled = await backfill_missing_chunk_urls_via_copy_link(
            page,
            chunks,
            urls,
            limit=2,
            extract_author=lambda c: "Author",
        )
    assert filled == 2
    assert urls[0].endswith("/")
