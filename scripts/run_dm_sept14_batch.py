#!/usr/bin/env python3
"""Run connect → check → send for Sept 14–23 DM window (no UI 10m phase timeout)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
PY = ROOT / ".venv/bin/python"
KEYS_PATH = ROOT / "runs" / "dm-sept14-23-keys.json"
LOG_PATH = ROOT / "runs" / "dm-sept14-23-run-direct.log"
TZ = ZoneInfo("America/Sao_Paulo")


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["JOBSEARCH_UI_APPROVED"] = "1"
    return env


def _run(label: str, script: str, extra: list[str], *, chunk_size: int = 12) -> int:
    keys = json.loads(KEYS_PATH.read_text(encoding="utf-8"))
    rc = 0
    for start in range(0, len(keys), chunk_size):
        chunk = keys[start : start + chunk_size]
        cmd = [
            str(PY),
            str(SCRIPTS / script),
            *extra,
            "--track",
            "ai-engineer",
            "--job-keys",
            ",".join(chunk),
        ]
        line = (
            f"\n[{datetime.now(TZ).isoformat()}] ▶ {label} "
            f"chunk {start // chunk_size + 1}/{(len(keys) + chunk_size - 1) // chunk_size} "
            f"({len(chunk)} keys)\n"
        )
        print(line, flush=True)
        with LOG_PATH.open("a", encoding="utf-8") as log:
            log.write(line)
            log.flush()
            proc = subprocess.run(cmd, cwd=str(SCRIPTS), env=_env(), stdout=log, stderr=subprocess.STDOUT)
        if proc.returncode != 0:
            rc = proc.returncode
    return rc


def main() -> int:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    phases = [
        (
            "send_connections",
            "dm_apply.py",
            ["--send", "--ui-approved", "--force-send"],
        ),
        (
            "check_connections",
            "dm_followup.py",
            ["--ui-approved", "--phase", "check"],
        ),
        (
            "send_messages",
            "dm_followup.py",
            ["--send", "--ui-approved", "--force-send", "--phase", "send"],
        ),
    ]
    rc = 0
    for label, script, extra in phases:
        code = _run(label, script, extra)
        if code != 0:
            print(f"{label} exited {code}", file=sys.stderr, flush=True)
            rc = code
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
