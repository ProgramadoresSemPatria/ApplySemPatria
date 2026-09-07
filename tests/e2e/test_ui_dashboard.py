"""Applications dashboard Playwright e2e — UI-01..05, UI-13."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.helpers.ui_e2e import wait_for_mock_action, wait_for_mock_bulk_action

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


def test_research_prompt_when_no_research_today(mock_ui_server_needs_research, page: Page):
    port, _captured = mock_ui_server_needs_research
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    expect(page.locator("#researchPrompt")).to_be_visible()
    expect(page.locator("#runResearchBtn")).to_contain_text("Make a research today")
    expect(page.locator("#listContent")).to_be_hidden()
    expect(page.locator(".card")).to_have_count(0)


def test_bulk_dm_button_triggers_process_all(mock_ui_server, page: Page):
    port, captured = mock_ui_server
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    expect(page.locator(".list-header #viewTitle")).to_contain_text("Applications")
    expect(page.locator(".list-header #bulkDmBtn")).to_be_visible()
    bulk_btn = page.locator(".list-header #bulkDmBtn")
    bulk_btn.click()
    bulk = wait_for_mock_bulk_action(captured, page)

    assert bulk["action"] == "dm_process_all"
    assert bulk["job_keys"] == ["ai-engineer|linkedin|acme ai|ai engineer"]
    expect(page.locator("#bulkDmBtn")).not_to_be_disabled()

