#!/usr/bin/env python3
"""Send a single job application to Applika (UI tag / retry)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from applied_state import APPLIKA_ERROR, APPLIKA_SENT, APPLIKA_SKIPPED, set_applika_result
from generate_applications import apply_url_for, post_url_for
from registry import job_key

TZ = ZoneInfo("America/Sao_Paulo")
APPLIKA = Path.home() / ".local/bin/applika"


def applika_cli_available() -> bool:
    return APPLIKA.is_file()


def applika_sync_enabled(track_id: str | None = None) -> bool:
    from track_store import load_email_config  # noqa: WPS433

    tid = (track_id or "ai-engineer").strip() or "ai-engineer"
    cfg = load_email_config(tid)
    if not cfg.get("log_to_applika", True):
        return False
    return applika_cli_available()


def _application_context(job: dict[str, Any]) -> tuple[str, str]:
    """Return (platform, observation) for Applika."""
    from application_channel import classify_channel  # noqa: WPS433
    from dm_state import load as load_dm  # noqa: WPS433
    from email_apply import email_apply_done, load_sent_log  # noqa: WPS433
    from form_apply_state import form_is_submitted  # noqa: WPS433
    from generate_applications import dm_profile_url  # noqa: WPS433
    from track_store import load_email_config  # noqa: WPS433

    company = (job.get("company") or "Unknown").strip()
    channel = classify_channel(job)
    tid = (job.get("track") or "ai-engineer").strip() or "ai-engineer"
    cfg = load_email_config(tid)
    from retrieval._paths import ROOT  # noqa: WPS433

    sent_log = load_sent_log(ROOT / cfg["sent_log_path"])

    if channel == "email" and email_apply_done(job, sent_log=sent_log):
        to = next(
            (
                (row.get("to") or "").strip()
                for row in sent_log.get("sent", [])
                if row.get("job_key") == job_key(job)
            ),
            "",
        )
        return "LinkedIn", f"Applied via Gmail to {to or 'recruiter'} (LinkedIn post)."

    dm = load_dm()
    prof = dm_profile_url(job)
    if prof:
        entry = (dm.get("profiles") or {}).get(prof) or {}
        if entry.get("message_sent_at"):
            return "LinkedIn", "Applied via LinkedIn DM (connect/message pipeline)."

    if form_is_submitted(job):
        return "LinkedIn", "Applied via URL/form (automated apply)."

    source = (job.get("source") or "").strip().lower()
    if source == "linkedin_jobs":
        return "LinkedIn", "Applied via LinkedIn Jobs (tagged in JobSemPatria)."
    if source in ("linkedin_posts", ""):
        return "LinkedIn", "Manually tagged as applied from JobSemPatria UI."

    return "Job board", "Manually tagged as applied from JobSemPatria UI."


def build_applika_payload(job: dict[str, Any]) -> dict[str, Any]:
    platform, observation = _application_context(job)
    post = post_url_for(job)
    apply = apply_url_for(job)
    job_url = post if post.startswith("http") else ""
    if not job_url and (apply or "").startswith("http"):
        job_url = apply
    return {
        "company": (job.get("company") or "Unknown")[:80],
        "role": (job.get("role") or "AI Engineer")[:80],
        "date": datetime.now(TZ).date().isoformat(),
        "platform": platform,
        "job_url": job_url,
        "observation": observation[:500],
    }


def send_job_to_applika(job: dict[str, Any], *, job_key_value: str | None = None) -> dict[str, Any]:
    from sync_applika import already_logged, create_applika, list_applika  # noqa: WPS433

    jk = (job_key_value or job_key(job)).strip()
    if not applika_cli_available():
        set_applika_result(jk, status=APPLIKA_ERROR, error="Applika CLI not found at ~/.local/bin/applika")
        return {"ok": False, "message": "Applika CLI not found at ~/.local/bin/applika"}

    payload = build_applika_payload(job)
    existing = list_applika()
    if already_logged(payload, existing):
        set_applika_result(jk, status=APPLIKA_SENT)
        return {"ok": True, "message": "Already logged in Applika.", "skipped": True}

    ok, msg = create_applika(payload, dry_run=False)
    if ok:
        set_applika_result(jk, status=APPLIKA_SENT)
        return {"ok": True, "message": "Sent to Applika."}
    set_applika_result(jk, status=APPLIKA_ERROR, error=msg[:500])
    return {"ok": False, "message": msg or "Applika sync failed"}


def tag_and_sync(job: dict[str, Any], *, job_key_value: str | None = None, track_id: str | None = None) -> dict[str, Any]:
    from applied_state import tag_job  # noqa: WPS433

    jk = (job_key_value or job_key(job)).strip()
    tag_job(jk)
    if not applika_sync_enabled(track_id):
        set_applika_result(jk, status=APPLIKA_SKIPPED)
        return {"ok": True, "message": "Tagged as applied."}

    result = send_job_to_applika(job, job_key_value=jk)
    if result.get("ok"):
        if result.get("skipped"):
            return {"ok": True, "message": "Tagged as applied (already in Applika)."}
        return {"ok": True, "message": "Tagged as applied and sent to Applika."}
    return {
        "ok": True,
        "message": f"Tagged as applied. Applika sync failed: {result.get('message', 'unknown error')}",
        "applika_error": True,
    }
