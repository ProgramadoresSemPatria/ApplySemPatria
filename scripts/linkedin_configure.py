"""LinkedIn DM configuration — onboarding + `jobsearch configure linkedin`."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
LINKEDIN_INSTRUCTIONS = ROOT / "prompts" / "linkedin-session-setup.txt"
SAMPLE_ROLE = "Senior AI Engineer"

DmApplyMode = Literal["manual", "automatic"]


def load_linkedin_config_raw(track_id: str) -> dict[str, Any]:
    from track_store import load_linkedin_config  # noqa: WPS433

    cfg = load_linkedin_config(track_id)
    defaults = {
        "dm_apply_enabled": False,
        "dm_apply_mode": "manual",
        "dm_message_confirmed": False,
        "form_link_message_enabled": True,
        "form_link_message_confirmed": False,
    }
    for key, val in defaults.items():
        cfg.setdefault(key, val)
    return cfg


def save_linkedin_config(track_id: str, cfg: dict[str, Any]) -> None:
    from track_store import track_path  # noqa: WPS433

    path = track_path(track_id, "linkedin_config_path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def set_linkedin_preferences(
    track_id: str,
    *,
    enabled: bool | None = None,
    mode: DmApplyMode | None = None,
    message_confirmed: bool | None = None,
    form_link_message_enabled: bool | None = None,
    form_link_message_confirmed: bool | None = None,
) -> dict[str, Any]:
    cfg = load_linkedin_config_raw(track_id)
    if enabled is not None:
        cfg["dm_apply_enabled"] = enabled
    if mode is not None:
        cfg["dm_apply_mode"] = mode
    if message_confirmed is not None:
        cfg["dm_message_confirmed"] = message_confirmed
    if form_link_message_enabled is not None:
        cfg["form_link_message_enabled"] = form_link_message_enabled
    if form_link_message_confirmed is not None:
        cfg["form_link_message_confirmed"] = form_link_message_confirmed
    save_linkedin_config(track_id, cfg)
    return cfg


def print_linkedin_instructions() -> None:
    if LINKEDIN_INSTRUCTIONS.exists():
        print(LINKEDIN_INSTRUCTIONS.read_text(encoding="utf-8"))
    else:
        print("  Run: jobsearch login login   or   jobsearch login import")


SAMPLE_APPLY_URL = "https://lnkd.in/example"


def preview_dm_message(track_id: str, *, sample_role: str = SAMPLE_ROLE) -> dict[str, str]:
    from dm_apply import message_body, pretty_role  # noqa: WPS433
    from track_store import load_profile  # noqa: WPS433

    profile = load_profile(track_id)
    job = {"role": sample_role, "company": "Example Company", "source": "linkedin_posts"}
    body = message_body(job, profile, track_id=track_id)
    return {
        "role": pretty_role(sample_role),
        "body": body,
        "template_field": "tracks/{}/applicant-profile.json → dm_message_template".format(track_id),
    }


def preview_form_link_message(track_id: str, *, sample_role: str = SAMPLE_ROLE) -> dict[str, str]:
    from dm_apply import message_body, pretty_role  # noqa: WPS433
    from track_store import load_profile  # noqa: WPS433

    profile = load_profile(track_id)
    job = {
        "role": sample_role,
        "company": "Example Company",
        "source": "linkedin_posts",
        "apply_url": SAMPLE_APPLY_URL,
    }
    body = message_body(job, profile, track_id=track_id)
    return {
        "role": pretty_role(sample_role),
        "apply_url": SAMPLE_APPLY_URL,
        "body": body,
        "template_field": "tracks/{}/applicant-profile.json → form_link_message_template".format(track_id),
    }


def print_dm_preview(track_id: str, *, sample_role: str = SAMPLE_ROLE) -> dict[str, str]:
    preview = preview_dm_message(track_id, sample_role=sample_role)
    print("\n  Example LinkedIn DM (after connection is accepted, or if already connected):\n")
    print(f"  Role:    {preview['role']}")
    print(f"  Message:\n")
    for line in preview["body"].splitlines():
        print(f"    {line}")
    print(f"\n  Edit template: {preview['template_field']}")
    print("  Policy: connect requests are sent WITHOUT a note; resume is NOT attached.")
    return preview


def print_form_link_preview(track_id: str, *, sample_role: str = SAMPLE_ROLE) -> dict[str, str]:
    preview = preview_form_link_message(track_id, sample_role=sample_role)
    print("\n  Example message for LinkedIn posts with an apply link/form:\n")
    print(f"  Role:      {preview['role']}")
    print(f"  Apply URL: {preview['apply_url']}")
    print(f"  Message:\n")
    for line in preview["body"].splitlines():
        print(f"    {line}")
    print(f"\n  Edit template: {preview['template_field']}")
    print("  Sent after connect is accepted (same as DM-only roles).")
    return preview


def _prompt_yes_no(question: str, *, default_yes: bool = False) -> bool:
    hint = "Y/n" if default_yes else "y/N"
    ans = input(f"  {question} [{hint}]: ").strip().lower()
    if not ans:
        return default_yes
    return ans in ("y", "yes")


def _linkedin_session_ok() -> bool:
    from environment_setup import linkedin_cookies_ok  # noqa: WPS433

    return linkedin_cookies_ok()


def _run_session_action(action: str) -> bool:
    login_sh = SCRIPTS / "linkedin-login.sh"
    if not login_sh.exists():
        print(f"  ✗ Missing {login_sh.name}")
        return False
    print(f"\n  Running LinkedIn {action}…")
    proc = subprocess.run([str(login_sh), action], cwd=str(ROOT))
    if proc.returncode != 0:
        print(f"  ✗ LinkedIn {action} failed.")
        return False
    if _linkedin_session_ok():
        print("  ✓ LinkedIn session saved.")
        return True
    print("  ⚠ Command finished but cookies not found — try again or: jobsearch login status")
    return False


def _step_session_setup(args: Any, non_interactive: bool) -> bool:
    if _linkedin_session_ok():
        print("  ✓ LinkedIn session already on disk — keeping it.")
        return True

    if os.environ.get("JOBSEARCH_SKIP_LINKEDIN") == "1":
        print("  ○ Session setup skipped (JOBSEARCH_SKIP_LINKEDIN=1).")
        return False

    session_mode = getattr(args, "linkedin_mode", None) or "ask"
    if non_interactive:
        if session_mode == "ask":
            session_mode = "skip"
        if getattr(args, "linkedin_login", False):
            session_mode = "login"
        if getattr(args, "linkedin_import", False):
            session_mode = "import"

    if session_mode == "skip":
        print("  ○ No LinkedIn session configured yet.")
        print("    Later: jobsearch configure linkedin --track …")
        return False

    if session_mode == "ask" and not non_interactive:
        print_linkedin_instructions()
        print("\n  How do you want to sign in to LinkedIn?\n")
        print("  1. Skip for now")
        print("  2. Import from Chrome / Brave / Edge (recommended)")
        print("  3. Browser login window")
        choice = input("  Choice [2]: ").strip() or "2"
        session_mode = {"1": "skip", "2": "import", "3": "login"}.get(choice, "import")

    if session_mode == "skip":
        return False
    if session_mode == "import":
        return _run_session_action("import")
    if session_mode == "login":
        return _run_session_action("login")
    return False


def _step_confirm_dm_message(track_id: str, non_interactive: bool, *, force_confirm: bool = False) -> bool:
    print("\n  --- LinkedIn DM message preview ---")
    try:
        print_dm_preview(track_id)
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ Cannot preview: {exc}")
        return False

    if non_interactive:
        if force_confirm:
            set_linkedin_preferences(track_id, message_confirmed=True)
            print("  ✓ DM message marked confirmed (non-interactive).")
            return True
        print("  ○ DM message confirmation skipped (non-interactive).")
        return True

    if _prompt_yes_no("Does this LinkedIn message look correct?", default_yes=True):
        set_linkedin_preferences(track_id, message_confirmed=True)
        print("  ✓ DM message confirmed.")
        return True

    print(f"\n  Edit dm_message_template in tracks/{track_id}/applicant-profile.json")
    print(f"  Then re-run: jobsearch configure linkedin --track {track_id} --preview")
    set_linkedin_preferences(track_id, message_confirmed=False)
    return False


def _step_dm_send_mode(track_id: str, non_interactive: bool, mode_override: str | None) -> DmApplyMode:
    print("\n  --- How should LinkedIn DMs be sent? ---\n")
    print("  1. Manual — review each role in the UI and tap to connect/message (recommended)")
    print("  2. Automatic — CLI/scripts connect/message without manual approval")
    print()

    if mode_override in ("manual", "automatic"):
        mode: DmApplyMode = mode_override  # type: ignore[assignment]
    elif non_interactive:
        mode = "manual"
        print("  Defaulting to manual (non-interactive).")
    else:
        choice = input("  Choice [1]: ").strip() or "1"
        mode = "automatic" if choice == "2" else "manual"

    set_linkedin_preferences(track_id, mode=mode)
    if mode == "manual":
        print("  ✓ Manual mode — DMs only when you approve in the UI (or CLI --force-send).")
    else:
        print("  ✓ Automatic mode — jobsearch apply dm --send may act without UI review.")
    return mode


def _step_confirm_form_link_message(track_id: str, non_interactive: bool, *, force_confirm: bool = False) -> bool:
    cfg = load_linkedin_config_raw(track_id)
    if not cfg.get("form_link_message_enabled", True):
        set_linkedin_preferences(track_id, form_link_message_confirmed=False)
        print("  ○ Form/link recruiter messages disabled — connect only for those roles.")
        return True

    print("\n  --- Form/link recruiter message preview ---")
    try:
        print_form_link_preview(track_id)
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ Cannot preview: {exc}")
        return False

    if non_interactive:
        if force_confirm:
            set_linkedin_preferences(track_id, form_link_message_confirmed=True)
            print("  ✓ Form/link message marked confirmed (non-interactive).")
            return True
        set_linkedin_preferences(track_id, form_link_message_confirmed=True)
        print("  ✓ Form/link message confirmed (non-interactive default).")
        return True

    if _prompt_yes_no("Does this form/link message look correct?", default_yes=True):
        set_linkedin_preferences(track_id, form_link_message_confirmed=True)
        print("  ✓ Form/link message confirmed.")
        return True

    print(f"\n  Edit form_link_message_template in tracks/{track_id}/applicant-profile.json")
    print(f"  Then re-run: jobsearch configure linkedin --track {track_id} --preview-form-link")
    set_linkedin_preferences(track_id, form_link_message_confirmed=False)
    return False


def _step_form_link_message_toggle(track_id: str, non_interactive: bool) -> bool:
    print("\n  --- Apply link / form posts on LinkedIn ---\n")
    print("  For LinkedIn posts that include an apply link or form, we still connect with")
    print("  the recruiter. You can also send a follow-up message after they accept.\n")

    if non_interactive:
        set_linkedin_preferences(track_id, form_link_message_enabled=True)
        print("  ✓ Will send recruiter messages for form/link posts (non-interactive default).")
        return True

    if _prompt_yes_no(
        "Also send a recruiter message for roles with an apply link/form?",
        default_yes=True,
    ):
        set_linkedin_preferences(track_id, form_link_message_enabled=True)
        print("  ✓ Recruiter messages enabled for form/link posts.")
        return True

    set_linkedin_preferences(track_id, form_link_message_enabled=False, form_link_message_confirmed=False)
    print("  ○ Connect only for form/link posts — no follow-up message.")
    return False


def linkedin_connect_allowed(track_id: str, *, cli_force: bool = False) -> tuple[bool, str]:
    from environment_setup import linkedin_cookies_ok  # noqa: WPS433

    cfg = load_linkedin_config_raw(track_id)
    if not cfg.get("dm_apply_enabled", False):
        return False, (
            f"LinkedIn DM apply is disabled for {track_id}. "
            f"Enable: jobsearch configure linkedin --track {track_id}"
        )
    if cfg.get("dm_apply_mode") == "manual" and not cli_force:
        return False, (
            "Manual DM mode — use the applications UI to approve each connect/message, "
            "or pass --force-send to override from CLI."
        )
    if not linkedin_cookies_ok():
        return False, (
            f"LinkedIn session missing. Run: jobsearch configure linkedin --track {track_id}"
        )
    return True, ""


def linkedin_message_allowed(
    track_id: str,
    job: dict[str, Any] | None = None,
    *,
    cli_force: bool = False,
) -> tuple[bool, str]:
    ok, reason = linkedin_connect_allowed(track_id, cli_force=cli_force)
    if not ok:
        return ok, reason

    cfg = load_linkedin_config_raw(track_id)
    from application_channel import has_form_apply, is_linkedin_post  # noqa: WPS433

    form_link_job = bool(
        job and is_linkedin_post(job) and has_form_apply(job)
    )
    if form_link_job:
        if not cfg.get("form_link_message_enabled", True):
            return False, "Form/link recruiter messages are disabled for this track."
        if not cfg.get("form_link_message_confirmed", False):
            return False, (
                "Form/link message not confirmed. "
                f"Run: jobsearch configure linkedin --track {track_id} --preview-form-link"
            )
    elif not cfg.get("dm_message_confirmed", False):
        return False, (
            "LinkedIn DM message not confirmed. "
            f"Run: jobsearch configure linkedin --track {track_id} --preview"
        )
    return True, ""


def linkedin_send_allowed(track_id: str, *, cli_force: bool = False) -> tuple[bool, str]:
    """Backward-compatible alias — checks connect permissions."""
    return linkedin_connect_allowed(track_id, cli_force=cli_force)


def run_linkedin_configure(args: Any) -> int:
    from environment_setup import browser_deps_ok, install_deps, linkedin_cookies_ok  # noqa: WPS433
    from track_store import resolve_track, track_label  # noqa: WPS433

    tid = resolve_track(getattr(args, "track", None))
    label = track_label(tid)
    non_interactive = getattr(args, "non_interactive", False) or getattr(args, "yes", False)

    if getattr(args, "status", False):
        cfg = load_linkedin_config_raw(tid)
        print(f"LinkedIn DM config — {label} ({tid})\n")
        print(f"  dm_apply_enabled:     {cfg.get('dm_apply_enabled')}")
        print(f"  dm_apply_mode:        {cfg.get('dm_apply_mode')}")
        print(f"  dm_message_confirmed:       {cfg.get('dm_message_confirmed')}")
        print(f"  form_link_message_enabled:  {cfg.get('form_link_message_enabled')}")
        print(f"  form_link_message_confirmed:{cfg.get('form_link_message_confirmed')}")
        print(f"  linkedin_session:     {linkedin_cookies_ok()}")
        return 0

    if getattr(args, "preview", False):
        print_dm_preview(tid)
        return 0

    if getattr(args, "preview_form_link", False):
        print_form_link_preview(tid)
        return 0

    if getattr(args, "disable", False):
        set_linkedin_preferences(tid, enabled=False)
        print(f"  ✓ LinkedIn DM apply disabled for {label}.")
        print(f"    Re-enable: jobsearch configure linkedin --track {tid}")
        return 0

    mode_override = getattr(args, "dm_apply_mode", None) or getattr(args, "apply_mode", None)

    print("\n" + "-" * 60)
    print(f"  LinkedIn — DM applications ({label})")
    print("-" * 60 + "\n")

    if os.environ.get("JOBSEARCH_SKIP_LINKEDIN") == "1" and not getattr(args, "enable", False):
        set_linkedin_preferences(tid, enabled=False)
        print("  ○ Skipped (JOBSEARCH_SKIP_LINKEDIN=1).")
        return 0

    if getattr(args, "enable", False) or getattr(args, "enable_linkedin", False):
        want_linkedin = True
    elif non_interactive:
        lm = getattr(args, "linkedin_mode", None)
        want_linkedin = lm not in (None, "skip") or bool(getattr(args, "linkedin_login", False))
        if lm == "skip":
            want_linkedin = False
    else:
        want_linkedin = _prompt_yes_no(
            "Configure LinkedIn to connect with recruiters on posts (DM-only and apply-link/form roles)?",
            default_yes=False,
        )

    if not want_linkedin:
        set_linkedin_preferences(tid, enabled=False, mode="manual", message_confirmed=False)
        print("\n  ○ LinkedIn DM apply left disabled.")
        print(f"    Enable later: jobsearch configure linkedin --track {tid}")
        return 0

    if not browser_deps_ok():
        print("  Installing browser packages (Patchright)…")
        ok, errs = install_deps(gmail=False, browser=True)
        if not ok:
            print(f"  ✗ {errs[0] if errs else 'install failed'}")
            return 1

    session_ok = _step_session_setup(args, non_interactive)
    if not session_ok:
        set_linkedin_preferences(tid, enabled=False)
        print("  ○ LinkedIn session not configured — DM apply remains disabled.")
        print(f"    Finish setup: jobsearch configure linkedin --track {tid}")
        return 0

    set_linkedin_preferences(tid, enabled=True)

    confirmed = _step_confirm_dm_message(
        tid,
        non_interactive,
        force_confirm=getattr(args, "confirm_message", False)
        or getattr(args, "confirm_dm_message", False),
    )
    if not confirmed and not non_interactive:
        print("  ○ Finish message edits, then run configure linkedin again.")
        return 0

    _step_form_link_message_toggle(tid, non_interactive)
    if load_linkedin_config_raw(tid).get("form_link_message_enabled", True):
        form_confirmed = _step_confirm_form_link_message(
            tid,
            non_interactive,
            force_confirm=getattr(args, "confirm_message", False)
            or getattr(args, "confirm_dm_message", False)
            or getattr(args, "confirm_form_link_message", False),
        )
        if not form_confirmed and not non_interactive:
            print("  ○ Finish form/link message edits, then run configure linkedin again.")
            return 0

    _step_dm_send_mode(tid, non_interactive, mode_override)

    print(f"\n  ✓ LinkedIn DM configured for {label}.")
    cfg = load_linkedin_config_raw(tid)
    if cfg.get("dm_apply_mode") == "manual":
        print("  Preview: jobsearch apply dm --track", tid, "--list --table-only")
    else:
        print("  Send:    jobsearch apply dm --track", tid, "--send --table-only")
    return 0
