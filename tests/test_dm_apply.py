"""Unit tests for dm_apply candidate selection."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def dm_registry_job():
    return {
        "track": "ai-engineer",
        "source": "linkedin_posts",
        "company": "Acme AI",
        "role": "AI Engineer",
        "url": "https://www.linkedin.com/posts/test-activity-123",
        "recruiter_profile_url": "https://www.linkedin.com/in/recruiter-test/",
        "filter_result": "eligible",
    }


def test_collect_candidates_filters_by_job_keys(dm_registry_job):
    from registry import job_key
    from dm_apply import collect_candidates

    other = {
        **dm_registry_job,
        "company": "Other Co",
        "url": "https://www.linkedin.com/posts/other-activity-456",
        "recruiter_profile_url": "https://www.linkedin.com/in/other-recruiter/",
    }
    reg = {"jobs": [dm_registry_job, other]}
    jk = job_key(dm_registry_job)

    with patch("dm_apply.load_registry", return_value=reg):
        with patch("dm_apply.needs_recruiter_connect", return_value=True):
            out = collect_candidates(table_only=False, limit=0, track_id="ai-engineer", job_keys=[jk])

    assert len(out) == 1
    assert out[0]["company"] == "Acme AI"


@pytest.mark.asyncio
async def test_run_skips_browser_when_no_candidates(monkeypatch):
    from dm_apply import run

    called: list[int] = []

    async def fake_launch(*args, **kwargs):
        called.append(1)
        raise AssertionError("browser should not launch")

    monkeypatch.setattr("dm_apply.launch_context", fake_launch)
    result = await run([], send=False, headless=False)
    assert result == {"sent_actions": 0, "skipped": 0}
    assert called == []
