"""Pytest fixtures for jobsearch tests."""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def linkedin_html_dir() -> Path:
    return FIXTURES / "linkedin"


def _start_mock_ui_server(
    monkeypatch,
    *,
    today: str = "2026-09-06",
    has_research_today: bool = True,
    last_research_day: str | None = "2026-09-06",
) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """HTTP server with mocked action/snapshot handlers for UI e2e."""
    from tests.helpers.jobs import ui_snapshot

    job_key = "ai-engineer|linkedin|acme ai|ai engineer"
    snapshot = ui_snapshot(job_key, day=today if has_research_today else last_research_day or today)
    captured: dict[str, Any] = {"last_action": None, "last_bulk_action": None}

    def fake_run_action(action: str, jk: str, track=None):
        captured["last_action"] = {"action": action, "job_key": jk, "track": track}
        return {"ok": True, "message": "mock ok", "action": action, "job_key": jk}

    def fake_run_bulk_dm_followup(*, track=None, limit=0, job_keys=None):
        captured["last_bulk_action"] = {
            "action": "dm_process_all",
            "track": track,
            "limit": limit,
            "job_keys": job_keys or [],
        }
        return {
            "ok": True,
            "message": "mock bulk ok",
            "action": "dm_process_all",
            "track": track,
            "limit": limit,
        }

    def fake_refresh():
        return snapshot

    sidebar_days: list[dict[str, Any]] = []
    if last_research_day:
        sidebar_days.append(
            {
                "day": last_research_day,
                "label": last_research_day,
                "job_count": 1,
                "generated_at": f"{last_research_day}T12:00:00",
            }
        )

    def fake_load_snapshot(day):
        known = {snapshot.get("day"), "live", today, last_research_day}
        return snapshot if day in {d for d in known if d} else None

    import applications_ui_data
    import ui_server

    monkeypatch.setattr(ui_server, "run_action", fake_run_action)
    monkeypatch.setattr(ui_server, "run_bulk_dm_followup", fake_run_bulk_dm_followup)
    monkeypatch.setattr(ui_server, "_run_apply_cmd", lambda cmd: MagicMock(returncode=0, stdout="mock", stderr=""))
    monkeypatch.setattr(applications_ui_data, "refresh_live_snapshot", fake_refresh)
    monkeypatch.setattr(applications_ui_data, "list_snapshot_days", lambda: sidebar_days)
    monkeypatch.setattr(applications_ui_data, "load_snapshot", fake_load_snapshot)

    def fake_set_disposition(jk, disp):
        return {"ok": True, "message": "mock disposition", "job_key": jk}

    monkeypatch.setattr(ui_server, "set_disposition", fake_set_disposition)
    monkeypatch.setattr(
        ui_server,
        "ui_meta_payload",
        lambda: {
            "ui_approval": True,
            "version": 3,
            "today": today,
            "has_research_today": has_research_today,
            "last_research_day": last_research_day,
            "last_research_at": f"{last_research_day}T12:00:00" if last_research_day else None,
            "research_days": [
                {
                    "day": last_research_day,
                    "job_count": 1,
                    "completed_at": f"{last_research_day}T12:00:00",
                }
            ]
            if last_research_day
            else [],
        },
    )

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.ApplicationsUIHandler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.15)
    try:
        yield port, captured
    finally:
        httpd.shutdown()
        captured.clear()


@pytest.fixture
def mock_ui_server(monkeypatch) -> Generator[tuple[int, dict[str, Any]], None, None]:
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-06",
        has_research_today=True,
        last_research_day="2026-09-06",
    )


@pytest.fixture
def mock_ui_server_needs_research(monkeypatch) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Today has no research yet; yesterday's snapshot remains in the sidebar."""
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-07",
        has_research_today=False,
        last_research_day="2026-09-06",
    )
