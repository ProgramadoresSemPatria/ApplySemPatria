"""Extended posts_merge pure-function coverage."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from linkedin_posts_merge import (  # noqa: E402
    backfill_registry_recruiter_profiles,
    harvest_feed_posts_from_network_body,
    match_author_profile_ref,
    merge_payload,
    pick_post_url_for_new_chunk,
)


def test_harvest_feed_posts_from_network_body():
    body = (
        '{"entityUrn":"urn:li:activity:12345","actor":{"name":{"text":"Jane Recruiter"}},'
        '"commentary":{"text":{"text":"Hiring AI Engineer"}}}'
    )
    posts = harvest_feed_posts_from_network_body(body)
    assert len(posts) == 1
    assert posts[0]["activity_id"] == "12345"
    assert "12345" in posts[0]["url"]


def test_harvest_skips_huge_body():
    assert harvest_feed_posts_from_network_body("x" * 6_000_000) == []


def test_match_author_profile_ref():
    refs = [
        {
            "kind": "person",
            "url": "https://www.linkedin.com/in/jane-recruiter/",
            "text": "Jane Recruiter",
        }
    ]
    url, source = match_author_profile_ref("Jane Recruiter", refs)
    assert url and "jane-recruiter" in url
    assert source.startswith("person_")


def test_pick_post_url_for_new_chunk():
    html_posts = [
        {"author": "Acme AI", "url": "https://www.linkedin.com/feed/update/urn:li:activity:999"},
    ]
    url, source = pick_post_url_for_new_chunk(
        "Acme AI",
        html_posts=html_posts,
        article_cards=[],
        used_urls=set(),
        author_url_map={},
        profile_refs=[],
        activity_refs=[],
    )
    assert url and "999" in url


def test_backfill_registry_recruiter_profiles(monkeypatch):
    job = {
        "source": "linkedin_posts",
        "url": "https://www.linkedin.com/posts/acme_ai-engineer-activity-123",
        "discovered_at": "2026-09-10T12:00:00-03:00",
    }
    registry = {"jobs": [job]}

    monkeypatch.setattr("linkedin_posts_merge.load_registry", lambda: registry)
    monkeypatch.setattr("linkedin_posts_merge.save_registry", lambda reg: registry.update(reg))
    monkeypatch.setattr(
        "linkedin_posts_merge.enrich_job_recruiter_profile",
        lambda job, refs, resolve_posts=True: job.update({"recruiter_profile_url": "https://www.linkedin.com/in/r/"}) or True,
    )

    stats = backfill_registry_recruiter_profiles(since=datetime(2020, 1, 1, tzinfo=timezone.utc))
    assert stats["scanned"] == 1
    assert stats["resolved"] == 1


def test_merge_payload_mocked(monkeypatch, tmp_path):
    post = {
        "author": "Acme",
        "text": "Hiring AI Engineer remote $120k USD apply",
        "url": "https://www.linkedin.com/posts/acme_ai-engineer-activity-123",
    }
    payload = {
        "period_days": 7,
        "queries": [{"query": "ai", "role_keyword": "AI Engineer", "region": "worldwide", "posts": [post]}],
    }
    job = {"url": post["url"], "role": "AI Engineer", "filter_result": "eligible", "source": "linkedin_posts"}

    monkeypatch.setattr("linkedin_posts_merge.load_linkedin_config", lambda: {"roles": ["AI Engineer"]})
    monkeypatch.setattr("linkedin_posts_merge.load_json", lambda *a, **k: {})
    monkeypatch.setattr("linkedin_posts_merge.load_registry", lambda: {"jobs": []})
    monkeypatch.setattr(
        "linkedin_posts_merge.normalize_payload",
        lambda p: [{"post": post, "query_meta": {"query": "ai"}, "refs": []}],
    )
    monkeypatch.setattr("linkedin_posts_merge.post_to_job", lambda *a, **k: dict(job))
    monkeypatch.setattr("linkedin_posts_merge.job_key", lambda j: j["url"])
    monkeypatch.setattr("linkedin_posts_merge.merge_jobs", lambda reg, inc, since: (reg, [job]))
    monkeypatch.setattr("linkedin_posts_merge.patch_recruiter_profiles_on_known", lambda *a: 0)
    monkeypatch.setattr("linkedin_posts_merge.save_registry", lambda *a: None)
    monkeypatch.setattr("linkedin_posts_merge.write_linkedin_run_markdown", lambda *a, **k: None)
    monkeypatch.setattr("linkedin_posts_merge.save_json", lambda *a, **k: None)
    monkeypatch.setattr("linkedin_posts_merge.RUNS_DIR", tmp_path)
    monkeypatch.setattr("audit_log.info", MagicMock())

    result = merge_payload(payload, 7)
    assert result["new_total"] == 1
