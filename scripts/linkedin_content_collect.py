#!/usr/bin/env python3
"""Deep LinkedIn content-search collector via browser scroll (Patchright).

Unlike a single-page snapshot (~3 posts), this script
scrolls with mouse.wheel and accumulates Feed post chunks until:
  - target role count reached (default 100), or
  - no new posts after several stale scrolls.

Requires logged-in browser session at ~/.linkedin-mcp/cookies.json.
Run: uvx --with patchright python3 scripts/linkedin_content_collect.py --query '"ai engineer" + "latam"'
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from linkedin_posts_merge import (  # noqa: E402
    build_queries,
    extract_activity_refs_from_html,
    extract_profile_refs_from_html,
    linkedin_content_search_url,
    load_linkedin_config,
    merge_payload,
    parse_feed_search_posts,
    period_to_recency,
    post_to_job,
)
from registry import load_json, job_key  # noqa: E402

from browser_session import PROFILE_DIR, browser_launch_kwargs, load_cookies  # noqa: E402
RUNS = ROOT / "runs"
TZ = ZoneInfo("America/Sao_Paulo")

WHEEL_DELTA = 2000
SCROLL_PAUSE = 1.2
MAX_STALE = 6
MAX_SCROLLS = 120


def _chunk_key(chunk: str, author: str) -> str:
    body = re.sub(r"\s+", " ", chunk[:240].strip().casefold())
    return f"{author.casefold()}|{body}"


def _extract_author(chunk: str) -> str:
    lines = [line.strip() for line in chunk.split("\n") if line.strip()]
    for line in lines[:12]:
        if line in {"Follow", "Connect", "Show translation", "Visit my website", "View my services"}:
            continue
        if re.search(r"\b(1st|2nd|3rd\+?)\b", line):
            continue
        if re.match(r"^\d+[hmdw]\b", line) or "Edited •" in line:
            continue
        if len(line) > 2 and not line.startswith("#"):
            return re.sub(r"\s+•.*", "", line).strip()
    return "Unknown"


def parse_feed_text(raw: str, refs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Parse accumulated innerText into post dicts."""
    fake = {"sections": {"search_results": raw}, "references": {"search_results": refs or []}}
    return parse_feed_search_posts(fake)


