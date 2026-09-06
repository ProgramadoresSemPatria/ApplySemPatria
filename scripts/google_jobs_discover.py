#!/usr/bin/env python3
"""Google-style job discovery: search, analyze pages, merge sorted table (max 20)."""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from html import unescape
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from filters import evaluate_job, has_usd_salary, is_blacklisted_url, is_eu_only, is_us_only, matches_title  # noqa: E402
from registry import (  # noqa: E402
    LOCAL_TZ,
    RUNS_DIR,
    load_json,
    load_registry,
    merge_jobs,
    save_registry,
    write_run_markdown,
)

CONFIG_PATH = ROOT / "google-jobs-config.json"
STATE_PATH = ROOT / "state" / "google-last-run.json"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

NOISE_URL_PARTS = (
    "github.com",
    "youtube.com",
    "medium.com",
    "substack.com",
    "wikipedia.org",
    "reddit.com",
    "/blog/",
    "/news/",
    "axiomlogica.com",
    "rahulkolekar.com",
    "sukruyusufkaya.com",
)

JOB_URL_HINTS = (
    "/job",
    "/jobs/",
    "/careers/",
    "/apply",
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "workday",
    "remote-jobs",
    "oneseventech.com",
    "hiretik.com",
    "jobs.",
)

JS_SHELL_MARKERS = (
    "requires javascript",
    "enable javascript",
    "javascript is disabled",
    "please enable javascript",
)


def load_config() -> dict[str, Any]:
    return load_json(CONFIG_PATH, {})


def build_query(role: str, after_date: str, cfg: dict[str, Any]) -> str:
    template = cfg.get(
        "query_template",
        '"{role}" "rag" "llm" remote after:{after_date}',
    )
    return template.format(role=role, after_date=after_date)


def default_after_date(cfg: dict[str, Any]) -> str:
    days = int(cfg.get("default_after_days", 7))
    return (datetime.now(LOCAL_TZ).date() - timedelta(days=days)).isoformat()


def search_google_cse(query: str, cfg: dict[str, Any], max_results: int = 10) -> list[dict[str, str]]:
    cse = cfg.get("google_cse", {})
    api_key = os.environ.get(cse.get("api_key_env", "GOOGLE_CSE_API_KEY"), "")
    cx = os.environ.get(cse.get("cx_env", "GOOGLE_CSE_CX"), "")
    if not api_key or not cx:
        return []

    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "num": min(max_results, 10),
    }
    date_restrict = cse.get("date_restrict")
    if date_restrict:
        params["dateRestrict"] = date_restrict

    url = "https://www.googleapis.com/customsearch/v1?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    results = []
    for item in data.get("items", []):
        results.append(
            {
                "url": item.get("link", ""),
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
            }
        )
    return results


