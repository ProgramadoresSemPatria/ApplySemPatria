"""Tests for daily audit log."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from audit_log import (
    audit_dir,
    events_for,
    get_logger,
    info,
    log_path,
    read_log,
    reset_audit_log,
    step,
    warn,
)

TZ = ZoneInfo("America/Sao_Paulo")


@pytest.fixture(autouse=True)
def _audit_tmp(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("JOBSEARCH_AUDIT_LOG_DIR", str(log_dir))
    reset_audit_log()
    yield
    reset_audit_log()


def test_writes_jsonl_per_day(tmp_path):
    day = datetime.now(TZ).date().isoformat()
    info("test", "hello", foo="bar")
    path = log_path(day)
    assert path.exists()
    assert path.parent == audit_dir()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["component"] == "test"
    assert rec["event"] == "hello"
    assert rec["data"]["foo"] == "bar"
    assert rec["level"] == "INFO"


def test_step_context_logs_start_and_done():
    with step("pipeline", "merge", since="7d") as ctx:
        ctx["rows"] = 12
    records = read_log()
    assert [r["event"] for r in records] == ["step_start", "step_done"]
    assert records[0]["data"]["step"] == "merge"
    assert records[1]["data"]["rows"] == 12
    assert "duration_ms" in records[1]["data"]


def test_step_context_logs_failure():
    with pytest.raises(ValueError, match="boom"):
        with step("pipeline", "fail"):
            raise ValueError("boom")
    records = read_log()
    assert records[-1]["event"] == "step_failed"
    assert records[-1]["data"]["error"] == "boom"


def test_events_for_filter():
    info("a", "one")
    warn("b", "two")
    info("a", "three")
    assert len(events_for(component="a")) == 2
    assert len(events_for(event="two")) == 1


def test_disabled_via_env(monkeypatch):
    monkeypatch.setenv("JOBSEARCH_AUDIT_LOG", "0")
    reset_audit_log()
    info("test", "silent")
    assert read_log() == []


def test_audit_logger_wrapper():
    log = get_logger("email_apply")
    log.info("batch_start", count=3)
    rec = read_log()[0]
    assert rec["component"] == "email_apply"
    assert rec["data"]["count"] == 3


def test_serializes_datetime_in_data():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    ts = datetime(2026, 9, 14, 16, 52, 30, tzinfo=ZoneInfo("America/Sao_Paulo"))
    info("linkedin_posts_merge", "merge_complete", since=ts, count=41)
    rec = read_log()[0]
    assert rec["data"]["since"] == ts.isoformat()
    assert rec["data"]["count"] == 41
