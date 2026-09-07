"""Unit tests for reclassify_linkedin_posts registry backfill."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from tests.helpers.post_fixtures import (  # noqa: E402
    HIRING_NO_SALARY,
    HIRING_WITH_SALARY,
    OPEN_TO_WORK,
    ROLE_KEYWORD_ONLY,
)


def _linkedin_job(snippet: str, **extra):
    job = {
        "source": "linkedin_posts",
        "url": f"https://www.linkedin.com/posts/test-{hash(snippet) & 0xffff:x}/",
        "role": "AI Engineer",
        "company": "Test Co",
        "description_snippet": snippet,
        "filter_result": "needs_review",
    }
    job.update(extra)
    return job


@patch("reclassify_linkedin_posts.save_registry")
@patch("reclassify_linkedin_posts.load_registry")
@patch("reclassify_linkedin_posts.load_linkedin_config")
def test_reclassify_marks_seeker_skipped(mock_cfg, mock_load, mock_save):
    from reclassify_linkedin_posts import reclassify_linkedin_posts

    mock_cfg.return_value = {"posts_default_filter_result": "needs_review"}
    seeker = _linkedin_job(OPEN_TO_WORK)
    hiring = _linkedin_job(HIRING_WITH_SALARY, salary_usd="USD 120k", filter_result="eligible")
    mock_load.return_value = {"jobs": [seeker, hiring]}

    stats = reclassify_linkedin_posts(dry_run=False)

    assert stats["total"] == 2
    assert stats["skipped_seeker"] >= 1
    assert seeker["filter_result"] == "skipped"
    assert seeker["post_intent"] == "job_seeker"
    assert seeker["skip_reason"] == "job_seeker_post"
    mock_save.assert_called_once()


@patch("reclassify_linkedin_posts.save_registry")
@patch("reclassify_linkedin_posts.load_registry")
@patch("reclassify_linkedin_posts.load_linkedin_config")
def test_reclassify_hiring_no_salary_stays_needs_review(mock_cfg, mock_load, mock_save):
    from reclassify_linkedin_posts import reclassify_linkedin_posts

    mock_cfg.return_value = {"posts_default_filter_result": "needs_review"}
    job = _linkedin_job(HIRING_NO_SALARY)
    mock_load.return_value = {"jobs": [job]}

    stats = reclassify_linkedin_posts(dry_run=False)

    assert stats["needs_review"] == 1
    assert job["filter_result"] == "needs_review"
    assert job["post_intent"] == "hiring"


@patch("reclassify_linkedin_posts.save_registry")
@patch("reclassify_linkedin_posts.load_registry")
@patch("reclassify_linkedin_posts.load_linkedin_config")
def test_reclassify_role_only_becomes_skipped_noise(mock_cfg, mock_load, mock_save):
    from reclassify_linkedin_posts import reclassify_linkedin_posts

    mock_cfg.return_value = {"posts_default_filter_result": "needs_review"}
    job = _linkedin_job(ROLE_KEYWORD_ONLY, filter_result="needs_review")
    mock_load.return_value = {"jobs": [job]}

    stats = reclassify_linkedin_posts(dry_run=False)

    assert stats["skipped_noise"] >= 1
    assert job["filter_result"] == "skipped"
    assert job["post_intent"] == "ambiguous"


@patch("reclassify_linkedin_posts.save_registry")
@patch("reclassify_linkedin_posts.load_registry")
@patch("reclassify_linkedin_posts.load_linkedin_config")
def test_reclassify_dry_run_does_not_save(mock_cfg, mock_load, mock_save):
    from reclassify_linkedin_posts import reclassify_linkedin_posts

    mock_cfg.return_value = {}
    job = _linkedin_job(OPEN_TO_WORK)
    before = dict(job)
    mock_load.return_value = {"jobs": [job]}

    reclassify_linkedin_posts(dry_run=True)

    mock_save.assert_not_called()
    assert job == before
