"""E2E: LinkedIn ingestion failure must not show a false success toast (UI-20)."""

from __future__ import annotations

import re
import time
from typing import Any, Generator
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Page, expect

from tests.conftest import _start_mock_ui_server
from tests.helpers.ui_e2e import wait_for_toast_text

pytestmark = pytest.mark.playwright


@pytest.fixture
def mock_ui_server_research_linkedin_fail(monkeypatch, tmp_path) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Research spawn completes with linkedin failure (ok=false)."""
    import ui_server
    from research_log import finish_research_run, join_research_run, set_research_step

    fail_msg = (
        "Research failed — LinkedIn ingestion did not complete.\n"
        "LinkedIn collect: patchright install chromium"
    )

    def fake_spawn_daily_research(**_kwargs):
        join_research_run("2026-09-07")
        set_research_step("linkedin_collect")
        time.sleep(0.35)
        finish_research_run(ok=False, message=fail_msg)
        mock_proc = MagicMock()
        mock_proc.pid = 5150
        mock_proc.poll.return_value = 1
        return mock_proc

    monkeypatch.setattr(ui_server, "spawn_daily_research", fake_spawn_daily_research)
    run_path = tmp_path / "state" / "research-run.json"
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-07",
        has_research_today=False,
        last_research_day="2026-09-06",
        research_run_path=run_path,
    )


def test_linkedin_failure_shows_error_toast_not_success(mock_ui_server_research_linkedin_fail, page: Page):
    port, _captured = mock_ui_server_research_linkedin_fail
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.locator("#runResearchBtn").click()
    expect(page.locator("#runResearchBtn")).to_be_disabled(timeout=5000)
    wait_for_toast_text(page, "LinkedIn ingestion did not complete")
    toast = page.locator("#toast.show")
    expect(toast).to_have_class(re.compile(r"\berr\b"))
    expect(toast).not_to_contain_text("Research complete for")


def test_linkedin_failure_keeps_today_research_prompt(mock_ui_server_research_linkedin_fail, page: Page):
    port, _captured = mock_ui_server_research_linkedin_fail
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.locator("#runResearchBtn").click()
    wait_for_toast_text(page, "LinkedIn ingestion did not complete")
    expect(page.locator("#researchPrompt")).to_be_visible()
    expect(page.locator("#listContent")).to_be_hidden()
    expect(page.locator(".card")).to_have_count(0)
    expect(page.locator('.day-btn[data-day="2026-09-07"] .meta')).to_contain_text("no research yet")
