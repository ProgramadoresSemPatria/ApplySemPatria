"""jobsearch.settings.yaml / .json loader."""

from __future__ import annotations

import json

import pytest

from retrieval import jobsearch_settings
from browser_session import linkedin_collect_headless


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    jobsearch_settings.load_settings.cache_clear()
    yield
    jobsearch_settings.load_settings.cache_clear()


def test_load_settings_json(tmp_path, monkeypatch):
    path = tmp_path / "jobsearch.settings.json"
    path.write_text(
        json.dumps({"browser": {"linkedin_collect_visible": True}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(jobsearch_settings, "SETTINGS_YAML", tmp_path / "missing.yaml")
    monkeypatch.setattr(jobsearch_settings, "SETTINGS_JSON", path)
    assert jobsearch_settings.linkedin_collect_visible_from_settings() is True


def test_linkedin_collect_headless_from_settings(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBSEARCH_COLLECT_HEADED", raising=False)
    path = tmp_path / "jobsearch.settings.json"
    path.write_text(
        json.dumps({"browser": {"linkedin_collect_visible": True}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(jobsearch_settings, "SETTINGS_YAML", tmp_path / "missing.yaml")
    monkeypatch.setattr(jobsearch_settings, "SETTINGS_JSON", path)
    jobsearch_settings.load_settings.cache_clear()
    assert linkedin_collect_headless() is False


def test_env_overrides_settings(tmp_path, monkeypatch):
    path = tmp_path / "jobsearch.settings.json"
    path.write_text(
        json.dumps({"browser": {"linkedin_collect_visible": True}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(jobsearch_settings, "SETTINGS_YAML", tmp_path / "missing.yaml")
    monkeypatch.setattr(jobsearch_settings, "SETTINGS_JSON", path)
    jobsearch_settings.load_settings.cache_clear()
    monkeypatch.setenv("JOBSEARCH_COLLECT_HEADED", "0")
    assert linkedin_collect_headless() is True
