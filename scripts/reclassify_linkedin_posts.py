#!/usr/bin/env python3
"""Reclassify linkedin_posts registry entries with post_intent rules."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from linkedin_posts_merge import extract_post_salary  # noqa: E402
from post_intent import classify_linkedin_post_filter, classify_post_intent, is_job_seeker_post  # noqa: E402
from post_intent_classify import classify_post_llm  # noqa: E402
from registry import load_registry, save_registry  # noqa: E402
from track_store import load_linkedin_config, resolve_track  # noqa: E402


def reclassify_linkedin_posts(
    *,
    track_id: str | None = None,
    dry_run: bool = False,
    use_llm: bool = False,
) -> dict[str, int]:
    tid = resolve_track(track_id)
    cfg = load_linkedin_config(tid)
    if use_llm:
        cfg = {**cfg, "llm_intent_classify_enabled": True}

    registry = load_registry()
    stats = {
        "total": 0,
        "skipped_seeker": 0,
        "skipped_noise": 0,
        "needs_review": 0,
        "eligible": 0,
        "unchanged": 0,
    }

    for job in registry.get("jobs", []):
        if job.get("source") != "linkedin_posts":
            continue
        stats["total"] += 1
        snippet = job.get("description_snippet") or job.get("description") or ""
        role = job.get("role") or "AI Engineer"
        salary = job.get("salary_usd") or extract_post_salary(snippet, role)

        intent = classify_post_intent(snippet)
        if use_llm and intent == "ambiguous" and cfg.get("llm_intent_classify_enabled"):
            llm = classify_post_llm(snippet, cfg=cfg)
            if llm:
                intent = llm

        filt = classify_linkedin_post_filter(
            snippet,
            salary,
            cfg,
            post_intent=intent,
        )

        old_result = job.get("filter_result")
        old_intent = job.get("post_intent")
        if old_result == filt.filter_result and old_intent == filt.post_intent:
            stats["unchanged"] += 1
            continue

        if not dry_run:
            job["filter_result"] = filt.filter_result
            job["skip_reason"] = filt.skip_reason
            job["post_intent"] = filt.post_intent
            if salary:
                job["salary_usd"] = salary
                job["currency"] = "USD"

        if filt.filter_result == "skipped":
            if is_job_seeker_post(snippet) or filt.post_intent == "job_seeker":
                stats["skipped_seeker"] += 1
            else:
                stats["skipped_noise"] += 1
        elif filt.filter_result == "eligible":
            stats["eligible"] += 1
        elif filt.filter_result == "needs_review":
            stats["needs_review"] += 1

    if not dry_run:
        save_registry(registry)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Reclassify LinkedIn posts in registry")
    parser.add_argument("--track", default=None, help="Track id (default: manifest default)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--llm", action="store_true", help="Use LLM for ambiguous posts")
    args = parser.parse_args()
    stats = reclassify_linkedin_posts(track_id=args.track, dry_run=args.dry_run, use_llm=args.llm)
    print(json_stats(stats))
    return 0


def json_stats(stats: dict[str, int]) -> str:
    import json

    return json.dumps(stats, indent=2)


if __name__ == "__main__":
    raise SystemExit(main())
