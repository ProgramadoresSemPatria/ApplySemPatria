"""Gmail configuration for email apply — onboarding + `jobsearch configure gmail`."""

from __future__ import annotations

import getpass
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
GMAIL_INSTRUCTIONS = ROOT / "prompts" / "gmail-app-password-setup.txt"
SAMPLE_ROLE = "Senior AI Engineer"

EmailApplyMode = Literal["manual", "automatic"]


def _save_gmail_app_password(password: str) -> Path:
    from environment_setup import GMAIL_APP_PASSWORD_FILE  # noqa: WPS433

    GMAIL_APP_PASSWORD_FILE.parent.mkdir(parents=True, exist_ok=True)
    GMAIL_APP_PASSWORD_FILE.write_text(password.strip() + "\n", encoding="utf-8")
    try:
        import os

        os.chmod(GMAIL_APP_PASSWORD_FILE, 0o600)
    except OSError:
        pass
    return GMAIL_APP_PASSWORD_FILE


def load_email_config_raw(track_id: str) -> dict[str, Any]:
    from track_store import load_email_config, track_path  # noqa: WPS433

    cfg = load_email_config(track_id)
    defaults = {
        "email_apply_enabled": False,
        "email_apply_mode": "manual",
        "email_message_confirmed": False,
    }
    for key, val in defaults.items():
        cfg.setdefault(key, val)
    return cfg


def save_email_config(track_id: str, cfg: dict[str, Any]) -> None:
    from track_store import track_path  # noqa: WPS433

    path = track_path(track_id, "email_config_path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def set_email_preferences(
    track_id: str,
    *,
    enabled: bool | None = None,
    mode: EmailApplyMode | None = None,
    message_confirmed: bool | None = None,
) -> dict[str, Any]:
    cfg = load_email_config_raw(track_id)
    if enabled is not None:
        cfg["email_apply_enabled"] = enabled
    if mode is not None:
        cfg["email_apply_mode"] = mode
    if message_confirmed is not None:
        cfg["email_message_confirmed"] = message_confirmed
    save_email_config(track_id, cfg)
    return cfg


def print_gmail_instructions() -> None:
    if GMAIL_INSTRUCTIONS.exists():
        print(GMAIL_INSTRUCTIONS.read_text(encoding="utf-8"))
    else:
        print("  See playbooks/gmail-email-apply-setup.md for Gmail setup instructions.")


def preview_application_email(track_id: str, *, sample_role: str = SAMPLE_ROLE) -> dict[str, str]:
    from email_apply import build_message, test_job  # noqa: WPS433

    cfg = load_email_config_raw(track_id)
    job = test_job()
    job["role"] = sample_role
    preview_to = cfg.get("sender_email") or "you@example.com"
    msg = build_message(cfg, job, preview_to)

    body_part = msg.get_payload()[0]
    charset = body_part.get_content_charset() or "utf-8"
    body_text = body_part.get_payload(decode=True).decode(charset)

    return {
        "to": preview_to,
        "subject": str(msg["Subject"]),
        "body": body_text,
        "template_file": str(cfg.get("body_template_file", "templates/email-application.txt")),
    }


def print_message_preview(track_id: str, *, sample_role: str = SAMPLE_ROLE) -> dict[str, str]:
    preview = preview_application_email(track_id, sample_role=sample_role)
    print("\n  Example application email (resume attached as PDF):\n")
    print(f"  To:      (recruiter email from job post)")
    print(f"  From:    {preview['to']}")
    print(f"  Subject: {preview['subject']}")
    print(f"  Body:\n")
    for line in preview["body"].splitlines():
        print(f"    {line}")
    print(f"\n  Template file: {preview['template_file']}")
    return preview


def _prompt_yes_no(question: str, *, default_yes: bool = False) -> bool:
    hint = "Y/n" if default_yes else "y/N"
    ans = input(f"  {question} [{hint}]: ").strip().lower()
    if not ans:
        return default_yes
    return ans in ("y", "yes")


