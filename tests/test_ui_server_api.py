"""UI server API tests — CLI-01..07, FE-06/07."""

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
    port = mock_ui_server
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/meta", timeout=5) as resp:
        meta = json.loads(resp.read().decode())
    assert meta.get("ui_approval") is True


def test_action_dm_connect_mock(mock_ui_server):
    port = mock_ui_server
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
