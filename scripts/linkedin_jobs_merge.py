#!/usr/bin/env python3
"""Merge LinkedIn Jobs search results into the job-search registry."""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from filters import evaluate_job, is_blacklisted_url  # noqa: E402
from linkedin_posts_merge import (  # noqa: E402
    parse_linkedin_relative_posted_at,
    sort_jobs_by_recency,
)
from registry import (  # noqa: E402
    LOCAL_TZ,
    REGISTRY_PATH,
    RUNS_DIR,
    job_key,
    load_json,
    load_registry,
    merge_jobs,
    parse_since,
    save_json,
    save_registry,
)
from track_store import load_linkedin_jobs_config  # noqa: E402

JOB_VIEW_RE = re.compile(r"/jobs/view/(?P<id>\d+)", re.I)
JOB_ID_ATTR_RE = re.compile(r'data-job-id="(?P<id>\d+)"', re.I)
TITLE_IN_CHUNK_RE = re.compile(
    r'jobs/view/(?P<id>\d+)[^"]*"[^>]*>(?P<title>[^<]{2,200})',
    re.I,
)
COMPANY_IN_CHUNK_RE = re.compile(
    r'base-search-card__subtitle[^>]*>(?P<company>[^<]{1,200})',
    re.I,
)
LOCATION_IN_CHUNK_RE = re.compile(
    r'job-search-card__location[^>]*>(?P<location>[^<]{1,200})',
    re.I,
)
RELATIVE_POSTED_RE = re.compile(
    r"(?:(?P<now>now)|(?P<num>\d+)\s*(?P<unit>m|h|d|w|mo))\s*(?:ago|•|$)",
    re.IGNORECASE,
)
JOB_POSTED_RE = re.compile(
    r"(?:Reposted\s+)?(?:(?P<now>now)|(?P<num>\d+)\s*(?P<unit>minutes?|hours?|days?|weeks?|months?|m|h|d|w|mo))\s*ago",
    re.IGNORECASE,
)

JOBS_STATE_PATH = ROOT / "state" / "linkedin-jobs-last-run.json"
JOB_SEARCH_CONFIG = ROOT / "config.json"
LOGIN_SCRIPT = SCRIPTS / "linkedin-login.sh"
JOBS_PER_PAGE = 25

REGION_DISPLAY: dict[str, str] = {
    "latam": "LATAM",
    "worldwide": "Worldwide",
}

JOB_TITLE_LINK_RE = re.compile(
    r'class="[^"]*job-card-list__title[^"]*"[^>]*href="[^"]*jobs/view/(?P<id>\d+)[^"]*"[^>]*>\s*(?P<title>[^<]+)',
    re.I,
)
JOB_HREF_TITLE_RE = re.compile(
    r'href="[^"]*jobs/view/(?P<id>\d+)[^"]*"[^>]*(?:title="(?P<title_attr>[^"]+)")?[^>]*>\s*(?P<title>[^<]{2,200})',
    re.I,
)
PLACEHOLDER_TITLE_RE = re.compile(r"^Job\s+\d+$", re.I)


def normalize_job_view_url(job_id: str) -> str:
    return f"https://www.linkedin.com/jobs/view/{job_id}/"


def extract_job_view_id(url: str | None) -> str | None:
    if not url:
        return None
    match = JOB_VIEW_RE.search(url)
    return match.group("id") if match else None


def period_to_time_posted(days: int, cfg: dict[str, Any]) -> str:
    mapping = cfg.get("time_posted_map") or {
        "1": "r86400",
        "7": "r604800",
        "30": "r2592000",
    }
    key = str(days)
    if key in mapping:
        return mapping[key]
    for candidate in ("7", "1", "30"):
        if candidate in mapping:
            return mapping[candidate]
    return "r604800"


def build_query_string(role: str, region: str, cfg: dict[str, Any]) -> str:
    template = cfg.get("query_template", "{role}")
    if "{region}" in template:
        return template.format(role=role, region=REGION_DISPLAY.get(region, region))
    return template.format(role=role)


