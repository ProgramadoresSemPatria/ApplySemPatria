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
    mock_research: bool = False,
    research_run_path: Path | None = None,
    snapshot_override: dict[str, Any] | None = None,
    bulk_dm: str = "mock",
) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """HTTP server with mocked action/snapshot handlers for UI e2e."""
    from tests.helpers.jobs import ui_snapshot

    job_key = "ai-engineer|linkedin|acme ai|ai engineer"
    snapshot = snapshot_override or ui_snapshot(job_key, day=today if has_research_today else last_research_day or today)
    research_snapshot = ui_snapshot(job_key, day=today)
    captured: dict[str, Any] = {
        "last_action": None,
        "last_bulk_action": None,
        "last_research": None,
        "apply_cmds": [],
    }

    if research_run_path:
        monkeypatch.setattr("research_log.RUN_PATH", research_run_path)

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
    if not has_research_today:
        sidebar_days.append({"day": today, "job_count": 0, "pending": True})
    if last_research_day:
        sidebar_days.append(
            {
                "day": last_research_day,
                "label": last_research_day,
                "job_count": 1,
                "generated_at": f"{last_research_day}T12:00:00",
                "pending": False,
            }
        )

    def fake_load_snapshot(day):
        if day == today and mock_research:
            return research_snapshot
        known = {snapshot.get("day"), "live", today, last_research_day}
        return snapshot if day in {d for d in known if d} else None

    def fake_run_daily_research(**_kwargs):
        from research_log import finish_research_run, set_research_step, start_research_run

        captured["last_research"] = {"started": True}
        start_research_run(today)
        set_research_step("linkedin_collect")
        time.sleep(1.2)
        set_research_step("generate_table")
        time.sleep(0.2)
        msg = f"Research complete for {today}: 1 roles in apply table."
        finish_research_run(ok=True, message=msg)
        for entry in sidebar_days:
            if entry.get("day") == today:
                entry["pending"] = False
                entry["job_count"] = 1
                entry["generated_at"] = f"{today}T12:00:00"
        captured["last_research"] = {"ok": True, "day": today, "message": msg}
        return {"ok": True, "message": msg, "day": today, "job_count": 1}

    import applications_ui_data
    import ui_server

    def fake_run_apply_cmd(cmd, *, inherit_stdio=False):
        captured["apply_cmds"].append(list(cmd))
        return MagicMock(returncode=0, stdout="[DRY RUN] checking 1 profile(s)\nSummary: ok", stderr="")

    monkeypatch.setattr(ui_server, "run_action", fake_run_action)
    if bulk_dm == "mock":
        monkeypatch.setattr(ui_server, "run_bulk_dm_followup", fake_run_bulk_dm_followup)
        monkeypatch.setattr(ui_server, "_run_apply_cmd", fake_run_apply_cmd)
    else:
        import dm_state as dm_state_mod
        from registry import job_key as registry_job_key
        from tests.helpers.jobs import linkedin_dm_job

        reg_job = linkedin_dm_job()
        reg_jk = registry_job_key(reg_job)
        snapshot = ui_snapshot(reg_jk, day=today if has_research_today else last_research_day or today)
        research_snapshot = ui_snapshot(reg_jk, day=today)

        profile = "https://www.linkedin.com/in/recruiter-test/"
        prof_key = dm_state_mod.normalize_profile_url(profile)
        if bulk_dm == "real":
            dm_data = {
                "profiles": {
                    prof_key: {
                        "company": "Acme AI",
                        "role": "AI Engineer",
                        "job_key": profile.rstrip("/"),  # legacy URL key — regression case
                        "profile_url": profile,
                        "connect_requested_at": "2026-09-07T12:00:00",
                        "accepted_at": None,
                        "message_sent_at": None,
                    }
                }
            }
        else:
            dm_data = {"profiles": {}}

        monkeypatch.setattr(dm_state_mod, "load", lambda: dm_data)
        monkeypatch.setattr("registry.load_registry", lambda: {"jobs": [reg_job]})
        monkeypatch.setattr(ui_server, "_browser_deps_ok", lambda: (True, ""))
        monkeypatch.setattr(ui_server, "_run_apply_cmd", fake_run_apply_cmd)
        monkeypatch.setattr(ui_server, "_find_job", lambda jk: reg_job if jk == reg_jk else None)
    monkeypatch.setattr(applications_ui_data, "refresh_live_snapshot", fake_refresh)
    monkeypatch.setattr(applications_ui_data, "list_snapshot_days", lambda: sidebar_days)
    monkeypatch.setattr(applications_ui_data, "load_snapshot", fake_load_snapshot)

    if mock_research:
        monkeypatch.setattr("daily_research.run_daily_research", fake_run_daily_research)

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


@pytest.fixture
def mock_ui_server_dm_sent(monkeypatch) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Dashboard with DM message already sent on the card."""
    from tests.helpers.jobs import ui_snapshot

    job_key = "ai-engineer|linkedin|acme ai|ai engineer"
    sent_actions = {
        "email": {"available": False, "done": False, "in_progress": False, "label": "Apply via email", "status_text": "not applied"},
        "form": {"available": True, "done": False, "in_progress": False, "label": "Apply via form", "status_text": "not applied"},
        "dm_connect": {"available": True, "done": True, "in_progress": False, "label": "Send connection", "status_text": "done"},
        "dm_check": {"available": False, "done": True, "in_progress": False, "label": "Check connection accepted", "status_text": "accepted"},
        "dm_message": {"available": True, "done": True, "in_progress": False, "label": "Send LinkedIn message", "status_text": "sent"},
    }
    snapshot = ui_snapshot(job_key, day="2026-09-06", actions=sent_actions)
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-06",
        has_research_today=True,
        last_research_day="2026-09-06",
        snapshot_override=snapshot,
    )


@pytest.fixture
def mock_ui_server_research_flow(monkeypatch, tmp_path) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Today pending with mock POST /api/research progress + completion."""
    run_path = tmp_path / "state" / "research-run.json"
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-07",
        has_research_today=False,
        last_research_day="2026-09-06",
        mock_research=True,
        research_run_path=run_path,
    )


@pytest.fixture
def mock_ui_server_bulk_dm_legacy_match(monkeypatch) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Real bulk DM preflight: legacy profile-key entry must match list row."""
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-06",
        has_research_today=True,
        last_research_day="2026-09-06",
        bulk_dm="real",
    )


@pytest.fixture
def mock_ui_server_bulk_dm_empty_queue(monkeypatch) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Real bulk DM preflight: empty follow-up queue surfaces a clear error."""
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-06",
        has_research_today=True,
        last_research_day="2026-09-06",
        bulk_dm="real_empty",
    )
