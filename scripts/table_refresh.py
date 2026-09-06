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
    """Run generate_applications.py using persisted table window. Returns True on success."""
    from table_paths import applications_table_path, ensure_table_dirs  # noqa: E402
    from table_window import load_window  # noqa: E402

    ensure_table_dirs()
    li_since, bd_since = load_window()
    out = applications_table_path()
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "generate_applications.py"),
                "--linkedin-since",
                li_since.date().isoformat(),
                "--board-since",
                bd_since.date().isoformat(),
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
