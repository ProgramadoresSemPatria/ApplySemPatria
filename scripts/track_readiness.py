"""Per-track readiness checks — warn on gaps, allow partial progress."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from profile_store import REQUIRED_FOR_FORMS, missing
from track_store import (
    load_email_config,
    load_linkedin_config,
    load_profile,
    list_track_ids,
    track_label,
    track_path,
)

Operation = Literal["discover", "table", "apply_email", "apply_dm", "apply_url"]

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class TrackReadiness:
    track_id: str
    label: str
    operation: str
    can_proceed: bool
    can_send: bool
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary_line(self) -> str:
        if self.can_send or (self.can_proceed and self.operation in ("discover", "table")):
            flag = "✓"
        elif self.can_proceed:
            flag = "○"
        else:
            flag = "✗"
        parts = [f"{flag} {self.label} ({self.track_id})"]
        if self.blockers:
            parts.append("blocked: " + "; ".join(self.blockers))
        elif self.warnings:
            parts.append("note: " + "; ".join(self.warnings[:2]))
        return " — ".join(parts)


def _resume_ok(track_id: str) -> tuple[bool, str]:
    prof = load_profile(track_id)
    path = str(prof.get("resume_path") or "").strip()
    if not path:
        return False, "resume_path not set"
    expanded = Path(path).expanduser()
    if not expanded.exists():
        return False, f"resume not found: {path}"
    return True, ""


def _gmail_ready() -> bool:
    token = ROOT / "state" / "gmail-token.json"
    app_pw_file = ROOT / "secrets" / "gmail-app-password"
    if token.exists():
        return True
    if os.environ.get("GMAIL_APP_PASSWORD", "").strip():
        return True
    if app_pw_file.exists() and app_pw_file.read_text(encoding="utf-8").strip():
        return True
    return False


def _linkedin_ready() -> bool:
    return (Path.home() / ".linkedin-mcp" / "cookies.json").exists()


def assess_track(track_id: str, operation: Operation) -> TrackReadiness:
    label = track_label(track_id)
    blockers: list[str] = []
    warnings: list[str] = []
    can_proceed = True
    can_send = True

    prof_path = track_path(track_id, "profile_path")
    if not prof_path.exists():
        blockers.append("profile file missing")
        can_proceed = False
        can_send = False
    else:
        miss = missing(track_id)
        if miss:
            warnings.append(f"profile gaps: {', '.join(miss)}")

    if operation == "discover":
        cfg_path = track_path(track_id, "board_config_path")
        if not cfg_path.exists():
            blockers.append("board config missing")
            can_proceed = False
        # Discovery never needs resume — only warn
        ok, msg = _resume_ok(track_id)
        if not ok:
            warnings.append(f"{msg} (apply will skip this track until fixed)")

    elif operation == "table":
        pass  # always show all rows

    elif operation == "apply_email":
        ok, msg = _resume_ok(track_id)
        if not ok:
            blockers.append(msg)
            can_proceed = False
            can_send = False
        email_cfg = load_email_config(track_id)
        if not str(email_cfg.get("sender_email") or "").strip():
            blockers.append("sender_email not set in email-apply-config")
            can_proceed = False
            can_send = False
        if not email_cfg.get("email_apply_enabled", False):
            warnings.append("Gmail email apply disabled (jobsearch configure gmail)")
            can_send = False
        elif not email_cfg.get("email_message_confirmed", False):
            warnings.append("application message not confirmed")
            can_send = False
        elif email_cfg.get("email_apply_mode") == "manual":
            warnings.append("manual mode — approve in UI (CLI --send needs --force)")
            can_send = False
        if not _gmail_ready():
            warnings.append("Gmail credentials missing (needed for --send)")
            can_send = False

    elif operation == "apply_dm":
        li_cfg = load_linkedin_config(track_id)
        if not li_cfg.get("dm_apply_enabled", False):
            warnings.append("LinkedIn DM apply disabled (jobsearch configure linkedin)")
            can_send = False
        elif not li_cfg.get("dm_message_confirmed", False):
            warnings.append("DM message not confirmed")
            can_send = False
        elif li_cfg.get("dm_apply_mode") == "manual":
            warnings.append("manual mode — approve in UI (CLI --send needs --force)")
            can_send = False
        if not _linkedin_ready():
            warnings.append("LinkedIn cookies missing (needed for --send)")
            can_send = False
        can_proceed = True

    elif operation == "apply_url":
        ok, msg = _resume_ok(track_id)
        if not ok:
            blockers.append(msg)
            can_proceed = False
            can_send = False

    if blockers and operation in ("discover",):
        can_proceed = False

    return TrackReadiness(
        track_id=track_id,
        label=label,
        operation=operation,
        can_proceed=can_proceed,
        can_send=can_send,
        blockers=blockers,
        warnings=warnings,
    )


def assess_all(operation: Operation, *, track_ids: list[str] | None = None) -> list[TrackReadiness]:
    ids = track_ids or list_track_ids()
    return [assess_track(tid, operation) for tid in ids]


def ready_track_ids(
    operation: Operation,
    *,
    for_send: bool = False,
    track_ids: list[str] | None = None,
) -> list[str]:
    reports = assess_all(operation, track_ids=track_ids)
    if for_send:
        return [r.track_id for r in reports if r.can_send]
    return [r.track_id for r in reports if r.can_proceed]


def print_readiness_report(
    operation: Operation,
    *,
    for_send: bool = False,
    track_ids: list[str] | None = None,
) -> list[TrackReadiness]:
    reports = assess_all(operation, track_ids=track_ids)
    mode = "live send" if for_send else "run"
    print(f"\nTrack readiness ({operation}, {mode}):\n")
    for r in reports:
        print(f"  {r.summary_line()}", flush=True)
    ready = [r for r in reports if (r.can_send if for_send else r.can_proceed)]
    skipped = [r for r in reports if r not in ready]
    if skipped and ready:
        print(f"\n→ Proceeding with: {', '.join(r.label for r in ready)}", flush=True)
        print(f"→ Skipping: {', '.join(r.label for r in skipped)}", flush=True)
    elif skipped and not ready:
        print("\n→ No tracks ready for this action.", flush=True)
    print(flush=True)
    return reports
