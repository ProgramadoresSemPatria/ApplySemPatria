"""Himalayas collector — public JSON API with cursor pagination."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from filters import matches_title

from .http_utils import fetch_json


def _matches_categories(categories: list[str], tags: list[str]) -> bool:
    for cat in categories:
        cat_lower = cat.lower().replace("_", "-")
        for tag in tags:
            tag_lower = tag.lower()
            if tag_lower == "ai":
                if re.search(
                    r"(^|-)ai(-|$)|artificial-intelligence|ai-engineer|generative-ai",
                    cat_lower,
                ):
                    return True
            elif tag_lower in cat_lower:
                return True
    return False


def _format_salary(job: dict[str, Any]) -> tuple[str | None, str | None]:
    currency = job.get("currency")
    min_s = job.get("minSalary")
    max_s = job.get("maxSalary")
    period = job.get("salaryPeriod") or "annual"
    if min_s is None and max_s is None:
        return None, currency
    parts = []
    if min_s is not None:
        parts.append(f"{currency or ''} {min_s:,}".strip())
    if max_s is not None and max_s != min_s:
        parts.append(f"{max_s:,}")
    label = "–".join(parts)
    if period == "hourly":
        label += "/hr"
    elif period == "annual":
        label += "/yr"
    return label, currency


def collect(config: dict[str, Any]) -> list[dict[str, Any]]:
    search = config.get("search", {})
    keywords = search.get("title_keywords", ["ai engineer"])
    tags = [t.lower() for t in search.get("tags", ["ai"])]
    source_cfg = config.get("sources", {}).get("himalayas", {})
    page_size = source_cfg.get("page_size", 50)
    max_pages = source_cfg.get("max_pages", 10)
    max_age_days = config.get("himalayas_max_age_days", 14)
    cutoff = datetime.now(timezone.utc).timestamp() - max_age_days * 86400

    jobs: list[dict[str, Any]] = []
    cursor: str | None = None

    for _ in range(max_pages):
        url = f"https://himalayas.app/jobs/api?limit={page_size}"
        if cursor:
            url += f"&cursor={cursor}"
        payload = fetch_json(url)
        batch = payload.get("jobs") or []
        if not batch:
            break

        for item in batch:
            pub = item.get("pubDate")
            if pub and pub < cutoff:
                continue
            title = item.get("title") or ""
            categories = item.get("categories") or []
            title_match = matches_title(title, keywords)
            cat_match = _matches_categories(categories, tags)
            if not (title_match or cat_match):
                continue

            salary_usd, currency = _format_salary(item)
            jobs.append(
                {
                    "source": "himalayas",
                    "url": item.get("applicationLink") or item.get("guid") or "",
                    "role": title,
                    "company": item.get("companyName") or "Unknown",
                    "salary_usd": salary_usd,
                    "currency": currency,
                    "location_note": ", ".join(item.get("locationRestrictions") or []) or "Worldwide",
                    "location_restrictions": item.get("locationRestrictions") or [],
                    "posted_at": pub,
                    "apply_channel": "external_url",
                    "description_snippet": item.get("excerpt") or "",
                }
            )

        cursor = payload.get("nextCursor")
        if not cursor:
            break

    return jobs
