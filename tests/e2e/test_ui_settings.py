"""Settings page Playwright e2e — UI-14..20."""

from __future__ import annotations

import json
import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.playwright

SETTINGS_SECTIONS = (
    "section#pipeline",
    "section#profile",
    "section#messages",
    "section#answers",
    "section#linkedin",
    "section#dm",
    "section#email",
    "section#board",
    "section#google",
    "section#form-rules",
)


def test_settings_all_sections_visible(mock_ui_server, page: Page):
    port, _captured = mock_ui_server
    page.goto(f"http://127.0.0.1:{port}/settings.html", wait_until="networkidle")
    for selector in SETTINGS_SECTIONS:
        expect(page.locator(selector)).to_be_visible(timeout=10000)


def test_settings_track_selector_lists_tracks(mock_ui_server, page: Page):
    port, _captured = mock_ui_server
    page.goto(f"http://127.0.0.1:{port}/settings.html", wait_until="networkidle")
    options = page.locator("#trackSelect option")
    expect(options).not_to_have_count(0)
    expect(options.first).to_contain_text("AI Engineer")


def test_settings_pipeline_flags_render(mock_ui_server, page: Page):
    port, _captured = mock_ui_server
    page.goto(f"http://127.0.0.1:{port}/settings.html", wait_until="networkidle")
    expect(page.locator("#pipeline .flag-pill")).not_to_have_count(0)
    expect(page.locator("#pipeline")).to_contain_text("job seeker")


def test_settings_dm_preview_visible(mock_ui_server, page: Page):
    port, _captured = mock_ui_server
    page.goto(f"http://127.0.0.1:{port}/settings.html", wait_until="networkidle")
    preview = page.locator("#dmPreview")
    expect(preview).to_be_visible()
    expect(preview).not_to_be_empty()


def test_settings_save_linkedin_toggle_records_api(mock_ui_server, page: Page):
    port, captured = mock_ui_server
    page.goto(f"http://127.0.0.1:{port}/settings.html", wait_until="networkidle")
    toggle = page.locator("#llm_intent_classify_enabled")
    toggle.wait_for(state="attached", timeout=10000)
    if not toggle.is_checked():
        page.locator("section#linkedin label.switch").filter(has=page.locator("#llm_intent_classify_enabled")).click()
    page.locator('#linkedin button.save-btn[data-section="linkedin"]').click()
    page.wait_for_function(
        "() => document.getElementById('toast')?.classList.contains('show')",
        timeout=10000,
    )
    saves = captured.get("config_saves") or []
    assert any(s.get("section") == "linkedin" for s in saves)
    linkedin_save = next(s for s in saves if s.get("section") == "linkedin")
    assert linkedin_save["payload"].get("llm_intent_classify_enabled") is True
    expect(toggle).to_be_checked()


def test_settings_round_trip_to_dashboard(mock_ui_server, page: Page):
    port, _captured = mock_ui_server
    page.goto(f"http://127.0.0.1:{port}/settings.html", wait_until="networkidle")
    page.locator('a.nav-link[href="index.html"]').click()
    page.wait_for_url(re.compile(r"/(index\.html)?$"), timeout=10000)
    expect(page.locator(".brand h1")).to_contain_text("Jobsearch")
    expect(page.locator('a.config-link[href="settings.html"]')).to_be_visible()


def test_dashboard_config_icon_has_aria_label(mock_ui_server, page: Page):
    port, _captured = mock_ui_server
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    link = page.locator('a.config-link[href="settings.html"]')
    expect(link).to_have_attribute("aria-label", "Configuration")


def test_settings_form_rules_editor_is_valid_json(mock_ui_server, page: Page):
    port, _captured = mock_ui_server
    page.goto(f"http://127.0.0.1:{port}/settings.html", wait_until="networkidle")
    raw = page.locator("#rulesJson").input_value()
    parsed = json.loads(raw)
    assert isinstance(parsed, list)
