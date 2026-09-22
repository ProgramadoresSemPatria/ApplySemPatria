"""Mocked collect_jobs_pages coverage."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from linkedin_jobs_collect import collect_jobs_pages  # noqa: E402

FIXTURE = (
    __import__("pathlib").Path(__file__).resolve().parents[1]
    / "fixtures"
    / "linkedin_jobs_search_page.html"
)


@pytest.mark.asyncio
async def test_collect_jobs_pages_parses_fixture_html():
    html = FIXTURE.read_text(encoding="utf-8")

    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.content = AsyncMock(return_value=html)

    cards = MagicMock()
    cards.count = AsyncMock(return_value=0)
    next_btn = MagicMock()
    next_btn.count = AsyncMock(return_value=0)

    def page_locator(sel: str) -> MagicMock:
        loc = MagicMock()
        if sel == "main":
            loc.inner_text = AsyncMock(return_value="AI Engineer\nAcme")
            loc.first = loc
            return loc
        if "data-job-id" in sel:
            return cards
        if "View next page" in sel or "Next" in sel:
            return next_btn
        panel = MagicMock()
        panel.count = AsyncMock(return_value=0)
        panel.first = panel
        return panel

    page.locator = page_locator

    context = MagicMock()
    context.pages = []
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()

    p = MagicMock()

    @asynccontextmanager
    async def fake_playwright():
        yield p

    with patch("patchright.async_api.async_playwright", fake_playwright):
        with patch("linkedin_jobs_collect._launch_context", AsyncMock(return_value=(context, {"auth_mode": "cookies", "errors": []}))):
            with patch("linkedin_jobs_collect.scroll_jobs_results", AsyncMock()):
                with patch("linkedin_jobs_collect.extract_listings_from_dom", AsyncMock(return_value=[])):
                    listings, stats = await collect_jobs_pages(
                        "https://www.linkedin.com/jobs/search/?keywords=ai",
                        max_pages=1,
                    )

    assert stats["pages"] == 1
    assert len(listings) >= 1
    assert listings[0].get("job_id")
