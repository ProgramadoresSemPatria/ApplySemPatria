"""Local log of days when job research (discover + table) was completed."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
TZ = ZoneInfo("America/Sao_Paulo")
LOG_PATH = ROOT / "state" / "research-log.json"
RUN_PATH = ROOT / "state" / "research-run.json"


def today_local() -> str:
    return datetime.now(TZ).date().isoformat()


def _default_log() -> dict[str, Any]:
    return {"days": {}, "version": 1}


def load_log() -> dict[str, Any]:
    if not LOG_PATH.exists():
        return _default_log()
    try:
        data = json.loads(LOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_log()
    data.setdefault("days", {})
    return data


def save_log(data: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def mark_research_day(day: str | None = None, **meta: Any) -> dict[str, Any]:
    """Record that research completed for ``day`` (default: today local)."""
    day = day or today_local()
    log = load_log()
    entry = {
        "completed_at": datetime.now(TZ).isoformat(),
        **meta,
    }
    log["days"][day] = entry
    save_log(log)
    return entry


def has_research(day: str) -> bool:
    return day in load_log().get("days", {})


def has_research_today() -> bool:
    return has_research(today_local())


def list_research_days() -> list[str]:
    return sorted(load_log().get("days", {}).keys(), reverse=True)


def latest_research_day() -> str | None:
    days = list_research_days()
    return days[0] if days else None


def research_status() -> dict[str, Any]:
    log = load_log()
    days = list_research_days()
    today = today_local()
    last = days[0] if days else None
    last_meta = log.get("days", {}).get(last, {}) if last else {}
    return {
        "today": today,
        "has_research_today": has_research(today),
        "last_research_day": last,
        "last_research_at": last_meta.get("completed_at"),
        "research_days": [
            {
                "day": d,
                "completed_at": log["days"][d].get("completed_at"),
                "job_count": log["days"][d].get("job_count"),
            }
            for d in days
        ],
        "run": research_run_status(),
    }


def _default_run() -> dict[str, Any]:
    return {"running": False, "version": 1}


def load_research_run() -> dict[str, Any]:
    if not RUN_PATH.exists():
        return _default_run()
    try:
        data = json.loads(RUN_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_run()
    return data


def _save_research_run(data: dict[str, Any]) -> None:
    RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUN_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def start_research_run(day: str | None = None) -> None:
    day = day or today_local()
    now = datetime.now(TZ).isoformat()
    _save_research_run(
        {
            "running": True,
            "day": day,
            "step": "starting",
            "detail": "",
            "started_at": now,
            "updated_at": now,
            "version": 1,
        }
    )


def set_research_step(step: str, *, detail: str = "") -> None:
    run = load_research_run()
    if not run.get("running"):
        return
    run["step"] = step
    if detail:
        run["detail"] = detail
    run["updated_at"] = datetime.now(TZ).isoformat()
    _save_research_run(run)


def finish_research_run(*, ok: bool, message: str = "") -> None:
    run = load_research_run()
    run["running"] = False
    run["ok"] = ok
    run["message"] = message
    run["step"] = "done" if ok else "failed"
    run["updated_at"] = datetime.now(TZ).isoformat()
    _save_research_run(run)


def research_run_status() -> dict[str, Any]:
    run = load_research_run()
    return {
        "running": bool(run.get("running")),
        "day": run.get("day"),
        "step": run.get("step"),
        "detail": run.get("detail") or "",
        "started_at": run.get("started_at"),
        "updated_at": run.get("updated_at"),
        "ok": run.get("ok"),
        "message": run.get("message") or "",
    }


def research_status_meta_only() -> dict[str, Any]:
    """Meta fields without nested run progress (for lightweight polling)."""
    status = research_status()
    status.pop("run", None)
    return status


def remove_research_day(day: str) -> None:
    log = load_log()
    log.get("days", {}).pop(day, None)
    save_log(log)


def repair_spurious_snapshot_days() -> list[str]:
    """Drop snapshot files for days without a research log entry."""
    from applications_ui_data import _snapshot_path_for_md  # noqa: WPS433
    from table_paths import APPLICATIONS_TABLES_DIR  # noqa: WPS433

    removed: list[str] = []
    researched = set(list_research_days())
    for md in sorted(APPLICATIONS_TABLES_DIR.glob("applications-*-full.md")):
        m = __import__("re").match(r"applications-(\d{4}-\d{2}-\d{2})-full\.md$", md.name)
        if not m:
            continue
        day = m.group(1)
        if day in researched:
            continue
        js = _snapshot_path_for_md(md)
        md.unlink(missing_ok=True)
        js.unlink(missing_ok=True)
        removed.append(day)
    return removed
