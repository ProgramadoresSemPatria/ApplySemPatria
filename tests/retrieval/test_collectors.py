"""Unit coverage for board collectors under retrieval/."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from retrieval.sources.boards.collectors import defi, f6s, opentoworkremote, remoteok, wellfound
from retrieval.sources.boards.collectors.wellfound import CollectorError


REMOTEOK_PAYLOAD = [
    {"legal": "Remote OK"},
    {
        "id": 1,
        "position": "AI Engineer",
        "company": "Acme",
        "tags": ["ai"],
        "salary_min": 120000,
        "salary_max": 160000,
        "url": "/l/1",
        "location": "Remote",
        "epoch": 1700000000,
        "description": "Build LLM agents",
    },
    {
        "id": 2,
        "position": "Marketing Manager",
        "company": "Other",
        "tags": ["marketing"],
    },
    {
        "id": 1,
        "position": "AI Engineer duplicate",
        "company": "Acme",
        "tags": ["ai"],
    },
    "not-a-dict",
]


def _wellfound_html(payload: dict) -> str:
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script></html>'


def _wellfound_data(*, status: int | None = None, payload: dict | None = None) -> str:
    if payload is None:
        payload = {
            "props": {
                "pageProps": {
                    "statusCode": status,
                    "nested": {
                        "title": "Staff AI Engineer",
                        "slug": "staff-ai-engineer",
                        "startup": {"name": "Rocket Co"},
                        "url": "https://wellfound.com/jobs/staff-ai-engineer",
                        "salary": "$150k",
                        "location": "Remote",
                    },
                }
            }
        }
    return _wellfound_html(payload)


CONFIG = {
    "search": {"title_keywords": ["ai engineer"], "tags": ["ai"]},
    "sources": {"defi": {"base_url": "https://www.defi.jobs"}},
    "opentoworkremote_max_pages": 2,
}


def test_remoteok_collect_parses_and_dedupes():
    with patch("retrieval.sources.boards.collectors.remoteok.fetch_json", return_value=REMOTEOK_PAYLOAD):
        jobs = remoteok.collect(CONFIG)
    assert len(jobs) == 1
    job = jobs[0]
    assert job["source"] == "remoteok"
    assert job["role"] == "AI Engineer"
    assert job["salary_usd"] == "$120,000–$160,000"
    assert job["url"].startswith("https://remoteok.com")


def test_remoteok_skips_non_matching_tags():
    payload = [
        {},
        {
            "id": 9,
            "position": "DevOps Engineer",
            "company": "X",
            "tags": ["devops"],
            "url": "https://remoteok.com/l/9",
        },
    ]
    with patch("retrieval.sources.boards.collectors.remoteok.fetch_json", return_value=payload):
        jobs = remoteok.collect(CONFIG)
    assert jobs == []


def test_wellfound_collect_extracts_jobs():
    html = _wellfound_data(status=None)
    with patch("retrieval.sources.boards.collectors.wellfound.fetch_text", return_value=html):
        jobs = wellfound.collect(CONFIG)
    assert len(jobs) == 1
    assert jobs[0]["company"] == "Rocket Co"
    assert jobs[0]["currency"] == "USD"


def test_wellfound_errors_when_blocked():
    html = "<html>no next data</html>"
    with patch("retrieval.sources.boards.collectors.wellfound.fetch_text", return_value=html):
        with pytest.raises(CollectorError, match="no __NEXT_DATA__"):
            wellfound.collect(CONFIG)


def test_wellfound_errors_on_http_status():
    html = _wellfound_data(status=403)
    with patch("retrieval.sources.boards.collectors.wellfound.fetch_text", return_value=html):
        with pytest.raises(CollectorError, match="statusCode=403"):
            wellfound.collect(CONFIG)


def test_wellfound_walk_nested_lists():
    nested = {
        "props": {
            "pageProps": {
                "items": [
                    {"title": "AI Engineer", "id": "1", "url": "https://wellfound.com/jobs/1"},
                    {"nested": [{"title": "ML Engineer", "slug": "ml", "companyName": "Co"}]},
                ]
            }
        }
    }
    html = _wellfound_html(nested)
    with patch("retrieval.sources.boards.collectors.wellfound.fetch_text", return_value=html):
        jobs = wellfound.collect(CONFIG)
    assert len(jobs) >= 1


def test_f6s_raises_on_captcha():
    with patch("retrieval.sources.boards.collectors.f6s.fetch_text", return_value="Checking your browser before access"):
        with pytest.raises(f6s.CollectorError, match="CAPTCHA"):
            f6s.collect(CONFIG)


def test_f6s_returns_empty_when_clean():
    with patch("retrieval.sources.boards.collectors.f6s.fetch_text", return_value="<html>jobs</html>"):
        assert f6s.collect(CONFIG) == []


def test_defi_collect_parses_listing_and_detail():
    listing = '<a href="/jobs/senior-ai-engineer">job</a><a href="/jobs/other-role">skip</a>'
    detail = """
    <title>Senior AI Engineer - DeFi.jobs</title>
    <span class="company">Chain Labs</span>
    Pay $120,000 remote
    """
    with patch(
        "retrieval.sources.boards.collectors.defi.fetch_text",
        side_effect=[listing, detail],
    ):
        jobs = defi.collect(CONFIG)
    assert len(jobs) == 1
    assert jobs[0]["company"] == "Chain Labs"
    assert jobs[0]["salary_usd"] == "$120,000"


def test_opentoworkremote_pagination_and_salary_formats():
    pages = {
        1: {
            "jobs": [
                {"title": "AI Engineer", "url": "https://otr.example/1", "company": "A", "salaryRange": "$100k"},
                {"title": "Designer", "url": "https://otr.example/2", "company": "B"},
            ],
            "pagesInfo": {"totalpages": 2},
        },
        2: {
            "jobs": [
                {
                    "title": "Senior AI Engineer",
                    "url": "https://otr.example/3",
                    "company": "C",
                    "salaryMin": 90000,
                    "salaryMax": 120000,
                }
            ],
            "pagesInfo": {"totalpages": 2},
        },
    }

    def fake_fetch(url: str):
        page = 1 if "page=1" in url else 2
        return pages[page]

    with patch("retrieval.sources.boards.collectors.opentoworkremote.fetch_json", side_effect=fake_fetch):
        jobs = opentoworkremote.collect(CONFIG)
    assert len(jobs) == 2
    assert jobs[0]["salary_usd"] == "$100k"
    assert jobs[1]["salary_usd"] == "$90,000–$120,000"


def test_opentoworkremote_format_salary_min_only():
    assert opentoworkremote._format_salary({"salaryMin": 80000}) == "$80,000"
