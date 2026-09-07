"""Tests for DM follow-up list scoping."""

from __future__ import annotations

from dm_followup import filter_entries_by_job_keys


def test_filter_entries_by_job_keys_matches_profile_url(monkeypatch):
    import dm_state
    from registry import job_key
    from tests.helpers.jobs import linkedin_dm_job

    job = linkedin_dm_job()
    jk = job_key(job)

    monkeypatch.setattr(
        "registry.load_registry",
        lambda: {"jobs": [job]},
    )

    entries = [
        {
            "company": "Acme AI",
            "role": "AI Engineer",
            "job_key": "https://www.linkedin.com/in/recruiter-test",  # legacy key shape
            "profile_url": "https://www.linkedin.com/in/recruiter-test/",
        }
    ]

    matched = filter_entries_by_job_keys(entries, [jk])
    assert len(matched) == 1
    assert dm_state.normalize_profile_url(matched[0]["profile_url"]) == dm_state.normalize_profile_url(
        job["recruiter_profile_url"]
    )


def test_filter_entries_by_job_keys_no_match():
    entries = [{"job_key": "other", "profile_url": "https://www.linkedin.com/in/other/"}]
    assert filter_entries_by_job_keys(entries, ["missing-key"]) == []
