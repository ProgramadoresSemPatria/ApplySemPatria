"""Applications dashboard Playwright e2e — UI-01..04."""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.playwright


def test_dashboard_loads_meta_and_cards(mock_ui_server, page):
    port = mock_ui_server
    page.goto(f"http://127.0.0.1:{port}/")
    page.wait_for_selector(".card", timeout=10000)
    assert page.locator("#serverStale").is_hidden()
    assert "Acme AI" in page.locator(".card-company").first.inner_text()


def test_tap_connect_posts_action(mock_ui_server, page):
    port = mock_ui_server
    page.goto(f"http://127.0.0.1:{port}/")
    page.wait_for_selector(".step-pill.clickable", timeout=10000)

    with page.expect_request(lambda r: "/api/action" in r.url and r.method == "POST") as req_info:
        page.locator('.step-pill[data-action="dm_connect"]').first.click()

    req = req_info.value
    body = json.loads(req.post_data or "{}")
    assert body.get("action") == "dm_connect"
    assert body.get("job_key")


def test_card_survives_after_action(mock_ui_server, page):
    port = mock_ui_server
    page.goto(f"http://127.0.0.1:{port}/")
    page.wait_for_selector(".card", timeout=10000)
    wrap = page.locator("#cardsWrap")
    scroll_before = wrap.evaluate("el => el.scrollTop")
    page.locator('.step-pill[data-action="dm_connect"]').first.click()
    page.wait_for_timeout(800)
    assert page.locator(".card").count() >= 1
    scroll_after = wrap.evaluate("el => el.scrollTop")
    assert scroll_after == scroll_before
