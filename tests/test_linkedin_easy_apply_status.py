#!/usr/bin/env python3
"""Tests for LinkedIn Easy Apply status probing."""

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


def test_classify_available_link():
    from linkedin_easy_apply_status import probe_easy_apply_status

    async def run():
        pw, browser, page = await _page("job-easy-apply-link.html")
        try:
            return await probe_easy_apply_status(page, page.url)
        finally:
            await browser.close()
            await pw.stop()

    result = asyncio.run(run())
    assert result["status"] == "available"
    assert result["easy_apply_enabled"] is True


def test_classify_applied():
    from linkedin_easy_apply_status import probe_easy_apply_status

    async def run():
        pw, browser, page = await _page("job-easy-apply-applied.html")
        try:
            return await probe_easy_apply_status(page, page.url)
        finally:
            await browser.close()
            await pw.stop()

    result = asyncio.run(run())
    assert result["status"] == "applied"
    assert result["easy_apply_enabled"] is False


def test_classify_closed():
    from linkedin_easy_apply_status import probe_easy_apply_status

    async def run():
        pw, browser, page = await _page("job-easy-apply-closed.html")
        try:
            return await probe_easy_apply_status(page, page.url)
        finally:
            await browser.close()
            await pw.stop()

    result = asyncio.run(run())
    assert result["status"] == "closed"


def test_easy_apply_form_action_labels():
    from applications_ui_data import _easy_apply_form_action

    available = _easy_apply_form_action(
        {"linkedin_easy_apply": True},
        form_submitted=False,
        ea_record={"status": "available", "status_text": "Easy Apply open", "easy_apply_enabled": True},
    )
    assert available["label"] == "Update Easy Apply status"
    assert available["status_kind"] == "available"

    applied = _easy_apply_form_action(
        {"linkedin_easy_apply": True},
        form_submitted=False,
        ea_record={"status": "applied", "status_text": "Applied on LinkedIn"},
    )
    assert applied["done"] is True
    assert applied["status_kind"] == "applied"
