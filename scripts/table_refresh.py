#!/usr/bin/env python3
"""Regenerate the applications table so the Status column reflects current state.

Called automatically at the end of any apply run (email / dm / followup) so the
table always shows live progress (connect sent · await accept / message sent /
email sent, etc.). Safe/no-op on failure.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


def refresh_applications_table() -> bool:
    """Refresh the latest *researched* day's table (never create a new calendar day)."""
    from research_log import latest_research_day  # noqa: E402
    from table_paths import applications_table_for_day, ensure_table_dirs  # noqa: E402
    day = latest_research_day()
    if not day:
        print("  ○ table refresh skipped — no research day logged yet")
        return False

    ensure_table_dirs()
    out = applications_table_for_day(day)
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "generate_applications.py"),
                "--research-day",
                day,
                "--output",
                str(out),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode == 0:
            print("  ↻ applications table refreshed (Status column updated)")
            return True
        print(f"  ! table refresh failed: {proc.stderr.strip()[:200]}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"  ! table refresh error: {str(exc)[:160]}")
        return False


if __name__ == "__main__":
    refresh_applications_table()
