#!/usr/bin/env python3
"""Smoke tests for environment setup (no Docker required)."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from environment_setup import (  # noqa: E402
    GMAIL_APP_PASSWORD_FILE,
    MIN_PYTHON,
    gmail_auth_ok,
    python_version_ok,
)


def test_python_version_meets_minimum():
    ok, _ = python_version_ok()
    assert ok, f"Need Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ for tests"


def test_gmail_auth_detects_app_password_file(tmp_path, monkeypatch):
    monkeypatch.setattr("environment_setup.ROOT", tmp_path)
    monkeypatch.setattr("environment_setup.GMAIL_APP_PASSWORD_FILE", tmp_path / "secrets" / "pw")
    pw = tmp_path / "secrets" / "pw"
    pw.parent.mkdir(parents=True)
    pw.write_text("secret\n")
    assert gmail_auth_ok() is True


def test_onboarding_module_imports():
    import onboarding_flow  # noqa: F401

    assert hasattr(onboarding_flow, "run_onboarding")


def test_gmail_configure_manual_mode_blocks_cli_send():
    from gmail_configure import email_send_allowed, set_email_preferences  # noqa: E402

    set_email_preferences("ai-engineer", enabled=True, message_confirmed=True, mode="manual")
    ok, reason = email_send_allowed("ai-engineer", cli_force=False)
    assert ok is False
    assert "manual" in reason.lower()


def test_linkedin_configure_manual_mode_blocks_cli_send():
    from linkedin_configure import linkedin_send_allowed, set_linkedin_preferences  # noqa: E402

    set_linkedin_preferences("ai-engineer", enabled=True, message_confirmed=True, mode="manual")
    ok, reason = linkedin_send_allowed("ai-engineer", cli_force=False)
    assert ok is False
    assert "manual" in reason.lower()


def test_linkedin_configure_disabled_blocks_send():
    from linkedin_configure import linkedin_send_allowed, set_linkedin_preferences  # noqa: E402

    set_linkedin_preferences("ai-engineer", enabled=False)
    ok, reason = linkedin_send_allowed("ai-engineer")
    assert ok is False
    assert "disabled" in reason.lower()


def test_linkedin_configure_preview():
    from linkedin_configure import preview_dm_message, preview_form_link_message  # noqa: E402

    preview = preview_dm_message("ai-engineer")
    assert "body" in preview
    assert len(preview["body"]) > 10

    form_preview = preview_form_link_message("ai-engineer")
    assert "apply_url" in form_preview
    assert "lnkd.in" in form_preview["body"] or "example" in form_preview["apply_url"]
