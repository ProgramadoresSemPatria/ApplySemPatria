#!/usr/bin/env python3
"""Local web UI for browsing application snapshots and triggering apply actions."""

from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
UI_DIR = ROOT / "ui" / "applications"
sys.path.insert(0, str(SCRIPTS))

BROWSER_ACTIONS = frozenset({"dm_connect", "dm_check", "dm_message", "form_apply", "dm_process_all"})


def _resolve_python() -> str:
    override = os.environ.get("JOBSEARCH_PYTHON")
    if override:
        return override
    for rel in (".venv/bin/python", ".venv-test/bin/python"):
        candidate = ROOT / rel
        if candidate.is_file():
            return str(candidate)
    return sys.executable


PY = _resolve_python()
UI_APPROVE = ("--ui-approved",)
UI_VERSION = 6
SUPPORTED_BULK_ACTIONS = ("dm_process_all", "email_process_all")
UI_META = {
    "ui_approval": True,
    "version": UI_VERSION,
    "bulk_actions": list(SUPPORTED_BULK_ACTIONS),
}


def ui_meta_payload() -> dict[str, Any]:
    from research_log import research_status  # noqa: E402

    return {**UI_META, **research_status()}


def server_supports_client(meta: dict[str, Any]) -> bool:
    """True when meta from /api/meta matches what the bundled UI expects."""
    if meta.get("ui_approval") is not True:
        return False
    if int(meta.get("version") or 0) < UI_VERSION:
        return False
    actions = set(meta.get("bulk_actions") or [])
    return all(a in actions for a in SUPPORTED_BULK_ACTIONS)


def _ui_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["JOBSEARCH_UI_APPROVED"] = "1"
    return env


