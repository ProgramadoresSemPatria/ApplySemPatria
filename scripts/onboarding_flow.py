"""First-run onboarding for a single career track."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent

PROFILE_FIELDS: list[tuple[str, str, bool]] = [
    ("full_name", "Full name", True),
    ("email", "Email", True),
    ("phone", "Phone", True),
    ("linkedin_url", "LinkedIn profile URL", True),
    ("resume_path", "Resume PDF (full path)", True),
    ("current_title", "Current job title", True),
    ("location", "Location (city, country)", False),
    ("years_experience", "Years of experience", False),
    ("notice_period", "Notice period / availability", False),
    ("work_authorization", "Work authorization (one line)", False),
]

FRESH_PROFILE: dict[str, Any] = {
    "full_name": "",
    "first_name": "",
    "last_name": "",
    "email": "",
    "phone": "",
    "location": "",
    "country": "",
    "city": "",
    "timezone": "",
    "linkedin_url": "",
    "github_url": "",
    "portfolio_url": "",
    "current_title": "",
    "years_experience": "",
    "work_authorization": "",
    "requires_sponsorship": "No",
    "remote_ok": "Yes",
    "salary_expectation_usd": "",
    "salary_period": "monthly",
    "notice_period": "",
    "resume_path": "",
    "dm_message_template": (
        "Hi I hope you're doing well! I'm contacting you because I have the "
        "qualifications for the {role} Role you published and I'd like to know next steps"
    ),
    "form_link_message_template": (
        "Hi I hope you're doing well! I'm contacting you about the {role} role you shared. "
        "I've applied via your link ({apply_url}) and would love to know the next steps."
    ),
}


def _banner(track_label: str, track_id: str) -> None:
    print()
    print("=" * 60)
    print("  jobsearch onboarding")
    print(f"  Track: {track_label} ({track_id})")
    print("=" * 60)
    print()
    print("This walkthrough sets up everything for ONE career track:")
    print("  1. Python + dependencies")
    print("  2. Profile + resume")
    print("  3. Gmail + application message + send mode")
    print("  4. LinkedIn session + recruiter connect/message + form/link message")
    print("  5. (Optional) CV Chameleon — jobsearch chameleon setup --track …")
    print()


def _split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split(None, 1)
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def _validate_resume(path_str: str) -> str:
    path = Path(path_str).expanduser()
    if not path_str.strip():
        raise ValueError("Resume path is required.")
    if not path.exists():
        raise ValueError(f"Resume file not found: {path}")
    if path.suffix.lower() != ".pdf":
        print(f"  ⚠ Warning: expected a PDF; got {path.suffix or 'unknown extension'}")
    return str(path.resolve())


def _prompt_field(key: str, label: str, current: str, *, required: bool) -> str:
    hint = f" [{current}]" if current else ""
    while True:
        val = input(f"  {label}{hint}: ").strip()
        if not val:
            if current:
                return current
            if required:
                print("    → required — please enter a value.")
                continue
            return ""
        if key == "resume_path":
            try:
                return _validate_resume(val)
            except ValueError as exc:
                print(f"    → {exc}")
                continue
        return val


def _apply_cli_overrides(data: dict[str, Any], args: Any) -> dict[str, Any]:
    mapping = {
        "full_name": getattr(args, "full_name", None),
        "email": getattr(args, "email", None),
        "phone": getattr(args, "phone", None),
        "linkedin_url": getattr(args, "linkedin_url", None),
        "current_title": getattr(args, "current_title", None),
        "location": getattr(args, "location", None),
        "years_experience": getattr(args, "years_experience", None),
        "notice_period": getattr(args, "notice_period", None),
        "work_authorization": getattr(args, "work_authorization", None),
    }
    for key, val in mapping.items():
        if val:
            data[key] = val
    resume = getattr(args, "resume", None) or getattr(args, "resume_path", None)
    if resume:
        data["resume_path"] = _validate_resume(resume)
    return data


def _sync_email_config(track_id: str, profile: dict[str, Any]) -> None:
    from track_store import load_email_config, track_path  # noqa: WPS433

    email_path = track_path(track_id, "email_config_path")
    cfg = load_email_config(track_id)
    cfg["sender_email"] = profile.get("email") or cfg.get("sender_email", "")
    cfg["sender_name"] = profile.get("full_name") or cfg.get("sender_name", "")
    cfg["resume_path"] = profile.get("resume_path") or cfg.get("resume_path", "")
    cfg["linkedin_url"] = profile.get("linkedin_url") or cfg.get("linkedin_url", "")
    cfg["location"] = profile.get("location") or cfg.get("location", "")
    email_path.parent.mkdir(parents=True, exist_ok=True)
    email_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _set_default_track(track_id: str) -> None:
    from track_store import load_manifest  # noqa: WPS433

    manifest_path = ROOT / "tracks.json"
    manifest = load_manifest()
    manifest["default_track"] = track_id
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _step_profile(args: Any, tid: str, data: dict[str, Any], non_interactive: bool) -> tuple[dict[str, Any], int]:
    from track_store import track_label  # noqa: WPS433

    print("\n" + "-" * 60)
    print(f"  Step 2/4 — Profile + resume ({track_label(tid)})")
    print("-" * 60 + "\n")

    if getattr(args, "reset", False):
        print("  ↺ Resetting profile to empty template…\n")
        data = dict(FRESH_PROFILE)

    if non_interactive:
        print("Mode: non-interactive (using flags + existing values)\n")
        data = _apply_cli_overrides(data, args)
        if not data.get("resume_path"):
            print("ERROR: --resume PATH is required for non-interactive onboarding.")
            return data, 1
        try:
            data["resume_path"] = _validate_resume(str(data["resume_path"]))
        except ValueError as exc:
            print(f"ERROR: {exc}")
            return data, 1
    else:
        print("Answer each prompt (press Enter to keep the value in [brackets]).\n")
        for key, field_label, required in PROFILE_FIELDS:
            current = str(data.get(key, "") or "")
            data[key] = _prompt_field(key, field_label, current, required=required)

    first, last = _split_name(str(data.get("full_name", "")))
    if first:
        data["first_name"] = first
    if last:
        data["last_name"] = last

    from profile_store import missing  # noqa: WPS433
    from track_store import save_profile  # noqa: WPS433

    print("\nSaving profile…")
    save_profile(tid, data)
    _sync_email_config(tid, data)
    _set_default_track(tid)
    print(f"  ✓ tracks/{tid}/applicant-profile.json")
    print(f"  ✓ tracks/{tid}/email-apply-config.json (resume + sender synced)")
    print(f"  ✓ default track → {tid}")

    miss = missing(tid)
    if miss:
        print(f"\n  Optional fields still empty: {', '.join(miss)}")
    return data, 0


def _step_email(args: Any, tid: str, profile: dict[str, Any], non_interactive: bool) -> int:
    from gmail_configure import run_gmail_configure  # noqa: WPS433

    print("\n" + "-" * 60)
    print("  Step 3/4 — Email applications (Gmail)")
    print("-" * 60)

    return run_gmail_configure(args)


def _step_linkedin(args: Any, tid: str, non_interactive: bool) -> int:
    from linkedin_configure import run_linkedin_configure  # noqa: WPS433

    print("\n" + "-" * 60)
    print("  Step 4/4 — LinkedIn recruiter outreach")
    print("-" * 60)

    return run_linkedin_configure(args)


def _final_report(tid: str) -> None:
    from profile_store import missing  # noqa: WPS433
    from track_readiness import assess_track  # noqa: WPS433
    from track_store import track_label  # noqa: WPS433
    from environment_setup import gmail_auth_ok, linkedin_cookies_ok  # noqa: WPS433
    from gmail_configure import load_email_config_raw  # noqa: WPS433
    from linkedin_configure import load_linkedin_config_raw  # noqa: WPS433

    label = track_label(tid)
    miss = missing(tid)
    email_cfg = load_email_config_raw(tid)
    li_cfg = load_linkedin_config_raw(tid)

    print("\n" + "-" * 60)
    print("  Readiness check")
    print("-" * 60 + "\n")

    for op_name, title in [
        ("discover", "Discover jobs (boards)"),
        ("apply_email", "Email apply"),
        ("apply_dm", "LinkedIn DM apply"),
    ]:
        r = assess_track(tid, op_name)  # type: ignore[arg-type]
        print(f"  {title}: {r.summary_line()}")

    print()
    if li_cfg.get("dm_apply_enabled") and linkedin_cookies_ok():
        dm_mode = li_cfg.get("dm_apply_mode", "manual")
        print(f"  LinkedIn DM:      ✓ enabled ({dm_mode} mode)")
    elif linkedin_cookies_ok():
        print("  LinkedIn DM:      ○ session saved but DM apply disabled")
    else:
        print("  LinkedIn DM:      ○ disabled — jobsearch configure linkedin --track", tid)
    if email_cfg.get("email_apply_enabled") and gmail_auth_ok():
        mode = email_cfg.get("email_apply_mode", "manual")
        print(f"  Gmail send:       ✓ enabled ({mode} mode)")
    elif gmail_auth_ok():
        print("  Gmail send:       ○ credentials saved but email apply disabled")
    else:
        print("  Gmail send:       ○ disabled — jobsearch configure gmail --track", tid)

    if miss:
        print(f"\n  Optional profile fields still empty: {', '.join(miss)}")

    print("\n" + "=" * 60)
    print(f"  You're set up for {label}. Next steps:")
    print("=" * 60)
    print(f"""
  1. Find jobs (boards):
     jobsearch discover --track {tid} --since 7d

  2. Build your apply table:
     jobsearch table

  3. Preview email candidates:
     jobsearch apply email --track {tid} --list --table-only

  4. LinkedIn posts (browser):
     ~/job-search/scripts/linkedin-deep-collect.sh --all-queries --merge --since 7d

  Re-check anytime:
     jobsearch doctor
""")


def run_onboarding(args: Any) -> int:
    from environment_setup import run_install_step  # noqa: WPS433
    from track_store import load_profile, resolve_track, track_label  # noqa: WPS433

    tid = resolve_track(args.track)
    label = track_label(tid)
    _banner(label, tid)

    non_interactive = getattr(args, "non_interactive", False) or getattr(args, "yes", False)
    skip_install = getattr(args, "skip_install", False)
    install_browser = getattr(args, "install_browser", False)

    code = run_install_step(
        gmail=True,
        browser=install_browser,
        skip=skip_install,
        quiet=non_interactive,
    )
    if code != 0:
        return code

    data = load_profile(tid)
    data, code = _step_profile(args, tid, data, non_interactive)
    if code != 0:
        return code

    code = _step_email(args, tid, data, non_interactive)
    if code != 0:
        return code

    code = _step_linkedin(args, tid, non_interactive)
    if code != 0:
        return code

    _final_report(tid)
    return 0
