"""UI server API tests — CLI-01..08, FE-06/07."""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers.judge import expect_action, expect_ui_approval_env


def _post_json(url: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def test_meta_ui_approval(mock_ui_server):
    port, _captured = mock_ui_server
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/meta", timeout=5) as resp:
        meta = json.loads(resp.read().decode())
    assert meta.get("ui_approval") is True
    assert meta.get("version") == 6
    assert "email_process_all" in (meta.get("bulk_actions") or [])
    assert meta.get("has_research_today") is True
    assert meta.get("today") == "2026-09-06"


def test_bulk_email_routing_uses_real_handler(monkeypatch):
    """Regression: stale servers returned Unknown bulk action before runner was called."""
    import threading
    import time
    from http.server import ThreadingHTTPServer

    import applications_ui_data
    import ui_server
    from tests.helpers.jobs import ui_snapshot

    snapshot = ui_snapshot("ai-engineer|linkedin|acme ai|ai engineer", day="2026-09-06")
    routed: list[dict] = []

    def track_email(**kwargs):
        routed.append(dict(kwargs))
        return {
            "ok": True,
            "message": "routed",
            "action": "email_process_all",
            "job_keys": kwargs.get("job_keys"),
        }

    monkeypatch.setattr(ui_server, "run_bulk_email_apply", track_email)
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
            {"action": "email_process_all", "job_keys": ["ai-engineer|linkedin|acme ai|ai engineer"]},
        )
    finally:
        httpd.shutdown()

    assert status == 200
    assert routed, "run_bulk_email_apply was never called — handler rejected email_process_all"
    assert "Unknown bulk action" not in (data.get("message") or "")
    assert data.get("action") == "email_process_all"


def test_bulk_action_unknown_returns_400(mock_ui_server):
    port, _captured = mock_ui_server
    status, data = _post_json(
        f"http://127.0.0.1:{port}/api/bulk-action",
        {"action": "not_a_real_bulk_action", "job_keys": ["k"]},
    )
    assert status == 400
    assert "Unknown bulk action" in data.get("message", "")


def test_research_status_endpoint(mock_ui_server_research_flow):
    port, _captured = mock_ui_server_research_flow
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/research/status", timeout=5) as resp:
        status = json.loads(resp.read().decode())
    assert status.get("running") is False


def test_action_dm_connect_mock(mock_ui_server):
    port, _captured = mock_ui_server
    jk = "ai-engineer|linkedin|acme ai|ai engineer"
    status, data = _post_json(
        f"http://127.0.0.1:{port}/api/action",
        {"action": "dm_connect", "job_key": jk},
    )
    assert status == 200
    assert data.get("ok") is True
    assert "snapshot" in data


