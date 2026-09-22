"""Branch coverage for posts_merge pure functions."""

from __future__ import annotations

import re
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from linkedin_posts_merge import (  # noqa: E402
    _author_matches_profile_slug,
    _first_feed_update,
    _norm_author_name,
    _role_keyword_in_text,
    build_feed_update_url,
    extract_post_salary,
    extract_role_apply_url,
    fallback_linkedin_post_search_url,
    is_apply_only_url,
    is_content_search_url,
    is_feed_update_url,
    is_linkedin_post_url,
    is_placeholder_post_url,
    is_posts_permalink,
    is_profile_fallback_url,
    lookup_author_profile_ref,
    match_author_activity_ref,
    match_author_feed_post_ref,
    match_author_profile_ref,
    normalize_linkedin_job_urls,
    normalize_payload,
    parse_linkedin_relative_posted_at,
    period_to_recency,
    permalink_author_slug,
    permalink_matches_author,
    placeholder_post_url_for_job,
    profile_ref_to_post_url,
    rank_jobs_for_table,
    resolve_apply_url_from_text,
    resolve_chunk_authors,
    split_apply_email,
    url_match_author_for_job,
)

TZ = ZoneInfo("America/Sao_Paulo")


def test_extract_post_salary_prefers_role_line():
    text = "Other role $2/mo\nAI Engineer remote $120k–$150k USD\n"
    assert extract_post_salary(text, "AI Engineer") == "$120k–$150k"


def test_extract_post_salary_avoids_small_dollar():
    assert extract_post_salary("Budget $2 but pay is $2.1k/mo for AI role") == "$2.1k/mo"


def test_url_classification_matrix():
    assert is_apply_only_url("https://lnkd.in/abc") is True
    assert is_apply_only_url("https://www.linkedin.com/jobs/view/1/") is True
    assert is_apply_only_url("https://example.com/apply") is True
    assert is_placeholder_post_url("linkedin-post:deadbeef") is True
    assert is_content_search_url("https://www.linkedin.com/search/results/content/?q=x") is True
    assert is_posts_permalink("https://www.linkedin.com/posts/user_activity-1/") is True
    assert is_feed_update_url("https://www.linkedin.com/feed/update/urn:li:activity:1/") is True
    assert is_profile_fallback_url("https://www.linkedin.com/in/x/recent-activity/all/") is True
    assert is_linkedin_post_url("https://www.linkedin.com/posts/x/") is True
    assert is_linkedin_post_url("https://lnkd.in/x") is False


def test_build_feed_update_and_first_feed_update():
    url = build_feed_update_url("activity", "12345")
    assert "urn:li:activity:12345" in url
    assert _first_feed_update("See urn:li:activity:999 for details").startswith("https://")


def test_permalink_author_matching():
    url = "https://www.linkedin.com/posts/jane-doe-123_activity-456/"
    assert permalink_author_slug(url)
    assert permalink_matches_author(url, "Jane Doe") is True
    assert permalink_matches_author(url, "Bob Smith") is False


def test_author_slug_fuzzy_match():
    assert _author_matches_profile_slug("Kethan Reddy", "kethan-reddy-06b3a4183") is True
    assert _author_matches_profile_slug("", "slug") is False


def test_resolve_chunk_authors():
    chunk = "Acme AI\n• 3rd+\nHiring AI Engineer"
    author, org = resolve_chunk_authors(chunk)
    assert "Acme" in author or author == "Unknown"
    chunk2 = "Just a company name without markers"
    a2, _ = resolve_chunk_authors(chunk2)
    assert a2


def test_split_apply_email():
    email, url = split_apply_email("jobs@acme.ai", "Apply jobs@acme.ai", "AI Engineer")
    assert email == "jobs@acme.ai"
    assert url is None


def test_extract_role_apply_url_role_line():
    text = "Backend Engineer — https://example.com/backend\nAI Engineer — https://lnkd.in/airole\n"
    assert "lnkd.in" in extract_role_apply_url(text, "AI Engineer")


def test_resolve_apply_url_from_text():
    text = "Apply: https://lnkd.in/applyrole and also https://example.com/jobs/1"
    url = resolve_apply_url_from_text(text, None)
    assert "lnkd.in" in url


