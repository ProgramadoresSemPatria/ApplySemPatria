#!/usr/bin/env python3
"""Job discovery orchestrator — collects, filters, dedupes, writes run report."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from collectors import COLLECTORS  # noqa: E402
from filters import evaluate_job  # noqa: E402
from registry import (  # noqa: E402
    LOCAL_TZ,
    RUNS_DIR,
    STATE_PATH,
    load_json,
    load_registry,
    merge_jobs,
    parse_since,
    save_json,
    save_registry,
    write_run_markdown,
)

from track_store import load_board_config, list_track_ids, resolve_track, stamp_track  # noqa: E402


def load_config(track_id: str | None = None) -> dict:
    return load_board_config(track_id)


def run_discovery(
    since_arg: str | None,
    dry_run: bool = False,
    *,
    track_id: str | None = None,
    all_tracks: bool = False,
) -> dict:
    track_ids = list_track_ids() if all_tracks else [resolve_track(track_id)]
    state = load_json(STATE_PATH, {"last_run_at": None})
    since = parse_since(since_arg, state.get("last_run_at"))
    registry = load_registry()

    all_incoming: list[dict] = []
    source_stats: dict[str, dict] = {}
    errors: list[str] = []

    for tid in track_ids:
        config = load_board_config(tid)
        for name, collector in COLLECTORS.items():
            source_cfg = config.get("sources", {}).get(name, {})
            stat_key = f"{tid}/{name}" if all_tracks else name
            if not source_cfg.get("enabled", True):
                source_stats[stat_key] = {"fetched": 0, "new": 0, "eligible": 0, "skipped": True, "track": tid}
                continue

            source_stats[stat_key] = {"fetched": 0, "new": 0, "eligible": 0, "error": None, "track": tid}
            try:
                fetched = [stamp_track(j, tid) for j in collector(config)]
                for job in fetched:
                    evaluate_job(job, config)
                source_stats[stat_key]["fetched"] = len(fetched)
                all_incoming.extend(fetched)
            except Exception as exc:  # noqa: BLE001 — report per-source failures
                msg = f"{tid}/{name}: {exc}"
                errors.append(msg)
                source_stats[stat_key]["error"] = str(exc)
                if dry_run:
                    traceback.print_exc()

    registry, new_jobs = merge_jobs(registry, all_incoming, since)

    for job in new_jobs:
        stats_key = f"{job.get('track', '')}/{job.get('source', '')}" if all_tracks else job.get("source", "")
        stats = source_stats.get(stats_key) or source_stats.get(job.get("source", ""), {})
        stats["new"] = stats.get("new", 0) + 1
        if job.get("filter_result") == "eligible":
            stats["eligible"] = stats.get("eligible", 0) + 1

    now = datetime.now(LOCAL_TZ)
    run_name = now.strftime("%Y-%m-%dT%H-%M")
    run_path = RUNS_DIR / f"{run_name}.md"

    if not dry_run:
        save_registry(registry)
        write_run_markdown(run_path, since, new_jobs, source_stats, errors)
        save_json(STATE_PATH, {"last_run_at": now.isoformat()})

    eligible = [j for j in new_jobs if j.get("filter_result") == "eligible"]
    skipped = [j for j in new_jobs if j.get("filter_result") == "skipped"]

    return {
        "since": since.isoformat(),
        "tracks": track_ids,
        "run_path": str(run_path),
        "registry_path": str(ROOT / "registry" / "jobs.json"),
        "new_total": len(new_jobs),
        "eligible": len(eligible),
        "skipped": len(skipped),
        "needs_review": len([j for j in new_jobs if j.get("filter_result") == "needs_review"]),
        "source_stats": source_stats,
        "errors": errors,
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover AI Engineer jobs from configured sources.")
    parser.add_argument(
        "--since",
        default="last-run",
        help='Time window: "last-run" (default), "24h", "7d", or ISO date like 2026-08-20',
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write registry, state, or run file.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary.")
    parser.add_argument("--track", default=None, help="Track id (default from tracks.json)")
    parser.add_argument("--all-tracks", action="store_true", help="Discover for every configured track")
    args = parser.parse_args()

    result = run_discovery(
        args.since,
        dry_run=args.dry_run,
        track_id=args.track,
        all_tracks=args.all_tracks,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Job discovery — since {result['since']}")
        print(f"New: {result['new_total']} | Eligible: {result['eligible']} | Skipped: {result['skipped']}")
        if result["errors"]:
            print("Errors:")
            for err in result["errors"]:
                print(f"  - {err}")
        print(f"Run file: {result['run_path']}")
        print(f"Registry: {result['registry_path']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
