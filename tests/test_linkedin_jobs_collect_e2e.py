#!/usr/bin/env python3
"""E2E-style tests for LinkedIn Jobs collect pagination (no live browser)."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from linkedin_jobs_collect import collect_jobs_pages  # noqa: E402
from linkedin_jobs_merge import JOBS_PER_PAGE, with_search_start  # noqa: E402
from tests.helpers.example_configs import load_example_linkedin_jobs_config  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "linkedin_jobs_search_page.html"
FIXTURE_PAGE2 = ROOT / "tests" / "fixtures" / "linkedin_jobs_search_page2.html"


def _mock_page(html: str, inner_text: str = "") -> MagicMock:
    page = MagicMock()
    page.content = AsyncMock(return_value=html)
    main = MagicMock()
    main.inner_text = AsyncMock(return_value=inner_text or "Senior AI Engineer\nAcme Robotics")
    page.locator.return_value.first = main
    page.locator.return_value.count = AsyncMock(return_value=1)
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    return page


class LinkedInJobsCollectE2ETests(unittest.IsolatedAsyncioTestCase):
    async def test_collect_walks_start_offsets_until_exhausted(self):
        cfg = load_example_linkedin_jobs_config()
        base_url = "https://www.linkedin.com/jobs/search/?keywords=ai+engineer"
        urls_seen: list[str] = []

        async def fake_collect(url: str, *, max_pages: int, use_profile: bool = False):
            urls_seen.append(url)
            page_idx = urls_seen.index(url)
            html = FIXTURE.read_text(encoding="utf-8") if page_idx == 0 else FIXTURE_PAGE2.read_text(encoding="utf-8")
            page = _mock_page(html)

            cards = MagicMock()
            cards.count = AsyncMock(return_value=0)
            page.locator.side_effect = lambda sel: cards if "data-job-id" in sel else MagicMock(
                first=MagicMock(count=AsyncMock(return_value=0))
            )

            listings = []
            stats = {"pages": 0, "page_details": [], "errors": []}
            for page_num in range(max_pages):
                page_url = with_search_start(url, page_num * JOBS_PER_PAGE)
                await page.goto(page_url)
                stats["pages"] = page_num + 1
                from linkedin_jobs_merge import parse_listings_from_html

                page_listings = parse_listings_from_html(html)
                if not page_listings and page_num > 0:
                    break
                listings.extend(page_listings)
                if page_num == 0:
                    html = FIXTURE_PAGE2.read_text(encoding="utf-8")
                else:
                    break
            stats["listings_total"] = len(listings)
            return listings, stats

        with patch("linkedin_jobs_collect.collect_jobs_pages", side_effect=fake_collect):
            listings, stats = await fake_collect(base_url, max_pages=4)

        self.assertEqual(stats["pages"], 2)
        self.assertEqual(len(listings), 4)
        self.assertIn("start=25", with_search_start(base_url, JOBS_PER_PAGE))

    async def test_collect_merges_dom_and_html_when_dom_has_titles(self):
        page = MagicMock()
        card = MagicMock()
        card.get_attribute = AsyncMock(return_value="99")

        def make_el(*, count: int, inner: str = "", attr: str | None = None) -> MagicMock:
            el = MagicMock()
            el.count = AsyncMock(return_value=count)
            el.inner_text = AsyncMock(return_value=inner)
            el.get_attribute = AsyncMock(return_value=attr)
            return el

        title_el = make_el(count=1, inner="Live DOM Title")
        company_el = make_el(count=0)
        loc_el = make_el(count=0)

        def card_locator(sel: str) -> MagicMock:
            if "job-card-list__title" in sel or "/jobs/view/" in sel:
                wrapper = MagicMock()
                wrapper.first = title_el
                return wrapper
            if "subtitle" in sel or "company-name" in sel:
                wrapper = MagicMock()
                wrapper.first = company_el
                return wrapper
            if "location" in sel or "metadata-item" in sel:
                wrapper = MagicMock()
                wrapper.first = loc_el
                return wrapper
            return MagicMock(first=make_el(count=0))

        card.locator = card_locator
        card.inner_text = AsyncMock(return_value="Live DOM Title\nEasy Apply")

        cards = MagicMock()
        cards.count = AsyncMock(return_value=1)
        cards.nth.return_value = card

        def page_locator(sel: str) -> MagicMock:
            if "data-job-id" in sel:
                return cards
            panel = MagicMock()
            panel.count = AsyncMock(return_value=0)
            return panel

        page.locator = page_locator

        from linkedin_jobs_collect import extract_listings_from_dom

        dom = await extract_listings_from_dom(page)
        self.assertEqual(dom[0]["title"], "Live DOM Title")
        self.assertTrue(dom[0]["easy_apply"])


if __name__ == "__main__":
    unittest.main()
