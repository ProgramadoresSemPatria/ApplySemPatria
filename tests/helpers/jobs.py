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


def ui_snapshot(job_key: str, *, day: str = "2026-09-06", actions: dict[str, Any] | None = None) -> dict[str, Any]:
    actions = actions or {
        "email": {"available": False, "done": False, "in_progress": False, "label": "Apply via email", "status_text": "not applied"},
        "form": {"available": True, "done": False, "in_progress": False, "label": "Apply via form", "status_text": "not applied"},
        "dm_connect": {"available": True, "done": False, "in_progress": False, "label": "Send connection", "status_text": "not applied"},
        "dm_check": {"available": False, "done": False, "in_progress": False, "label": "Check connection accepted", "status_text": "not applied"},
        "dm_message": {"available": True, "done": False, "in_progress": False, "label": "Send LinkedIn message", "status_text": "not applied"},
    }
    formats = [
        {"id": "form", "label": "Form"},
        {"id": "direct_message", "label": "Direct message"},
    ]
    if actions.get("email", {}).get("available"):
        formats.insert(0, {"id": "email", "label": "Email"})
    return {
        "day": day,
        "generated_at": f"{day}T12:00:00",
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
                "application_formats": formats,
                "post_url": "https://www.linkedin.com/posts/test-activity-123",
                "apply_url": "https://example.com/apply",
                "apply_email": "recruiter@acme.ai" if actions.get("email", {}).get("available") else "",
                "profile_url": "https://www.linkedin.com/in/recruiter-test/",
                "actions": actions,
            }
        ],
    }


def ui_snapshot_with_email(job_key: str, *, day: str = "2026-09-06", email_done: bool = False) -> dict[str, Any]:
    actions = {
        "email": {
            "available": True,
            "done": email_done,
            "in_progress": False,
            "label": "Apply via email",
            "status_text": "sent" if email_done else "not applied",
        },
        "form": {"available": True, "done": False, "in_progress": False, "label": "Apply via form", "status_text": "not applied"},
        "dm_connect": {"available": True, "done": False, "in_progress": False, "label": "Send connection", "status_text": "not applied"},
        "dm_check": {"available": False, "done": False, "in_progress": False, "label": "Check connection accepted", "status_text": "not applied"},
        "dm_message": {"available": True, "done": False, "in_progress": False, "label": "Send LinkedIn message", "status_text": "not applied"},
    }
    return ui_snapshot(job_key, day=day, actions=actions)


def ui_snapshot_duplicate_email(
    *,
    day: str = "2026-09-06",
    email: str = "recruiter@acme.ai",
    email_done: bool = False,
) -> dict[str, Any]:
    """Two list rows sharing one apply email (bulk dedupe regression fixture)."""
    actions = {
        "email": {
            "available": True,
            "done": email_done,
            "in_progress": False,
            "label": "Apply via email",
            "status_text": "sent" if email_done else "not applied",
        },
        "form": {"available": False, "done": False, "in_progress": False, "label": "Apply via form", "status_text": "not applied"},
        "dm_connect": {"available": True, "done": False, "in_progress": False, "label": "Send connection", "status_text": "not applied"},
        "dm_check": {"available": False, "done": False, "in_progress": False, "label": "Check connection accepted", "status_text": "not applied"},
        "dm_message": {"available": True, "done": False, "in_progress": False, "label": "Send LinkedIn message", "status_text": "not applied"},
    }
    formats = [{"id": "email", "label": "Email"}, {"id": "direct_message", "label": "Direct message"}]
    jobs = []
    for idx, suffix in enumerate(("a", "b"), start=1):
        jobs.append(
            {
                "job_key": f"ai-engineer|linkedin|acme ai|ai engineer {suffix}",
                "role": f"AI Engineer {suffix}",
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
                "application_formats": formats,
                "post_url": f"https://www.linkedin.com/posts/test-activity-{idx}",
                "apply_url": "",
                "apply_email": email,
                "profile_url": "https://www.linkedin.com/in/recruiter-test/",
                "actions": actions,
            }
        )
    return {"day": day, "generated_at": f"{day}T12:00:00", "jobs": jobs}


def ui_snapshot_multi_dm(*, day: str = "2026-09-06") -> dict[str, Any]:
    """Two DM list rows with no connect sent yet (full-pipeline regression fixture)."""
    actions = {
        "email": {"available": False, "done": False, "in_progress": False, "label": "Apply via email", "status_text": "not applied"},
        "form": {"available": False, "done": False, "in_progress": False, "label": "Apply via form", "status_text": "not applied"},
        "dm_connect": {"available": True, "done": False, "in_progress": False, "label": "Send connection", "status_text": "not applied"},
        "dm_check": {"available": False, "done": False, "in_progress": False, "label": "Check connection accepted", "status_text": "not applied"},
        "dm_message": {"available": True, "done": False, "in_progress": False, "label": "Send LinkedIn message", "status_text": "not applied"},
    }
    formats = [{"id": "direct_message", "label": "Direct message"}]
    jobs = []
    for idx, (suffix, profile) in enumerate(
        (("a", "https://www.linkedin.com/in/recruiter-a/"), ("b", "https://www.linkedin.com/in/recruiter-b/")),
        start=1,
    ):
        jobs.append(
            {
                "job_key": f"ai-engineer|linkedin|acme ai|ai engineer {suffix}",
                "role": f"AI Engineer {suffix}",
                "company": f"Acme AI {suffix}",
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
                "application_formats": formats,
                "post_url": f"https://www.linkedin.com/posts/test-activity-{idx}",
                "apply_url": "",
                "apply_email": "",
                "profile_url": profile,
                "actions": actions,
            }
        )
    return {"day": day, "generated_at": f"{day}T12:00:00", "jobs": jobs}


def ui_snapshot_multi_dm(*, day: str = "2026-09-06") -> dict[str, Any]:
    """Two DM list rows with no connect sent yet (full-pipeline regression fixture)."""
    actions = {
        "email": {"available": False, "done": False, "in_progress": False, "label": "Apply via email", "status_text": "not applied"},
        "form": {"available": False, "done": False, "in_progress": False, "label": "Apply via form", "status_text": "not applied"},
        "dm_connect": {"available": True, "done": False, "in_progress": False, "label": "Send connection", "status_text": "not applied"},
        "dm_check": {"available": False, "done": False, "in_progress": False, "label": "Check connection accepted", "status_text": "not applied"},
        "dm_message": {"available": True, "done": False, "in_progress": False, "label": "Send LinkedIn message", "status_text": "not applied"},
    }
    formats = [{"id": "direct_message", "label": "Direct message"}]
    jobs = []
    for idx, (suffix, profile) in enumerate(
        (("a", "https://www.linkedin.com/in/recruiter-a/"), ("b", "https://www.linkedin.com/in/recruiter-b/")),
        start=1,
    ):
        jobs.append(
            {
                "job_key": f"ai-engineer|linkedin|acme ai|ai engineer {suffix}",
                "role": f"AI Engineer {suffix}",
                "company": f"Acme AI {suffix}",
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
                "application_formats": formats,
                "post_url": f"https://www.linkedin.com/posts/test-activity-{idx}",
                "apply_url": "",
                "apply_email": "",
                "profile_url": profile,
                "actions": actions,
            }
        )
    return {"day": day, "generated_at": f"{day}T12:00:00", "jobs": jobs}
