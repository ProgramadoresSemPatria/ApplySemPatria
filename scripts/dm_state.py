#!/usr/bin/env python3
"""DM pipeline state: per-profile connect -> accept -> message tracking.

State file: state/dm-applications.json

New schema:
{
  "profiles": {
    "<normalized profile_url>": {
      "company": "...", "role": "...", "job_key": "...",
      "profile_url": "https://www.linkedin.com/in/slug/",
      "connect_requested_at": "iso|null",
      "accepted_at": "iso|null",          # detected 1st-degree after a request
      "message_sent_at": "iso|null",
      "already_connected": false          # true if we messaged an existing connection directly
    }
  }
}

Status derivation (see status_for):
  not_started            -> nothing done
  connect_pending        -> request sent, not yet accepted
  accepted_msg_pending   -> accepted, message not sent yet
  message_sent           -> done
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
STATE_PATH = ROOT / "state" / "dm-applications.json"
TZ = ZoneInfo("America/Sao_Paulo")

STATUS_NONE = "not_started"
STATUS_CONNECT_PENDING = "connect_pending"
STATUS_ACCEPTED_MSG_PENDING = "accepted_msg_pending"
STATUS_MESSAGE_SENT = "message_sent"

STATUS_LABELS = {
    STATUS_NONE: "—",
    STATUS_CONNECT_PENDING: "connect sent · await accept",
    STATUS_ACCEPTED_MSG_PENDING: "accepted · msg pending",
    STATUS_MESSAGE_SENT: "message sent",
}


def normalize_profile_url(url: str) -> str:
    """Canonical key: lowercase host+path, no trailing slash, strip query/fragment."""
    if not url:
        return ""
    u = url.strip().split("?")[0].split("#")[0]
    u = u.rstrip("/")
    return u.lower()


def _now() -> str:
    return datetime.now(TZ).isoformat()


def load() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"profiles": {}}
    data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if "profiles" in data:
        return data
    # Migrate legacy {"actions": [...]} format.
    migrated: dict[str, Any] = {"profiles": {}}
    for a in data.get("actions", []):
        prof = a.get("profile_url") or ""
        key = normalize_profile_url(prof)
        if not key:
            continue
        branch = a.get("branch", "")
        entry = migrated["profiles"].setdefault(
            key,
            {
                "company": a.get("company"),
                "role": a.get("role"),
                "job_key": a.get("job_key"),
                "profile_url": prof,
                "connect_requested_at": None,
                "accepted_at": None,
                "message_sent_at": None,
                "already_connected": False,
            },
        )
        if branch == "already_connected_message":
            entry["already_connected"] = True
            entry["message_sent_at"] = a.get("at")
            entry["accepted_at"] = a.get("at")
        else:  # connect_top_card / connect_via_more_menu
            entry["connect_requested_at"] = a.get("at")
    return migrated


def save(data: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _entry(data: dict[str, Any], job: dict[str, Any] | None, profile_url: str) -> dict[str, Any]:
    key = normalize_profile_url(profile_url)
    entry = data["profiles"].get(key)
    if entry is None:
        entry = {
            "company": (job or {}).get("company"),
            "role": (job or {}).get("role"),
            "job_key": (job or {}).get("job_key"),
            "profile_url": profile_url,
            "connect_requested_at": None,
            "accepted_at": None,
            "message_sent_at": None,
            "already_connected": False,
        }
        data["profiles"][key] = entry
    return entry


def record_connect(data: dict[str, Any], job: dict[str, Any], profile_url: str) -> None:
    e = _entry(data, job, profile_url)
    e["connect_requested_at"] = _now()


def record_message(
    data: dict[str, Any],
    job: dict[str, Any],
    profile_url: str,
    *,
    already_connected: bool,
    note: str | None = None,
) -> None:
    e = _entry(data, job, profile_url)
    now = _now()
    e["message_sent_at"] = now
    e["accepted_at"] = e.get("accepted_at") or now
    if already_connected:
        e["already_connected"] = True
    if note:
        e["message_note"] = note


def record_accepted(data: dict[str, Any], job: dict[str, Any], profile_url: str) -> None:
    e = _entry(data, job, profile_url)
    if not e.get("accepted_at"):
        e["accepted_at"] = _now()


def set_pending_confirmed(data: dict[str, Any], profile_url: str, value: bool) -> None:
    """Record whether a 'Pending' button was observed right after connecting.

    Note: follow-primary profiles (connect via More menu) may not surface a
    'Pending' button in the top card even though the request registered, so a
    False here is not treated as failure.
    """
    e = data["profiles"].get(normalize_profile_url(profile_url))
    if e is not None:
        e["pending_confirmed"] = bool(value)


def get(data: dict[str, Any], profile_url: str) -> dict[str, Any] | None:
    return data["profiles"].get(normalize_profile_url(profile_url))


def status_of(entry: dict[str, Any] | None) -> str:
    if not entry:
        return STATUS_NONE
    if entry.get("message_sent_at"):
        return STATUS_MESSAGE_SENT
    if entry.get("accepted_at"):
        return STATUS_ACCEPTED_MSG_PENDING
    if entry.get("connect_requested_at"):
        return STATUS_CONNECT_PENDING
    return STATUS_NONE


def status_for(data: dict[str, Any], profile_url: str) -> str:
    return status_of(get(data, profile_url))


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)
