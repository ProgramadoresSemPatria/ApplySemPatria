#!/usr/bin/env python3
"""Canonical paths for generated markdown tables."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
RUNS_DIR = ROOT / "runs"
TABLES_DIR = RUNS_DIR / "tables"
APPLICATIONS_TABLES_DIR = TABLES_DIR / "applications"
DISCOVERY_TABLES_DIR = TABLES_DIR / "discovery"

TZ = ZoneInfo("America/Sao_Paulo")


def ensure_table_dirs() -> None:
    APPLICATIONS_TABLES_DIR.mkdir(parents=True, exist_ok=True)
    DISCOVERY_TABLES_DIR.mkdir(parents=True, exist_ok=True)


def applications_table_path(
    when: datetime | None = None,
    *,
    suffix: str = "full",
) -> Path:
    """Live apply table for a given day. Default suffix: full."""
    when = when or datetime.now(TZ)
    return APPLICATIONS_TABLES_DIR / f"applications-{when.strftime('%Y-%m-%d')}-{suffix}.md"


def latest_applications_table(*, suffix: str = "full") -> Path | None:
    """Most recent applications table file, or None."""
    ensure_table_dirs()
    matches = sorted(APPLICATIONS_TABLES_DIR.glob(f"applications-*-{suffix}.md"))
    return matches[-1] if matches else None
