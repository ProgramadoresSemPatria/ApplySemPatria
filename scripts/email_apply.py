#!/usr/bin/env python3
"""Send job applications via Gmail for registry rows with apply email."""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from apply_email import apply_email_for_job  # noqa: E402
from registry import job_key, load_registry  # noqa: E402
from track_store import filter_jobs_by_track, load_email_config, resolve_track  # noqa: E402

TZ = ZoneInfo("America/Sao_Paulo")

APPLIED_KEYWORDS = [
    "jeeves", "perficient", "oowlish", "taskworks", "zazmic", "workvista",
    "hr disruptive", "talentpulse", "zahra", "ana lauren",
]


def load_config(track_id: str | None = None) -> dict:
    return load_email_config(track_id)


def load_sent_log(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"sent": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_sent_log(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sent_recipient_emails(sent_log: dict[str, Any]) -> set[str]:
    return {
        (entry.get("to") or "").strip().lower()
        for entry in sent_log.get("sent", [])
        if entry.get("to")
    }


def already_sent(job: dict[str, Any], sent_log: dict[str, Any]) -> bool:
    key = job_key(job)
    if any(entry.get("job_key") == key for entry in sent_log.get("sent", [])):
        return True
    email = (apply_email_for_job(job) or "").strip().lower()
    return bool(email and email in sent_recipient_emails(sent_log))


def pending_send_candidates(
    *,
    track_id: str | None = None,
    job_keys: list[str] | None = None,
    sent_log: dict[str, Any] | None = None,
    track_from_config: str | None = None,
) -> list[dict[str, Any]]:
    """Unique-email candidates that would actually be sent (matches --send filtering)."""
    tid = track_id or track_from_config or "ai-engineer"
    cfg = load_config(tid)
    log = sent_log if sent_log is not None else load_sent_log(ROOT / cfg["sent_log_path"])
    key_list = [k.strip() for k in (job_keys or []) if k and k.strip()] or None
    candidates = collect_candidates(
        table_only=False,
        limit=0,
        track_id=tid,
        job_keys=key_list,
    )
    sent_emails = sent_recipient_emails(log)
    return [
        job
        for job in candidates
        if not already_sent(job, log)
        and (apply_email_for_job(job) or "").strip().lower() not in sent_emails
    ]


def is_applied_skip(job: dict[str, Any]) -> bool:
    blob = f"{job.get('company', '')} {job.get('description_snippet', '')}".lower()
    return any(kw in blob for kw in APPLIED_KEYWORDS)


def render_body(cfg: dict, job: dict[str, Any], template_text: str) -> str:
    role = (job.get("role") or "AI Engineer").strip()
    return template_text.format(role=role)


def build_message(cfg: dict, job: dict[str, Any], to_email: str) -> MIMEMultipart:
    template_path = ROOT / cfg["body_template_file"]
    template_text = template_path.read_text(encoding="utf-8")
    body = render_body(cfg, job, template_text)
    role = job.get("role") or "AI Engineer"
    subject = cfg["subject_template"].format(role=role)

    msg = MIMEMultipart()
    msg["From"] = f"{cfg['sender_name']} <{cfg['sender_email']}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    resume_path = Path(cfg["resume_path"]).expanduser()
    if not resume_path.exists():
        raise FileNotFoundError(f"Resume not found: {resume_path}")
    with resume_path.open("rb") as fh:
        part = MIMEApplication(fh.read(), _subtype="pdf")
    part.add_header("Content-Disposition", "attachment", filename=resume_path.name)
    msg.attach(part)
    return msg


def send_gmail_api(cfg: dict, msg: MIMEMultipart) -> str:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token_path = ROOT / cfg["gmail_token_path"]
    if not token_path.exists():
        raise RuntimeError(f"Gmail not authorized. Run: python3 {SCRIPTS}/gmail_setup.py")

    creds = Credentials.from_authorized_user_file(
        str(token_path), ["https://www.googleapis.com/auth/gmail.send"]
    )
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return result.get("id", "")


def _gmail_app_password() -> str:
    env = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if env:
        return env
    pw_file = ROOT / "secrets" / "gmail-app-password"
    if pw_file.exists():
        return pw_file.read_text(encoding="utf-8").strip()
    return ""


def send_smtp(cfg: dict, msg: MIMEMultipart) -> str:
    import smtplib

    password = _gmail_app_password()
    if not password:
        raise RuntimeError(
            "Gmail app password missing. Run onboarding (SMTP) or set GMAIL_APP_PASSWORD."
        )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(cfg["sender_email"], password)
        smtp.send_message(msg)
    return "smtp-sent"


def log_applika(cfg: dict, job: dict[str, Any], to_email: str) -> None:
    if not cfg.get("log_to_applika", True):
        return
    applika = Path.home() / ".local/bin/applika"
    if not applika.exists():
        return
    company = (job.get("company") or "Unknown")[:80]
    role = (job.get("role") or "AI Engineer")[:80]
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    post_url = job.get("url") or ""
    cmd = [
        str(applika), "applications", "new",
        "--company", company,
        "--role", role,
        "--platform", "LinkedIn",
        "--mode", "active",
        "--date", today,
        "--observation", f"Applied via Gmail to {to_email}. LinkedIn post: {post_url}",
    ]
    if post_url.startswith("http"):
        cmd.extend(["--job-url", post_url])
    subprocess.run(cmd, capture_output=True, text=True, check=False)


def collect_candidates(
    *,
    table_only: bool,
    limit: int,
    company_filters: list[str] | None = None,
    track_id: str | None = None,
    job_keys: list[str] | None = None,
) -> list[dict[str, Any]]:
    registry = load_registry()
    jobs = registry["jobs"]
    jobs = filter_jobs_by_track(jobs, track_id or "all")

    if job_keys:
        allowed = {k.strip() for k in job_keys if k and k.strip()}
        jobs = [j for j in jobs if job_key(j) in allowed]

    if table_only:
        from linkedin_posts_merge import sort_jobs_by_recency  # noqa: E402

        from table_window import table_since  # noqa: E402

        since = table_since()
        li = [
            j for j in jobs
            if j.get("source") == "linkedin_posts"
            and j.get("discovered_at")
            and datetime.fromisoformat(j["discovered_at"]) >= since
        ]
        li = sort_jobs_by_recency(li)
        eligible = [j for j in li if j.get("filter_result") == "eligible"][:45]
        review = [j for j in li if j.get("filter_result") == "needs_review"][:35]
        keys = {job_key(j) for j in eligible + review}
        jobs = [j for j in registry["jobs"] if job_key(j) in keys]

    filters = [c.casefold() for c in (company_filters or [])]
    out: list[dict[str, Any]] = []
    seen_emails: set[str] = set()
    for job in jobs:
        email = apply_email_for_job(job)
        if not email:
            continue
        if filters and not any(f in (job.get("company") or "").casefold() for f in filters):
            continue
        if email in seen_emails:  # dedupe by recipient within this run
            continue
        seen_emails.add(email)
        out.append(job)
        if limit and len(out) >= limit:
            break
    return out


def test_job() -> dict[str, Any]:
    return {
        "source": "email_test",
        "role": "AI Engineer",
        "company": "Email Apply Test",
        "url": "",
        "description_snippet": "SMTP pipeline verification",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply via Gmail when apply email is known")
    parser.add_argument("--list", action="store_true", help="List email-apply candidates")
    parser.add_argument("--dry-run", action="store_true", help="Preview emails (default if no --send)")
    parser.add_argument("--send", action="store_true", help="Actually send emails")
    parser.add_argument("--smtp", action="store_true", help="Use SMTP + GMAIL_APP_PASSWORD")
    parser.add_argument("--table-only", action="store_true", help="Only jobs in applications table window")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--company",
        action="append",
        default=[],
        help="Only jobs whose company contains this substring (repeatable)",
    )
    parser.add_argument("--force", action="store_true", help="Send even if already in sent log")
    parser.add_argument(
        "--force-send",
        action="store_true",
        help="Send in manual UI mode (override; default is UI-only approval)",
    )
    parser.add_argument("--track", default=None, help="Only jobs for this track id")
    parser.add_argument(
        "--job-keys",
        default="",
        help="Comma-separated job_keys — limit email apply to these list rows",
    )
    parser.add_argument(
        "--test-to",
        metavar="EMAIL",
        help="Send one test message to this address (uses sample AI Engineer role)",
    )
    parser.add_argument(
        "--ui-approved",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    cfg = load_config(args.track)
    sent_path = ROOT / cfg["sent_log_path"]
    sent_log = load_sent_log(sent_path)

    if args.send and not args.test_to:
        from gmail_configure import email_send_allowed  # noqa: E402

        tid = args.track or "ai-engineer"
        allowed, reason = email_send_allowed(
            tid, cli_force=args.force_send, ui_approved=args.ui_approved
        )
        if not allowed:
            print(f"ERROR: {reason}")
            return 1

    if args.test_to:
        job = test_job()
        try:
            msg = build_message(cfg, job, args.test_to)
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}")
            return 1
        print(f"Test To: {args.test_to}")
        print(f"  Subject: {msg['Subject']}")
        body_part = msg.get_payload()[0]
        body_text = body_part.get_payload(decode=True).decode(body_part.get_content_charset() or "utf-8")
        print(f"  Body preview:\n{body_text}\n")
        if not args.send:
            print("DRY RUN — add --send to deliver test email")
            return 0
        try:
            msg_id = send_smtp(cfg, msg) if args.smtp else send_gmail_api(cfg, msg)
        except Exception as exc:
            print(f"FAILED: {exc}")
            return 1
        print(f"SENT test email (id={msg_id})")
        return 0

    key_list = [k.strip() for k in args.job_keys.split(",") if k.strip()] if args.job_keys else None
    candidates = collect_candidates(
        table_only=args.table_only,
        limit=0,
        company_filters=args.company,
        track_id=args.track,
        job_keys=key_list,
    )
    sent_emails = sent_recipient_emails(sent_log)
    if not args.force:
        candidates = [
            j
            for j in candidates
            if (apply_email_for_job(j) or "").strip().lower() not in sent_emails
        ]
    if args.limit:
        candidates = candidates[: args.limit]

    if args.list or (not args.send and not args.dry_run):
        print(f"Email-apply candidates: {len(candidates)}\n")
        for job in candidates:
            email = apply_email_for_job(job)
            status = "sent" if already_sent(job, sent_log) else "pending"
            print(f"  [{status}] {job.get('company', '?')[:40]} | {job.get('role', '?')} | {email}")
        return 0

    dry_run = not args.send
    if dry_run:
        print("DRY RUN — pass --send to deliver\n")

    sent_count = 0
    for job in candidates:
        if not args.force and already_sent(job, sent_log):
            print(f"  skip (already sent): {job.get('company')}")
            continue
        if cfg.get("skip_if_already_applied_in_applika") and is_applied_skip(job):
            print(f"  skip (applika blocklist): {job.get('company')}")
            continue

        to_email = apply_email_for_job(job)
        if not to_email:
            continue

        try:
            msg = build_message(cfg, job, to_email)
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}")
            return 1

        subject = msg["Subject"]
        print(f"\n{'[DRY RUN] ' if dry_run else ''}To: {to_email}")
        print(f"  Subject: {subject}")
        print(f"  Company: {job.get('company')} | Role: {job.get('role')}")

        if dry_run:
            continue

        try:
            msg_id = send_smtp(cfg, msg) if args.smtp else send_gmail_api(cfg, msg)
        except Exception as exc:
            print(f"  FAILED: {exc}")
            continue

        sent_log.setdefault("sent", []).append(
            {
                "job_key": job_key(job),
                "company": job.get("company"),
                "role": job.get("role"),
                "to": to_email,
                "subject": subject,
                "gmail_message_id": msg_id,
                "sent_at": datetime.now(TZ).isoformat(),
            }
        )
        save_sent_log(sent_path, sent_log)
        log_applika(cfg, job, to_email)
        sent_count += 1
        print(f"  SENT (id={msg_id})")
        time.sleep(float(cfg.get("rate_limit_seconds", 45)))

    if not dry_run:
        print(f"\nSent {sent_count} email(s). Log: {sent_path}")
        if sent_count:
            from table_refresh import refresh_applications_table  # noqa: E402
            refresh_applications_table()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
