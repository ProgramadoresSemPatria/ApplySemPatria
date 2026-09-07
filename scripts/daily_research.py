#!/usr/bin/env python3
"""Run daily job research: LinkedIn collect, board discover, applications table."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from research_log import (  # noqa: E402
    finish_research_run,
    mark_research_day,
    set_research_step,
    start_research_run,
    today_local,
)


def _resolve_python() -> str:
    for rel in (".venv/bin/python", ".venv-test/bin/python"):
        candidate = ROOT / rel
        if candidate.is_file():
            return str(candidate)
    return sys.executable


PY = _resolve_python()


def run_daily_research(
    *,
    track: str | None = None,
    since: str = "7d",
    skip_linkedin: bool = False,
) -> dict[str, Any]:
    """Discover jobs and build today's researched applications snapshot."""
    from table_paths import applications_table_path, ensure_table_dirs  # noqa: E402
    from table_window import load_window, save_window  # noqa: E402
    from track_readiness import ready_track_ids  # noqa: E402
    from track_store import resolve_track  # noqa: E402

    day = today_local()
    ensure_table_dirs()
    steps: list[str] = []
    errors: list[str] = []
    start_research_run(day)

    try:
        if not skip_linkedin:
            li_script = SCRIPTS / "linkedin-deep-collect.sh"
            if li_script.is_file():
                steps.append("linkedin_collect")
                set_research_step("linkedin_collect")
                proc = subprocess.run(
                    [str(li_script), "--all-queries", "--merge", "--since", since],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                )
                if proc.returncode != 0:
                    tail = (proc.stderr or proc.stdout or "").strip().splitlines()
                    errors.append("LinkedIn collect: " + (tail[-1] if tail else f"exit {proc.returncode}"))
            else:
                errors.append("LinkedIn collect script missing — skipped")

        track_ids = [resolve_track(track)] if track else ready_track_ids("discover")
        if not track_ids:
            msg = "No tracks ready for discovery. Run jobsearch doctor."
            finish_research_run(ok=False, message=msg)
            return {
                "ok": False,
                "message": msg,
                "day": day,
            }

        for tid in track_ids:
            steps.append(f"discover:{tid}")
            set_research_step("discover", detail=tid)
            proc = subprocess.run(
                [PY, str(SCRIPTS / "discover.py"), "--since", since, "--track", tid],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                tail = (proc.stderr or proc.stdout or "").strip().splitlines()
                errors.append(f"Discover {tid}: " + (tail[-1] if tail else f"exit {proc.returncode}"))

        li_since, bd_since = load_window()
        save_window(linkedin_since=li_since, board_since=bd_since)
        out = applications_table_path()

        steps.append("generate_table")
        set_research_step("generate_table")
        proc = subprocess.run(
            [
                PY,
                str(SCRIPTS / "generate_applications.py"),
                "--linkedin-since",
                li_since.date().isoformat(),
                "--board-since",
                bd_since.date().isoformat(),
                "--output",
                str(out),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()
            errors.append("Table: " + (tail[-1] if tail else f"exit {proc.returncode}"))
            msg = "\n".join(errors)
            finish_research_run(ok=False, message=msg)
            return {
                "ok": False,
                "message": msg,
                "day": day,
                "steps": steps,
            }

        job_count = 0
        try:
            import json

            snap = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
            job_count = len(snap.get("jobs", []))
        except (OSError, json.JSONDecodeError):
            pass

        mark_research_day(day, job_count=job_count, tracks=track_ids, since=since, steps=steps)
        msg = f"Research complete for {day}: {job_count} roles in apply table."
        if errors:
            msg += "\nWarnings:\n" + "\n".join(errors)
        finish_research_run(ok=True, message=msg)
        return {
            "ok": True,
            "message": msg,
            "day": day,
            "job_count": job_count,
            "steps": steps,
            "warnings": errors,
        }
    except Exception as exc:  # noqa: BLE001
        msg = f"Research error: {exc}"
        finish_research_run(ok=False, message=msg)
        return {"ok": False, "message": msg, "day": day, "steps": steps}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run daily job research pipeline")
    parser.add_argument("--track", default=None)
    parser.add_argument("--since", default="7d")
    parser.add_argument("--skip-linkedin", action="store_true")
    parser.add_argument("--repair-snapshots", action="store_true", help="Remove snapshot files without research log entry")
    args = parser.parse_args()

    if args.repair_snapshots:
        from research_log import repair_spurious_snapshot_days  # noqa: WPS433

        removed = repair_spurious_snapshot_days()
        if removed:
            print("Removed spurious snapshot days:", ", ".join(removed))
        else:
            print("No spurious snapshot days to remove.")
        return 0

    result = run_daily_research(
        track=args.track,
        since=args.since,
        skip_linkedin=args.skip_linkedin,
    )
    print(result.get("message", result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
