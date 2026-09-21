"""We Work Remotely collector — uses RSS feed."""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from typing import Any

from filters import matches_title

from .http_utils import fetch_text

NS = {"content": "http://purl.org/rss/1.0/modules/content/"}


def _strip_html(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_title(raw_title: str) -> tuple[str, str]:
    if ":" in raw_title:
        company, role = raw_title.split(":", 1)
        return company.strip(), role.strip()
    return "Unknown", raw_title.strip()


def _extract_salary(text: str) -> str | None:
    patterns = [
        r"\$\s?\d[\d,]*(?:\s?[-–]\s?\$?\s?\d[\d,]*)?(?:\s?(?:k|K|USD|usd|per year|/yr))?",
        r"\b\d{2,3}\s?[kK]\s?(?:USD|usd)?\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            value = match.group(0).strip()
            if value.lower() in {"401k", "401 k"}:
                continue
            if re.fullmatch(r"\$?\d{1,2}\b", value.replace(",", "")):
                continue
            return value
    return None


def collect(config: dict[str, Any]) -> list[dict[str, Any]]:
    search = config.get("search", {})
    keywords = search.get("title_keywords", ["ai engineer"])
    rss_url = config.get("sources", {}).get("weworkremotely", {}).get(
        "rss_url", "https://weworkremotely.com/categories/remote-programming-jobs.rss"
    )

    xml_text = fetch_text(rss_url)
    root = ET.fromstring(xml_text)
    jobs: list[dict[str, Any]] = []

    for item in root.findall(".//item"):
        title_raw = item.findtext("title") or ""
        company, role = _parse_title(title_raw)
        if not matches_title(role, keywords) and not matches_title(title_raw, keywords):
            continue

        link = item.findtext("link") or ""
        region = item.findtext("region") or "Remote"
        pub_date = item.findtext("pubDate")
        description_html = item.findtext("description") or ""
        description_text = _strip_html(description_html)
        salary_usd = _extract_salary(description_text)

        jobs.append(
            {
                "source": "weworkremotely",
                "url": link,
                "role": role,
                "company": company,
                "salary_usd": salary_usd,
                "currency": "USD" if salary_usd else None,
                "location_note": region,
                "posted_at": pub_date,
                "apply_channel": "external_url",
                "description_snippet": description_text[:500],
            }
        )

    return jobs
