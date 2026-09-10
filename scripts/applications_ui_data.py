"""Build JSON snapshots for the applications HTML UI."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
TZ = ZoneInfo("America/Sao_Paulo")

ROLE_FROM_LABELS: dict[str, str] = {
    "linkedin_posts": "LinkedIn Post",
    "linkedin_jobs": "LinkedIn Job",
    "google": "Google Jobs",
    "remoteok": "RemoteOK",
    "weworkremotely": "We Work Remotely",
    "himalayas": "Himalayas",
    "opentoworkremote": "Open To Work Remote",
    "defi": "DeFi Jobs",
    "wellfound": "Wellfound",
    "f6s": "F6S",
    "browser_scroll": "LinkedIn",
}


def role_from_label(job: dict) -> str:
    raw = (job.get("source") or "").strip().lower()
    if not raw:
        return "Unknown"
    if raw in ROLE_FROM_LABELS:
        return ROLE_FROM_LABELS[raw]
    return raw.replace("_", " ").title()

from application_channel import (  # noqa: E402
    CHANNEL_DM,
    CHANNEL_EMAIL,
    CHANNEL_URL,
    classify_channel,
    channel_label,
    list_application_formats,
    needs_recruiter_connect,
    recruiter_message_enabled,
)
from apply_email import apply_email_display, apply_email_for_job  # noqa: E402
from generate_applications import (  # noqa: E402
    apply_url_for,
    dm_profile_url,
    is_applied,
    load_email_sent,
    post_url_for,
    priority,
    status_cell,
    track_cell,
)
from form_apply_state import load_form_submission_state  # noqa: E402
from registry import job_key, load_registry  # noqa: E402
from table_format import format_posted  # noqa: E402
from linkedin_jobs_merge import posted_within_hours  # noqa: E402
from table_paths import APPLICATIONS_TABLES_DIR  # noqa: E402
import dm_state  # noqa: E402
from position_disposition import (  # noqa: E402
    application_steps_enabled,
    dm_apply_steps_enabled,
    auto_disposition_for_job,
    disposition_is_override,
    disposition_label,
    get_disposition,
    include_in_apply_table,
)


def _snapshot_path_for_md(md_path: Path) -> Path:
    return md_path.with_suffix(".json")


def list_snapshot_days() -> list[dict[str, Any]]:
    from research_log import has_research, list_research_days, today_local  # noqa: E402

    APPLICATIONS_TABLES_DIR.mkdir(parents=True, exist_ok=True)
    researched = set(list_research_days())
    days: dict[str, dict[str, Any]] = {}
    for md in sorted(APPLICATIONS_TABLES_DIR.glob("applications-*-full.md")):
        m = re.match(r"applications-(\d{4}-\d{2}-\d{2})-full\.md$", md.name)
        if not m:
            continue
        day = m.group(1)
        if day not in researched:
            continue
        js = _snapshot_path_for_md(md)
        meta: dict[str, Any] = {"day": day, "md": str(md.name), "job_count": 0, "pending": False}
        if js.exists():
            try:
                data = json.loads(js.read_text(encoding="utf-8"))
                meta["job_count"] = len(data.get("jobs", []))
                meta["generated_at"] = data.get("generated_at")
            except (OSError, json.JSONDecodeError):
                pass
        days[day] = meta

    today = today_local()
    if not has_research(today):
        days.setdefault(
            today,
            {"day": today, "job_count": 0, "pending": True},
        )

    return sorted(days.values(), key=lambda d: d["day"], reverse=True)


def _status_kind(
    job: dict,
    dm: dict,
    email_to: set[str],
    email_keys: set[str],
    url_done: set[str],
    *,
    form_job_keys: set[str] | None = None,
) -> str:
    channel = classify_channel(job)
    if channel == CHANNEL_EMAIL:
        email = (apply_email_for_job(job) or "").strip().lower()
        if (email and email in email_to) or job_key(job) in email_keys:
            return "email_sent"
        return "pending"
    if channel == CHANNEL_URL:
        au = apply_url_for(job)
        keys_done = form_job_keys or set()
        if job_key(job) in keys_done or au in url_done or (job.get("apply_url") or "").strip() in url_done:
            return "form_submitted"
        return "pending"
    if channel == CHANNEL_DM:
        prof = dm_profile_url(job)
        if not prof:
            return "unknown"
        st = dm_state.status_for(dm, prof)
        return st or "not_started"
    return "unknown"


def _easy_apply_form_action(
    job: dict,
    *,
    form_submitted: bool,
    ea_record: dict[str, Any] | None,
) -> dict[str, Any]:
    status = str((ea_record or {}).get("status") or "")
    checked_text = str((ea_record or {}).get("status_text") or "")

    if form_submitted or status == "applied":
        return {
            "label": "Update Easy Apply status",
            "status_text": checked_text or "Applied on LinkedIn",
            "done": True,
            "in_progress": False,
            "status_kind": "applied",
            "easy_apply_enabled": False,
            "checked_at": (ea_record or {}).get("checked_at"),
        }
    if status == "continue":
        return {
            "label": "Update Easy Apply status",
            "status_text": checked_text or "Application in progress",
            "done": False,
            "in_progress": True,
            "status_kind": "continue",
            "easy_apply_enabled": True,
            "checked_at": (ea_record or {}).get("checked_at"),
        }
    if status == "closed":
        return {
            "label": "Update Easy Apply status",
            "status_text": checked_text or "No longer accepting",
            "done": False,
            "in_progress": False,
            "status_kind": "closed",
            "easy_apply_enabled": False,
            "checked_at": (ea_record or {}).get("checked_at"),
        }
    if status == "external":
        return {
            "label": "Update Easy Apply status",
            "status_text": checked_text or "External apply only",
            "done": False,
            "in_progress": False,
            "status_kind": "external",
            "easy_apply_enabled": False,
            "checked_at": (ea_record or {}).get("checked_at"),
        }
    if status == "available":
        return {
            "label": "Update Easy Apply status",
            "status_text": checked_text or "Easy Apply open",
            "done": False,
            "in_progress": False,
            "status_kind": "available",
            "easy_apply_enabled": True,
            "checked_at": (ea_record or {}).get("checked_at"),
        }
    if ea_record:
        return {
            "label": "Update Easy Apply status",
            "status_text": checked_text or "Status unknown",
            "done": False,
            "in_progress": False,
            "status_kind": status or "unknown",
            "easy_apply_enabled": bool((ea_record or {}).get("easy_apply_enabled")),
            "checked_at": (ea_record or {}).get("checked_at"),
        }
    return {
        "label": "Update Easy Apply status",
        "status_text": "Check status",
        "done": False,
        "in_progress": False,
        "status_kind": "unchecked",
        "easy_apply_enabled": None,
        "checked_at": None,
    }


def _action_states(
    job: dict,
    dm: dict,
    email_to: set[str],
    email_keys: set[str],
    url_done: set[str],
    *,
    form_job_keys: set[str] | None = None,
    li_cfg: dict[str, Any] | None = None,
    ea_status: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    formats = {f["id"] for f in list_application_formats(job)}
    prof = dm_profile_url(job)
    jk = job_key(job)
    email_addr = (apply_email_for_job(job) or "").strip().lower()
    email_sent = bool(formats & {"email"}) and (
        (email_addr and email_addr in email_to) or jk in email_keys
    )

    au = apply_url_for(job)
    resolved = (job.get("apply_url") or "").strip()
    keys_done = form_job_keys or set()
    form_submitted = bool(formats & {"form"}) and (
        jk in keys_done or au in url_done or resolved in url_done
    )

    dm_st = dm_state.status_for(dm, prof) if prof else dm_state.STATUS_NONE
    msg_done = dm_st == dm_state.STATUS_MESSAGE_SENT
    accepted = dm_st in (
        dm_state.STATUS_ACCEPTED_MSG_PENDING,
        dm_state.STATUS_MESSAGE_SENT,
    )

    email = {
        "available": "email" in formats,
        "done": email_sent,
        "in_progress": False,
        "label": "Apply via email",
        "status_text": "sent" if email_sent else "not applied",
    }
    form = {
        "available": "form" in formats,
        "done": form_submitted,
        "in_progress": False,
        "label": "Apply via form",
        "status_text": "submitted" if form_submitted else "not applied",
    }
    if job.get("linkedin_easy_apply"):
        form.update(
            _easy_apply_form_action(
                job,
                form_submitted=form_submitted,
                ea_record=(ea_status or {}).get(jk),
            )
        )

    if dm_st == dm_state.STATUS_NONE:
        connect_status = "not applied"
        connect_done = False
        connect_progress = False
    elif dm_st == dm_state.STATUS_CONNECT_PENDING:
        connect_status = "connect sent"
        connect_done = False
        connect_progress = True
    else:
        connect_status = "done"
        connect_done = True
        connect_progress = False

    cfg = li_cfg or {}
    msg_wanted = recruiter_message_enabled(job, cfg)
    dm_formats = "direct_message" in formats and bool(prof) and needs_recruiter_connect(job)

    dm_connect = {
        "available": dm_formats,
        "done": connect_done,
        "in_progress": connect_progress,
        "label": "Send connection",
        "status_text": connect_status,
    }

    check_available = dm_formats and dm_st == dm_state.STATUS_CONNECT_PENDING
    dm_check = {
        "available": check_available,
        "done": accepted and dm_st != dm_state.STATUS_CONNECT_PENDING,
        "in_progress": check_available and not accepted,
        "label": "Check connection accepted",
        "status_text": "accepted" if accepted else ("awaiting accept" if check_available else "not applied"),
    }

    if msg_done:
        msg_status = "sent"
    elif dm_st == dm_state.STATUS_ACCEPTED_MSG_PENDING:
        msg_status = "ready to send"
    elif dm_formats and not msg_wanted:
        msg_status = "connect only"
    else:
        msg_status = "not applied"

    dm_message = {
        "available": dm_formats and msg_wanted,
        "done": msg_done,
        "in_progress": dm_st == dm_state.STATUS_ACCEPTED_MSG_PENDING and not msg_done and msg_wanted,
        "label": "Send LinkedIn message",
        "status_text": msg_status,
    }
    return {
        "email": email,
        "form": form,
        "dm_connect": dm_connect,
        "dm_check": dm_check,
        "dm_message": dm_message,
    }


def _chameleon_card_state(job: dict[str, Any]) -> dict[str, Any]:
    from resume_chameleon import chameleon_is_configured, resolve_output_for_job  # noqa: WPS433
    from resume_keywords import extract_role_keywords_for_job  # noqa: WPS433
    from track_store import infer_track, load_chameleon_config  # noqa: WPS433

    tid = (job.get("track") or infer_track(job) or "ai-engineer").strip()
    cfg = load_chameleon_config(tid)
    jk = job_key(job)
    ready = chameleon_is_configured(cfg)
    keywords = extract_role_keywords_for_job(job, cfg) if ready else []
    output = resolve_output_for_job(jk, track_id=tid) if ready else None
    return {
        "ready": ready,
        "generated": output is not None,
        "download_url": f"/api/chameleon/download?job_key={jk}" if output else "",
        "role_keywords": keywords[:10],
        "role_keywords_count": len(keywords),
    }


def job_to_card(
    job: dict,
    *,
    section: str,
    dm: dict,
    email_to: set[str],
    email_keys: set[str],
    url_done: set[str],
    form_job_keys: set[str] | None = None,
    li_cfg: dict[str, Any] | None = None,
    ea_status: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    kind = _status_kind(job, dm, email_to, email_keys, url_done, form_job_keys=form_job_keys)
    apply_url = apply_url_for(job)
    if apply_url in ("—", "See post", "DM recruiter"):
        resolved = (job.get("apply_url") or "").strip()
        if resolved.startswith("http"):
            apply_url = resolved
    actions = _action_states(
        job,
        dm,
        email_to,
        email_keys,
        url_done,
        form_job_keys=form_job_keys,
        li_cfg=li_cfg,
        ea_status=ea_status,
    )
    steps_on = application_steps_enabled(job)
    dm_on = dm_apply_steps_enabled(job)
    if not steps_on:
        for key, state in actions.items():
            if key.startswith("dm_") and dm_on:
                continue
            state["available"] = False
            state["in_progress"] = False
    return {
        "job_key": job_key(job),
        "track": job.get("track") or "",
        "track_label": track_cell(job),
        "role_from": (job.get("source") or "").strip(),
        "role_from_label": role_from_label(job),
        "role": job.get("role") or "—",
        "company": job.get("company") or "—",
        "salary": job.get("salary_usd") or "—",
        "location": job.get("location_note") or "—",
        "posted": format_posted(job),
        "posted_within_24h": posted_within_hours(job, 24),
        "priority": priority(job),
        "channel": classify_channel(job),
        "channel_label": channel_label(job),
        "status": status_cell(job),
        "status_kind": kind,
        "section": section,
        "position_disposition": get_disposition(job),
        "position_disposition_label": disposition_label(get_disposition(job)),
        "position_disposition_auto": auto_disposition_for_job(job),
        "position_disposition_is_override": disposition_is_override(job),
        "application_steps_enabled": steps_on,
        "dm_apply_steps_enabled": dm_on,
        "post_url": post_url_for(job),
        "apply_url": apply_url,
        "apply_email": apply_email_display(job) or "",
        "profile_url": dm_profile_url(job) or "",
        "application_formats": list_application_formats(job),
        "form_link_message_enabled": recruiter_message_enabled(job, li_cfg or {}),
        "linkedin_easy_apply": bool(job.get("linkedin_easy_apply")),
        "apply_method": job.get("apply_method") or "",
        "actions": actions,
        "chameleon": _chameleon_card_state(job),
    }


def collect_jobs_for_ui(
    *,
    research_day: str | None = None,
    linkedin_since: datetime | None = None,
    board_since: datetime | None = None,
    track_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Same rows as generate_applications table, as UI card dicts."""
    from generate_applications import (  # noqa: E402
        NOISE,
        _job_in_table_scope,
        dedupe_linkedin_rows,
    )
    from table_window import day_bounds, load_research_day  # noqa: E402

    if research_day:
        linkedin_since, _ = day_bounds(research_day)
        board_since = linkedin_since
    elif linkedin_since is None or board_since is None:
        day = load_research_day() or datetime.now(TZ).date().isoformat()
        linkedin_since, _ = day_bounds(day)
        board_since = linkedin_since
        research_day = day
    from filters import salary_sort_value  # noqa: E402
    from linkedin_posts_merge import sort_jobs_by_recency  # noqa: E402
    from track_store import filter_jobs_by_track, infer_track, job_track_label, load_linkedin_config  # noqa: E402

    from linkedin_easy_apply_status import load_all_status_records  # noqa: E402

    dm = dm_state.load()
    email_to, email_keys = load_email_sent()
    url_done, form_job_keys = load_form_submission_state()
    ea_status = load_all_status_records()
    li_cfgs: dict[str, dict[str, Any]] = {}

    registry = load_registry()
    all_jobs = registry["jobs"]
    if track_filter and track_filter != "all":
        all_jobs = filter_jobs_by_track(all_jobs, track_filter)

    linkedin = [
        j
        for j in all_jobs
        if j.get("source") in ("linkedin_posts", "linkedin_jobs")
        and _job_in_table_scope(
            j,
            research_day=research_day,
            linkedin_since=linkedin_since,
            board_since=board_since,
            linkedin_source=True,
        )
    ]
    linkedin = [j for j in linkedin if not NOISE.search((j.get("role", "") + j.get("company", "") + j.get("description_snippet", "")))]
    linkedin_ranked = sort_jobs_by_recency(linkedin)
    linkedin_eligible = [j for j in linkedin_ranked if j.get("filter_result") == "eligible"]
    linkedin_review = [j for j in linkedin_ranked if j.get("filter_result") == "needs_review"]

    boards = [
        j
        for j in all_jobs
        if j.get("source") not in ("linkedin_posts", "linkedin_jobs", "google")
        and _job_in_table_scope(
            j,
            research_day=research_day,
            linkedin_since=linkedin_since,
            board_since=board_since,
            linkedin_source=False,
        )
    ]
    boards = [j for j in boards if not NOISE.search((j.get("role", "") + j.get("company", "")))]
    boards_eligible = sorted(
        [j for j in boards if j.get("filter_result") == "eligible"],
        key=lambda j: -salary_sort_value(j.get("salary_usd")),
    )

    eligible_pool = [j for j in linkedin_eligible if not is_applied(j)]
    review_pool = [j for j in linkedin_review if not is_applied(j)]

    def _cap(jobs: list[dict], limit: int = 0) -> list[dict]:
        return jobs if limit <= 0 else jobs[:limit]

    li_apply = dedupe_linkedin_rows(_cap(eligible_pool))
    li_review = dedupe_linkedin_rows(_cap(review_pool))

    def _li_cfg_for(job: dict) -> dict[str, Any]:
        tid = (job.get("track") or infer_track(job) or "ai-engineer").strip()
        if tid not in li_cfgs:
            li_cfgs[tid] = load_linkedin_config(tid)
        return li_cfgs[tid]

    cards: list[dict[str, Any]] = []
    for job in li_apply:
        cards.append(
            job_to_card(
                job,
                section="linkedin_eligible",
                dm=dm,
                email_to=email_to,
                email_keys=email_keys,
                url_done=url_done,
                form_job_keys=form_job_keys,
                li_cfg=_li_cfg_for(job),
                ea_status=ea_status,
            )
        )
    for job in li_review:
        cards.append(
            job_to_card(
                job,
                section="linkedin_review",
                dm=dm,
                email_to=email_to,
                email_keys=email_keys,
                url_done=url_done,
                form_job_keys=form_job_keys,
                li_cfg=_li_cfg_for(job),
                ea_status=ea_status,
            )
        )
    for job in boards_eligible:
        cards.append(
            job_to_card(
                job,
                section="boards",
                dm=dm,
                email_to=email_to,
                email_keys=email_keys,
                url_done=url_done,
                form_job_keys=form_job_keys,
                li_cfg=_li_cfg_for(job),
                ea_status=ea_status,
            )
        )
    return cards