def fetch_page(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        raw = resp.read(500_000)
    text = raw.decode("utf-8", errors="replace")
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(re.sub(r"\s+", " ", text)).strip()
    return text


def is_noise_url(url: str) -> bool:
    blocked, _ = is_blacklisted_url(url)
    if blocked:
        return True
    lower = url.lower()
    if any(part in lower for part in NOISE_URL_PARTS):
        return True
    return not any(hint in lower for hint in JOB_URL_HINTS) and "job" not in lower


def page_is_js_shell(text: str) -> bool:
    lower = text.lower()
    return len(text) < 250 or any(m in lower for m in JS_SHELL_MARKERS)


def looks_like_job_page(text: str, title: str, url: str, *, snippet: str = "") -> bool:
    if is_noise_url(url):
        return False
    lower = (text + " " + title + " " + snippet).lower()
    hints = ["apply", "hiring", "responsibilities", "requirements", "qualifications", "full-time", "remote", "posted"]
    hits = sum(1 for h in hints if h in lower)
    role_hits = any(k in lower for k in ("engineer", "developer", "architect"))
    if hits >= 2 and role_hits:
        return True
    # JS-rendered boards: trust snippet + known job URL when page fetch is empty
    if snippet and not is_noise_url(url) and role_hits and hits >= 1:
        return True
    return False


def geo_blocked(text: str) -> tuple[bool, str | None]:
    lower = text.lower()

    if latam_friendly(text):
        latam_hiring = any(
            re.search(p, lower)
            for p in (
                r"\b(?:latam|latin\s+america)\s+only\b",
                r"\bremote\s+anywhere\s+in\s+latin\s+america\b",
                r"\banywhere\s+in\s+latin\s+america\b",
                r"\blimited\s+to\s+candidates\s+based\s+in\s+latam\b",
                r"\bengineering\s+-\s+latam\b",
                r"\bregion\s+latam\b",
            )
        )
        if latam_hiring:
            return False, None

    explicit = [
        r"\bonly\s+(?:open\s+to\s+)?candidates\s+in\s+(?:the\s+)?usa\b",
        r"\bopen\s+to\s+candidates\s+in\s+usa\b",
        r"\bremote\s+in\s+usa\b",
        r"\bremote,\s*usa\b",
        r"\bus\s+only\b",
        r"\busa\s+only\b",
        r"\beu\s+only\b",
        r"\beurope\s+only\b",
        r"\bmust\s+be\s+located\s+in\s+(?:the\s+)?united\s+states\b",
        r"\bw2\s+only\b",
        r"\bremote\s*\(\s*us\s*/\s*canada\s*\)\b",
        r"\bwithin\s+the\s+united\s+states\s+or\s+canada\b",
    ]
    for pat in explicit:
        if re.search(pat, lower):
            return True, "geo_restricted"

    if latam_friendly(text):
        return False, None

    if is_us_only(None, text) or is_eu_only(None, text):
        return True, "geo_restricted"
    return False, None


def latam_friendly(text: str) -> bool:
    lower = text.lower()
    return any(
        k in lower
        for k in (
            "latam",
            "latin america",
            "south america",
            "argentina",
            "brazil",
            "worldwide",
            "anywhere",
            "global",
        )
    )


def extract_salary(text: str) -> str | None:
    patterns = [
        r"\$\s?\d[\d,]*(?:\s?[-–]\s?\$?\s?\d[\d,]*)?\s?[kK]?",
        r"\bUSD\s?\d[\d,]*(?:\s?[-–]\s?\d[\d,]*)?\s?[kK]?",
        r"\$\s?\d[\d,]+(?:\.\d+)?\s?/month",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    return None


def extract_role(title: str, text: str, role_keyword: str) -> str:
    for source in (title, text[:500]):
        m = re.search(
            r"((?:Senior|Staff|Lead|Principal|Full Stack|Remote)?\s*(?:AI|Agentic|Agent|LLM|ML)\s*(?:Engineer|Developer|Architect)[^|\n]{0,40})",
            source,
            re.IGNORECASE,
        )
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip(" -|")
    return role_keyword.title()


def extract_company(title: str, text: str) -> str:
    if "|" in title:
        parts = [p.strip() for p in title.split("|") if p.strip()]
        if len(parts) >= 2:
            return parts[-1][:60]
    for pat in [
        r"at\s+([A-Z][A-Za-z0-9&\.\-\s]{2,40})\s*\|",
        r"([A-Z][A-Za-z0-9&\.\-\s]{2,40})\s+is\s+(?:seeking|hiring)",
        r"@\s+([A-Z][A-Za-z0-9&\.\-\s]{2,40})\b",
        r"^\s*([A-Z][A-Za-z0-9&\.\-\s]{2,40})\s+-\s+(?:Senior|Staff|Lead|AI|Agent)",
    ]:
        m = re.search(pat, title + " " + text[:800])
        if m:
            return m.group(1).strip()
    return "Unknown"


def profile_match_score(text: str, title: str, role_keyword: str, cfg: dict[str, Any]) -> float:
    lower = (title + " " + text).lower()
    score = 0.0
    if matches_title(lower, [role_keyword]):
        score += 3.0
    for kw in cfg.get("profile_match_keywords", []):
        if kw.lower() in lower:
            score += 0.5
    if "rag" in lower:
        score += 1.0
    if "llm" in lower or "langchain" in lower or "langgraph" in lower:
        score += 1.0
    if "agentic" in lower or "agent" in lower:
        score += 0.8
    if "remote" in lower:
        score += 1.0
    if latam_friendly(lower):
        score += 2.0
    if has_usd_salary(lower):
        score += 1.5
    if geo_blocked(lower)[0]:
        score -= 10.0
    return score


def result_to_job(
    result: dict[str, str],
    role_keyword: str,
    cfg: dict[str, Any],
    job_search_config: dict[str, Any],
) -> dict[str, Any] | None:
    url = result.get("url", "").strip()
    title = result.get("title", "").strip()
    snippet = result.get("snippet", "").strip()
    if not url:
        return None

    try:
        page_text = fetch_page(url)
    except (urllib.error.URLError, TimeoutError, ValueError):
        page_text = ""
    if page_is_js_shell(page_text):
        page_text = snippet
    if not title:
        title = url

    combined = f"{title}\n{snippet}\n{page_text}"
    if not looks_like_job_page(combined, title, url, snippet=snippet):
        return None

    blocked, reason = geo_blocked(combined)
    if blocked:
        return None

    score = profile_match_score(combined, title, role_keyword, cfg)
    if score < 2.0:
        return None

    salary = extract_salary(combined)
    location = "LATAM" if latam_friendly(combined) else "Remote"
    if re.search(r"\bworldwide\b|\banywhere\b|\bglobal\b", combined, re.I):
        location = "Worldwide"

    job: dict[str, Any] = {
        "source": "google",
        "url": url,
        "role": extract_role(title, combined, role_keyword),
        "company": extract_company(title, combined),
        "salary_usd": salary,
        "currency": "USD" if salary else None,
        "location_note": location,
        "posted_at": result.get("posted_at"),
        "apply_channel": "external_url",
        "description_snippet": (snippet or page_text)[:500],
        "search_role": role_keyword,
        "google_query": result.get("query"),
        "match_score": round(score, 2),
    }

    if cfg.get("require_usd_salary", False):
        evaluate_job(job, job_search_config)
    else:
        if salary:
            job["filter_result"] = "eligible"
            job["skip_reason"] = None
        else:
            job["filter_result"] = cfg.get("posts_default_filter_result", "needs_review")
            job["skip_reason"] = "no_usd_salary"

    return job


def collect_search_results(
    cfg: dict[str, Any],
    after_date: str,
    input_json: Path | None,
) -> list[dict[str, str]]:
    if input_json:
        payload = json.loads(input_json.read_text(encoding="utf-8"))
        out: list[dict[str, str]] = []
        for block in payload.get("queries", []):
            query = block.get("query", "")
            for item in block.get("results", []):
                item = dict(item)
                item["query"] = query
                item.setdefault("role_keyword", block.get("role_keyword", ""))
                out.append(item)
        return out

    per_role = int(cfg.get("max_results_per_role", 10))
    all_results: list[dict[str, str]] = []
    for role in cfg.get("roles", []):
        query = build_query(role, after_date, cfg)
        hits = search_google_cse(query, cfg, max_results=per_role)
        for hit in hits:
            hit["query"] = query
            hit["role_keyword"] = role
            all_results.append(hit)
    return all_results


def run_discovery(
    after_date: str | None = None,
    input_json: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    cfg = load_config()
    job_search_config = load_json(ROOT / "config.json", {})
    after = after_date or default_after_date(cfg)
    max_total = int(cfg.get("max_results_total", 20))

    raw_results = collect_search_results(cfg, after, input_json)
    if not raw_results and not input_json:
        return {
            "error": "No search results. Set GOOGLE_CSE_API_KEY + GOOGLE_CSE_CX or pass --input-json from WebSearch.",
            "after_date": after,
        }

    jobs: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for result in raw_results:
        url = result.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        role_kw = result.get("role_keyword") or cfg.get("roles", ["ai engineer"])[0]
        job = result_to_job(result, role_kw, cfg, job_search_config)
        if job:
            jobs.append(job)

    jobs.sort(key=lambda j: (-float(j.get("match_score", 0)), j.get("role", "")))
    jobs = jobs[:max_total]

    since = datetime.now(LOCAL_TZ) - timedelta(days=int(cfg.get("default_after_days", 7)))
    registry = load_registry()
    registry, new_jobs = merge_jobs(registry, jobs, since)

    now = datetime.now(LOCAL_TZ)
    run_path = RUNS_DIR / f"google-jobs-{now.strftime('%Y-%m-%dT%H-%M')}.md"

    if not dry_run:
        save_registry(registry)
        source_stats = {
            "google": {
                "fetched": len(raw_results),
                "new": len(new_jobs),
                "eligible": len([j for j in new_jobs if j.get("filter_result") == "eligible"]),
                "error": None,
            }
        }
        write_google_run_markdown(run_path, after, jobs, source_stats)
        save_json(STATE_PATH, {"last_run_at": now.isoformat(), "after_date": after})

    return {
        "after_date": after,
        "run_path": str(run_path),
        "candidates_analyzed": len(raw_results),
        "matched": len(jobs),
        "new_total": len(new_jobs),
        "eligible": len([j for j in new_jobs if j.get("filter_result") == "eligible"]),
        "needs_review": len([j for j in new_jobs if j.get("filter_result") == "needs_review"]),
        "jobs": [
            {
                "role": j["role"],
                "company": j["company"],
                "salary_usd": j.get("salary_usd"),
                "location_note": j.get("location_note"),
                "match_score": j.get("match_score"),
                "filter_result": j.get("filter_result"),
                "url": j["url"],
            }
            for j in new_jobs
        ],
    }


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_google_run_markdown(
    run_path: Path,
    after_date: str,
    jobs: list[dict[str, Any]],
    source_stats: dict[str, Any],
) -> None:
    """Write run file with jobs sorted by match_score."""
    sorted_jobs = sorted(jobs, key=lambda j: (-float(j.get("match_score", 0)), j.get("role", "")))
    now = datetime.now(LOCAL_TZ)
    eligible = [j for j in sorted_jobs if j.get("filter_result") == "eligible"]
    review = [j for j in sorted_jobs if j.get("filter_result") == "needs_review"]

    lines = [
        f"# Google job discovery — {now.strftime('%Y-%m-%d %H:%M %Z')}",
        "",
        f"**After date:** {after_date}",
        "",
        "## Summary",
        "",
        f"- Matched roles: **{len(sorted_jobs)}** (max 20)",
        f"- Eligible: **{len(eligible)}**",
        f"- Needs review: **{len(review)}**",
        "",
        "## Source stats",
        "",
        "| Source | Fetched | New | Eligible |",
        "|--------|---------|-----|----------|",
        f"| google | {source_stats['google']['fetched']} | {source_stats['google']['new']} | {source_stats['google']['eligible']} |",
        "",
        "## Roles (sorted by match score)",
        "",
        "| Rank | ☐ | Score | Role | Company | Salary | Location | URL |",
        "|------|---|-------|------|---------|--------|----------|-----|",
    ]

    for i, job in enumerate(sorted_jobs, 1):
        lines.append(
            f"| {i} | ☐ | {job.get('match_score', '—')} | {job.get('role', '—')} | "
            f"{job.get('company', '—')} | {job.get('salary_usd') or '—'} | "
            f"{job.get('location_note', '—')} | {job.get('url', '—')} |"
        )

    if review:
        lines.extend(["", "## Needs review (included above, flagged)"])
        for job in review:
            lines.append(f"- {job.get('role')} @ {job.get('company')} — {job.get('skip_reason')}")

    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover jobs via Google-style queries.")
    parser.add_argument("--after", help="after:YYYY-MM-DD date for query (default: 7 days ago)")
    parser.add_argument("--input-json", help="JSON with WebSearch/CSE results (queries[].results[])")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = run_discovery(
        after_date=args.after,
        input_json=Path(args.input_json) if args.input_json else None,
        dry_run=args.dry_run,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result.get("error"):
            print(result["error"])
            return 1
        print(f"Google jobs — after {result.get('after_date')}")
        print(f"Matched: {result.get('matched')} | New: {result.get('new_total')} | Eligible: {result.get('eligible')}")
        print(f"Run file: {result.get('run_path')}")
        for i, job in enumerate(result.get("jobs", []), 1):
            print(f"  {i}. [{job.get('match_score')}] {job.get('role')} @ {job.get('company')} — {job.get('url')}")

    return 0 if not result.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
