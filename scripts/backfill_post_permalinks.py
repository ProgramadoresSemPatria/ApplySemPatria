#!/usr/bin/env python3
"""Backfill linkedin.com/posts/… permalinks by scraping author recent-activity pages."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from linkedin_posts_merge import (  # noqa: E402
    HIRING_HINTS,
    build_feed_update_url,
    is_posts_permalink,
    is_profile_fallback_url,
    match_author_profile_ref,
    permalink_matches_author,
    resolve_feed_update_to_posts_permalink,
)
from registry import REGISTRY_PATH, load_registry, save_registry  # noqa: E402

BROWSERS_PATH = Path.home() / ".linkedin-mcp/patchright-browsers"
CHROME_EXECUTABLE = (
    BROWSERS_PATH
    / "chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
)
COOKIES_PATH = Path.home() / ".linkedin-mcp/cookies.json"

URN_RE = re.compile(
    r"urn(?:%3A|:)li(?:%3A|:)(activity|share|ugcPost)(?:%3A|:)(\d+)",
    re.IGNORECASE,
)
TAG_RE = re.compile(r"<[^>]+>")


def load_refs_from_runs() -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for pattern in ("browser-collect*/**/*.json",):
        for path in sorted((ROOT / "runs").glob(pattern)):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            refs.extend((data.get("references") or {}).get("search_results") or [])
    return refs


def build_author_slug_map(refs: list[dict[str, Any]]) -> dict[str, tuple[str, str]]:
    mapping: dict[str, tuple[str, str]] = {}
    for ref in refs:
        url = ref.get("url") or ""
        kind = ref.get("kind") or ""
        if kind == "person":
            match = re.search(r"linkedin\.com/in/([^/?#]+)", url, re.I)
            if match:
                mapping[_norm_name(ref.get("text") or "")] = (match.group(1), "person")
        elif kind == "company":
            match = re.search(r"linkedin\.com/company/([^/?#]+)", url, re.I)
            if match:
                mapping[_norm_name(ref.get("text") or "")] = (match.group(1), "company")
        slug = ref.get("author_slug") or ref.get("text") or ""
        if ref.get("kind") == "feed_post" and slug and ref.get("author_kind") == "person":
            mapping.setdefault(_norm_name(slug.replace("-", " ")), (slug, "person"))
    return mapping


def _norm_name(name: str) -> str:
    name = re.sub(r"^~+\s*", "", (name or "").strip())
    name = re.sub(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF]", " ", name)
    return re.sub(r"\s+", " ", name).casefold()


def author_slug_for_job(
    job: dict[str, Any],
    refs: list[dict[str, Any]],
    slug_map: dict[str, tuple[str, str]] | None = None,
) -> tuple[str, str] | None:
    url = (job.get("url") or "").strip()
    person = re.search(r"linkedin\.com/in/([^/?#]+)", url, re.I)
    if person:
        return person.group(1), "person"
    company = re.search(r"linkedin\.com/company/([^/?#]+)", url, re.I)
    if company:
        return company.group(1), "company"

    author = _norm_name(job.get("company") or "")
    if slug_map and author in slug_map:
        return slug_map[author]

    matched, _ = match_author_profile_ref(job.get("company") or "", refs)
    if matched:
        person = re.search(r"linkedin\.com/in/([^/?#]+)", matched, re.I)
        if person:
            return person.group(1), "person"
        company = re.search(r"linkedin\.com/company/([^/?#]+)", matched, re.I)
        if company:
            return company.group(1), "company"
    return None


def needs_permalink(job: dict[str, Any]) -> bool:
    if job.get("source") != "linkedin_posts":
        return False
    url = (job.get("url") or "").strip()
    if is_posts_permalink(url):
        return False
    if is_profile_fallback_url(url):
        return True
    if "search/results/content" in url:
        return True
    if "/feed/update/" in url:
        return True
    return False


def _html_window_text(html: str, pos: int, *, radius: int = 6000) -> str:
    window = html[max(0, pos - radius) : pos + radius]
    text = TAG_RE.sub(" ", window)
    return re.sub(r"\s+", " ", text).strip().casefold()


def _score_match(window_text: str, job: dict[str, Any]) -> float:
    snippet = (job.get("description_snippet") or "").casefold()
    if not snippet or not window_text:
        return 0.0
    score = 0.0
    snippet_words = {w for w in re.findall(r"[a-z0-9]{4,}", snippet) if len(w) >= 4}
    window_words = set(re.findall(r"[a-z0-9]{4,}", window_text))
    overlap = len(snippet_words & window_words)
    score += overlap * 2.0
    role = (job.get("role") or "").casefold()
    if role and role in window_text:
        score += 8.0
    if HIRING_HINTS.search(window_text):
        score += 3.0
    if HIRING_HINTS.search(snippet) and any(w in window_text for w in ("hiring", "contratando", "buscamos")):
        score += 2.0
    # Prefer windows that share distinctive snippet prefix (author block + early body)
    prefix = re.sub(r"\s+", " ", snippet[40:220]).strip()
    if len(prefix) > 40 and prefix[:80] in window_text:
        score += 15.0
    # First 120 chars of snippet often unique per duplicate author repost
    head = re.sub(r"\s+", " ", snippet[:120])
    if len(head) > 30 and head in window_text:
        score += 20.0
    return score


async def lookup_slug_via_people_search(
    context: Any,
    author: str,
    slug_map: dict[str, tuple[str, str]],
) -> tuple[str, str] | None:
    """Find /in/ or /company/ slug via LinkedIn people search."""
    author_key = _norm_name(author)
    if author_key in slug_map:
        return slug_map[author_key]

    query = re.sub(r"^~+\s*", "", author.strip())
    query = re.sub(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF]", " ", query)
    query = re.sub(r"\s+", " ", query).strip()
    if not query or query.lower() == "unknown":
        return None

    url = "https://www.linkedin.com/search/results/people/?" + urllib.parse.urlencode(
        {"keywords": query, "origin": "FACETED_SEARCH"}
    )
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(2.0)
        html = await page.content()
    finally:
        await page.close()

    author_slug = _slugify(query)
    best: tuple[str, str] | None = None
    for match in re.finditer(r"https://www\.linkedin\.com/in/([a-z0-9-]+)/", html, re.I):
        slug = match.group(1)
        slug_norm = re.sub(r"[^a-z0-9]", "", slug.casefold())
        if author_slug and (author_slug in slug_norm or slug_norm in author_slug):
            best = (slug, "person")
            break
    if not best:
        match = re.search(r"https://www\.linkedin\.com/in/([a-z0-9-]+)/", html, re.I)
        if match:
            slug_norm = re.sub(r"[^a-z0-9]", "", match.group(1).casefold())
            if author_slug and (author_slug in slug_norm or slug_norm in author_slug):
                best = (match.group(1), "person")
    if best:
        slug_map[author_key] = best
    return best


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())


async def fetch_activity_candidates(
    slug: str,
    kind: str,
    *,
    max_scrolls: int = 4,
) -> list[tuple[str, str, str]]:
    """Return list of (urn_kind, activity_id, window_text)."""
    import os

    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS_PATH)
    from patchright.async_api import async_playwright

    if kind == "company":
        url = f"https://www.linkedin.com/company/{slug}/posts/?viewAsMember=true"
    else:
        url = f"https://www.linkedin.com/in/{slug}/recent-activity/all/"

    cookies: list[dict[str, Any]] = []
    if COOKIES_PATH.exists():
        cookies = json.loads(COOKIES_PATH.read_text(encoding="utf-8"))

    async with async_playwright() as p:
        launch_kwargs: dict[str, Any] = {"headless": True}
        if CHROME_EXECUTABLE.exists():
            launch_kwargs["executable_path"] = str(CHROME_EXECUTABLE)
        browser = await p.chromium.launch(**launch_kwargs)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        if cookies:
            await context.add_cookies(cookies)
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=90000)
        await asyncio.sleep(2.0)

        seen: set[str] = set()
        candidates: list[tuple[str, str, str]] = []
        for _ in range(max_scrolls):
            html = await page.content()
            for match in URN_RE.finditer(html):
                activity_id = match.group(2)
                if activity_id in seen:
                    continue
                seen.add(activity_id)
                urn_kind = match.group(1).lower()
                window_text = _html_window_text(html, match.start())
                candidates.append((urn_kind, activity_id, window_text))
            await page.mouse.wheel(0, 2400)
            await asyncio.sleep(1.2)
        await context.close()
    return candidates


async def backfill_jobs(
    jobs: list[dict[str, Any]],
    refs: list[dict[str, Any]],
    *,
    limit: int = 0,
    pause_sec: float = 0.8,
) -> dict[str, int]:
    stats = {"checked": 0, "resolved": 0, "skipped_no_slug": 0, "skipped_no_match": 0}
    slug_cache: dict[str, list[tuple[str, str, str]]] = {}
    slug_map = build_author_slug_map(refs)

    import os

    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS_PATH)
    from patchright.async_api import async_playwright

    cookies: list[dict[str, Any]] = []
    if COOKIES_PATH.exists():
        cookies = json.loads(COOKIES_PATH.read_text(encoding="utf-8"))

    targets = [j for j in jobs if needs_permalink(j)]
    if limit:
        targets = targets[:limit]

    launch_kwargs: dict[str, Any] = {"headless": True}
    if CHROME_EXECUTABLE.exists():
        launch_kwargs["executable_path"] = str(CHROME_EXECUTABLE)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**launch_kwargs)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        if cookies:
            await context.add_cookies(cookies)

        for job in targets:
            stats["checked"] += 1
            slug_info = author_slug_for_job(job, refs, slug_map)
            if not slug_info:
                slug_info = await lookup_slug_via_people_search(
                    context, job.get("company") or "", slug_map
                )
                await asyncio.sleep(pause_sec)
            if not slug_info:
                stats["skipped_no_slug"] += 1
                continue
            slug, kind = slug_info
            cache_key = f"{kind}:{slug}"
            if cache_key not in slug_cache:
                slug_cache[cache_key] = await fetch_activity_candidates(slug, kind)
                await asyncio.sleep(pause_sec)

            candidates = slug_cache[cache_key]
            if not candidates:
                stats["skipped_no_match"] += 1
                continue

            best: tuple[str, str, str] | None = None
            best_score = 0.0
            for candidate in candidates:
                score = _score_match(candidate[2], job)
                if score > best_score:
                    best_score = score
                    best = candidate

            if not best or best_score < 4.0:
                stats["skipped_no_match"] += 1
                continue

            urn_kind, activity_id, _window = best
            feed_url = build_feed_update_url(urn_kind, activity_id)
            posts_url = resolve_feed_update_to_posts_permalink(feed_url)
            if not is_posts_permalink(posts_url):
                stats["skipped_no_match"] += 1
                continue
            if not permalink_matches_author(posts_url, job.get("company") or ""):
                stats["skipped_no_match"] += 1
                continue

            job["url"] = posts_url
            job["url_source"] = "activity_backfill"
            stats["resolved"] += 1
            print(f"  ✓ {job.get('company', '?')[:40]} → {posts_url[:90]}…")

        await browser.close()

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill LinkedIn /posts/ permalinks from activity pages")
    parser.add_argument("--limit", type=int, default=0, help="Max jobs to process (0 = all needing permalinks)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--table-only", action="store_true", help="Only jobs that would appear in applications table")
    args = parser.parse_args()

    refs = load_refs_from_runs()
    registry = load_registry()
    jobs = registry["jobs"]

    if args.table_only:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from linkedin_posts_merge import sort_jobs_by_recency  # noqa: E402
        from registry import job_key  # noqa: E402

        tz = ZoneInfo("America/Sao_Paulo")
        since = datetime(2026, 8, 24, tzinfo=tz)
        li = [
            j
            for j in jobs
            if j.get("source") == "linkedin_posts"
            and j.get("discovered_at")
            and datetime.fromisoformat(j["discovered_at"]) >= since
        ]
        li = sort_jobs_by_recency(li)
        eligible = [j for j in li if j.get("filter_result") == "eligible"][:45]
        review = [j for j in li if j.get("filter_result") == "needs_review"][:35]
        table_keys = {job_key(j) for j in eligible + review}
        jobs = [j for j in registry["jobs"] if job_key(j) in table_keys]

    needing = sum(1 for j in jobs if needs_permalink(j))
    print(f"Backfilling permalinks for {needing} jobs…")

    stats = asyncio.run(backfill_jobs(jobs, refs, limit=args.limit))
    print(
        f"Done: checked={stats['checked']} resolved={stats['resolved']} "
        f"no_slug={stats['skipped_no_slug']} no_match={stats['skipped_no_match']}"
    )

    if args.dry_run:
        return 0

    save_registry(registry)
    print(f"Saved {REGISTRY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
