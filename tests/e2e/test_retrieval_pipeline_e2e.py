"""E2E retrieval pipeline: collect fixtures → merge → registry → table (no live browser)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from tests.helpers.example_configs import load_example_linkedin_config  # noqa: E402


@pytest.fixture
def linkedin_cfg():
    return load_example_linkedin_config()


@pytest.fixture
def registry_env(tmp_path, monkeypatch, linkedin_cfg):
    registry_path = tmp_path / "registry" / "jobs.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(json.dumps({"jobs": []}), encoding="utf-8")
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    import retrieval.registry.store as store
    import retrieval.sources.linkedin.posts_merge as posts_merge

    monkeypatch.setattr(posts_merge, "REGISTRY_PATH", registry_path)
    monkeypatch.setattr(store, "REGISTRY_PATH", registry_path)
    monkeypatch.setattr(posts_merge, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(posts_merge, "load_linkedin_config", lambda *a, **k: linkedin_cfg)
    monkeypatch.setattr(
        posts_merge,
        "LINKEDIN_STATE_PATH",
        state_dir / "linkedin-last-run.json",
    )
    monkeypatch.setattr(
        posts_merge,
        "JOB_SEARCH_CONFIG",
        tmp_path / "config.json",
    )
    return registry_path, runs_dir


def test_e2e_retrieval_merge_produces_real_post_url(registry_env):
    """Merge hiring post via retrieval layer → registry row with feed/update URL."""
    registry_path, _runs = registry_env
    from retrieval.sources.linkedin.posts_merge import merge_payload

    urn = "7503481913303584769"
    feed_url = f"https://www.linkedin.com/feed/update/urn:li:activity:{urn}/"
    inner = (
        "Feed post\n\nMonika Kuqi\n\n1h • \n\nFollow\n\n"
        "We're hiring an AI Engineer remote LATAM. USD 120k-150k.\n"
    )
    feed_payload = {
        "sections": {"search_results": inner},
        "references": {"search_results": []},
        "chunk_post_urls": [feed_url],
        "author_post_urls": {"monika kuqi": feed_url},
    }
    payload = {
        "period_days": 7,
        "queries": [
            {
                "query": '"ai engineer" + "latam"',
                "role_keyword": "ai engineer",
                "region": "latam",
                "feed_payload": feed_payload,
            }
        ],
    }

    result = merge_payload(payload, period_days=7, since_arg="30d")

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    linkedin = [j for j in registry["jobs"] if j.get("source") == "linkedin_posts"]
    assert result["new_total"] >= 1
    assert any(urn in (j.get("url") or "") for j in linkedin)


def test_e2e_retrieval_boards_discover_dry_run(tmp_path, monkeypatch):
    """Board discover merges collector output without live HTTP."""
    registry_path = tmp_path / "registry" / "jobs.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(json.dumps({"jobs": []}), encoding="utf-8")

    import retrieval.registry.store as store
    import retrieval.sources.boards.discover as board_discover

    monkeypatch.setattr(store, "REGISTRY_PATH", registry_path)
    monkeypatch.setattr(store, "STATE_PATH", tmp_path / "state" / "last-run.json")
    monkeypatch.setattr(store, "RUNS_DIR", tmp_path / "runs")

    fake_job = {
        "source": "remoteok",
        "url": "https://remoteOK.com/remote-jobs/test-role",
        "role": "AI Engineer",
        "company": "Test Co",
        "salary_usd": "$100k",
        "location_note": "Remote",
    }

    monkeypatch.setitem(
        board_discover.COLLECTORS,
        "remoteok",
        lambda _cfg: [fake_job],
    )

    result = board_discover.run_discovery("7d", dry_run=False, track_id="ai-engineer")
    assert result["new_total"] >= 1
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert any(j.get("company") == "Test Co" for j in registry["jobs"])


def test_e2e_retrieval_copy_link_fixture():
    """Copy-link helpers parse SDUI card fixture without browser."""
    from retrieval.sources.linkedin.copy_link import (
        extract_ordered_article_post_cards,
        normalize_copied_post_url,
    )

    fixture = ROOT / "tests/fixtures/linkedin/content_search_melissa_sdui.html"
    html = fixture.read_text(encoding="utf-8")
    cards = extract_ordered_article_post_cards(html)
    assert cards, "SDUI fixture should expose post cards"

    sample = "https://lnkd.in/p/abc123"
    mock_proc = type("P", (), {"stdout": "location: https://www.linkedin.com/posts/melissa-oliveira-in_test-share-123/\n"})()
    with patch("subprocess.run", return_value=mock_proc):
        resolved = normalize_copied_post_url(sample)
    assert "/posts/" in resolved
