"""Shared job filtering logic."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BLACKLIST_PATH = ROOT / "domain-blacklist.json"

EU_ONLY_PATTERNS = [
    r"\beu\s*[- ]?only\b",
    r"\beurope\s*[- ]?only\b",
    r"\bemea\s*[- ]?only\b",
    r"\beuropean\s+union\s+only\b",
    r"\bmust\s+be\s+located\s+in\s+(?:the\s+)?eu\b",
    r"\bonly\s+(?:within\s+)?europe\b",
    r"\bresidents?\s+of\s+(?:the\s+)?eu\b",
]

US_ONLY_PATTERNS = [
    r"\bus\s*[- ]?only\b",
    r"\busa\s*[- ]?only\b",
    r"\bu\.s\.\s*[- ]?only\b",
    r"\bunited\s+states\s+only\b",
    r"\bmust\s+be\s+(?:a\s+)?(?:us|u\.s\.)\s+citizen\b",
    r"\bonly\s+(?:within\s+)?(?:the\s+)?(?:us|usa|united\s+states)\b",
    r"\bauthorized\s+to\s+work\s+in\s+(?:the\s+)?(?:us|usa|united\s+states)\s+only\b",
]

USD_SALARY_PATTERNS = [
    r"\$\s*\d",
    r"\d+\s*(?:k|K)\s*(?:usd|USD)?",
    r"\bUSD\b",
    r"\busd\b",
    r"\bdollars?\b",
]

EU_LOCATION_LABELS = {
    "europe",
    "eu",
    "emea",
    "european union",
    "uk",
    "united kingdom",
    "germany",
    "france",
    "spain",
    "italy",
    "netherlands",
    "sweden",
    "poland",
    "portugal",
    "ireland",
    "switzerland",
}

US_LOCATION_LABELS = {
    "us",
    "usa",
    "u.s.",
    "united states",
    "north america",
}


def _compile(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


EU_ONLY_RES = _compile(EU_ONLY_PATTERNS)
US_ONLY_RES = _compile(US_ONLY_PATTERNS)
USD_RES = _compile(USD_SALARY_PATTERNS)


def normalize_text(*parts: str | None) -> str:
    return " ".join(p for p in parts if p).lower()


def salary_sort_value(salary_text: str | None) -> float:
    """Comparable USD annual estimate for sorting (higher = better). -1 = unknown."""
    if not salary_text:
        return -1.0
    text = str(salary_text).strip()
    if not text or text == "—":
        return -1.0
    lower = text.lower()
    if "see post" in lower and not re.search(r"\d", text):
        return 0.0

    amounts: list[float] = []
    for match in re.finditer(r"\$?\s*([\d.,]+)\s*([kK])?", text):
        raw = match.group(1)
        has_k = bool(match.group(2))
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw):
            num = float(raw.replace(".", ""))
        else:
            num = float(raw.replace(",", ""))
        if has_k:
            num *= 1000
        amounts.append(num)

    if not amounts:
        return 0.0 if has_usd_salary(text) else -1.0

    peak = max(amounts)
    monthly_hint = any(
        token in lower
        for token in ("/mo", "/month", "per month", "monthly", "mês", "mensal", "mes ", "/m ")
    )
    hourly_hint = any(token in lower for token in ("hourly", "/hr", "per hour", "/hour"))

    if hourly_hint:
        return peak * 160 * 12
    if monthly_hint or (peak < 8000 and not re.search(r"\b(?:year|annual|yr)\b", lower)):
        return peak * 12
    return peak


def sort_jobs_by_salary(jobs: list[dict[str, Any]], *, descending: bool = True) -> list[dict[str, Any]]:
    """Sort jobs by estimated USD annual compensation (eligible/high salary first)."""
    return sorted(
        jobs,
        key=lambda job: (
            salary_sort_value(job.get("salary_usd")),
            1 if job.get("filter_result") == "eligible" else 0,
        ),
        reverse=descending,
    )


def has_usd_salary(salary_text: str | None, currency: str | None = None) -> bool:
    if currency and currency.upper() == "USD":
        return True
    if not salary_text:
        return False
    return any(p.search(salary_text) for p in USD_RES)


def is_eu_only(location: str | None, description: str | None = None) -> bool:
    text = normalize_text(location, description)
    if any(p.search(text) for p in EU_ONLY_RES):
        return True
    loc = (location or "").strip().lower()
    if loc in EU_LOCATION_LABELS:
        return True
    if loc == "europe":
        return True
    return False


def is_us_only(location: str | None, description: str | None = None) -> bool:
    text = normalize_text(location, description)
    if any(p.search(text) for p in US_ONLY_RES):
        return True
    loc = (location or "").strip().lower()
    if loc in US_LOCATION_LABELS:
        return True
    return False


def is_geo_restricted(
    location: str | None,
    location_restrictions: list[str] | None = None,
    description: str | None = None,
    *,
    skip_eu: bool = True,
    skip_us: bool = True,
) -> tuple[bool, str | None]:
    if skip_eu and is_eu_only(location, description):
        return True, "eu_only"
    if skip_us and is_us_only(location, description):
        return True, "us_only"

    if location_restrictions:
        normalized = [r.strip().lower() for r in location_restrictions if r]
        if skip_us and normalized == ["united states"]:
            return True, "us_only"
        if skip_eu and len(normalized) == 1 and normalized[0] in EU_LOCATION_LABELS:
            return True, "eu_only"
        if skip_eu and all(r in EU_LOCATION_LABELS for r in normalized) and normalized:
            return True, "eu_only"

    return False, None


@lru_cache(maxsize=1)
def load_domain_blacklist(blacklist_path: str | None = None) -> dict[str, Any]:
    path = Path(blacklist_path) if blacklist_path else DEFAULT_BLACKLIST_PATH
    if not path.exists():
        return {"domains": [], "url_substrings": []}
    import json

    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {"domains": [], "url_substrings": []}
    data.setdefault("domains", [])
    data.setdefault("url_substrings", [])
    return data


def _normalize_host(url: str) -> str:
    parsed = urlparse(url.strip())
    host = (parsed.netloc or parsed.path.split("/", 1)[0]).lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def is_blacklisted_url(
    url: str | None,
    *,
    blacklist: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """Return (blocked, reason_code) for a job or apply URL."""
    if not url or not str(url).strip():
        return False, None

    data = blacklist if blacklist is not None else load_domain_blacklist()
    normalized = url.strip().lower()

    for entry in data.get("url_substrings", []):
        match = (entry.get("match") or "").lower()
        if match and match in normalized:
            return True, entry.get("reason") or "blacklisted_url"

    host = _normalize_host(normalized)
    if not host:
        return False, None

    for entry in data.get("domains", []):
        domain = (entry.get("domain") or "").lower().lstrip(".")
        if not domain:
            continue
        if host == domain or host.endswith(f".{domain}"):
            return True, entry.get("reason") or "blacklisted_domain"

    return False, None


def job_is_blacklisted(job: dict[str, Any]) -> tuple[bool, str | None]:
    """Check job URL and any apply_url field against the domain blacklist."""
    blocked, reason = is_blacklisted_url(job.get("url"))
    if blocked:
        return True, reason

    blocked, reason = is_blacklisted_url(job.get("apply_url"))
    if blocked:
        return True, reason

    snippet = job.get("description_snippet") or job.get("description") or ""
    for match in re.finditer(r"https?://[^\s\)\]\"']+", snippet, re.IGNORECASE):
        blocked, reason = is_blacklisted_url(match.group(0))
        if blocked:
            return True, reason

    return False, None


def matches_title(title: str, keywords: list[str]) -> bool:
    title_lower = title.lower()
    for kw in keywords:
        kw_lower = kw.lower()
        if len(kw_lower) <= 3:
            if re.search(rf"\b{re.escape(kw_lower)}\b", title_lower):
                return True
        elif kw_lower in title_lower:
            return True
    return False


def evaluate_job(
    job: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Return job with filter_result and skip_reason set."""
    blocked, block_reason = job_is_blacklisted(job)
    if blocked:
        job["filter_result"] = "skipped"
        job["skip_reason"] = block_reason or "blacklisted_domain"
        return job

    filters = config.get("filters", {})
    salary_text = job.get("salary_usd") or job.get("salary") or ""
    currency = job.get("currency")
    location = job.get("location_note") or job.get("location") or ""
    description = job.get("description_snippet") or job.get("description") or ""
    restrictions = job.get("location_restrictions")

    geo_skip, geo_reason = is_geo_restricted(
        location,
        restrictions,
        description,
        skip_eu=filters.get("skip_eu_only", True),
        skip_us=filters.get("skip_us_only", True),
    )
    if geo_skip:
        job["filter_result"] = "skipped"
        job["skip_reason"] = geo_reason
        return job

    if filters.get("require_usd_salary", True):
        if not has_usd_salary(str(salary_text), currency):
            action = filters.get("salary_unknown_action", "skip")
            if action == "needs_review":
                job["filter_result"] = "needs_review"
                job["skip_reason"] = "no_usd_salary"
            else:
                job["filter_result"] = "skipped"
                job["skip_reason"] = "no_usd_salary"
            return job

    job["filter_result"] = "eligible"
    job["skip_reason"] = None
    return job
