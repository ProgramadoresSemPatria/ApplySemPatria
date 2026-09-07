#!/usr/bin/env python3
"""Repair registry fields used by applications table (salary, URLs, company labels, apply email)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from apply_email import apply_email_for_job, extract_apply_email_from_text, is_email_address  # noqa: E402
from linkedin_posts_merge import (  # noqa: E402
    extract_post_salary,
    extract_role_apply_url,
    fallback_linkedin_post_search_url,
    is_apply_only_url,
    is_posts_permalink,
    permalink_matches_author,
    resolve_apply_url_from_text,
    split_apply_email,
)
from post_intent import classify_linkedin_post_filter, classify_post_intent  # noqa: E402
from post_intent_classify import classify_post_llm  # noqa: E402
from registry import load_registry, save_registry  # noqa: E402
from table_format import normalize_company_display  # noqa: E402
from track_store import load_linkedin_config, resolve_track  # noqa: E402


def repair_registry(*, dry_run: bool = False) -> dict[str, int]:
    registry = load_registry()
    stats = {
        "company_cleaned": 0,
        "salary_fixed": 0,
        "salary_cleared": 0,
        "post_url_reset": 0,
        "apply_url_fixed": 0,
        "apply_email_set": 0,
    }

    for job in registry["jobs"]:
        if job.get("source") != "linkedin_posts":
            snippet = job.get("description_snippet") or job.get("description") or ""
            role = job.get("role") or ""
            email = apply_email_for_job(job) or extract_apply_email_from_text(snippet, role)
            if email and job.get("apply_email") != email:
                stats["apply_email_set"] += 1
                if not dry_run:
                    job["apply_email"] = email
            continue

        snippet = job.get("description_snippet") or ""
        role = job.get("role") or "AI Engineer"
        company = job.get("company") or ""
        cleaned = normalize_company_display(company)
        if cleaned != company:
            stats["company_cleaned"] += 1
            if not dry_run:
                job["company"] = cleaned

        new_salary = extract_post_salary(snippet, role)
        old_salary = job.get("salary_usd")
        if new_salary != old_salary:
            if new_salary:
                stats["salary_fixed"] += 1
            else:
                stats["salary_cleared"] += 1
            if not dry_run:
                job["salary_usd"] = new_salary
                job["currency"] = "USD" if new_salary else None

        salary_for_filter = job.get("salary_usd") or new_salary

        url = (job.get("url") or "").strip()
        if is_posts_permalink(url) and not permalink_matches_author(url, cleaned):
            stats["post_url_reset"] += 1
            if not dry_run:
                job["url"] = fallback_linkedin_post_search_url(cleaned, role)
                job["url_source"] = "permalink_author_mismatch"

        apply = (job.get("apply_url") or "").strip()
        if apply and ("search/results/content" in apply or is_posts_permalink(apply) or is_email_address(apply)):
            stats["apply_url_fixed"] += 1
            if not dry_run:
                job["apply_url"] = None if is_email_address(apply) or is_posts_permalink(apply) else None

        # Re-derive apply_email from scratch so extractor improvements (e.g. skip
        # headline "CEO@company" addresses) also CLEAR previously-stored bad values.
        apply_email, apply_url = split_apply_email(job.get("apply_url"), snippet, role)
        if not apply_email:
            apply_email = extract_apply_email_from_text(snippet, role)
        if (job.get("apply_email") or None) != (apply_email or None):
            stats["apply_email_set"] += 1
            if not dry_run:
                job["apply_email"] = apply_email

        if apply_url != (job.get("apply_url") or None):
            stats["apply_url_fixed"] += 1
            if not dry_run:
                job["apply_url"] = apply_url
        elif not job.get("apply_url"):
            resolved = extract_role_apply_url(snippet, role)
            if not resolved:
                resolved = resolve_apply_url_from_text(snippet, job.get("apply_channel"))
            if resolved and not is_posts_permalink(resolved) and not is_email_address(resolved):
                if "search/results/content" not in resolved:
                    stats["apply_url_fixed"] += 1
                    if not dry_run:
                        job["apply_url"] = resolved

        if is_apply_only_url(url) and not is_posts_permalink(url):
            if not dry_run:
                if not job.get("apply_url") and not is_email_address(url):
                    job["apply_url"] = url
                if is_email_address(url):
                    job["apply_email"] = apply_email_for_job(job)
                else:
                    job["url"] = fallback_linkedin_post_search_url(cleaned, role)
                    job["url_source"] = "apply_url_split"

        tid = job.get("track") or resolve_track(None)
        li_cfg = load_linkedin_config(tid)
        intent = classify_post_intent(snippet)
        if li_cfg.get("llm_intent_classify_enabled") and intent == "ambiguous":
            llm = classify_post_llm(snippet, cfg=li_cfg)
            if llm:
                intent = llm
        filt = classify_linkedin_post_filter(snippet, salary_for_filter, li_cfg, post_intent=intent)
        if (
            job.get("filter_result") != filt.filter_result
            or job.get("post_intent") != filt.post_intent
            or job.get("skip_reason") != filt.skip_reason
        ):
            stats.setdefault("filter_reclassified", 0)
            stats["filter_reclassified"] += 1
            if not dry_run:
                job["filter_result"] = filt.filter_result
                job["skip_reason"] = filt.skip_reason
                job["post_intent"] = filt.post_intent

    if not dry_run:
        save_registry(registry)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair registry table fields")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    stats = repair_registry(dry_run=args.dry_run)
    mode = "DRY RUN" if args.dry_run else "UPDATED"
    print(f"{mode}: {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
