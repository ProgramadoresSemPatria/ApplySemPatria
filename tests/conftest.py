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


@pytest.fixture
def mock_ui_server(monkeypatch) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """HTTP server with mocked action/snapshot handlers for UI e2e."""
    from tests.helpers.jobs import ui_snapshot

    job_key = "ai-engineer|linkedin|acme ai|ai engineer"
    snapshot = ui_snapshot(job_key)
    captured: dict[str, Any] = {"last_action": None, "last_bulk_action": None}

    def fake_run_action(action: str, jk: str, track=None):
        captured["last_action"] = {"action": action, "job_key": jk, "track": track}
        return {"ok": True, "message": "mock ok", "action": action, "job_key": jk}

    def fake_run_bulk_dm_followup(*, track=None, limit=0):
        captured["last_bulk_action"] = {
            "action": "dm_process_all",
            "track": track,
            "limit": limit,
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

    def fake_list_days():
        return [{"day": "live", "label": "Live", "job_count": 1, "generated_at": "2026-09-06T12:00:00"}]

    def fake_load_snapshot(day):
        return snapshot if day in ("live", snapshot.get("day")) else None

    import applications_ui_data
    import ui_server

    monkeypatch.setattr(ui_server, "run_action", fake_run_action)
    monkeypatch.setattr(ui_server, "run_bulk_dm_followup", fake_run_bulk_dm_followup)
    monkeypatch.setattr(ui_server, "_run_apply_cmd", lambda cmd: MagicMock(returncode=0, stdout="mock", stderr=""))
    monkeypatch.setattr(applications_ui_data, "refresh_live_snapshot", fake_refresh)
    monkeypatch.setattr(applications_ui_data, "list_snapshot_days", fake_list_days)
    monkeypatch.setattr(applications_ui_data, "load_snapshot", fake_load_snapshot)

    def fake_set_disposition(jk, disp):
        return {"ok": True, "message": "mock disposition", "job_key": jk}

    monkeypatch.setattr(ui_server, "set_disposition", fake_set_disposition)

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
