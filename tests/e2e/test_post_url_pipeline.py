"""E2E-style tests for LinkedIn post URL resolution pipeline (no live browser).

Covers: HTML card extraction → author map → chunk URLs → parse → merge → table display.
Regression targets for Sep 14 failures (placeholder → search fallback).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures" / "linkedin"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from audit_log import read_log, reset_audit_log  # noqa: E402
from generate_applications import post_url_for  # noqa: E402
from linkedin_content_collect import collect_feed_text, posts_to_jobs  # noqa: E402
from linkedin_posts_merge import (  # noqa: E402
    is_feed_update_url,
    is_placeholder_post_url,
    merge_payload,
    normalize_payload,
    parse_feed_search_posts,
    post_to_job,
)
from registry import REGISTRY_PATH, job_key, load_registry, save_registry  # noqa: E402
from tests.helpers.example_configs import load_example_linkedin_config  # noqa: E402

MONIKA_URN = "7503481913303584769"
MELISSA_URN = MONIKA_URN  # shared fixture activity id
KIMBERLY_URN = "7503200610150973442"
MONIKA_FEED = f"https://www.linkedin.com/feed/update/urn:li:activity:{MONIKA_URN}/"
KIMBERLY_FEED = f"https://www.linkedin.com/feed/update/urn:li:activity:{KIMBERLY_URN}/"

MONIKA_INNER = (
    "Feed post\n\n"
    "Monika Kuqi\n\n"
    "1h • \n\nFollow\n\n"
    "We're hiring an AI Engineer remote LATAM. USD 120k-150k.\n"
)
TWO_POST_INNER = (
    "Feed post\n\n"
    "Monika Kuqi\n\n1h • \n\nFollow\n\nHiring AI Engineer LATAM USD 120k\n\n"
    "Feed post\n\n"
    "Kimberly Membrillo\n\n2h • \n\nFollow\n\nHiring AI Engineer remote\n"
)


def _mock_playwright_page(*, scrolls: list[dict[str, str]]) -> MagicMock:
    """Build a mock page that replays innerText/html per scroll."""
    page = MagicMock()
    page.viewport_size = {"width": 1280, "height": 900}
    page.mouse.move = AsyncMock()
    page.mouse.wheel = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.on = MagicMock()

    state = {"i": 0}

    async def inner_text(*_args, **_kwargs):
        idx = min(state["i"], len(scrolls) - 1)
        return scrolls[idx]["inner"]

    async def content(*_args, **_kwargs):
        idx = min(state["i"], len(scrolls) - 1)
        return scrolls[idx]["html"]

    async def wheel(*_args, **_kwargs):
        state["i"] += 1

    main = MagicMock()
    main.inner_text = inner_text
    page.locator.return_value = main
    page.content = content
    page.mouse.wheel = wheel
    return page


def _mock_playwright_context(page: MagicMock) -> MagicMock:
    context = MagicMock()
    context.pages = [page]
    context.add_cookies = AsyncMock()
    context.close = AsyncMock()
    return context


@pytest.fixture
def linkedin_cfg():
    return load_example_linkedin_config()


@pytest.fixture
def job_cfg():
    path = ROOT / "config.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


@pytest.mark.asyncio
async def test_e2e_collect_pairs_monika_urn_on_first_scroll(monkeypatch):
    """Scroll 1: new post visible in DOM → chunk_post_urls gets feed/update (not placeholder)."""
    html = FIXTURES.joinpath("content_search_monika_card.html").read_text(encoding="utf-8")
    page = _mock_playwright_page(scrolls=[{"inner": MONIKA_INNER, "html": html}] * 8)
    context = _mock_playwright_context(page)
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)

    pw = MagicMock()
    pw.chromium.launch = AsyncMock(return_value=browser)
    pw.__aenter__ = AsyncMock(return_value=pw)
    pw.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr("linkedin_content_collect.load_cookies", lambda: [])
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    with patch("patchright.async_api.async_playwright", return_value=pw):
        raw, refs, stats = await collect_feed_text(
            "https://www.linkedin.com/search/results/content/?keywords=test",
            max_scrolls=3,
            max_stale=2,
            pause=0,
        )

    posts = parse_feed_search_posts(
        {
            "sections": {"search_results": raw},
            "references": {"search_results": refs},
            "author_post_urls": stats.get("author_url_map") or {},
            "chunk_post_urls": stats.get("chunk_post_urls") or [],
        }
    )
    assert len(posts) == 1
    assert MONIKA_URN in posts[0]["url"]
    assert stats["chunk_urls_resolved"] >= 1
    assert stats["author_post_urls"] >= 1


@pytest.mark.asyncio
async def test_e2e_collect_resolves_two_posts_by_author(monkeypatch):
    """Two posts in one scroll — each gets its own feed/update URL (index-aligned)."""
    html = FIXTURES.joinpath("content_search_two_posts.html").read_text(encoding="utf-8")
    page = _mock_playwright_page(scrolls=[{"inner": TWO_POST_INNER, "html": html}] * 8)
    context = _mock_playwright_context(page)
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    pw = MagicMock()
    pw.chromium.launch = AsyncMock(return_value=browser)
    pw.__aenter__ = AsyncMock(return_value=pw)
    pw.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr("linkedin_content_collect.load_cookies", lambda: [])
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    with patch("patchright.async_api.async_playwright", return_value=pw):
        raw, refs, stats = await collect_feed_text(
            "https://www.linkedin.com/search/results/content/?keywords=test",
            max_scrolls=2,
            max_stale=1,
            pause=0,
        )

    posts = parse_feed_search_posts(
        {
            "sections": {"search_results": raw},
            "references": {"search_results": refs},
            "chunk_post_urls": stats.get("chunk_post_urls") or [],
            "author_post_urls": stats.get("author_url_map") or {},
        }
    )
    assert len(posts) == 2
    by_author = {p.get("author"): p.get("url") for p in posts}
    assert MONIKA_URN in by_author["Monika Kuqi"]
    assert KIMBERLY_URN in by_author["Kimberly Membrillo"]


@pytest.mark.asyncio
async def test_e2e_collect_pairs_melissa_via_article_card(monkeypatch):
    """Article-card author match (Copy link menu card) → chunk URL for Melissa Oliveira."""
    html = FIXTURES.joinpath("content_search_melissa_card.html").read_text(encoding="utf-8")
    inner = (
        "Feed post\n\n"
        "Melissa Oliveira\n\n"
        "5d • \n\nFollow\n\n"
        "Full-Stack & AI Engineer USD $5.6k-7.5k / month\n"
    )
    page = _mock_playwright_page(scrolls=[{"inner": inner, "html": html}] * 6)
    context = _mock_playwright_context(page)
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    pw = MagicMock()
    pw.chromium.launch = AsyncMock(return_value=browser)
    pw.__aenter__ = AsyncMock(return_value=pw)
    pw.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr("linkedin_content_collect.load_cookies", lambda: [])
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    monkeypatch.setattr(
        "linkedin_content_collect.backfill_missing_chunk_urls_via_copy_link",
        AsyncMock(return_value=0),
    )
    with patch("patchright.async_api.async_playwright", return_value=pw):
        raw, refs, stats = await collect_feed_text(
            "https://www.linkedin.com/search/results/content/?keywords=%22Melissa%20Oliveira%22%20%22Ai%20Engineer%22",
            max_scrolls=2,
            max_stale=1,
            pause=0,
        )

    posts = parse_feed_search_posts(
        {
            "sections": {"search_results": raw},
            "references": {"search_results": refs},
            "chunk_post_urls": stats.get("chunk_post_urls") or [],
        }
    )
    assert len(posts) == 1
    assert MELISSA_URN in posts[0]["url"]
    assert stats["chunk_urls_resolved"] >= 1


def test_e2e_network_harvest_populates_author_map_for_parse():
    """Voyager JSON → author map → parse assigns feed/update when HTML cards are sparse."""
    from linkedin_posts_merge import harvest_feed_posts_from_network_body, register_author_post_urls

    network = FIXTURES.joinpath("content_search_network_monika.json").read_text(encoding="utf-8")
    html_posts = harvest_feed_posts_from_network_body(network)
    author_map: dict[str, str] = {}
    register_author_post_urls(author_map, html_posts)
    posts = parse_feed_search_posts(
        {
            "sections": {"search_results": MONIKA_INNER},
            "references": {"search_results": []},
            "author_post_urls": author_map,
            "chunk_post_urls": [""],
        }
    )
    assert len(posts) == 1
    assert MONIKA_URN in posts[0]["url"]
    assert posts[0]["url_source"] == "author_map"


def test_e2e_parse_to_job_to_table_has_real_post_url(linkedin_cfg, job_cfg):
    """Full pipeline slice: parse → post_to_job → post_url_for shows feed/update (not search)."""
    payload = {
        "sections": {"search_results": MONIKA_INNER},
        "references": {"search_results": []},
        "chunk_post_urls": [MONIKA_FEED],
        "author_post_urls": {"monika kuqi": MONIKA_FEED},
    }
    posts = parse_feed_search_posts(payload)
    job = post_to_job(
        posts[0],
        {"query": '"ai engineer" + "latam"', "role_keyword": "ai engineer", "region": "latam"},
        linkedin_cfg,
        job_cfg,
    )
    assert job is not None
    assert is_feed_update_url(job["url"])
    assert not is_placeholder_post_url(job["url"])
    assert "search/results/content" not in post_url_for(job)


def test_e2e_merge_payload_writes_real_urls(tmp_path, linkedin_cfg, monkeypatch):
    """merge_payload persists feed/update URLs — merge audit log accepts datetime."""
    registry_path = tmp_path / "registry" / "jobs.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(json.dumps({"jobs": []}, indent=2) + "\n", encoding="utf-8")
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("JOBSEARCH_AUDIT_LOG_DIR", str(log_dir))
    reset_audit_log()
    monkeypatch.setattr("linkedin_posts_merge.REGISTRY_PATH", registry_path)
    monkeypatch.setattr("registry.REGISTRY_PATH", registry_path)
    monkeypatch.setattr("linkedin_posts_merge.RUNS_DIR", runs_dir)
    monkeypatch.setattr("linkedin_posts_merge.load_linkedin_config", lambda *a, **k: linkedin_cfg)

    feed_payload = {
        "sections": {"search_results": MONIKA_INNER},
        "references": {"search_results": []},
        "chunk_post_urls": [MONIKA_FEED],
        "author_post_urls": {"monika kuqi": MONIKA_FEED},
    }
    payload = {
        "period_days": 7,
        "queries": [
            {
                "query": '"ai engineer" + "latam"',
                "role_keyword": "ai engineer",
                "region": "latam",
                "feed_payload": feed_payload,
            }
        ],
    }
    result = merge_payload(payload, period_days=7, since_arg="30d")
    assert result["new_total"] >= 1

    reg = load_registry()
    li_posts = [j for j in reg["jobs"] if j.get("source") == "linkedin_posts"]
    assert li_posts
    assert any(MONIKA_URN in (j.get("url") or "") for j in li_posts)
    assert not any(is_placeholder_post_url(j.get("url", "")) for j in li_posts)

    audit = read_log()
    merge_events = [r for r in audit if r.get("component") == "linkedin_posts_merge"]
    assert merge_events
    assert merge_events[-1]["event"] == "merge_complete"
    assert "since" in merge_events[-1]["data"]


def test_e2e_placeholder_still_falls_back_to_search_url(linkedin_cfg, job_cfg):
    """Regression: registry keeps placeholder; UI display still gets content-search URL."""
    posts = parse_feed_search_posts(
        {
            "sections": {"search_results": MONIKA_INNER},
            "references": {"search_results": []},
            "chunk_post_urls": [""],
            "author_post_urls": {},
        }
    )
    job = post_to_job(
        posts[0],
        {"query": '"ai engineer" + "latam"', "role_keyword": "ai engineer", "region": "latam"},
        linkedin_cfg,
        job_cfg,
    )
    assert job is not None
    assert is_placeholder_post_url(job["url"])
    display = post_url_for(job)
    assert "search/results/content" in display
    assert MONIKA_URN not in display


def test_e2e_merge_unresolved_post_url_stays_placeholder_in_registry(tmp_path, linkedin_cfg, monkeypatch):
    """FE-11: merge must not persist content-search URLs when URN resolution fails."""
    from linkedin_posts_merge import normalize_linkedin_job_urls

    registry_path = tmp_path / "registry" / "jobs.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(json.dumps({"jobs": []}, indent=2) + "\n", encoding="utf-8")
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    monkeypatch.setattr("linkedin_posts_merge.REGISTRY_PATH", registry_path)
    monkeypatch.setattr("registry.REGISTRY_PATH", registry_path)
    monkeypatch.setattr("linkedin_posts_merge.RUNS_DIR", runs_dir)
    monkeypatch.setattr("linkedin_posts_merge.load_linkedin_config", lambda *a, **k: linkedin_cfg)

    payload = {
        "period_days": 7,
        "queries": [
            {
                "query": '"ai engineer" + "latam"',
                "role_keyword": "ai engineer",
                "region": "latam",
                "feed_payload": {
                    "sections": {"search_results": MONIKA_INNER},
                    "references": {"search_results": []},
                    "chunk_post_urls": [""],
                    "author_post_urls": {},
                },
            }
        ],
    }
    result = merge_payload(payload, period_days=7, since_arg="30d")
    assert result["new_total"] >= 1

    reg = load_registry()
    li_posts = [j for j in reg["jobs"] if j.get("source") == "linkedin_posts"]
    assert li_posts
    for job in li_posts:
        assert is_placeholder_post_url(job["url"]), job["url"]
        assert "search/results/content" not in job["url"]
        assert post_url_for(job)  # display link still clickable
        assert "search/results/content" in post_url_for(job) or MONIKA_URN in post_url_for(job)

    # normalize must never re-introduce search URLs
    job = li_posts[0]
    normalize_linkedin_job_urls(job, refs=[])
    assert is_placeholder_post_url(job["url"])


def test_e2e_normalize_payload_accepts_browser_collect_shape(linkedin_cfg, job_cfg):
    """Browser collect JSON (sections + references + maps) normalizes without extra wrapping."""
    collect_export = {
        "query": '"ai engineer" + "latam"',
        "role_keyword": "ai engineer",
        "region": "latam",
        "sections": {"search_results": TWO_POST_INNER},
        "references": {
            "search_results": [
                {"kind": "feed_post", "url": MONIKA_FEED, "text": "Monika Kuqi"},
                {"kind": "feed_post", "url": KIMBERLY_FEED, "text": "Kimberly Membrillo"},
            ]
        },
        "chunk_post_urls": [MONIKA_FEED, KIMBERLY_FEED],
    }
    items = normalize_payload(collect_export)
    assert len(items) == 2
    jobs = []
    for item in items:
        job = post_to_job(item["post"], item["query_meta"], linkedin_cfg, job_cfg)
        if job:
            jobs.append(job)
    assert len(jobs) == 2
    assert all(is_feed_update_url(post_url_for(j)) for j in jobs)
    assert all("search/results/content" not in post_url_for(j) for j in jobs)


def test_e2e_posts_to_jobs_from_collect_payload(linkedin_cfg, job_cfg):
    """posts_to_jobs on parsed posts respects chunk_post_urls (collect export shape)."""
    posts = parse_feed_search_posts(
        {
            "sections": {"search_results": MONIKA_INNER},
            "references": {"search_results": []},
            "chunk_post_urls": [MONIKA_FEED],
        }
    )
    meta = {"query": '"ai engineer" + "latam"', "role_keyword": "ai engineer", "region": "latam"}
    jobs = posts_to_jobs(posts, meta, max_roles=10)
    assert len(jobs) == 1
    assert MONIKA_URN in jobs[0]["url"]
    assert job_key(jobs[0])
