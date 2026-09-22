"""Coverage for LinkedIn URL/field repair scripts."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from retrieval.sources.linkedin import repair_fields, repair_urls


def test_repair_urls_dedupe_and_load_refs(tmp_path: Path):
    run_dir = tmp_path / "runs" / "browser-collect-2026"
    run_dir.mkdir(parents=True)
    payload = {
        "references": {
            "search_results": [
                {"url": "https://www.linkedin.com/in/a/"},
                {"url": "https://www.linkedin.com/in/a/"},
                {"url": ""},
            ]
        }
    }
    (run_dir / "refs.json").write_text(json.dumps(payload), encoding="utf-8")

    refs = repair_urls.load_refs_from_runs(tmp_path / "runs")
    assert len(refs) == 1
    assert refs[0]["url"].endswith("/in/a/")


def test_repair_urls_fixes_placeholder_post_url():
    jobs = [
        {
            "source": "linkedin_posts",
            "url": "linkedin-post:abc123",
            "company": "Acme",
            "role": "AI Engineer",
        }
    ]
    refs = [{"url": "https://www.linkedin.com/in/recruiter/", "profile_url": "https://www.linkedin.com/in/recruiter/"}]
    stats = repair_urls.repair_jobs(jobs, refs, resolve_posts=False)
    assert stats["post_url_fixed"] >= 0


@pytest.mark.asyncio
async def test_collect_refs_via_browser(monkeypatch):
    async def fake_collect(url, *, max_scrolls):
        return "raw", [{"url": "https://www.linkedin.com/in/x/"}], {"profile_refs": 1, "activity_urls": 0, "scrolls": 1}

    monkeypatch.setattr(repair_urls, "collect_feed_text", fake_collect)
    refs = await repair_urls.collect_refs_via_browser([{"query": "ai", "linkedin_url": "https://li/search"}], max_scrolls=2)
    assert len(refs) == 1


def test_repair_urls_main_dry_run(tmp_path: Path, monkeypatch):
    registry_path = tmp_path / "jobs.json"
    registry_path.write_text(json.dumps({"jobs": []}), encoding="utf-8")
    monkeypatch.setattr(repair_urls, "ROOT", tmp_path)
    monkeypatch.setattr(repair_urls, "load_refs_from_runs", lambda _d: [])
    monkeypatch.setattr(repair_urls, "load_registry", lambda: {"jobs": []})
    monkeypatch.setattr(repair_urls, "save_registry", lambda *_a: None)
    monkeypatch.setattr("sys.argv", ["repair_urls.py", "--dry-run"])
    assert repair_urls.main() == 0


def test_repair_urls_main_with_browser(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(repair_urls, "ROOT", tmp_path)
    monkeypatch.setattr(repair_urls, "load_refs_from_runs", lambda _d: [])
    monkeypatch.setattr(repair_urls, "load_registry", lambda: {"jobs": []})
    monkeypatch.setattr(repair_urls, "save_registry", lambda *_a: None)
    monkeypatch.setattr(repair_urls, "load_linkedin_config", lambda: {"queries": []})
    monkeypatch.setattr(repair_urls, "build_queries", lambda _c: [{"query": "ai", "linkedin_url": "https://li/search"}])
    monkeypatch.setattr(repair_urls, "collect_refs_via_browser", AsyncMock(return_value=[]))
    monkeypatch.setattr("sys.argv", ["repair_urls.py", "--browser", "--query-index", "1"])
    assert repair_urls.main() == 0


def test_repair_registry_dry_run_non_linkedin(monkeypatch):
    job = {
        "source": "remoteok",
        "role": "AI Engineer",
        "description_snippet": "Email careers@acme.ai to apply",
    }
    monkeypatch.setattr(repair_fields, "load_registry", lambda: {"jobs": [job]})
    monkeypatch.setattr(repair_fields, "load_refs_from_runs", lambda _d: [])
    monkeypatch.setattr(repair_fields, "save_registry", lambda *_a: None)
    stats = repair_fields.repair_registry(dry_run=True)
    assert stats["apply_email_set"] >= 0


def test_repair_registry_linkedin_post(monkeypatch):
    job = {
        "source": "linkedin_posts",
        "url": "https://www.linkedin.com/posts/acme_ai-engineer-activity-123",
        "company": "Acme AI ",
        "role": "AI Engineer",
        "description_snippet": "Hiring AI Engineer remote LATAM $120k apply https://example.com/apply",
        "apply_url": None,
        "track": "ai-engineer",
    }
    monkeypatch.setattr(repair_fields, "load_registry", lambda: {"jobs": [job]})
    monkeypatch.setattr(repair_fields, "load_refs_from_runs", lambda _d: [])
    monkeypatch.setattr(repair_fields, "save_registry", lambda *_a: None)
    monkeypatch.setattr(repair_fields, "load_linkedin_config", lambda _t: {"llm_intent_classify_enabled": False})
    stats = repair_fields.repair_registry(dry_run=True)
    assert stats["company_cleaned"] == 1


def test_repair_fields_main(monkeypatch):
    monkeypatch.setattr(repair_fields, "repair_registry", lambda **kwargs: {"company_cleaned": 0})
    monkeypatch.setattr("sys.argv", ["repair_fields.py", "--dry-run"])
    assert repair_fields.main() == 0


def test_repair_registry_salary_and_apply_url(monkeypatch):
    job = {
        "source": "linkedin_posts",
        "url": "https://www.linkedin.com/posts/acme_ai-engineer-activity-123",
        "company": "Acme AI ",
        "role": "AI Engineer",
        "description_snippet": "Hiring AI Engineer remote $120k USD apply https://example.com/apply",
        "salary_usd": 90000,
        "apply_url": "https://www.linkedin.com/search/results/content/",
        "track": "ai-engineer",
    }
    monkeypatch.setattr(repair_fields, "load_registry", lambda: {"jobs": [job]})
    monkeypatch.setattr(repair_fields, "load_refs_from_runs", lambda _d: [])
    monkeypatch.setattr(repair_fields, "save_registry", lambda *_a: None)
    monkeypatch.setattr(repair_fields, "load_linkedin_config", lambda _t: {"llm_intent_classify_enabled": False})
    stats = repair_fields.repair_registry(dry_run=True)
    assert stats["company_cleaned"] == 1
    assert stats["salary_fixed"] >= 0
    assert stats["apply_url_fixed"] >= 1


def test_repair_registry_post_url_reset(monkeypatch):
    job = {
        "source": "linkedin_posts",
        "url": "https://www.linkedin.com/posts/wrong-author_ai-engineer-activity-123",
        "company": "Acme AI",
        "role": "AI Engineer",
        "description_snippet": "Hiring",
        "recruiter_profile_url": "https://www.linkedin.com/in/other-recruiter/",
        "track": "ai-engineer",
    }
    monkeypatch.setattr(repair_fields, "load_registry", lambda: {"jobs": [job]})
    monkeypatch.setattr(repair_fields, "load_refs_from_runs", lambda _d: [])
    monkeypatch.setattr(repair_fields, "save_registry", lambda *_a: None)
    monkeypatch.setattr(repair_fields, "load_linkedin_config", lambda _t: {"llm_intent_classify_enabled": False})
    monkeypatch.setattr(
        repair_fields,
        "permalink_matches_author",
        lambda url, company, recruiter_profile_url=None: False,
    )
    stats = repair_fields.repair_registry(dry_run=True)
    assert stats["post_url_reset"] == 1