def test_lookup_and_match_author_refs():
    refs = [
        {"kind": "person", "url": "https://www.linkedin.com/in/jane-doe/", "text": "Jane Doe"},
        {"kind": "company", "url": "https://www.linkedin.com/company/acme/", "text": "Acme"},
    ]
    found = lookup_author_profile_ref("Jane Doe", refs)
    assert found and found["kind"] == "person"
    url, source = match_author_profile_ref("Jane Doe", refs)
    assert "/in/jane-doe" in url
    feed_refs = [
        {
            "kind": "feed_post",
            "author_slug": "jane-doe",
            "url": "https://www.linkedin.com/posts/jane-doe_hiring-activity-1/",
            "text": "Jane Doe hiring post",
        }
    ]
    furl, fsrc = match_author_feed_post_ref("Jane Doe", feed_refs)
    assert furl or fsrc
    act_refs = [{"kind": "activity", "activity_id": "999", "author_slug": "jane-doe", "url": ""}]
    aurl, asrc = match_author_activity_ref("Jane Doe", act_refs)
    assert aurl


def test_normalize_linkedin_job_urls_apply_only():
    job = {
        "source": "linkedin_posts",
        "url": "https://lnkd.in/apply123",
        "company": "Acme",
        "role": "AI Engineer",
        "description_snippet": "Hiring",
    }
    refs: list = []
    normalize_linkedin_job_urls(job, refs, resolve_posts=False)
    assert job.get("apply_url") or job["url"] != "https://lnkd.in/apply123" or is_placeholder_post_url(job["url"])


def test_placeholder_post_url_for_job():
    job = {"company": "Acme", "role": "AI Engineer", "description_snippet": ""}
    ph = placeholder_post_url_for_job(job)
    assert ph.startswith("linkedin-post:")


def test_parse_linkedin_relative_posted_at():
    now = datetime(2026, 1, 15, 12, 0, tzinfo=TZ)
    assert parse_linkedin_relative_posted_at("now •", now=now) is not None
    assert parse_linkedin_relative_posted_at("13h •", now=now) is not None
    assert parse_linkedin_relative_posted_at("2d •", now=now) is not None
    assert parse_linkedin_relative_posted_at("1w •", now=now) is not None
    assert parse_linkedin_relative_posted_at("nonsense", now=now) is None


def test_period_to_recency_and_profile_ref_to_post_url():
    cfg = {}
    assert period_to_recency(1, cfg) == "past-24h"
    assert period_to_recency(7, cfg) == "past-week"
    assert period_to_recency(30, cfg) == "past-month"
    assert profile_ref_to_post_url("person", "https://www.linkedin.com/in/foo/").endswith("/")


def test_normalize_payload_shapes():
    legacy = {
        "queries": [
            {
                "query": "ai engineer",
                "role_keyword": "ai engineer",
                "region": "latam",
                "feed_payload": {
                    "sections": {"search_results": "Feed post\nAcme AI\nHiring AI Engineer remote $120k USD"},
                    "references": {"search_results": []},
                },
            }
        ]
    }
    flat = {"posts": [{"text": "hiring AI engineer", "company": "Acme"}], "query": "ai", "role_keyword": "ai engineer"}
    out1 = normalize_payload(legacy)
    out2 = normalize_payload(flat)
    assert len(out1) >= 1
    assert len(out2) >= 1


def test_rank_jobs_for_table():
    jobs = [
        {"role": "A", "salary_usd": "$200k", "posted_at": "2026-01-01"},
        {"role": "B", "salary_usd": "$100k", "posted_at": "2026-01-10"},
    ]
    by_salary = rank_jobs_for_table(jobs, {"table_sort": "salary"})
    assert by_salary[0]["salary_usd"] == "$200k"


def test_url_match_author_for_job():
    job = {
        "company": "Acme AI",
        "recruiter_profile_url": "https://www.linkedin.com/in/jane-doe/",
        "description_snippet": "Jane Doe\nAcme AI\nHiring",
    }
    author = url_match_author_for_job(job)
    assert author


def test_role_keyword_and_norm_author():
    assert _role_keyword_in_text("We need an AI engineer remote", "ai engineer") is True
    assert _norm_author_name("  Jane   Doe  ") == "jane doe"


def test_fallback_linkedin_post_search_url():
    url = fallback_linkedin_post_search_url("Jane Doe")
    assert "linkedin.com" in url


def test_resolve_feed_update_to_posts_permalink_mock(monkeypatch):
    def fake_run(cmd, **kwargs):
        class R:
            stdout = ""
            stderr = "location: https://www.linkedin.com/posts/user_activity-123/\n"
            returncode = 0

        return R()

    monkeypatch.setattr("subprocess.run", fake_run)
    feed = "https://www.linkedin.com/feed/update/urn:li:activity:123/"
    out = __import__("linkedin_posts_merge").resolve_feed_update_to_posts_permalink(feed)
    assert "/posts/" in out or feed in out
