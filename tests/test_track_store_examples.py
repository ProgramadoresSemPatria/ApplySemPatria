"""Track store falls back to committed examples when local tracks/ is absent (CI)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def test_load_email_config_from_examples_when_track_missing(monkeypatch, tmp_path):
    import track_store

    monkeypatch.setattr(track_store, "ROOT", tmp_path)
    manifest = {
        "default_track": "ai-engineer",
        "tracks": {
            "ai-engineer": {
                "label": "AI Engineer",
                "email_config_path": "tracks/ai-engineer/email-apply-config.json",
            }
        },
    }
    (tmp_path / "tracks.json").write_text(__import__("json").dumps(manifest), encoding="utf-8")

    example_dir = tmp_path / "examples" / "tracks" / "ai-engineer"
    example_dir.mkdir(parents=True)
    (example_dir / "email-apply-config.json").write_text(
        '{"sent_log_path": "state/email-applications.json", "email_apply_enabled": false}',
        encoding="utf-8",
    )

    cfg = track_store.load_email_config("ai-engineer")
    assert cfg["sent_log_path"] == "state/email-applications.json"


def test_example_track_path_resolves():
    from track_store import example_track_path

    path = example_track_path("ai-engineer", "email_config_path")
    assert path is not None
    assert path.name == "email-apply-config.json"
    assert path.is_file()
