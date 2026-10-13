"""Redacted debug report for maintainers (no secrets, registry, or resumes)."""

from __future__ import annotations

import re
import subprocess
from typing import Any

from retrieval._paths import ROOT

_URL_RE = re.compile(r"https?://\S+")


def sanitize_text(text: str, *, max_len: int = 500) -> str:
    cleaned = _URL_RE.sub("<url>", text or "")
    cleaned = cleaned.replace("\n", " ").strip()
    return cleaned[:max_len]


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    head = ROOT / ".git" / "HEAD"
    if head.is_file():
        return head.read_text(encoding="utf-8").strip()[:40]
    return "unknown"


def _git_branch() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "unknown"


def build_debug_report() -> dict[str, Any]:
    from research_log import load_research_run, today_local  # noqa: WPS433

    day = today_local()
    audit_tail: list[str] = []
    audit_path = ROOT / "logs" / f"audit-{day}.jsonl"
    if audit_path.is_file():
        lines = audit_path.read_text(encoding="utf-8").splitlines()
        audit_tail = lines[-40:]

    run = load_research_run()
    run_public = {
        k: run.get(k)
        for k in ("running", "day", "step", "ok", "started_at", "updated_at")
    }
    if run.get("message"):
        run_public["message"] = sanitize_text(str(run["message"]), max_len=500)

    return {
        "schema": 1,
        "kind": "applysempatria_debug_report",
        "day": day,
        "git_head": _git_head(),
        "git_branch": _git_branch(),
        "research_run": run_public,
        "audit_tail": audit_tail,
    }