def _normalize_posted_unit(unit: str) -> str:
    u = (unit or "").lower()
    if u.startswith("minute") or u == "m":
        return "m"
    if u.startswith("hour") or u == "h":
        return "h"
    if u.startswith("day") or u == "d":
        return "d"
    if u.startswith("week") or u == "w":
        return "w"
    if u.startswith("month") or u == "mo":
        return "mo"
    return u[:1] if u else "d"


def extract_posted_label(*texts: str) -> str:
    """Parse LinkedIn job card posted strings including 'Reposted 3 hours ago'."""
    for raw in texts:
        if not raw:
            continue
        match = JOB_POSTED_RE.search(raw)
        if match:
            if match.group("now"):
                return "now"
            return f"{match.group('num')}{_normalize_posted_unit(match.group('unit') or 'd')}"
        match = RELATIVE_POSTED_RE.search(raw)
        if match:
            if match.group("now"):
                return "now"
            return f"{match.group('num')}{match.group('unit')}"
    return ""


def posted_within_hours(job: dict[str, Any], hours: int = 24, *, now: datetime | None = None) -> bool:
    ref = now or datetime.now(LOCAL_TZ)
    posted = job.get("posted_at")
    if posted:
        from registry import parse_posted_at  # noqa: WPS433

        dt = parse_posted_at(posted)
        if dt:
            dt = dt.astimezone(LOCAL_TZ) if dt.tzinfo else dt.replace(tzinfo=LOCAL_TZ)
            return (ref - dt).total_seconds() <= hours * 3600
    label = (job.get("posted_label") or "").strip().lower()
    if label in {"now"}:
        return True
    m = re.fullmatch(r"(\d+)(m|h|d|w|mo)", label)
    if not m:
        return False
    num = int(m.group(1))
    unit = m.group(2)
    if unit == "m":
        return num <= hours * 60
    if unit == "h":
        return num <= hours
    if unit == "d":
        return num * 24 <= hours
    return False


def region_search_variants(region: str, cfg: dict[str, Any]) -> list[dict[str, str]]:
    """Expand a region into concrete LinkedIn location/geo search variants."""
    alts = (cfg.get("region_location_alts") or {}).get(region)
    default = (cfg.get("region_locations") or {}).get(region, "")
    geo_map = cfg.get("region_geo_ids") or {}
    if alts:
        locations = [str(x).strip() for x in alts if str(x).strip()]
    elif default:
        locations = [default]
    else:
        locations = [""]
    variants: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for loc in locations:
        geo_id = (geo_map.get(region) or "") if loc else ""
        key = (loc.casefold(), geo_id)
        if key in seen:
            continue
        seen.add(key)
        variants.append(
            {
                "location": loc,
                "geo_id": geo_id,
                "location_label": loc or REGION_DISPLAY.get(region, region.title()),
            }
        )
    return variants


def role_names_for_track(track_id: str, cfg: dict[str, Any]) -> list[str]:
    roles = [str(r).strip() for r in (cfg.get("roles") or []) if str(r).strip()]
    if roles:
        return roles
    from track_store import track_label  # noqa: WPS433

    return [track_label(track_id)]


def build_queries(cfg: dict[str, Any], *, track_id: str | None = None) -> list[dict[str, str]]:
    tid = track_id or "ai-engineer"
    roles = role_names_for_track(tid, cfg)
    suffixes = cfg.get("region_suffixes", ["latam", "worldwide"])
    period = int(cfg.get("default_period_days", 1))
    queries: list[dict[str, str]] = []
    for role in roles:
        for suffix in suffixes:
            query = build_query_string(role, suffix, cfg)
            for variant in region_search_variants(suffix, cfg):
                queries.append(
                    {
                        "query": query,
                        "role_keyword": role,
                        "role_label": role,
                        "region": suffix,
                        "region_label": REGION_DISPLAY.get(suffix, suffix.title()),
                        "location_label": variant["location_label"],
                        "search_location": variant["location"],
                        "search_geo_id": variant["geo_id"],
                        "track": tid,
                        "linkedin_url": linkedin_jobs_search_url(
                            query,
                            region=suffix,
                            period_days=period,
                            cfg=cfg,
                            location=variant["location"],
                            geo_id=variant["geo_id"],
                        ),
                    }
                )
    return queries


