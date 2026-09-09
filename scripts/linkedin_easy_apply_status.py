#!/usr/bin/env python3
"""Probe LinkedIn job pages for Easy Apply availability and application state.

Does not open the apply wizard or submit forms — only reads the live job page
and persists status for the applications UI.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from browser_session import close_session, launch_context  # noqa: E402
from linkedin_ui import dismiss_blocking_dialogs, wait_for_job_detail_ready  # noqa: E402

STATUS_PATH = ROOT / "state" / "easy-apply-status.json"
TZ = ZoneInfo("America/Sao_Paulo")

EasyApplyStatus = Literal["available", "applied", "continue", "closed", "external", "unknown"]

APPLIED_RE = re.compile(
    r"^Applied$|^Applied to\b|^You applied|Application submitted|already applied",
    re.I,
)
CONTINUE_RE = re.compile(r"Continue application|Continue applying", re.I)
CLOSED_RE = re.compile(
    r"No longer accepting applications|Applications are closed|"
    r"is no longer accepting|job has been closed|This job is closed",
    re.I,
)
EXTERNAL_RE = re.compile(r"Apply on company website|Apply on external website", re.I)
EASY_APPLY_RE = re.compile(r"Easy Apply", re.I)


def _load_store() -> dict[str, Any]:
    if not STATUS_PATH.is_file():
        return {"checks": {}}
    try:
        data = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"checks": {}}
    if not isinstance(data.get("checks"), dict):
        data["checks"] = {}
    return data


def _save_store(data: dict[str, Any]) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def get_status_record(job_key: str) -> dict[str, Any] | None:
    jk = (job_key or "").strip()
    if not jk:
        return None
    row = _load_store().get("checks", {}).get(jk)
    return row if isinstance(row, dict) else None


def load_all_status_records() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key, row in _load_store().get("checks", {}).items():
        if isinstance(row, dict):
            out[str(key)] = row
    return out


def status_label(status: str) -> str:
    return {
        "available": "Easy Apply open",
        "applied": "Applied on LinkedIn",
        "continue": "Application in progress",
        "closed": "No longer accepting",
        "external": "External apply only",
        "unknown": "Status unknown",
    }.get(status, "Status unknown")


async def _collect_apply_controls(page) -> list[dict[str, Any]]:
    return await page.eval_on_selector_all(
        "a, button",
        """els => els.filter(e => {
          const text = ((e.innerText || '') + ' ' + (e.getAttribute('aria-label') || '')).trim();
          return /easy apply|applied|continue application|company website|no longer accepting/i.test(text);
        }).map(e => ({
          tag: e.tagName,
          text: (e.innerText || '').trim().slice(0, 120),
          aria: e.getAttribute('aria-label') || '',
          disabled: !!e.disabled,
          href: e.href || null,
          visible: !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length)
        }))""",
    )


def _control_blob(ctrl: dict[str, Any]) -> str:
    return f"{ctrl.get('text', '')} {ctrl.get('aria', '')}".strip()


def _is_applied_control(ctrl: dict[str, Any]) -> bool:
    text = str(ctrl.get("text") or "").strip()
    aria = str(ctrl.get("aria") or "").strip()
    if EASY_APPLY_RE.search(text) or EASY_APPLY_RE.search(aria):
        return False
    if text.lower() == "applied":
        return True
    if aria.lower().startswith("applied to"):
        return True
    return bool(APPLIED_RE.search(text) or APPLIED_RE.search(aria))


def _classify_controls(controls: list[dict[str, Any]], body: str) -> dict[str, Any]:
    visible = [c for c in controls if c.get("visible")]
    body_l = body.lower()

    if CLOSED_RE.search(body):
        return {
            "status": "closed",
            "easy_apply_enabled": False,
            "detail": "Listing indicates applications are closed.",
        }

    for ctrl in visible:
        if _is_applied_control(ctrl):
            blob = _control_blob(ctrl)
            return {
                "status": "applied",
                "easy_apply_enabled": False,
                "detail": blob[:120] or "Applied",
            }

    for ctrl in visible:
        blob = _control_blob(ctrl)
        if CONTINUE_RE.search(blob):
            return {
                "status": "continue",
                "easy_apply_enabled": True,
                "detail": blob.strip()[:120] or "Continue application",
            }

    for ctrl in visible:
        blob = _control_blob(ctrl)
        if EXTERNAL_RE.search(blob):
            return {
                "status": "external",
                "easy_apply_enabled": False,
                "detail": blob.strip()[:120] or "Apply on company website",
            }

    for ctrl in visible:
        blob = _control_blob(ctrl)
        if EASY_APPLY_RE.search(blob) and not ctrl.get("disabled"):
            return {
                "status": "available",
                "easy_apply_enabled": True,
                "detail": blob.strip()[:120] or "Easy Apply",
            }

    if EXTERNAL_RE.search(body):
        return {
            "status": "external",
            "easy_apply_enabled": False,
            "detail": "Apply on company website",
        }

    if "sign in" in body_l[:2500] and "easy apply" not in body_l[:2500]:
        return {
            "status": "unknown",
            "easy_apply_enabled": False,
            "detail": "Sign-in required or page did not load completely.",
        }

    return {
        "status": "unknown",
        "easy_apply_enabled": False,
        "detail": "Could not detect Easy Apply state on the job page.",
    }


async def probe_easy_apply_status(page, job_url: str) -> dict[str, Any]:
    await page.goto(job_url, wait_until="domcontentloaded", timeout=90000)
    await dismiss_blocking_dialogs(page)
    await wait_for_job_detail_ready(page, timeout_ms=45000)
    await asyncio.sleep(1.0)
    controls = await _collect_apply_controls(page)
    try:
        body = await page.inner_text("body")
    except Exception:  # noqa: BLE001
        body = ""
    result = _classify_controls(controls, body)
    visible_controls = [c for c in controls if c.get("visible")][:8]
    result.update(
        {
            "url": job_url,
            "page_url": page.url,
            "controls": visible_controls,
            "ok": True,
        }
    )
    result["status_text"] = status_label(str(result.get("status", "unknown")))
    return result


def save_status(
    job_key: str,
    probe: dict[str, Any],
    *,
    company: str = "",
    role: str = "",
) -> dict[str, Any]:
    jk = (job_key or "").strip()
    if not jk:
        raise ValueError("job_key required")

    status = str(probe.get("status") or "unknown")
    record = {
        "job_key": jk,
        "url": probe.get("url") or "",
        "page_url": probe.get("page_url") or "",
        "status": status,
        "status_text": probe.get("status_text") or status_label(status),
        "easy_apply_enabled": bool(probe.get("easy_apply_enabled")),
        "detail": (probe.get("detail") or "")[:200],
        "company": (company or "")[:80],
        "role": (role or "")[:80],
        "checked_at": datetime.now(TZ).isoformat(),
    }
    data = _load_store()
    data.setdefault("checks", {})[jk] = record
    _save_store(data)
    return record


def sync_form_state_from_status(job: dict[str, Any], record: dict[str, Any]) -> None:
    """Mark form applied when LinkedIn reports an submitted application."""
    from form_apply_state import form_is_submitted, set_form_applied  # noqa: WPS433

    status = str(record.get("status") or "")
    if status == "applied" and not form_is_submitted(job):
        set_form_applied(job, True, source="linkedin_status")
    elif status in ("closed", "external") and form_is_submitted(job):
        # Keep manual/logged applied state; status is informational only.
        pass


async def run_check(
    job_url: str,
    *,
    job_key: str = "",
    company: str = "",
    role: str = "",
    hold: int = 10,
    visual: bool = True,
) -> dict[str, Any]:
    pw, browser, ctx = await launch_context(headless=not visual)
    summary: dict[str, Any] = {"url": job_url, "visual": visual}
    try:
        page = await ctx.new_page()
        print(f"{'[visual]' if visual else '[headless]'} Easy Apply status → {job_url}")
        probe = await probe_easy_apply_status(page, job_url)
        summary.update(probe)
        if job_key:
            record = save_status(job_key, probe, company=company, role=role)
            summary["record"] = record
            from registry import job_key as registry_job_key, load_registry  # noqa: WPS433

            job = next(
                (j for j in load_registry()["jobs"] if registry_job_key(j) == job_key),
                None,
            )
            if job:
                sync_form_state_from_status(job, record)
            from table_refresh import refresh_applications_table  # noqa: WPS433

            refresh_applications_table()
        print(f"status: {probe.get('status')} · {probe.get('status_text')}")
        if hold > 0:
            print(f"holding browser open {hold}s…")
            await asyncio.sleep(hold)
    finally:
        await close_session(pw=pw, browser=browser, context=ctx)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Check LinkedIn Easy Apply status for a job listing")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="Open job page and detect Easy Apply state")
    p_check.add_argument("--url", required=True)
    p_check.add_argument("--job-key", default="")
    p_check.add_argument("--company", default="")
    p_check.add_argument("--role", default="")
    p_check.add_argument("--hold", type=int, default=10)
    p_check.add_argument(
        "--visual",
        action=argparse.BooleanOptionalAction,
        default=True,
    )

    args = parser.parse_args()
    if args.command != "check":
        return 1

    result = asyncio.run(
        run_check(
            args.url,
            job_key=args.job_key,
            company=args.company,
            role=args.role,
            hold=args.hold,
            visual=args.visual,
        )
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
