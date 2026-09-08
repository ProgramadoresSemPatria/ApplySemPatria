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


def test_filter_entries_by_status():
    from dm_followup import filter_entries_by_status
    import dm_state

    rows = [
        {"profile_url": "https://www.linkedin.com/in/a/", "connect_requested_at": "x"},
        {"profile_url": "https://www.linkedin.com/in/b/", "accepted_at": "x"},
    ]
    check = filter_entries_by_status(rows, phase="check")
    send = filter_entries_by_status(rows, phase="send")
    assert len(check) == 1
    assert dm_state.status_of(check[0]) == dm_state.STATUS_CONNECT_PENDING
    assert len(send) == 1
    assert dm_state.status_of(send[0]) == dm_state.STATUS_ACCEPTED_MSG_PENDING


def test_followup_scopes_job_key_before_limit(monkeypatch):
    """job_keys must win over --limit so card actions don't visit the wrong profiles."""
    import dm_followup
    import dm_state
    from registry import job_key
    from tests.helpers.jobs import linkedin_dm_job

    job = linkedin_dm_job()
    jk = job_key(job)
    entries = [
        {
            "company": "Other Co",
            "role": "Other",
            "job_key": "other-key",
            "profile_url": "https://www.linkedin.com/in/other-recruiter/",
        },
        {
            "company": "Acme AI",
            "role": "AI Engineer",
            "job_key": jk,
            "profile_url": job["recruiter_profile_url"],
        },
    ]

    monkeypatch.setattr("registry.load_registry", lambda: {"jobs": [job]})

    scoped = dm_followup.filter_entries_by_job_keys(entries, [jk])
    assert len(scoped) == 1
    assert dm_state.normalize_profile_url(scoped[0]["profile_url"]) == dm_state.normalize_profile_url(
        job["recruiter_profile_url"]
    )
