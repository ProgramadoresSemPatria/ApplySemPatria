"""E2E: stale failed research run must not flash a false error toast on new spawn (UI-25)."""

from __future__ import annotations

import json
import time
from typing import Any, Generator
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Page, expect

from tests.conftest import _start_mock_ui_server
pytestmark = pytest.mark.playwright


@pytest.fixture
def mock_ui_server_research_stale_false_failure(
    monkeypatch, tmp_path
) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Prior failed run on disk; new spawn should not surface that message immediately."""
    import ui_server
    from research_log import finish_research_run, join_research_run, set_research_step

    run_path = tmp_path / "state" / "research-run.json"
    run_path.parent.mkdir(parents=True)
    run_path.write_text(
        json.dumps(
            {
                "running": False,
                "day": "2026-09-07",
                "step": "failed",
                "ok": False,
                "message": "Research failed — LinkedIn ingestion did not complete.",
                "started_at": "2026-09-07T10:00:00-03:00",
                "updated_at": "2026-09-07T10:05:00-03:00",
                "version": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    stale_msg = "Research failed — LinkedIn ingestion did not complete."

    def fake_spawn_daily_research(**_kwargs):
        time.sleep(0.35)
        join_research_run("2026-09-07")
        set_research_step("linkedin_collect")
        time.sleep(0.35)
        finish_research_run(
            ok=True,
            message="Research complete for 2026-09-07: 1 roles in apply table.",
        )
        mock_proc = MagicMock()
        mock_proc.pid = 5252
        mock_proc.poll.return_value = 0
        return mock_proc

    monkeypatch.setattr(ui_server, "spawn_daily_research", fake_spawn_daily_research)
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-07",
        has_research_today=False,
        last_research_day="2026-09-06",
        research_run_path=run_path,
    )


def test_stale_failure_does_not_flash_error_toast(mock_ui_server_research_stale_false_failure, page: Page):
    port, _captured = mock_ui_server_research_stale_false_failure
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.locator("#runResearchBtn").click()
    expect(page.locator("#runResearchBtn")).to_be_disabled(timeout=5000)
    toast = page.locator("#toast.show")
    expect(toast).not_to_contain_text("LinkedIn ingestion did not complete", timeout=3000)


def test_stale_failure_completes_without_old_error(mock_ui_server_research_stale_false_failure, page: Page):
    port, _captured = mock_ui_server_research_stale_false_failure
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.locator("#runResearchBtn").click()
    expect(page.locator("#listContent")).to_be_visible(timeout=15000)
    expect(page.locator("#toast.show")).to_contain_text("Research complete for 2026-09-07")
    expect(page.locator("#toast.show")).not_to_contain_text("LinkedIn ingestion did not complete")
