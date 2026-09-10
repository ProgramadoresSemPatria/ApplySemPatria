#!/usr/bin/env python3
"""Run daily job research: LinkedIn collect, board discover, applications table."""

from __future__ import annotations

import argparse
import os
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

# Wall-clock limits for external collect scripts (avoid stuck research-run.json).
STEP_TIMEOUT_SEC = {
    "linkedin_collect": int(os.environ.get("JOBSEARCH_LINKEDIN_COLLECT_TIMEOUT", "3600")),
    "linkedin_jobs_collect": int(os.environ.get("JOBSEARCH_LINKEDIN_JOBS_TIMEOUT", "2700")),
    "discover": int(os.environ.get("JOBSEARCH_DISCOVER_TIMEOUT", "900")),
    "generate_table": int(os.environ.get("JOBSEARCH_TABLE_TIMEOUT", "600")),
}


def _linkedin_steps_planned(*, table_only: bool, skip_linkedin: bool, skip_linkedin_jobs: bool) -> bool:
    if table_only:
        return False
    return not skip_linkedin or not skip_linkedin_jobs


def _ensure_headless_browser(*, step_key: str, steps: list[str], errors: list[str]) -> bool:
    from browser_session import headless_chromium_missing_message, headless_chromium_ready  # noqa: WPS433

    if step_key not in steps:
        steps.append(step_key)
    set_research_step(step_key, detail="checking browser")
    if headless_chromium_ready():
        return True
    msg = headless_chromium_missing_message()
    errors.append(f"{step_key}: {msg}")
    return False


