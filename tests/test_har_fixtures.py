"""HAR fixture integrity — unit tier (no browser)."""

from __future__ import annotations

import json

import pytest

from tests.helpers.linkedin_har import HAR_SLUGS, har_path, mock_profile_url


def test_all_har_files_present_and_valid():
    for name, slug in HAR_SLUGS.items():
        path = har_path(name)
        assert path.stat().st_size > 100, f"{path} too small"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "log" in data
        entries = data["log"].get("entries") or []
        assert entries, f"{name} has no entries"
        urls = [e["request"]["url"] for e in entries]
        expected = mock_profile_url(slug)
        assert any(expected in u for u in urls), f"{expected} not in {urls}"


@pytest.mark.parametrize("name,slug", list(HAR_SLUGS.items()))
def test_har_entry_count_stable(name: str, slug: str):
    path = har_path(name)
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data["log"]["entries"]
    assert 1 <= len(entries) <= 5, f"{name}: unexpected entry count {len(entries)}"


def test_mock_urls_use_fixed_port():
    url = mock_profile_url("test-connect")
    assert url == "http://127.0.0.1:18766/in/test-connect/"