def build_all_track_queries() -> list[dict[str, str]]:
    from track_store import list_track_ids, load_linkedin_jobs_config  # noqa: WPS433

    all_queries: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for tid in list_track_ids():
        cfg = load_linkedin_jobs_config(tid)
        if not cfg.get("jobs_collect_enabled", True):
            continue
        for item in build_queries(cfg, track_id=tid):
            key = (
                item["track"],
                item["role_keyword"].casefold(),
                item["region"],
                (item.get("search_location") or "").casefold(),
            )
            if key in seen:
                continue
            seen.add(key)
            all_queries.append(item)
    return all_queries


def linkedin_jobs_search_url(
    query: str,
    *,
    region: str,
    period_days: int,
    cfg: dict[str, Any],
    start: int = 0,
    location: str | None = None,
    geo_id: str | None = None,
) -> str:
    params: dict[str, str] = {
        "keywords": query,
        "origin": "JOB_SEARCH_PAGE_JOB_FILTER",
        "sortBy": "DD",
        "f_TPR": period_to_time_posted(period_days, cfg),
    }
    if start > 0:
        params["start"] = str(start)
    if cfg.get("remote_only", False):
        params["f_WT"] = "2"
    salary = (cfg.get("salary_filter") or "").strip()
    if salary:
        params["f_SAL"] = salary
    loc = location if location is not None else (cfg.get("region_locations") or {}).get(region, "")
    gid = geo_id if geo_id is not None else (cfg.get("region_geo_ids") or {}).get(region, "")
    if loc:
        params["location"] = loc
    elif gid:
        params["geoId"] = gid
    return "https://www.linkedin.com/jobs/search/?" + urllib.parse.urlencode(params)


def with_search_start(url: str, start: int) -> str:
    if start <= 0:
        return url
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    flat = {k: (v[0] if isinstance(v, list) and v else v) for k, v in params.items()}
    flat["start"] = str(start)
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(flat)))