def _run_step(
    cmd: list[str],
    *,
    step_key: str,
    steps: list[str],
    errors: list[str],
    cwd: Path | None = None,
    step_label: str | None = None,
    detail: str = "",
) -> subprocess.CompletedProcess[str] | None:
    label = step_label or step_key
    if label not in steps:
        steps.append(label)
    set_research_step(step_key, detail=detail)
    timeout = STEP_TIMEOUT_SEC.get(step_key, 1800)
    try:
        return subprocess.run(
            cmd,
            cwd=str(cwd or ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        errors.append(f"{step_key}: timed out after {timeout}s")
        return None


def run_daily_research(
    *,
    track: str | None = None,
    since: str | None = None,
    skip_linkedin: bool = False,
    skip_linkedin_jobs: bool = False,
    skip_discover: bool = False,
    table_only: bool = False,
) -> dict[str, Any]:
    """Discover jobs and build today's researched applications snapshot."""
    from table_paths import applications_table_for_day, applications_table_path, ensure_table_dirs  # noqa: E402
    from track_readiness import ready_track_ids  # noqa: E402
    from research_log import default_ingestion_since, has_research, load_log  # noqa: E402
    from track_store import resolve_track  # noqa: E402

    since = since or default_ingestion_since()
    day = today_local()
    ensure_table_dirs()
    steps: list[str] = []
    errors: list[str] = []
    prev_steps: list[str] = []
    if has_research(day):
        prev_steps = list(load_log().get("days", {}).get(day, {}).get("steps") or [])

    try:
        start_research_run(day)
    except Exception as exc:
        from research_log import ResearchRunInProgressError  # noqa: WPS433

        if isinstance(exc, ResearchRunInProgressError):
            return {"ok": False, "message": str(exc), "day": day}
        raise

    try:
        track_ids: list[str] = []

        linkedin_planned = _linkedin_steps_planned(
            table_only=table_only,
            skip_linkedin=skip_linkedin,
            skip_linkedin_jobs=skip_linkedin_jobs,
        )
        linkedin_browser_ok = True
        if linkedin_planned:
            linkedin_browser_ok = _ensure_headless_browser(
                step_key="browser_preflight",
                steps=steps,
                errors=errors,
            )
            if not linkedin_browser_ok:
                msg = "\n".join(errors)
                finish_research_run(ok=False, message=msg)
                return {
                    "ok": False,
                    "message": msg,
                    "day": day,
                    "steps": steps,
                }

        if not table_only:
            if not skip_linkedin:
                li_script = SCRIPTS / "linkedin-deep-collect.sh"
                if li_script.is_file():
                    proc = _run_step(
                        [str(li_script), "--all-queries", "--merge", "--since", since],
                        step_key="linkedin_collect",
                        steps=steps,
                        errors=errors,
                    )
                    if proc is not None and proc.returncode != 0:
                        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
                        errors.append("LinkedIn collect: " + (tail[-1] if tail else f"exit {proc.returncode}"))
                else:
                    errors.append("LinkedIn collect script missing — skipped")

            if not skip_linkedin_jobs:
                li_jobs_script = SCRIPTS / "linkedin-jobs-collect.sh"
                if li_jobs_script.is_file():
                    proc = _run_step(
                        [str(li_jobs_script), "--all-queries", "--merge", "--since", since],
                        step_key="linkedin_jobs_collect",
                        steps=steps,
                        errors=errors,
                    )
                    if proc is not None and proc.returncode != 0:
                        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
                        errors.append("LinkedIn jobs: " + (tail[-1] if tail else f"exit {proc.returncode}"))
                else:
                    errors.append("LinkedIn jobs collect script missing — skipped")

            track_ids = [resolve_track(track)] if track else ready_track_ids("discover")
            if not track_ids:
                msg = "No tracks ready for discovery. Run jobsearch doctor."
                finish_research_run(ok=False, message=msg)
                return {
                    "ok": False,
                    "message": msg,
                    "day": day,
                }

            if not skip_discover:
                for tid in track_ids:
                    proc = _run_step(
                        [PY, str(SCRIPTS / "discover.py"), "--since", since, "--track", tid],
                        step_key="discover",
                        step_label=f"discover:{tid}",
                        detail=tid,
                        steps=steps,
                        errors=errors,
                    )
                    if proc is not None and proc.returncode != 0:
                        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
                        errors.append(f"Discover {tid}: " + (tail[-1] if tail else f"exit {proc.returncode}"))
        else:
            track_ids = [resolve_track(track)] if track else ready_track_ids("discover")
            if not track_ids:
                track_ids = ["ai-engineer"]

        from table_window import save_window_for_day  # noqa: WPS433

        save_window_for_day(day)
        out = applications_table_for_day(day)

        proc = _run_step(
            [
                PY,
                str(SCRIPTS / "generate_applications.py"),
                "--research-day",
                day,
                "--output",
                str(out),
            ],
            step_key="generate_table",
            steps=steps,
            errors=errors,
        )
        if proc is None:
            msg = "\n".join(errors) or "Table generation timed out."
            finish_research_run(ok=False, message=msg)
            return {
                "ok": False,
                "message": msg,
                "day": day,
                "steps": steps,
            }
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

        merged_steps = prev_steps + [s for s in steps if s not in prev_steps]
        mark_research_day(
            day,
            job_count=job_count,
            tracks=track_ids,
            since=since,
            steps=merged_steps,
            catch_up=bool(prev_steps and set(steps) - set(prev_steps)),
        )
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
    parser.add_argument("--skip-linkedin-jobs", action="store_true")
    parser.add_argument(
        "--skip-discover",
        action="store_true",
        help="Skip job-board discover (use with catch-up when posts/jobs already ran)",
    )
    parser.add_argument(
        "--table-only",
        action="store_true",
        help="Regenerate today's apply table from registry only (no new discovery)",
    )
    parser.add_argument(
        "--catch-up-jobs",
        action="store_true",
        help="LinkedIn Jobs collect + refresh table; skip posts scroll and boards",
    )
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

    skip_linkedin = args.skip_linkedin or args.catch_up_jobs or args.table_only
    skip_linkedin_jobs = args.skip_linkedin_jobs or args.table_only
    skip_discover = args.skip_discover or args.catch_up_jobs or args.table_only

    result = run_daily_research(
        track=args.track,
        since=args.since,
        skip_linkedin=skip_linkedin,
        skip_linkedin_jobs=skip_linkedin_jobs,
        skip_discover=skip_discover,
        table_only=args.table_only,
    )
    print(result.get("message", result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
