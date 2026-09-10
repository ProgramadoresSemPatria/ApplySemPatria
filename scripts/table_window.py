#!/usr/bin/env python3
"""Applications table scope: one calendar research day per snapshot (not cumulative)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
WINDOW_PATH = ROOT / "state" / "table-window.json"
TZ = ZoneInfo("America/Sao_Paulo")
TABLE_MODE_DAILY = "daily"


def last_monday(when: datetime | None = None) -> datetime:
    """Most recent Monday 00:00 in America/Sao_Paulo."""
    when = when or datetime.now(TZ)
    monday = when - timedelta(days=when.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def day_bounds(day: str) -> tuple[datetime, datetime]:
    """Local [start, end) for one research calendar day."""
    d = date.fromisoformat(day)
    start = datetime(d.year, d.month, d.day, tzinfo=TZ)
    return start, start + timedelta(days=1)


def job_discovered_on_day(job: dict[str, Any], day: str) -> bool:
    """True when registry ``discovered_at`` falls on ``day`` (America/Sao_Paulo)."""
    raw = job.get("discovered_at")
    if not raw:
        return False
    try:
        dt = datetime.fromisoformat(str(raw))
    except ValueError:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    else:
        dt = dt.astimezone(TZ)
    start, end = day_bounds(day)
    return start <= dt < end


def save_window_for_day(day: str) -> None:
    """Persist daily table scope for apply-script refresh."""
    start, _end = day_bounds(day)
    WINDOW_PATH.parent.mkdir(parents=True, exist_ok=True)
    WINDOW_PATH.write_text(
        json.dumps(
            {
                "mode": TABLE_MODE_DAILY,
                "research_day": day,
                "linkedin_since": start.date().isoformat(),
                "board_since": start.date().isoformat(),
                "updated_at": datetime.now(TZ).isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def load_research_day() -> str | None:
    if not WINDOW_PATH.exists():
        return None
    try:
        data = json.loads(WINDOW_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    day = data.get("research_day")
    if isinstance(day, str) and day:
        return day
    legacy = data.get("linkedin_since")
    return legacy if isinstance(legacy, str) and legacy else None


def save_window(*, linkedin_since: datetime, board_since: datetime) -> None:
    """Legacy alias — treats since date as a single research day."""
    save_window_for_day(linkedin_since.date().isoformat())


def load_window() -> tuple[datetime, datetime]:
    day = load_research_day()
    if day:
        return day_bounds(day)
    mon = last_monday()
    return mon, mon + timedelta(days=1)


def table_since() -> datetime:
    """Start of the current research-day window (for --table-only apply scripts)."""
    return load_window()[0]
