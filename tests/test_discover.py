#!/usr/bin/env python3
"""Tests for job discovery pipeline."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from filters import (  # noqa: E402
    evaluate_job,
    has_usd_salary,
    is_blacklisted_url,
    is_eu_only,
    is_us_only,
    job_is_blacklisted,
    matches_title,
    salary_sort_value,
    sort_jobs_by_salary,
)
from registry import merge_jobs, parse_since, parse_posted_at  # noqa: E402


class FilterTests(unittest.TestCase):
    def test_matches_title_word_boundary(self):
        self.assertFalse(matches_title("Retail Store Associate", ["ai"]))
        self.assertTrue(matches_title("Senior AI Engineer", ["ai engineer"]))

    def test_usd_salary(self):
        self.assertTrue(has_usd_salary("$120,000 - $180,000"))
        self.assertTrue(has_usd_salary(None, currency="USD"))
        self.assertFalse(has_usd_salary("Competitive"))

    def test_geo_filters(self):
        self.assertTrue(is_eu_only("Europe"))
        self.assertTrue(is_us_only("United States only in description", "Remote"))
        self.assertFalse(is_eu_only("Worldwide"))

    def test_evaluate_eligible(self):
        config = {"filters": {"require_usd_salary": True, "skip_eu_only": True, "skip_us_only": True}}
        job = evaluate_job(
            {
                "salary_usd": "$100k",
                "currency": "USD",
                "location_note": "Worldwide",
            },
            config,
        )
        self.assertEqual(job["filter_result"], "eligible")

    def test_evaluate_skip_no_salary(self):
        config = {"filters": {"require_usd_salary": True, "salary_unknown_action": "skip"}}
        job = evaluate_job({"location_note": "Remote"}, config)
        self.assertEqual(job["filter_result"], "skipped")
        self.assertEqual(job["skip_reason"], "no_usd_salary")

    def test_evaluate_skip_us_only(self):
        config = {"filters": {"require_usd_salary": False, "skip_us_only": True}}
        job = evaluate_job({"location_note": "United States", "salary_usd": "$100k"}, config)
        self.assertEqual(job["filter_result"], "skipped")
        self.assertEqual(job["skip_reason"], "us_only")

    def test_blacklist_domain(self):
        blocked, reason = is_blacklisted_url("https://talentpulse.66ghz.com/remote-jobs/genai-engineer")
        self.assertTrue(blocked)
        self.assertEqual(reason, "fake_job_aggregator")

    def test_blacklist_phishing_substring(self):
        blocked, reason = is_blacklisted_url("https://ihire.allboardsolutions.in/apply-for-the-job/")
        self.assertTrue(blocked)
        self.assertEqual(reason, "phishing_apply_portal")

    def test_blacklist_allows_lever(self):
        blocked, _ = is_blacklisted_url("https://jobs.lever.co/tryjeeves/639e39d0-b357-4bc2-aff2-968cdedb14b6")
        self.assertFalse(blocked)

    def test_evaluate_skip_blacklisted(self):
        config = {"filters": {"require_usd_salary": False}}
        job = evaluate_job(
            {
                "url": "https://taskworks.totalh.net/remote-jobs/senior-ai-engineer-5",
                "location_note": "LATAM",
                "salary_usd": "$5000/mo",
            },
            config,
        )
        self.assertEqual(job["filter_result"], "skipped")
        self.assertEqual(job["skip_reason"], "fake_job_aggregator")

    def test_job_blacklisted_via_snippet_url(self):
        blocked, reason = job_is_blacklisted(
            {
                "url": "https://www.linkedin.com/in/recruiter/",
                "description_snippet": "Apply here https://ihire.allboardsolutions.in/apply-for-the-job/ today",
            }
        )
        self.assertTrue(blocked)
        self.assertEqual(reason, "phishing_apply_portal")

    def test_salary_sort_annual(self):
        self.assertEqual(salary_sort_value("$84K–$120K USD"), 120000.0)

    def test_salary_sort_monthly(self):
        self.assertEqual(salary_sort_value("US$ 2.100 a US$ 3.500/mês"), 42000.0)

    def test_sort_jobs_by_salary_desc(self):
        jobs = [
            {"role": "A", "salary_usd": "$2,100/mo", "filter_result": "eligible"},
            {"role": "B", "salary_usd": "$100K", "filter_result": "eligible"},
            {"role": "C", "salary_usd": None, "filter_result": "needs_review"},
        ]
        ordered = [j["role"] for j in sort_jobs_by_salary(jobs)]
        self.assertEqual(ordered, ["B", "A", "C"])


class RegistryTests(unittest.TestCase):
    def test_parse_since_relative(self):
        since = parse_since("7d", None)
        self.assertLess(since, datetime.now(timezone.utc))

    def test_parse_posted_at_epoch(self):
        dt = parse_posted_at(1787495100)
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_merge_dedupes(self):
        registry = {"jobs": []}
        job = {
            "source": "remoteok",
            "url": "https://remoteok.com/job/1",
            "role": "AI Engineer",
            "company": "Acme",
            "posted_at": datetime.now(timezone.utc).isoformat(),
            "filter_result": "eligible",
        }
        _, new_jobs = merge_jobs(registry, [job], datetime.min.replace(tzinfo=timezone.utc))
        self.assertEqual(len(new_jobs), 1)
        _, new_again = merge_jobs(registry, [job], datetime.min.replace(tzinfo=timezone.utc))
        self.assertEqual(len(new_again), 0)


class CollectorIntegrationTests(unittest.TestCase):
    """Live network tests — verify real sources respond."""

    def test_remoteok_live(self):
        from collectors.remoteok import collect

        config = json.loads((ROOT / "config.json").read_text())
        jobs = collect(config)
        self.assertGreater(len(jobs), 0, "RemoteOK should return AI-related jobs")
        self.assertIn("url", jobs[0])
        self.assertIn("role", jobs[0])

    def test_opentoworkremote_live(self):
        from collectors.opentoworkremote import collect

        config = json.loads((ROOT / "config.json").read_text())
        jobs = collect(config)
        self.assertGreater(len(jobs), 0, "OpenToWorkRemote API should return jobs")
        self.assertTrue(any("ai" in j["role"].lower() for j in jobs))

    def test_weworkremotely_live(self):
        from collectors.weworkremotely import collect

        config = json.loads((ROOT / "config.json").read_text())
        jobs = collect(config)
        self.assertIsInstance(jobs, list)

    def test_himalayas_live(self):
        from collectors.himalayas import collect

        config = json.loads((ROOT / "config.json").read_text())
        jobs = collect(config)
        self.assertIsInstance(jobs, list)

    def test_full_discovery_dry_run(self):
        from discover import run_discovery

        result = run_discovery("30d", dry_run=True)
        self.assertIn("source_stats", result)
        self.assertIn("remoteok", result["source_stats"])
        self.assertGreater(result["source_stats"]["remoteok"]["fetched"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
