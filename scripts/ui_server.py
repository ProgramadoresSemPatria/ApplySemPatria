#!/usr/bin/env python3
"""Local web UI for browsing application snapshots and triggering apply actions."""

from __future__ import annotations

import json
import mimetypes
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

PY = sys.executable


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

    job = _find_job(job_key)
    if not job:
        return {"ok": False, "message": f"Job not found: {job_key}"}

    tid = track or job.get("track") or "ai-engineer"
    match = _match_company(job)

    if action == "email_send":
        cmd = [
            PY,
            str(SCRIPTS / "email_apply.py"),
            "--send",
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

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "Action timed out (browser may still be open)."}
    except OSError as exc:
        return {"ok": False, "message": str(exc)}

    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    summary = tail[-3:] if tail else [f"exit {proc.returncode}"]
    ok = proc.returncode == 0
    if action in ("form_apply",) and proc.returncode == 0:
        ok = True
    return {
        "ok": ok,
        "message": "\n".join(summary),
        "exit_code": proc.returncode,
        "action": action,
        "job_key": job_key,
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
            if not days:
                live = {"day": "live", "label": "Live registry", "job_count": 0}
                days = [live]
            self._json(200, {"days": days})
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
        if path != "/api/action":
            self.send_error(404)
            return
        body = self._read_json()
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
