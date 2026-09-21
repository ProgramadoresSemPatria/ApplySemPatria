"""Shared types for retrieval source outputs."""

from __future__ import annotations

from typing import Any, TypedDict


class JobRecord(TypedDict, total=False):
    """Normalized job dict written to registry/jobs.json."""

    source: str
    url: str
    role: str
    company: str
    salary_usd: str | None
    currency: str | None
    location_note: str | None
    posted_at: str | int | float | None
    posted_label: str | None
    apply_url: str | None
    apply_channel: str | None
    filter_result: str | None
    skip_reason: str | None
    discovered_at: str
    description_snippet: str | None
    recruiter_profile_url: str | None
    profile_url: str | None
    track_id: str | None


class MergeResult(TypedDict, total=False):
    run_path: str
    registry_path: str
    new_total: int
    eligible: int
    needs_review: int
    posts_parsed: int


class CollectResult(TypedDict, total=False):
    query: str
    posts_found: int
    roles_kept: int
    raw_path: str
    merge: MergeResult | None


def as_job_record(raw: dict[str, Any]) -> JobRecord:
    return raw  # type: ignore[return-value]
