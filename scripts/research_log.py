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
    }


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
