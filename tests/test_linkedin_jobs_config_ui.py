#!/usr/bin/env python3
"""Config UI bundle includes linkedin_jobs section."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from config_ui_data import load_config_bundle, save_config_section  # noqa: E402


class LinkedInJobsConfigUiTests(unittest.TestCase):
    def test_bundle_has_linkedin_jobs(self):
        bundle = load_config_bundle("ai-engineer")
        self.assertIn("linkedin_jobs", bundle)
        self.assertTrue(bundle["linkedin_jobs"].get("roles"))

    def test_save_linkedin_jobs_section(self):
        before = load_config_bundle("ai-engineer")["linkedin_jobs"]
        try:
            bundle = save_config_section(
                "ai-engineer",
                "linkedin_jobs",
                {"default_max_pages": 3, "jobs_collect_enabled": False},
            )
            self.assertEqual(bundle["linkedin_jobs"]["default_max_pages"], 3)
            self.assertFalse(bundle["linkedin_jobs"]["jobs_collect_enabled"])
        finally:
            save_config_section(
                "ai-engineer",
                "linkedin_jobs",
                {
                    "default_max_pages": before.get("default_max_pages", 10),
                    "jobs_collect_enabled": True,
                },
            )


if __name__ == "__main__":
    unittest.main()
