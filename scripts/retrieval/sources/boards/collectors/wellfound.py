"""Wellfound collector — attempts __NEXT_DATA__ extraction."""

from __future__ import annotations

import json
import re
from typing import Any

from filters import matches_title

from .http_utils import fetch_text


class CollectorError(Exception):
    pass


def _walk_for_jobs(obj: Any, found: list[dict[str, Any]]) -> None:
    if isinstance(obj, dict):
        title = obj.get("title") or obj.get("jobTitle")
        if title and (obj.get("slug") or obj.get("id") or obj.get("url")):
            startup = obj.get("startup") or {}
            company = (
                obj.get("companyName")
                or startup.get("name")
                or obj.get("company")
                or "Unknown"
            )
            url = obj.get("url") or obj.get("jobUrl") or obj.get("applyUrl")
            if not url and obj.get("slug"):
                url = f"https://wellfound.com/jobs/{obj['slug']}"
            if url and title:
                found.append(
                    {
                        "title": title,
                        "company": company,
                        "url": url,
                        "salary": obj.get("salary") or obj.get("compensation"),
                        "location": obj.get("location") or obj.get("remotePolicy"),
                        "posted_at": obj.get("publishedAt") or obj.get("createdAt"),
                    }
                )
        for value in obj.values():
            _walk_for_jobs(value, found)
    elif isinstance(obj, list):
        for item in obj:
            _walk_for_jobs(item, found)


def collect(config: dict[str, Any]) -> list[dict[str, Any]]:
    search = config.get("search", {})
    keywords = search.get("title_keywords", ["ai engineer"])
    query = keywords[0].replace(" ", "-")
    url = f"https://wellfound.com/role/l/{query}"

    try:
        html = fetch_text(url)
    except Exception as exc:
        raise CollectorError(f"Wellfound request failed ({exc})") from exc
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not match:
        raise CollectorError("Wellfound blocked or changed layout (no __NEXT_DATA__)")

    data = json.loads(match.group(1))
    status = data.get("props", {}).get("pageProps", {}).get("statusCode")
    if status in (403, 404, 500):
        raise CollectorError(f"Wellfound returned statusCode={status} (login or bot protection likely)")

    raw_jobs: list[dict[str, Any]] = []
    _walk_for_jobs(data, raw_jobs)

    if not raw_jobs:
        raise CollectorError("Wellfound page loaded but no jobs extracted")

    jobs: list[dict[str, Any]] = []
    seen = set()
    for item in raw_jobs:
        title = item["title"]
        if not matches_title(title, keywords):
            continue
        key = item["url"]
        if key in seen:
            continue
        seen.add(key)
        salary = item.get("salary")
        salary_text = str(salary) if salary else None
        jobs.append(
            {
                "source": "wellfound",
                "url": item["url"],
                "role": title,
                "company": item.get("company") or "Unknown",
                "salary_usd": salary_text,
                "currency": "USD" if salary_text and "$" in salary_text else None,
                "location_note": item.get("location") or "Remote",
                "posted_at": item.get("posted_at"),
                "apply_channel": "form",
                "description_snippet": "",
            }
        )

    return jobs
