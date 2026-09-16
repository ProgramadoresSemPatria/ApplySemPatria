"""LinkedIn post roles should always show DM connect/message steps alongside email/form."""

from __future__ import annotations

from applications_ui_data import _action_states, job_to_card
from application_channel import (
    classify_channel,
    has_direct_message_apply,
    list_application_formats,
    needs_recruiter_connect,
)
from tests.helpers.jobs import linkedin_dm_job


def _email_linkedin_post(**overrides):
    job = {
        "source": "linkedin_posts",
        "url": "https://www.linkedin.com/in/recruiter-test/recent-activity/all/",
        "apply_email": "recruiter@acme.ai",
        "role": "AI Engineer",
        "company": "Acme AI",
        "discovered_at": "2026-09-14T12:00:00-03:00",
        "filter_result": "eligible",
        "salary_usd": "USD 120k",
    }
    job.update(overrides)
    return job


def _form_email_linkedin_post(**overrides):
    job = {
        "source": "linkedin_posts",
        "url": "https://www.linkedin.com/in/nicolebarraconde/recent-activity/all/",
        "apply_url": "https://lnkd.in/e4m6CuUu",
        "apply_email": "nicole@company.com",
        "role": "AI Engineer",
        "company": "Nicole Barra",
        "discovered_at": "2026-09-14T12:00:00-03:00",
        "filter_result": "eligible",
    }
    job.update(overrides)
    return job


def test_email_linkedin_post_includes_direct_message_format():
    job = _email_linkedin_post()
    assert classify_channel(job) == "email"
    assert has_direct_message_apply(job) is True
    fmt_ids = {f["id"] for f in list_application_formats(job)}
    assert fmt_ids == {"email", "direct_message"}


def test_email_linkedin_post_needs_recruiter_connect_when_profile_known():
    job = _email_linkedin_post()
    assert needs_recruiter_connect(job) is True


def test_form_and_email_linkedin_post_shows_all_dm_steps():
    job = _form_email_linkedin_post()
    fmt_ids = {f["id"] for f in list_application_formats(job)}
    assert fmt_ids == {"email", "form", "direct_message"}
    actions = _action_states(job, {"profiles": {}}, set(), set(), set(), li_cfg={"form_link_message_enabled": True})
    assert actions["email"]["available"] is True
    assert actions["form"]["available"] is True
    assert actions["dm_connect"]["available"] is True
    assert actions["dm_message"]["available"] is True


def test_job_to_card_email_post_exposes_dm_connect_actions():
    job = _email_linkedin_post()
    card = job_to_card(
        job,
        section="linkedin_eligible",
        dm={"profiles": {}},
        email_to=set(),
        email_keys=set(),
        url_done=set(),
        li_cfg={"form_link_message_enabled": True},
    )
    assert card["actions"]["email"]["available"] is True
    assert card["actions"]["dm_connect"]["available"] is True
    assert card["actions"]["dm_message"]["available"] is True
    assert card["dm_profile_missing"] is False


def test_linkedin_post_without_profile_still_lists_direct_message_format():
    job = linkedin_dm_job()
    job.pop("recruiter_profile_url")
    assert has_direct_message_apply(job) is True
    fmt_ids = {f["id"] for f in list_application_formats(job)}
    assert "direct_message" in fmt_ids
    card = job_to_card(
        job,
        section="linkedin_eligible",
        dm={"profiles": {}},
        email_to=set(),
        email_keys=set(),
        url_done=set(),
        li_cfg={"form_link_message_enabled": True},
    )
    assert card["dm_profile_missing"] is True
    assert card["actions"]["dm_connect"]["available"] is False