def _collect_app_password(existing_ok: bool) -> bool:
    from environment_setup import gmail_auth_ok  # noqa: WPS433

    if existing_ok and gmail_auth_ok():
        print("  ✓ Gmail credentials already on disk — keeping them.")
        return True

    print_gmail_instructions()
    print("\n  Paste your 16-character Gmail app password (input hidden):")
    pwd = getpass.getpass("  App password: ").strip().replace(" ", "")
    if not pwd:
        print("  ○ No password entered.")
        return False
    path = _save_gmail_app_password(pwd)
    print(f"  ✓ Saved → {path.relative_to(ROOT)}")
    return True


def _setup_oauth(track_id: str, creds_src: str) -> bool:
    from environment_setup import gmail_deps_ok, install_deps  # noqa: WPS433
    from track_store import load_email_config  # noqa: WPS433

    src = Path(creds_src).expanduser()
    if not src.exists():
        print(f"  ✗ File not found: {src}")
        return False

    cfg = load_email_config(track_id)
    dest_rel = cfg.get("gmail_credentials_path", "secrets/gmail-credentials.json")
    dest = ROOT / dest_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    print(f"  ✓ Credentials → {dest_rel}")

    if not gmail_deps_ok():
        ok, errs = install_deps(gmail=True, browser=False)
        if not ok:
            print(f"  ✗ {errs[0] if errs else 'install failed'}")
            return False

    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "gmail_setup.py"), "--track", track_id],
        cwd=str(ROOT),
    )
    return proc.returncode == 0


def _step_confirm_message(track_id: str, non_interactive: bool, *, force_confirm: bool = False) -> bool:
    print("\n  --- Application email preview ---")
    try:
        print_message_preview(track_id)
    except FileNotFoundError as exc:
        print(f"  ✗ Cannot preview: {exc}")
        return False

    if non_interactive:
        if force_confirm:
            set_email_preferences(track_id, message_confirmed=True)
            print("  ✓ Message marked confirmed (non-interactive).")
            return True
        print("  ○ Message confirmation skipped (non-interactive).")
        return True

    if _prompt_yes_no("Does this application message look correct?", default_yes=True):
        set_email_preferences(track_id, message_confirmed=True)
        print("  ✓ Message confirmed.")
        return True

    print(f"\n  Edit the template, then re-run:")
    print(f"    jobsearch configure gmail --track {track_id} --preview")
    print(f"    jobsearch configure gmail --track {track_id}")
    set_email_preferences(track_id, message_confirmed=False)
    return False


def _step_send_mode(track_id: str, non_interactive: bool, mode_override: str | None) -> EmailApplyMode:
    print("\n  --- How should email applications be sent? ---\n")
    print("  1. Manual — review each role in the UI and tap to send (recommended)")
    print("  2. Automatic — CLI/scripts send emails without manual approval")
    print()

    if mode_override in ("manual", "automatic"):
        mode: EmailApplyMode = mode_override  # type: ignore[assignment]
    elif non_interactive:
        mode = "manual"
        print(f"  Defaulting to manual (non-interactive).")
    else:
        choice = input("  Choice [1]: ").strip() or "1"
        mode = "automatic" if choice == "2" else "manual"

    set_email_preferences(track_id, mode=mode)
    if mode == "manual":
        print("  ✓ Manual mode — emails only when you approve (UI or explicit CLI --send).")
    else:
        print("  ✓ Automatic mode — jobsearch apply email --send may send without UI review.")
    return mode


def email_send_allowed(
    track_id: str,
    *,
    cli_force: bool = False,
    ui_approved: bool = False,
) -> tuple[bool, str]:
    """Whether CLI batch send is allowed for this track."""
    from environment_setup import gmail_auth_ok  # noqa: WPS433

    cfg = load_email_config_raw(track_id)
    if not cfg.get("email_apply_enabled", False):
        return False, (
            f"Gmail email apply is disabled for {track_id}. "
            f"Enable: jobsearch configure gmail --track {track_id}"
        )
    if not cfg.get("email_message_confirmed", False):
        return False, (
            "Application email message not confirmed. "
            f"Run: jobsearch configure gmail --track {track_id} --preview"
        )
    approved = cli_force or ui_approved or os.environ.get("JOBSEARCH_UI_APPROVED") == "1"
    if cfg.get("email_apply_mode") == "manual" and not approved:
        return False, (
            "Manual send mode — use the applications UI to approve each email, "
            "or pass --force-send to override from CLI."
        )
    if not gmail_auth_ok():
        return False, (
            f"Gmail credentials missing. Run: jobsearch configure gmail --track {track_id}"
        )
    return True, ""


