"""Extended coverage for linkedin jobs_collect (mocked browser)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from linkedin_jobs_collect import (  # noqa: E402
    _launch_context,
    backfill_job_ids,
    extract_listings_from_dom,
    listing_from_job_view,
    listings_to_jobs_preview,
    scroll_jobs_results,
)
from tests.helpers.example_configs import load_example_linkedin_jobs_config  # noqa: E402

FIXTURE = (
    __import__("pathlib").Path(__file__).resolve().parents[1]
    / "fixtures"
    / "linkedin_jobs_search_page.html"
)


def _card_mock(*, job_id: str = "123", title: str = "AI Engineer", easy_apply: bool = False):
    card = MagicMock()
    card.get_attribute = AsyncMock(return_value=job_id)
    card.scroll_into_view_if_needed = AsyncMock()
    card.inner_text = AsyncMock(return_value=f"{title}\n{'Easy Apply' if easy_apply else 'Apply on company website'}")

    def make_el(*, count: int, inner: str = "", attr: str | None = None) -> MagicMock:
        el = MagicMock()
        el.count = AsyncMock(return_value=count)
        el.inner_text = AsyncMock(return_value=inner)
        el.get_attribute = AsyncMock(return_value=attr)
        return el

    title_el = make_el(count=1, inner=title)
    company_el = make_el(count=1, inner="Acme Robotics")
    loc_el = make_el(count=1, inner="Brazil · Remote · 2 days ago")

    def card_locator(sel: str) -> MagicMock:
        if "job-card-list__title" in sel or "/jobs/view/" in sel:
            w = MagicMock()
            w.first = title_el
            return w
        if "subtitle" in sel or "company-name" in sel:
            w = MagicMock()
            w.first = company_el
            return w
        if "location" in sel or "metadata-item" in sel:
            w = MagicMock()
            w.first = loc_el
            return w
        return MagicMock(first=make_el(count=0))

    card.locator = card_locator
    return card


@pytest.mark.asyncio
async def test_scroll_jobs_results_scrolls_panel():
    page = MagicMock()
    panel = MagicMock()
    panel.count = AsyncMock(return_value=1)
    panel.evaluate = AsyncMock()
    page.locator.return_value.first = panel
    with patch("linkedin_jobs_collect.asyncio.sleep", new=AsyncMock()):
        await scroll_jobs_results(page)
    panel.evaluate.assert_awaited()


@pytest.mark.asyncio
async def test_extract_listings_from_dom_full_card():
    card = _card_mock(easy_apply=True)
    cards = MagicMock()
    cards.count = AsyncMock(return_value=1)
    cards.nth.return_value = card
    page = MagicMock()
    page.locator = MagicMock(return_value=cards)
    with patch("linkedin_jobs_collect.asyncio.sleep", new=AsyncMock()):
        listings = await extract_listings_from_dom(page)
    assert listings[0]["job_id"] == "123"
    assert listings[0]["easy_apply"] is True
    assert listings[0]["apply_method"] == "easy_apply"


@pytest.mark.asyncio
async def test_extract_listings_skips_empty_job_id():
    card = MagicMock()
    card.get_attribute = AsyncMock(return_value="")
    cards = MagicMock()
    cards.count = AsyncMock(return_value=1)
    cards.nth.return_value = card
    page = MagicMock()
    page.locator = MagicMock(return_value=cards)
    with patch("linkedin_jobs_collect.asyncio.sleep", new=AsyncMock()):
        listings = await extract_listings_from_dom(page)
    assert listings == []


@pytest.mark.asyncio
async def test_listing_from_job_view():
    page = MagicMock()
    page.goto = AsyncMock()
    main = MagicMock()
    main.inner_text = AsyncMock(return_value="Acme\nSenior AI Engineer\nBrazil · Remote · 1 day ago\nEasy Apply")
    h1 = MagicMock()
    h1.count = AsyncMock(return_value=1)
    h1.inner_text = AsyncMock(return_value="Senior AI Engineer")

    def page_locator(sel: str) -> MagicMock:
        if sel == "main":
            w = MagicMock()
            w.inner_text = main.inner_text
            return w
        w = MagicMock()
        w.first = h1
        w.count = AsyncMock(return_value=1 if "h1" in sel else 0)
        return w

    page.locator = page_locator
    with patch("linkedin_jobs_collect.asyncio.sleep", new=AsyncMock()):
        item = await listing_from_job_view(page, "4464387581")
    assert item is not None
    assert item["job_id"] == "4464387581"
    assert "Engineer" in item["title"]


@pytest.mark.asyncio
async def test_launch_context_with_cookies(monkeypatch):
    p = MagicMock()
    browser = MagicMock()
    context = MagicMock()
    context.add_cookies = AsyncMock()
    browser.new_context = AsyncMock(return_value=context)
    p.chromium.launch = AsyncMock(return_value=browser)
    monkeypatch.setattr("linkedin_jobs_collect.load_cookies", lambda: [{"name": "li_at", "value": "x", "domain": ".linkedin.com"}])
    monkeypatch.setattr("linkedin_jobs_collect.PROFILE_DIR", __import__("pathlib").Path("/nonexistent-profile"))
    ctx, stats = await _launch_context(p, use_profile=False)
    assert stats["auth_mode"] == "cookies"
    context.add_cookies.assert_awaited()


@pytest.mark.asyncio
async def test_backfill_job_ids_empty():
    listings, stats = await backfill_job_ids([])
    assert listings == []
    assert stats["backfill_ids"] == []


def test_listings_to_jobs_preview():
    cfg = load_example_linkedin_jobs_config()
    listings = [
        {
            "job_id": "4464387581",
            "url": "https://www.linkedin.com/jobs/view/4464387581/",
            "title": "AI Engineer",
            "company": "Acme",
            "location": "Remote",
            "posted_label": "1d",
            "easy_apply": True,
            "apply_method": "easy_apply",
        }
    ]
    meta = {"query": "ai engineer", "role_keyword": "ai engineer", "region": "latam", "track": "ai-engineer"}
    with patch("linkedin_jobs_collect.load_linkedin_jobs_config", return_value=cfg):
        jobs = listings_to_jobs_preview(listings, meta, max_roles=5, track_id="ai-engineer")
    assert len(jobs) >= 1
    assert jobs[0]["source"] == "linkedin_jobs"
