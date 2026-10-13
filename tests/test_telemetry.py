"""Opt-in telemetry helpers."""

from __future__ import annotations

import json

import pytest

from retrieval.shared import telemetry


@pytest.fixture
def telemetry_paths(tmp_path, monkeypatch):
    sec = tmp_path / "secrets"
    sec.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    cfg = sec / "telemetry.json"
    install = state / "telemetry-install-id"
    monkeypatch.setattr(telemetry, "TELEMETRY_PATH", cfg)
    monkeypatch.setattr(telemetry, "INSTALL_ID_PATH", install)
    monkeypatch.setattr(telemetry, "ROOT", tmp_path)
    return cfg


def test_telemetry_disabled_by_default(telemetry_paths):
    assert telemetry.telemetry_enabled() is False
    assert telemetry.public_config()["enabled"] is False
    assert telemetry.send_event("test") is False


def test_sanitize_strips_urls():
    msg = "fail https://www.linkedin.com/foo bar"
    assert "<url>" in telemetry.sanitize_text(msg)
    assert "linkedin.com" not in telemetry.sanitize_text(msg)


def test_public_config_no_secret(telemetry_paths):
    telemetry_paths.write_text(
        json.dumps(
            {
                "enabled": True,
                "measurement_id": "G-ABC",
                "api_secret": "secret-should-not-leak",
                "firebase_web": {
                    "apiKey": "k",
                    "projectId": "p",
                    "measurementId": "G-ABC",
                },
            }
        ),
        encoding="utf-8",
    )
    pub = telemetry.public_config()
    assert pub["enabled"] is True
    assert "api_secret" not in json.dumps(pub)
    assert pub["firebase_web"]["projectId"] == "p"


def test_install_id_stable(telemetry_paths):
    telemetry_paths.write_text('{"enabled": false}', encoding="utf-8")
    a = telemetry.install_id()
    b = telemetry.install_id()
    assert a == b
    assert len(a) >= 32
