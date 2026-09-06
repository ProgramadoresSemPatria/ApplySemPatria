"""Feature tests for UI action state machine — FE-01..05, FE-09."""

from __future__ import annotations

import dm_state
from applications_ui_data import _action_states
from tests.helpers.judge import expect_step_states
from tests.helpers.jobs import linkedin_dm_job


def _formats_job():
    job = linkedin_dm_job()
    formats = [
        {"id": "form", "label": "Form"},
        {"id": "direct_message", "label": "Direct message"},
    ]
    return job, formats


def test_dm_fresh_job_connect_available():
    job = linkedin_dm_job()
    dm: dict = {"profiles": {}}
    prof = job["recruiter_profile_url"]
    actions = _action_states(job, dm, set(), set(), set(), li_cfg={"form_link_message_enabled": True})
    assert expect_step_states(
        actions,
        {
            "dm_connect": {"available": True, "done": False, "in_progress": False},
            "dm_check": {"available": False},
            "dm_message": {"available": True, "done": False},
        },
    )


def test_dm_connect_pending():
    job = linkedin_dm_job()
    dm: dict = {"profiles": {}}
    prof = job["recruiter_profile_url"]
    dm_state.record_connect(dm, job, prof)
    actions = _action_states(job, dm, set(), set(), set(), li_cfg={"form_link_message_enabled": True})
    assert expect_step_states(
        actions,
        {
            "dm_connect": {"in_progress": True, "done": False},
            "dm_check": {"available": True},
        },
    )


def test_dm_message_sent():
    job = linkedin_dm_job()
    dm: dict = {"profiles": {}}
    prof = job["recruiter_profile_url"]
    dm_state.record_connect(dm, job, prof)
    dm_state.set_pending_confirmed(dm, prof, True)
    dm_state.record_message(dm, job, prof, already_connected=True)
    actions = _action_states(job, dm, set(), set(), set(), li_cfg={"form_link_message_enabled": True})
    assert actions["dm_message"]["done"] is True
    assert actions["dm_connect"]["done"] is True


def test_human_review_disables_steps_in_card():
    from applications_ui_data import job_to_card
    from datetime import datetime
    from zoneinfo import ZoneInfo

    job = linkedin_dm_job(filter_result="needs_review")
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
    for state in card["actions"].values():
        assert state["available"] is False
