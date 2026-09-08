"""Form status override menu e2e."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.playwright


def test_form_status_menu_marks_applied(mock_ui_server, monkeypatch, tmp_path: Path, page: Page):
    monkeypatch.setattr("form_apply_state.URL_APPLICATIONS_PATH", tmp_path / "url-applications.json")

    port, _captured = mock_ui_server
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.wait_for_selector(".card-menu-btn", timeout=10000)
    page.locator(".card-menu-btn").first.click()
    btn = page.locator('.card-menu button[data-form-applied="1"]')
    expect(btn).to_be_visible()
    expect(btn).to_contain_text("Mark form as applied")
    btn.click()
    page.locator(".card-menu-btn").first.click()
    expect(page.locator('.card-menu button[data-form-applied="0"]')).to_contain_text("Mark form as not applied")
