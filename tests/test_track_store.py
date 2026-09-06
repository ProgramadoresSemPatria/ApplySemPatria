#!/usr/bin/env python3
"""Tests for multi-track support."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from track_store import (  # noqa: E402
    filter_jobs_by_track,
    infer_track,
    job_track_label,
    list_track_ids,
    stamp_track,
    track_label,
)


def test_manifest_has_two_tracks():
    ids = list_track_ids()
    assert "ai-engineer" in ids
    assert "android-developer" in ids


def test_stamp_and_filter():
    job = stamp_track({"url": "https://example.com/job", "role": "AI Engineer", "company": "X"}, "ai-engineer")
    assert job["track"] == "ai-engineer"
    jobs = [
        job,
        stamp_track({"url": "https://example.com/android", "role": "Android Dev", "company": "Y"}, "android-developer"),
    ]
    ai_only = filter_jobs_by_track(jobs, "ai-engineer")
    assert len(ai_only) == 1
    assert infer_track(ai_only[0]) == "ai-engineer"


def test_track_label():
    assert track_label("ai-engineer") == "AI Engineer"
    assert job_track_label({"track": "android-developer"}) == "Android Developer"
