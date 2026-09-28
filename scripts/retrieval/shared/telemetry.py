"""Opt-in telemetry (Firebase GA4 Measurement Protocol). Disabled unless secrets/telemetry.json enables it."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from retrieval._paths import ROOT

TELEMETRY_PATH = ROOT / "secrets" / "telemetry.json"
INSTALL_ID_PATH = ROOT / "state" / "telemetry-install-id"
GA4_COLLECT = "https://www.google-analytics.com/mp/collect"
_URL_RE = re.compile(r"https?://\S+")


def _load_raw() -> dict[str, Any]:
    if not TELEMETRY_PATH.is_file():
        return {}
    try:
        data = json.loads(TELEMETRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def telemetry_enabled() -> bool:
    raw = _load_raw()
    return bool(raw.get("enabled")) and bool(raw.get("measurement_id")) and bool(raw.get("api_secret"))


def install_id() -> str:
    INSTALL_ID_PATH.parent.mkdir(parents=True, exist_ok=True)
    if INSTALL_ID_PATH.is_file():
        existing = INSTALL_ID_PATH.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    new_id = str(uuid.uuid4())
    INSTALL_ID_PATH.write_text(new_id, encoding="utf-8")
    return new_id


def sanitize_text(text: str, *, max_len: int = 240) -> str:
    cleaned = _URL_RE.sub("<url>", text or "")
    cleaned = cleaned.replace("\n", " ").strip()
    return cleaned[:max_len]


def public_config() -> dict[str, Any]:
    """Safe to expose via /api/meta (no api_secret)."""
    raw = _load_raw()
    if not raw.get("enabled"):
        return {"enabled": False}
    web = raw.get("firebase_web")
    if not isinstance(web, dict):
        return {"enabled": False}
    public_web = {
        k: web[k]
        for k in (
            "apiKey",
            "authDomain",
            "projectId",
            "storageBucket",
            "messagingSenderId",
            "appId",
            "measurementId",
        )
        if k in web and web[k]
    }
    if not public_web.get("measurementId") and raw.get("measurement_id"):
        public_web["measurementId"] = raw["measurement_id"]
    return {
        "enabled": bool(public_web),
        "install_id": install_id() if raw.get("enabled") else None,
        "firebase_web": public_web if public_web else None,
    }


def send_event(event_name: str, params: dict[str, Any] | None = None) -> bool:
    if not telemetry_enabled():
        return False
    raw = _load_raw()
    measurement_id = str(raw.get("measurement_id") or "").strip()
    api_secret = str(raw.get("api_secret") or "").strip()
    if not measurement_id or not api_secret:
        return False

    safe_params = {str(k): sanitize_text(str(v), max_len=100) for k, v in (params or {}).items()}
    safe_params["install_id"] = install_id()

    body = {
        "client_id": install_id(),
        "events": [{"name": event_name[:40], "params": safe_params}],
    }
    url = f"{GA4_COLLECT}?measurement_id={measurement_id}&api_secret={api_secret}"
    req = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=8) as resp:
            return 200 <= resp.status < 300
    except (HTTPError, URLError, OSError, TimeoutError):
        return False


def forward_audit_record(record: dict[str, Any]) -> None:
    """Send high-signal server events to GA4 (best-effort, never raises)."""
    if not telemetry_enabled():
        return
    level = str(record.get("level") or "").upper()
    event = str(record.get("event") or "")
    component = str(record.get("component") or "")
    if level != "ERROR" and not (level == "WARN" and event == "step_failed"):
        return
    if component not in ("daily_research", "ui_server"):
        return
    data = record.get("data") if isinstance(record.get("data"), dict) else {}
    name = "research_step_failed" if event == "step_failed" else "server_error"
    if event == "research_failed":
        name = "research_failed"
    msg = sanitize_text(str(data.get("message") or data.get("tail") or ""))
    send_event(
        name,
        {
            "component": component,
            "event": event,
            "step": str(data.get("step") or data.get("label") or ""),
            "message": msg,
        },
    )


def build_support_bundle() -> dict[str, Any]:
    """Redacted snapshot for user-initiated sharing (no secrets, no full registry)."""
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

    commit = "unknown"
    head = ROOT / ".git" / "HEAD"
    if head.is_file():
        commit = head.read_text(encoding="utf-8").strip()[:12]

    return {
        "schema": 1,
        "install_id": install_id(),
        "day": day,
        "git_head": commit,
        "telemetry_enabled": telemetry_enabled(),
        "research_run": run_public,
        "audit_tail": audit_tail,
    }
