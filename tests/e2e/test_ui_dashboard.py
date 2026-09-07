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
    expect(page.locator('.day-btn.active')).to_have_attribute("data-day", "2026-09-07")
    expect(page.locator('.day-btn[data-day="2026-09-07"] .meta')).to_contain_text("no research yet")


def test_select_past_day_while_today_pending(mock_ui_server_needs_research, page: Page):
    port, _captured = mock_ui_server_needs_research
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.locator('.day-btn[data-day="2026-09-06"]').click()
    expect(page.locator("#researchPrompt")).to_be_hidden()
    expect(page.locator("#listContent")).to_be_visible()
    page.wait_for_selector(".card", timeout=10000)
    expect(page.locator('.day-btn.active')).to_have_attribute("data-day", "2026-09-06")


def test_research_button_shows_progress_and_completes(mock_ui_server_research_flow, page: Page):
    port, captured = mock_ui_server_research_flow
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.locator("#runResearchBtn").click()
    expect(page.locator("#runResearchBtn")).to_be_disabled()
    expect(page.locator("#researchProgressText")).to_contain_text("LinkedIn", timeout=8000)
    expect(page.locator("#listContent")).to_be_visible(timeout=15000)
    expect(page.locator("#researchPrompt")).to_be_hidden()
    expect(page.locator(".card")).to_have_count(1)
    assert captured.get("last_research", {}).get("ok") is True


def test_dm_message_pill_done_when_already_sent(mock_ui_server_dm_sent, page: Page):
    port, _captured = mock_ui_server_dm_sent
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    msg_pill = page.locator('.step-pill[data-action="dm_message"]').first
    msg_pill.wait_for(state="visible", timeout=10000)
    expect(msg_pill).to_have_class(re.compile(r"done"))
    expect(msg_pill.locator(".step-status")).to_contain_text("sent")


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