@patch("ui_server._run_apply_cmd")
def test_run_action_dm_connect_cmd(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
    from ui_server import run_action

    with patch("ui_server._find_job") as find:
        find.return_value = {
            "company": "Acme AI",
            "track": "ai-engineer",
            "filter_result": "eligible",
        }
        with patch("position_disposition.application_steps_enabled", return_value=True):
            result = run_action("dm_connect", "test-key")

    assert result["ok"] is True
    cmd = mock_run.call_args[0][0]
    verdict = expect_action(
        cmd,
        must_include=["dm_apply.py", "--send", "--ui-approved", "--force-send", "Acme AI"],
    )
    assert verdict, verdict.reason


def test_ui_subprocess_env_sets_approval():
    from ui_server import _ui_subprocess_env

    env = _ui_subprocess_env()
    assert expect_ui_approval_env(env)


@patch("ui_server._run_apply_cmd")
def test_run_action_dm_message_cmd(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
    from ui_server import run_action

    with patch("ui_server._find_job") as find:
        find.return_value = {"company": "Acme", "track": "ai-engineer"}
        with patch("position_disposition.application_steps_enabled", return_value=True):
            run_action("dm_message", "test-key")

    cmd = mock_run.call_args[0][0]
    assert expect_action(cmd, must_include=["dm_followup.py", "--send", "--ui-approved"])


@patch("ui_server._run_apply_cmd")
def test_run_action_email_cmd(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
    from ui_server import run_action

    with patch("ui_server._find_job") as find:
        find.return_value = {"company": "Acme", "track": "ai-engineer"}
        with patch("position_disposition.application_steps_enabled", return_value=True):
            run_action("email_send", "test-key")

    cmd = mock_run.call_args[0][0]
    assert expect_action(cmd, must_include=["email_apply.py", "--ui-approved", "--smtp"])


def test_run_action_job_not_found():
    from ui_server import run_action

    with patch("ui_server._find_job", return_value=None):
        result = run_action("dm_connect", "missing")
    assert result["ok"] is False
    assert "not found" in result["message"].lower()


def test_run_action_steps_disabled():
    from ui_server import run_action

    with patch("ui_server._find_job") as find:
        find.return_value = {"company": "X", "filter_result": "needs_review"}
        with patch("position_disposition.application_steps_enabled", return_value=False):
            result = run_action("dm_connect", "k")
    assert result["ok"] is False
    assert "disabled" in result["message"].lower()


@patch("ui_server._run_apply_cmd")
def test_run_bulk_dm_followup_invokes_connect_check_then_send(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="phase ok", stderr="")
    from ui_server import run_bulk_dm_followup

    keys = ["ai-engineer|linkedin|acme ai|ai engineer"]
    result = run_bulk_dm_followup(track="ai-engineer", limit=0, job_keys=keys)

    assert result["ok"] is True
    assert result["action"] == "dm_process_all"
    assert result["job_keys"] == keys
    assert mock_run.call_count == 3

    connect_cmd = mock_run.call_args_list[0][0][0]
    check_cmd = mock_run.call_args_list[1][0][0]
    send_cmd = mock_run.call_args_list[2][0][0]

    assert expect_action(
        connect_cmd,
        must_include=["dm_apply.py", "--send", "--ui-approved", "--force-send", "--track", "ai-engineer", "--job-keys"],
    )
    assert expect_action(check_cmd, must_include=["dm_followup.py", "--track", "ai-engineer", "--job-keys"])
    assert expect_action(
        send_cmd,
        must_include=["dm_followup.py", "--send", "--ui-approved", "--force-send", "--track", "ai-engineer", "--job-keys"],
    )
    assert keys[0] in connect_cmd[connect_cmd.index("--job-keys") + 1]


@patch("ui_server._run_apply_cmd")
def test_run_bulk_dm_followup_runs_connect_when_queue_empty(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="processing 0", stderr="")
    from ui_server import run_bulk_dm_followup

    keys = ["ai-engineer|linkedin|acme ai|ai engineer"]
    result = run_bulk_dm_followup(track="ai-engineer", job_keys=keys)

    assert result["ok"] is True
    assert mock_run.call_count == 3
    assert expect_action(mock_run.call_args_list[0][0][0], must_include=["dm_apply.py", "--send"])


@patch("ui_server._run_apply_cmd")
def test_run_bulk_dm_followup_empty_list_rejected(mock_run):
    from ui_server import run_bulk_dm_followup

    result = run_bulk_dm_followup(job_keys=[])
    assert result["ok"] is False
    assert "current list" in result["message"].lower()
    mock_run.assert_not_called()


@patch("ui_server._run_apply_cmd")
def test_run_bulk_dm_followup_respects_limit(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
    from ui_server import run_bulk_dm_followup

    fake_entry = {"profile_url": "https://www.linkedin.com/in/recruiter-test/", "job_key": "k"}
    with patch("dm_followup.pending_profiles", return_value=[fake_entry]):
        with patch("dm_followup.filter_entries_by_job_keys", return_value=[fake_entry]):
            run_bulk_dm_followup(track="android-developer", limit=3)

    for call in mock_run.call_args_list:
        cmd = call[0][0]
        assert expect_action(cmd, must_include=["--limit", "3", "--track", "android-developer"])


def test_bulk_dm_followup_mock(mock_ui_server):
    port, captured = mock_ui_server
    jk = "ai-engineer|linkedin|acme ai|ai engineer"
    status, data = _post_json(
        f"http://127.0.0.1:{port}/api/bulk-action",
        {"action": "dm_process_all", "track": "ai-engineer", "job_keys": [jk]},
    )
    assert status == 200
    assert data.get("ok") is True
    assert data.get("action") == "dm_process_all"
    assert "snapshot" in data
    assert captured["last_bulk_action"]["action"] == "dm_process_all"
    assert captured["last_bulk_action"]["job_keys"] == [jk]


@patch("ui_server._run_apply_cmd")
def test_run_bulk_email_apply_invokes_email_script(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="Sent 1 email(s)", stderr="")
    from registry import job_key
    from ui_server import run_bulk_email_apply

    job = {
        "track": "ai-engineer",
        "company": "Acme AI",
        "role": "AI Engineer",
        "apply_email": "recruiter@acme.ai",
        "url": "https://www.linkedin.com/posts/test-activity-123",
    }
    keys = [job_key(job)]
    with patch("ui_server._find_job", return_value=job):
        with patch("email_apply.load_registry", return_value={"jobs": [job]}):
            with patch("gmail_configure.email_send_allowed", return_value=(True, "")):
                result = run_bulk_email_apply(track="ai-engineer", job_keys=keys)

    assert result["ok"] is True
    assert result["action"] == "email_process_all"
    assert result["job_keys"] == keys
    assert result["unique_emails"] == 1
    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert expect_action(
        cmd,
        must_include=["email_apply.py", "--send", "--ui-approved", "--smtp", "--force-send", "--job-keys"],
    )
    assert keys[0] in cmd[cmd.index("--job-keys") + 1]


@patch("ui_server._run_apply_cmd")
def test_run_bulk_email_apply_no_apply_email_skips_send(mock_run):
    from ui_server import run_bulk_email_apply

    keys = ["ai-engineer|linkedin|acme ai|ai engineer"]
    job = {"track": "ai-engineer", "company": "Acme AI", "role": "AI Engineer"}
    with patch("ui_server._find_job", return_value=job):
        result = run_bulk_email_apply(track="ai-engineer", job_keys=keys)

    assert result["ok"] is False
    assert "apply email" in result["message"].lower()
    mock_run.assert_not_called()


@patch("ui_server._run_apply_cmd")
def test_run_bulk_email_apply_already_sent_skips_send(mock_run):
    from ui_server import run_bulk_email_apply

    keys = ["ai-engineer|linkedin|acme ai|ai engineer"]
    job = {
        "track": "ai-engineer",
        "company": "Acme AI",
        "role": "AI Engineer",
        "apply_email": "recruiter@acme.ai",
    }
    with patch("ui_server._find_job", return_value=job):
        with patch("email_apply.already_sent", return_value=True):
            result = run_bulk_email_apply(track="ai-engineer", job_keys=keys)

    assert result["ok"] is False
    assert "already sent" in result["message"].lower()
    mock_run.assert_not_called()


@patch("ui_server._run_apply_cmd")
def test_run_bulk_email_apply_rejects_sent_recipient_for_sibling_keys(mock_run):
    from registry import job_key
    from ui_server import run_bulk_email_apply

    job_a = {
        "track": "ai-engineer",
        "company": "Acme AI",
        "role": "AI Engineer A",
        "apply_email": "recruiter@acme.ai",
        "url": "https://www.linkedin.com/posts/a",
    }
    job_b = {**job_a, "role": "AI Engineer B", "url": "https://www.linkedin.com/posts/b"}
    keys = [job_key(job_a), job_key(job_b)]
    reg = {"jobs": [job_a, job_b]}

    def find_job(jk: str):
        return job_a if jk == keys[0] else job_b

    sent_log = {"sent": [{"job_key": "other-key", "to": "recruiter@acme.ai"}]}
    with patch("ui_server._find_job", side_effect=find_job):
        with patch("email_apply.load_registry", return_value=reg):
            with patch("email_apply.load_sent_log", return_value=sent_log):
                with patch("email_apply.load_config", return_value={"sent_log_path": "state/email-applications.json"}):
                    result = run_bulk_email_apply(track="ai-engineer", job_keys=keys)

    assert result["ok"] is False
    assert result.get("unique_emails") == 0
    assert "already sent" in result["message"].lower()
    mock_run.assert_not_called()


@patch("ui_server._run_apply_cmd")
def test_run_bulk_email_apply_preflight_unique_email_count(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="Sent 1 email(s)", stderr="")
    from registry import job_key
    from ui_server import run_bulk_email_apply

    job_a = {
        "track": "ai-engineer",
        "company": "Acme AI",
        "role": "AI Engineer A",
        "apply_email": "recruiter@acme.ai",
        "url": "https://www.linkedin.com/posts/a",
    }
    job_b = {**job_a, "role": "AI Engineer B", "url": "https://www.linkedin.com/posts/b"}
    keys = [job_key(job_a), job_key(job_b)]
    reg = {"jobs": [job_a, job_b]}

    def find_job(jk: str):
        return job_a if jk == keys[0] else job_b

    with patch("ui_server._find_job", side_effect=find_job):
        with patch("email_apply.load_registry", return_value=reg):
            with patch("gmail_configure.email_send_allowed", return_value=(True, "")):
                result = run_bulk_email_apply(track="ai-engineer", job_keys=keys)

    assert result["ok"] is True
    assert result["pending_roles"] == 2
    assert result["unique_emails"] == 1
    assert "1 unique address" in result["message"]
    mock_run.assert_called_once()


@patch("ui_server._run_apply_cmd")
def test_run_bulk_email_apply_empty_list_rejected(mock_run):
    from ui_server import run_bulk_email_apply

    result = run_bulk_email_apply(job_keys=[])
    assert result["ok"] is False
    assert "current list" in result["message"].lower()
    mock_run.assert_not_called()


def test_bulk_email_apply_mock(mock_ui_server_email):
    port, captured = mock_ui_server_email
    jk = "ai-engineer|linkedin|acme ai|ai engineer"
    status, data = _post_json(
        f"http://127.0.0.1:{port}/api/bulk-action",
        {"action": "email_process_all", "track": "ai-engineer", "job_keys": [jk]},
    )
    assert status == 200
    assert data.get("ok") is True
    assert data.get("action") == "email_process_all"
    assert "snapshot" in data
    assert captured["last_bulk_action"]["action"] == "email_process_all"
    assert captured["last_bulk_action"]["job_keys"] == [jk]


def test_resolve_python_prefers_project_venv(tmp_path, monkeypatch):
    from ui_server import _resolve_python

    venv_py = tmp_path / ".venv-test" / "bin" / "python"
    venv_py.parent.mkdir(parents=True)
    venv_py.write_text("#!/bin/sh\n")
    monkeypatch.setattr("ui_server.ROOT", tmp_path)
    monkeypatch.delenv("JOBSEARCH_PYTHON", raising=False)
    assert _resolve_python() == str(venv_py)


