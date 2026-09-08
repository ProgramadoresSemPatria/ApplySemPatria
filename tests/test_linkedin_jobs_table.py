#!/usr/bin/env python3
"""Table + UI integration for linkedin_jobs source."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from application_channel import CHANNEL_URL, classify_channel  # noqa: E402
from applications_ui_data import collect_jobs_for_ui, role_from_label  # noqa: E402
from generate_applications import LINKEDIN_TABLE_SOURCES, post_url_for  # noqa: E402

TZ = ZoneInfo("America/Sao_Paulo")


def _sample_job(**overrides):
    base = {
        "source": "linkedin_jobs",
        "url": "https://www.linkedin.com/jobs/view/4100012345/",
        "apply_url": "https://www.linkedin.com/jobs/view/4100012345/",
        "role": "Senior AI Engineer",
        "company": "Acme Robotics",
        "filter_result": "eligible",
        "location_note": "LATAM",
        "discovered_at": datetime.now(TZ).isoformat(),
        "linkedin_easy_apply": True,
        "apply_method": "easy_apply",
    }
    base.update(overrides)
    return base


class LinkedInJobsTableTests(unittest.TestCase):
    def test_linkedin_table_sources_include_jobs(self):
        self.assertIn("linkedin_jobs", LINKEDIN_TABLE_SOURCES)

    def test_post_url_for_job_listing(self):
        job = _sample_job()
        self.assertEqual(post_url_for(job), job["url"])

    def test_role_from_label(self):
        self.assertEqual(role_from_label(_sample_job()), "LinkedIn Job")

    def test_classify_channel_url(self):
        job = _sample_job()
        self.assertEqual(classify_channel(job), CHANNEL_URL)

    def test_collect_jobs_includes_linkedin_jobs(self):
        since = datetime.now(TZ) - timedelta(days=1)
        with patch("applications_ui_data.load_registry") as mock_reg:
            mock_reg.return_value = {"jobs": [_sample_job()]}
            cards = collect_jobs_for_ui(linkedin_since=since, board_since=since)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["role_from"], "linkedin_jobs")
        self.assertTrue(cards[0]["linkedin_easy_apply"])


if __name__ == "__main__":
    unittest.main()
