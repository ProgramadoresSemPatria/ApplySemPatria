"""Regression tests for post_intent edge cases (parametrized)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from post_intent import (  # noqa: E402
    classify_post_intent,
    is_job_seeker_post,
    should_ingest_linkedin_post,
)
from tests.helpers.post_fixtures import (  # noqa: E402
    FOUNDER_SEEKING,
    HIRING_NO_SALARY,
    HIRING_WITH_SALARY,
    NOISE_POST,
    OPEN_TO_WORK,
    ROLE_KEYWORD_ONLY,
    VELIA_STYLE_SEEKER,
)


@pytest.mark.parametrize(
    "text,expected_seeker",
    [
        (OPEN_TO_WORK, True),
        (VELIA_STYLE_SEEKER, True),
        (FOUNDER_SEEKING, True),
        (HIRING_WITH_SALARY, False),
        (HIRING_NO_SALARY, False),
        (NOISE_POST, False),
    ],
)
def test_job_seeker_detection_parametrized(text, expected_seeker):
    assert is_job_seeker_post(text) is expected_seeker


@pytest.mark.parametrize(
    "text,expected_intent",
    [
        (HIRING_WITH_SALARY, "hiring"),
        (HIRING_NO_SALARY, "hiring"),
        (OPEN_TO_WORK, "job_seeker"),
        (VELIA_STYLE_SEEKER, "job_seeker"),
        (ROLE_KEYWORD_ONLY, "ambiguous"),
        (NOISE_POST, "noise"),
    ],
)
def test_classify_post_intent_parametrized(text, expected_intent):
    assert classify_post_intent(text) == expected_intent


@pytest.mark.parametrize(
    "text,should_ingest",
    [
        (HIRING_WITH_SALARY, True),
        (HIRING_NO_SALARY, True),
        (OPEN_TO_WORK, False),
        (VELIA_STYLE_SEEKER, False),
        (ROLE_KEYWORD_ONLY, False),
        (NOISE_POST, False),
    ],
)
def test_should_ingest_parametrized(text, should_ingest):
    ingest, _reason = should_ingest_linkedin_post(text, cfg={})
    assert ingest is should_ingest


def test_llm_rejects_seeker_when_enabled():
    def llm(_text, _headline):
        return "job_seeker"

    ingest, reason = should_ingest_linkedin_post(
        ROLE_KEYWORD_ONLY,
        cfg={"llm_intent_classify_enabled": True},
        llm_classify=llm,
    )
    assert ingest is False
    assert reason == "llm_job_seeker"


def test_llm_noise_rejects_ambiguous():
    def llm(_text, _headline):
        return "noise"

    ingest, reason = should_ingest_linkedin_post(
        ROLE_KEYWORD_ONLY,
        cfg={"llm_intent_classify_enabled": True},
        llm_classify=llm,
    )
    assert ingest is False
    assert reason == "llm_noise"


def test_is_borderline_post():
    from post_intent import is_borderline_post

    assert is_borderline_post("") is False
    assert is_borderline_post(ROLE_KEYWORD_ONLY) is True
    assert is_borderline_post(HIRING_WITH_SALARY) is False


def test_legacy_role_keyword_ingest_flag():
    ingest, reason = should_ingest_linkedin_post(
        ROLE_KEYWORD_ONLY,
        cfg={"allow_role_keyword_ingest": True},
    )
    assert ingest is True
    assert reason == "role_keyword_legacy"


def test_filter_require_usd_salary_paths():
    from post_intent import classify_linkedin_post_filter

    with_salary = classify_linkedin_post_filter(
        HIRING_WITH_SALARY, "$120k", {"require_usd_salary": True}
    )
    assert with_salary.filter_result == "eligible"

    no_salary = classify_linkedin_post_filter(
        HIRING_NO_SALARY, None, {"require_usd_salary": True, "posts_default_filter_result": "skipped"}
    )
    assert no_salary.filter_result == "skipped"
