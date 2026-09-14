"""Audit log coverage for DM follow-up (check connect / message)."""

from __future__ import annotations

import json

import pytest

from audit_log import events_for, read_log, reset_audit_log


@pytest.fixture(autouse=True)
def _audit_tmp(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("JOBSEARCH_AUDIT_LOG_DIR", str(log_dir))
    reset_audit_log()
    yield
    reset_audit_log()


def test_empty_batch_logs_start_and_done(monkeypatch):
    import sys

    import dm_followup
    import dm_state

    monkeypatch.setattr(sys, "argv", ["dm_followup.py"])
    monkeypatch.setattr(dm_state, "load", lambda: {"profiles": {}})
    monkeypatch.setattr(
        dm_followup,
        "pending_profiles",
        lambda state, include_sent=False: [],
    )

    rc = dm_followup.main()
    assert rc == 0
    events = [r["event"] for r in events_for(component="dm_followup")]
    assert events == ["batch_start", "batch_done"]
    start = events_for(component="dm_followup", event="batch_start")[0]["data"]
    assert start["candidates"] == 0
    assert start["phase"] == "all"


def test_profile_audit_context_shape():
    from dm_followup import _profile_audit_context
    import dm_state

    entry = {
        "job_key": "linkedin-post:abc",
        "company": "Acme",
        "role": "AI Engineer",
        "profile_url": "https://www.linkedin.com/in/recruiter/",
        "connect_requested_at": "2026-09-14T10:00:00-03:00",
        "accepted_at": None,
        "message_sent_at": None,
    }
    ctx = _profile_audit_context(entry)
    assert ctx["prior_status"] == dm_state.STATUS_CONNECT_PENDING
    assert ctx["job_key"] == "linkedin-post:abc"