def _browser_deps_ok() -> tuple[bool, str]:
    proc = subprocess.run(
        [PY, "-c", "import patchright"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return False, (
            "Browser automation unavailable (patchright missing). "
            f"Run: {ROOT / '.venv-test' / 'bin' / 'pip'} install -r requirements-dev.txt "
            "&& patchright install chromium"
        )
    return True, ""


def _run_apply_cmd(cmd: list[str], *, inherit_stdio: bool = False) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = dict(
        cwd=str(ROOT),
        text=True,
        timeout=600,
        env=_ui_subprocess_env(),
    )
    if inherit_stdio:
        return subprocess.run(cmd, stdout=None, stderr=None, **kwargs)
    return subprocess.run(cmd, capture_output=True, **kwargs)


def _find_job(job_key: str) -> dict[str, Any] | None:
    from registry import job_key as jk, load_registry  # noqa: E402

    for job in load_registry()["jobs"]:
        if jk(job) == job_key:
            return job
    return None


def _match_company(job: dict[str, Any]) -> str:
    return (job.get("company") or "Unknown")[:60]


def run_action(action: str, job_key: str, track: str | None = None) -> dict[str, Any]:
    from generate_applications import apply_url_for  # noqa: E402
    from position_disposition import application_steps_enabled  # noqa: E402

    job = _find_job(job_key)
    if not job:
        return {"ok": False, "message": f"Job not found: {job_key}"}

    if not application_steps_enabled(job):
        return {
            "ok": False,
            "message": "Application steps are disabled (human review). Use ⋮ → Real role to enable, or dismiss if noise.",
        }

    tid = track or job.get("track") or "ai-engineer"
    match = _match_company(job)

    if action == "email_send":
        cmd = [
            PY,
            str(SCRIPTS / "email_apply.py"),
            "--send",
            *UI_APPROVE,
            "--smtp",
            "--force-send",
            "--company",
            match,
            "--limit",
            "1",
            "--track",
            tid,
        ]
    elif action == "form_apply":
        url = apply_url_for(job)
        if not url or not url.startswith("http"):
            return {"ok": False, "message": "No apply URL for this role."}
        if job.get("linkedin_easy_apply") and "/jobs/view/" in url.lower():
            from track_store import load_linkedin_jobs_config  # noqa: WPS433

            lj_cfg = load_linkedin_jobs_config(tid)
            cmd = [
                PY,
                str(SCRIPTS / "linkedin_easy_apply.py"),
                "apply",
                "--url",
                url,
                "--track",
                tid,
                "--hold",
                "300",
                "--company",
                match,
                "--role",
                (job.get("role") or "")[:80],
            ]
            if lj_cfg.get("easy_apply_visual", True):
                cmd.append("--visual")
            else:
                cmd.append("--no-visual")
            if lj_cfg.get("easy_apply_submit_from_ui", True):
                cmd.append("--submit")
        else:
            cmd = [
                PY,
                str(SCRIPTS / "url_apply.py"),
                "apply",
                "--url",
                url,
                "--track",
                tid,
                "--hold",
                "300",
            ]
    elif action == "dm_connect":
        cmd = [
            PY,
            str(SCRIPTS / "dm_apply.py"),
            "--send",
            *UI_APPROVE,
            "--force-send",
            "--match",
            match,
            "--limit",
            "1",
            "--track",
            tid,
        ]
    elif action == "dm_check":
        cmd = [
            PY,
            str(SCRIPTS / "dm_followup.py"),
            "--match",
            match,
            "--limit",
            "1",
            "--track",
            tid,
        ]
    elif action == "dm_message":
        cmd = [
            PY,
            str(SCRIPTS / "dm_followup.py"),
            "--send",
            *UI_APPROVE,
            "--force-send",
            "--match",
            match,
            "--limit",
            "1",
            "--track",
            tid,
        ]
    else:
        return {"ok": False, "message": f"Unknown action: {action}"}

    browser_action = action in ("form_apply", "dm_connect", "dm_check", "dm_message")
    if browser_action:
        ok_deps, dep_reason = _browser_deps_ok()
        if not ok_deps:
            return {"ok": False, "message": dep_reason}

    try:
        proc = _run_apply_cmd(cmd, inherit_stdio=browser_action)
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "Action timed out (browser may still be open)."}
    except OSError as exc:
        return {"ok": False, "message": str(exc)}

    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    summary = tail[-3:] if tail else [f"exit {proc.returncode}"]
    ok = proc.returncode == 0
    if action in ("form_apply",) and proc.returncode == 0:
        ok = True
    if proc.stdout is None and proc.stderr is None:
        ok = proc.returncode == 0
        summary = [f"Finished (exit {proc.returncode})"]
    return {
        "ok": ok,
        "message": "\n".join(summary),
        "exit_code": proc.returncode,
        "action": action,
        "job_key": job_key,
    }


def _proc_summary(proc: subprocess.CompletedProcess[str], *, streamed: bool = False) -> tuple[bool, str]:
    if streamed:
        ok = proc.returncode == 0
        msg = "Finished — see terminal for profile-by-profile output." if ok else (
            f"Failed (exit {proc.returncode}) — see UI server terminal for details."
        )
        return ok, msg

    out = (proc.stdout or "").strip().splitlines()
    err = (proc.stderr or "").strip().splitlines()
    if proc.returncode != 0:
        combined = out + err
        tail = combined[-8:] if combined else [f"exit {proc.returncode}"]
    else:
        tail = out[-3:] if out else err[-3:] if err else [f"exit {proc.returncode}"]
    return proc.returncode == 0, "\n".join(tail)


def run_bulk_dm_followup(
    *,
    track: str | None = None,
    limit: int = 0,
    job_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Full DM pipeline for list rows: connect → check accepts → send messages."""
    ok_deps, dep_reason = _browser_deps_ok()
    if not ok_deps:
        return {"ok": False, "message": dep_reason, "action": "dm_process_all"}

    keys = [k for k in (job_keys or []) if k]
    if job_keys is not None and not keys:
        return {
            "ok": False,
            "message": "No DM roles in the current list to process.",
            "action": "dm_process_all",
        }

    tid = track or "ai-engineer"
    if keys:
        for jk in keys:
            job = _find_job(jk)
            if job and job.get("track"):
                tid = job["track"]
                break

    limit_args: list[str] = ["--limit", str(limit)] if limit > 0 else []
    key_args: list[str] = ["--job-keys", ",".join(keys)] if keys else []

    connect_cmd = [
        PY,
        str(SCRIPTS / "dm_apply.py"),
        "--send",
        *UI_APPROVE,
        "--force-send",
        "--track",
        tid,
        *limit_args,
        *key_args,
    ]
    check_cmd = [
        PY,
        str(SCRIPTS / "dm_followup.py"),
        "--track",
        tid,
        *limit_args,
        *key_args,
    ]
    send_cmd = [
        PY,
        str(SCRIPTS / "dm_followup.py"),
        "--send",
        *UI_APPROVE,
        "--force-send",
        "--track",
        tid,
        *limit_args,
        *key_args,
    ]

    phases: list[tuple[str, list[str]]] = [
        ("send_connections", connect_cmd),
        ("check_connections", check_cmd),
        ("send_messages", send_cmd),
    ]
    summaries: list[str] = []
    ok = True

    for label, cmd in phases:
        try:
            proc = _run_apply_cmd(cmd, inherit_stdio=True)
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "message": f"Bulk DM timed out during {label.replace('_', ' ')}.",
                "action": "dm_process_all",
            }
        except OSError as exc:
            return {"ok": False, "message": str(exc), "action": "dm_process_all"}

        phase_ok, phase_msg = _proc_summary(proc, streamed=True)
        ok = ok and phase_ok
        summaries.append(f"[{label}] {phase_msg}")

    scope = f"{len(keys)} role(s)" if keys else "all DM candidates"
    return {
        "ok": ok,
        "message": "\n\n".join(summaries) + f"\n\nProcessed list scope: {scope}",
        "action": "dm_process_all",
        "track": tid,
        "limit": limit,
        "job_keys": keys,
    }


def run_bulk_email_apply(
    *,
    track: str | None = None,
    limit: int = 0,
    job_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Send email applications for list rows with apply email (optionally scoped to job_keys)."""
    keys = [k for k in (job_keys or []) if k]
    if job_keys is not None and not keys:
        return {
            "ok": False,
            "message": "No email-apply roles in the current list.",
            "action": "email_process_all",
        }

    from apply_email import apply_email_for_job  # noqa: E402
    from email_apply import load_config, load_sent_log, pending_send_candidates  # noqa: E402
    from gmail_configure import email_send_allowed  # noqa: E402

    tid = track or "ai-engineer"
    if keys:
        for jk in keys:
            job = _find_job(jk)
            if job and job.get("track"):
                tid = job["track"]
                break

    cfg = load_config(tid)
    sent_path = ROOT / cfg["sent_log_path"]
    sent_log = load_sent_log(sent_path)

    scoped_jobs = [_find_job(jk) for jk in keys] if keys else []
    scoped_jobs = [j for j in scoped_jobs if j]
    if keys and not [j for j in scoped_jobs if apply_email_for_job(j)]:
        return {
            "ok": False,
            "message": "No roles with apply email in this list.",
            "action": "email_process_all",
            "job_keys": keys,
        }

    pending = pending_send_candidates(
        track_id=tid,
        job_keys=keys if keys else None,
        sent_log=sent_log,
    )
    role_count = len(keys) if keys else len(pending)
    unique_count = len(pending)
    if not pending:
        if keys:
            return {
                "ok": False,
                "message": (
                    f"No pending email applications in this list ({len(keys)} role(s) — already sent)."
                ),
                "action": "email_process_all",
                "job_keys": keys,
                "pending_roles": len(keys),
                "unique_emails": 0,
            }
        return {
            "ok": False,
            "message": "No pending email applications in queue.",
            "action": "email_process_all",
            "unique_emails": 0,
        }

    allowed, reason = email_send_allowed(tid, cli_force=True, ui_approved=True)
    if not allowed:
        return {"ok": False, "message": reason, "action": "email_process_all"}

    limit_args: list[str] = ["--limit", str(limit)] if limit > 0 else []
    key_args: list[str] = ["--job-keys", ",".join(keys)] if keys else []

    cmd = [
        PY,
        str(SCRIPTS / "email_apply.py"),
        "--send",
        *UI_APPROVE,
        "--smtp",
        "--force-send",
        "--track",
        tid,
        *limit_args,
        *key_args,
    ]

    try:
        proc = _run_apply_cmd(cmd, inherit_stdio=False)
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "message": "Bulk email apply timed out.",
            "action": "email_process_all",
        }
    except OSError as exc:
        return {"ok": False, "message": str(exc), "action": "email_process_all"}

    ok, msg = _proc_summary(proc)
    if ok and unique_count:
        scope = f"{role_count} role(s)" if keys else f"{unique_count} candidate(s)"
        if keys and unique_count < role_count:
            scope = f"{role_count} role(s) · {unique_count} unique address(es)"
        msg = f"{msg}\n\nQueued: {scope}"
    return {
        "ok": ok,
        "message": msg,
        "action": "email_process_all",
        "track": tid,
        "limit": limit,
        "job_keys": keys,
        "pending_roles": role_count,
        "unique_emails": unique_count,
    }


def set_disposition(job_key: str, disposition: str) -> dict[str, Any]:
    from position_disposition import (  # noqa: E402
        DISPOSITION_AUTO,
        DISPOSITIONS,
        disposition_label,
        get_disposition,
        disposition_is_override,
        update_disposition,
    )
    from registry import load_registry, save_registry  # noqa: E402

    if disposition not in DISPOSITIONS and disposition != DISPOSITION_AUTO:
        return {"ok": False, "message": f"Invalid disposition: {disposition}"}

    registry = load_registry()
    job = update_disposition(registry, job_key, disposition)
    if not job:
        return {"ok": False, "message": f"Job not found: {job_key}"}

    save_registry(registry)
    effective = get_disposition(job)
    if disposition == DISPOSITION_AUTO:
        msg = "Reset to automatic pipeline classification."
    else:
        msg = f"Override set: {disposition_label(effective)}."
    return {
        "ok": True,
        "message": msg,
        "job_key": job_key,
        "position_disposition": effective,
        "position_disposition_label": disposition_label(effective),
        "position_disposition_is_override": disposition_is_override(job),
    }


class ApplicationsUIHandler(BaseHTTPRequestHandler):
    server_version = "JobsearchUI/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[ui] {self.address_string()} {fmt % args}")

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path)
        qs = parse_qs(path.query)

        if path.path == "/api/days":
            from applications_ui_data import list_snapshot_days  # noqa: E402

            days = list_snapshot_days()
            self._json(200, {"days": days})
            return

        if path.path == "/api/meta":
            self._json(200, ui_meta_payload())
            return

        if path.path == "/api/research/status":
            from research_log import research_run_status  # noqa: E402

            self._json(200, research_run_status())
            return

        if path.path == "/api/research":
            self._json(200, ui_meta_payload())
            return

        if path.path == "/api/snapshot":
            day = (qs.get("day") or ["live"])[0]
            from applications_ui_data import load_snapshot, refresh_live_snapshot  # noqa: E402

            if day == "live":
                snap = refresh_live_snapshot()
            else:
                snap = load_snapshot(day)
            if not snap:
                self._json(404, {"error": f"No snapshot for {day}"})
                return
            self._json(200, snap)
            return

        if path.path == "/api/config":
            from config_ui_data import load_config_bundle  # noqa: E402

            track = (qs.get("track") or [None])[0]
            try:
                bundle = load_config_bundle(track)
            except ValueError as exc:
                self._json(400, {"ok": False, "message": str(exc)})
                return
            self._json(200, {"ok": True, "config": bundle})
            return

        if path.path in ("/", "/index.html"):
            self._serve_file(UI_DIR / "index.html")
            return

        rel = path.path.lstrip("/")
        candidate = UI_DIR / rel
        if candidate.is_file():
            self._serve_file(candidate)
            return

        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path

        if path == "/api/research":
            body = self._read_json()
            track = body.get("track")
            since = str(body.get("since") or "7d")
            skip_linkedin = bool(body.get("skip_linkedin"))

            result_holder: dict[str, Any] = {}

            def _worker() -> None:
                try:
                    from daily_research import run_daily_research  # noqa: E402
                    from research_log import has_research_today  # noqa: E402

                    force_full = bool(body.get("force_full"))
                    same_day_refresh = has_research_today() and not force_full

                    result_holder["result"] = run_daily_research(
                        track=track,
                        since=since,
                        skip_linkedin=skip_linkedin or same_day_refresh,
                        skip_linkedin_jobs=bool(body.get("skip_linkedin_jobs")),
                        skip_discover=bool(body.get("table_only")),
                        table_only=bool(body.get("table_only")),
                    )
                except Exception as exc:  # noqa: BLE001
                    result_holder["result"] = {
                        "ok": False,
                        "message": f"Research error: {exc}",
                    }

            t = threading.Thread(target=_worker, daemon=True)
            t.start()
            t.join()
            result = result_holder.get("result")
            if not result:
                from research_log import research_run_status  # noqa: E402

                run = research_run_status()
                if run.get("running"):
                    result = {
                        "ok": False,
                        "message": "Research stopped unexpectedly. Check server logs.",
                    }
                else:
                    result = {
                        "ok": bool(run.get("ok")),
                        "message": run.get("message") or "Research finished.",
                        "day": run.get("day"),
                    }
            if result.get("ok"):
                from applications_ui_data import load_snapshot, refresh_live_snapshot  # noqa: E402

                day = result.get("day")
                result["snapshot"] = load_snapshot(day) if day else refresh_live_snapshot()
            self._json(200 if result.get("ok") else 500, result)
            return

        if path == "/api/bulk-action":
            body = self._read_json()
            action = str(body.get("action") or "")
            if action not in SUPPORTED_BULK_ACTIONS:
                self._json(400, {"ok": False, "message": f"Unknown bulk action: {action}"})
                return
            track = body.get("track")
            limit = int(body.get("limit") or 0)
            raw_keys = body.get("job_keys")
            job_keys: list[str] | None = None
            if raw_keys is not None:
                if not isinstance(raw_keys, list):
                    self._json(400, {"ok": False, "message": "job_keys must be an array"})
                    return
                job_keys = [str(k) for k in raw_keys if k]

            result_holder: dict[str, Any] = {}

            def _worker() -> None:
                if action == "dm_process_all":
                    result_holder["result"] = run_bulk_dm_followup(
                        track=track,
                        limit=limit,
                        job_keys=job_keys,
                    )
                else:
                    result_holder["result"] = run_bulk_email_apply(
                        track=track,
                        limit=limit,
                        job_keys=job_keys,
                    )

            t = threading.Thread(target=_worker, daemon=True)
            t.start()
            t.join(timeout=1200)
            result = result_holder.get("result") or {
                "ok": False,
                "message": "Bulk action failed to start or timed out.",
            }

            from applications_ui_data import refresh_live_snapshot  # noqa: E402

            result["snapshot"] = refresh_live_snapshot()
            self._json(200, result)
            return

        if path == "/api/config":
            body = self._read_json()
            section = str(body.get("section") or "")
            track = body.get("track")
            payload = body.get("payload")
            if not section or not isinstance(payload, dict):
                self._json(400, {"ok": False, "message": "section and payload required"})
                return
            from config_ui_data import save_config_section  # noqa: E402

            try:
                bundle = save_config_section(track, section, payload)
            except ValueError as exc:
                self._json(400, {"ok": False, "message": str(exc)})
                return
            self._json(200, {"ok": True, "message": f"Saved {section}.", "config": bundle})
            return

        if path not in ("/api/action", "/api/disposition"):
            self.send_error(404)
            return
        body = self._read_json()

        if path == "/api/disposition":
            job_key = str(body.get("job_key") or "")
            disposition = str(body.get("disposition") or "")
            if not job_key or not disposition:
                self._json(400, {"ok": False, "message": "job_key and disposition required"})
                return
            result = set_disposition(job_key, disposition)
            from applications_ui_data import refresh_live_snapshot  # noqa: E402

            result["snapshot"] = refresh_live_snapshot()
            self._json(200 if result.get("ok") else 400, result)
            return

        action = str(body.get("action") or "")
        job_key = str(body.get("job_key") or "")
        track = body.get("track")
        if not action or not job_key:
            self._json(400, {"ok": False, "message": "action and job_key required"})
            return

        result_holder: dict[str, Any] = {}

        def _worker() -> None:
            result_holder["result"] = run_action(action, job_key, track)

        # Long browser actions: run in thread for email quick path use sync
        if action in ("email_send", "dm_check"):
            result = run_action(action, job_key, track)
        else:
            t = threading.Thread(target=_worker, daemon=True)
            t.start()
            t.join(timeout=600)
            result = result_holder.get("result") or {"ok": False, "message": "Action failed to start."}

        from applications_ui_data import refresh_live_snapshot  # noqa: E402

        result["snapshot"] = refresh_live_snapshot()
        self._json(200, result)

    def _serve_file(self, path: Path) -> None:
        content = path.read_bytes()
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def serve(*, port: int = 8765, open_browser: str | None = "safari") -> int:
    UI_DIR.mkdir(parents=True, exist_ok=True)
    if not (UI_DIR / "index.html").exists():
        print(f"Missing UI: {UI_DIR / 'index.html'}")
        return 1

    url = f"http://127.0.0.1:{port}/"
    httpd = ThreadingHTTPServer(("127.0.0.1", port), ApplicationsUIHandler)
    print(f"Applications UI → {url}")
    print(f"UI API v{UI_VERSION} — bulk actions: {', '.join(SUPPORTED_BULK_ACTIONS)}")
    print("Press Ctrl+C to stop.")

    if open_browser:
        browser = open_browser.lower()
        if browser == "safari":
            subprocess.run(["open", "-a", "Safari", url], check=False)
        else:
            webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Job search applications UI server")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--browser", default="safari", help="safari | default | none")
    args = parser.parse_args()
    opener = None if args.no_open or args.browser == "none" else args.browser
    return serve(port=args.port, open_browser=opener)


if __name__ == "__main__":
    raise SystemExit(main())
