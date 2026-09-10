"""Regression: Review-section DMs with profiles must stay connectable via bulk DM."""

from __future__ import annotations

from applications_ui_data import job_to_card
from position_disposition import dm_apply_steps_enabled
from tests.helpers.jobs import linkedin_dm_job


def test_dm_apply_steps_enabled_for_review_with_profile():
    job = linkedin_dm_job(filter_result="needs_review")
    assert dm_apply_steps_enabled(job) is True


def test_dm_apply_steps_enabled_false_without_profile():
    job = linkedin_dm_job(filter_result="needs_review")
    job.pop("recruiter_profile_url")
    assert dm_apply_steps_enabled(job) is False


def test_job_to_card_review_dm_keeps_connect_actions():
    job = linkedin_dm_job(filter_result="needs_review", company="Gabriela Rayo")
    card = job_to_card(
        job,
        section="linkedin_review",
        dm={"profiles": {}},
        email_to=set(),
        email_keys=set(),
        url_done=set(),
        li_cfg={"form_link_message_enabled": True},
    )
    assert card["application_steps_enabled"] is False
    assert card["dm_apply_steps_enabled"] is True
    assert card["actions"]["dm_connect"]["available"] is True
    assert card["actions"]["dm_message"]["available"] is True
    assert card["actions"]["email"]["available"] is False
    assert card["actions"]["form"]["available"] is False


def test_job_to_card_review_dm_without_profile_stays_disabled():
    job = linkedin_dm_job(filter_result="needs_review")
    job.pop("recruiter_profile_url")
    card = job_to_card(
        job,
        section="linkedin_review",
        dm={"profiles": {}},
        email_to=set(),
        email_keys=set(),
        url_done=set(),
        li_cfg={"form_link_message_enabled": True},
    )
    assert card["dm_apply_steps_enabled"] is False
    assert card["actions"]["dm_connect"]["available"] is False
