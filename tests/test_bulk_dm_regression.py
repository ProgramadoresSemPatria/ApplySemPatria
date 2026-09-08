"""Regression tests: bulk DM must run connect → check → send for list roles.

Guards against the old behaviour that only processed profiles already in the
follow-up queue and told users to tap per-card connect first.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers.judge import expect_action

# Messages from the follow-up-only bulk DM implementation (must never return).
OLD_FOLLOW_UP_ONLY_MESSAGES = (
    "Use per-card",
    "bulk only checks",
    "No DM follow-ups in queue",
    "Send connections from individual cards first",
)


@pytest.mark.parametrize("msg", OLD_FOLLOW_UP_ONLY_MESSAGES)
@patch("ui_server._run_apply_cmd")
def test_regression_bulk_dm_never_returns_follow_up_only_errors(mock_run, msg: str):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
    from ui_server import run_bulk_dm_followup

    keys = ["ai-engineer|linkedin|acme ai|ai engineer"]
    with patch("dm_followup.pending_profiles", return_value=[]):
        with patch("dm_followup.filter_entries_by_job_keys", return_value=[]):
            result = run_bulk_dm_followup(track="ai-engineer", job_keys=keys)

    assert result["ok"] is True
    assert msg not in result.get("message", "")


@patch("ui_server._run_apply_cmd")
def test_regression_bulk_dm_runs_connect_before_follow_up_phases(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
    from ui_server import run_bulk_dm_followup

    keys = ["ai-engineer|linkedin|acme ai|ai engineer"]
    pending = [
        {"profile_url": "https://www.linkedin.com/in/recruiter-test/", "job_key": keys[0], "company": "Acme AI"},
    ]
    with patch("dm_followup.pending_profiles", return_value=pending):
        with patch("dm_followup.filter_entries_by_job_keys", return_value=pending):
            with patch("dm_followup.filter_entries_by_status", side_effect=lambda entries, phase: entries):
                result = run_bulk_dm_followup(track="ai-engineer", job_keys=keys)

    assert result["ok"] is True
    assert mock_run.call_count == 3
    labels = [line for line in result["message"].splitlines() if line.startswith("[")]
    assert labels == [
        "[send_connections] Finished — see terminal for profile-by-profile output.",
        "[check_connections] Finished — see terminal for profile-by-profile output.",
        "[send_messages] Finished — see terminal for profile-by-profile output.",
    ]

    scripts = [call[0][0] for call in mock_run.call_args_list]
    assert expect_action(scripts[0], must_include=["dm_apply.py", "--send", "--job-keys"])
    assert expect_action(scripts[1], must_include=["dm_followup.py", "--phase", "check", "--job-keys"])
    assert expect_action(scripts[2], must_include=["dm_followup.py", "--phase", "send", "--send", "--job-keys"])
    assert "dm_apply.py" not in " ".join(scripts[1] + scripts[2])


@patch("ui_server._run_apply_cmd")
def test_regression_bulk_dm_passes_all_list_job_keys_to_connect(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
    from ui_server import run_bulk_dm_followup

    keys = ["key-a", "key-b", "key-c"]
    run_bulk_dm_followup(track="ai-engineer", job_keys=keys)

    connect_cmd = mock_run.call_args_list[0][0][0]
    joined = connect_cmd[connect_cmd.index("--job-keys") + 1]
    for key in keys:
        assert key in joined


def test_bulk_dm_routing_uses_real_handler(monkeypatch):
    """Regression: handler must call run_bulk_dm_followup (not reject dm_process_all)."""
    from http.server import ThreadingHTTPServer

    import applications_ui_data
    import ui_server
    from tests.helpers.jobs import ui_snapshot
    from tests.test_ui_server_api import _post_json

    snapshot = ui_snapshot("ai-engineer|linkedin|acme ai|ai engineer", day="2026-09-06")
    routed: list[dict] = []

    def track_dm(**kwargs):
        routed.append(dict(kwargs))
        return {
            "ok": True,
            "message": "[send_connections] ok\n\n[check_connections] ok\n\n[send_messages] ok",
            "action": "dm_process_all",
            "job_keys": kwargs.get("job_keys"),
        }

    monkeypatch.setattr(ui_server, "run_bulk_dm_followup", track_dm)
    monkeypatch.setattr(applications_ui_data, "refresh_live_snapshot", lambda: snapshot)
    monkeypatch.setattr(
        ui_server,
        "ui_meta_payload",
        lambda: {**ui_server.UI_META, "today": "2026-09-06", "has_research_today": True},
    )

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.ApplicationsUIHandler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.15)
    try:
        status, data = _post_json(
            f"http://127.0.0.1:{port}/api/bulk-action",
            {"action": "dm_process_all", "job_keys": ["ai-engineer|linkedin|acme ai|ai engineer"]},
        )
    finally:
        httpd.shutdown()

    assert status == 200
    assert routed, "run_bulk_dm_followup was never called — handler rejected dm_process_all"
    assert "Unknown bulk action" not in (data.get("message") or "")
    assert data.get("action") == "dm_process_all"
    assert "snapshot" in data
