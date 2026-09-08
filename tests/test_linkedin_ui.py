#!/usr/bin/env python3
"""Unit tests for LinkedIn UI click helpers."""

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


async def _page(html_name: str, *, subdir: str = "linkedin"):
    uri = (ROOT / "tests" / "fixtures" / subdir / html_name).resolve().as_uri()
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    page = await browser.new_page()
    await page.goto(uri, wait_until="domcontentloaded")
    return pw, browser, page


def test_wait_for_job_detail_ready_fixture():
    from linkedin_ui import wait_for_job_detail_ready

    async def run():
        pw, browser, page = await _page("job-easy-apply-step1.html")
        try:
            return await wait_for_job_detail_ready(page, timeout_ms=5000)
        finally:
            await browser.close()
            await pw.stop()

    assert asyncio.run(run()) is True


def test_click_easy_apply_link_fixture():
    from linkedin_easy_apply import modal_visible
    from linkedin_ui import click_easy_apply_button

    async def run():
        pw, browser, page = await _page("job-easy-apply-link.html")
        try:
            click = await click_easy_apply_button(page)
            visible = await modal_visible(page)
            return click, visible
        finally:
            await browser.close()
            await pw.stop()

    click, visible = asyncio.run(run())
    assert click.get("clicked") is True
    assert "link" in str(click.get("strategy", ""))
    assert visible is True


def test_flow_recipe_has_easy_apply_steps():
    from flow_runner import resolve_recipe

    recipe = resolve_recipe("https://www.linkedin.com/jobs/view/123/", name="linkedin-easy-apply-open")
    actions = [s.get("action") for s in recipe.get("steps", [])]
    assert "wait_job_detail" in actions
    assert "click_easy_apply" in actions
