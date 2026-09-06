"""RemoteOK collector — uses public JSON API."""

from __future__ import annotations

from typing import Any

from filters import matches_title

from .http_utils import fetch_json


def _parse_jobs(raw: list[Any], keywords: list[str], tags: list[str]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for item in raw:
        if not isinstance(item, dict) or not item.get("position"):
            continue

        job_id = str(item.get("id", ""))
        if job_id in seen_ids:
            continue

        title = item.get("position", "")
        item_tags = [str(t).lower() for t in (item.get("tags") or [])]
        title_match = matches_title(title, keywords)
        tag_match = any(t in item_tags for t in tags)
        if not (title_match or tag_match):
            continue

        seen_ids.add(job_id)
        salary_min = item.get("salary_min")
        salary_max = item.get("salary_max")
        salary_parts = []
        if salary_min:
            salary_parts.append(f"${salary_min:,}")
        if salary_max:
            salary_parts.append(f"${salary_max:,}")
        salary_usd = "–".join(salary_parts) if salary_parts else None

        url = item.get("url") or item.get("apply_url") or f"https://remoteok.com/l/{item.get('id')}"
        if url and not url.startswith("http"):
            url = f"https://remoteok.com{url}"

        jobs.append(
            {
                "source": "remoteok",
                "url": url,
                "role": title,
                "company": item.get("company") or "Unknown",
                "salary_usd": salary_usd,
                "currency": "USD" if salary_usd else None,
                "location_note": item.get("location") or "Remote",
                "posted_at": item.get("epoch") or item.get("date"),
                "apply_channel": "external_url",
                "description_snippet": (item.get("description") or "")[:500],
            }
        )

    return jobs


def collect(config: dict[str, Any]) -> list[dict[str, Any]]:
    search = config.get("search", {})
    keywords = search.get("title_keywords", ["ai engineer"])
    tags = [t.lower() for t in search.get("tags", ["ai"])]

    jobs: list[dict[str, Any]] = []
    api_tags = ["ai", "machine-learning", "llm"]
    for api_tag in api_tags:
        raw = fetch_json(f"https://remoteok.com/api?tag={api_tag}")
        jobs.extend(_parse_jobs(raw, keywords, tags))

    deduped: dict[str, dict[str, Any]] = {}
    for job in jobs:
        deduped[job["url"]] = job
    return list(deduped.values())
