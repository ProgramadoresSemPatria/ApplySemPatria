"""Coverage for retrieval.sources.boards.discover orchestrator."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from retrieval.sources.boards import discover as bd


def test_load_config_delegates(monkeypatch):
    monkeypatch.setattr(bd, "load_board_config", lambda tid=None: {"sources": {}})
    assert bd.load_config("ai-engineer") == {"sources": {}}


def test_run_discovery_dry_run_single_track(monkeypatch):
    config = {
        "sources": {
            name: {"enabled": name == "remoteok"}
            for name in bd.COLLECTORS
        }
    }
    sample_job = {
        "source": "remoteok",
        "url": "https://remoteok.com/l/1",
        "role": "AI Engineer",
        "company": "Acme",
    }

    monkeypatch.setattr(bd, "list_track_ids", lambda: ["ai-engineer"])
    monkeypatch.setattr(bd, "resolve_track", lambda tid: tid or "ai-engineer")
    monkeypatch.setattr(bd, "load_board_config", lambda tid: config)
    monkeypatch.setattr(bd, "load_json", lambda *_a, **_k: {"last_run_at": None})
    monkeypatch.setattr(bd, "load_registry", lambda: {"jobs": []})
    monkeypatch.setattr(bd, "parse_since", lambda *_a, **_k: __import__("datetime").datetime.now(bd.LOCAL_TZ))
    monkeypatch.setattr(bd, "merge_jobs", lambda reg, jobs, since: (reg, jobs))
    monkeypatch.setattr(bd, "stamp_track", lambda job, tid: {**job, "track": tid})
    monkeypatch.setattr(bd, "evaluate_job", lambda job, cfg: job.update({"filter_result": "eligible"}) or job)
    monkeypatch.setitem(bd.COLLECTORS, "remoteok", MagicMock(return_value=[sample_job]))
    for name in bd.COLLECTORS:
        if name != "remoteok":
            monkeypatch.setitem(bd.COLLECTORS, name, MagicMock(return_value=[]))

    result = bd.run_discovery("24h", dry_run=True, track_id="ai-engineer")
    assert result["new_total"] == 1
    assert result["eligible"] == 1
    assert result["dry_run"] is True
    assert "remoteok" in result["source_stats"]


def test_run_discovery_collector_error(monkeypatch):
    config = {"sources": {name: {"enabled": name == "remoteok"} for name in bd.COLLECTORS}}

    monkeypatch.setattr(bd, "resolve_track", lambda tid: "ai-engineer")
    monkeypatch.setattr(bd, "load_board_config", lambda tid: config)
    monkeypatch.setattr(bd, "load_json", lambda *_a, **_k: {})
    monkeypatch.setattr(bd, "load_registry", lambda: {"jobs": []})
    monkeypatch.setattr(bd, "parse_since", lambda *_a, **_k: __import__("datetime").datetime.now(bd.LOCAL_TZ))
    monkeypatch.setattr(bd, "merge_jobs", lambda reg, jobs, since: (reg, jobs))

    def boom(_cfg):
        raise RuntimeError("network down")

    monkeypatch.setitem(bd.COLLECTORS, "remoteok", boom)
    for name in bd.COLLECTORS:
        if name != "remoteok":
            monkeypatch.setitem(bd.COLLECTORS, name, MagicMock(return_value=[]))

    result = bd.run_discovery("24h", dry_run=True)
    assert result["errors"]
    assert result["source_stats"]["remoteok"]["error"] == "network down"


def test_main_json_output(monkeypatch, capsys):
    monkeypatch.setattr(
        bd,
        "run_discovery",
        lambda *a, **k: {
            "since": "2026-01-01T00:00:00",
            "new_total": 0,
            "eligible": 0,
            "skipped": 0,
            "errors": [],
            "run_path": "/tmp/run.md",
            "registry_path": "/tmp/jobs.json",
        },
    )
    monkeypatch.setattr("sys.argv", ["discover.py", "--json"])
    assert bd.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["since"].startswith("2026")
