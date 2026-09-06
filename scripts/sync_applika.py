#!/usr/bin/env python3
"""Sync completed applications (email / DM / URL) into Applika."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
APPLIKA = Path.home() / ".local/bin/applika"


def _load(path: Path) -> dict | list:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def collect_applied() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    dm = _load(STATE / "dm-applications.json")
    for entry in dm.get("profiles", {}).values():
        if not entry.get("message_sent_at"):
            continue
        out.append({
            "company": entry.get("company") or "Unknown",
            "role": entry.get("role") or "AI Engineer",
            "date": entry["message_sent_at"][:10],
            "platform": "LinkedIn",
            "job_url": entry.get("profile_url") or entry.get("job_key") or "",
            "observation": "Applied via LinkedIn DM (connect/message pipeline).",
            "key": f"dm:{entry.get('profile_url')}",
        })

    email = _load(STATE / "email-applications.json")
    for entry in email.get("sent", []):
        to = entry.get("to", "")
        out.append({
            "company": entry.get("company") or "Unknown",
            "role": entry.get("role") or "AI Engineer",
            "date": entry["sent_at"][:10],
            "platform": "LinkedIn",
            "job_url": entry.get("job_key") or "",
            "observation": f"Applied via Gmail to {to} (LinkedIn post).",
            "key": f"email:{entry.get('job_key')}:{to}",
        })

    url_state = _load(STATE / "url-applications.json")
    seen_url: set[tuple[str, str]] = set()
    for entry in url_state.get("submitted", []):
        if not entry.get("confirmed"):
            continue
        k = (entry.get("company", ""), entry.get("role", ""))
        if k in seen_url:
            continue
        seen_url.add(k)
        out.append({
            "company": entry.get("company") or "Unknown",
            "role": entry.get("role") or "AI Engineer",
            "date": entry["submitted_at"][:10],
            "platform": "LinkedIn",
            "job_url": entry.get("url") or entry.get("resolved_url") or "",
            "observation": "Applied via URL/form (automated apply).",
            "key": f"url:{entry.get('url')}",
        })
    return out


def list_applika() -> list[dict[str, Any]]:
    if not APPLIKA.exists():
        return []
    proc = subprocess.run(
        [str(APPLIKA), "applications", "list", "--output-format", "json"],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        return []
    data = json.loads(proc.stdout)
    if isinstance(data, list):
        return data
    return data.get("applications") or data.get("data") or []


def already_logged(app: dict[str, Any], existing: list[dict[str, Any]]) -> bool:
    company = app["company"].casefold()
    role = app["role"].casefold()
    date = app["date"]
    for e in existing:
        ec = (e.get("company_name") or "").casefold()
        er = (e.get("role") or "").casefold()
        ed = (e.get("application_date") or "")[:10]
        if company in ec or ec in company:
            if role.split()[0] in er or er.split()[0] in role:
                if ed == date or abs(int(ed.replace("-", "")) - int(date.replace("-", ""))) <= 2:
                    return True
    return False


def create_applika(app: dict[str, Any], *, dry_run: bool) -> tuple[bool, str]:
    cmd = [
        str(APPLIKA), "applications", "new",
        "--company", app["company"][:80],
        "--role", app["role"][:80],
        "--platform", app["platform"],
        "--mode", "active",
        "--date", app["date"],
        "--work-mode", "remote",
        "--observation", app["observation"][:500],
    ]
    url = app.get("job_url") or ""
    if url.startswith("http"):
        cmd.extend(["--job-url", url])
    if dry_run:
        return True, " ".join(cmd)
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode == 0:
        return True, (proc.stdout or "ok").strip()
    return False, (proc.stderr or proc.stdout or "failed").strip()


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Sync applied jobs to Applika")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not APPLIKA.exists():
        print("ERROR: applika CLI not found at ~/.local/bin/applika")
        return 1

    applied = collect_applied()
    existing = list_applika()
    created = skipped = failed = 0

    print(f"Applied in state: {len(applied)} · Already in Applika (approx): checking…\n")
    for app in applied:
        if already_logged(app, existing):
            print(f"  skip (exists): {app['company']} — {app['role']}")
            skipped += 1
            continue
        ok, msg = create_applika(app, dry_run=args.dry_run)
        if ok:
            print(f"  {'would create' if args.dry_run else 'created'}: {app['company']} — {app['role']} ({app['platform']}, {app['date']})")
            if args.dry_run:
                print(f"    {msg}")
            created += 1
            existing.append({"company_name": app["company"], "role": app["role"], "application_date": app["date"]})
        else:
            print(f"  FAILED: {app['company']} — {msg}")
            failed += 1

    print(f"\nSummary: created={created} skipped={skipped} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
