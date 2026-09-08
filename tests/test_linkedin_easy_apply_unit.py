#!/usr/bin/env python3
"""Unit tests for linkedin_easy_apply wizard helpers."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from patchright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

pytestmark = [pytest.mark.browser]


async def _page(html_name: str):
    uri = (ROOT / "tests" / "fixtures" / "linkedin" / html_name).resolve().as_uri()
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    page = await browser.new_page()
    await page.goto(uri, wait_until="domcontentloaded")
    return pw, browser, page


def test_detect_next_on_contact_step():
    from linkedin_easy_apply import detect_wizard_button

    async def run():
        pw, browser, page = await _page("job-easy-apply-step1.html")
        try:
            return await detect_wizard_button(page)
        finally:
            await browser.close()
            await pw.stop()

    assert asyncio.run(run()) == "next"


def test_detect_submit_on_review_step():
    from linkedin_easy_apply import detect_wizard_button

    async def run():
        pw, browser, page = await _page("job-easy-apply-review.html")
        try:
            return await detect_wizard_button(page)
        finally:
            await browser.close()
            await pw.stop()

    assert asyncio.run(run()) == "submit"


def test_wizard_dry_run_does_not_submit():
    from linkedin_easy_apply import run_wizard

    async def run():
        pw, browser, page = await _page("job-easy-apply-review.html")
        try:
            profile = {"email": "you@example.com", "phone": "+1 555 000 0000", "resume_path": "/tmp/nope.pdf"}
            return await run_wizard(page, profile, {}, track_id="ai-engineer", send=False)
        finally:
            await browser.close()
            await pw.stop()

    result = asyncio.run(run())
    assert result["ok"] is True
    assert result["submitted"] is True  # dry-run marks would-submit
    assert any(s.get("dry_run") for s in result["log"] if isinstance(s, dict))


def test_open_flow_recipe_exists():
    from flow_runner import resolve_recipe

    recipe = resolve_recipe("https://www.linkedin.com/jobs/view/123/", name="linkedin-easy-apply-open")
    assert recipe is not None
    assert recipe["name"] == "linkedin-easy-apply-open"
