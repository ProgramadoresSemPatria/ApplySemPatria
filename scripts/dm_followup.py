#!/usr/bin/env python3
"""DM follow-up: check accepted connection requests, then send the message.

Policy:
  - Pending visible on profile -> NOT accepted yet (skip).
  - Open message thread; if latest date header is Today/Yesterday/weekday name
    (LinkedIn's <1-week bucket) -> already messaged recently -> mark message_sent,
    do NOT send again.
  - If accepted and no recent thread message -> send DM template.

Default is DRY RUN. Pass --send to perform real actions. Headed by default.

Usage:
  dm_followup.py --list
  dm_followup.py                 # dry run (headed)
  dm_followup.py --send --limit 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import dm_chat  # noqa: E402
import dm_state  # noqa: E402
from browser_session import launch_context  # noqa: E402
from dm_apply import message_body  # noqa: E402
from track_store import load_profile as load_track_profile  # noqa: E402
from flow_runner import resolve_recipe, run_recipe  # noqa: E402
from linkedin_ui import cleanup_after_message, dismiss_blocking_dialogs  # noqa: E402

MESSAGE_AFFORDANCE = dm_chat.MESSAGE_AFFORDANCE
PENDING_RE = re.compile(r"^pending$", re.I)


async def shows_pending(page) -> bool:
    """If Pending is visible on the profile top card, not accepted yet."""
    top = page.locator("main section").first
    if await top.locator("a:has-text('Pending'), button:has-text('Pending')").count() > 0:
        return True
    for role in ("button", "link"):
        if await page.locator("main").first.get_by_role(role, name=PENDING_RE).count() > 0:
            return True
    return False


async def has_top_card_message(page) -> bool:
    """Message affordance on the profile top card (not feed/recommendations)."""
    return await page.locator("main a[href*='messaging/compose']:not([aria-label])").count() > 0


async def is_connected(page, prof_url: str) -> tuple[bool, str]:
    try:
        await page.goto(prof_url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(2.5)
        dismissed = await dismiss_blocking_dialogs(page)
        if dismissed:
            await asyncio.sleep(0.3)
    except Exception:  # noqa: BLE001
        return False, "profile load failed"
    main = page.locator("main").first
    if await shows_pending(page):
        return False, "Pending visible — not accepted yet"
    if await has_top_card_message(page):
        return True, "Message available (accepted)"
    if await main.locator(MESSAGE_AFFORDANCE).count() > 0:
        return True, "Message available (accepted or open profile)"
    return False, "no Message yet — still waiting"


def pending_profiles(state: dict[str, Any], *, include_sent: bool = False) -> list[dict[str, Any]]:
    """Profiles awaiting a message, or (with --audit-sent) already messaged for header audit."""
    out = []
    for entry in state["profiles"].values():
        status = dm_state.status_of(entry)
        if status in (dm_state.STATUS_CONNECT_PENDING, dm_state.STATUS_ACCEPTED_MSG_PENDING):
            out.append(entry)
        elif include_sent and status == dm_state.STATUS_MESSAGE_SENT:
            out.append(entry)
    return out


def filter_entries_by_status(
    entries: list[dict[str, Any]],
    *,
    phase: str | None,
) -> list[dict[str, Any]]:
    """Restrict follow-up rows to connect checks or message sends."""
    if phase == "check":
        return [e for e in entries if dm_state.status_of(e) == dm_state.STATUS_CONNECT_PENDING]
    if phase == "send":
        return [e for e in entries if dm_state.status_of(e) == dm_state.STATUS_ACCEPTED_MSG_PENDING]
    return entries


def filter_entries_by_job_keys(
    entries: list[dict[str, Any]],
    job_keys: list[str] | None,
) -> list[dict[str, Any]]:
    """Keep follow-up rows scoped to UI list job_keys (match key or recruiter profile)."""
    if not job_keys:
        return entries
    allowed = {k.strip() for k in job_keys if k and k.strip()}
    if not allowed:
        return []

    from generate_applications import dm_profile_url  # noqa: E402
    from registry import job_key as registry_job_key, load_registry  # noqa: E402

    allowed_profiles: set[str] = set()
    for job in load_registry()["jobs"]:
        if registry_job_key(job) in allowed:
            prof = dm_profile_url(job)
            if prof:
                allowed_profiles.add(dm_state.normalize_profile_url(prof))

    matched: list[dict[str, Any]] = []
    seen_profiles: set[str] = set()
    for entry in entries:
        prof = dm_state.normalize_profile_url(entry.get("profile_url") or "")
        entry_key = (entry.get("job_key") or "").strip()
        if entry_key in allowed or (prof and prof in allowed_profiles):
            if prof and prof in seen_profiles:
                continue
            if prof:
                seen_profiles.add(prof)
            matched.append(entry)
    return matched


async def run(
    entries: list[dict[str, Any]],
    *,
    send: bool,
    headless: bool,
    audit_sent: bool = False,
    track_id: str | None = None,
) -> None:
    profile = load_track_profile(track_id)
    state = dm_state.load()
    recipe = resolve_recipe("linkedin.com/in/", name="linkedin-message-only")
    if not recipe:
        recipe = resolve_recipe("linkedin.com/in/", name="linkedin-connect-or-message")
    if not recipe:
        print("ERROR: recipe not found")
        return
    pw, browser, ctx = await launch_context(headless=headless)
    accepted = messaged = recent_skipped = still_pending = 0
    print(f"  recipe: {recipe.get('name')}\n")
    try:
        page = await ctx.new_page()
        for entry in entries:
            prof_url = entry["profile_url"]
            job = {"role": entry.get("role"), "company": entry.get("company"), "job_key": entry.get("job_key")}
            print(f"\n▶ {entry.get('company')} — {entry.get('role')}")
            print(f"  profile: {prof_url}")
            try:
                connected, reason = await is_connected(page, prof_url)
                if not connected:
                    print(f"  → skip: {reason}")
                    if "Pending" in reason:
                        entry = dm_state.get(state, prof_url)
                        if entry and entry.get("accepted_at") and not entry.get("message_sent_at"):
                            entry["accepted_at"] = None
                            dm_state.save(state)
                            print("  → state corrected (cleared stale accepted_at)")
                    still_pending += 1
                    continue

                accepted += 1
                dm_state.record_accepted(state, job, prof_url)
                dm_state.save(state)
                print("  → ACCEPTED ✓ (no Pending on profile)")

                thread = await dm_chat.inspect_thread(page)
                hdrs = [h for h in thread.get("headers", []) if dm_chat.classify_header(h) != "other"]
                if hdrs:
                    print(f"  thread headers: {' → '.join(hdrs[-5:])}")
                print(f"  thread check: {thread.get('reason', '?')}")

                if thread.get("recent"):
                    recent_skipped += 1
                    note = f"skip recent: header '{thread.get('last_header')}'"
                    if audit_sent and dm_state.status_of(entry) == dm_state.STATUS_MESSAGE_SENT:
                        print(f"  → audit OK: recent header confirms message_sent state")
                        continue
                    if send:
                        dm_state.record_message(
                            state, job, prof_url, already_connected=False, note=note
                        )
                        dm_state.save(state)
                        print(f"  → RECENT MESSAGE — marked message_sent (no resend)")
                    else:
                        print(f"  → (dry) would mark message_sent — recent header, no resend")
                    continue

                msg = message_body(job, profile, track_id=track_id)
                ok, note = await dm_chat.send_message(page, msg, send=send)
                print(f"  send: {note}")
                if send and ok and note.startswith("sent"):
                    dm_state.record_message(state, job, prof_url, already_connected=False)
                    dm_state.save(state)
                    messaged += 1
                    print("  → MESSAGE SENT ✓")
                    await asyncio.sleep(20)
                elif not send and ok:
                    print("  → (dry) would send message")
                elif send and not ok:
                    # Fallback: reload profile and use message-only recipe.
                    print("  → composer send failed — trying recipe fallback")
                    await page.goto(prof_url, wait_until="domcontentloaded", timeout=60000)
                    await asyncio.sleep(2.0)
                    await dismiss_blocking_dialogs(page)
                    variables = {"profile_url": prof_url, "message": msg}
                    try:
                        result = await run_recipe(page, recipe, variables=variables, profile=profile, send=send)
                    except Exception as exc:  # noqa: BLE001
                        result = {"committed": False, "steps": [{"note": str(exc)[:120]}]}
                    for s in result.get("steps", []):
                        print(f"     [{'ok' if s.get('ok') else '!!'}] {s.get('action')}: {s.get('note')}")
                    if result.get("committed") and result.get("commit_kind") == "message":
                        dm_state.record_message(state, job, prof_url, already_connected=False)
                        dm_state.save(state)
                        messaged += 1
                        print("  → MESSAGE SENT ✓ (recipe fallback)")
                        await asyncio.sleep(20)
            finally:
                closed = await cleanup_after_message(page)
                if closed:
                    print(f"  cleanup: {', '.join(closed)}")
    finally:
        await browser.close()
        await pw.stop()
    if send:
        from table_refresh import refresh_applications_table  # noqa: E402
        refresh_applications_table()
    print(
        f"\nSummary: accepted={accepted} messaged={messaged} "
        f"recent_skipped={recent_skipped} still_pending={still_pending}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="DM follow-up: message accepted connections")
    parser.add_argument("--list", action="store_true", help="List profiles awaiting a message")
    parser.add_argument("--send", action="store_true", help="Actually send messages to accepted connections")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--match", default="", help="Filter by company/name substring")
    parser.add_argument("--audit-sent", action="store_true",
                        help="Also audit profiles already marked message_sent (header check only)")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--track", default=None, help="Profile track for message template")
    parser.add_argument(
        "--phase",
        choices=("check", "send"),
        default="",
        help="check = only connect_pending profiles; send = only accepted_msg_pending",
    )
    parser.add_argument(
        "--job-keys",
        default="",
        help="Comma-separated job_keys — limit follow-up to these list rows",
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
        from linkedin_configure import linkedin_message_allowed  # noqa: E402
        from registry import job_key as jk, load_registry  # noqa: E402

        tid = args.track or "ai-engineer"
        jobs_by_key = {jk(j): j for j in load_registry()["jobs"]}

    state = dm_state.load()
    entries = pending_profiles(state, include_sent=args.audit_sent)
    if args.job_keys:
        entries = filter_entries_by_job_keys(entries, args.job_keys.split(","))
    elif args.match:
        needle = args.match.casefold()
        entries = [e for e in entries if needle in (e.get("company") or "").casefold()]
    phase = (args.phase or "").strip().lower()
    if phase:
        entries = filter_entries_by_status(entries, phase=phase)
    if args.limit:
        entries = entries[: args.limit]

    if args.send:
        for entry in entries:
            job = jobs_by_key.get(entry.get("job_key") or "")
            allowed, reason = linkedin_message_allowed(
                tid,
                job,
                cli_force=getattr(args, "force_send", False),
                ui_approved=getattr(args, "ui_approved", False),
            )
            if not allowed:
                print(f"ERROR: {reason}")
                return 1

    if args.list:
        print(f"Awaiting message: {len(entries)}\n")
        for e in entries:
            print(f"  {dm_state.status_of(e):22} {e.get('company','?')[:34]:34} {e['profile_url']}")
        return 0

    mode = "SEND" if args.send else "DRY RUN"
    print(f"[{mode}] checking {len(entries)} profile(s)\n")
    asyncio.run(
        run(
            entries,
            send=args.send,
            headless=args.headless,
            audit_sent=args.audit_sent,
            track_id=args.track,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
