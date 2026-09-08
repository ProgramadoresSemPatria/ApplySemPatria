"""CV Chameleon Playwright e2e — UI chameleon button + stale-server hint."""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import Page, expect

from tests.helpers.ui_e2e import wait_for_toast_text

pytestmark = pytest.mark.playwright


def _wait_for_chameleon_generate(captured: dict, page: Page, *, timeout_ms: int = 10_000) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if captured.get("last_chameleon"):
            return
        page.wait_for_timeout(50)
    pytest.fail(f"chameleon generate not recorded within {timeout_ms}ms")


def test_chameleon_button_visible(mock_ui_server_chameleon, page: Page):
    port, _captured = mock_ui_server_chameleon
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.wait_for_selector(".chameleon-link", timeout=10000)
    expect(page.locator(".chameleon-link").first).to_contain_text("CV Chameleon")


def test_chameleon_generate_posts_and_updates_label(mock_ui_server_chameleon, page: Page):
    port, captured = mock_ui_server_chameleon
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    btn = page.locator(".chameleon-link").first
    btn.wait_for(state="visible", timeout=10000)
    btn.click()
    _wait_for_chameleon_generate(captured, page)
    assert captured.get("last_chameleon", {}).get("job_key")
    expect(btn).to_contain_text("CV Chameleon ↓", timeout=10000)


def test_chameleon_setup_modal_when_not_ready(mock_ui_server_chameleon_not_ready, page: Page):
    port, _captured = mock_ui_server_chameleon_not_ready
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.locator(".chameleon-link").first.click()
    expect(page.locator("#chameleonModal")).to_be_visible()
    expect(page.locator("#chameleonModalTitle")).to_contain_text("Set up CV Chameleon")


def test_chameleon_stale_server_shows_restart_hint(mock_ui_server_stale_meta, page: Page):
    port, _captured = mock_ui_server_stale_meta
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.wait_for_selector(".chameleon-link", timeout=10000)
    page.locator(".chameleon-link").first.click()
    wait_for_toast_text(page, "restart", timeout_ms=10000)
    expect(page.locator("#serverStale")).to_be_visible()


def test_meta_includes_chameleon_on_ready_server(mock_ui_server_chameleon, page: Page):
    port, _captured = mock_ui_server_chameleon
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    meta = page.evaluate(
        """async () => {
          const res = await fetch('/api/meta');
          return res.json();
        }"""
    )
    assert meta["chameleon"]["ready"] is True
    assert meta["version"] >= 7
