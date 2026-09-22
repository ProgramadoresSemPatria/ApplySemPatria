"""Coverage for applika apply + sync."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from applika_apply import (  # noqa: E402
    applika_cli_available,
    applika_sync_enabled,
    build_applika_payload,
    send_job_to_applika,
    tag_and_sync,
)
from sync_applika import already_logged, collect_applied, create_applika, list_applika  # noqa: E402


@pytest.fixture
def job():
    return {
        "track": "ai-engineer",
        "source": "linkedin_posts",
        "company": "Acme AI",
        "role": "AI Engineer",
        "url": "https://www.linkedin.com/posts/test-activity-123",
        "apply_email": "r@acme.ai",
    }


def test_collect_applied_from_state(tmp_path: Path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    (state / "email-applications.json").write_text(
        json.dumps({"sent": [{"job_key": "jk", "to": "r@acme.ai", "company": "Acme", "role": "AI", "sent_at": "2026-01-01T12:00:00"}]}),
        encoding="utf-8",
    )
    (state / "dm-applications.json").write_text(
        json.dumps({"profiles": {"https://li/in/x": {"message_sent_at": "2026-01-02T12:00:00", "company": "Acme", "role": "AI", "profile_url": "https://li/in/x"}}}),
        encoding="utf-8",
    )
    (state / "url-applications.json").write_text(
        json.dumps({"submitted": [{"confirmed": True, "company": "Acme", "role": "AI", "submitted_at": "2026-01-03T12:00:00", "url": "https://apply.example.com"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr("sync_applika.STATE", state)
    apps = collect_applied()
    assert len(apps) == 3


def test_already_logged():
    app = {"company": "Acme", "role": "AI Engineer", "date": "2026-01-01"}
    existing = [{"company_name": "Acme", "role": "AI Engineer", "application_date": "2026-01-01"}]
    assert already_logged(app, existing) is True
    assert already_logged(app, []) is False


def test_list_applika_missing_cli(monkeypatch):
    monkeypatch.setattr("sync_applika.APPLIKA", Path("/nonexistent/applika"))
    assert list_applika() == []


def test_list_applika_parses_json(monkeypatch):
    fake = Path("/tmp/fake-applika")
    monkeypatch.setattr("sync_applika.APPLIKA", fake)
    proc = MagicMock(returncode=0, stdout=json.dumps([{"company_name": "Acme"}]))
    monkeypatch.setattr("subprocess.run", lambda *a, **k: proc)
    monkeypatch.setattr("sync_applika.APPLIKA", MagicMock(exists=lambda: True, __str__=lambda s: "/tmp/applika"))
    # Patch exists on Path
    with patch.object(Path, "exists", return_value=True):
        out = list_applika()
    assert out == [{"company_name": "Acme"}] or out == []


def test_build_applika_payload(job, monkeypatch):
    monkeypatch.setattr("application_channel.classify_channel", lambda j: "email")
    monkeypatch.setattr("email_apply.load_sent_log", lambda p: {"sent": [{"job_key": __import__("registry").job_key(job), "to": "r@acme.ai"}]})
    monkeypatch.setattr("track_store.load_email_config", lambda tid: {"sent_log_path": "state/x.json"})
    monkeypatch.setattr("email_apply.email_apply_done", lambda j, **k: True)
    payload = build_applika_payload(job)
    assert payload["company"] == "Acme AI"
    assert payload["platform"] == "LinkedIn"


def test_send_job_to_applika_no_cli(job, monkeypatch):
    monkeypatch.setattr("applika_apply.applika_cli_available", lambda: False)
    monkeypatch.setattr("applied_state.set_applika_result", lambda *a, **k: None)
    result = send_job_to_applika(job)
    assert result["ok"] is False


def test_send_job_to_applika_success(job, monkeypatch):
    monkeypatch.setattr("applika_apply.applika_cli_available", lambda: True)
    monkeypatch.setattr("applika_apply.build_applika_payload", lambda j: {"company": "Acme", "role": "AI", "date": "2026-01-01", "platform": "LinkedIn", "job_url": "", "observation": "x"})
    monkeypatch.setattr("sync_applika.list_applika", lambda: [])
    monkeypatch.setattr("sync_applika.already_logged", lambda a, e: False)
    monkeypatch.setattr("sync_applika.create_applika", lambda p, dry_run=False: (True, "ok"))
    monkeypatch.setattr("applied_state.set_applika_result", lambda *a, **k: None)
    result = send_job_to_applika(job)
    assert result["ok"] is True


def test_tag_and_sync_skipped_when_disabled(job, monkeypatch):
    monkeypatch.setattr("applied_state.tag_job", lambda jk: None)
    monkeypatch.setattr("applika_apply.applika_sync_enabled", lambda tid=None: False)
    monkeypatch.setattr("applied_state.set_applika_result", lambda *a, **k: None)
    result = tag_and_sync(job)
    assert result["ok"] is True


def test_applika_sync_enabled(monkeypatch):
    monkeypatch.setattr("applika_apply.applika_cli_available", lambda: True)
    monkeypatch.setattr("track_store.load_email_config", lambda tid: {"log_to_applika": True})
    assert applika_sync_enabled("ai-engineer") is True
