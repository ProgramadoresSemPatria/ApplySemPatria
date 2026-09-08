"""Persist and query manual/automatic form apply status for UI cards."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
URL_APPLICATIONS_PATH = ROOT / "state" / "url-applications.json"
TZ = ZoneInfo("America/Sao_Paulo")


def _load_data() -> dict[str, Any]:
    if not URL_APPLICATIONS_PATH.is_file():
        return {"submitted": []}
    try:
        data = json.loads(URL_APPLICATIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"submitted": []}
    if not isinstance(data.get("submitted"), list):
        data["submitted"] = []
    return data


def _save_data(data: dict[str, Any]) -> None:
    URL_APPLICATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    URL_APPLICATIONS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _job_urls(job: dict[str, Any]) -> set[str]:
    from generate_applications import apply_url_for  # noqa: WPS433

    urls: set[str] = set()
    for raw in (apply_url_for(job), job.get("apply_url") or ""):
        value = str(raw or "").strip()
        if value.startswith("http"):
            urls.add(value)
    return urls


def load_form_submission_state() -> tuple[set[str], set[str]]:
    """Return submitted apply URLs and job keys."""
    urls: set[str] = set()
    keys: set[str] = set()
    for row in _load_data().get("submitted", []):
        if not isinstance(row, dict):
            continue
        jk = (row.get("job_key") or "").strip()
        if jk:
            keys.add(jk)
        for field in ("url", "resolved_url"):
            value = (row.get(field) or "").strip()
            if value:
                urls.add(value)
    return urls, keys


def load_url_submitted() -> set[str]:
    """Backward-compatible URL-only loader."""
    urls, _keys = load_form_submission_state()
    return urls


def form_is_submitted(job: dict[str, Any], *, url_done: set[str] | None = None, job_keys_done: set[str] | None = None) -> bool:
    from registry import job_key as registry_job_key  # noqa: WPS433

    if url_done is None or job_keys_done is None:
        loaded_urls, loaded_keys = load_form_submission_state()
        url_done = loaded_urls if url_done is None else url_done
        job_keys_done = loaded_keys if job_keys_done is None else job_keys_done

    jk = registry_job_key(job)
    if jk in job_keys_done:
        return True
    urls = _job_urls(job)
    return any(url in url_done for url in urls)


def set_form_applied(job: dict[str, Any], applied: bool, *, source: str = "manual") -> dict[str, Any]:
    from registry import job_key as registry_job_key  # noqa: WPS433
    from generate_applications import apply_url_for  # noqa: WPS433

    jk = registry_job_key(job)
    urls = _job_urls(job)
    data = _load_data()
    rows = [row for row in data.get("submitted", []) if isinstance(row, dict)]

    def _matches(row: dict[str, Any]) -> bool:
        row_key = (row.get("job_key") or "").strip()
        if row_key and row_key == jk:
            return True
        row_urls = {(row.get("url") or "").strip(), (row.get("resolved_url") or "").strip()} - {""}
        return bool(urls & row_urls)

    if applied:
        if any(_matches(row) for row in rows):
            return {"ok": True, "message": "Form already marked as applied.", "applied": True}
        primary = next(iter(urls), apply_url_for(job))
        if not str(primary or "").startswith("http"):
            return {"ok": False, "message": "No apply URL for this role.", "applied": False}
        rows.append(
            {
                "job_key": jk,
                "url": primary,
                "resolved_url": primary,
                "company": (job.get("company") or "")[:80],
                "role": (job.get("role") or "")[:80],
                "confirmed": True,
                "manual": source == "manual",
                "submitted_at": datetime.now(TZ).isoformat(),
            }
        )
        data["submitted"] = rows
        _save_data(data)
        return {"ok": True, "message": "Form marked as applied.", "applied": True}

    before = len(rows)
    rows = [row for row in rows if not _matches(row)]
    if len(rows) == before:
        return {"ok": True, "message": "Form already marked as not applied.", "applied": False}
    data["submitted"] = rows
    _save_data(data)
    return {"ok": True, "message": "Form marked as not applied.", "applied": False}
