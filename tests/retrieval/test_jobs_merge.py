"""Pure-function coverage for linkedin_jobs_merge."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from linkedin_jobs_merge import (  # noqa: E402
    audit_collect_results,
    build_all_track_queries,
    existing_job_view_ids,
    extract_job_ids_from_html,
    extract_posted_label,
    merge_payload,
    normalize_payload,
    parse_listings_from_text,
    posted_within_hours,
    region_search_variants,
)

TZ = ZoneInfo("America/Sao_Paulo")


def test_extract_posted_label_variants():
    assert extract_posted_label("Reposted 3 hours ago") == "3h"
    assert extract_posted_label("Posted 2 days ago") == "2d"
    assert extract_posted_label("Just now") == "now"


def test_posted_within_hours_label_and_timestamp():
    now = datetime(2026, 9, 10, 12, 0, tzinfo=TZ)
    assert posted_within_hours({"posted_label": "2h"}, 24, now=now) is True
    assert posted_within_hours({"posted_label": "3d"}, 24, now=now) is False
    assert posted_within_hours({"posted_label": "now"}, 24, now=now) is True
    assert posted_within_hours({"posted_at": "2026-09-10T11:00:00-03:00"}, 24, now=now) is True


def test_region_search_variants_dedupes():
    cfg = {
        "region_location_alts": {"latam": ["Brazil", "Brazil"]},
        "region_geo_ids": {"latam": "123"},
    }
    variants = region_search_variants("latam", cfg)
    assert len(variants) == 1
    assert variants[0]["geo_id"] == "123"


def test_parse_listings_from_text_view_url():
    raw = (
        "Staff AI Engineer\nAcme AI\nRemote · Full-time\n"
        "https://www.linkedin.com/jobs/view/1234567890\nEasy Apply\n2 hours ago"
    )
    listings = parse_listings_from_text(raw)
    assert len(listings) == 1
    assert listings[0]["job_id"] == "1234567890"
    assert listings[0]["easy_apply"] is True


def test_parse_listings_from_text_block_fallback():
    raw = (
        "Senior ML Engineer\n\n"
        "OpenAI\nRemote\n\n"
        "https://www.linkedin.com/jobs/view/9876543210\nApply on company website"
    )
    listings = parse_listings_from_text(raw)
    assert any(x["job_id"] == "9876543210" for x in listings)


def test_extract_job_ids_from_html():
    html = '<a href="https://www.linkedin.com/jobs/view/111">A</a><a href="/jobs/view/222">B</a>'
    ids = extract_job_ids_from_html(html)
    assert ids == ["111", "222"]


def test_existing_job_view_ids():
    registry = {
        "jobs": [
            {"url": "https://www.linkedin.com/jobs/view/555"},
            {"apply_url": "https://linkedin.com/jobs/view/666"},
        ]
    }
    assert existing_job_view_ids(registry) == {"555", "666"}


def test_normalize_payload_from_search_payload():
    payload = {
        "queries": [
            {
                "query": "ai engineer remote",
                "role_keyword": "AI Engineer",
                "region": "worldwide",
                "search_payload": {
                    "html": "Job 1234567890 Easy Apply",
                    "inner_text": "Staff AI Engineer\nAcme\nhttps://www.linkedin.com/jobs/view/1234567890",
                },
            }
        ]
    }
    items = normalize_payload(payload)
    assert len(items) == 1
    assert items[0]["query_meta"]["query"] == "ai engineer remote"


def test_audit_collect_results_flags_issues(tmp_path):
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps({"listings": [{"title": "Job 1234567890", "company": "—"}]}), encoding="utf-8")
    results = [
        {
            "track": "ai-engineer",
            "region": "worldwide",
            "role_keyword": "AI Engineer",
            "listings": [{"title": "Job 9999999999", "company": "—"}],
            "page_stats": {"pages": 1},
            "raw_path": str(raw),
        },
        {
            "track": "ai-engineer",
            "region": "latam",
            "role_keyword": "AI Engineer",
            "listings": [{"title": "Job 8888888888", "company": "—"}],
            "page_stats": {"pages": 1},
        },
    ]
    audit = audit_collect_results(results)
    assert audit["placeholder_titles"] >= 2
    assert audit["issues"]


def test_merge_payload_mocked(monkeypatch, tmp_path):
    listing = {
        "job_id": "1234567890",
        "url": "https://www.linkedin.com/jobs/view/1234567890",
        "title": "AI Engineer",
        "company": "Acme",
        "location": "Remote",
        "posted_label": "1d",
        "easy_apply": True,
        "apply_method": "easy_apply",
    }
    payload = {
        "period_days": 7,
        "queries": [{"query": "ai", "role_keyword": "AI Engineer", "region": "worldwide", "listings": [listing]}],
    }
    job = {"url": listing["url"], "role": "AI Engineer", "filter_result": "eligible"}

    monkeypatch.setattr("linkedin_jobs_merge.load_linkedin_jobs_config", lambda tid=None: {"roles": ["AI Engineer"]})
    monkeypatch.setattr("linkedin_jobs_merge.load_json", lambda *a, **k: {})
    monkeypatch.setattr("linkedin_jobs_merge.load_registry", lambda: {"jobs": []})
    monkeypatch.setattr("linkedin_jobs_merge.listing_to_job", lambda *a, **k: dict(job))
    monkeypatch.setattr("linkedin_jobs_merge.merge_jobs", lambda reg, inc, since: (reg, [job]))
    monkeypatch.setattr("linkedin_jobs_merge.save_registry", lambda *a: None)
    monkeypatch.setattr("linkedin_jobs_merge.write_jobs_run_markdown", lambda *a, **k: None)
    monkeypatch.setattr("linkedin_jobs_merge.save_json", lambda *a, **k: None)
    monkeypatch.setattr("linkedin_jobs_merge.RUNS_DIR", tmp_path)

    result = merge_payload(payload, 7)
    assert result["new_total"] == 1
    assert result["eligible"] == 1


def test_build_all_track_queries(monkeypatch):
    monkeypatch.setattr("track_store.list_track_ids", lambda: ["ai-engineer"])
    monkeypatch.setattr(
        "linkedin_jobs_merge.build_queries",
        lambda cfg, track_id=None: [
            {
                "query": "ai engineer",
                "track": track_id,
                "role_keyword": "AI Engineer",
                "region": "worldwide",
                "search_location": "",
            }
        ],
    )
    monkeypatch.setattr(
        "linkedin_jobs_merge.load_linkedin_jobs_config",
        lambda tid=None: {"jobs_collect_enabled": True},
    )
    queries = build_all_track_queries()
    assert len(queries) == 1
    assert queries[0]["track"] == "ai-engineer"
