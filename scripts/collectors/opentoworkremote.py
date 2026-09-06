"""OpenToWorkRemote collector — Heroku JSON API."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from filters import matches_title

from .http_utils import fetch_json


def _format_salary(job: dict[str, Any]) -> str | None:
    if job.get("salaryRange"):
        return str(job["salaryRange"])
    min_s = job.get("salaryMin")
    max_s = job.get("salaryMax")
    if min_s or max_s:
        if min_s and max_s:
            return f"${min_s:,}–${max_s:,}"
        val = min_s or max_s
        return f"${val:,}"
    return None


def collect(config: dict[str, Any]) -> list[dict[str, Any]]:
    search = config.get("search", {})
    keywords = search.get("title_keywords", ["ai engineer"])
    api_url = config.get("sources", {}).get("opentoworkremote", {}).get(
        "api_url", "https://opentoworkremote-api.herokuapp.com/jobs"
    )
    max_pages = config.get("opentoworkremote_max_pages", 5)
    query = keywords[0] if keywords else "ai engineer"

    jobs: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        url = f"{api_url}?title={quote(query)}&page={page}"
        payload = fetch_json(url)
        batch = payload.get("jobs") or []
        if not batch:
            break

        for item in batch:
            title = item.get("title") or ""
            if not matches_title(title, keywords):
                continue
            salary_usd = _format_salary(item)
            jobs.append(
                {
                    "source": "opentoworkremote",
                    "url": item.get("url") or "",
                    "role": title,
                    "company": item.get("company") or "Unknown",
                    "salary_usd": salary_usd,
                    "currency": "USD" if salary_usd else None,
                    "location_note": item.get("location") or "Remote",
                    "posted_at": item.get("publicationDate") or item.get("date"),
                    "apply_channel": "external_url",
                    "description_snippet": ", ".join(item.get("tags") or []),
                }
            )

        pages_info = payload.get("pagesInfo") or {}
        if page >= pages_info.get("totalpages", page):
            break

    return jobs
