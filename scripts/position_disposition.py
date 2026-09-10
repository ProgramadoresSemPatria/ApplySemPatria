"""Per-role triage: pipeline defaults + optional user override from the UI."""

from __future__ import annotations

from typing import Any

DISPOSITION_BEST_FIT = "best_fit"
DISPOSITION_HUMAN_REVIEW = "human_review"
DISPOSITION_REAL_ROLE = "real_role"  # legacy manual override; treated like best_fit
DISPOSITION_NOT_REAL = "not_real"
DISPOSITION_HIDDEN = "hidden"
DISPOSITION_AUTO = "auto"  # API/UI: clear override, use pipeline again

DISPOSITIONS: tuple[str, ...] = (
    DISPOSITION_BEST_FIT,
    DISPOSITION_HUMAN_REVIEW,
    DISPOSITION_REAL_ROLE,
    DISPOSITION_NOT_REAL,
    DISPOSITION_HIDDEN,
)

DISPOSITION_LABELS: dict[str, str] = {
    DISPOSITION_BEST_FIT: "Best fit",
    DISPOSITION_HUMAN_REVIEW: "Human review",
    DISPOSITION_REAL_ROLE: "Real role",
    DISPOSITION_NOT_REAL: "Not a real position",
    DISPOSITION_HIDDEN: "Hidden",
}

DISPOSITION_SHORT: dict[str, str] = {
    DISPOSITION_BEST_FIT: "Best fit",
    DISPOSITION_HUMAN_REVIEW: "Review",
    DISPOSITION_REAL_ROLE: "Real role",
    DISPOSITION_NOT_REAL: "Not real",
    DISPOSITION_HIDDEN: "Hidden",
}


def normalize_disposition(raw: str | None) -> str | None:
    val = (raw or "").strip().lower()
    if val in DISPOSITIONS:
        return val
    return None


def user_override(job: dict[str, Any]) -> str | None:
    """Explicit user choice stored on the job, if any."""
    return normalize_disposition(job.get("position_disposition"))


def auto_disposition_for_job(job: dict[str, Any]) -> str:
    """What the discovery pipeline assumes (same rules as table sections)."""
    filter_result = (job.get("filter_result") or "").strip().lower()
    if filter_result == "skipped":
        return DISPOSITION_NOT_REAL
    if filter_result == "needs_review":
        return DISPOSITION_HUMAN_REVIEW
    if filter_result == "eligible":
        return DISPOSITION_BEST_FIT
    return DISPOSITION_BEST_FIT


def get_disposition(job: dict[str, Any]) -> str:
    override = user_override(job)
    if override:
        return override
    return auto_disposition_for_job(job)


def disposition_label(disposition: str) -> str:
    return DISPOSITION_LABELS.get(disposition, DISPOSITION_LABELS[DISPOSITION_BEST_FIT])


def disposition_is_override(job: dict[str, Any]) -> bool:
    return user_override(job) is not None


def include_in_apply_table(job: dict[str, Any]) -> bool:
    return get_disposition(job) in (
        DISPOSITION_BEST_FIT,
        DISPOSITION_REAL_ROLE,
        DISPOSITION_HUMAN_REVIEW,
    )


def show_in_ui(job: dict[str, Any], *, show_dismissed: bool = False) -> bool:
    d = get_disposition(job)
    if d in (DISPOSITION_NOT_REAL, DISPOSITION_HIDDEN):
        return show_dismissed
    return True


def application_steps_enabled(job: dict[str, Any]) -> bool:
    """Apply steps on automatically for pipeline best-fit; off for review/dismissed."""
    return get_disposition(job) in (DISPOSITION_BEST_FIT, DISPOSITION_REAL_ROLE)


def dm_apply_steps_enabled(job: dict[str, Any]) -> bool:
    """Allow LinkedIn connect/check/message even when salary review disabled other steps."""
    if application_steps_enabled(job):
        return True
    if get_disposition(job) != DISPOSITION_HUMAN_REVIEW:
        return False
    from application_channel import classify_channel, list_application_formats, needs_recruiter_connect  # noqa: WPS433
    from generate_applications import dm_profile_url  # noqa: WPS433

    if not needs_recruiter_connect(job) or not dm_profile_url(job):
        return False
    if classify_channel(job) == "dm":
        return True
    formats = {f["id"] for f in list_application_formats(job)}
    return "direct_message" in formats


def clear_job_disposition(job: dict[str, Any]) -> str:
    job.pop("position_disposition", None)
    return get_disposition(job)


def set_job_disposition(job: dict[str, Any], disposition: str) -> str:
    if disposition == DISPOSITION_AUTO:
        return clear_job_disposition(job)
    normalized = normalize_disposition(disposition)
    if not normalized:
        return clear_job_disposition(job)
    job["position_disposition"] = normalized
    return normalized


def find_job_in_registry(registry: dict[str, Any], job_key: str) -> dict[str, Any] | None:
    from registry import job_key as jk  # noqa: WPS433

    for job in registry.get("jobs", []):
        if jk(job) == job_key:
            return job
    return None


def update_disposition(registry: dict[str, Any], job_key: str, disposition: str) -> dict[str, Any] | None:
    job = find_job_in_registry(registry, job_key)
    if not job:
        return None
    set_job_disposition(job, disposition)
    return job
