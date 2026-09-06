#!/usr/bin/env python3
"""Tests for application channel + LinkedIn form+connect behavior."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from application_channel import (  # noqa: E402
    classify_channel,
    has_direct_message_apply,
    list_application_formats,
    needs_recruiter_connect,
    recruiter_message_enabled,
    recruiter_profile_url,
)
from dm_apply import message_body  # noqa: E402


def _form_linkedin_job(**overrides):
    job = {
        "source": "linkedin_posts",
        "url": "https://www.linkedin.com/in/nicolebarraconde/recent-activity/all/",
        "apply_url": "https://lnkd.in/e4m6CuUu",
        "role": "Ai Engineer",
        "company": "Nicole Barra",
        "discovered_at": "2026-09-06T12:00:00-03:00",
    }
    job.update(overrides)
    return job


def test_form_linkedin_post_has_both_formats():
    job = _form_linkedin_job()
    assert classify_channel(job) == "url"
    assert needs_recruiter_connect(job) is True
    fmt_ids = {f["id"] for f in list_application_formats(job)}
    assert fmt_ids == {"form", "direct_message"}


def test_recruiter_profile_from_posts_slug():
    job = _form_linkedin_job(
        url="https://www.linkedin.com/posts/jane-doe_hiring-activity-123-abc/",
    )
    assert recruiter_profile_url(job) == "https://www.linkedin.com/in/jane-doe/"


def test_dm_collect_includes_form_linkedin_posts():
    job = _form_linkedin_job()
    assert classify_channel(job) != "dm"
    # collect_candidates filters registry; smoke-test helper logic via needs_recruiter_connect
    assert needs_recruiter_connect(job) and recruiter_profile_url(job)


def test_form_link_message_body_includes_apply_url():
    job = _form_linkedin_job()
    profile = {
        "form_link_message_template": "Applied for {role} via {apply_url}",
    }
    body = message_body(job, profile, track_id="ai-engineer")
    assert "Nicole Barra" not in body
    assert "Ai Engineer" in body or "AI Engineer" in body
    assert "lnkd.in" in body


def test_recruiter_message_disabled_when_config_off():
    job = _form_linkedin_job()
    assert recruiter_message_enabled(job, {"form_link_message_enabled": False}) is False
    assert recruiter_message_enabled(job, {"form_link_message_enabled": True}) is True


def test_pure_dm_still_messages_by_default():
    job = {
        "source": "linkedin_posts",
        "url": "https://www.linkedin.com/posts/recruiter_hiring-activity-1-abc/",
        "role": "Ai Engineer",
        "company": "Recruiter",
    }
    assert classify_channel(job) == "dm"
    assert has_direct_message_apply(job) is True
    assert recruiter_message_enabled(job, {"form_link_message_enabled": False}) is True
