#!/usr/bin/env python3
"""Shared applications-table date window (persisted for refresh + apply scripts)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
WINDOW_PATH = ROOT / "state" / "table-window.json"
TZ = ZoneInfo("America/Sao_Paulo")


def last_monday(when: datetime | None = None) -> datetime:
    """Most recent Monday 00:00 in America/Sao_Paulo."""
    when = when or datetime.now(TZ)
    monday = when - timedelta(days=when.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def save_window(*, linkedin_since: datetime, board_since: datetime) -> None:
    WINDOW_PATH.parent.mkdir(parents=True, exist_ok=True)
    WINDOW_PATH.write_text(
        json.dumps(
            {
                "linkedin_since": linkedin_since.date().isoformat(),
                "board_since": board_since.date().isoformat(),
                "updated_at": datetime.now(TZ).isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def load_window() -> tuple[datetime, datetime]:
    if WINDOW_PATH.exists():
        data = json.loads(WINDOW_PATH.read_text(encoding="utf-8"))
        li = datetime.fromisoformat(data["linkedin_since"]).replace(tzinfo=TZ)
        bd = datetime.fromisoformat(data["board_since"]).replace(tzinfo=TZ)
        return li, bd
    mon = last_monday()
    return mon, mon


def table_since() -> datetime:
    """LinkedIn/board filter date for --table-only apply scripts."""
    return load_window()[0]
