"""Local log of days when job research (discover + table) was completed."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
TZ = ZoneInfo("America/Sao_Paulo")
LOG_PATH = ROOT / "state" / "research-log.json"
INGESTION_HISTORY_PATH = ROOT / "state" / "ingestion-history.json"
RUN_PATH = ROOT / "state" / "research-run.json"
STALE_RUN_MINUTES = 25
DEFAULT_INGESTION_LOOKBACK_DAYS = 7


class ResearchRunInProgressError(RuntimeError):
    """Raised when a research run is already active and not stale."""


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


def _default_ingestion_history() -> dict[str, Any]:
    return {"entries": [], "version": 1}


def load_ingestion_history() -> dict[str, Any]:
    if not INGESTION_HISTORY_PATH.exists():
        return _default_ingestion_history()
    try:
        data = json.loads(INGESTION_HISTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_ingestion_history()
    data.setdefault("entries", [])
    return data


def ensure_ingestion_history_migrated() -> dict[str, Any]:
    """One-time backfill from research-log.json when history file is missing."""
    if INGESTION_HISTORY_PATH.exists():
        return load_ingestion_history()
    return _backfill_ingestion_history_from_log()


def save_ingestion_history(data: dict[str, Any]) -> None:
    INGESTION_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    INGESTION_HISTORY_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _backfill_ingestion_history_from_log() -> dict[str, Any]:
    """One-time migration from research-log.json day entries."""
    log = load_log()
    entries: list[dict[str, Any]] = []
    for day, meta in log.get("days", {}).items():
        completed_at = meta.get("completed_at")
        if not completed_at:
            continue
        entries.append(
            {
                "day": day,
                "completed_at": completed_at,
                "job_count": meta.get("job_count"),
                "since": meta.get("since"),
            }
        )
    entries.sort(key=lambda e: e["completed_at"])
    data = {"entries": entries, "version": 1}
    if entries:
        save_ingestion_history(data)
    return data


def append_ingestion_record(day: str, entry: dict[str, Any]) -> dict[str, Any]:
    """Append one completed ingestion (every run, including same-day catch-up)."""
    hist = load_ingestion_history()
    record = {
        "day": day,
        "completed_at": entry.get("completed_at") or datetime.now(TZ).isoformat(),
        "job_count": entry.get("job_count"),
        "since": entry.get("since"),
    }
    hist.setdefault("entries", []).append(record)
    save_ingestion_history(hist)
    return record


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
    append_ingestion_record(day, entry)
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


def last_ingestion_completed_at() -> datetime | None:
    """Timestamp of the most recent completed ingestion."""
    log = load_log()
    today = today_local()
    if has_research(today):
        latest: datetime | None = None
        for entry in load_ingestion_history().get("entries", []):
            if entry.get("day") != today:
                continue
            ts = _parse_run_timestamp(entry.get("completed_at"))
            if ts is not None and (latest is None or ts > latest):
                latest = ts
        if latest is not None:
            return latest
    days = list_research_days()
    if not days:
        return None
    raw = log.get("days", {}).get(days[0], {}).get("completed_at")
    return _parse_run_timestamp(raw)


def ingestion_since_datetime(*, now: datetime | None = None) -> datetime:
    """Collect from last ingestion completion, or 7 days ago when none."""
    now = now or datetime.now(TZ)
    last = last_ingestion_completed_at()
    if last is None:
        return now - timedelta(days=DEFAULT_INGESTION_LOOKBACK_DAYS)
    return last


def default_ingestion_since(*, now: datetime | None = None) -> str:
    """``since`` flag for collect/discover scripts."""
    last = last_ingestion_completed_at()
    if last is None:
        return f"{DEFAULT_INGESTION_LOOKBACK_DAYS}d"
    return ingestion_since_datetime(now=now).isoformat()


def ingestion_window_meta(*, now: datetime | None = None) -> dict[str, Any]:
    """UI + API fields describing the next ingestion window."""
    now = now or datetime.now(TZ)
    last_at = last_ingestion_completed_at()
    since_dt = ingestion_since_datetime(now=now)
    last_day = latest_research_day()
    if last_at is None:
        return {
            "ingestion_has_prior": False,
            "ingestion_last_at": None,
            "ingestion_last_day": None,
            "ingestion_since_at": since_dt.isoformat(),
            "ingestion_since": f"{DEFAULT_INGESTION_LOOKBACK_DAYS}d",
        }
    return {
        "ingestion_has_prior": True,
        "ingestion_last_at": last_at.isoformat(),
        "ingestion_last_day": last_day,
        "ingestion_since_at": since_dt.isoformat(),
        "ingestion_since": since_dt.isoformat(),
    }


def research_status() -> dict[str, Any]:
    ensure_ingestion_history_migrated()
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
        **ingestion_window_meta(),
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


def _parse_run_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def research_run_is_stale(run: dict[str, Any] | None = None) -> bool:
    """True when a run is marked running but has not updated recently."""
    run = run or load_research_run()
    if not run.get("running"):
        return False
    ts = _parse_run_timestamp(run.get("updated_at")) or _parse_run_timestamp(run.get("started_at"))
    if ts is None:
        return True
    age_sec = (datetime.now(TZ) - ts).total_seconds()
    return age_sec > STALE_RUN_MINUTES * 60


def clear_stale_research_run(*, reason: str = "") -> bool:
    """Mark a stuck run as failed so a new research can start."""
    run = load_research_run()
    if not run.get("running") or not research_run_is_stale(run):
        return False
    finish_research_run(
        ok=False,
        message=reason or "Previous research run timed out or was interrupted.",
    )
    return True


def start_research_run(day: str | None = None, *, force: bool = False) -> None:
    day = day or today_local()
    run = load_research_run()
    if run.get("running"):
        if research_run_is_stale(run):
            clear_stale_research_run(reason="Stale research run cleared — starting fresh.")
        elif not force:
            raise ResearchRunInProgressError(
                "Research is already running. Wait for it to finish or retry after "
                f"{STALE_RUN_MINUTES} minutes without progress."
            )
        else:
            finish_research_run(ok=False, message="Previous research run replaced.")
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
    """Drop research log entry, ingestion history, and snapshot files for ``day``."""
    log = load_log()
    log.get("days", {}).pop(day, None)
    save_log(log)

    hist = load_ingestion_history()
    hist["entries"] = [e for e in hist.get("entries", []) if e.get("day") != day]
    save_ingestion_history(hist)

    from applications_ui_data import _snapshot_path_for_md  # noqa: WPS433
    from table_paths import APPLICATIONS_TABLES_DIR  # noqa: WPS433

    for md in APPLICATIONS_TABLES_DIR.glob(f"applications-{day}-full.md"):
        js = _snapshot_path_for_md(md)
        md.unlink(missing_ok=True)
        js.unlink(missing_ok=True)

    run = load_research_run()
    if run.get("day") == day:
        _save_research_run(_default_run())


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
