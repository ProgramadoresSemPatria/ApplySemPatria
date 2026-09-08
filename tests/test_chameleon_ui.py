"""CV Chameleon UI/API regression tests."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.helpers.jobs import linkedin_dm_job, ui_snapshot


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read().decode())


def _post_json(url: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def test_ui_meta_includes_chameleon_status():
    from ui_server import UI_VERSION, ui_meta_payload

    meta = ui_meta_payload()
    assert meta["version"] == UI_VERSION
    ch = meta.get("chameleon") or {}
    assert "ready" in ch
    assert "message" in ch
    assert "masters_count" in ch


def test_job_to_card_includes_chameleon(monkeypatch, tmp_path: Path):
    from applications_ui_data import job_to_card

    master_pdf = tmp_path / "master.pdf"
    master_pdf.write_bytes(b"%PDF-1.4\n% minimal\n")

    cfg = {
        "enabled": True,
        "masters": [
            {
                "id": "ai",
                "label": "AI",
                "pdf_path": str(master_pdf),
                "default": True,
                "keywords": ["Python"],
            }
        ],
        "tech_lexicon": ["python", "rag"],
    }
    monkeypatch.setattr("resume_chameleon.load_chameleon_config", lambda track_id=None: cfg)

    job = linkedin_dm_job()
    job["description_snippet"] = "Need Python, RAG, and LangChain."
    card = job_to_card(
        job,
        section="linkedin_eligible",
        dm={"profiles": {}},
        email_to=set(),
        email_keys=set(),
        url_done=set(),
    )
    assert card["chameleon"]["ready"] is True
    assert "python" in [k.lower() for k in card["chameleon"]["role_keywords"]]
    assert card["chameleon"]["generated"] is False


def test_meta_chameleon_ready_on_mock_server(mock_ui_server):
    port, _captured = mock_ui_server
    meta = _get_json(f"http://127.0.0.1:{port}/api/meta")
    assert "chameleon" in meta
    assert "ready" in meta["chameleon"]


def test_chameleon_generate_endpoint(mock_ui_server_chameleon):
    port, captured = mock_ui_server_chameleon
    jk = "ai-engineer|linkedin|acme ai|ai engineer"
    status, data = _post_json(
        f"http://127.0.0.1:{port}/api/chameleon/generate",
        {"job_key": jk},
    )
    assert status == 200
    assert data.get("ok") is True
    assert data.get("download_url", "").startswith("/api/chameleon/download")
    assert captured.get("last_chameleon", {}).get("job_key")
    job = next(j for j in (data.get("snapshot") or {}).get("jobs", []) if j["job_key"] == jk)
    assert job["chameleon"]["generated"] is True


def test_chameleon_generate_needs_setup(mock_ui_server_chameleon_not_ready):
    port, _captured = mock_ui_server_chameleon_not_ready
    status, data = _post_json(
        f"http://127.0.0.1:{port}/api/chameleon/generate",
        {"job_key": "ai-engineer|linkedin|acme ai|ai engineer"},
    )
    assert status == 400
    assert data.get("needs_setup") is True


def test_stale_ui_meta_missing_chameleon_regression(mock_ui_server_stale_meta):
    """Old servers (v6) omitted chameleon — UI must not silently look configured."""
    port, _captured = mock_ui_server_stale_meta
    meta = _get_json(f"http://127.0.0.1:{port}/api/meta")
    assert meta.get("version", 0) < 7
    assert "chameleon" not in meta


def test_chameleon_status_endpoint(mock_ui_server):
    port, _captured = mock_ui_server
    status = _get_json(f"http://127.0.0.1:{port}/api/chameleon/status")
    assert "ready" in status
    assert "track_id" in status
