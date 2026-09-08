"""Tests for manual form apply status overrides."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from form_apply_state import (  # noqa: E402
    form_is_submitted,
    load_form_submission_state,
    set_form_applied,
    URL_APPLICATIONS_PATH,
)
from applications_ui_data import _action_states  # noqa: E402
from tests.helpers.jobs import linkedin_dm_job


@pytest.fixture
def form_state_file(tmp_path: Path, monkeypatch):
    path = tmp_path / "url-applications.json"
    monkeypatch.setattr("form_apply_state.URL_APPLICATIONS_PATH", path)
    monkeypatch.setattr("generate_applications.load_url_submitted", lambda: load_form_submission_state()[0])
    return path


def test_set_form_applied_and_clear(form_state_file: Path):
    job = linkedin_dm_job()
    job["apply_url"] = "https://example.com/apply/acme"

    applied = set_form_applied(job, True)
    assert applied["ok"] is True
    assert applied["applied"] is True
    urls, keys = load_form_submission_state()
    assert "https://example.com/apply/acme" in urls
    assert form_is_submitted(job) is True

    cleared = set_form_applied(job, False)
    assert cleared["ok"] is True
    assert cleared["applied"] is False
    assert form_is_submitted(job) is False
    assert not form_state_file.read_text().strip() or json.loads(form_state_file.read_text())["submitted"] == []


def test_action_states_reflects_manual_form_applied(form_state_file: Path):
    job = linkedin_dm_job()
    job["apply_url"] = "https://example.com/apply/acme"
    set_form_applied(job, True)
    urls, keys = load_form_submission_state()
    actions = _action_states(job, {"profiles": {}}, set(), set(), urls, form_job_keys=keys)
    assert actions["form"]["done"] is True
    assert actions["form"]["status_text"] == "submitted"


def test_set_form_status_api(mock_ui_server, monkeypatch, tmp_path: Path):
    import urllib.error
    import urllib.request
    import json as json_mod

    path = tmp_path / "url-applications.json"
    monkeypatch.setattr("form_apply_state.URL_APPLICATIONS_PATH", path)

    job = linkedin_dm_job()
    job["apply_url"] = "https://example.com/apply/acme"
    from registry import job_key as registry_job_key

    jk = "ai-engineer|linkedin|acme ai|ai engineer"

    port, _captured = mock_ui_server

    def _post(payload: dict) -> tuple[int, dict]:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/form-status",
            data=json_mod.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json_mod.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            return exc.code, json_mod.loads(exc.read().decode())

    status, data = _post({"job_key": jk, "applied": True})
    assert status == 200
    assert data.get("ok") is True
    assert data.get("form_applied") is True
    card = next(row for row in (data.get("snapshot") or {}).get("jobs", []) if row.get("job_key") == jk)
    assert card["actions"]["form"]["done"] is True

    status, data = _post({"job_key": jk, "applied": False})
    assert status == 200
    assert data.get("form_applied") is False
    card = next(row for row in (data.get("snapshot") or {}).get("jobs", []) if row.get("job_key") == jk)
    assert card["actions"]["form"]["done"] is False
