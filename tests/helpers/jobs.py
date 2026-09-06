"""Shared job/card fixtures for UI and feature tests."""

from __future__ import annotations

from typing import Any


def linkedin_dm_job(
    *,
    company: str = "Acme AI",
    role: str = "AI Engineer",
    profile_url: str = "https://www.linkedin.com/in/recruiter-test/",
    apply_url: str = "https://example.com/apply",
    track: str = "ai-engineer",
    filter_result: str = "eligible",
) -> dict[str, Any]:
    return {
        "track": track,
        "source": "linkedin_posts",
        "company": company,
        "role": role,
        "url": "https://www.linkedin.com/posts/test-activity-123",
        "apply_url": apply_url,
        "recruiter_profile_url": profile_url,
        "filter_result": filter_result,
        "salary_usd": "USD 120k",
        "location_note": "Remote LATAM",
        "posted_label": "2d",
    }


def ui_snapshot(job_key: str, *, actions: dict[str, Any] | None = None) -> dict[str, Any]:
    actions = actions or {
        "email": {"available": False, "done": False, "in_progress": False, "label": "Apply via email", "status_text": "not applied"},
        "form": {"available": True, "done": False, "in_progress": False, "label": "Apply via form", "status_text": "not applied"},
        "dm_connect": {"available": True, "done": False, "in_progress": False, "label": "Send connection", "status_text": "not applied"},
        "dm_check": {"available": False, "done": False, "in_progress": False, "label": "Check connection accepted", "status_text": "not applied"},
        "dm_message": {"available": True, "done": False, "in_progress": False, "label": "Send LinkedIn message", "status_text": "not applied"},
    }
    return {
        "day": "live",
        "generated_at": "2026-09-06T12:00:00",
        "jobs": [
            {
                "job_key": job_key,
                "role": "AI Engineer",
                "company": "Acme AI",
                "track_label": "AI Engineer",
                "role_from_label": "LinkedIn",
                "salary": "USD 120k",
                "location": "Remote LATAM",
                "posted": "2d",
                "section": "linkedin_eligible",
                "position_disposition": "best_fit",
                "position_disposition_label": "Best fit",
                "position_disposition_auto": "best_fit",
                "position_disposition_is_override": False,
                "application_steps_enabled": True,
                "application_formats": [
                    {"id": "form", "label": "Form"},
                    {"id": "direct_message", "label": "Direct message"},
                ],
                "post_url": "https://www.linkedin.com/posts/test-activity-123",
                "apply_url": "https://example.com/apply",
                "profile_url": "https://www.linkedin.com/in/recruiter-test/",
                "actions": actions,
            }
        ],
    }
