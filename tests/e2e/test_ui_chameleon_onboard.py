"""CV Chameleon LinkedIn onboard e2e — UI-21..23."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.helpers.ui_e2e import wait_for_toast_text

pytestmark = pytest.mark.playwright


def test_chameleon_setup_modal_shows_import_button(mock_ui_server_chameleon_not_ready, page: Page):
    port, _captured = mock_ui_server_chameleon_not_ready
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.locator(".chameleon-link").first.click()
    expect(page.locator("#chameleonModal")).to_be_visible()
    expect(page.locator("#chameleonModalImport")).to_contain_text("Import from LinkedIn")


def test_chameleon_onboard_posts_and_closes_modal(mock_ui_server_chameleon_onboard, page: Page):
    port, captured = mock_ui_server_chameleon_onboard
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.locator(".chameleon-link").first.click()
    expect(page.locator("#chameleonModal")).to_be_visible()
    page.locator("#chameleonModalImport").click()
    wait_for_toast_text(page, "ready", timeout_ms=15000)
    expect(page.locator("#chameleonModal")).to_be_hidden()
    assert captured.get("last_chameleon_onboard", {}).get("track_id") == "ai-engineer"


def test_chameleon_onboard_updates_meta_ready(mock_ui_server_chameleon_onboard, page: Page):
    port, _captured = mock_ui_server_chameleon_onboard
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.locator(".chameleon-link").first.click()
    page.locator("#chameleonModalImport").click()
    wait_for_toast_text(page, "ready", timeout_ms=15000)
    meta = page.evaluate(
        """async () => {
          const res = await fetch('/api/meta');
          return res.json();
        }"""
    )
    assert meta.get("version") >= 10
