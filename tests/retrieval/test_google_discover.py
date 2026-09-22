"""Unit coverage for retrieval.sources.google.discover."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from retrieval.sources.google import discover as gd


JOB_HTML = """
<html><body>
<h1>AI Engineer</h1>
<p>Remote LATAM hiring. Requirements: Python, LLM, RAG.</p>
<p>Salary: $120k–$150k USD. Apply now.</p>
</body></html>
"""


@pytest.fixture
def cfg() -> dict:
    return {
        "query_template": '"{role}" remote after:{after_date}',
        "default_after_days": 7,
        "roles": ["ai engineer"],
        "max_results_per_role": 5,
        "max_results_total": 20,
        "profile_match_keywords": ["langchain"],
        "posts_default_filter_result": "needs_review",
        "require_usd_salary": False,
        "google_cse": {"api_key_env": "GOOGLE_CSE_API_KEY", "cx_env": "GOOGLE_CSE_CX"},
    }


def test_build_query_and_default_after_date(cfg):
    assert gd.build_query("ai engineer", "2026-01-01", cfg) == '"ai engineer" remote after:2026-01-01'
    after = gd.default_after_date(cfg)
    assert len(after) == 10 and after[4] == "-"


def test_search_google_cse_missing_keys_returns_empty(cfg):
    with patch.dict("os.environ", {}, clear=True):
        assert gd.search_google_cse("q", cfg) == []


def test_search_google_cse_parses_response(cfg):
    body = json.dumps({"items": [{"link": "https://jobs.example/1", "title": "AI", "snippet": "hiring"}]}).encode()
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)

    with patch.dict("os.environ", {"GOOGLE_CSE_API_KEY": "k", "GOOGLE_CSE_CX": "cx"}):
        with patch("urllib.request.urlopen", return_value=resp):
            hits = gd.search_google_cse("ai engineer", cfg)
    assert hits[0]["url"] == "https://jobs.example/1"


def test_fetch_page_strips_html():
    raw = b"<style>x</style><script>y</script><p>Hello&nbsp;world</p>"
    resp = MagicMock()
    resp.read.return_value = raw
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=resp):
        text = gd.fetch_page("https://example.com/job")
    assert "Hello" in text and "world" in text


def test_is_noise_url_and_job_page_heuristics(cfg):
    assert gd.is_noise_url("https://github.com/org/repo") is True
    assert gd.is_noise_url("https://company.com/careers/ai-engineer") is False
    assert gd.page_is_js_shell("enable javascript") is True
    assert gd.looks_like_job_page("remote hiring apply requirements engineer", "AI Engineer", "https://co.com/jobs/1") is True


def test_geo_blocked_latam_and_us_only():
    assert gd.latam_friendly("remote latam only") is True
    blocked, reason = gd.geo_blocked("US only candidates remote engineer apply")
    assert blocked is True and reason == "geo_restricted"
    assert gd.geo_blocked("Worldwide remote LATAM friendly hiring apply engineer")[0] is False


def test_extractors():
    assert gd.extract_salary("Pay $120k–$150k") == "$120k"
    role = gd.extract_role("AI Engineer | Acme", "We need an AI Engineer remote", "ai engineer")
    assert "Engineer" in role
    assert gd.extract_company("AI Engineer | Acme AI", "") == "Acme AI"


def test_profile_match_score(cfg):
    score = gd.profile_match_score(
        "AI engineer remote LATAM LLM RAG langchain $120k apply",
        "AI Engineer role",
        "ai engineer",
        cfg,
    )
    assert score > 2.0


def test_result_to_job_success(cfg):
    result = {
        "url": "https://company.com/careers/ai-engineer",
        "title": "AI Engineer | Acme",
        "snippet": "Remote LATAM LLM hiring apply requirements",
    }
    with patch("retrieval.sources.google.discover.fetch_page", return_value=JOB_HTML):
        job = gd.result_to_job(result, "ai engineer", cfg, {})
    assert job is not None
    assert job["filter_result"] in {"eligible", "needs_review"}
    assert job["company"] != "Unknown"


def test_result_to_job_rejects_noise(cfg):
    result = {"url": "https://github.com/x/y", "title": "Repo", "snippet": ""}
    assert gd.result_to_job(result, "ai engineer", cfg, {}) is None


def test_collect_search_results_from_input_json(tmp_path: Path, cfg):
    payload = {
        "queries": [
            {
                "query": "ai engineer remote",
                "role_keyword": "ai engineer",
                "results": [{"url": "https://jobs.example/1", "title": "AI Engineer"}],
            }
        ]
    }
    path = tmp_path / "input.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    out = gd.collect_search_results(cfg, "2026-01-01", path)
    assert out[0]["query"] == "ai engineer remote"
    assert out[0]["role_keyword"] == "ai engineer"


def test_run_discovery_dry_run_with_input(tmp_path: Path, cfg, monkeypatch):
    payload = {
        "queries": [
            {
                "query": "q",
                "role_keyword": "ai engineer",
                "results": [
                    {
                        "url": "https://company.com/careers/ai-engineer",
                        "title": "AI Engineer | Acme",
                        "snippet": "Remote LATAM LLM RAG apply requirements engineer hiring",
                    }
                ],
            }
        ]
    }
    input_path = tmp_path / "in.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(gd, "load_config", lambda: cfg)
    monkeypatch.setattr(gd, "load_json", lambda *_a, **_k: {})
    monkeypatch.setattr(gd, "load_registry", lambda: {"jobs": []})
    monkeypatch.setattr(gd, "merge_jobs", lambda reg, jobs, since: (reg, jobs))
    with patch("retrieval.sources.google.discover.fetch_page", return_value=JOB_HTML):
        result = gd.run_discovery(input_json=input_path, dry_run=True)
    assert result["matched"] >= 1
    assert result["new_total"] >= 1


def test_run_discovery_no_results_returns_error(cfg, monkeypatch):
    monkeypatch.setattr(gd, "load_config", lambda: cfg)
    monkeypatch.setattr(gd, "load_json", lambda *_a, **_k: {})
    with patch("retrieval.sources.google.discover.search_google_cse", return_value=[]):
        result = gd.run_discovery(dry_run=True)
    assert "error" in result


def test_write_google_run_markdown_and_save_json(tmp_path: Path):
    run_path = tmp_path / "run.md"
    jobs = [
        {
            "role": "AI Engineer",
            "company": "Acme",
            "salary_usd": "$120k",
            "location_note": "LATAM",
            "match_score": 5.0,
            "filter_result": "eligible",
            "url": "https://example.com",
        },
        {
            "role": "Staff AI Engineer",
            "company": "Beta",
            "match_score": 3.0,
            "filter_result": "needs_review",
            "skip_reason": "no_usd_salary",
            "url": "https://beta.example.com",
        },
    ]
    gd.write_google_run_markdown(run_path, "2026-01-01", jobs, {"google": {"fetched": 2, "new": 2, "eligible": 1}})
    text = run_path.read_text(encoding="utf-8")
    assert "Matched roles" in text
    assert "Needs review" in text

    state_path = tmp_path / "state.json"
    gd.save_json(state_path, {"last_run_at": "now"})
    assert json.loads(state_path.read_text(encoding="utf-8"))["last_run_at"] == "now"


def test_main_json_and_error_paths(tmp_path: Path, cfg, monkeypatch, capsys):
    monkeypatch.setattr(
        gd,
        "run_discovery",
        lambda **kwargs: {"error": "missing keys", "after_date": "2026-01-01"},
    )
    monkeypatch.setattr(
        "sys.argv",
        ["discover.py"],
    )
    assert gd.main() == 1

    monkeypatch.setattr(
        gd,
        "run_discovery",
        lambda **kwargs: {"after_date": "2026-01-01", "matched": 0, "new_total": 0, "eligible": 0, "run_path": str(tmp_path / "r.md"), "jobs": []},
    )
    monkeypatch.setattr("sys.argv", ["discover.py", "--json"])
    assert gd.main() == 0
    assert "after_date" in capsys.readouterr().out
