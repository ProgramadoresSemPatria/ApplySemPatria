"""Config UI API tests."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


def _get_json(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


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
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def test_config_get_returns_bundle(mock_ui_server):
    port, _ = mock_ui_server
    status, data = _get_json(f"http://127.0.0.1:{port}/api/config?track=ai-engineer")
    assert status == 200
    assert data["ok"] is True
    cfg = data["config"]
    assert cfg["track_id"] == "ai-engineer"
    assert "profile" in cfg
    assert "linkedin" in cfg
    assert "email" in cfg
    assert cfg["flags"]["job_seeker_reject"] is True


def test_config_post_saves_linkedin_toggle(mock_ui_server):
    port, captured = mock_ui_server
    status, data = _post_json(
        f"http://127.0.0.1:{port}/api/config",
        {
            "track": "ai-engineer",
            "section": "linkedin",
            "payload": {"llm_intent_classify_enabled": True},
        },
    )
    assert status == 200
    assert data["ok"] is True
    saves = captured.get("config_saves") or []
    assert any(s.get("section") == "linkedin" for s in saves)
    assert saves[-1]["payload"].get("llm_intent_classify_enabled") is True
    assert data["config"]["linkedin"]["llm_intent_classify_enabled"] is True


def test_settings_page_served(mock_ui_server):
    port, _ = mock_ui_server
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/settings.html", timeout=5) as resp:
        html = resp.read().decode()
    assert resp.status == 200
    assert "Setup &amp; preferences" in html or "Setup & preferences" in html
    assert "/api/config" in html


def test_config_get_unknown_track_returns_400(mock_ui_server):
    port, _ = mock_ui_server
    status, data = _get_json(f"http://127.0.0.1:{port}/api/config?track=not-a-track")
    assert status == 400
    assert data["ok"] is False


def test_config_post_missing_section_returns_400(mock_ui_server):
    port, _ = mock_ui_server
    status, data = _post_json(
        f"http://127.0.0.1:{port}/api/config",
        {"track": "ai-engineer", "payload": {"llm_intent_classify_enabled": True}},
    )
    assert status == 400
    assert "section" in (data.get("message") or "").lower()


def test_config_post_unknown_section_returns_400(mock_ui_server):
    port, _ = mock_ui_server
    status, data = _post_json(
        f"http://127.0.0.1:{port}/api/config",
        {"track": "ai-engineer", "section": "bogus", "payload": {}},
    )
    assert status == 400
    assert data["ok"] is False


def test_config_get_includes_previews_and_flags(mock_ui_server):
    port, _ = mock_ui_server
    _status, data = _get_json(f"http://127.0.0.1:{port}/api/config?track=ai-engineer")
    cfg = data["config"]
    assert "previews" in cfg
    assert "dm_message" in cfg["previews"]
    assert cfg["linkedin"]["llm_intent_model"]
    assert isinstance(cfg["form_answers"]["rules"], list)
