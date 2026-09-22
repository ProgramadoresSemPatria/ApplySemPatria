"""Manual applied tag + Applika sync status for UI cards."""

from __future__ import annotations

import sys

from retrieval._paths import ROOT, SCRIPTS

sys.path.insert(0, str(SCRIPTS))
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
APPLIED_PATH = ROOT / "state" / "applied-applications.json"
TZ = ZoneInfo("America/Sao_Paulo")

APPLIKA_SENT = "sent"
APPLIKA_ERROR = "error"
APPLIKA_PENDING = "pending"
APPLIKA_SKIPPED = "skipped"


def _load_data() -> dict[str, Any]:
    if not APPLIED_PATH.is_file():
        return {"entries": {}}
    try:
        data = json.loads(APPLIED_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"entries": {}}
    if not isinstance(data.get("entries"), dict):
        data["entries"] = {}
    return data


def _save_data(data: dict[str, Any]) -> None:
    APPLIED_PATH.parent.mkdir(parents=True, exist_ok=True)
    APPLIED_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_applied_entries() -> dict[str, dict[str, Any]]:
    return dict(_load_data().get("entries") or {})


def get_entry(job_key: str) -> dict[str, Any]:
    return dict(load_applied_entries().get((job_key or "").strip(), {}))


def is_tagged(job_key: str) -> bool:
    return bool(get_entry(job_key).get("tagged_at"))


def tag_job(job_key: str) -> dict[str, Any]:
    key = (job_key or "").strip()
    if not key:
        raise ValueError("job_key required")
    data = _load_data()
    entries = data.setdefault("entries", {})
    row = dict(entries.get(key) or {})
    if not row.get("tagged_at"):
        row["tagged_at"] = datetime.now(TZ).isoformat()
    entries[key] = row
    _save_data(data)
    return row


def set_applika_result(
    job_key: str,
    *,
    status: str,
    error: str | None = None,
    sent_at: str | None = None,
) -> dict[str, Any]:
    key = (job_key or "").strip()
    data = _load_data()
    entries = data.setdefault("entries", {})
    row = dict(entries.get(key) or {})
    if not row.get("tagged_at"):
        row["tagged_at"] = datetime.now(TZ).isoformat()
    row["applika_status"] = status
    row["applika_error"] = (error or "").strip() or None
    if status == APPLIKA_SENT:
        row["applika_sent_at"] = sent_at or datetime.now(TZ).isoformat()
        row["applika_error"] = None
    entries[key] = row
    _save_data(data)
    return row
