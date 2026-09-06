"""Local LinkedIn profile mock server for HAR record/replay tests."""

from __future__ import annotations

import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "linkedin"
MOCK_HOST = "127.0.0.1"
MOCK_PORT = 18766

PROFILE_MAP: dict[str, str] = {
    "test-connect": "profile-connect.html",
    "test-message": "profile-message.html",
    "test-pending": "profile-pending.html",
    "test-connect-more": "profile-connect-more.html",
    "test-connected": "profile-connected.html",
    "test-connected-only": "profile-connected-only.html",
}


def profile_url(host: str, port: int, slug: str) -> str:
    return f"http://{host}:{port}/in/{slug}/"


class _Handler(BaseHTTPRequestHandler):
    server_version = "LinkedInMock/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        m = re.match(r"/in/([a-z0-9-]+)/?", self.path)
        if not m:
            self.send_error(404)
            return
        slug = m.group(1)
        fname = PROFILE_MAP.get(slug)
        if not fname:
            self.send_error(404)
            return
        body = (FIXTURES / fname).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class LinkedInMockServer:
    def __init__(self, host: str = MOCK_HOST, port: int = MOCK_PORT) -> None:
        self._host = host
        self._httpd = ThreadingHTTPServer((host, port), _Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return int(self._httpd.server_address[1])

    def url(self, slug: str) -> str:
        return profile_url(self._host, self.port, slug)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
        self._thread.join(timeout=5)
