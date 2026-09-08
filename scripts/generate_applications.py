#!/usr/bin/env python3
"""Generate consolidated applications markdown table from registry."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from apply_email import apply_email_display, apply_email_for_job, is_email_address  # noqa: E402
from application_channel import (  # noqa: E402
    channel_label,
    classify_channel,
    is_linkedin_post,
    needs_recruiter_connect,
    recruiter_profile_url,
)
from filters import salary_sort_value  # noqa: E402
from linkedin_posts_merge import (  # noqa: E402
    fallback_linkedin_post_search_url,
    is_apply_only_url,
    is_feed_update_url,
    is_linkedin_post_url,
    is_placeholder_post_url,
    is_posts_permalink,
    is_profile_fallback_url,
    permalink_matches_author,
    resolve_apply_url_from_text,
    sort_jobs_by_recency,
)
from linkedin_jobs_merge import extract_job_view_id  # noqa: E402
from registry import RUNS_DIR, job_key, load_registry  # noqa: E402
from table_format import format_posted, md_cell, normalize_company_display  # noqa: E402
from track_store import filter_jobs_by_track, job_track_label, list_track_ids, track_label  # noqa: E402
from position_disposition import disposition_label, get_disposition, include_in_apply_table  # noqa: E402
import dm_state  # noqa: E402

TZ = ZoneInfo("America/Sao_Paulo")

IN_SLUG_RE = re.compile(r"linkedin\.com/in/([^/?#]+)", re.I)
POSTS_SLUG_RE = re.compile(r"linkedin\.com/posts/([a-z0-9-]+)_", re.I)


def dm_profile_url(job: dict) -> str | None:
    return recruiter_profile_url(job)


# Populated in generate() so row builders can read progress state without plumbing.
_DM_STATE: dict = {"profiles": {}}
_EMAIL_TO: set[str] = set()
_EMAIL_KEYS: set[str] = set()
_URL_SUBMITTED: set[str] = set()


def load_email_sent() -> tuple[set[str], set[str]]:
    path = ROOT / "state" / "email-applications.json"
    if not path.exists():
        return set(), set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set(), set()
    tos = {(r.get("to") or "").strip().lower() for r in data.get("sent", []) if r.get("to")}
    keys = {r.get("job_key") for r in data.get("sent", []) if r.get("job_key")}
    return tos, keys


def load_url_submitted() -> set[str]:
    path = ROOT / "state" / "url-applications.json"
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    out: set[str] = set()
    for r in data.get("submitted", []):
        for k in ("url", "resolved_url"):
            v = (r.get(k) or "").strip()
            if v:
                out.add(v)
    return out


def _form_status(job: dict) -> str:
    au = apply_url_for(job)
    if au in _URL_SUBMITTED or (job.get("apply_url") or "").strip() in _URL_SUBMITTED:
        return "✅ form submitted"
    return "☐ form pending"


def load_progress_state() -> None:
    """Load email / form / DM progress into module globals for status_cell."""
    global _DM_STATE, _EMAIL_TO, _EMAIL_KEYS, _URL_SUBMITTED
    _DM_STATE = dm_state.load()
    _EMAIL_TO, _EMAIL_KEYS = load_email_sent()
    _URL_SUBMITTED = load_url_submitted()


def status_cell(job: dict) -> str:
    """Progress status for a row, based on channel + saved state."""
    load_progress_state()
    channel = classify_channel(job)
    if channel == "email":
        email = (apply_email_for_job(job) or "").strip().lower()
        if (email and email in _EMAIL_TO) or job_key(job) in _EMAIL_KEYS:
            return "✅ email sent"
        return "☐ pending"
    if channel == "dm":
        prof = dm_profile_url(job)
        if not prof:
            return "—"
        return dm_state.status_label(dm_state.status_for(_DM_STATE, prof))
    if channel == "url":
        form_st = _form_status(job)
        if is_linkedin_post(job) and needs_recruiter_connect(job):
            prof = dm_profile_url(job)
            if prof:
                dm_st = dm_state.status_label(dm_state.status_for(_DM_STATE, prof))
                if dm_st and dm_st != "—":
                    return f"{form_st} · {dm_st}"
        au = apply_url_for(job)
        if au in _URL_SUBMITTED or (job.get("apply_url") or "").strip() in _URL_SUBMITTED:
            return "✅ submitted"
        return "not applied"
    return "—"

NOISE = re.compile(
    r"annotator|mindrift|toloka|data label|labeling|coding annotator|"
    r"evaluation expert|red team|safety specialist",
    re.IGNORECASE,
)

APPLIED_KEYWORDS = [
    ("jeeves", "Jeeves"),
    ("perficient", "Perficient"),
    ("oowlish", "Oowlish"),
    ("taskworks", "Taskworks"),
    ("zazmic", "Zazmic"),
    ("workvista", "Workvista"),
    ("hr disruptive", "HR Disruptive"),
    ("talentpulse", "Talentpulse"),
    ("muqadas", "Muqadas/HR Disruptive"),
    ("zahra", "Zahra"),
    ("ana lauren", "Ana Lauren"),
]


def discovered_at(job: dict) -> datetime | None:
    raw = job.get("discovered_at")
    if not raw:
        return None
    return datetime.fromisoformat(raw)


def priority(job: dict) -> str:
    salary = salary_sort_value(job.get("salary_usd"))
    status = job.get("filter_result")
    snippet = (job.get("description_snippet") or "").lower()
    if "colombia" in snippet and "mexico" in snippet and "brazil" not in snippet:
        return "★☆☆"
    if status == "eligible" and salary >= 40000:
        return "★★★"
    if status == "eligible":
        return "★★☆"
    if status and "hiring" in snippet:
        return "★★☆"
    return "★☆☆"


def post_url_for(job: dict) -> str:
    if job.get("source") == "linkedin_jobs":
        return (job.get("url") or "").strip()
    url = (job.get("url") or "").strip()
    author = normalize_company_display(job.get("company") or "")
    role = job.get("role") or "ai engineer"

    if is_apply_only_url(url):
        return fallback_linkedin_post_search_url(author, role)
    if is_posts_permalink(url):
        return url if permalink_matches_author(url, author) else fallback_linkedin_post_search_url(author, role)
    if is_feed_update_url(url):
        return url
    if is_linkedin_post_url(url) and not is_profile_fallback_url(url):
        return url
    if url.startswith("http"):
        return url
    return fallback_linkedin_post_search_url(author, role)


def apply_url_for(job: dict) -> str:
    apply = (job.get("apply_url") or "").strip()
    post = post_url_for(job)

    if apply and is_email_address(apply):
        apply = ""

    if apply:
        if apply == post:
            apply = ""
        elif is_posts_permalink(apply) or "search/results/content" in apply:
            apply = ""

    if apply:
        return apply

    url = (job.get("url") or "").strip()
    if is_apply_only_url(url) and url != post and not is_email_address(url):
        return url

    channel = job.get("apply_channel") or ""
    snippet = job.get("description_snippet") or ""
    if channel == "chat":
        return "DM recruiter"
    resolved = resolve_apply_url_from_text(snippet, channel)
    if resolved and resolved != post and not is_posts_permalink(resolved) and not is_email_address(resolved):
        return resolved
    if job.get("source") == "linkedin_posts":
        return "See post"
    if job.get("source") == "linkedin_jobs":
        url = (job.get("url") or "").strip()
        return url if url.startswith("http") else "—"
    return "—"


def dedupe_linkedin_rows(jobs: list[dict]) -> list[dict]:
    """Drop duplicate rows that share the same post permalink or jobs/view id."""
    seen: set[str] = set()
    out: list[dict] = []
    for job in jobs:
        view_id = extract_job_view_id(job.get("url")) or extract_job_view_id(job.get("apply_url"))
        if view_id:
            key = f"jobview:{view_id}"
        else:
            post = post_url_for(job)
            key = post if is_posts_permalink(post) else job_key(job)
        if key in seen:
            continue
        seen.add(key)
        out.append(job)
    return out


LINKEDIN_TABLE_SOURCES = ("linkedin_posts", "linkedin_jobs")


def is_applied(job: dict) -> bool:
    blob = f"{job.get('company', '')} {job.get('description_snippet', '')}".lower()
    return any(keyword in blob for keyword, _ in APPLIED_KEYWORDS)


def track_cell(job: dict) -> str:
    return job_track_label(job)


def linkedin_row(job: dict) -> str:
    posted = format_posted(job)
    salary = job.get("salary_usd") or "—"
    location = job.get("location_note") or "—"
    company = normalize_company_display(job.get("company") or "—")
    return (
        f"| ☐ | {md_cell(track_cell(job))} | {md_cell(priority(job))} | {md_cell(posted)} | {md_cell(job.get('role', '—'))} | "
        f"{md_cell(company)} | {md_cell(salary)} | {md_cell(location)} | {md_cell(disposition_label(get_disposition(job)))} | "
        f"{md_cell(channel_label(job))} | {md_cell(status_cell(job))} | "
        f"{md_cell(post_url_for(job))} | {md_cell(apply_url_for(job))} | {md_cell(apply_email_display(job))} |"
    )


def board_row(job: dict) -> str:
    salary = salary_sort_value(job.get("salary_usd"))
    pri = "★★★" if salary >= 70000 else "★★☆"
    url = job.get("url") or "—"
    apply = apply_url_for(job)
    if apply in {"—", "See post"}:
        apply = "Job page"
    return (
        f"| ☐ | {md_cell(track_cell(job))} | {md_cell(pri)} | {md_cell(job.get('role', '—'))} | "
        f"{md_cell(normalize_company_display(job.get('company', '—')))} | "
        f"{md_cell(job.get('salary_usd') or '—')} | {md_cell(job.get('location_note') or '—')} | "
        f"{md_cell(disposition_label(get_disposition(job)))} | "
        f"{md_cell(channel_label(job))} | {md_cell(status_cell(job))} | {md_cell(apply)} | {md_cell(url)} | {md_cell(apply_email_display(job))} |"
    )


def generate(
    *,
    linkedin_since: datetime,
    board_since: datetime,
    output: Path,
    linkedin_eligible_limit: int = 0,
    linkedin_review_limit: int = 0,
    linkedin_run_note: str = "",
    boards_run_note: str = "",
    track_filter: str | None = None,
) -> dict[str, int]:
    load_progress_state()

    registry = load_registry()
    all_jobs = registry["jobs"]
    if track_filter and track_filter != "all":
        all_jobs = filter_jobs_by_track(all_jobs, track_filter)
    now = datetime.now(TZ)

    linkedin = [
        j
        for j in all_jobs
        if j.get("source") in LINKEDIN_TABLE_SOURCES
        and discovered_at(j)
        and discovered_at(j) >= linkedin_since
    ]
    linkedin = [
        j
        for j in linkedin
        if not NOISE.search((j.get("role", "") + j.get("company", "") + j.get("description_snippet", "")))
    ]
    linkedin_ranked = sort_jobs_by_recency(linkedin)
    linkedin_eligible = [j for j in linkedin_ranked if j.get("filter_result") == "eligible"]
    linkedin_review = [j for j in linkedin_ranked if j.get("filter_result") == "needs_review"]

    boards = [
        j
        for j in all_jobs
        if j.get("source") not in (*LINKEDIN_TABLE_SOURCES, "google")
        and discovered_at(j)
        and discovered_at(j) >= board_since
    ]
    boards = [j for j in boards if not NOISE.search((j.get("role", "") + j.get("company", "")))]
    boards_eligible = sorted(
        [j for j in boards if j.get("filter_result") == "eligible"],
        key=lambda j: -salary_sort_value(j.get("salary_usd")),
    )

    eligible_pool = [j for j in linkedin_eligible if not is_applied(j)]
    review_pool = [j for j in linkedin_review if not is_applied(j)]

    def cap(jobs: list[dict], limit: int) -> list[dict]:
        return jobs if limit <= 0 else jobs[:limit]

    li_apply = dedupe_linkedin_rows(cap(eligible_pool, linkedin_eligible_limit))
    li_review_apply = dedupe_linkedin_rows(cap(review_pool, linkedin_review_limit))
    boards_eligible = [j for j in boards_eligible if include_in_apply_table(j)]
    li_apply = [j for j in li_apply if include_in_apply_table(j)]
    li_review_apply = [j for j in li_review_apply if include_in_apply_table(j)]

    all_rows = li_apply + li_review_apply + boards_eligible
    chan_counts = {"email": 0, "url": 0, "dm": 0}
    track_counts: dict[str, int] = {}
    for job in all_rows:
        chan_counts[classify_channel(job)] += 1
        label = track_cell(job)
        track_counts[label] = track_counts.get(label, 0) + 1

    track_lines = [
        "",
        "### By career track",
        "",
        "| Track | Rows in table |",
        "|-------|--------------:|",
    ]
    for tid in list_track_ids():
        label = track_label(tid)
        track_lines.append(f"| **{label}** | {track_counts.get(label, 0)} |")
    for label, count in sorted(track_counts.items()):
        if label not in {track_label(t) for t in list_track_ids()}:
            track_lines.append(f"| {label} (legacy) | {count} |")

    lines = [
        "# Application list — full refresh",
        "",
        f"**Generated:** {now.strftime('%Y-%m-%d %H:%M %Z')}",
        f"**LinkedIn window:** since {linkedin_since.strftime('%a %b %d')} · sort **latest → oldest**",
        f"**Boards window:** since {board_since.strftime('%a %b %d')}",
        f"**Tracks shown:** {track_filter or 'all'}",
        "",
        "## Summary",
        "",
        "| Source | Window | Total | Eligible | In table |",
        "|--------|--------|------:|---------:|---------:|",
        f"| **LinkedIn** (posts + jobs · registry) | {linkedin_since.strftime('%b %d')} → now | {len(linkedin)} | {len(linkedin_eligible)} | {len(li_apply) + len(li_review_apply)} |",
        f"| **Boards** (Himalayas, RemoteOK, etc.) | {board_since.strftime('%b %d')} → now | {len(boards)} | {len(boards_eligible)} | {len(boards_eligible)} |",
        "| Google jobs | — | — | — | skipped (no API key) |",
        *track_lines,
        "",
        "### By application channel",
        "",
        "| Channel | Count | How to apply |",
        "|---------|------:|--------------|",
        f"| **Email** | {chan_counts['email']} | `email_apply.py` — send resume + message |",
        f"| **URL/Form** | {chan_counts['url']} | `url_apply.py` — headed browser, LLM-fill form |",
        f"| **Direct Msg** | {chan_counts['dm']} | `dm_apply.py` — connect (no note) / message if connected. Comment-to-apply is treated as DM; **never comment** |",
        "",
    ]
    if linkedin_run_note:
        lines.append(linkedin_run_note)
    if boards_run_note:
        lines.append(boards_run_note)
    lines += [
        "",
        "---",
        "",
        "## LinkedIn — best fit (eligible · newest first)",
        "",
        "| ☐ | Track | Pri | Posted | Role | Company | Salary | Location | Disposition | Channel | Status | Post URL | Apply URL | Apply Email |",
        "|---|-------|-----|--------|------|---------|--------|----------|-------------|---------|--------|----------|-----------|-------------|",
    ]
    lines.extend(linkedin_row(j) for j in li_apply)
    lines += [
        "",
        "---",
        "",
        "## LinkedIn — needs review (newest first)",
        "",
        "| ☐ | Track | Pri | Posted | Role | Company | Salary | Location | Disposition | Channel | Status | Post URL | Apply URL | Apply Email |",
        "|---|-------|-----|--------|------|---------|--------|----------|-------------|---------|--------|----------|-----------|-------------|",
    ]
    lines.extend(linkedin_row(j) for j in li_review_apply)
    lines += [
        "",
        "---",
        "",
        "## Boards — since window",
        "",
        "| ☐ | Track | Pri | Role | Company | Salary | Location | Disposition | Channel | Status | Apply | URL | Apply Email |",
        "|---|-------|-----|------|---------|--------|----------|-------------|---------|--------|-------|-----|-------------|",
    ]
    lines.extend(board_row(j) for j in boards_eligible)
    lines += [
        "",
        "---",
        "",
        "## Already applied (Applika · do not re-apply)",
        "",
        "| Company | Role | Status |",
        "|---------|------|--------|",
        "| HR Disruptive | Founding ML Engineer | Initial Screen (Aijaz) |",
        "| Jeeves | Senior AI Engineer | Active |",
        "| Perficient | Senior AWS Agentic AI Engineer | Active |",
        "| Oowlish | Senior LLM Engineer | Active |",
        "| Taskworks / Able | Senior / Principal AI Engineer | Active |",
        "| Zazmic | AI Engineer (Google) | Active |",
        "| Talentpulse | AI Engineer | Active |",
        "| Workvista | AI Engineer / Architect | Active |",
        "| Not disclosed | AI Engineer (Ana Lauren) | Active |",
        "| Not disclosed | AI Platform (Zahra) | Active |",
        "",
        "---",
        "",
        "## Skipped (noise / wrong geo)",
        "",
        "Annotator/evaluator gigs (Toloka, Mindrift, Mercor eval), Colombia/Mexico-only posts, US-only, hotel spam.",
        "",
        f"_Full LinkedIn registry dump ({len(linkedin)} rows): see run markdown above._",
        "",
    ]

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")

    from applications_ui_data import collect_jobs_for_ui, write_ui_snapshot  # noqa: E402

    ui_jobs = collect_jobs_for_ui(
        linkedin_since=linkedin_since,
        board_since=board_since,
        track_filter=track_filter,
    )
    write_ui_snapshot(
        output,
        jobs=ui_jobs,
        linkedin_since=linkedin_since,
        board_since=board_since,
        track_filter=track_filter,
        counts={
            "linkedin_eligible_rows": len(li_apply),
            "linkedin_review_rows": len(li_review_apply),
            "board_rows": len(boards_eligible),
            "total": len(ui_jobs),
        },
    )

    return {
        "linkedin_eligible_rows": len(li_apply),
        "linkedin_review_rows": len(li_review_apply),
        "board_rows": len(boards_eligible),
    }


def main() -> int:
    from table_paths import applications_table_path, ensure_table_dirs  # noqa: E402
    from table_window import last_monday, save_window  # noqa: E402

    ensure_table_dirs()
    default_since = last_monday().date().isoformat()
    parser = argparse.ArgumentParser(description="Generate applications markdown table")
    parser.add_argument("--linkedin-since", default=default_since, help="LinkedIn since date (YYYY-MM-DD)")
    parser.add_argument("--board-since", default=default_since, help="Board jobs since date (YYYY-MM-DD)")
    parser.add_argument(
        "--linkedin-eligible-limit",
        type=int,
        default=0,
        help="Max eligible LinkedIn rows (0 = all)",
    )
    parser.add_argument(
        "--linkedin-review-limit",
        type=int,
        default=0,
        help="Max needs-review LinkedIn rows (0 = all)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path (default: runs/tables/applications/applications-YYYY-MM-DD-full.md)",
    )
    parser.add_argument(
        "--track",
        default=None,
        help="Filter table to one track id, or 'all' (default: all tracks in one file)",
    )
    args = parser.parse_args()

    linkedin_since = datetime.fromisoformat(args.linkedin_since).replace(tzinfo=TZ)
    board_since = datetime.fromisoformat(args.board_since).replace(tzinfo=TZ)
    output = args.output or applications_table_path()
    save_window(linkedin_since=linkedin_since, board_since=board_since)
    counts = generate(
        linkedin_since=linkedin_since,
        board_since=board_since,
        output=output,
        linkedin_eligible_limit=args.linkedin_eligible_limit,
        linkedin_review_limit=args.linkedin_review_limit,
        track_filter=args.track or "all",
    )
    print(f"Wrote {output}")
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
