#!/usr/bin/env python3
"""Generic applicant-profile store: get/set fields, list missing required fields.

Profiles are per-track (see tracks.json). When a needed field is empty, the
agent asks the user and persists the answer here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from track_store import default_track_id, load_profile, resolve_track, save_profile, track_path  # noqa: E402

REQUIRED_FOR_FORMS = [
    "full_name",
    "email",
    "phone",
    "location",
    "linkedin_url",
    "years_experience",
    "salary_expectation_usd",
    "notice_period",
    "work_authorization",
    "resume_path",
]


def missing(track_id: str | None = None) -> list[str]:
    data = load_profile(track_id)
    return [k for k in REQUIRED_FOR_FORMS if not str(data.get(k, "")).strip()]


def get(key: str, track_id: str | None = None) -> str:
    val = load_profile(track_id).get(key)
    return "" if val is None else str(val)


def set_field(key: str, value: str, track_id: str | None = None) -> None:
    tid = resolve_track(track_id)
    data = load_profile(tid)
    data[key] = value
    save_profile(tid, data)


def main() -> int:
    parser = argparse.ArgumentParser(description="Applicant profile store (per track)")
    parser.add_argument("--track", default=None, help=f"Track id (default: {default_track_id()})")
    sub = parser.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("get")
    g.add_argument("key")

    s = sub.add_parser("set")
    s.add_argument("key")
    s.add_argument("value")

    sub.add_parser("missing")
    sub.add_parser("show")
    sub.add_parser("path")

    args = parser.parse_args()
    tid = resolve_track(args.track)

    if args.cmd == "get":
        print(get(args.key, tid))
    elif args.cmd == "set":
        set_field(args.key, args.value, tid)
        print(f"[{tid}] set {args.key} = {args.value}")
    elif args.cmd == "missing":
        miss = missing(tid)
        if miss:
            print(f"[{tid}] missing: {', '.join(miss)}")
        else:
            print(f"[{tid}] profile complete for forms")
    elif args.cmd == "show":
        print(json.dumps(load_profile(tid), indent=2, ensure_ascii=False))
    elif args.cmd == "path":
        print(track_path(tid, "profile_path"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
