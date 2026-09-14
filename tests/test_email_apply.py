"""Unit tests for email_apply candidate selection."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def email_registry_job():
    return {
        "track": "ai-engineer",
        "source": "linkedin_posts",
        "company": "Acme AI",
        "role": "AI Engineer",
        "url": "https://www.linkedin.com/posts/test-activity-123",
        "apply_email": "recruiter@acme.ai",
        "filter_result": "eligible",
    }


def test_collect_candidates_filters_by_job_keys(email_registry_job):
    from registry import job_key
    from email_apply import collect_candidates

    other = {
        **email_registry_job,
        "company": "Other Co",
        "url": "https://www.linkedin.com/posts/other-activity-456",
        "apply_email": "other@co.ai",
    }
    reg = {"jobs": [email_registry_job, other]}
    jk = job_key(email_registry_job)

    with patch("email_apply.load_registry", return_value=reg):
        out = collect_candidates(table_only=False, limit=0, track_id="ai-engineer", job_keys=[jk])

    assert len(out) == 1
    assert out[0]["company"] == "Acme AI"


def test_collect_candidates_dedupes_shared_apply_email(email_registry_job):
    from registry import job_key
    from email_apply import collect_candidates

    dup = {
        **email_registry_job,
        "url": "https://www.linkedin.com/posts/dup-activity-789",
        "role": "AI Engineer (republish)",
    }
    reg = {"jobs": [email_registry_job, dup]}
    keys = [job_key(email_registry_job), job_key(dup)]

    with patch("email_apply.load_registry", return_value=reg):
        out = collect_candidates(table_only=False, limit=0, track_id="ai-engineer", job_keys=keys)

    assert len(out) == 1


def test_already_sent_requires_matching_job_key(email_registry_job):
    from email_apply import already_sent
    from registry import job_key

    jk = job_key(email_registry_job)
    sent_log = {
        "sent": [
            {
                "job_key": "other-key",
                "to": "recruiter@acme.ai",
            }
        ]
    }
    assert already_sent(email_registry_job, sent_log) is False

    sent_log["sent"].append({"job_key": jk, "to": "recruiter@acme.ai"})
    assert already_sent(email_registry_job, sent_log) is True


def test_pending_send_candidates_allows_same_recipient_new_post(email_registry_job):
    from registry import job_key
    from email_apply import pending_send_candidates

    dup = {
        **email_registry_job,
        "url": "https://www.linkedin.com/feed/update/urn:li:activity:7503200610150973442/",
    }
    reg = {"jobs": [email_registry_job, dup]}
    keys = [job_key(dup)]
    sent_log = {
        "sent": [
            {
                "job_key": job_key(email_registry_job),
                "to": "recruiter@acme.ai",
            }
        ]
    }

    with patch("email_apply.load_registry", return_value=reg):
        pending = pending_send_candidates(
            track_id="ai-engineer",
            job_keys=keys,
            sent_log=sent_log,
        )

    assert len(pending) == 1
    assert pending[0]["url"] == dup["url"]


def test_action_states_email_done_only_for_matching_job_key():
    from applications_ui_data import _action_states
    from registry import job_key

    job = {
        "source": "linkedin_posts",
        "company": "Luis Hernandez",
        "role": "Ai Engineer",
        "url": "https://www.linkedin.com/feed/update/urn:li:activity:7503200610150973442/",
        "apply_email": "luis@mexicoteksol.com",
        "filter_result": "eligible",
    }
    other_key = "https://www.linkedin.com/in/luis-hernandez-75ba5399/recent-activity/all"
    actions = _action_states(
        job,
        {"profiles": {}},
        email_to={"luis@mexicoteksol.com"},
        email_keys={other_key},
        url_done=set(),
    )
    assert actions["email"]["done"] is False

    actions_sent = _action_states(
        job,
        {"profiles": {}},
        email_to={"luis@mexicoteksol.com"},
        email_keys={job_key(job)},
        url_done=set(),
    )
    assert actions_sent["email"]["done"] is True
