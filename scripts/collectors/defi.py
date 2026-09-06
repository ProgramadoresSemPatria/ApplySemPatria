"""DeFi.jobs collector — static HTML listing."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from filters import matches_title

from .http_utils import fetch_text

JOB_LINK_RE = re.compile(r'href="(/jobs/[^"]+)"')


def collect(config: dict[str, Any]) -> list[dict[str, Any]]:
    search = config.get("search", {})
    keywords = search.get("title_keywords", ["ai engineer"])
    base_url = config.get("sources", {}).get("defi", {}).get("base_url", "https://www.defi.jobs")

    html = fetch_text(base_url)
    slugs = []
    seen = set()
    for match in JOB_LINK_RE.finditer(html):
        path = match.group(1)
        if path in seen:
            continue
        seen.add(path)
        slug = path.rsplit("/", 1)[-1]
        role_guess = slug.replace("-", " ")
        if matches_title(role_guess, keywords) or matches_title(slug, keywords):
            slugs.append(path)

    jobs: list[dict[str, Any]] = []
    for path in slugs:
        url = urljoin(base_url, path)
        page = fetch_text(url)
        title_match = re.search(r"<title>([^<|]+)", page, re.IGNORECASE)
        role = title_match.group(1).strip() if title_match else path.rsplit("/", 1)[-1].replace("-", " ")
        role = re.sub(r"\s*-\s*DeFi\.jobs.*", "", role, flags=re.IGNORECASE).strip()
        company_match = re.search(r"company[^>]*>([^<]+)", page, re.IGNORECASE)
        company = company_match.group(1).strip() if company_match else "Unknown"
        text_only = re.sub(r"<[^>]+>", " ", page)
        salary_match = re.search(r"\$\s?\d[\d,]*", text_only)
        salary_usd = salary_match.group(0) if salary_match else None

        jobs.append(
            {
                "source": "defi",
                "url": url,
                "role": role,
                "company": company,
                "salary_usd": salary_usd,
                "currency": "USD" if salary_usd else None,
                "location_note": "Remote",
                "posted_at": None,
                "apply_channel": "external_url",
                "description_snippet": text_only[:500],
            }
        )

    return jobs
