"""Append-only daily audit logs for pipeline behavior, debugging, and test verification.

Each calendar day gets one JSONL file under ``logs/audit-YYYY-MM-DD.jsonl``.
Set ``JOBSEARCH_AUDIT_LOG=0`` to disable. Override directory with
``JOBSEARCH_AUDIT_LOG_DIR`` (or legacy ``JOBSEARCH_AUDIT_DIR``).
"""

from __future__ import annotations

import sys

from retrieval._paths import ROOT, SCRIPTS

sys.path.insert(0, str(SCRIPTS))
import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")

_lock = threading.Lock()
_configured_dir: Path | None = None
_enabled: bool | None = None


def reset_audit_log(*, enabled: bool | None = None, log_dir: Path | None = None) -> None:
    """Reset cached config (tests). Pass ``enabled=False`` to disable for one run."""
    global _enabled, _configured_dir
    _enabled = enabled
    _configured_dir = log_dir


def _is_enabled() -> bool:
    global _enabled
    if _enabled is None:
        raw = os.environ.get("JOBSEARCH_AUDIT_LOG", "1").strip().lower()
        _enabled = raw not in ("0", "false", "no", "off")
    return _enabled


def audit_dir() -> Path:
    global _configured_dir
    if _configured_dir is None:
        override = os.environ.get("JOBSEARCH_AUDIT_LOG_DIR") or os.environ.get("JOBSEARCH_AUDIT_DIR")
        _configured_dir = Path(override) if override else ROOT / "logs"
    return _configured_dir


def log_path(day: str | None = None) -> Path:
    """Path to the audit file for ``day`` (default: today local)."""
    day = day or datetime.now(TZ).date().isoformat()
    return audit_dir() / f"audit-{day}.jsonl"


def _json_safe(value: Any) -> Any:
    """Coerce values (datetime, Path, …) into JSON-serializable form."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return str(value)


def _emit(level: str, component: str, event: str, **data: Any) -> None:
    if not _is_enabled():
        return
    record: dict[str, Any] = {
        "ts": datetime.now(TZ).isoformat(),
        "level": level.upper(),
        "component": component,
        "event": event,
    }
    if data:
        record["data"] = _json_safe(data)
    line = json.dumps(record, ensure_ascii=False)
    path = log_path()
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def debug(component: str, event: str, **data: Any) -> None:
    _emit("DEBUG", component, event, **data)


def info(component: str, event: str, **data: Any) -> None:
    _emit("INFO", component, event, **data)


def warn(component: str, event: str, **data: Any) -> None:
    _emit("WARN", component, event, **data)


def error(component: str, event: str, **data: Any) -> None:
    _emit("ERROR", component, event, **data)


@contextmanager
def step(component: str, step_name: str, **start_data: Any) -> Iterator[dict[str, Any]]:
    """Log ``step_start`` / ``step_done`` / ``step_failed`` with ``duration_ms``."""
    ctx: dict[str, Any] = {}
    info(component, "step_start", step=step_name, **start_data)
    t0 = time.monotonic()
    try:
        yield ctx
        duration_ms = int((time.monotonic() - t0) * 1000)
        done_data = {**start_data, **ctx, "duration_ms": duration_ms}
        info(component, "step_done", step=step_name, **done_data)
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        error(
            component,
            "step_failed",
            step=step_name,
            duration_ms=duration_ms,
            error=str(exc),
            **start_data,
        )
        raise


def read_log(day: str | None = None) -> list[dict[str, Any]]:
    """Return all audit records for ``day`` (empty list when file missing)."""
    path = log_path(day)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def events_for(
    day: str | None = None,
    *,
    component: str | None = None,
    event: str | None = None,
) -> list[dict[str, Any]]:
    """Filter ``read_log`` by component and/or event name."""
    out = read_log(day)
    if component:
        out = [r for r in out if r.get("component") == component]
    if event:
        out = [r for r in out if r.get("event") == event]
    return out


class AuditLogger:
    """Component-scoped helper."""

    __slots__ = ("component",)

    def __init__(self, component: str) -> None:
        self.component = component

    def debug(self, event: str, **data: Any) -> None:
        debug(self.component, event, **data)

    def info(self, event: str, **data: Any) -> None:
        info(self.component, event, **data)

    def warn(self, event: str, **data: Any) -> None:
        warn(self.component, event, **data)

    def error(self, event: str, **data: Any) -> None:
        error(self.component, event, **data)

    @contextmanager
    def step(self, step_name: str, **start_data: Any) -> Iterator[dict[str, Any]]:
        with step(self.component, step_name, **start_data) as ctx:
            yield ctx


def get_logger(component: str) -> AuditLogger:
    return AuditLogger(component)
