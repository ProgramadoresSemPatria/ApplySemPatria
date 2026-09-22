"""Extract recruiter apply-by-email addresses from job registry rows."""

from __future__ import annotations

import re
from typing import Any

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
EMAIL_FIND_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# Never treat sender / personal inboxes as apply targets
IGNORE_EMAILS = {
    "caiohandradelima@gmail.com",
    "caiohenriqueandradel@gmail.com",
}

# Local-parts that usually indicate a person's HEADLINE/title (e.g. "CEO@Company.la"),
# not an apply address — skip unless an explicit apply cue is nearby.
TITLE_LOCALPARTS = {
    "ceo", "cto", "cfo", "coo", "cmo", "founder", "cofounder", "co-founder",
    "director", "president", "owner", "partner", "vp",
}

APPLY_CUE = re.compile(
    r"(send|share|apply|e-?mail|mail|cv|resume|postul|env[ií]a|mand[ae]|contact|reach|📩|📧|✉)",
    re.IGNORECASE,
)


def is_email_address(value: str | None) -> bool:
    return bool(value and EMAIL_RE.match(value.strip()))


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    email = value.strip().lower()
    if not EMAIL_RE.match(email):
        return None
    if email in IGNORE_EMAILS:
        return None
    return email


def extract_apply_email_from_text(text: str, role: str = "") -> str | None:
    """Pick the best apply email from post/JD text."""
    if not text:
        return None

    role_lower = (role or "").casefold()
    candidates: list[str] = []

    if role_lower:
        for line in re.split(r"[\n\r]+", text):
            if role_lower not in line.casefold():
                continue
            for match in EMAIL_FIND_RE.finditer(line):
                email = normalize_email(match.group(0))
                if not email:
                    continue
                local = email.split("@", 1)[0]
                if local in TITLE_LOCALPARTS and not APPLY_CUE.search(line):
                    continue
                candidates.append(email)

    for match in EMAIL_FIND_RE.finditer(text):
        email = normalize_email(match.group(0))
        if not email or email in candidates:
            continue
        local = email.split("@", 1)[0]
        if local in TITLE_LOCALPARTS:
            # Only accept a title-looking email if an apply cue sits near it.
            span = text[max(0, match.start() - 60): match.end() + 60]
            if not APPLY_CUE.search(span):
                continue
        candidates.append(email)

    if not candidates:
        return None

    def score(email: str) -> tuple[int, int]:
        local = email.split("@", 1)[0]
        hiring_hint = any(
            token in local
            for token in ("hr", "jobs", "career", "recruit", "hiring", "talent", "apply")
        )
        return (1 if hiring_hint else 0, -len(email))

    return sorted(candidates, key=score, reverse=True)[0]


def apply_email_for_job(job: dict[str, Any]) -> str | None:
    """Return apply email for a registry job, or None."""
    stored = normalize_email(job.get("apply_email"))
    if stored:
        return stored

    apply = (job.get("apply_url") or "").strip()
    if is_email_address(apply):
        return normalize_email(apply)

    snippet = job.get("description_snippet") or job.get("description") or ""
    role = job.get("role") or ""
    return extract_apply_email_from_text(snippet, role)


def apply_email_display(job: dict[str, Any]) -> str:
    return apply_email_for_job(job) or "—"
