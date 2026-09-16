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
FIXTURES = ROOT / "tests" / "fixtures" / "linkedin"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from linkedin_posts_merge import (  # noqa: E402
    build_feed_update_url,
    build_queries,
    extract_feed_posts_from_html,
    extract_ordered_feed_update_urls,
    fallback_linkedin_post_search_url,
    harvest_feed_posts_from_network_body,
    is_feed_update_url,
    is_profile_fallback_url,
    merge_payload,
    match_author_activity_ref,
    match_author_profile_ref,
    parse_feed_search_posts,
    parse_linkedin_relative_posted_at,
    period_to_recency,
    post_to_job,
    register_author_post_urls,
    resolve_author_post_url,
    resolve_chunk_authors,
    resolve_feed_update_to_posts_permalink,
    resolve_post_urls,
    sort_jobs_by_recency,
    write_linkedin_run_markdown,
)


from tests.helpers.example_configs import load_example_linkedin_config  # noqa: E402


class LinkedInPostsMergeTests(unittest.TestCase):
    def test_build_queries_six_combinations(self):
        cfg = load_example_linkedin_config()
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
        cfg_full = load_example_linkedin_config()
        self.assertEqual(cfg_full.get("default_period_days"), 7)

    def test_post_to_job_hiring_post(self):
        cfg = load_example_linkedin_config()
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
        self.assertEqual(job.get("post_intent"), "hiring")

    def test_post_to_job_rejects_job_seeker(self):
        cfg = load_example_linkedin_config()
        post = {
            "text": "Open to remote AI Engineer roles. #OpenToWork looking for opportunities myself.",
            "url": "https://www.linkedin.com/feed/update/urn:li:activity:456/",
            "author": {"name": "Sameer Ray"},
        }
        meta = {"query": '"ai engineer" + "latam"', "role_keyword": "ai engineer", "region": "latam"}
        job = post_to_job(post, meta, cfg, {})
        self.assertIsNone(job)

    def test_post_to_job_hiring_no_salary_needs_review(self):
        cfg = load_example_linkedin_config()
        post = {
            "text": "We're hiring an AI Engineer — remote LATAM friendly. DM me to apply.",
            "url": "https://www.linkedin.com/feed/update/urn:li:activity:789/",
            "author": {"name": "Recruiter"},
        }
        meta = {"query": '"ai engineer" + "latam"', "role_keyword": "ai engineer", "region": "latam"}
        job = post_to_job(post, meta, cfg, {})
        self.assertIsNotNone(job)
        self.assertEqual(job["filter_result"], "needs_review")
        self.assertEqual(job.get("post_intent"), "hiring")

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

        cfg = load_example_linkedin_config()
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

    def test_resolve_post_urls_prefers_feed_update_over_recent_activity(self):
        refs = [
            {
                "kind": "feed_post",
                "url": "https://www.linkedin.com/feed/update/urn:li:activity:7503481913303584769/",
                "author_slug": "manuela-g",
                "activity_id": "7503481913303584769",
                "urn_kind": "activity",
            },
            {
                "kind": "person",
                "url": "https://www.linkedin.com/in/manuela-g%C3%A9nova/",
                "text": "Manuela Sánchez González",
            },
        ]
        chunk = (
            "Manuela Sánchez González\n\n"
            "1d • \n\nFollow\n\n"
            "We're hiring an AI Engineer remote LATAM. USD 120k."
        )
        post_url, _apply, source, _feed_idx, _job_idx = resolve_post_urls(
            chunk,
            "Manuela Sánchez González",
            refs,
            feed_post_urls=[],
            feed_post_by_title={},
            feed_idx=0,
            job_urls=[],
            job_idx=0,
        )
        self.assertTrue(is_feed_update_url(post_url), post_url)
        self.assertNotIn("recent-activity", post_url)
        self.assertIn("7503481913303584769", post_url)
        self.assertIn(source, {"feed_post_slug", "activity_ref_slug", "activity_ref_urn"})

    def test_resolve_post_urls_never_uses_profile_activity_page(self):
        refs = [
            {
                "kind": "person",
                "url": "https://www.linkedin.com/in/kimberlymembrillo/",
                "text": "Kimberly Membrillo",
            }
        ]
        chunk = "Kimberly Membrillo\n\n2d • \n\nFollow\n\nHiring AI Engineer LATAM."
        post_url, _apply, source, _feed_idx, _job_idx = resolve_post_urls(
            chunk,
            "Kimberly Membrillo",
            refs,
            feed_post_urls=[],
            feed_post_by_title={},
            feed_idx=0,
            job_urls=[],
            job_idx=0,
        )
        self.assertEqual(post_url, "")
        self.assertEqual(source, "none")

    def test_parse_feed_search_posts_assigns_feed_update_urls(self):
        raw = (
            "Feed post\n\n"
            "Manuela Sánchez González\n\n1d • \n\nFollow\n\nHiring AI Engineer LATAM USD 120k\n\n"
            "Feed post\n\n"
            "Kimberly Membrillo\n\n2d • \n\nFollow\n\nHiring AI Engineer remote\n"
        )
        refs = [
            {
                "kind": "feed_post",
                "url": "https://www.linkedin.com/feed/update/urn:li:activity:7503481913303584769/",
                "author_slug": "manuela-g",
                "activity_id": "7503481913303584769",
                "urn_kind": "activity",
            },
            {
                "kind": "feed_post",
                "url": "https://www.linkedin.com/feed/update/urn:li:activity:7503200610150973442/",
                "author_slug": "kimberlymembrillo",
                "activity_id": "7503200610150973442",
                "urn_kind": "activity",
            },
            {
                "kind": "person",
                "url": "https://www.linkedin.com/in/kimberlymembrillo/",
                "text": "Kimberly Membrillo",
            },
        ]
        posts = parse_feed_search_posts({"sections": {"search_results": raw}, "references": {"search_results": refs}})
        self.assertEqual(len(posts), 2)
        manuela = posts[0]
        kimberly = posts[1]
        self.assertIn("/feed/update/", manuela["url"])
        self.assertNotIn("recent-activity", manuela["url"])
        self.assertIn("7503481913303584769", manuela["url"])
        self.assertIn("/feed/update/", kimberly["url"])
        self.assertNotIn("recent-activity", kimberly["url"])

    def test_match_author_activity_ref_builds_feed_update_from_urn(self):
        refs = [
            {
                "kind": "feed_post",
                "url": "",
                "author_slug": "gabriela-rayo-10b6a262",
                "activity_id": "7501660025132589056",
                "urn_kind": "activity",
            }
        ]
        url, source = match_author_activity_ref("Gabriela Rayo", refs)
        self.assertEqual(
            url,
            "https://www.linkedin.com/feed/update/urn:li:activity:7501660025132589056/",
        )
        self.assertEqual(source, "activity_ref_urn")

    def test_extract_feed_posts_from_html_pairs_two_authors(self):
        html = (FIXTURES / "content_search_two_posts.html").read_text(encoding="utf-8")
        posts = extract_feed_posts_from_html(html)
        by_slug = {p["author_slug"]: p["url"] for p in posts}
        self.assertIn("monikakuqi", by_slug)
        self.assertIn("kimberlymembrillo", by_slug)
        self.assertIn("7503481913303584769", by_slug["monikakuqi"])
        self.assertIn("7503200610150973442", by_slug["kimberlymembrillo"])

    def test_extract_feed_posts_from_html_pairs_author_and_urn(self):
        html = """
        <article data-urn="urn:li:activity:7503481913303584769">
          <a href="https://www.linkedin.com/in/monikakuqi/">Monika Kuqi</a>
          <span class="update-components-actor__title"><span>Monika Kuqi</span></span>
        </article>
        """
        posts = extract_feed_posts_from_html(html)
        self.assertEqual(len(posts), 1)
        self.assertIn("7503481913303584769", posts[0]["url"])
        self.assertIn("monikakuqi", posts[0]["author_slug"])

    def test_harvest_feed_posts_from_network_body(self):
        body = (
            '{"actor":{"name":{"text":"Monika Kuqi"}},"commentary":{"text":"Hiring"},'
            '"entityUrn":"urn:li:activity:7503481913303584769"}'
        )
        posts = harvest_feed_posts_from_network_body(body)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["author"], "Monika Kuqi")
        self.assertIn("7503481913303584769", posts[0]["url"])

    def test_resolve_author_post_url_uses_author_map(self):
        author_map = {"monika kuqi": "https://www.linkedin.com/feed/update/urn:li:activity:123/"}
        url, source = resolve_author_post_url("Monika Kuqi", author_url_map=author_map)
        self.assertIn("/feed/update/", url)
        self.assertEqual(source, "author_map")

    def test_parse_feed_search_posts_uses_chunk_post_urls(self):
        raw = "Feed post\n\nMonika Kuqi\n\n1h • \n\nFollow\n\nHiring AI Engineer LATAM\n"
        posts = parse_feed_search_posts(
            {
                "sections": {"search_results": raw},
                "references": {"search_results": []},
                "chunk_post_urls": [
                    "https://www.linkedin.com/feed/update/urn:li:activity:7503481913303584769/"
                ],
            }
        )
        self.assertEqual(len(posts), 1)
        self.assertIn("7503481913303584769", posts[0]["url"])
        self.assertEqual(posts[0]["url_source"], "collect_chunk_url")

    def test_resolve_chunk_authors_company_page_post(self):
        chunk = (
            "CtrlSkill Data & AI Training Hub\n\n"
            "Shadab Barmare • 3rd+\n\n"
            "9h\n\nJoin\n\n"
            "We're building something bigger than a course.\n"
        )
        person, company = resolve_chunk_authors(chunk)
        self.assertEqual(person, "Shadab Barmare")
        self.assertEqual(company, "CtrlSkill Data & AI Training Hub")

    def test_parse_feed_search_posts_company_page_uses_person_for_url(self):
        raw = (
            "Feed post\n\n"
            "CtrlSkill Data & AI Training Hub\n\n"
            "Shadab Barmare • 3rd+\n\n"
            "9h\n\nJoin\n\n"
            "We're building something bigger than a course.\n"
        )
        activity = "https://www.linkedin.com/feed/update/urn:li:activity:7501234567890123456/"
        posts = parse_feed_search_posts(
            {
                "sections": {"search_results": raw},
                "references": {"search_results": []},
                "chunk_post_urls": [""],
                "ordered_activity_urls": [activity],
                "author_post_urls": {"shadab barmare": activity},
            }
        )
        self.assertEqual(len(posts), 1)
        self.assertIn("7501234567890123456", posts[0]["url"])
        self.assertEqual(posts[0]["author"], "Shadab Barmare")
        self.assertEqual(posts[0]["company_header"], "CtrlSkill Data & AI Training Hub")

    def test_parse_feed_search_posts_falls_back_to_ordered_activity_urls(self):
        raw = (
            "Feed post\n\nAngela Hernández santamaría\n\n2h • \n\nFollow\n\n"
            "WE'RE HIRING | ADVANCED TO BILINGUAL ENGLISH REQUIRED\n"
        )
        activity = "https://www.linkedin.com/feed/update/urn:li:activity:7505685397302284290/"
        posts = parse_feed_search_posts(
            {
                "sections": {"search_results": raw},
                "references": {"search_results": []},
                "chunk_post_urls": [""],
                "ordered_activity_urls": [activity],
            }
        )
        self.assertEqual(len(posts), 1)
        self.assertIn("7505685397302284290", posts[0]["url"])
        self.assertIn(
            posts[0]["url_source"],
            {"ordered_activity_index", "collect_chunk_url", "text_feed_update"},
        )

    def test_extract_ordered_feed_update_urls_dedupes_in_order(self):
        html = (
            'href="https://www.linkedin.com/feed/update/urn:li:activity:111/" '
            '"activityUrn":"urn:li:activity:222" '
            'https://www.linkedin.com/feed/update/urn:li:activity:111/'
        )
        urls = extract_ordered_feed_update_urls(html)
        self.assertEqual(len(urls), 2)
        self.assertIn("111", urls[0])
        self.assertIn("222", urls[1])

    def test_parse_feed_search_posts_preserves_index_aligned_urls(self):
        raw = (
            "Feed post\n\n"
            "Alice Recruiter\n\n1h • \n\nFollow\n\nHiring AI Engineer LATAM\n\n"
            "Feed post\n\n"
            "Bob Recruiter\n\n2h • \n\nFollow\n\nHiring AI Engineer remote\n"
        )
        refs = [
            {
                "kind": "feed_post",
                "url": "https://www.linkedin.com/feed/update/urn:li:activity:100/",
                "text": "Alice Recruiter",
            },
            {
                "kind": "feed_post",
                "url": "https://www.linkedin.com/feed/update/urn:li:activity:200/",
                "text": "Bob Recruiter",
            },
        ]
        posts = parse_feed_search_posts({"sections": {"search_results": raw}, "references": {"search_results": refs}})
        self.assertEqual(posts[0]["url"], refs[0]["url"])
        self.assertEqual(posts[1]["url"], refs[1]["url"])

    def test_post_to_job_strips_recent_activity_url(self):
        cfg = load_example_linkedin_config()
        post = {
            "text": "We're hiring an AI Engineer remote LATAM. USD 120k. urn:li:activity:7503481913303584769",
            "url": "https://www.linkedin.com/in/kimberlymembrillo/recent-activity/all/",
            "author": {"name": "Kimberly Membrillo"},
        }
        meta = {"query": '"ai engineer" + "latam"', "role_keyword": "ai engineer", "region": "latam"}
        job = post_to_job(post, meta, cfg, {})
        self.assertIsNotNone(job)
        self.assertFalse(is_profile_fallback_url(job["url"]))
        self.assertIn("/feed/update/", job["url"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