async def collect_feed_text(
    url: str,
    *,
    max_scrolls: int = MAX_SCROLLS,
    wheel_delta: int = WHEEL_DELTA,
    pause: float = SCROLL_PAUSE,
    max_stale: int = MAX_STALE,
    use_profile: bool = False,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    import os

    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS_PATH)
    from patchright.async_api import async_playwright

    seen_keys: set[str] = set()
    chunks: list[str] = []
    activity_urls: list[str] = []
    profile_refs: list[dict[str, Any]] = []
    activity_refs: list[dict[str, Any]] = []
    profile_seen: set[str] = set()
    activity_seen: set[str] = set()
    stats: dict[str, Any] = {"scrolls": 0, "stale": 0, "errors": [], "auth_mode": "cookies"}

    cookies = load_cookies()

    async with async_playwright() as p:
        launch_kwargs = browser_launch_kwargs(headless=True)

        context = None
        if use_profile:
            try:
                context = await p.chromium.launch_persistent_context(
                    str(PROFILE_DIR),
                    viewport={"width": 1280, "height": 900},
                    locale="en-US",
                    **launch_kwargs,
                )
                stats["auth_mode"] = "profile"
            except Exception as exc:
                stats["errors"].append(f"profile_launch: {exc}")

        if context is None:
            browser = await p.chromium.launch(**launch_kwargs)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="en-US",
            )
            if cookies:
                await context.add_cookies(cookies)
            stats["auth_mode"] = "cookies"

        page = context.pages[0] if context.pages else await context.new_page()

        def on_response(resp: Any) -> None:
            try:
                if "linkedin.com" not in resp.url:
                    return
                # fire-and-forget body read in background not needed sync
            except Exception:
                pass

        page.on("response", on_response)

        await page.goto(url, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_selector("main", timeout=30000)
        await asyncio.sleep(2.0)

        initial = await page.locator("main").inner_text(timeout=15000)
        if "No results found" in initial and initial.count("Feed post") == 0:
            stats["errors"].append("no_results_page")
            await context.close()
            return "", [], stats

        viewport = page.viewport_size or {"width": 1280, "height": 900}
        cx, cy = viewport["width"] // 2, viewport["height"] // 2
        await page.mouse.move(cx, cy)

        stale = 0
        for i in range(max_scrolls):
            stats["scrolls"] = i + 1
            try:
                raw = await page.locator("main").inner_text(timeout=15000)
            except Exception as exc:
                stats["errors"].append(str(exc))
                break

            before = len(chunks)
            for part in re.split(r"(?:^|\n)Feed post\n", raw):
                part = part.strip()
                if not part or part.startswith("Are these results helpful?"):
                    continue
                author = _extract_author(part)
                key = _chunk_key(part, author)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                chunks.append(part)

            # capture activity URNs and profile links from HTML for URL fallback
            html = await page.content()
            for urn_kind, urn in re.findall(r"urn(?:%3A|:)li(?:%3A|:)(activity|share|ugcPost)(?:%3A|:)(\d+)", html, re.I):
                u = f"https://www.linkedin.com/feed/update/urn:li:{urn_kind.lower()}:{urn}/"
                if u not in activity_urls:
                    activity_urls.append(u)
            for ref in extract_profile_refs_from_html(html):
                key = ref["url"]
                if key in profile_seen:
                    continue
                profile_seen.add(key)
                profile_refs.append(ref)
            for ref in extract_activity_refs_from_html(html):
                key = ref.get("activity_id") or ref.get("url")
                if key in activity_seen:
                    continue
                activity_seen.add(str(key))
                activity_refs.append(ref)

            if len(chunks) > before:
                stale = 0
            else:
                stale += 1
                stats["stale"] = stale
                if stale >= max_stale:
                    break

            await page.mouse.wheel(0, wheel_delta)
            await asyncio.sleep(pause)

        final_raw = "Feed post\n\n" + "\nFeed post\n\n".join(chunks)
        refs: list[dict[str, Any]] = activity_refs + profile_refs + [
            {"kind": "feed_post", "url": u, "text": ""} for u in activity_urls[: len(chunks)]
        ]
        await context.close()

    stats["raw_posts"] = len(chunks)
    stats["activity_urls"] = len(activity_urls)
    stats["profile_refs"] = len(profile_refs)
    stats["activity_refs"] = len(activity_refs)
    return final_raw, refs, stats


def posts_to_jobs(
    posts: list[dict[str, Any]],
    query_meta: dict[str, str],
    *,
    max_roles: int,
) -> list[dict[str, Any]]:
    cfg = load_linkedin_config()
    job_cfg = load_json(ROOT / "config.json", {})
    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for post in posts:
        job = post_to_job(post, query_meta, cfg, job_cfg)
        if not job:
            continue
        key = job_key(job)
        if key in seen:
            continue
        seen.add(key)
        jobs.append(job)
        if len(jobs) >= max_roles:
            break
    return jobs


async def run_query(
    query: str,
    role_keyword: str,
    region: str,
    *,
    period_days: int,
    max_roles: int,
    max_scrolls: int,
    merge: bool,
    since: str,
) -> dict[str, Any]:
    cfg = load_linkedin_config()
    recency = period_to_recency(period_days, cfg)
    url = linkedin_content_search_url(query, recency=recency)
    meta = {"query": query, "role_keyword": role_keyword, "region": region}
    # URL includes sortBy=date_posted — scroll accumulates top (newest) first

    t0 = time.monotonic()
    raw, refs, scroll_stats = await collect_feed_text(url, max_scrolls=max_scrolls)
    posts = parse_feed_text(raw, refs)
    jobs = posts_to_jobs(posts, meta, max_roles=max_roles)
    elapsed = time.monotonic() - t0

    stamp = datetime.now(TZ).strftime("%Y-%m-%dT%H-%M-%S")
    out_dir = RUNS / f"browser-collect-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:60]
    raw_path = out_dir / f"{slug}.json"
    payload = {
        "source": "browser_scroll",
        "query": query,
        "role_keyword": role_keyword,
        "region": region,
        "url": url,
        "period_days": period_days,
        "scroll_stats": scroll_stats,
        "posts_found": len(posts),
        "roles_kept": len(jobs),
        "elapsed_sec": round(elapsed, 1),
        "sections": {"search_results": raw},
        "references": {"search_results": refs},
        "jobs": jobs,
    }
    raw_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    merge_result = None
    if merge and jobs:
        merge_payload_in = {
            "period_days": period_days,
            "queries": [
                {
                    "query": query,
                    "role_keyword": role_keyword,
                    "region": region,
                    "feed_payload": {
                        "url": url,
                        "sections": {"search_results": raw},
                        "references": {"search_results": refs},
                    },
                }
            ],
        }
        merge_result = merge_payload(merge_payload_in, period_days, since)

    return {
        "query": query,
        "url": url,
        "posts_found": len(posts),
        "roles_kept": len(jobs),
        "elapsed_sec": round(elapsed, 1),
        "scroll_stats": scroll_stats,
        "raw_path": str(raw_path),
        "merge": merge_result,
        "top_roles": [{"role": j.get("role"), "company": j.get("company"), "salary": j.get("salary_usd")} for j in jobs[:10]],
    }


async def run_all(
    *,
    period_days: int,
    max_roles: int,
    max_roles_total: int,
    max_scrolls: int,
    merge: bool,
    since: str,
) -> dict[str, Any]:
    cfg = load_linkedin_config()
    queries = build_queries(cfg)
    results = []
    total_roles = 0
    for q in queries:
        if total_roles >= max_roles_total:
            break
        remaining = max_roles_total - total_roles
        per_query_cap = min(max_roles, remaining)
        r = await run_query(
            q["query"],
            q["role_keyword"],
            q["region"],
            period_days=period_days,
            max_roles=per_query_cap,
            max_scrolls=max_scrolls,
            merge=False,
            since=since,
        )
        results.append(r)
        total_roles += r["roles_kept"]

    # single merge with all queries
    merge_result = None
    if merge:
        payload_queries = []
        for r in results:
            data = json.loads(Path(r["raw_path"]).read_text())
            payload_queries.append(
                {
                    "query": data["query"],
                    "role_keyword": data["role_keyword"],
                    "region": data["region"],
                    "feed_payload": {
                        "url": data["url"],
                        "sections": data["sections"],
                        "references": data.get("references", {}),
                    },
                }
            )
        if payload_queries:
            merge_result = merge_payload(
                {"period_days": period_days, "queries": payload_queries},
                period_days,
                since,
            )

    return {"queries": results, "total_roles": total_roles, "merge": merge_result}


def main() -> int:
    parser = argparse.ArgumentParser(description="Deep LinkedIn content search via browser scroll")
    parser.add_argument("--query", help='Single query e.g. \'"ai engineer" + "latam"\'')
    parser.add_argument("--role-keyword", default="ai engineer")
    parser.add_argument("--region", default="latam")
    parser.add_argument("--all-queries", action="store_true", help="Run all 6 config queries")
    parser.add_argument("--period", type=int, default=7)
    parser.add_argument("--max-roles", type=int, default=100, help="Max roles per query")
    parser.add_argument("--max-roles-total", type=int, default=100, help="Stop all-queries after this many roles")
    parser.add_argument("--max-scrolls", type=int, default=MAX_SCROLLS)
    parser.add_argument("--merge", action="store_true", help="Merge into registry + run markdown")
    parser.add_argument("--since", default="7d")
    args = parser.parse_args()

    if not PROFILE_DIR.exists():
        print(f"Missing LinkedIn profile: {PROFILE_DIR}", file=sys.stderr)
        return 1

    if args.all_queries:
        result = asyncio.run(
            run_all(
                period_days=args.period,
                max_roles=args.max_roles,
                max_roles_total=args.max_roles_total,
                max_scrolls=args.max_scrolls,
                merge=args.merge,
                since=args.since,
            )
        )
    elif args.query:
        result = asyncio.run(
            run_query(
                args.query,
                args.role_keyword,
                args.region,
                period_days=args.period,
                max_roles=args.max_roles,
                max_scrolls=args.max_scrolls,
                merge=args.merge,
                since=args.since,
            )
        )
    else:
        parser.error("Provide --query or --all-queries")

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
