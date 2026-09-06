#!/usr/bin/env python3
"""Remove blacklisted jobs from the registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from filters import job_is_blacklisted  # noqa: E402
from registry import REGISTRY_PATH, load_registry, save_registry  # noqa: E402


def purge_registry(dry_run: bool = False) -> dict:
    registry = load_registry()
    jobs = registry.get("jobs", [])
    before_count = len(jobs)
    kept = []
    removed = []

    for job in jobs:
        blocked, reason = job_is_blacklisted(job)
        if blocked:
            removed.append({**job, "blacklist_reason": reason})
        else:
            kept.append(job)

    if not dry_run:
        registry["jobs"] = kept
        save_registry(registry)

    return {
        "registry_path": str(REGISTRY_PATH),
        "before": before_count,
        "removed": len(removed),
        "after": len(kept),
        "removed_jobs": [
            {
                "company": j.get("company"),
                "role": j.get("role"),
                "url": j.get("url"),
                "reason": j.get("blacklist_reason"),
            }
            for j in removed
        ],
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge blacklisted domains from jobs registry.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = purge_registry(dry_run=args.dry_run)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Registry: {result['registry_path']}")
        print(f"Before: {result['before']} | Removed: {result['removed']} | After: {result['after']}")
        for job in result["removed_jobs"]:
            print(f"  - [{job['reason']}] {job['role']} @ {job['company']}")
            print(f"    {job['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
