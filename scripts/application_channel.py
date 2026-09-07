"""Classify how to apply for a job: email, url (form), or dm (direct message).

Categories (per user spec):
  - email : recruiter apply email is known -> use email-apply skill
  - url   : external apply link / form (lnkd.in, /jobs/view, ATS, company form)
  - dm    : direct message the recruiter. Commenting on a post is ALSO treated
            as dm (we NEVER comment on posts).
"""

from __future__ import annotations

import re
from typing import Any

SCRIPTS_DIR_MARKER = True

from apply_email import apply_email_for_job, is_email_address  # noqa: E402

CHANNEL_EMAIL = "email"
CHANNEL_URL = "url"
CHANNEL_DM = "dm"

IN_SLUG_RE = re.compile(r"linkedin\.com/in/([^/?#]+)", re.I)
POSTS_SLUG_RE = re.compile(r"linkedin\.com/posts/([a-z0-9-]+)_", re.I)

CHANNEL_LABELS = {
    CHANNEL_EMAIL: "Email",
    CHANNEL_URL: "URL/Form",
    CHANNEL_DM: "Direct Msg",
}

FORMAT_LABELS = {
    "email": "Email",
    "form": "Form",
    "direct_message": "Direct message",
}

# Signals in post text that mean "comment to apply" -> treated as DM (never comment)
COMMENT_HINTS = re.compile(
    r"\b(comment(?:ing)?|drop(?:\s+a)?\s+comment|comment\s+below|comment\s+\"?interested"
    r"|comenta|comente|deixe\s+um\s+coment|type\s+\"?interested)\b",
    re.IGNORECASE,
)

# Signals that mean "DM / message me" explicitly
DM_HINTS = re.compile(
    r"\b(dm|d\.m\.|message me|send me a message|inbox|reach out|pm me|"
    r"env[ií]a(?:me)?\s+un\s+mensaje|mand[ae]\s+(?:me\s+)?(?:un\s+)?mensaje)\b",
    re.IGNORECASE,
)

APPLY_URL_RE = re.compile(r"https?://[^\s\)\]\"']+", re.IGNORECASE)


def _real_apply_url(job: dict[str, Any]) -> str | None:
    apply = (job.get("apply_url") or "").strip()
    if apply and apply.startswith("http") and not is_email_address(apply):
        return apply
    # Non-LinkedIn/board jobs: the job url itself is the apply page.
    if job.get("source") not in ("linkedin_posts", "google"):
        url = (job.get("url") or "").strip()
        if url.startswith("http"):
            return url
    return None


def classify_channel(job: dict[str, Any]) -> str:
    """Return one of: email, url, dm."""
    if apply_email_for_job(job):
        return CHANNEL_EMAIL

    if _real_apply_url(job):
        return CHANNEL_URL

    # LinkedIn post with no email and no external link -> DM the recruiter.
    # Commenting-to-apply is explicitly downgraded to DM (never comment).
    return CHANNEL_DM


def channel_label(job: dict[str, Any]) -> str:
    return CHANNEL_LABELS[classify_channel(job)]


def form_apply_url(job: dict[str, Any]) -> str | None:
    """External apply link when the role has a form/link apply path."""
    return _real_apply_url(job)


def has_form_apply(job: dict[str, Any]) -> bool:
    """True when an external apply URL / form is available."""
    if _real_apply_url(job):
        return True
    apply = (job.get("apply_url") or "").strip()
    if apply.startswith("http") and not is_email_address(apply):
        return True
    return False


def is_linkedin_post(job: dict[str, Any]) -> bool:
    return job.get("source") == "linkedin_posts"


def recruiter_profile_url(job: dict[str, Any]) -> str | None:
    """Resolve a recruiter PERSON /in/ URL for connect + message."""
    url = (job.get("url") or "").strip()
    m = IN_SLUG_RE.search(url)
    if m:
        return f"https://www.linkedin.com/in/{m.group(1)}/"
    m = POSTS_SLUG_RE.search(url)
    if m:
        return f"https://www.linkedin.com/in/{m.group(1)}/"
    prof = (job.get("recruiter_profile_url") or job.get("profile_url") or "").strip()
    if prof.startswith("http") and "/in/" in prof.lower():
        return prof if prof.endswith("/") else f"{prof}/"
    return None


def needs_recruiter_connect(job: dict[str, Any]) -> bool:
    """True when we should connect with the recruiter on LinkedIn."""
    if job.get("post_intent") == "job_seeker" or job.get("filter_result") == "skipped":
        text = job.get("description_snippet") or job.get("description") or ""
        from post_intent import is_job_seeker_post  # noqa: WPS433

        if job.get("skip_reason") == "job_seeker_post" or is_job_seeker_post(text):
            return False
    if not is_linkedin_post(job):
        return classify_channel(job) == CHANNEL_DM
    prof = recruiter_profile_url(job)
    if not prof:
        return False
    if classify_channel(job) == CHANNEL_DM:
        return True
    return has_form_apply(job)


def has_direct_message_apply(job: dict[str, Any]) -> bool:
    """True when LinkedIn DM/connect to a recruiter profile is possible."""
    if not is_linkedin_post(job):
        return False
    return recruiter_profile_url(job) is not None


def recruiter_message_enabled(job: dict[str, Any], li_cfg: dict[str, Any] | None = None) -> bool:
    """True when a follow-up recruiter message is part of the workflow."""
    if not has_direct_message_apply(job):
        return False
    cfg = li_cfg or {}
    if is_linkedin_post(job) and has_form_apply(job):
        return bool(cfg.get("form_link_message_enabled", True))
    return True


def list_application_formats(job: dict[str, Any]) -> list[dict[str, str]]:
    """All ways to apply for this role (can be more than one)."""
    formats: list[dict[str, str]] = []
    if apply_email_for_job(job):
        formats.append({"id": "email", "label": FORMAT_LABELS["email"]})
    if has_form_apply(job):
        formats.append({"id": "form", "label": FORMAT_LABELS["form"]})
    if has_direct_message_apply(job):
        formats.append({"id": "direct_message", "label": FORMAT_LABELS["direct_message"]})
    if not formats:
        ch = classify_channel(job)
        fallback = {"email": "email", "url": "form", "dm": "direct_message"}.get(ch, ch)
        formats.append({"id": fallback, "label": FORMAT_LABELS.get(fallback, channel_label(job))})
    return formats


def apply_target(job: dict[str, Any]) -> str:
    """Human-readable apply target for the given channel."""
    channel = classify_channel(job)
    if channel == CHANNEL_EMAIL:
        return apply_email_for_job(job) or "—"
    if channel == CHANNEL_URL:
        return _real_apply_url(job) or "—"
    # dm -> recruiter profile if we can derive one, else the post
    url = (job.get("url") or "").strip()
    return url or "DM recruiter"


def is_comment_apply(job: dict[str, Any]) -> bool:
    """True if the post asks to comment to apply (still handled as DM)."""
    text = job.get("description_snippet") or job.get("description") or ""
    return bool(COMMENT_HINTS.search(text))
