"""Tests for post_intent classification."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from post_intent import (  # noqa: E402
    classify_linkedin_post_filter,
    classify_post_intent,
    has_hiring_intent,
    is_job_seeker_post,
    should_ingest_linkedin_post,
)


HIRING_POST = (
    "We're hiring an AI Engineer — remote LATAM. USD 120k. Apply via DM or email."
)
SEEKER_POST = (
    "Open to remote AI Engineer opportunities. #OpenToWork — looking for my next role. "
    "Not the hiring manager, just networking."
)
ROLE_ONLY_POST = "AI Engineer with 5 years experience in RAG and LangChain."


def test_hiring_intent_detected():
    assert has_hiring_intent(HIRING_POST) is True
    assert classify_post_intent(HIRING_POST) == "hiring"


def test_job_seeker_rejected():
    assert is_job_seeker_post(SEEKER_POST) is True
    assert classify_post_intent(SEEKER_POST) == "job_seeker"


def test_role_only_is_ambiguous_not_hiring():
    assert has_hiring_intent(ROLE_ONLY_POST) is False
    assert classify_post_intent(ROLE_ONLY_POST) == "ambiguous"


def test_should_not_ingest_seeker():
    ingest, reason = should_ingest_linkedin_post(SEEKER_POST)
    assert ingest is False
    assert reason == "job_seeker_post"


def test_should_not_ingest_role_only_without_hiring():
    ingest, reason = should_ingest_linkedin_post(ROLE_ONLY_POST, cfg={})
    assert ingest is False
    assert reason == "no_hiring_intent"


def test_should_ingest_hiring_post():
    ingest, reason = should_ingest_linkedin_post(HIRING_POST)
    assert ingest is True
    assert reason == "hiring_intent"


def test_filter_hiring_with_salary_eligible():
    filt = classify_linkedin_post_filter(HIRING_POST, "$120k", {})
    assert filt.filter_result == "eligible"
    assert filt.post_intent == "hiring"


def test_filter_hiring_no_salary_needs_review():
    text = "We're hiring an AI Engineer remote. Apply now via DM."
    filt = classify_linkedin_post_filter(text, None, {"posts_default_filter_result": "needs_review"})
    assert filt.filter_result == "needs_review"
    assert filt.skip_reason == "no_usd_salary_in_post"


def test_filter_seeker_skipped():
    filt = classify_linkedin_post_filter(SEEKER_POST, None, {})
    assert filt.filter_result == "skipped"
    assert filt.post_intent == "job_seeker"


def test_filter_ambiguous_skipped():
    filt = classify_linkedin_post_filter(ROLE_ONLY_POST, None, {})
    assert filt.filter_result == "skipped"
    assert filt.post_intent == "ambiguous"


def test_llm_callback_can_admit_borderline():
    def llm(_text, _headline):
        return "hiring"

    ingest, reason = should_ingest_linkedin_post(
        ROLE_ONLY_POST,
        cfg={"llm_intent_classify_enabled": True},
        llm_classify=llm,
    )
    assert ingest is True
    assert reason == "llm_hiring"
