#!/usr/bin/env python3
"""Job search CLI — discover, table, apply across career tracks.

Incomplete tracks are reported during execution; complete tracks proceed.

Install (dev):
  alias jobsearch='python3 ~/job-search/scripts/jobsearch.py'
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

PY = sys.executable


def _run(script: str, *args: str) -> int:
    cmd = [PY, str(SCRIPTS / script), *args]
    return subprocess.call(cmd, cwd=str(ROOT))


def _resolve_track_scope(args: argparse.Namespace) -> list[str] | None:
    from track_store import default_track_id, list_track_ids, resolve_track  # noqa: WPS433

    if getattr(args, "all_tracks", False):
        return list_track_ids()
    if getattr(args, "track", None):
        return [resolve_track(args.track)]
    return [default_track_id()]


def cmd_tracks_list(_: argparse.Namespace) -> int:
    from track_readiness import assess_all  # noqa: WPS433
    from track_store import list_track_ids, track_label  # noqa: WPS433

    print(f"{'Track':<22} {'Label':<20} {'Discover':<10} {'Apply'}")
    print("-" * 70)
    for tid in list_track_ids():
        disc = next(r for r in assess_all("discover") if r.track_id == tid)
        email = next(r for r in assess_all("apply_email") if r.track_id == tid)
        d = "ready" if disc.can_proceed else "blocked"
        a = "ready" if email.can_send else ("list only" if email.can_proceed else "blocked")
        print(f"{tid:<22} {track_label(tid):<20} {d:<10} {a}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from track_readiness import assess_all  # noqa: WPS433

    print(f"Job search doctor — {ROOT}\n")

    if not (ROOT / "tracks.json").exists():
        print("✗ tracks.json missing")
        return 1
    print("✓ tracks.json")

    cookies = Path.home() / ".linkedin-mcp" / "cookies.json"
    print("✓ LinkedIn cookies" if cookies.exists() else "○ LinkedIn cookies missing")

    gmail = ROOT / "state" / "gmail-token.json"
    smtp = os.environ.get("GMAIL_APP_PASSWORD")
    smtp_file = (ROOT / "secrets" / "gmail-app-password").exists()
    print("✓ Gmail ready" if gmail.exists() or smtp or smtp_file else "○ Gmail not configured")

    any_ready_apply = False
    for op, title in [("discover", "Discover"), ("apply_email", "Email apply"), ("apply_dm", "DM apply")]:
        print(f"\n{title}:")
        for r in assess_all(op):  # type: ignore[arg-type]
            print(f"  {r.summary_line()}")
            if op.startswith("apply") and r.can_send:
                any_ready_apply = True

    if args.json:
        reports = {
            op: [r.__dict__ for r in assess_all(op)]  # type: ignore[arg-type]
            for op in ("discover", "apply_email", "apply_dm")
        }
        print(json.dumps(reports, indent=2))
        return 0

    print("\nDiscover/table always run for configured tracks.")
    print("Apply --send only runs tracks marked ready above.")
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    print("Tip: use `jobsearch onboarding --track …` for the full first-run flow.\n")
    from track_store import load_profile, resolve_track, save_profile, track_label  # noqa: WPS433

    tid = resolve_track(args.track)
    print(f"Setup track: {track_label(tid)} ({tid})\n")
    data = load_profile(tid)
    prompts = [
        ("full_name", "Full name"),
        ("email", "Email"),
        ("phone", "Phone"),
        ("linkedin_url", "LinkedIn profile URL"),
        ("resume_path", "Resume PDF path"),
        ("current_title", "Current title"),
    ]
    for key, label in prompts:
        current = str(data.get(key, "") or "")
        hint = f" [{current}]" if current else ""
        val = input(f"{label}{hint}: ").strip()
        if val:
            data[key] = val
    save_profile(tid, data)
    print(f"\nSaved → tracks/{tid}/applicant-profile.json")
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    from track_readiness import print_readiness_report, ready_track_ids  # noqa: WPS433

    scope = _resolve_track_scope(args)
    print_readiness_report("discover", track_ids=scope)
    ready = ready_track_ids("discover", track_ids=scope)
    if not ready:
        print("Nothing to discover — fix blocked tracks above.")
        return 1

    exit_code = 0
    for tid in ready:
        print(f"Discovering: {tid} …")
        argv = ["--since", args.since, "--track", tid]
        if args.dry_run:
            argv.append("--dry-run")
        if args.json:
            argv.append("--json")
        code = _run("discover.py", *argv)
        if code != 0:
            exit_code = code
    return exit_code


def cmd_table(args: argparse.Namespace) -> int:
    from track_readiness import print_readiness_report  # noqa: WPS433

    scope = _resolve_track_scope(args) if args.track else None
    print_readiness_report("table", track_ids=scope)
    argv: list[str] = []
    if args.track:
        argv.extend(["--track", args.track])
    return _run("generate_applications.py", *argv)


def cmd_apply(args: argparse.Namespace) -> int:
    from track_readiness import print_readiness_report, ready_track_ids  # noqa: WPS433
    from track_store import track_label  # noqa: WPS433

    channel = args.channel
    op = {"email": "apply_email", "dm": "apply_dm", "url": "apply_url"}.get(channel, "apply_email")
    scope = _resolve_track_scope(args)
    for_send = bool(args.send)

    print_readiness_report(op, for_send=for_send, track_ids=scope)  # type: ignore[arg-type]
    ready = ready_track_ids(op, for_send=for_send, track_ids=scope)  # type: ignore[arg-type]

    if not ready:
        if for_send:
            print("No tracks ready to send. Fix blockers above or use --list to preview.")
        else:
            print("No tracks available. Fix blockers above.")
        return 1

    if channel == "url":
        print("URL apply: use url_apply.py apply --url URL --track TRACK directly")
        return 0

    script = {"email": "email_apply.py", "dm": "dm_apply.py"}[channel]
    exit_code = 0
    for tid in ready:
        print(f"{'=' * 60}\n{track_label(tid)} ({tid})\n{'=' * 60}")
        argv: list[str] = ["--track", tid]
        if args.list:
            argv.append("--list")
        if args.dry_run and channel == "email":
            argv.append("--dry-run")
        if args.send:
            argv.append("--send")
        if args.table_only:
            argv.append("--table-only")
        if args.limit:
            argv.extend(["--limit", str(args.limit)])
        if channel == "email" and args.smtp:
            argv.append("--smtp")
        if channel == "email" and args.force_send:
            argv.append("--force-send")
        if channel == "dm" and args.force_send:
            argv.append("--force-send")
        print(flush=True)
        code = _run(script, *argv)
        if code != 0:
            exit_code = code
    return exit_code


def cmd_onboarding(args: argparse.Namespace) -> int:
    from onboarding_flow import run_onboarding  # noqa: WPS433

    return run_onboarding(args)


def cmd_install(args: argparse.Namespace) -> int:
    from environment_setup import install_deps, print_environment_report, run_install_step  # noqa: WPS433

    if args.check_only:
        print(f"Job search environment — {ROOT}\n")
        print_environment_report()
        return 0
    return run_install_step(
        gmail=not args.no_gmail,
        browser=args.browser,
        skip=False,
        quiet=args.quiet,
    )


def cmd_configure_gmail(args: argparse.Namespace) -> int:
    from gmail_configure import run_gmail_configure  # noqa: WPS433

    return run_gmail_configure(args)


def cmd_configure_linkedin(args: argparse.Namespace) -> int:
    from linkedin_configure import run_linkedin_configure  # noqa: WPS433

    return run_linkedin_configure(args)


def cmd_ui(args: argparse.Namespace) -> int:
    if getattr(args, "build", False):
        return _run("generate_applications.py")
    from ui_server import serve  # noqa: WPS433

    return serve(port=args.port, open_browser=None if args.no_open else args.browser)


def cmd_login(args: argparse.Namespace) -> int:
    if args.action == "gmail":
        return _run("gmail_setup.py", "--track", args.track or "ai-engineer")
    script = SCRIPTS / "linkedin-login.sh"
    return subprocess.call([str(script), args.action])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobsearch",
        description="Multi-track job search — warns on incomplete tracks, proceeds with ready ones",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    t = sub.add_parser("tracks", help="List career tracks and readiness")
    t_sub = t.add_subparsers(dest="tracks_cmd", required=True)
    t_list = t_sub.add_parser("list")
    t_list.set_defaults(func=cmd_tracks_list)

    doc = sub.add_parser("doctor", help="Full readiness report")
    doc.add_argument("--json", action="store_true")
    doc.set_defaults(func=cmd_doctor)

    setup = sub.add_parser("setup", help="Quick profile edit (prefer: onboarding)")
    setup.add_argument("--track", required=True)
    setup.set_defaults(func=cmd_setup)

    onboard = sub.add_parser(
        "onboarding",
        help="First-run setup for one track (profile + resume + email config)",
    )
    onboard.add_argument("--track", default="ai-engineer", help="Track id (default: ai-engineer)")
    onboard.add_argument("--resume", dest="resume", help="Resume PDF path")
    onboard.add_argument("--full-name", dest="full_name")
    onboard.add_argument("--email")
    onboard.add_argument("--phone")
    onboard.add_argument("--linkedin-url", dest="linkedin_url")
    onboard.add_argument("--current-title", dest="current_title")
    onboard.add_argument("--location")
    onboard.add_argument("--years-experience", dest="years_experience")
    onboard.add_argument("--notice-period", dest="notice_period")
    onboard.add_argument("--work-authorization", dest="work_authorization")
    onboard.add_argument("--yes", action="store_true", help="Non-interactive mode")
    onboard.add_argument("--non-interactive", action="store_true", help="Same as --yes")
    onboard.add_argument("--reset", action="store_true", help="Clear profile first (fresh install)")
    onboard.add_argument("--skip-install", action="store_true", help="Skip venv/deps step")
    onboard.add_argument("--install-browser", action="store_true", help="Install Patchright Chromium")
    onboard.add_argument(
        "--email-mode",
        choices=["skip", "smtp", "oauth", "ask"],
        default=None,
        help="Gmail setup (default: ask interactively, skip with --yes)",
    )
    onboard.add_argument("--gmail-app-password", dest="gmail_app_password", help="SMTP app password")
    onboard.add_argument("--gmail-credentials", dest="gmail_credentials", help="OAuth client JSON path")
    onboard.add_argument("--linkedin-login", action="store_true", help="Open LinkedIn login during onboarding")
    onboard.add_argument(
        "--apply-mode",
        choices=["manual", "automatic"],
        default=None,
        help="Email send mode when Gmail is enabled",
    )
    onboard.add_argument("--confirm-message", action="store_true", help="Confirm email template (non-interactive)")
    onboard.add_argument("--enable-gmail", action="store_true", help="Enable Gmail in non-interactive mode")
    onboard.add_argument(
        "--linkedin-mode",
        choices=["skip", "login", "import", "ask"],
        default=None,
        help="LinkedIn session (default: ask; skip with --yes)",
    )
    onboard.add_argument("--linkedin-import", action="store_true", help="Import LinkedIn from browser")
    onboard.add_argument("--enable-linkedin", action="store_true", help="Enable LinkedIn DM in non-interactive mode")
    onboard.add_argument(
        "--dm-apply-mode",
        choices=["manual", "automatic"],
        default=None,
        help="LinkedIn DM send mode when enabled",
    )
    onboard.add_argument("--confirm-dm-message", action="store_true", help="Confirm DM template (non-interactive)")
    onboard.set_defaults(func=cmd_onboarding)

    cfg = sub.add_parser("configure", help="Configure integrations (Gmail, …)")
    cfg_sub = cfg.add_subparsers(dest="configure_cmd", required=True)
    gmail_cfg = cfg_sub.add_parser("gmail", help="Enable/disable Gmail and set send mode")
    gmail_cfg.add_argument("--track", default="ai-engineer")
    gmail_cfg.add_argument("--enable", action="store_true", help="Skip enable question (yes)")
    gmail_cfg.add_argument("--disable", action="store_true", help="Turn off email apply for this track")
    gmail_cfg.add_argument("--preview", action="store_true", help="Show application email preview")
    gmail_cfg.add_argument("--status", action="store_true", help="Show current Gmail settings")
    gmail_cfg.add_argument("--yes", action="store_true", help="Non-interactive")
    gmail_cfg.add_argument("--non-interactive", action="store_true")
    gmail_cfg.add_argument("--email-mode", choices=["skip", "smtp", "oauth"], default=None)
    gmail_cfg.add_argument("--gmail-app-password", dest="gmail_app_password")
    gmail_cfg.add_argument("--gmail-credentials", dest="gmail_credentials")
    gmail_cfg.add_argument("--apply-mode", choices=["manual", "automatic"], default=None)
    gmail_cfg.add_argument("--confirm-message", action="store_true")
    gmail_cfg.set_defaults(func=cmd_configure_gmail)

    li_cfg = cfg_sub.add_parser("linkedin", help="Enable/disable LinkedIn DM and set send mode")
    li_cfg.add_argument("--track", default="ai-engineer")
    li_cfg.add_argument("--enable", action="store_true", help="Skip enable question (yes)")
    li_cfg.add_argument("--disable", action="store_true", help="Turn off DM apply for this track")
    li_cfg.add_argument("--preview", action="store_true", help="Show DM message preview")
    li_cfg.add_argument(
        "--preview-form-link",
        action="store_true",
        help="Show recruiter message preview for apply-link/form posts",
    )
    li_cfg.add_argument("--status", action="store_true", help="Show current LinkedIn DM settings")
    li_cfg.add_argument("--yes", action="store_true", help="Non-interactive")
    li_cfg.add_argument("--non-interactive", action="store_true")
    li_cfg.add_argument(
        "--linkedin-mode",
        choices=["skip", "login", "import"],
        default=None,
        help="Session setup method",
    )
    li_cfg.add_argument("--linkedin-login", action="store_true")
    li_cfg.add_argument("--linkedin-import", action="store_true")
    li_cfg.add_argument("--dm-apply-mode", choices=["manual", "automatic"], default=None)
    li_cfg.add_argument("--apply-mode", choices=["manual", "automatic"], default=None)
    li_cfg.add_argument("--confirm-message", action="store_true")
    li_cfg.add_argument("--confirm-dm-message", action="store_true")
    li_cfg.set_defaults(func=cmd_configure_linkedin)

    ui = sub.add_parser("ui", help="Open applications dashboard in browser")
    ui.add_argument("--port", type=int, default=8765)
    ui.add_argument("--build", action="store_true", help="Regenerate table + JSON snapshot first")
    ui.add_argument("--no-open", action="store_true")
    ui.add_argument("--browser", default="safari", help="safari | default | none")
    ui.set_defaults(func=cmd_ui)

    inst = sub.add_parser("install", help="Create venv and install Python dependencies")
    inst.add_argument("--check-only", action="store_true", help="Report environment only")
    inst.add_argument("--browser", action="store_true", help="Also install Patchright + Chromium")
    inst.add_argument("--no-gmail", action="store_true", help="Skip Gmail packages")
    inst.add_argument("--quiet", action="store_true")
    inst.set_defaults(func=cmd_install)

    login = sub.add_parser("login", help="LinkedIn browser session or Gmail OAuth")
    login.add_argument(
        "action",
        nargs="?",
        choices=["login", "import", "status", "logout", "gmail"],
        default="status",
    )
    login.add_argument("--track", default=None, help="Track for login gmail")
    login.set_defaults(func=cmd_login)

    disc = sub.add_parser("discover", help="Discover board jobs (ready tracks only)")
    disc.add_argument("--since", default="7d")
    disc.add_argument("--track", default=None, help="Single track (default: all tracks)")
    disc.add_argument("--all-tracks", action="store_true", help="Explicit: all tracks")
    disc.add_argument("--dry-run", action="store_true")
    disc.add_argument("--json", action="store_true")
    disc.set_defaults(func=cmd_discover)

    tab = sub.add_parser("table", help="Generate unified applications table")
    tab.add_argument("--track", default=None)
    tab.set_defaults(func=cmd_table)

    app = sub.add_parser("apply", help="Apply via email or DM (skips incomplete tracks)")
    app.add_argument("channel", choices=["email", "dm", "url"])
    app.add_argument("--track", default=None, help="Single track (default: all ready tracks)")
    app.add_argument("--all-tracks", action="store_true")
    app.add_argument("--list", action="store_true")
    app.add_argument("--send", action="store_true")
    app.add_argument("--dry-run", action="store_true")
    app.add_argument("--table-only", action="store_true")
    app.add_argument("--limit", type=int, default=0)
    app.add_argument("--smtp", action="store_true")
    app.add_argument(
        "--force-send",
        action="store_true",
        help="Override manual UI mode and send from CLI (email or DM)",
    )
    app.set_defaults(func=cmd_apply)

    return parser


def main() -> int:
    if os.environ.get("JOBSEARCH_NO_REEXEC") != "1":
        from environment_setup import reexec_in_venv_if_needed  # noqa: WPS433

        reexec_in_venv_if_needed()

    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
