"""LinkedIn Jobs UI e2e — LJ-UI-01..04 source + Posted 24h filters."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.playwright


def test_lj_ui00_all_selected_by_default(mock_ui_server_linkedin_jobs, page: Page):
    port, _captured = mock_ui_server_linkedin_jobs
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.wait_for_selector(".card", timeout=10000)
    expect(page.locator('.chip[data-filter="all"]')).to_have_class(re.compile(r"\bactive\b"))
    expect(page.locator(".card")).to_have_count(4)
    page.locator('.chip[data-filter="all"]').click()
    expect(page.locator('.chip[data-filter="all"]')).to_have_class(re.compile(r"\bactive\b"))
    expect(page.locator(".card")).to_have_count(4)


def test_lj_ui01_source_filter_linkedin_jobs(mock_ui_server_linkedin_jobs, page: Page):
    port, _captured = mock_ui_server_linkedin_jobs
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.wait_for_selector(".card", timeout=10000)
    expect(page.locator(".card")).to_have_count(4)

    page.locator('.chip-source[data-source="linkedin_jobs"]').click()
    expect(page.locator(".card")).to_have_count(3)
    expect(page.locator(".card-company").first).to_contain_text("Tata Consultancy Services")
    expect(page.locator(".card-title").first).to_contain_text("AI Engineer")


def test_lj_ui02_posted_24h_filter(mock_ui_server_linkedin_jobs, page: Page):
    port, _captured = mock_ui_server_linkedin_jobs
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.wait_for_selector(".card", timeout=10000)

    page.locator('.chip[data-filter="posted_24h"]').click()
    expect(page.locator(".card")).to_have_count(2)
    roles = page.locator(".card-title").all_text_contents()
    assert any("AI Engineer" in r for r in roles)
    assert any("Forward Deployed" in r for r in roles)


def test_lj_ui03_single_filter_replaces_previous(mock_ui_server_linkedin_jobs, page: Page):
    """Only one chip active at a time — Posted 24h replaces LinkedIn jobs, not AND."""
    port, _captured = mock_ui_server_linkedin_jobs
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.wait_for_selector(".card", timeout=10000)

    page.locator('.chip-source[data-source="linkedin_jobs"]').click()
    expect(page.locator(".card")).to_have_count(3)
    expect(page.locator('.chip-source[data-source="linkedin_jobs"]')).to_have_class(re.compile(r"\bactive\b"))

    page.locator('.chip[data-filter="posted_24h"]').click()
    expect(page.locator(".card")).to_have_count(2)
    expect(page.locator('.chip[data-filter="posted_24h"]')).to_have_class(re.compile(r"\bactive\b"))
    expect(page.locator('.chip-source[data-source="linkedin_jobs"]')).not_to_have_class(re.compile(r"\bactive\b"))

    page.locator('.chip[data-filter="all"]').click()
    expect(page.locator('.chip[data-filter="all"]')).to_have_class(re.compile(r"\bactive\b"))
    expect(page.locator(".card")).to_have_count(4)


def test_lj_ui04_old_job_hidden_by_posted_24h(mock_ui_server_linkedin_jobs, page: Page):
    port, _captured = mock_ui_server_linkedin_jobs
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.wait_for_selector(".card", timeout=10000)

    page.locator('.chip[data-filter="posted_24h"]').click()
    expect(page.get_by_text("Staff ML Engineer")).to_have_count(0)
    expect(page.locator(".card")).to_have_count(2)


def test_lj_ui05_settings_linkedin_jobs_fields(mock_ui_server, page: Page):
    port, _captured = mock_ui_server
    page.goto(f"http://127.0.0.1:{port}/settings.html", wait_until="networkidle")
    expect(page.locator("#linkedin-jobs")).to_be_visible()
    expect(page.locator("#lj_default_period_days")).to_have_value("1")
    expect(page.locator("#lj_salary_filter")).to_have_value(re.compile(r"f_SA_id"))
