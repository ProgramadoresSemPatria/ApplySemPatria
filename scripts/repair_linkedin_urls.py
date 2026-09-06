#!/usr/bin/env python3
"""Repair linkedin-post: placeholder URLs in the job registry."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from linkedin_content_collect import collect_feed_text  # noqa: E402
from linkedin_posts_merge import (  # noqa: E402
    build_queries,
    is_feed_update_url,
    is_placeholder_post_url,
    load_linkedin_config,
    normalize_linkedin_job_urls,
    resolve_feed_update_to_posts_permalink,
)
from registry import REGISTRY_PATH, load_registry, save_registry  # noqa: E402


def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for ref in refs:
        url = ref.get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(ref)
    return out


def load_refs_from_runs(runs_dir: Path) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    patterns = ("browser-collect*/**/*.json",)
    for pattern in patterns:
        for path in sorted(runs_dir.glob(pattern)):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            block = (data.get("references") or {}).get("search_results") or []
            refs.extend(block)
    return _dedupe_refs(refs)


async def collect_refs_via_browser(
    queries: list[dict[str, str]],
    *,
    max_scrolls: int,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for block in queries:
        url = block["linkedin_url"]
        _raw, scroll_refs, stats = await collect_feed_text(url, max_scrolls=max_scrolls)
        refs.extend(scroll_refs)
        print(
            f"  {block['query']}: profile_refs={stats.get('profile_refs', 0)} "
            f"activity={stats.get('activity_urls', 0)} scrolls={stats.get('scrolls', 0)}"
        )
    return _dedupe_refs(refs)


def repair_jobs(
    jobs: list[dict[str, Any]],
    refs: list[dict[str, Any]],
    *,
    resolve_posts: bool = False,
) -> dict[str, int]:
    stats = {"post_url_fixed": 0, "apply_url_fixed": 0, "posts_resolved": 0, "still_broken": 0}
    for job in jobs:
        if job.get("source") != "linkedin_posts":
            continue

        before_url = job.get("url")
        before_apply = job.get("apply_url")
        normalize_linkedin_job_urls(job, refs, resolve_posts=resolve_posts)

        if resolve_posts:
            url = (job.get("url") or "").strip()
            if is_feed_update_url(url):
                resolved = resolve_feed_update_to_posts_permalink(url)
                if resolved != url:
                    job["url"] = resolved
                    job["url_source"] = job.get("url_source") or "posts_permalink"
                    stats["posts_resolved"] += 1

        if before_url != job.get("url"):
            stats["post_url_fixed"] += 1
        if (not before_apply) and job.get("apply_url"):
            stats["apply_url_fixed"] += 1
        if is_placeholder_post_url(job.get("url", "")):
            stats["still_broken"] += 1
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair LinkedIn placeholder post URLs in registry")
    parser.add_argument("--browser", action="store_true", help="Scroll LinkedIn search to collect profile refs")
    parser.add_argument(
        "--query-index",
        type=int,
        default=1,
        help="1-based query index to scroll when --browser (default: 1 = ai engineer latam)",
    )
    parser.add_argument("--max-scrolls", type=int, default=120, help="Max scrolls per browser query")
    parser.add_argument(
        "--resolve-posts",
        action="store_true",
        help="Resolve feed/update URLs to linkedin.com/posts/… permalinks",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report fixes without saving registry")
    args = parser.parse_args()

    refs = load_refs_from_runs(ROOT / "runs")
    print(f"Loaded {len(refs)} refs from saved runs")

    if args.browser:
        cfg = load_linkedin_config()
        queries = build_queries(cfg)
        idx = max(1, min(args.query_index, len(queries))) - 1
        selected = [queries[idx]]
        print(f"Browser scroll for query: {selected[0]['query']}")
        browser_refs = asyncio.run(
            collect_refs_via_browser(selected, max_scrolls=args.max_scrolls)
        )
        refs = _dedupe_refs(refs + browser_refs)
        print(f"Total refs after browser: {len(refs)}")

    registry = load_registry()
    stats = repair_jobs(registry["jobs"], refs, resolve_posts=args.resolve_posts)
    broken = sum(
        1
        for j in registry["jobs"]
        if j.get("source") == "linkedin_posts" and is_placeholder_post_url(j.get("url", ""))
    )
    print(
        f"Fixed post URLs: {stats['post_url_fixed']} · apply URLs: {stats['apply_url_fixed']} · "
        f"posts permalinks: {stats['posts_resolved']} · still broken: {stats['still_broken']} · "
        f"remaining placeholders: {broken}"
    )

    if args.dry_run:
        return 0

    save_registry(registry)
    print(f"Saved {REGISTRY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
