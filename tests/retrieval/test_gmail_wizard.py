"""Gmail configure wizard non-interactive paths."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from gmail_configure import run_gmail_configure  # noqa: E402


def test_run_gmail_configure_non_interactive_enable(tmp_path, monkeypatch):
    monkeypatch.setattr("track_store.resolve_track", lambda t: "ai-engineer")
    monkeypatch.setattr("track_store.track_label", lambda t: "AI Engineer")
    monkeypatch.setattr("environment_setup.gmail_deps_ok", lambda: True)
    monkeypatch.setattr("environment_setup.gmail_auth_ok", lambda: True)
    monkeypatch.setattr("environment_setup.install_deps", lambda **k: (True, []))
    monkeypatch.setattr("gmail_configure._step_confirm_message", lambda *a, **k: True)
    monkeypatch.setattr("gmail_configure._step_send_mode", lambda *a, **k: "manual")
    monkeypatch.setattr("gmail_configure.set_email_preferences", lambda *a, **k: None)
    monkeypatch.setattr(
        "gmail_configure.load_email_config_raw",
        lambda tid: {
            "sender_email": "t@gmail.com",
            "body_template_file": str(tmp_path / "body.txt"),
            "resume_path": str(tmp_path / "r.pdf"),
            "subject_template": "Application for {role}",
        },
    )
    (tmp_path / "body.txt").write_text("Hi {role}", encoding="utf-8")
    (tmp_path / "r.pdf").write_bytes(b"%PDF")
    monkeypatch.setattr("gmail_configure.preview_application_email", lambda tid, **k: {"to": "t@gmail.com", "subject": "S", "body": "B", "template_file": "x"})

    args = SimpleNamespace(
        track=None,
        status=False,
        preview=False,
        disable=False,
        non_interactive=True,
        yes=True,
        enable=True,
        enable_gmail=False,
        email_mode="smtp",
        gmail_app_password="abcd efgh ijkl mnop",
        gmail_credentials=None,
        apply_mode=None,
        confirm_message=True,
    )
    assert run_gmail_configure(args) == 0
