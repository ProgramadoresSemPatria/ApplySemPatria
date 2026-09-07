"""LinkedIn post intent: hiring vs job-seeker vs noise (regex + optional LLM)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

# Recruiter / company hiring language (tightened — no bare "looking for").
HIRING_HINTS = re.compile(
    r"(?:"
    r"\b(?:we'?re hiring|we are hiring|now hiring|actively hiring|hiring)\b"
    r"|#hiring\b"
    r"|\b(?:open role|open roles|open position|open positions|join (?:us|our team))\b"
    r"|\bapply now\b|\bjob alert\b"
    r"|\b(?:contratando|buscamos|estamos contratando)\b"
    r"|\blooking for (?:a |an |the )?(?:senior |sr\.? |lead |staff )?"
    r"(?:ai |ml |software |data |backend |frontend |full[- ]stack )?"
    r"(?:engineer|developer|architect|designer|manager|analyst|scientist)s?\b"
    r"|\bseeking (?:a |an )?(?:senior |sr\.? )?"
    r"(?:ai |ml |software )?(?:engineer|developer|architect)s?\b"
    r")",
    re.IGNORECASE,
)

# Candidate / job-seeker language — reject before DM pipeline.
JOB_SEEKER_HINTS = re.compile(
    r"(?:"
    r"#opentowork\b|\bopen to work\b|\bopen to (?:new )?opportunities\b"
    r"|\bseeking (?:new )?opportunities\b|\blooking for opportunities\b"
    r"|\blooking for (?:my |a )?(?:next )?(?:role|job|position|challenge)\b"
    r"|\b(?:actively )?job hunting\b|\bjob search\b|\bhelp me find\b"
    r"|\bavailable for (?:hire|work)\b|\bfor hire\b"
    r"|\bnot the hiring manager\b|\bnot (?:a |the )?recruiter\b"
    r"|\bi'?m not hiring\b|\bwe are not hiring\b"
    r"|\bfounder\b.*\blooking for opportunities\b"
    r"|\bconnect me with recruiters\b|\brefer me\b"
    r"|\bresume review\b|\bopen to remote (?:roles|opportunities|work)\b"
    r")",
    re.IGNORECASE,
)

ROLE_KEYWORD_RE = re.compile(
    r"\b(?:ai engineer|agent engineer|agentic engineer|ml engineer|llm engineer)\b",
    re.IGNORECASE,
)

LLMClassifyFn = Callable[[str, str | None], str | None]


@dataclass(frozen=True)
class PostFilterResult:
    filter_result: str
    skip_reason: str | None
    post_intent: str
    ingest: bool


def is_job_seeker_post(text: str) -> bool:
    return bool(text and JOB_SEEKER_HINTS.search(text))


def has_hiring_intent(text: str) -> bool:
    return bool(text and HIRING_HINTS.search(text))


def is_borderline_post(text: str) -> bool:
    """Regex unclear — role keyword present but no hiring/seeker signal."""
    if not text:
        return False
    if is_job_seeker_post(text) or has_hiring_intent(text):
        return False
    return bool(ROLE_KEYWORD_RE.search(text))


def classify_post_intent(text: str, *, author_headline: str | None = None) -> str:
    combined = f"{text or ''}\n{author_headline or ''}".strip()
    if is_job_seeker_post(combined):
        return "job_seeker"
    if has_hiring_intent(combined):
        return "hiring"
    if ROLE_KEYWORD_RE.search(combined):
        return "ambiguous"
    return "noise"


def should_ingest_linkedin_post(
    text: str,
    *,
    author_headline: str | None = None,
    cfg: dict[str, Any] | None = None,
    llm_classify: LLMClassifyFn | None = None,
) -> tuple[bool, str]:
    """Return (ingest, reason)."""
    cfg = cfg or {}
    combined = f"{text or ''}\n{author_headline or ''}".strip()
    intent = classify_post_intent(combined)

    if intent == "job_seeker":
        return False, "job_seeker_post"

    if intent == "hiring":
        return True, "hiring_intent"

    if intent == "noise":
        return False, "no_hiring_intent"

    # ambiguous — optional LLM
    if cfg.get("llm_intent_classify_enabled") and llm_classify:
        llm_intent = llm_classify(combined, author_headline)
        if llm_intent == "hiring":
            return True, "llm_hiring"
        if llm_intent == "job_seeker":
            return False, "llm_job_seeker"
        return False, "llm_noise"

    if cfg.get("allow_role_keyword_ingest", False) and ROLE_KEYWORD_RE.search(combined):
        return True, "role_keyword_legacy"

    return False, "no_hiring_intent"


def classify_linkedin_post_filter(
    text: str,
    salary_usd: str | None,
    cfg: dict[str, Any],
    *,
    author_headline: str | None = None,
    post_intent: str | None = None,
) -> PostFilterResult:
    """Map post text + salary to filter_result for registry jobs."""
    combined = f"{text or ''}\n{author_headline or ''}".strip()
    intent = post_intent or classify_post_intent(combined)

    if intent == "job_seeker":
        return PostFilterResult("skipped", "job_seeker_post", "job_seeker", False)

    if intent == "noise" or intent == "ambiguous":
        reason = "no_hiring_intent" if intent == "noise" else "ambiguous_post"
        return PostFilterResult("skipped", reason, intent, False)

    if cfg.get("require_usd_salary", False):
        if salary_usd:
            return PostFilterResult("eligible", None, intent, True)
        default = cfg.get("posts_default_filter_result", "needs_review")
        return PostFilterResult(default, "no_usd_salary_in_post", intent, True)

    if salary_usd:
        return PostFilterResult("eligible", None, intent, True)

    return PostFilterResult(
        cfg.get("posts_default_filter_result", "needs_review"),
        "no_usd_salary_in_post",
        intent,
        True,
    )
