#!/usr/bin/env python3
"""Tests for table display helpers."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from table_format import format_posted  # noqa: E402


class FormatPostedTests(unittest.TestCase):
    def test_prefers_posted_label(self):
        job = {"posted_label": "2h", "posted_at": 1788713604}
        self.assertEqual(format_posted(job), "2h")

    def test_epoch_seconds_relative(self):
        recent = datetime.now(timezone.utc) - timedelta(hours=3)
        job = {"posted_at": int(recent.timestamp())}
        self.assertEqual(format_posted(job), "3h")

    def test_epoch_seconds_date_when_old(self):
        old = datetime.now(timezone.utc) - timedelta(days=30)
        job = {"posted_at": int(old.timestamp())}
        self.assertEqual(format_posted(job), old.strftime("%Y-%m-%d"))

    def test_iso_date_string(self):
        job = {"posted_at": "2026-08-14T12:00:00+00:00"}
        self.assertEqual(format_posted(job), "2026-08-14")

    def test_himalayas_style_epoch_not_raw_number(self):
        job = {"posted_at": 1788713604}
        result = format_posted(job)
        self.assertFalse(result.isdigit() or len(result) > 8)
        self.assertNotEqual(result, "1788713604")

    def test_missing_posted(self):
        self.assertEqual(format_posted({}), "—")


if __name__ == "__main__":
    unittest.main()
