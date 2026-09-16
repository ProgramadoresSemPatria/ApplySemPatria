"""E2E: Tag as applied + Send for Applika tracking steps (UI-17..19)."""

from __future__ import annotations

from typing import Any, Generator

import pytest
from playwright.sync_api import Page, expect

from tests.conftest import _start_mock_ui_server
from tests.helpers.ui_e2e import wait_for_mock_action, wait_for_toast_text

pytestmark = pytest.mark.playwright

_APPLIKA_META = {
    "ui_approval": True,
    "version": 8,
    "bulk_actions": ["dm_process_all", "email_process_all"],
    "applika_sync_enabled": True,
    "chameleon": {"ready": False},
}


@pytest.fixture
def mock_ui_server_applika(monkeypatch) -> Generator[tuple[int, dict[str, Any]], None, None]:
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-06",
        has_research_today=True,
        last_research_day="2026-09-06",
        meta_override=_APPLIKA_META,
    )


@pytest.fixture
def mock_ui_server_applika_retry(monkeypatch) -> Generator[tuple[int, dict[str, Any]], None, None]:
    from registry import job_key as registry_job_key
    from tests.helpers.jobs import linkedin_dm_job, ui_snapshot_applika_retry

    jk = registry_job_key(linkedin_dm_job())
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-06",
        has_research_today=True,
        last_research_day="2026-09-06",
        snapshot_override=ui_snapshot_applika_retry(jk),
        meta_override=_APPLIKA_META,
    )


def test_tag_applied_pill_visible_on_all_cards(mock_ui_server_applika, page: Page):
    port, _captured = mock_ui_server_applika
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    pill = page.locator('.step-pill[data-action="tag_applied"]').first
    expect(pill).to_be_visible()
    expect(pill).to_contain_text("Tag as applied")


def test_tap_tag_applied_posts_action(mock_ui_server_applika, page: Page):
    port, captured = mock_ui_server_applika
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.locator('.step-pill[data-action="tag_applied"]').first.click()
    action = wait_for_mock_action(captured, page)
    assert action["action"] == "tag_applied"


def test_applika_retry_pill_posts_action(mock_ui_server_applika_retry, page: Page):
    port, captured = mock_ui_server_applika_retry
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.locator('.step-pill[data-action="applika"]').first.click()
    action = wait_for_mock_action(captured, page)
    assert action["action"] == "applika_send"


def test_tag_applied_applika_error_shows_toast(mock_ui_server_applika, monkeypatch, page: Page):
    port, _captured = mock_ui_server_applika

    def fake_run_action(action, jk, track=None):
        return {
            "ok": True,
            "applika_error": True,
            "message": "Tagged as applied. Applika sync failed: CLI failed",
            "action": action,
            "job_key": jk,
        }

    monkeypatch.setattr("ui_server.run_action", fake_run_action)
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.locator('.step-pill[data-action="tag_applied"]').first.click()
    wait_for_toast_text(page, "Applika sync failed")
