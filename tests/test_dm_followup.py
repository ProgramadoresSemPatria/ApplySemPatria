"""Tests for DM follow-up list scoping and check-phase behaviour."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

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


def test_filter_entries_prefers_canonical_registry_profile(monkeypatch):
    """Regression: stale dm_state profile URL must not win over registry recruiter."""
    import dm_state
    from registry import job_key

    registry_jobs = [
        {
            "company": "Paulo Chavez",
            "role": "AI Engineer",
            "url": "https://www.linkedin.com/posts/paulo-chavez-ai",
            "recruiter_profile_url": "https://www.linkedin.com/in/pablo-saldarriaga/",
            "source": "linkedin_posts",
            "track": "ai-engineer",
        },
        {
            "company": "Paulo Chavez",
            "role": "AI Engineer",
            "url": "https://www.linkedin.com/posts/paulo-chavez-ai",
            "recruiter_profile_url": "https://www.linkedin.com/in/paulochb/",
            "source": "linkedin_posts",
            "track": "ai-engineer",
        },
    ]
    monkeypatch.setattr("registry.load_registry", lambda: {"jobs": registry_jobs})
    jk = job_key(registry_jobs[0])

    entries = [
        {
            "company": "Paulo Chavez",
            "role": "AI Engineer",
            "job_key": None,
            "profile_url": "https://www.linkedin.com/in/paulochb/",
            "connect_requested_at": "2026-09-15T12:00:00",
        },
        {
            "company": "Paulo Chavez",
            "role": "AI Engineer",
            "job_key": None,
            "profile_url": "https://www.linkedin.com/in/pablo-saldarriaga/",
            "connect_requested_at": "2026-09-21T12:00:00",
        },
    ]

    matched = filter_entries_by_job_keys(entries, [jk])
    assert len(matched) == 1
    assert dm_state.normalize_profile_url(matched[0]["profile_url"]) == dm_state.normalize_profile_url(
        "https://www.linkedin.com/in/pablo-saldarriaga/"
    )


def test_filter_entries_rewrites_single_stale_profile_to_canonical(monkeypatch):
    import dm_state
    from registry import job_key

    registry_jobs = [
        {
            "company": "Paulo Chavez",
            "role": "AI Engineer",
            "url": "https://www.linkedin.com/posts/paulo-chavez-ai",
            "recruiter_profile_url": "https://www.linkedin.com/in/pablo-saldarriaga/",
            "source": "linkedin_posts",
            "track": "ai-engineer",
        }
    ]
    monkeypatch.setattr("registry.load_registry", lambda: {"jobs": registry_jobs})
    jk = job_key(registry_jobs[0])

    entries = [
        {
            "company": "Paulo Chavez",
            "role": "AI Engineer",
            "job_key": None,
            "profile_url": "https://www.linkedin.com/in/paulochb/",
            "connect_requested_at": "2026-09-15T12:00:00",
        }
    ]

    matched = filter_entries_by_job_keys(entries, [jk])
    assert len(matched) == 1
    assert dm_state.normalize_profile_url(matched[0]["profile_url"]) == dm_state.normalize_profile_url(
        "https://www.linkedin.com/in/pablo-saldarriaga/"
    )


@pytest.mark.asyncio
async def test_run_check_phase_records_accept_without_messaging(monkeypatch, tmp_path):
    import dm_followup
    import dm_state

    state = {
        "profiles": {
            dm_state.normalize_profile_url("https://www.linkedin.com/in/recruiter-test/"): {
                "company": "Acme AI",
                "role": "AI Engineer",
                "job_key": "jk-1",
                "profile_url": "https://www.linkedin.com/in/recruiter-test/",
                "connect_requested_at": "2026-09-15T12:00:00",
                "accepted_at": None,
                "message_sent_at": None,
            }
        }
    }
    saved: list[dict] = []

    monkeypatch.setattr(dm_state, "load", lambda: state)
    monkeypatch.setattr(dm_state, "save", lambda data: saved.append(data))
    monkeypatch.setattr(
        dm_followup,
        "load_track_profile",
        lambda _track: {"dm_message_template": "Hi {role}"},
    )
    monkeypatch.setattr(
        dm_followup,
        "resolve_recipe",
        lambda *args, **kwargs: {"name": "linkedin-message-only"},
    )

    page = MagicMock()
    ctx = MagicMock()
    ctx.new_page = AsyncMock(return_value=page)
    monkeypatch.setattr(
        dm_followup,
        "launch_context",
        AsyncMock(return_value=(MagicMock(), MagicMock(), ctx)),
    )
    monkeypatch.setattr(dm_followup, "close_session", AsyncMock())
    monkeypatch.setattr(
        dm_followup,
        "is_connected",
        AsyncMock(return_value=(True, "Message available (accepted)")),
    )
    inspect_thread = AsyncMock(return_value={"opened": False})
    monkeypatch.setattr("dm_chat.inspect_thread", inspect_thread)
    send_message = AsyncMock(return_value=(True, "sent"))
    monkeypatch.setattr("dm_chat.send_message", send_message)
    monkeypatch.setattr(dm_followup, "cleanup_after_message", AsyncMock(return_value=[]))
    monkeypatch.setattr("table_refresh.refresh_applications_table", lambda: None)

    entries = [
        {
            "company": "Acme AI",
            "role": "AI Engineer",
            "job_key": "jk-1",
            "profile_url": "https://www.linkedin.com/in/recruiter-test/",
            "connect_requested_at": "2026-09-15T12:00:00",
        }
    ]

    await dm_followup.run(
        entries,
        send=False,
        headless=True,
        track_id="ai-engineer",
        phase="check",
    )

    inspect_thread.assert_not_called()
    send_message.assert_not_called()
    prof = dm_state.get(state, "https://www.linkedin.com/in/recruiter-test/")
    assert prof is not None
    assert prof.get("accepted_at")
    assert saved
