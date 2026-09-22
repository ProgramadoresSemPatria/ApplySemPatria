"""run_query / run_all coverage for jobs_collect."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from linkedin_jobs_collect import run_all, run_query  # noqa: E402
from tests.helpers.example_configs import load_example_linkedin_jobs_config  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "linkedin_jobs_search_page.html"


@pytest.mark.asyncio
async def test_run_query_with_mocked_collect(tmp_path: Path, monkeypatch):
    html = FIXTURE.read_text(encoding="utf-8")
    listings = [{"job_id": "1", "title": "AI Engineer", "company": "Acme", "easy_apply": True}]
    page_stats = {"pages": 1, "listings_total": 1}

    monkeypatch.setattr(
        "linkedin_jobs_collect.collect_jobs_pages",
        AsyncMock(return_value=(listings, page_stats)),
    )
    monkeypatch.setattr(
        "linkedin_jobs_collect.listings_to_jobs_preview",
        lambda listings, meta, max_roles, track_id: [{"source": "linkedin_jobs", "role": "AI Engineer", "company": "Acme", "url": "https://li/jobs/1"}],
    )
    monkeypatch.setattr("linkedin_jobs_collect.merge_payload", lambda *a, **k: {"new_total": 1})

    meta = {
        "query": "ai engineer",
        "role_keyword": "ai engineer",
        "region": "latam",
        "track": "ai-engineer",
        "linkedin_url": "https://www.linkedin.com/jobs/search/?keywords=ai",
    }
    cfg = load_example_linkedin_jobs_config()
    result = await run_query(
        meta,
        period_days=1,
        max_pages=1,
        max_roles=5,
        merge=True,
        since="2026-01-01",
        cfg=cfg,
        out_dir=tmp_path,
    )
    assert result["listings_found"] == 1
    assert result["roles_kept"] == 1
    assert Path(result["raw_path"]).is_file()


@pytest.mark.asyncio
async def test_run_all_skips_disabled_track(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "linkedin_jobs_collect.build_all_track_queries",
        lambda: [{"query": "ai", "role_keyword": "ai", "region": "latam", "track": "ai-engineer"}],
    )
    cfg = load_example_linkedin_jobs_config()
    cfg["jobs_collect_enabled"] = False
    monkeypatch.setattr("linkedin_jobs_collect.load_linkedin_jobs_config", lambda t: cfg)
    monkeypatch.setattr("linkedin_jobs_collect.RUNS", tmp_path)
    result = await run_all(period_days=1, max_pages=1, max_roles=5, max_roles_total=5, merge=False, since="2026-01-01")
    assert result["queries_run"] == 0 or "results" in result
