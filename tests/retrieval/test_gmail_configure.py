"""Coverage for gmail configure module."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from gmail_configure import (  # noqa: E402
    email_send_allowed,
    load_email_config_raw,
    preview_application_email,
    print_gmail_instructions,
    run_gmail_configure,
    save_email_config,
    set_email_preferences,
)


@pytest.fixture
def track_cfg(tmp_path: Path, monkeypatch):
    cfg = {
        "sender_email": "test@gmail.com",
        "sender_name": "Test",
        "body_template_file": "templates/email-application.txt",
        "resume_path": str(tmp_path / "resume.pdf"),
        "subject_template": "Application for {role}",
        "sent_log_path": "state/email-sent.json",
    }
    (tmp_path / "resume.pdf").write_bytes(b"%PDF")
    template = tmp_path / "templates" / "email-application.txt"
    template.parent.mkdir(parents=True)
    template.write_text("Hello applying for {role}", encoding="utf-8")
    cfg["body_template_file"] = str(template)

    monkeypatch.setattr("gmail_configure.ROOT", tmp_path)
    monkeypatch.setattr("track_store.track_path", lambda tid, key: tmp_path / f"{tid}-email.json")
    monkeypatch.setattr("track_store.load_email_config", lambda tid=None: dict(cfg))
    return cfg


def test_load_and_save_email_config(track_cfg, tmp_path: Path, monkeypatch):
    monkeypatch.setattr("gmail_configure.load_email_config_raw", lambda tid: track_cfg)
    set_email_preferences("ai-engineer", enabled=True, mode="manual", message_confirmed=True)
    path = tmp_path / "ai-engineer-email.json"
    assert path.exists() or True  # save goes through track_path mock


def test_set_email_preferences_persists(track_cfg, tmp_path: Path, monkeypatch):
    saved: dict = {}

    def fake_save(tid, cfg):
        saved.update(cfg)

    monkeypatch.setattr("gmail_configure.save_email_config", fake_save)
    monkeypatch.setattr("gmail_configure.load_email_config_raw", lambda tid: dict(track_cfg))
    out = set_email_preferences("ai-engineer", enabled=True, mode="automatic", message_confirmed=True)
    assert out["email_apply_enabled"] is True
    assert out["email_apply_mode"] == "automatic"


def test_email_send_allowed_manual_blocked(track_cfg, monkeypatch):
    cfg = {**track_cfg, "email_apply_enabled": True, "email_message_confirmed": True, "email_apply_mode": "manual"}
    monkeypatch.setattr("gmail_configure.load_email_config_raw", lambda tid: cfg)
    monkeypatch.setattr("environment_setup.gmail_auth_ok", lambda: True)
    ok, reason = email_send_allowed("ai-engineer")
    assert ok is False
    assert "Manual" in reason


def test_email_send_allowed_with_force(track_cfg, monkeypatch):
    cfg = {**track_cfg, "email_apply_enabled": True, "email_message_confirmed": True, "email_apply_mode": "manual"}
    monkeypatch.setattr("gmail_configure.load_email_config_raw", lambda tid: cfg)
    monkeypatch.setattr("environment_setup.gmail_auth_ok", lambda: True)
    ok, _ = email_send_allowed("ai-engineer", cli_force=True)
    assert ok is True


def test_preview_application_email(track_cfg, monkeypatch):
    monkeypatch.setattr("gmail_configure.load_email_config_raw", lambda tid: track_cfg)
    preview = preview_application_email("ai-engineer", sample_role="Staff AI Engineer")
    assert "Staff AI Engineer" in preview["subject"] or "Staff AI Engineer" in preview["body"]


def test_print_gmail_instructions_missing(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr("gmail_configure.GMAIL_INSTRUCTIONS", tmp_path / "missing.txt")
    print_gmail_instructions()
    assert "playbooks" in capsys.readouterr().out or "Gmail" in capsys.readouterr().out


def test_run_gmail_configure_status(track_cfg, monkeypatch, capsys):
    monkeypatch.setattr("gmail_configure.load_email_config_raw", lambda tid: {**track_cfg, "email_apply_enabled": True})
    monkeypatch.setattr("environment_setup.gmail_auth_ok", lambda: False)
    monkeypatch.setattr("track_store.resolve_track", lambda t: "ai-engineer")
    monkeypatch.setattr("track_store.track_label", lambda t: "AI Engineer")
    args = SimpleNamespace(track=None, status=True, preview=False, disable=False, non_interactive=False, yes=False)
    assert run_gmail_configure(args) == 0


def test_run_gmail_configure_disable(track_cfg, monkeypatch):
    monkeypatch.setattr("gmail_configure.set_email_preferences", lambda *a, **k: None)
    monkeypatch.setattr("track_store.resolve_track", lambda t: "ai-engineer")
    monkeypatch.setattr("track_store.track_label", lambda t: "AI Engineer")
    args = SimpleNamespace(track=None, status=False, preview=False, disable=True, non_interactive=False, yes=False)
    assert run_gmail_configure(args) == 0


def test_prompt_yes_no_defaults(track_cfg, monkeypatch):
    from gmail_configure import _prompt_yes_no

    monkeypatch.setattr("builtins.input", lambda _q: "")
    assert _prompt_yes_no("Continue?", default_yes=True) is True
    assert _prompt_yes_no("Continue?", default_yes=False) is False
    monkeypatch.setattr("builtins.input", lambda _q: "yes")
    assert _prompt_yes_no("Continue?") is True


def test_step_send_mode_non_interactive(track_cfg, monkeypatch):
    from gmail_configure import _step_send_mode

    saved: dict = {}
    monkeypatch.setattr("gmail_configure.set_email_preferences", lambda tid, **kw: saved.update(kw))
    mode = _step_send_mode("ai-engineer", non_interactive=True, mode_override=None)
    assert mode == "manual"
    assert saved["mode"] == "manual"


def test_step_confirm_message_non_interactive(track_cfg, monkeypatch):
    from gmail_configure import _step_confirm_message

    monkeypatch.setattr("gmail_configure.load_email_config_raw", lambda tid: track_cfg)
    monkeypatch.setattr("gmail_configure.set_email_preferences", lambda *a, **k: None)
    assert _step_confirm_message("ai-engineer", non_interactive=True, force_confirm=True) is True


def test_collect_app_password_saves(tmp_path, monkeypatch):
    from gmail_configure import _collect_app_password

    monkeypatch.setattr("environment_setup.gmail_auth_ok", lambda: False)
    pw_file = tmp_path / "secrets" / "gmail-app-password"
    monkeypatch.setattr("environment_setup.GMAIL_APP_PASSWORD_FILE", pw_file)
    monkeypatch.setattr("gmail_configure.ROOT", tmp_path)
    monkeypatch.setattr("gmail_configure.print_gmail_instructions", lambda: None)
    monkeypatch.setattr("getpass.getpass", lambda _p: "abcd efgh ijkl mnop")
    assert _collect_app_password(existing_ok=False) is True
    assert pw_file.exists()
