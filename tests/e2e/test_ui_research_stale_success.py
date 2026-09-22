"""E2E: stale completed research run must not flash a false success toast (UI-26)."""

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
def mock_ui_server_research_stale_success(
    monkeypatch, tmp_path
) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Prior successful run on disk; new spawn must not replay that toast immediately."""
    import ui_server
    from research_log import finish_research_run, join_research_run, set_research_step

    run_path = tmp_path / "state" / "research-run.json"
    run_path.parent.mkdir(parents=True)
    run_path.write_text(
        json.dumps(
            {
                "running": False,
                "day": "2026-09-07",
                "step": "done",
                "ok": True,
                "message": "Research complete for 2026-09-07: 1 roles in apply table.",
                "started_at": "2026-09-07T10:00:00-03:00",
                "updated_at": "2026-09-07T10:05:00-03:00",
                "version": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_spawn_daily_research(**_kwargs):
        from research_log import mark_research_day

        time.sleep(0.2)
        join_research_run("2026-09-07")
        set_research_step("linkedin_collect", detail="mock collect")
        time.sleep(2.5)
        finish_research_run(
            ok=True,
            message="Research complete for 2026-09-07: 2 roles in apply table.",
        )
        mark_research_day("2026-09-07", job_count=2, tracks=["ai-engineer"])
        mock_proc = MagicMock()
        mock_proc.pid = 5253
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


def test_stale_success_does_not_flash_immediately(mock_ui_server_research_stale_success, page: Page):
    port, _captured = mock_ui_server_research_stale_success
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.locator("#runResearchBtn").click()
    expect(page.locator("#runResearchBtn")).to_be_disabled(timeout=5000)
    toast = page.locator("#toast.show")
    expect(toast).not_to_contain_text("1 roles in apply table", timeout=1500)
    expect(page.locator("#runResearchBtn")).to_contain_text("Researching", timeout=2000)


def test_stale_success_shows_progress_not_cards(mock_ui_server_research_stale_success, page: Page):
    port, _captured = mock_ui_server_research_stale_success
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.locator("#runResearchBtn").click()
    expect(page.locator("#researchPrompt")).to_be_visible(timeout=5000)
    expect(page.locator("#listContent")).to_be_hidden()
    expect(page.locator("#researchProgressText")).to_contain_text("LinkedIn", timeout=5000)
