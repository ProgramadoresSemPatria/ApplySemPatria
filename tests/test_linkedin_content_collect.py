"""Regression tests for LinkedIn content collector."""

from __future__ import annotations


def test_collect_feed_text_imports_browsers_path():
    """Regression: BROWSERS_PATH must be defined (NameError broke daily research)."""
    from browser_session import BROWSERS_PATH as expected
    from linkedin_content_collect import BROWSERS_PATH

    assert BROWSERS_PATH == expected
