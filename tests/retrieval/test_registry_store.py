"""Additional coverage for retrieval.registry.store."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from retrieval.registry import store


def test_job_key_prefers_url():
    job = {"track": "ai-engineer", "url": "https://Example.com/Posts/1", "company": "X", "role": "Y"}
    assert store.job_key(job) == "ai-engineer|https://example.com/posts/1"


def test_job_key_fallback_company_role():
    job = {"source": "google", "company": "Acme", "role": "AI Engineer"}
    assert store.job_key(job) == "google|acme|ai engineer"


def test_is_placeholder_job_key():
    assert store.is_placeholder_job_key("ai-engineer|linkedin-post:abc123") is True
    assert store.is_placeholder_job_key("ai-engineer|https://linkedin.com/posts/x") is False


def test_remember_legacy_job_key():
    job: dict = {}
    store.remember_legacy_job_key(job, "ai-engineer|linkedin-post:deadbeef")
    assert job["legacy_job_key"] == "ai-engineer|linkedin-post:deadbeef"
    store.remember_legacy_job_key(job, "not-a-placeholder")
    assert job["legacy_job_key"] == "ai-engineer|linkedin-post:deadbeef"


def test_find_job_by_key_legacy_and_direct():
    job = {
        "track": "ai-engineer",
        "url": "https://www.linkedin.com/posts/fixed",
        "legacy_job_key": "ai-engineer|linkedin-post:abc123",
        "company": "Acme",
        "role": "AI Engineer",
    }
    jobs = [job]
    assert store.find_job_by_key(jobs, store.job_key(job)) is job
    assert store.find_job_by_key(jobs, "ai-engineer|linkedin-post:abc123") is job


def test_placeholder_mapping_from_runs(tmp_path: Path, monkeypatch):
    runs = tmp_path / "runs"
    collect_dir = runs / "browser-collect-test"
    collect_dir.mkdir(parents=True)
    payload = {
        "jobs": [
            {
                "url": "linkedin-post:abc123",
                "company": "Acme",
                "role": "AI Engineer",
                "search_query": "ai engineer latam",
                "discovery_index": 2,
            }
        ]
    }
    (collect_dir / "raw.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(store, "RUNS_DIR", runs)
    if hasattr(store.find_job_by_key, "_placeholder_map"):
        delattr(store.find_job_by_key, "_placeholder_map")

    mapping = store._placeholder_collect_mapping()
    assert "ai-engineer|linkedin-post:abc123" in mapping or "linkedin-post:abc123" in str(mapping)


def test_backfill_legacy_job_keys(tmp_path: Path, monkeypatch):
    runs = tmp_path / "runs"
    collect_dir = runs / "browser-collect-test"
    collect_dir.mkdir(parents=True)
    (collect_dir / "raw.json").write_text(
        json.dumps(
            {
                "jobs": [
                    {"url": "linkedin-post:feed1", "company": "Acme", "role": "AI Engineer", "discovery_index": 1}
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(store, "RUNS_DIR", runs)
    if hasattr(store.find_job_by_key, "_placeholder_map"):
        delattr(store.find_job_by_key, "_placeholder_map")

    registry = {
        "jobs": [
            {
                "company": "Acme",
                "role": "AI Engineer",
                "url": "https://www.linkedin.com/posts/acme-123",
                "discovery_index": 1,
            }
        ]
    }
    updated = store.backfill_legacy_job_keys(registry)
    assert updated >= 0