def write_ui_snapshot(
    md_path: Path,
    *,
    jobs: list[dict[str, Any]],
    research_day: str | None,
    linkedin_since: datetime,
    board_since: datetime,
    track_filter: str | None,
    counts: dict[str, int],
) -> Path:
    import re

    out = _snapshot_path_for_md(md_path)
    m = re.match(r"applications-(\d{4}-\d{2}-\d{2})-", md_path.name)
    day = research_day or (m.group(1) if m else datetime.now(TZ).strftime("%Y-%m-%d"))
    payload = {
        "generated_at": datetime.now(TZ).isoformat(),
        "day": day,
        "research_day": day,
        "table_mode": "daily",
        "linkedin_since": linkedin_since.date().isoformat(),
        "board_since": board_since.date().isoformat(),
        "track_filter": track_filter or "all",
        "counts": counts,
        "jobs": jobs,
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def load_snapshot(day: str) -> dict[str, Any] | None:
    js = APPLICATIONS_TABLES_DIR / f"applications-{day}-full.json"
    if js.exists():
        return json.loads(js.read_text(encoding="utf-8"))
    md = APPLICATIONS_TABLES_DIR / f"applications-{day}-full.md"
    if not md.exists():
        return None
    jobs = collect_jobs_for_ui(research_day=day, track_filter="all")
    return {
        "generated_at": datetime.fromtimestamp(md.stat().st_mtime, TZ).isoformat(),
        "day": day,
        "research_day": day,
        "table_mode": "daily",
        "linkedin_since": day,
        "board_since": day,
        "track_filter": "all",
        "counts": {"jobs": len(jobs)},
        "jobs": jobs,
    }


def refresh_live_snapshot() -> dict[str, Any]:
    from research_log import latest_research_day, today_local  # noqa: E402

    day = latest_research_day() or today_local()
    jobs = collect_jobs_for_ui(research_day=day, track_filter="all")
    return {
        "generated_at": datetime.now(TZ).isoformat(),
        "day": day,
        "research_day": day,
        "table_mode": "daily",
        "linkedin_since": day,
        "board_since": day,
        "track_filter": "all",
        "counts": {"jobs": len(jobs)},
        "jobs": jobs,
    }
