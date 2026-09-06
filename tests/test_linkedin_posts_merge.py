#!/usr/bin/env python3
"""Tests for linkedin_posts_merge.py"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from linkedin_posts_merge import (  # noqa: E402
    build_feed_update_url,
    build_queries,
    fallback_linkedin_post_search_url,
    merge_payload,
    match_author_profile_ref,
    parse_linkedin_relative_posted_at,
    period_to_recency,
    post_to_job,
    resolve_feed_update_to_posts_permalink,
    sort_jobs_by_recency,
    write_linkedin_run_markdown,
)


class LinkedInPostsMergeTests(unittest.TestCase):
    def test_build_queries_six_combinations(self):
        cfg = json.loads((ROOT / "linkedin-posts-config.json").read_text())
        queries = build_queries(cfg)
        self.assertEqual(len(queries), 6)
        self.assertEqual(queries[0]["query"], '"ai engineer" + "latam"')
        self.assertIn("linkedin.com/search/results/content", queries[0]["linkedin_url"])
        self.assertIn("datePosted", queries[0]["linkedin_url"])
        self.assertIn("sortBy", queries[0]["linkedin_url"])
        self.assertIn("date_posted", queries[0]["linkedin_url"])

    def test_period_to_recency_default_seven(self):
        cfg = {"recency_map": {"1": "past-24h", "7": "past-week"}}
        self.assertEqual(period_to_recency(7, cfg), "past-week")
        cfg_full = json.loads((ROOT / "linkedin-posts-config.json").read_text())
        self.assertEqual(cfg_full.get("default_period_days"), 7)

    def test_post_to_job_hiring_post(self):
        cfg = json.loads((ROOT / "linkedin-posts-config.json").read_text())
        post = {
            "text": "We're hiring an AI Engineer remote LATAM. USD 120k-150k. Apply: jobs@acme.com",
            "url": "https://www.linkedin.com/feed/update/urn:li:activity:123/",
            "author": {"name": "Jane Recruiter"},
        }
        meta = {"query": '"ai engineer" + "latam"', "role_keyword": "ai engineer", "region": "latam"}
        job = post_to_job(post, meta, cfg, {})
        self.assertIsNotNone(job)
        self.assertEqual(job["source"], "linkedin_posts")
        self.assertEqual(job["filter_result"], "eligible")
        self.assertEqual(job["apply_channel"], "email")
        self.assertEqual(job["location_note"], "LATAM")

    def test_merge_payload_writes_run(self):
        payload = {
            "period_days": 1,
            "queries": [
                {
                    "query": "agent engineer worldwide",
                    "role_keyword": "agent engineer",
                    "region": "worldwide",
                    "posts": [
                        {
                            "text": "Hiring Agent Engineer worldwide remote. $100k USD.",
                            "url": "https://www.linkedin.com/feed/update/urn:li:activity:998877/",
                            "author": "Tech Co",
                        }
                    ],
                }
            ],
        }
        result = merge_payload(payload, period_days=1, since_arg="30d")
        self.assertGreaterEqual(result["new_total"], 0)
        self.assertTrue(Path(result["run_path"]).exists())

    def test_parse_relative_posted_at(self):
        text = "Thalia Balbinot\n\n2d • \n\nFollow\n\nAI Engineer"
        dt = parse_linkedin_relative_posted_at(text)
        self.assertIsNotNone(dt)

    def test_write_linkedin_run_sorted_by_recency(self):
        from datetime import datetime, timezone

        jobs = [
            {
                "role": "Old",
                "company": "A",
                "posted_at": "2026-08-20",
                "discovery_index": 5,
                "filter_result": "needs_review",
                "location_note": "LATAM",
                "url": "https://example.com/a",
                "source": "linkedin_posts",
            },
            {
                "role": "New",
                "company": "B",
                "posted_label": "2h",
                "posted_at": datetime.now(timezone.utc).isoformat(),
                "discovery_index": 0,
                "filter_result": "needs_review",
                "location_note": "LATAM",
                "url": "https://example.com/b",
                "source": "linkedin_posts",
            },
        ]
        ranked = sort_jobs_by_recency(jobs)
        self.assertEqual(ranked[0]["role"], "New")

    def test_write_linkedin_run_markdown_recency(self):
        from datetime import datetime, timezone

        cfg = json.loads((ROOT / "linkedin-posts-config.json").read_text())
        jobs = [
            {
                "role": "Old",
                "company": "A",
                "discovery_index": 10,
                "filter_result": "needs_review",
                "location_note": "LATAM",
                "url": "https://example.com/a",
                "source": "linkedin_posts",
            },
            {
                "role": "New",
                "company": "B",
                "posted_label": "1h",
                "discovery_index": 0,
                "filter_result": "needs_review",
                "location_note": "LATAM",
                "url": "https://example.com/b",
                "source": "linkedin_posts",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.md"
            write_linkedin_run_markdown(
                path,
                datetime.now(timezone.utc),
                jobs,
                jobs[:1],
                7,
                "past-week",
                6,
                cfg,
            )
            text = path.read_text()
            self.assertIn("latest → oldest", text)
            self.assertLess(text.index("New"), text.index("Old"))


    def test_resolve_feed_update_to_posts_permalink(self):
        url = resolve_feed_update_to_posts_permalink(
            "https://www.linkedin.com/feed/update/urn:li:activity:7500249103348490240/"
        )
        self.assertIn("/posts/", url)
        self.assertIn("kenia-denisse-salinas", url)
        self.assertIn("7500249103348490240", url)

    def test_build_feed_update_url(self):
        url = build_feed_update_url("activity", "12345")
        self.assertEqual(url, "https://www.linkedin.com/feed/update/urn:li:activity:12345/")

    def test_match_author_profile_ref_by_slug(self):
        refs = [
            {
                "kind": "person",
                "url": "https://www.linkedin.com/in/kethan-reddy-06b3a4183/",
                "text": "kethan-reddy-06b3a4183",
            }
        ]
        url, source = match_author_profile_ref("Kethan Reddy", refs)
        self.assertIn("/in/kethan-reddy", url)
        self.assertIn("recent-activity", url)
        self.assertEqual(source, "person_slug")

    def test_fallback_linkedin_post_search_url(self):
        url = fallback_linkedin_post_search_url("Agustin Bellini", "ai engineer")
        self.assertIn("linkedin.com/search/results/content", url)
        self.assertIn("Agustin", url)


if __name__ == "__main__":
    unittest.main(verbosity=2)
