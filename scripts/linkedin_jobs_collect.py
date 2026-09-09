#!/usr/bin/env python3
"""LinkedIn Jobs search collector via Patchright (pagination, not scroll).

Collects job listings from linkedin.com/jobs/search using URL start offsets
and next-page controls. Scrolls the results panel on each page before extract.
Requires logged-in session at ~/.linkedin-mcp/cookies.json or profile dir.
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

from linkedin_jobs_merge import (  # noqa: E402
    JOBS_PER_PAGE,
    audit_collect_results,
    build_all_track_queries,
    extract_posted_label,
    linkedin_jobs_search_url,
    merge_listings_by_id,
    merge_payload,
    normalize_listing_title,
    parse_listings_from_html,
    with_search_start,
)
from track_store import load_linkedin_jobs_config  # noqa: E402

from browser_session import PROFILE_DIR, browser_launch_kwargs, load_cookies  # noqa: E402
RUNS = ROOT / "runs"
TZ = ZoneInfo("America/Sao_Paulo")
PAGE_PAUSE = 1.5
SCROLL_STEPS = 12
CARD_PAUSE = 0.12


async def _launch_context(p: Any, *, use_profile: bool) -> tuple[Any, dict[str, Any]]:
    stats: dict[str, Any] = {"errors": [], "auth_mode": "cookies"}
    launch_kwargs = browser_launch_kwargs(headless=True)
    cookies = load_cookies()

    context = None
    if use_profile and PROFILE_DIR.exists():
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

    return context, stats


async def scroll_jobs_results(page: Any) -> None:
    """Scroll the left jobs list to load lazy cards before extraction."""
    selectors = (
        ".jobs-search-results-list",
        "ul.jobs-search__results-list",
        '[class*="jobs-search-results"]',
        "main",
    )
    for selector in selectors:
        panel = page.locator(selector).first
        if await panel.count() == 0:
            continue
        try:
            for _ in range(SCROLL_STEPS):
                await panel.evaluate(
                    "(el) => { el.scrollTop = el.scrollHeight; window.scrollBy(0, 400); }"
                )
                await asyncio.sleep(0.35)
            await panel.evaluate("(el) => { el.scrollTop = 0; }")
            await asyncio.sleep(0.25)
            return
        except Exception:
            continue


async def extract_listings_from_dom(page: Any) -> list[dict[str, Any]]:
    """Read job cards from live DOM (titles/companies survive minified HTML)."""
    listings: list[dict[str, Any]] = []
    cards = page.locator('[data-job-id], li.jobs-search-results__list-item [data-job-id]')
    count = await cards.count()
    for idx in range(count):
        card = cards.nth(idx)
        try:
            await card.scroll_into_view_if_needed(timeout=4000)
            await asyncio.sleep(CARD_PAUSE)
        except Exception:
            pass
        job_id = (await card.get_attribute("data-job-id") or "").strip()
        if not job_id:
            continue

        title = ""
        title_el = card.locator('a.job-card-list__title, a[href*="/jobs/view/"]').first
        if await title_el.count():
            try:
                title = (await title_el.inner_text(timeout=3000)).strip()
            except Exception:
                title = ""
            if not title:
                title = (await title_el.get_attribute("title") or "").strip()
            title = normalize_listing_title(title)

        company = "—"
        company_el = card.locator(
            ".base-search-card__subtitle, .job-card-container__company-name, .artdeco-entity-lockup__subtitle"
        ).first
        if await company_el.count():
            try:
                company = (await company_el.inner_text(timeout=3000)).strip() or "—"
            except Exception:
                pass

        location = ""
        loc_el = card.locator(".job-search-card__location, .job-card-container__metadata-item").first
        if await loc_el.count():
            try:
                location = (await loc_el.inner_text(timeout=3000)).strip()
            except Exception:
                pass

        card_text = ""
        try:
            card_text = await card.inner_text(timeout=3000)
        except Exception:
            pass
        easy_apply = bool(re.search(r"Easy Apply", card_text, re.I))
        apply_method = "easy_apply" if easy_apply else "unknown"
        if re.search(r"Apply on company website|Apply on external site", card_text, re.I):
            apply_method = "external"

        posted_label = extract_posted_label(card_text, location)

        listings.append(
            {
                "job_id": job_id,
                "url": f"https://www.linkedin.com/jobs/view/{job_id}/",
                "title": title,
                "company": company,
                "location": location,
                "posted_label": posted_label,
                "card_text": card_text,
                "easy_apply": easy_apply,
                "apply_method": apply_method,
                "discovery_index": idx,
            }
        )
    return listings


async def listing_from_job_view(page: Any, job_id: str, *, url: str | None = None) -> dict[str, Any] | None:
    """Fetch a single job listing from its view page (backfill)."""
    target = url or f"https://www.linkedin.com/jobs/view/{job_id}/"
    await page.goto(target, wait_until="domcontentloaded", timeout=90000)
    await asyncio.sleep(2.0)
    text = await page.locator("main").inner_text(timeout=20000)
    title = ""
    for sel in ("h1", ".job-details-jobs-unified-top-card__job-title"):
        el = page.locator(sel).first
        if await el.count():
            try:
                title = (await el.inner_text(timeout=3000)).strip()
            except Exception:
                title = ""
            if title:
                break
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    company = lines[0] if lines else "—"
    if not title and len(lines) > 1:
        title = lines[1]
    if title.lower() in {"remote", "full-time", "part-time", "contract"} and len(lines) > 2:
        title = lines[2]
    title = normalize_listing_title(title)
    location = ""
    for line in lines[2:10]:
        if "ago" in line.lower() or "·" in line or "remote" in line.lower():
            location = line
            break
    posted_label = extract_posted_label(text, location)
    easy_apply = bool(re.search(r"Easy Apply", text, re.I))
    apply_method = "easy_apply" if easy_apply else "unknown"
    if not title:
        return None
    return {
        "job_id": job_id,
        "url": f"https://www.linkedin.com/jobs/view/{job_id}/",
        "title": title,
        "company": company if company != title else "—",
        "location": location,
        "posted_label": posted_label,
        "card_text": text[:2000],
        "easy_apply": easy_apply,
        "apply_method": apply_method,
        "discovery_index": 0,
        "backfill": True,
    }


async def backfill_job_ids(job_ids: list[str], *, use_profile: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from patchright.async_api import async_playwright

    stats: dict[str, Any] = {"backfill_ids": job_ids, "errors": []}
    listings: list[dict[str, Any]] = []
    if not job_ids:
        return listings, stats

    async with async_playwright() as p:
        context, launch_stats = await _launch_context(p, use_profile=use_profile)
        stats.update({k: v for k, v in launch_stats.items() if k != "errors"})
        stats["errors"].extend(launch_stats.get("errors", []))
        page = context.pages[0] if context.pages else await context.new_page()
        for jid in job_ids:
            try:
                item = await listing_from_job_view(page, jid)
                if item:
                    listings.append(item)
            except Exception as exc:
                stats["errors"].append(f"backfill_{jid}: {exc}")
        await context.close()
    stats["backfill_found"] = len(listings)
    return listings, stats


async def collect_jobs_pages(
    url: str,
    *,
    max_pages: int,
    use_profile: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from patchright.async_api import async_playwright

    stats: dict[str, Any] = {
        "pages": 0,
        "page_details": [],
        "errors": [],
        "auth_mode": "cookies",
        "pagination_mode": "start_offset",
    }
    listings: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    async with async_playwright() as p:
        context, launch_stats = await _launch_context(p, use_profile=use_profile)
        stats.update({k: v for k, v in launch_stats.items() if k != "errors"})
        stats["errors"].extend(launch_stats.get("errors", []))

        page = context.pages[0] if context.pages else await context.new_page()

        for page_num in range(max_pages):
            page_url = with_search_start(url, page_num * JOBS_PER_PAGE)
            try:
                await page.goto(page_url, wait_until="domcontentloaded", timeout=90000)
                await page.wait_for_selector("main", timeout=30000)
            except Exception as exc:
                stats["errors"].append(f"page_{page_num + 1}_load: {exc}")
                if page_num == 0:
                    await context.close()
                    return listings, stats
                break

            await asyncio.sleep(1.5 if page_num == 0 else PAGE_PAUSE)
            await scroll_jobs_results(page)

            page_detail: dict[str, Any] = {"page": page_num + 1, "url": page_url}
            try:
                html = await page.content()
                inner_text = await page.locator("main").inner_text(timeout=15000)
                dom_listings = await extract_listings_from_dom(page)
                html_listings = parse_listings_from_html(html, inner_text)
                page_listings = merge_listings_by_id(dom_listings, html_listings)
            except Exception as exc:
                stats["errors"].append(f"page_{page_num + 1}_extract: {exc}")
                break

            added = 0
            for item in page_listings:
                jid = item.get("job_id") or ""
                if jid and jid in seen_ids:
                    continue
                if jid:
                    seen_ids.add(jid)
                item["discovery_index"] = len(listings)
                listings.append(item)
                added += 1

            page_detail.update(
                {
                    "dom_count": len(dom_listings),
                    "html_count": len(html_listings),
                    "merged_count": len(page_listings),
                    "added": added,
                }
            )
            stats["page_details"].append(page_detail)
            stats["pages"] = page_num + 1
            stats["listings_on_page"] = len(page_listings)
            stats["listings_total"] = len(listings)

            if not page_listings and page_num == 0:
                stats["errors"].append("no_results_page")
                break
            if added == 0:
                break

            next_btn = page.locator('button[aria-label="View next page"]')
            if await next_btn.count() == 0:
                next_btn = page.locator('button:has-text("Next")')
            has_next = await next_btn.count() > 0 and await next_btn.first.is_enabled()
            if has_next:
                stats["pagination_mode"] = "start_offset+next_button"
            if not has_next:
                break
            if page_num + 1 >= max_pages:
                break

        await context.close()

    return listings, stats


def listings_to_jobs_preview(
    listings: list[dict[str, Any]],
    query_meta: dict[str, str],
    *,
    max_roles: int,
    track_id: str | None = None,
) -> list[dict[str, Any]]:
    from linkedin_jobs_merge import listing_to_job  # noqa: WPS433
    from registry import job_key, load_json  # noqa: WPS433

    cfg = load_linkedin_jobs_config(track_id or query_meta.get("track"))
    job_cfg = load_json(ROOT / "config.json", {})
    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for listing in listings:
        job = listing_to_job(listing, query_meta, cfg, job_cfg)
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
    query_meta: dict[str, str],
    *,
    period_days: int,
    max_pages: int,
    max_roles: int,
    merge: bool,
    since: str,
    cfg: dict[str, Any] | None = None,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    track = query_meta.get("track")
    cfg = cfg or load_linkedin_jobs_config(track)
    query = query_meta["query"]
    role_keyword = query_meta["role_keyword"]
    region = query_meta["region"]
    url = query_meta.get("linkedin_url") or linkedin_jobs_search_url(
        query,
        region=region,
        period_days=period_days,
        cfg=cfg,
        location=query_meta.get("search_location"),
        geo_id=query_meta.get("search_geo_id"),
    )
    meta = {
        "query": query,
        "role_keyword": role_keyword,
        "region": region,
        "track": track,
        "region_label": query_meta.get("region_label"),
        "role_label": query_meta.get("role_label"),
        "location_label": query_meta.get("location_label"),
    }
    t0 = time.monotonic()
    listings, page_stats = await collect_jobs_pages(url, max_pages=max_pages)
    jobs = listings_to_jobs_preview(listings, meta, max_roles=max_roles, track_id=track)
    elapsed = time.monotonic() - t0

    if out_dir is None:
        stamp = datetime.now(TZ).strftime("%Y-%m-%dT%H-%M-%S")
        out_dir = RUNS / f"linkedin-jobs-collect-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    slug_parts = [
        track or "track",
        region,
        re.sub(r"[^a-z0-9]+", "-", (query_meta.get("location_label") or role_keyword).lower()),
    ]
    slug = "-".join(p for p in slug_parts if p).strip("-")[:72]
    raw_path = out_dir / f"{slug}.json"
    payload = {
        "source": "linkedin_jobs_pagination",
        "query": query,
        "role_keyword": role_keyword,
        "region": region,
        "track": track,
        "location_label": query_meta.get("location_label"),
        "url": url,
        "period_days": period_days,
        "page_stats": page_stats,
        "listings_found": len(listings),
        "roles_kept": len(jobs),
        "elapsed_sec": round(elapsed, 1),
        "listings": listings,
        "jobs": jobs,
    }
    raw_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    merge_result = None
    if merge and listings:
        merge_result = merge_payload(
            {
                "period_days": period_days,
                "queries": [
                    {
                        "query": query,
                        "role_keyword": role_keyword,
                        "region": region,
                        "track": track,
                        "listings": listings,
                    }
                ],
            },
            period_days,
            since,
            track_id=track,
        )

    return {
        "query": query,
        "role_keyword": role_keyword,
        "region": region,
        "track": track,
        "url": url,
        "listings_found": len(listings),
        "roles_kept": len(jobs),
        "elapsed_sec": round(elapsed, 1),
        "page_stats": page_stats,
        "raw_path": str(raw_path),
        "merge": merge_result,
        "top_roles": [
            {"role": j.get("role"), "company": j.get("company"), "easy_apply": j.get("linkedin_easy_apply")}
            for j in jobs[:10]
        ],
    }


async def run_all(
    *,
    period_days: int,
    max_pages: int,
    max_roles: int,
    max_roles_total: int,
    merge: bool,
    since: str,
    backfill_ids: list[str] | None = None,
    use_profile: bool = False,
) -> dict[str, Any]:
    queries = build_all_track_queries()
    if not queries:
        return {"skipped": True, "reason": "no enabled tracks/queries"}

    stamp = datetime.now(TZ).strftime("%Y-%m-%dT%H-%M-%S")
    out_dir = RUNS / f"linkedin-jobs-collect-{stamp}"

    results = []
    total_roles = 0
    for q in queries:
        if total_roles >= max_roles_total:
            break
        track = q.get("track")
        cfg = load_linkedin_jobs_config(track)
        if not cfg.get("jobs_collect_enabled", True):
            continue
        remaining = max_roles_total - total_roles
        per_query_cap = min(max_roles, remaining)
        track_max_pages = max_pages or int(cfg.get("default_max_pages", 12))
        track_period = period_days or int(cfg.get("default_period_days", 1))
        r = await run_query(
            q,
            period_days=track_period,
            max_pages=track_max_pages,
            max_roles=per_query_cap,
            merge=False,
            since=since,
            cfg=cfg,
            out_dir=out_dir,
        )
        results.append(r)
        total_roles += r["roles_kept"]

    backfill_stats = None
    backfill_listings: list[dict[str, Any]] = []
    ids = [str(x).strip() for x in (backfill_ids or []) if str(x).strip()]
    if ids:
        backfill_listings, backfill_stats = await backfill_job_ids(ids, use_profile=use_profile)
        if backfill_listings:
            bf_path = out_dir / "backfill.json"
            bf_path.write_text(
                json.dumps({"listings": backfill_listings, "stats": backfill_stats}, indent=2) + "\n",
                encoding="utf-8",
            )

    merge_result = None
    if merge:
        payload_queries = []
        for r in results:
            data = json.loads(Path(r["raw_path"]).read_text(encoding="utf-8"))
            payload_queries.append(
                {
                    "query": data["query"],
                    "role_keyword": data["role_keyword"],
                    "region": data["region"],
                    "track": data.get("track"),
                    "listings": data.get("listings") or [],
                }
            )
        if backfill_listings:
            payload_queries.append(
                {
                    "query": "backfill",
                    "role_keyword": "ai engineer",
                    "region": "worldwide",
                    "track": "ai-engineer",
                    "listings": backfill_listings,
                }
            )
        if payload_queries:
            merge_result = merge_payload(
                {"period_days": period_days or 1, "queries": payload_queries},
                period_days or 1,
                since,
            )

    audit = audit_collect_results(results)
    return {
        "queries": results,
        "total_roles": total_roles,
        "query_count": len(queries),
        "queries_run": len(results),
        "out_dir": str(out_dir),
        "backfill": backfill_stats,
        "merge": merge_result,
        "audit": audit,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="LinkedIn Jobs search via browser pagination")
    parser.add_argument("--query", help="Single role keyword e.g. ai engineer")
    parser.add_argument("--role-keyword", default="ai engineer")
    parser.add_argument("--region", default="latam")
    parser.add_argument("--track", default=None, help="Track id for single query")
    parser.add_argument("--all-queries", action="store_true", help="All roles × regions for all tracks")
    parser.add_argument("--period", type=int, default=None, help="Days (1 = past 24 hours)")
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--max-roles", type=int, default=50, help="Max roles per query")
    parser.add_argument("--max-roles-total", type=int, default=300)
    parser.add_argument("--merge", action="store_true")
    parser.add_argument("--since", default="1d")
    parser.add_argument("--use-profile", action="store_true")
    parser.add_argument(
        "--backfill-ids",
        default="",
        help="Comma-separated /jobs/view/{id} to fetch directly after search",
    )
    args = parser.parse_args()

    cookies = Path.home() / ".linkedin-mcp" / "cookies.json"
    if not cookies.exists() and not PROFILE_DIR.exists():
        print("Missing LinkedIn session (~/.linkedin-mcp/cookies.json)", file=sys.stderr)
        return 1

    track = args.track
    cfg = load_linkedin_jobs_config(track)
    max_pages = args.max_pages if args.max_pages is not None else int(cfg.get("default_max_pages", 12))
    period = args.period if args.period is not None else int(cfg.get("default_period_days", 1))
    backfill_ids = [x.strip() for x in re.split(r"[,\\s]+", args.backfill_ids) if x.strip()]
    cfg_backfill = [str(x).strip() for x in (cfg.get("backfill_job_ids") or []) if str(x).strip()]
    backfill_ids = list(dict.fromkeys(backfill_ids + cfg_backfill))

    if args.all_queries:
        result = asyncio.run(
            run_all(
                period_days=period,
                max_pages=max_pages,
                max_roles=args.max_roles,
                max_roles_total=args.max_roles_total,
                merge=args.merge,
                since=args.since,
                backfill_ids=backfill_ids,
                use_profile=args.use_profile,
            )
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if result.get("audit") and not result["audit"].get("ok"):
            return 2
        return 0

    if not args.query:
        parser.error("--query or --all-queries required")

    query_meta = {
        "query": args.query,
        "role_keyword": args.role_keyword,
        "region": args.region,
        "track": track,
        "linkedin_url": linkedin_jobs_search_url(
            args.query,
            region=args.region,
            period_days=period,
            cfg=cfg,
        ),
    }
    result = asyncio.run(
        run_query(
            query_meta,
            period_days=period,
            max_pages=max_pages,
            max_roles=args.max_roles,
            merge=args.merge,
            since=args.since,
            cfg=cfg,
        )
    )
    audit = audit_collect_results([result])
    result["audit"] = audit
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not audit.get("ok"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
