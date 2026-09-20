"""LinkedIn profile PDF download — unit tests (no live network in default CI)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from browser_session import COOKIES_PATH  # noqa: E402
from linkedin_profile_pdf_download import (  # noqa: E402
    PdfDownloadResult,
    default_dest_path,
    download_linkedin_profile_pdf,
    find_more_button_candidates,
    find_save_to_pdf_candidates,
    menu_fixture_has_save_to_pdf,
    normalize_profile_url,
    profile_slug,
    resolve_linkedin_url,
)

FIXTURE_HTML = Path(__file__).resolve().parent / "fixtures" / "linkedin" / "profile-more-menu.html"


def test_normalize_profile_url():
    assert normalize_profile_url("linkedin.com/in/caiohandradelima") == (
        "https://www.linkedin.com/in/caiohandradelima/"
    )
    assert normalize_profile_url("https://www.linkedin.com/in/caiohandradelima/?original=true") == (
        "https://www.linkedin.com/in/caiohandradelima/"
    )


def test_profile_slug():
    assert profile_slug("https://www.linkedin.com/in/caiohandradelima/") == "caiohandradelima"


def test_default_dest_path():
    path = default_dest_path("https://www.linkedin.com/in/caiohandradelima/")
    assert path.name == "caiohandradelima-profile.pdf"
    assert "state/chameleon/imports" in str(path)


def test_fixture_more_and_save_menu():
    html = FIXTURE_HTML.read_text(encoding="utf-8")
    more = find_more_button_candidates(html)
    save = find_save_to_pdf_candidates(html)
    assert any("Resources" in label or "More" in label for label in more) or menu_fixture_has_save_to_pdf(html)
    assert save == ["Save to PDF"]
    assert menu_fixture_has_save_to_pdf(html) is True


def test_resolve_linkedin_url_from_explicit():
    url = resolve_linkedin_url("https://www.linkedin.com/in/jane-doe/", "ai-engineer")
    assert url == "https://www.linkedin.com/in/jane-doe/"


def test_resolve_linkedin_url_from_track_profile(monkeypatch):
    monkeypatch.setattr(
        "track_store.load_profile",
        lambda track_id=None: {"linkedin_url": "https://www.linkedin.com/in/caiohandradelima/"},
    )
    url = resolve_linkedin_url("", "ai-engineer")
    assert "caiohandradelima" in url


@pytest.mark.asyncio
async def test_download_missing_cookies(tmp_path, monkeypatch):
    monkeypatch.setattr("linkedin_profile_pdf_download.COOKIES_PATH", tmp_path / "missing.json")
    dest = tmp_path / "out.pdf"
    result = await download_linkedin_profile_pdf(
        "https://www.linkedin.com/in/caiohandradelima/",
        dest,
        use_cookies=True,
    )
    assert result.ok is False
    assert "cookies" in result.message.lower()


@pytest.mark.asyncio
async def test_download_linkedin_menu_mock(tmp_path, monkeypatch):
    cookies = tmp_path / "cookies.json"
    cookies.write_text("[]", encoding="utf-8")
    monkeypatch.setattr("linkedin_profile_pdf_download.COOKIES_PATH", cookies)

    dest = tmp_path / "profile.pdf"
    menu_ok = PdfDownloadResult(
        ok=True,
        path=dest,
        message="Downloaded via LinkedIn More → Save to PDF",
        method="linkedin_download",
    )

    page = AsyncMock()
    page.url = "https://www.linkedin.com/in/caiohandradelima/"
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.evaluate = AsyncMock(return_value=False)

    ctx = AsyncMock()
    ctx.pages = []
    ctx.new_page = AsyncMock(return_value=page)

    async def fake_launch(**kwargs):
        return MagicMock(), MagicMock(), ctx

    menu_mock = AsyncMock(return_value=menu_ok)
    with patch("linkedin_profile_pdf_download.launch_context", fake_launch):
        with patch("linkedin_profile_pdf_download.close_session", AsyncMock()):
            with patch("linkedin_profile_pdf_download._try_linkedin_save_to_pdf", menu_mock):
                result = await download_linkedin_profile_pdf(
                    "https://www.linkedin.com/in/caiohandradelima/",
                    dest,
                    use_cookies=True,
                )

    assert result.ok is True
    assert result.method == "linkedin_download"
    menu_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_download_page_pdf_fallback(tmp_path, monkeypatch):
    cookies = tmp_path / "cookies.json"
    cookies.write_text("[]", encoding="utf-8")
    monkeypatch.setattr("linkedin_profile_pdf_download.COOKIES_PATH", cookies)

    dest = tmp_path / "fallback.pdf"

    page = AsyncMock()
    page.url = "https://www.linkedin.com/in/caiohandradelima/"
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.evaluate = AsyncMock(return_value=False)
    page.emulate_media = AsyncMock()

    async def fake_pdf(**kwargs):
        Path(kwargs["path"]).write_bytes(b"%PDF-1.4 fallback content " + b"x" * 600)

    page.pdf = fake_pdf
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()

    ctx = AsyncMock()
    ctx.pages = []
    ctx.new_page = AsyncMock(return_value=page)

    async def fake_launch(**kwargs):
        return MagicMock(), MagicMock(), ctx

    with patch("linkedin_profile_pdf_download.launch_context", fake_launch):
        with patch("linkedin_profile_pdf_download.close_session", AsyncMock()):
            with patch("linkedin_profile_pdf_download._try_linkedin_save_to_pdf", AsyncMock(return_value=None)):
                result = await download_linkedin_profile_pdf(
                    "https://www.linkedin.com/in/caiohandradelima/",
                    dest,
                    use_cookies=True,
                )

    assert result.ok is True
    assert result.method == "page_pdf"
    assert dest.is_file()


@pytest.mark.integration
@pytest.mark.skipif(not COOKIES_PATH.is_file(), reason="no LinkedIn cookies — live download skipped")
@pytest.mark.asyncio
async def test_live_download_caio_profile(tmp_path):
    dest = tmp_path / "caiohandradelima-profile.pdf"
    result = await download_linkedin_profile_pdf(
        "https://www.linkedin.com/in/caiohandradelima/",
        dest,
        headless=True,
    )
    assert isinstance(result, PdfDownloadResult)
    if result.ok:
        assert dest.is_file()
        assert dest.stat().st_size > 500
