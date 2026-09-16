"""Recruiter profile URLs must be persisted during LinkedIn post ingestion."""

from __future__ import annotations

from unittest.mock import patch

from application_channel import recruiter_profile_url
from linkedin_posts_merge import (
    enrich_job_recruiter_profile,
    parse_feed_search_posts,
    post_to_job,
    resolve_recruiter_profile_url,
)
from tests.helpers.jobs import linkedin_dm_job


def _sample_refs():
    return [
        {
            "kind": "feed_post",
            "url": "https://www.linkedin.com/feed/update/urn:li:activity:7503481913303584769/",
            "author_slug": "monikakuqi",
            "activity_id": "7503481913303584769",
            "urn_kind": "activity",
        },
        {
            "kind": "person",
            "url": "https://www.linkedin.com/in/monikakuqi/",
            "text": "Monika Kuqi",
        },
    ]


def test_resolve_recruiter_profile_url_from_feed_post_slug():
    refs = _sample_refs()
    url = "https://www.linkedin.com/feed/update/urn:li:activity:7503481913303584769/"
    assert resolve_recruiter_profile_url("Monika Kuqi", url, refs) == "https://www.linkedin.com/in/monikakuqi/"


def test_parse_feed_search_posts_attaches_recruiter_profile_url():
    raw = (
        "Feed post\n\n"
        "Monika Kuqi\n\n1d • \n\nFollow\n\nHiring AI Engineer LATAM USD 120k\n"
    )
    posts = parse_feed_search_posts(
        {"sections": {"search_results": raw}, "references": {"search_results": _sample_refs()}}
    )
    assert len(posts) == 1
    assert posts[0]["recruiter_profile_url"] == "https://www.linkedin.com/in/monikakuqi/"


def test_post_to_job_persists_recruiter_profile_url():
    post = {
        "text": "Hiring AI Engineer remote LATAM USD 120k",
        "url": "https://www.linkedin.com/feed/update/urn:li:activity:7503481913303584769/",
        "author": "Monika Kuqi",
        "recruiter_profile_url": "https://www.linkedin.com/in/monikakuqi/",
    }
    cfg = {"require_usd_salary": False}
    job = post_to_job(post, {"query": "q", "role_keyword": "AI Engineer", "region": "latam"}, cfg, {})
    assert job is not None
    assert job["recruiter_profile_url"] == "https://www.linkedin.com/in/monikakuqi/"
    assert recruiter_profile_url(job) == "https://www.linkedin.com/in/monikakuqi/"


def test_enrich_job_resolves_posts_permalink_when_curl_succeeds():
    job = linkedin_dm_job()
    job["url"] = "https://www.linkedin.com/feed/update/urn:li:activity:7503481913303584769/"
    job.pop("recruiter_profile_url", None)
    with patch(
        "linkedin_posts_merge.resolve_feed_update_to_posts_permalink",
        return_value="https://www.linkedin.com/posts/monikakuqi_hiring-ai-engineer-activity-7503481913303584769-abcd/",
    ):
        assert enrich_job_recruiter_profile(job, [], resolve_posts=True) is True
    assert job["recruiter_profile_url"] == "https://www.linkedin.com/in/monikakuqi/"
    assert "linkedin.com/posts/" in job["url"]