def run_gmail_configure(args: Any) -> int:
    """Interactive or flag-driven Gmail setup. Used by onboarding and configure gmail."""
    from environment_setup import gmail_auth_ok, gmail_deps_ok, install_deps  # noqa: WPS433
    from track_store import resolve_track, track_label  # noqa: WPS433

    tid = resolve_track(getattr(args, "track", None))
    label = track_label(tid)
    non_interactive = getattr(args, "non_interactive", False) or getattr(args, "yes", False)

    if getattr(args, "status", False):
        cfg = load_email_config_raw(tid)
        print(f"Gmail config — {label} ({tid})\n")
        print(f"  email_apply_enabled:    {cfg.get('email_apply_enabled')}")
        print(f"  email_apply_mode:       {cfg.get('email_apply_mode')}")
        print(f"  email_message_confirmed:{cfg.get('email_message_confirmed')}")
        print(f"  gmail_auth_on_disk:     {gmail_auth_ok()}")
        return 0

    if getattr(args, "preview", False):
        print_message_preview(tid)
        return 0

    if getattr(args, "disable", False):
        set_email_preferences(tid, enabled=False)
        print(f"  ✓ Gmail email apply disabled for {label}.")
        print(f"    Re-enable: jobsearch configure gmail --track {tid}")
        return 0

    mode_override = getattr(args, "apply_mode", None)

    # Full wizard
    print("\n" + "-" * 60)
    print(f"  Gmail — email applications ({label})")
    print("-" * 60 + "\n")

    if getattr(args, "enable", False) or getattr(args, "enable_gmail", False):
        want_gmail = True
    elif non_interactive:
        email_mode_flag = getattr(args, "email_mode", None)
        want_gmail = email_mode_flag not in (None, "skip") or bool(getattr(args, "gmail_app_password", None))
        if email_mode_flag == "skip":
            want_gmail = False
    else:
        want_gmail = _prompt_yes_no(
            "Configure Gmail to send applications for email roles?",
            default_yes=False,
        )

    if not want_gmail:
        set_email_preferences(tid, enabled=False, mode="manual", message_confirmed=False)
        print("\n  ○ Gmail email apply left disabled.")
        print(f"    Enable later: jobsearch configure gmail --track {tid}")
        return 0

    if not gmail_deps_ok():
        print("  Installing Gmail packages…")
        ok, errs = install_deps(gmail=True, browser=False)
        if not ok:
            print(f"  ✗ {errs[0] if errs else 'install failed'}")
            return 1

    email_mode = getattr(args, "email_mode", None) or "smtp"
    if non_interactive and email_mode == "ask":
        email_mode = "smtp" if getattr(args, "gmail_app_password", None) else "skip"

    auth_ok = False
    if email_mode == "oauth":
        creds = getattr(args, "gmail_credentials", None) or ""
        if creds:
            auth_ok = _setup_oauth(tid, creds)
        elif not non_interactive:
            creds = input("  Path to OAuth client JSON: ").strip()
            auth_ok = _setup_oauth(tid, creds) if creds else False
    elif email_mode == "smtp" or email_mode != "skip":
        pwd = getattr(args, "gmail_app_password", None) or ""
        if pwd:
            _save_gmail_app_password(pwd)
            auth_ok = True
        else:
            auth_ok = _collect_app_password(existing_ok=gmail_auth_ok())
    else:
        auth_ok = gmail_auth_ok()

    if not auth_ok:
        set_email_preferences(tid, enabled=False)
        print("  ○ Gmail not configured — feature remains disabled.")
        return 0

    set_email_preferences(tid, enabled=True)

    confirmed = _step_confirm_message(
        tid,
        non_interactive,
        force_confirm=getattr(args, "confirm_message", False),
    )
    if not confirmed and not non_interactive:
        print("  ○ Finish template edits, then run configure gmail again.")
        return 0

    _step_send_mode(tid, non_interactive, mode_override)

    print(f"\n  ✓ Gmail configured for {label}.")
    if load_email_config_raw(tid).get("email_apply_mode") == "manual":
        print("  Preview candidates: jobsearch apply email --track", tid, "--list --table-only")
    else:
        print("  Send: jobsearch apply email --track", tid, "--send --smtp")
    return 0