def _dedupe_repeated_title(title: str) -> str:
    text = title.strip()
    if len(text) < 10:
        return text
    for split in range(len(text) // 2, 0, -1):
        head = text[:split].strip()
        tail = text[split:].strip()
        if tail == head:
            return head
    return text


def normalize_listing_title(title: str, role_keyword: str = "") -> str:
    cleaned = re.sub(r"\s+", " ", (title or "").strip())
    cleaned = re.sub(r"\s+with verification\s*$", "", cleaned, flags=re.I).strip()
    cleaned = _dedupe_repeated_title(cleaned)
    if not cleaned or PLACEHOLDER_TITLE_RE.match(cleaned) or cleaned.isdigit():
        fallback = (role_keyword or "").strip()
        return fallback.title() if fallback else cleaned
    return cleaned


def _extract_title_from_chunk(chunk: str, job_id: str) -> str:
    for pattern in (JOB_TITLE_LINK_RE, JOB_HREF_TITLE_RE, TITLE_IN_CHUNK_RE):
        match = pattern.search(chunk)
        if match and match.group("id") == job_id:
            groups = match.groupdict()
            title = groups.get("title") or groups.get("title_attr") or ""
            title = re.sub(r"\s+", " ", title).strip()
            if title:
                return title
    aria = re.search(rf'aria-label="([^"]*{job_id}[^"]*)"', chunk, re.I)
    if aria:
        return re.sub(r"\s+", " ", aria.group(1)).strip()
    return ""


def merge_listings_by_id(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for group in groups:
        for item in group:
            jid = str(item.get("job_id") or "").strip()
            if not jid:
                continue
            if jid not in merged:
                order.append(jid)
                merged[jid] = dict(item)
                continue
            prev = merged[jid]
            for key, value in item.items():
                if value in (None, "", "—") or PLACEHOLDER_TITLE_RE.match(str(value)):
                    continue
                prev[key] = value
    return [merged[jid] for jid in order]


def audit_collect_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize a collect run; flag placeholder titles and low page counts."""
    issues: list[str] = []
    by_track: dict[str, dict[str, int]] = {}
    placeholder_titles = 0
    missing_company = 0
    total_listings = 0
    total_pages = 0

    for result in results:
        track = str(result.get("track") or "unknown")
        region = str(result.get("region") or "unknown")
        bucket = by_track.setdefault(track, {"listings": 0, "queries": 0})
        bucket["queries"] += 1

        listings = result.get("listings") or []
        if not listings and result.get("raw_path"):
            try:
                data = json.loads(Path(result["raw_path"]).read_text(encoding="utf-8"))
                listings = data.get("listings") or []
            except (OSError, json.JSONDecodeError):
                pass

        total_listings += len(listings)
        bucket["listings"] += len(listings)

        page_stats = result.get("page_stats") or {}
        pages = int(page_stats.get("pages") or 0)
        total_pages += pages
        if pages <= 1 and len(listings) >= 20:
            issues.append(f"{track}/{region}: only 1 page scraped but {len(listings)} listings")

        for listing in listings:
            title = str(listing.get("title") or "")
            if PLACEHOLDER_TITLE_RE.match(title.strip()):
                placeholder_titles += 1
            if (listing.get("company") or "—") == "—":
                missing_company += 1

        role = str(result.get("role_keyword") or "")
        if listings and all(PLACEHOLDER_TITLE_RE.match(str(x.get("title") or "").strip()) for x in listings):
            issues.append(f"{track}/{region}/{role}: all titles are placeholders")

    if placeholder_titles:
        issues.append(f"{placeholder_titles} listings still use placeholder titles (Job <id>)")
    if total_listings < 10 and len(results) >= 2:
        issues.append(f"only {total_listings} total listings across {len(results)} queries (expected more)")

    return {
        "ok": not issues,
        "issues": issues,
        "total_listings": total_listings,
        "total_pages": total_pages,
        "placeholder_titles": placeholder_titles,
        "missing_company": missing_company,
        "by_track": by_track,
        "query_count": len(results),
    }


def _extract_company_from_chunk(chunk: str) -> str:
    match = COMPANY_IN_CHUNK_RE.search(chunk)
    return re.sub(r"\s+", " ", match.group("company")).strip() if match else ""


def _extract_location_from_chunk(chunk: str) -> str:
    match = LOCATION_IN_CHUNK_RE.search(chunk)
    return re.sub(r"\s+", " ", match.group("location")).strip() if match else ""


def _extract_posted_label_from_chunk(chunk: str) -> str:
    return extract_posted_label(chunk)


def _detect_apply_method(chunk: str) -> tuple[bool, str]:
    if re.search(r"Easy Apply", chunk, re.I):
        return True, "easy_apply"
    if re.search(r"Apply on company website|Apply on external site", chunk, re.I):
        return False, "external"
    return False, "unknown"


def parse_listings_from_html(html: str, inner_text: str = "") -> list[dict[str, Any]]:
    """Parse job cards from LinkedIn jobs search HTML (see playbooks/linkedin-jobs-search.md)."""
    listings: list[dict[str, Any]] = []
    seen: set[str] = set()

    id_matches = list(JOB_ID_ATTR_RE.finditer(html))
    for idx, match in enumerate(id_matches):
        job_id = match.group("id")
        if job_id in seen:
            continue
        seen.add(job_id)
        start = match.start()
        end = id_matches[idx + 1].start() if idx + 1 < len(id_matches) else min(len(html), match.end() + 1800)
        chunk = html[start:end]
        easy_apply, apply_method = _detect_apply_method(chunk)
        title = _extract_title_from_chunk(chunk, job_id)
        if not title or PLACEHOLDER_TITLE_RE.match(title):
            title = ""
        company = _extract_company_from_chunk(chunk)
        location = _extract_location_from_chunk(chunk)
        posted_label = _extract_posted_label_from_chunk(chunk)
        listings.append(
            {
                "job_id": job_id,
                "url": normalize_job_view_url(job_id),
                "title": title,
                "company": company or "—",
                "location": location,
                "posted_label": posted_label,
                "easy_apply": easy_apply,
                "apply_method": apply_method,
            }
        )

    text_listings = parse_listings_from_text(inner_text) if inner_text else []
    if listings or text_listings:
        return merge_listings_by_id(listings, text_listings)

    for job_id in extract_job_ids_from_html(html):
        if job_id in seen:
            continue
        seen.add(job_id)
        listings.append(
            {
                "job_id": job_id,
                "url": normalize_job_view_url(job_id),
                "title": "",
                "company": "—",
                "location": "",
                "posted_label": "",
                "easy_apply": "Easy Apply" in html,
                "apply_method": "easy_apply" if "Easy Apply" in html else "unknown",
            }
        )

    return listings


def extract_job_ids_from_html(html: str) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for match in JOB_VIEW_RE.finditer(html):
        job_id = match.group("id")
        if job_id not in seen:
            seen.add(job_id)
            ordered.append(job_id)
    return ordered


def parse_listings_from_text(raw: str) -> list[dict[str, Any]]:
    """Fallback parser when only innerText is available."""
    listings: list[dict[str, Any]] = []
    seen: set[str] = set()

    for view_match in re.finditer(r"linkedin\.com/jobs/view/(\d+)", raw, re.I):
        job_id = view_match.group(1)
        if job_id in seen:
            continue
        seen.add(job_id)
        start = max(0, view_match.start() - 400)
        end = min(len(raw), view_match.end() + 400)
        block = raw[start:end]
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        title = ""
        company = "—"
        location = ""
        posted_label = ""
        for line in lines:
            lower = line.lower()
            if line in {"Easy Apply", "Apply on company website", "Viewed", "Promoted"}:
                continue
            if re.match(r"^\d[\d,]*\s+results?$", line, re.I):
                continue
            if " in " in lower and "linkedin" not in lower and not title:
                continue
            if RELATIVE_POSTED_RE.search(line):
                rel = RELATIVE_POSTED_RE.search(line)
                posted_label = rel.group(0).strip() if rel else ""
                continue
            if not title and not re.search(r"jobs/view", line, re.I):
                title = line
                continue
            if company == "—" and not RELATIVE_POSTED_RE.search(line):
                company = line
                continue
            if not location and ("remote" in lower or "·" in line or "," in line):
                location = line
        easy_apply = bool(re.search(r"Easy Apply", block, re.I))
        apply_method = "easy_apply" if easy_apply else "unknown"
        listings.append(
            {
                "job_id": job_id,
                "url": normalize_job_view_url(job_id),
                "title": title,
                "company": company,
                "location": location,
                "posted_label": posted_label,
                "easy_apply": easy_apply,
                "apply_method": apply_method,
            }
        )

    if listings:
        return listings

    blocks = re.split(r"\n{2,}", raw)
    for block in blocks:
        view_match = re.search(r"linkedin\.com/jobs/view/(\d+)", block, re.I)
        if not view_match:
            continue
        job_id = view_match.group(1)
        if job_id in seen:
            continue
        seen.add(job_id)
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        title = lines[0] if lines else ""
        company = "—"
        location = ""
        posted_label = ""
        for line in lines[1:6]:
            if line in {"Easy Apply", "Apply on company website"}:
                continue
            if RELATIVE_POSTED_RE.search(line):
                rel = RELATIVE_POSTED_RE.search(line)
                posted_label = rel.group(0).strip() if rel else ""
                continue
            if company == "—" and not RELATIVE_POSTED_RE.search(line):
                company = line
                continue
            if not location and ("remote" in line.lower() or "·" in line):
                location = line
        easy_apply = bool(re.search(r"Easy Apply", block, re.I))
        apply_method = "easy_apply" if easy_apply else "unknown"
        listings.append(
            {
                "job_id": job_id,
                "url": normalize_job_view_url(job_id),
                "title": title,
                "company": company,
                "location": location,
                "posted_label": posted_label,
                "easy_apply": easy_apply,
                "apply_method": apply_method,
            }
        )
    return listings


def existing_job_view_ids(registry: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for job in registry.get("jobs", []):
        for field in ("url", "apply_url"):
            jid = extract_job_view_id(job.get(field))
            if jid:
                ids.add(jid)
    return ids


def _eval_config(jobs_cfg: dict[str, Any], job_search_config: dict[str, Any]) -> dict[str, Any]:
    cfg = copy.deepcopy(job_search_config)
    filters = cfg.setdefault("filters", {})
    if jobs_cfg.get("require_usd_salary"):
        filters["require_usd_salary"] = True
        filters.setdefault("salary_unknown_action", "needs_review")
    else:
        filters["require_usd_salary"] = False
    return cfg


def listing_to_job(
    listing: dict[str, Any],
    query_meta: dict[str, str],
    jobs_cfg: dict[str, Any],
    job_search_config: dict[str, Any],
) -> dict[str, Any] | None:
    url = (listing.get("url") or "").strip()
    if not url:
        return None
    blocked, _ = is_blacklisted_url(url)
    if blocked:
        return None

    region = query_meta.get("region", "")
    location_note = listing.get("location") or ("LATAM" if region == "latam" else "Worldwide")
    posted_label = extract_posted_label(
        listing.get("posted_label") or "",
        listing.get("location") or "",
        listing.get("card_text") or "",
    )
    posted_at = None
    if posted_label:
        rel = parse_linkedin_relative_posted_at(f"{posted_label} •")
        if rel:
            posted_at = rel.isoformat()

    role = normalize_listing_title(
        str(listing.get("title") or ""),
        str(query_meta.get("role_keyword") or ""),
    )
    if not role:
        role = (query_meta.get("role_keyword") or "AI Engineer").strip()
    company = (listing.get("company") or "—").strip()
    easy_apply = bool(listing.get("easy_apply"))
    apply_method = listing.get("apply_method") or ("easy_apply" if easy_apply else "unknown")

    job: dict[str, Any] = {
        "source": "linkedin_jobs",
        "url": url,
        "apply_url": url,
        "role": role,
        "company": company,
        "salary_usd": None,
        "currency": None,
        "location_note": location_note,
        "posted_at": posted_at,
        "posted_label": posted_label or None,
        "description_snippet": f"{role} at {company}. {location_note}.",
        "search_query": query_meta.get("query"),
        "region_tag": region,
        "linkedin_easy_apply": easy_apply,
        "apply_method": apply_method,
    }
    if query_meta.get("track"):
        job["track"] = query_meta["track"]
    if listing.get("discovery_index") is not None:
        job["discovery_index"] = listing["discovery_index"]

    evaluate_job(job, _eval_config(jobs_cfg, job_search_config))
    return job


def normalize_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for query in payload.get("queries", []):
        meta = {
            "query": query.get("query", ""),
            "role_keyword": query.get("role_keyword", ""),
            "region": query.get("region", ""),
            "track": query.get("track"),
        }
        listings = query.get("listings") or []
        if not listings and query.get("search_payload"):
            sp = query["search_payload"]
            listings = parse_listings_from_html(
                sp.get("html") or "",
                sp.get("inner_text") or "",
            )
        for idx, listing in enumerate(listings):
            enriched = dict(listing)
            enriched.setdefault("discovery_index", idx)
            items.append({"listing": enriched, "query_meta": meta})
    return items


def merge_payload(
    payload: dict[str, Any],
    period_days: int,
    since_arg: str | None = None,
    *,
    track_id: str | None = None,
) -> dict[str, Any]:
    jobs_cfg = load_linkedin_jobs_config(track_id)
    job_search_config = load_json(JOB_SEARCH_CONFIG, {})
    linkedin_state = load_json(JOBS_STATE_PATH, {"last_run_at": None})

    period_days = int(payload.get("period_days") or period_days)
    since = parse_since(since_arg or f"{period_days}d", linkedin_state.get("last_run_at"))

    registry = load_registry()
    known_view_ids = existing_job_view_ids(registry)
    incoming: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    skipped_cross = 0

    for item in normalize_payload(payload):
        listing = item["listing"]
        jid = extract_job_view_id(listing.get("url"))
        if jid and jid in known_view_ids:
            skipped_cross += 1
            continue
        job = listing_to_job(listing, item["query_meta"], jobs_cfg, job_search_config)
        if not job:
            continue
        key = job_key(job)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        incoming.append(job)
        if jid:
            known_view_ids.add(jid)

    registry, new_jobs = merge_jobs(registry, incoming, since)
    now = datetime.now(LOCAL_TZ)
    run_path = RUNS_DIR / f"linkedin-jobs-{now.strftime('%Y-%m-%dT%H-%M')}.md"

    save_registry(registry)
    write_jobs_run_markdown(
        run_path,
        since,
        incoming,
        new_jobs,
        period_days,
        len(payload.get("queries", [])),
        jobs_cfg,
        skipped_cross,
    )
    save_json(JOBS_STATE_PATH, {"last_run_at": now.isoformat()})

    return {
        "run_path": str(run_path),
        "registry_path": str(REGISTRY_PATH),
        "period_days": period_days,
        "queries_run": len(payload.get("queries", [])),
        "listings_parsed": len(incoming),
        "skipped_cross_dedup": skipped_cross,
        "new_total": len(new_jobs),
        "eligible": len([j for j in new_jobs if j.get("filter_result") == "eligible"]),
        "needs_review": len([j for j in new_jobs if j.get("filter_result") == "needs_review"]),
    }


def write_jobs_run_markdown(
    run_path: Path,
    since: datetime,
    incoming: list[dict[str, Any]],
    new_jobs: list[dict[str, Any]],
    period_days: int,
    query_count: int,
    cfg: dict[str, Any],
    skipped_cross: int,
) -> None:
    run_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# LinkedIn Jobs collect",
        "",
        f"**Since:** {since.isoformat()}",
        f"**Period days:** {period_days}",
        f"**Queries:** {query_count}",
        f"**Cross-dedup skipped:** {skipped_cross}",
        f"**Parsed:** {len(incoming)} · **New:** {len(new_jobs)}",
        "",
        "## New roles",
        "",
        "| Role | Company | Easy Apply | Filter | URL |",
        "|------|---------|------------|--------|-----|",
    ]
    ranked = sort_jobs_by_recency(new_jobs) if cfg.get("table_sort") == "date_posted" else new_jobs
    for job in ranked[:50]:
        easy = "yes" if job.get("linkedin_easy_apply") else "no"
        lines.append(
            f"| {job.get('role', '—')} | {job.get('company', '—')} | {easy} | "
            f"{job.get('filter_result', '—')} | {job.get('url', '—')} |"
        )
    run_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def check_linkedin_session() -> tuple[bool, str]:
    if not LOGIN_SCRIPT.exists():
        return False, f"Login script missing: {LOGIN_SCRIPT}"
    try:
        result = subprocess.run(
            [str(LOGIN_SCRIPT), "status"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    out = (result.stdout or result.stderr or "").strip()
    if result.returncode == 0:
        return True, out or "LinkedIn session OK"
    return False, out or f"LinkedIn session check failed (exit {result.returncode})"


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge LinkedIn Jobs search JSON into registry.")
    parser.add_argument("--input", "-i", help="JSON file from linkedin_jobs_collect.py")
    parser.add_argument("--period", type=int, default=None)
    parser.add_argument("--since", help='Dedup window: "last-run", "7d", or ISO date')
    parser.add_argument("--track", default=None)
    parser.add_argument("--print-queries", action="store_true")
    parser.add_argument("--check-session", action="store_true")
    args = parser.parse_args()

    if args.check_session:
        ok, msg = check_linkedin_session()
        print(msg)
        return 0 if ok else 1

    cfg = load_linkedin_jobs_config(args.track)
    if args.print_queries:
        period = args.period or cfg.get("default_period_days", 7)
        print(
            json.dumps(
                {
                    "period_days": period,
                    "time_posted": period_to_time_posted(period, cfg),
                    "max_pages": cfg.get("default_max_pages", 5),
                    "queries": build_queries(cfg),
                },
                indent=2,
            )
        )
        return 0

    if not args.input:
        parser.error("--input is required unless using --print-queries or --check-session")

    period = args.period if args.period is not None else cfg.get("default_period_days", 7)
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    payload.setdefault("period_days", period)
    result = merge_payload(payload, period, args.since, track_id=args.track)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
