#!/usr/bin/env python3
"""Tests for position disposition triage."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from position_disposition import (  # noqa: E402
    DISPOSITION_AUTO,
    DISPOSITION_BEST_FIT,
    DISPOSITION_HUMAN_REVIEW,
    DISPOSITION_NOT_REAL,
    DISPOSITION_REAL_ROLE,
    application_steps_enabled,
    auto_disposition_for_job,
    clear_job_disposition,
    disposition_label,
    get_disposition,
    include_in_apply_table,
    set_job_disposition,
    update_disposition,
)


def test_eligible_auto_best_fit_with_steps():
    job = {"role": "AI Engineer", "filter_result": "eligible"}
    assert auto_disposition_for_job(job) == DISPOSITION_BEST_FIT
    assert get_disposition(job) == DISPOSITION_BEST_FIT
    assert application_steps_enabled(job) is True


def test_needs_review_auto_no_steps():
    job = {"role": "AI Engineer", "filter_result": "needs_review"}
    assert auto_disposition_for_job(job) == DISPOSITION_HUMAN_REVIEW
    assert application_steps_enabled(job) is False


def test_skipped_auto_not_real():
    job = {"role": "Annotator", "filter_result": "skipped"}
    assert auto_disposition_for_job(job) == DISPOSITION_NOT_REAL
    assert include_in_apply_table(job) is False


def test_real_role_enables_steps_from_human_review():
    job = {"role": "AI Engineer", "filter_result": "needs_review"}
    set_job_disposition(job, DISPOSITION_REAL_ROLE)
    assert get_disposition(job) == DISPOSITION_REAL_ROLE
    assert disposition_label(get_disposition(job)) == "Real role"
    assert application_steps_enabled(job) is True


def test_reset_to_auto_clears_override():
    job = {"role": "AI Engineer", "filter_result": "needs_review", "position_disposition": "best_fit"}
    set_job_disposition(job, DISPOSITION_AUTO)
    assert get_disposition(job) == DISPOSITION_HUMAN_REVIEW


def test_update_disposition_in_registry():
    registry = {
        "jobs": [
            {
                "url": "https://example.com/job/1",
                "role": "AI Engineer",
                "company": "Acme",
                "filter_result": "eligible",
            },
        ]
    }
    from registry import job_key  # noqa: E402

    jk = job_key(registry["jobs"][0])
    updated = update_disposition(registry, jk, DISPOSITION_NOT_REAL)
    assert updated is not None
    assert get_disposition(updated) == DISPOSITION_NOT_REAL
