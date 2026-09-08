#!/usr/bin/env python3
"""Extended tests for linkedin_jobs merge, pagination, multi-track queries, audit."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from linkedin_jobs_merge import (  # noqa: E402
    JOBS_PER_PAGE,
    audit_collect_results,
    build_all_track_queries,
    build_queries,
    existing_job_view_ids,
    extract_job_view_id,
    extract_posted_label,
    linkedin_jobs_search_url,
    listing_to_job,
    merge_listings_by_id,
    merge_payload,
    normalize_job_view_url,
    normalize_listing_title,
    parse_listings_from_html,
    parse_listings_from_text,
    period_to_time_posted,
    posted_within_hours,
    region_search_variants,
    with_search_start,
)
from tests.helpers.example_configs import load_example_linkedin_jobs_config  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "linkedin_jobs_search_page.html"
FIXTURE_PAGE2 = ROOT / "tests" / "fixtures" / "linkedin_jobs_search_page2.html"
INNER_TEXT = ROOT / "tests" / "fixtures" / "linkedin_jobs_inner_text.txt"


class LinkedInJobsMergeTests(unittest.TestCase):
    def test_build_queries_role_only_keywords(self):
        cfg = load_example_linkedin_jobs_config()
        queries = build_queries(cfg, track_id="ai-engineer")
        self.assertGreaterEqual(len(queries), 15)
        self.assertEqual(queries[0]["query"], "ai engineer")
        self.assertEqual(queries[0]["track"], "ai-engineer")
        self.assertNotIn("+", queries[0]["query"])
        self.assertIn("keywords=ai+engineer", queries[0]["linkedin_url"])

    def test_search_url_includes_24h_and_salary(self):
        cfg = load_example_linkedin_jobs_config()
        url = linkedin_jobs_search_url("ai engineer", region="worldwide", period_days=1, cfg=cfg)
        self.assertIn("f_TPR=r86400", url)
        self.assertIn("f_SAL=f_SA_id_225001", url)
        self.assertNotIn("f_WT=2", url)

    def test_search_url_latam_uses_brazil_location(self):
        cfg = load_example_linkedin_jobs_config()
        url = linkedin_jobs_search_url(
            "ai engineer",
            region="latam",
            period_days=1,
            cfg=cfg,
            location="Brazil",
        )
        self.assertIn("location=Brazil", url.replace("+", " "))

    def test_region_search_variants_latam(self):
        cfg = load_example_linkedin_jobs_config()
        variants = region_search_variants("latam", cfg)
        self.assertGreaterEqual(len(variants), 4)
        self.assertEqual(variants[0]["location"], "Brazil")

    def test_build_all_track_queries_includes_both_tracks(self):
        import json

        def example_cfg(track_id: str) -> dict:
            path = ROOT / "examples" / "tracks" / track_id / "linkedin-jobs-config.json"
            return json.loads(path.read_text(encoding="utf-8"))

        with patch("track_store.list_track_ids", return_value=["ai-engineer", "android-developer"]):
            with patch("track_store.load_linkedin_jobs_config", side_effect=example_cfg):
                queries = build_all_track_queries()
        tracks = {q["track"] for q in queries}
        self.assertIn("ai-engineer", tracks)
        self.assertIn("android-developer", tracks)
        self.assertGreaterEqual(len(queries), 20)

    def test_extract_posted_label_reposted(self):
        self.assertEqual(extract_posted_label("Reposted 3 hours ago · Brazil"), "3h")
        self.assertEqual(extract_posted_label("19 hours ago"), "19h")

    def test_posted_within_hours(self):
        job = {"posted_label": "5h"}
        self.assertTrue(posted_within_hours(job, 24))
        job2 = {"posted_label": "3d"}
        self.assertFalse(posted_within_hours(job2, 24))

    def test_with_search_start_pagination(self):
        cfg = load_example_linkedin_jobs_config()
        base = linkedin_jobs_search_url("ai engineer", region="worldwide", period_days=1, cfg=cfg)
        page2 = with_search_start(base, JOBS_PER_PAGE)
        self.assertIn("start=25", page2)

    def test_parse_fixture_html(self):
        html = FIXTURE.read_text(encoding="utf-8")
        listings = parse_listings_from_html(html)
        self.assertEqual(len(listings), 2)
        self.assertEqual(listings[0]["title"], "Senior AI Engineer")

    def test_parse_multi_page_fixtures_dedupes(self):
        page1 = parse_listings_from_html(FIXTURE.read_text(encoding="utf-8"))
        page2 = parse_listings_from_html(FIXTURE_PAGE2.read_text(encoding="utf-8"))
        merged = merge_listings_by_id(page1, page2)
        self.assertEqual(len(merged), 4)

    def test_parse_inner_text_fixture_titles(self):
        raw = INNER_TEXT.read_text(encoding="utf-8")
        listings = parse_listings_from_text(raw)
        self.assertGreaterEqual(len(listings), 2)
        titles = [x["title"] for x in listings if x["title"]]
        self.assertIn("Senior AI Engineer", titles)

    def test_normalize_listing_title_rejects_job_id_placeholder(self):
        self.assertEqual(normalize_listing_title("Job 4406863861", "ai engineer"), "Ai Engineer")
        self.assertEqual(
            normalize_listing_title(
                "Staff Software Engineer, Product Staff Software Engineer, Product with verification",
                "",
            ),
            "Staff Software Engineer, Product",
        )

    def test_listing_to_job_parses_posted_from_location(self):
        cfg = load_example_linkedin_jobs_config()
        listing = {
            "job_id": "4464387581",
            "url": normalize_job_view_url("4464387581"),
            "title": "AI Engineer",
            "company": "TCS",
            "location": "Brazil · 19 hours ago · Over 100 applicants",
            "posted_label": "",
            "easy_apply": True,
            "apply_method": "easy_apply",
        }
        meta = {"query": "ai engineer", "role_keyword": "ai engineer", "region": "worldwide"}
        job = listing_to_job(listing, meta, cfg, {"filters": {}})
        self.assertIsNotNone(job)
        self.assertEqual(job["posted_label"], "19h")
        self.assertTrue(posted_within_hours(job, 24))

    @patch("linkedin_jobs_merge.save_registry")
    @patch("linkedin_jobs_merge.load_registry")
    @patch("linkedin_jobs_merge.load_linkedin_jobs_config")
    def test_merge_payload_skips_cross_dedup(self, mock_cfg, mock_load, mock_save):
        mock_cfg.return_value = load_example_linkedin_jobs_config()
        mock_load.return_value = {
            "jobs": [{"url": "https://www.linkedin.com/jobs/view/4100012345/", "source": "linkedin_posts"}]
        }
        listings = parse_listings_from_html(FIXTURE.read_text(encoding="utf-8"))
        payload = {
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
        }
        result = merge_payload(payload, 1, "1d")
        self.assertEqual(result["skipped_cross_dedup"], 1)
        self.assertEqual(result["new_total"], 1)

    def test_period_to_time_posted_24h(self):
        cfg = load_example_linkedin_jobs_config()
        self.assertEqual(period_to_time_posted(1, cfg), "r86400")

    def test_extract_job_view_id(self):
        self.assertEqual(extract_job_view_id("https://www.linkedin.com/jobs/view/12345/"), "12345")

    def test_existing_job_view_ids_from_registry(self):
        registry = {
            "jobs": [
                {"url": "https://www.linkedin.com/jobs/view/999/"},
                {"apply_url": "https://www.linkedin.com/jobs/view/888/?ref=abc"},
            ]
        }
        self.assertEqual(existing_job_view_ids(registry), {"999", "888"})


    def test_audit_collect_results_flags_issues(self):
        audit = audit_collect_results(
            [
                {
                    "track": "ai-engineer",
                    "region": "worldwide",
                    "role_keyword": "ai engineer",
                    "listings": [{"job_id": "1", "title": "Job 1", "company": "—"}],
                    "page_stats": {"pages": 1},
                }
            ]
        )
        self.assertFalse(audit["ok"])
        self.assertTrue(audit["issues"])

    def test_merge_listings_by_id(self):
        merged = merge_listings_by_id(
            [{"job_id": "1", "title": "", "company": "—"}],
            [{"job_id": "1", "title": "AI Engineer", "company": "TCS"}],
        )
        self.assertEqual(merged[0]["title"], "AI Engineer")

    def test_search_url_geo_id_without_location(self):
        cfg = load_example_linkedin_jobs_config()
        url = linkedin_jobs_search_url(
            "ai engineer",
            region="latam",
            period_days=1,
            cfg=cfg,
            location="",
            geo_id="106057199",
        )
        self.assertIn("geoId=106057199", url)
        self.assertNotIn("location=", url)


if __name__ == "__main__":
    unittest.main()
