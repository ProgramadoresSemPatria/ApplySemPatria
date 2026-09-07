"""Unit tests for LinkedIn DM thread recent-message detection."""

from __future__ import annotations

from dm_chat import classify_header, latest_header_is_recent


def test_classify_header_recent_buckets():
    assert classify_header("Today") == "recent"
    assert classify_header("Yesterday") == "recent"
    assert classify_header("Monday") == "recent"
    assert classify_header("AUG 6") == "older"
    assert classify_header("random") == "other"


def test_latest_header_is_recent_when_last_message_is_today():
    recent, last, reason = latest_header_is_recent(["AUG 1", "Today"])
    assert recent is True
    assert last == "Today"
    assert "Today" in reason


def test_latest_header_is_not_recent_when_last_message_is_older():
    recent, last, reason = latest_header_is_recent(["AUG 1", "Jul 29"])
    assert recent is False
    assert last == "Jul 29"
    assert "older" in reason.lower()


def test_latest_header_empty_thread():
    recent, last, reason = latest_header_is_recent([])
    assert recent is False
    assert last == ""
    assert "no date headers" in reason
