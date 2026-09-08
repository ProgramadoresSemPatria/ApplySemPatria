"""LinkedIn Jobs browser e2e — LJ-01..06 (fixtures + Patchright, no live LinkedIn)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from patchright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

pytestmark = pytest.mark.browser


async def _dom_listings(html_uri: str) -> list[dict]:
    from linkedin_jobs_collect import extract_listings_from_dom

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(html_uri, wait_until="domcontentloaded")
        listings = await extract_listings_from_dom(page)
        await browser.close()
    return listings


async def _backfill_listing(html_uri: str, job_id: str) -> dict | None:
    from linkedin_jobs_collect import listing_from_job_view

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        listing = await listing_from_job_view(page, job_id, url=html_uri)
        await browser.close()
    return listing


def test_lj01_dom_extract_titles_and_posted(linkedin_jobs_html_dir: Path):
    uri = (linkedin_jobs_html_dir / "search_page.html").resolve().as_uri()
    listings = asyncio.run(_dom_listings(uri))
    by_id = {item["job_id"]: item for item in listings}
    assert by_id["4464387581"]["title"] == "AI Engineer"
    assert by_id["4464387581"]["company"] == "Tata Consultancy Services"
    assert by_id["4464387581"]["posted_label"] == "19h"
    assert by_id["4298246321"]["title"] == "Senior Forward Deployed Engineer"
    assert by_id["4298246321"]["posted_label"] == "4h"
    assert by_id["4464387581"]["easy_apply"] is True


def test_lj02_search_url_matches_browser_filters():
    from linkedin_jobs_merge import linkedin_jobs_search_url
    from tests.helpers.example_configs import load_example_linkedin_jobs_config

    cfg = load_example_linkedin_jobs_config()
    url = linkedin_jobs_search_url("ai engineer", region="worldwide", period_days=1, cfg=cfg)
    assert "f_TPR=r86400" in url
    assert "f_SAL=f_SA_id_225001" in url
    assert "f_WT=2" not in url


def test_lj03_latam_queries_use_country_locations():
    from linkedin_jobs_merge import build_queries
    from tests.helpers.example_configs import load_example_linkedin_jobs_config

    cfg = load_example_linkedin_jobs_config()
    queries = build_queries(cfg, track_id="ai-engineer")
    brazil = [q for q in queries if q.get("search_location") == "Brazil"]
    assert brazil
    assert "location=Brazil" in brazil[0]["linkedin_url"].replace("+", " ")


def test_lj04_backfill_job_view_fixture(linkedin_jobs_html_dir: Path):
    uri = (linkedin_jobs_html_dir / "job_view_tcs.html").resolve().as_uri()
    listing = asyncio.run(_backfill_listing(uri, "4464387581"))
    assert listing is not None
    assert listing["title"] == "AI Engineer"
    assert listing["posted_label"] == "19h"
    assert listing.get("backfill") is True


def test_lj05_merge_pipeline_produces_posted_at(tmp_path: Path):
    from linkedin_jobs_merge import listing_to_job, merge_payload, parse_listings_from_html
    from tests.helpers.example_configs import load_example_linkedin_jobs_config

    html = (ROOT / "tests" / "fixtures" / "linkedin_jobs" / "search_page.html").read_text(encoding="utf-8")
    listings = parse_listings_from_html(html)
    cfg = load_example_linkedin_jobs_config()
    reg_path = tmp_path / "jobs.json"
    reg_path.write_text(json.dumps({"jobs": []}), encoding="utf-8")

    with patch("linkedin_jobs_merge.REGISTRY_PATH", reg_path):
        with patch("linkedin_jobs_merge.load_registry", side_effect=lambda: json.loads(reg_path.read_text())):
            with patch("linkedin_jobs_merge.save_registry", side_effect=lambda data: reg_path.write_text(json.dumps(data, indent=2))):
                with patch("linkedin_jobs_merge.load_linkedin_jobs_config", return_value=cfg):
                    result = merge_payload(
                        {
                            "period_days": 1,
                            "queries": [
                                {
                                    "query": "ai engineer",
                                    "role_keyword": "ai engineer",
                                    "region": "worldwide",
                                    "track": "ai-engineer",
                                    "listings": listings,
                                }
                            ],
                        },
                        1,
                        "1d",
                    )
    assert result["new_total"] >= 2
    saved = json.loads(reg_path.read_text())
    jobs = [j for j in saved["jobs"] if j.get("source") == "linkedin_jobs"]
    tcs = next(j for j in jobs if "4464387581" in j.get("url", ""))
    assert tcs["role"] == "AI Engineer"
    assert tcs.get("posted_label") == "19h"
    assert tcs.get("posted_at")

    meta = {"query": "ai engineer", "role_keyword": "ai engineer", "region": "worldwide"}
    job = listing_to_job(listings[0], meta, cfg, {"filters": {}})
    assert job is not None
    assert job["posted_label"] == "19h"


def test_lj06_audit_flags_clean_after_fixture_collect():
    from linkedin_jobs_merge import audit_collect_results

    audit = audit_collect_results(
        [
            {
                "track": "ai-engineer",
                "region": "worldwide",
                "role_keyword": "ai engineer",
                "listings": [
                    {"job_id": "4464387581", "title": "AI Engineer", "company": "TCS", "posted_label": "19h"},
                ],
                "page_stats": {"pages": 2},
            }
        ]
    )
    assert audit["ok"] is True
    assert audit["placeholder_titles"] == 0
