"""Applications dashboard Playwright e2e — UI-01..04."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.helpers.ui_e2e import wait_for_mock_action

pytestmark = pytest.mark.playwright


def test_dashboard_loads_meta_and_cards(mock_ui_server, page: Page):
    port, _captured = mock_ui_server
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.wait_for_selector(".card", timeout=10000)
    expect(page.locator("#serverStale")).to_be_hidden()
    expect(page.locator(".card-company").first).to_contain_text("Acme AI")


def test_tap_connect_posts_action(mock_ui_server, page: Page):
    port, captured = mock_ui_server
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    pill = page.locator('.step-pill[data-action="dm_connect"]').first
    pill.wait_for(state="visible", timeout=10000)
    expect(pill).to_have_class(re.compile(r"clickable"))

    pill.click()
    action = wait_for_mock_action(captured, page)

    assert action["action"] == "dm_connect"
    assert action["job_key"]


def test_card_survives_after_action(mock_ui_server, page: Page):
    port, captured = mock_ui_server
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.wait_for_selector(".card", timeout=10000)
    wrap = page.locator("#cardsWrap")
    scroll_before = wrap.evaluate("el => el.scrollTop")
    page.locator('.step-pill[data-action="dm_connect"]').first.click()
    wait_for_mock_action(captured, page)
    expect(page.locator(".card")).not_to_have_count(0)
    assert wrap.evaluate("el => el.scrollTop") == scroll_before
