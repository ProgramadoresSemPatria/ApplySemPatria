"""Integration tests: merge pipeline + post intent filtering."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from tests.helpers.example_configs import load_example_linkedin_config  # noqa: E402
from tests.helpers.post_fixtures import HIRING_WITH_SALARY, OPEN_TO_WORK  # noqa: E402


@patch("linkedin_posts_merge.save_registry")
@patch("linkedin_posts_merge.load_registry")
@patch("linkedin_posts_merge.load_linkedin_config")
def test_merge_payload_skips_job_seeker_posts(mock_li_cfg, mock_load_reg, mock_save_reg):
    from linkedin_posts_merge import merge_payload

    mock_li_cfg.return_value = load_example_linkedin_config()
    mock_load_reg.return_value = {"jobs": []}

    payload = {
        "period_days": 1,
        "queries": [
            {
                "query": "ai engineer latam",
                "role_keyword": "ai engineer",
                "region": "latam",
                "posts": [
                    {
                        "text": OPEN_TO_WORK,
                        "url": "https://www.linkedin.com/feed/update/urn:li:activity:111/",
                        "author": {"name": "Job Seeker"},
                    },
                    {
                        "text": HIRING_WITH_SALARY,
                        "url": "https://www.linkedin.com/feed/update/urn:li:activity:222/",
                        "author": {"name": "Recruiter"},
                    },
                ],
            }
        ],
    }

    result = merge_payload(payload, period_days=1, since_arg="30d")

    saved_registry = mock_save_reg.call_args[0][0]
    new_jobs = [j for j in saved_registry["jobs"] if j.get("source") == "linkedin_posts"]
    assert len(new_jobs) == 1
    assert new_jobs[0].get("post_intent") == "hiring"
    assert result["posts_parsed"] == 1
    assert result["new_total"] == 1


@patch("linkedin_posts_merge.save_registry")
@patch("linkedin_posts_merge.load_registry")
@patch("linkedin_posts_merge.load_linkedin_config")
def test_merge_payload_fetched_count_excludes_rejected(mock_li_cfg, mock_load_reg, mock_save_reg):
    from linkedin_posts_merge import merge_payload

    mock_li_cfg.return_value = load_example_linkedin_config()
    mock_load_reg.return_value = {"jobs": []}

    payload = {
        "period_days": 1,
        "queries": [
            {
                "query": "ai engineer latam",
                "role_keyword": "ai engineer",
                "region": "latam",
                "posts": [
                    {
                        "text": OPEN_TO_WORK,
                        "url": "https://www.linkedin.com/feed/update/urn:li:activity:333/",
                        "author": {"name": "Seeker Only"},
                    },
                ],
            }
        ],
    }

    result = merge_payload(payload, period_days=1, since_arg="30d")

    assert result["posts_parsed"] == 0
    assert result["new_total"] == 0
    assert mock_save_reg.call_args[0][0]["jobs"] == []
