#!/usr/bin/env python3
"""Direct-message apply channel (headed Playwright).

Policy (per user):
  - Open the recruiter's profile page.
  - If NOT connected: click "Connect" and "Send without a note" (NEVER add a note).
  - If already connected / messageable: send a message (same text as email).
    Do NOT attach the resume yet.
  - NEVER comment on any post. Comment-to-apply posts are handled here as DM.

Default is DRY RUN. Pass --send to perform real actions.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import dm_state  # noqa: E402
from application_channel import (  # noqa: E402
    classify_channel,
    form_apply_url,
    has_form_apply,
    is_linkedin_post,
    needs_recruiter_connect,
    recruiter_message_enabled,
    recruiter_profile_url,
)
from browser_session import close_session, launch_context  # noqa: E402
from human_pacing import (
    drift_mouse,
    human_click,
    maybe_session_break,
    pause_between_actions,
    pause_between_reads,
    pause_human,
    pause_page_settle,
)
from flow_runner import resolve_recipe, run_recipe  # noqa: E402
from linkedin_ui import cleanup_after_message, dismiss_blocking_dialogs  # noqa: E402
from registry import job_key, load_registry  # noqa: E402
from track_store import filter_jobs_by_track, load_profile as load_track_profile  # noqa: E402

TZ = ZoneInfo("America/Sao_Paulo")

APPLIED_KEYWORDS = [
    "jeeves", "perficient", "oowlish", "taskworks", "zazmic", "workvista",
    "hr disruptive", "talentpulse", "zahra", "ana lauren",
]

POSTS_SLUG_RE = re.compile(r"linkedin\.com/posts/([a-z0-9-]+)_", re.I)
IN_SLUG_RE = re.compile(r"linkedin\.com/in/([^/?#]+)", re.I)
COMPANY_SLUG_RE = re.compile(r"linkedin\.com/company/([^/?#]+)", re.I)


def profile_url_for(job: dict[str, Any]) -> str | None:
    return recruiter_profile_url(job)


def pretty_role(role: str) -> str:
    """Normalize a registry role label for display (e.g. 'Ai Engineer' -> 'AI Engineer')."""
    role = (role or "AI Engineer").strip()
    role = re.sub(r"\bAi\b", "AI", role)
    role = re.sub(r"\bai\b", "AI", role)
    return role


def is_applied_skip(job: dict[str, Any]) -> bool:
    blob = f"{job.get('company', '')} {job.get('description_snippet', '')}".lower()
    return any(kw in blob for kw in APPLIED_KEYWORDS)


FORM_LINK_DM_TEMPLATE = (
    "Hi I hope you're doing well! I'm contacting you about the {role} role you shared. "
    "I've applied via your link ({apply_url}) and would love to know the next steps."
)

DM_MESSAGE_TEMPLATE = (
    "Hi I hope you're doing well! I'm contacting you because I have the "
    "qualifications for the {role} Role you published and I'd like to know next steps"
)


def message_body(job: dict[str, Any], profile: dict[str, Any], *, track_id: str | None = None) -> str:
    role = pretty_role(job.get("role"))
    use_form_link = is_linkedin_post(job) and has_form_apply(job)
    if use_form_link and track_id:
        from linkedin_configure import load_linkedin_config_raw  # noqa: WPS433

        if not recruiter_message_enabled(job, load_linkedin_config_raw(track_id)):
            use_form_link = False

    if use_form_link:
        tmpl = (
            profile.get("form_link_message_template")
            or profile.get("dm_message_template")
            or FORM_LINK_DM_TEMPLATE
        )
        apply_url = form_apply_url(job) or (job.get("apply_url") or "").strip()
        if not apply_url.startswith("http"):
            apply_url = "your apply link"
    else:
        tmpl = profile.get("dm_message_template") or DM_MESSAGE_TEMPLATE
        apply_url = ""

    try:
        return tmpl.format(role=role, apply_url=apply_url)
    except KeyError:
        return tmpl.format(role=role)


def collect_candidates(
    *,
    table_only: bool,
    limit: int,
    actionable_only: bool = False,
    track_id: str | None = None,
    job_keys: list[str] | None = None,
) -> list[dict[str, Any]]:
    registry = load_registry()
    jobs = filter_jobs_by_track(registry["jobs"], track_id or "all")

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
        jobs = sort_jobs_by_recency(li)

    actionable_keys: set[str] | None = None
    if actionable_only:
        scan_path = ROOT / "runs" / "dm-scan.json"
        if scan_path.exists():
            data = json.loads(scan_path.read_text(encoding="utf-8"))
            actionable_keys = {
                r["job_key"] for r in data.get("results", []) if r.get("actionable")
            }

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for job in jobs:
        if not needs_recruiter_connect(job):
            continue
        prof = profile_url_for(job)
        if not prof:
            continue  # company page / aggregator / no resolvable person profile
        if prof in seen:
            continue  # dedupe repeated recruiters
        if actionable_keys is not None and job_key(job) not in actionable_keys:
            continue
        seen.add(prof)
        out.append(job)
        if limit and len(out) >= limit:
            break
    return out


async def classify_affordance(page, prof_url: str) -> str:
    """Return: message | connect_top | connect_more | connected | follow_only | error.

    All top-card checks are scoped to <main> so we never hit a post's "More"
    menu or the chat-dock messaging button.
    """
    try:
        await page.goto(prof_url, wait_until="domcontentloaded", timeout=60000)
        await pause_page_settle()
        await drift_mouse(page)
        await dismiss_blocking_dialogs(page)
    except Exception:  # noqa: BLE001
        return "error"
    main = page.locator("main").first
    if await main.get_by_role("button", name=re.compile(r"^Message", re.I)).count() > 0:
        return "message"
    if await main.get_by_role("button", name=re.compile(r"^Connect$", re.I)).count() > 0:
        return "connect_top"
    more = main.get_by_role("button", name=re.compile(r"^More", re.I))
    if await more.count() > 0:
        try:
            await human_click(page, more, timeout=10000)
            await pause_human(base=6.0)
            items = page.get_by_role("menuitem")
            labels = []
            for i in range(await items.count()):
                try:
                    nm = (await items.nth(i).get_attribute("aria-label")) or (await items.nth(i).inner_text())
                except Exception:  # noqa: BLE001
                    nm = ""
                labels.append(" ".join((nm or "").split()))
            await page.keyboard.press("Escape")
            if any(re.search(r"remove connection|^following$", x, re.I) for x in labels):
                return "connected"
            if any(re.search(r"\bconnect\b|invite", x, re.I) for x in labels):
                return "connect_more"
        except Exception:  # noqa: BLE001
            pass
    return "follow_only"


async def scan(candidates: list[dict[str, Any]], *, headless: bool) -> None:
    out_path = ROOT / "runs" / "dm-scan.json"
    pw, browser, ctx = await launch_context(headless=headless)
    results: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    try:
        page = await ctx.new_page()
        for i, job in enumerate(candidates, 1):
            prof = profile_url_for(job)
            kind = await classify_affordance(page, prof)
            counts[kind] = counts.get(kind, 0) + 1
            actionable = kind in {"message", "connect_top", "connect_more", "connected"}
            results.append(
                {
                    "company": job.get("company"),
                    "role": job.get("role"),
                    "profile_url": prof,
                    "affordance": kind,
                    "actionable": actionable,
                    "job_key": job_key(job),
                }
            )
            flag = "✓" if actionable else "·"
            print(f"  [{i:>2}/{len(candidates)}] {flag} {kind:12} {job.get('company','?')[:32]:32} {prof}")
            if i < len(candidates):
                await pause_between_reads()
    finally:
        await close_session(pw=pw, browser=browser, context=ctx)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"counts": counts, "results": results}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    actionable = [r for r in results if r["actionable"]]
    print(f"\nScan complete. {len(actionable)}/{len(results)} actionable.")
    print("  by type:", counts)
    print(f"  saved: {out_path}")


async def run(candidates: list[dict[str, Any]], *, send: bool, headless: bool, track_id: str | None = None) -> None:
    profile = load_track_profile(track_id)
    state = dm_state.load()
    recipe = resolve_recipe("linkedin.com/in/", name="linkedin-connect-or-message")
    if not recipe:
        print("ERROR: flows/linkedin-connect-or-message.json not found")
        return
    pw, browser, ctx = await launch_context(headless=headless)
    try:
        page = await ctx.new_page()
        sent_actions = 0
        for job in candidates:
            prof_check = profile_url_for(job)
            existing = dm_state.status_for(state, prof_check)
            if existing != dm_state.STATUS_NONE:
                print(f"  skip (already {dm_state.status_label(existing)}): {job.get('company')}")
                continue
            if is_applied_skip(job):
                print(f"  skip (applied blocklist): {job.get('company')}")
                continue
            prof_url = profile_url_for(job)
            print(f"\n▶ {job.get('company')} — {job.get('role')}")
            print(f"  profile: {prof_url}")
            variables = {"profile_url": prof_url, "message": message_body(job, profile, track_id=track_id)}
            try:
                await page.goto(prof_url, wait_until="domcontentloaded", timeout=60000)
                await pause_page_settle()
                await drift_mouse(page)
                await dismiss_blocking_dialogs(page)
                result = await run_recipe(page, recipe, variables=variables, profile=profile, send=send)
            except Exception as exc:  # noqa: BLE001
                result = {"branch": "error", "steps": [{"action": "goto", "ok": False, "note": str(exc)[:160]}]}

            branch = result.get("branch")
            print(f"  → branch: {branch}")
            for s in result.get("steps", []):
                flag = "ok" if s.get("ok") else "!!"
                print(f"     [{flag}] {s.get('action')}: {s.get('note')}")

            did_action = bool(result.get("committed"))
            kind = result.get("commit_kind")
            if not send:
                # dry-run: report the action that WOULD be taken (connect preferred)
                if did_action:
                    print(f"     would: {'CONNECT (no note)' if kind == 'connect' else 'MESSAGE'}")
                else:
                    print("     would: SKIP (follow-only — no connect/message)")
            if send and did_action:
                if kind == "message":
                    dm_state.record_message(state, job, prof_url, already_connected=True)
                    print("  → MESSAGE sent (no connect available)")
                else:
                    dm_state.record_connect(state, job, prof_url)
                    try:
                        pend = await page.locator("main").first.get_by_role(
                            "button", name=re.compile(r"Pending", re.I)
                        ).count()
                    except Exception:  # noqa: BLE001
                        pend = 0
                    dm_state.set_pending_confirmed(state, prof_url, pend > 0)
                    if pend > 0:
                        print("  → CONNECT request sent · ✓ Pending button confirmed")
                    else:
                        print("  → CONNECT request sent (no note) · Pending not shown (follow-primary; verify via Sent Invitations)")
                dm_state.save(state)
                sent_actions += 1
                await pause_between_actions()
                await maybe_session_break(sent_actions)
    finally:
        await close_session(pw=pw, browser=browser, context=ctx)
    if send:
        from table_refresh import refresh_applications_table  # noqa: E402
        refresh_applications_table()


def main() -> int:
    parser = argparse.ArgumentParser(description="Direct-message / connect apply channel")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--scan", action="store_true", help="Headless: classify affordance per profile, save runs/dm-scan.json")
    parser.add_argument("--send", action="store_true", help="Perform real connect/message actions")
    parser.add_argument("--headless", action="store_true", help="Run without visible browser")
    parser.add_argument("--table-only", action="store_true")
    parser.add_argument("--actionable", action="store_true", help="Only profiles the scan marked actionable")
    parser.add_argument("--match", default="", help="Only candidates whose company/name contains this substring")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--track", default=None, help="Only jobs for this track id")
    parser.add_argument(
        "--job-keys",
        default="",
        help="Comma-separated job_keys — limit connect/message to these list rows",
    )
    parser.add_argument(
        "--force-send",
        action="store_true",
        help="Override manual UI mode and send from CLI",
    )
    parser.add_argument(
        "--ui-approved",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    if args.send:
        from linkedin_configure import linkedin_connect_allowed  # noqa: E402

        tid = args.track or "ai-engineer"
        allowed, reason = linkedin_connect_allowed(
            tid, cli_force=args.force_send, ui_approved=args.ui_approved
        )
        if not allowed:
            print(f"ERROR: {reason}")
            return 1

    key_list = [k.strip() for k in args.job_keys.split(",") if k.strip()] if args.job_keys else None
    candidates = collect_candidates(
        table_only=args.table_only,
        limit=0,
        actionable_only=args.actionable,
        track_id=args.track,
        job_keys=key_list,
    )
    if args.match:
        needle = args.match.casefold()
        candidates = [j for j in candidates if needle in (j.get("company") or "").casefold()]
    # Drop already-actioned profiles BEFORE limiting so --limit counts fresh work.
    if not args.list and not args.scan:
        _state = dm_state.load()
        candidates = [
            j for j in candidates
            if dm_state.status_for(_state, profile_url_for(j) or "") == dm_state.STATUS_NONE
        ]
    if args.limit:
        candidates = candidates[: args.limit]

    if args.scan:
        print(f"[SCAN] classifying {len(candidates)} profile(s) (headless)\n")
        asyncio.run(scan(candidates, headless=True))
        return 0

    if args.list or (not args.send and not args.limit and not args.table_only and not args.match):
        print(f"DM candidates (resolvable profiles): {len(candidates)}\n")
        for job in candidates:
            print(f"  {job.get('company', '?')[:38]:38} | {job.get('role')} | {profile_url_for(job)}")
        return 0

    mode = "SEND" if args.send else "DRY RUN"
    print(f"[{mode}] processing {len(candidates)} DM candidate(s)\n")
    asyncio.run(run(candidates, send=args.send, headless=args.headless, track_id=args.track))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
