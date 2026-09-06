"""F6S collector — often blocked by anti-bot checks."""

from __future__ import annotations

from typing import Any

from .http_utils import fetch_text


class CollectorError(Exception):
    pass


def collect(config: dict[str, Any]) -> list[dict[str, Any]]:
    url = "https://www.f6s.com/jobs"
    html = fetch_text(url)
    if "Checking your browser" in html or "captcha" in html.lower():
        raise CollectorError("F6S blocked request (CAPTCHA / anti-bot)")
    return []
