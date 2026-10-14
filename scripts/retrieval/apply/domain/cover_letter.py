"""Generate a cover letter at apply time and reject it unless guardrails pass.

Disabled unless the track email config sets ``cover_letter.enabled``. A letter
that fails the invention check (G4) is never injected. Other failures can use
the track's short template when ``allow_fallback`` is true.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Never

from retrieval._paths import ROOT

from audit_log import info as audit_info
from audit_log import warn as audit_warn
from registry import job_key
from track_store import load_email_config, load_profile

Channel = Literal["email", "form", "linkedin"]

_DEFAULT_CHANNELS = {"email": True, "form": False, "linkedin": False}
_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "auto_inject": True,
    "max_words": 220,
    "min_words": 120,
    "quality_threshold": 0.7,
    "allow_fallback": True,
    "language": "auto",
    "model": "gpt-4o-mini",
    "channels": dict(_DEFAULT_CHANNELS),
}

_HARD_MIN_WORDS = 100
_HARD_MAX_WORDS = 280
_FALLBACK_MAX_WORDS = 80
_MAX_HTTP_RETRIES = 2
_DESCRIPTION_LIMIT = 1500

_CLICHES = (
    "i am writing to apply",
    "i am a passionate",
    "i believe i would be a great fit",
    "as per my resume",
    "i am excited to apply",
)

_FALLBACK_TEMPLATE = (
    "Hi,\n\n"
    "I am applying for the {role} role at {company}. "
    "My background is {current_title}. "
    "I am available to discuss next steps.\n"
)

_STOP = frozenset(
    {
        "about", "after", "again", "also", "and", "are", "been", "being", "with",
        "from", "have", "that", "this", "your", "their", "them", "then", "than",
        "into", "over", "such", "some", "what", "when", "where", "which", "while",
        "will", "would", "could", "should", "there", "here", "just", "more", "most",
        "other", "only", "very", "role", "team", "work", "working", "years", "year",
        "para", "como", "uma", "com", "que", "não", "nao", "por", "dos", "das",
        "the", "for", "you", "our", "was", "were", "has", "had", "its", "but",
        "not", "can", "all", "any", "who", "how", "out", "use", "using", "used",
        "hello", "thank", "thanks", "available", "discuss", "next", "steps",
    }
)

_EN_MARKERS = frozenset(
    {"the", "and", "with", "for", "this", "your", "experience", "available", "team", "role"}
)
_PT_MARKERS = frozenset(
    {
        "não", "nao", "você", "voce", "experiência", "experiencia", "vaga",
        "gostaria", "obrigado", "obrigada", "equipe", "disponível", "disponivel",
        "sobre", "minha",
    }
)

_ORG_RE = re.compile(
    r"\b(?:at|with|for|from)\s+([A-Z][A-Za-z0-9&.'’\-]+(?:\s+[A-Z][A-Za-z0-9&.'’\-]+){0,3})"
)
_TITLE_RE = re.compile(
    r"\b(?:as an?|i am an?|i'm an?|worked as an?)\s+([A-Za-z][A-Za-z0-9 /+\-]{2,48})"
)
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_CLOSING_RE = re.compile(
    r"\b(available|regards|thank|thanks|sincerely|next steps|discuss|"
    r"dispon[ií]vel|obrigad[oa]|atenciosamente)\b",
    re.IGNORECASE,
)
_SENTENCE_RE = re.compile(r"[.!?]+")
_WORD_RE = re.compile(r"\b[\w']+\b", re.UNICODE)
_TAG_RE = re.compile(r"<[^>]+>")


def cover_settings(cfg: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict((cfg or {}).get("cover_letter") or {})
    channels = dict(_DEFAULT_CHANNELS)
    channels.update(raw.get("channels") or {})
    merged = dict(_DEFAULTS)
    merged.update(raw)
    merged["channels"] = channels
    merged["enabled"] = bool(merged["enabled"])
    merged["auto_inject"] = bool(merged["auto_inject"])
    merged["allow_fallback"] = bool(merged["allow_fallback"])
    merged["min_words"] = int(merged["min_words"])
    merged["max_words"] = int(merged["max_words"])
    merged["quality_threshold"] = float(merged["quality_threshold"])
    merged["language"] = str(merged["language"] or "auto").strip().lower()
    merged["model"] = str(merged["model"] or "gpt-4o-mini")
    return merged


def word_count(text: str) -> int:
    return len(_WORD_RE.findall(text or ""))


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", text or "")).strip()


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[,;\n]", value) if part.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _profile_blob(profile: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in profile.items():
        if str(key).startswith("_"):
            continue
        if isinstance(value, list):
            parts.extend(_as_list(value))
        elif isinstance(value, str):
            parts.append(value)
    return "\n".join(parts)


def track_summary(profile: dict[str, Any]) -> str:
    """Build the labeled profile text inserted into the cover-letter prompt.

    Reads full_name, current_title, years_experience, ai_experience_summary,
    skills, and achievements from profile. The summary is flattened to plain
    text. Skills are comma-separated and achievements semicolon-separated.
    Empty fields are omitted. Returns the remaining lines joined by newlines.
    """
    lines = [
        f"Name: {profile.get('full_name') or ''}".strip(),
        f"Title: {profile.get('current_title') or ''}".strip(),
        f"Years: {profile.get('years_experience') or ''}".strip(),
        f"Summary: {_plain(str(profile.get('ai_experience_summary') or ''))}",
    ]
    skills = _as_list(profile.get("skills"))
    if skills:
        lines.append("Skills: " + ", ".join(skills))
    achievements = _as_list(profile.get("achievements"))
    if achievements:
        lines.append("Achievements: " + "; ".join(achievements))
    return "\n".join(line for line in lines if not line.endswith(":"))


def _content_tokens(text: str, *, min_len: int = 4) -> set[str]:
    tokens = set()
    for match in re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9+\-]{%d,}" % (min_len - 1), text or ""):
        token = match.lower()
        if token not in _STOP:
            tokens.add(token)
    return tokens


def _profile_tokens(profile: dict[str, Any]) -> set[str]:
    tokens = _content_tokens(_profile_blob(profile))
    for skill in _as_list(profile.get("skills")):
        lowered = skill.lower()
        if len(lowered) >= 3:
            tokens.add(lowered)
    return tokens


def _mentions(text: str, token: str) -> bool:
    return re.search(rf"\b{re.escape(token)}\b", text or "", re.IGNORECASE) is not None


def _numbers(text: str) -> set[str]:
    found: set[str] = set()
    for match in _NUMBER_RE.findall(text or ""):
        raw = match.replace(",", "")
        found.add(raw)
        if "." in raw:
            found.add(raw.rstrip("0").rstrip("."))
    return {item for item in found if item}


def _phrase_grounded(phrase: str, blob: str) -> bool:
    words = [
        word
        for word in re.findall(r"[A-Za-z][A-Za-z0-9+\-]{2,}", phrase.lower())
        if word not in _STOP
    ]
    if not words:
        return True
    return all(_mentions(blob, word) for word in words)


def _job_fields(job: dict[str, Any]) -> tuple[str, str, str]:
    title = str(job.get("role") or job.get("title") or "").strip()
    company = str(job.get("company") or "").strip()
    description = _plain(str(job.get("description") or job.get("description_snippet") or ""))
    return title, company, description[:_DESCRIPTION_LIMIT]


def detect_language(text: str) -> str:
    tokens = re.findall(r"[A-Za-zÀ-ÿ']+", (text or "").lower())
    english = sum(1 for token in tokens if token in _EN_MARKERS)
    portuguese = sum(1 for token in tokens if token in _PT_MARKERS)
    if portuguese >= 2 and portuguese > english:
        return "pt"
    if english >= 2 and english > portuguese:
        return "en"
    return "en"


def expected_language(job: dict[str, Any], settings: dict[str, Any]) -> str:
    pref = settings.get("language") or "auto"
    if pref in {"en", "pt"}:
        return pref
    _title, _company, description = _job_fields(job)
    if description:
        return detect_language(description)
    return "en"


def _bounds(settings: dict[str, Any]) -> tuple[int, int]:
    low = max(_HARD_MIN_WORDS, int(settings["min_words"]))
    high = min(_HARD_MAX_WORDS, int(settings["max_words"]))
    if low > high:
        low, high = _HARD_MIN_WORDS, _HARD_MAX_WORDS
    return low, high


def validate_cover_letter(
    text: str,
    profile: dict[str, Any],
    job: dict[str, Any],
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run G1–G8. G6 is a heuristic score, not a second model call."""
    settings = settings or cover_settings({})
    letter = (text or "").strip()
    failed: list[str] = []
    reasons: list[str] = []
    blob = _profile_blob(profile)
    title, company, description = _job_fields(job)
    low, high = _bounds(settings)

    count = word_count(letter)
    if count < low or count > high:
        failed.append("G1")
        reasons.append(f"G1: {count} words, expected {low}-{high}")

    profile_hits = [token for token in _profile_tokens(profile) if _mentions(letter, token)]
    if not profile_hits:
        failed.append("G2")
        reasons.append("G2: letter does not mention the track profile")

    job_tokens = _content_tokens(f"{title} {description}")
    job_hits = [token for token in job_tokens if _mentions(letter, token)]
    company_hit = bool(company) and company.casefold() in letter.casefold()
    if not job_hits and not company_hit:
        failed.append("G3")
        reasons.append("G3: letter does not reference the job")

    allowed_numbers = _numbers(blob)
    invented_numbers = sorted(_numbers(letter) - allowed_numbers)
    if invented_numbers:
        failed.append("G4")
        reasons.append("G4: number not in track: " + ", ".join(invented_numbers))

    for match in _ORG_RE.finditer(letter):
        org = match.group(1).strip()
        org_cf = org.casefold()
        company_cf = company.casefold()
        grounded = org_cf in blob.casefold() or (company_cf and (org_cf in company_cf or company_cf in org_cf))
        if not grounded:
            failed.append("G4")
            reasons.append(f"G4: organization not in track: {org}")
            break

    if "G4" not in failed:
        for match in _TITLE_RE.finditer(letter):
            phrase = match.group(1).strip(" .")
            if not _phrase_grounded(phrase, blob):
                failed.append("G4")
                reasons.append(f"G4: title not in track: {phrase}")
                break

    lowered = letter.lower()
    for phrase in _CLICHES:
        if phrase in lowered:
            failed.append("G5")
            reasons.append(f"G5: cliche: {phrase}")
            break

    language = expected_language(job, settings)
    if letter and detect_language(letter) != language:
        failed.append("G7")
        reasons.append(f"G7: expected {language}")

    sentences = [part for part in _SENTENCE_RE.split(letter) if part.strip()]
    last_words = " ".join(letter.split()[-60:])
    if len(sentences) < 3 or not _CLOSING_RE.search(last_words):
        failed.append("G8")
        reasons.append("G8: missing opening, body, or closing")

    specific_job_hits = [token for token in job_hits if token not in _content_tokens(company)]
    score = 0.0
    if low <= count <= high:
        score += 0.25
    if len(profile_hits) >= 2:
        score += 0.35
    elif len(profile_hits) == 1:
        score += 0.15
    if specific_job_hits or (not description and (job_hits or company_hit)):
        score += 0.2
    elif company_hit or job_hits:
        score += 0.1
    if 4 <= len(sentences) <= 12 and "G8" not in failed:
        score += 0.2
    score = round(min(score, 1.0), 2)
    threshold = float(settings["quality_threshold"])
    if score < threshold:
        failed.append("G6")
        reasons.append(f"G6: score {score} below {threshold}")

    # Preserve first-seen order while dropping repeats.
    ordered: list[str] = []
    for check_id in failed:
        if check_id not in ordered:
            ordered.append(check_id)

    return {
        "passed": not ordered,
        "failed_checks": ordered,
        "quality_score": score,
        "reasons": reasons,
    }


def fallback_text(profile: dict[str, Any], job: dict[str, Any]) -> str:
    template = str(profile.get("cover_letter_default") or _FALLBACK_TEMPLATE).strip() or _FALLBACK_TEMPLATE
    title, company, _description = _job_fields(job)
    values = {
        "role": title or "the role",
        "company": company or "the company",
        "current_title": str(profile.get("current_title") or "my field"),
    }
    try:
        text = template.format(**values)
    except (KeyError, IndexError, ValueError):
        text = template
        for key, value in values.items():
            text = text.replace("{" + key + "}", value)
    words = text.split()
    if len(words) > _FALLBACK_MAX_WORDS:
        text = " ".join(words[:_FALLBACK_MAX_WORDS])
    return text.strip()


def build_prompt(
    profile: dict[str, Any],
    job: dict[str, Any],
    settings: dict[str, Any],
    *,
    language: str,
) -> str:
    title, company, description = _job_fields(job)
    low, high = _bounds(settings)
    lang_line = "Write in English." if language == "en" else "Escreva em português."
    return (
        f"Write a professional cover letter between {low} and {high} words.\n\n"
        "Required rules:\n"
        "- Use only facts from the profile. Do not invent experience, numbers, employers, or titles.\n"
        "- Mention one or two concrete facts from the profile.\n"
        "- Relate the letter to at least one aspect of the job.\n"
        "- Avoid generic openings such as 'I am writing to apply' or 'I am a passionate'.\n"
        "- Direct, confident tone.\n"
        "- End with a short sentence about availability.\n"
        f"- {lang_line}\n"
        "- Plain text. No subject line. No markdown.\n\n"
        f"Profile:\n{track_summary(profile)}\n\n"
        f"Job:\n{title} at {company}\n{description}\n"
    )


def _strip_model_text(raw: str) -> str:
    text = (raw or "").strip()
    fence = re.match(r"^```(?:\w+)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    text = re.sub(r"^subject:.*\n", "", text, count=1, flags=re.IGNORECASE)
    return text.strip()


def chat_completion(prompt: str, *, model: str, api_key: str | None = None) -> str | None:
    key = (api_key or os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You write concise, factual cover letters."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 700,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    for attempt in range(_MAX_HTTP_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            text = _strip_model_text(str(content))
            return text or None
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < _MAX_HTTP_RETRIES:
                time.sleep(min(2**attempt, 8))
                continue
            return None
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt < _MAX_HTTP_RETRIES:
                time.sleep(min(2**attempt, 8))
                continue
            return None
        except (json.JSONDecodeError, KeyError, IndexError):
            return None
    return None


def _cache_path(root: Path) -> Path:
    return root / "state" / "cover-letter-cache.json"


def _log_path(root: Path) -> Path:
    return root / "state" / "cover-letters.json"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _cache_key(prompt: str, model: str) -> str:
    digest = hashlib.sha256(f"{model}\n{prompt}".encode("utf-8")).hexdigest()
    return digest[:24]


def _empty_decision(
    *,
    model: str,
    failed: list[str],
    reasons: list[str],
    text: str = "",
    rejected_text: str = "",
    used_fallback: bool = False,
    injected: bool = False,
    passed: bool = False,
    score: float = 0.0,
) -> dict[str, Any]:
    return {
        "text": text,
        "rejected_text": rejected_text,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "passed_guardrails": passed,
        "failed_checks": failed,
        "reasons": reasons,
        "quality_score": score,
        "used_fallback": used_fallback,
        "injected": injected,
    }


def _channel_open(settings: dict[str, Any], channel: Channel) -> bool:
    if channel == "linkedin":
        return False
    if channel == "email":
        return bool(settings["channels"].get("email", True))
    if channel == "form":
        return bool(settings["channels"].get("form", False))
    unexpected: Never = channel
    return unexpected


def _decide(
    generated: str | None,
    *,
    profile: dict[str, Any],
    job: dict[str, Any],
    settings: dict[str, Any],
    channel: Channel,
) -> dict[str, Any]:
    model = str(settings["model"])
    if not generated:
        verdict = {
            "passed": False,
            "failed_checks": ["LLM"],
            "quality_score": 0.0,
            "reasons": ["LLM: generation failed"],
        }
    else:
        verdict = validate_cover_letter(generated, profile, job, settings)

    passed = bool(verdict["passed"])
    failed = list(verdict["failed_checks"])
    critical = "G4" in failed
    can_inject = settings["auto_inject"] and _channel_open(settings, channel)
    if passed and not critical:
        text = generated or ""
        injected = bool(can_inject and text)
        used_fallback = False
        rejected = ""
    elif settings["allow_fallback"] and can_inject:
        text = fallback_text(profile, job)
        injected = bool(text)
        used_fallback = True
        rejected = generated or ""
    else:
        text = ""
        injected = False
        used_fallback = False
        rejected = generated or ""

    if critical and generated and text == generated:
        text = ""
        injected = False

    return _empty_decision(
        model=model,
        failed=failed,
        reasons=list(verdict["reasons"]),
        text=text,
        rejected_text=rejected if text != generated else "",
        used_fallback=used_fallback,
        injected=injected,
        passed=passed,
        score=float(verdict["quality_score"]),
    )


def _persist(root: Path, key: str, decision: dict[str, Any]) -> None:
    path = _log_path(root)
    data = _read_json(path)
    entries = data.get("entries")
    if not isinstance(entries, dict):
        entries = {}
    entries[key] = decision
    data["entries"] = entries
    _write_json(path, data)


def _audit(decision: dict[str, Any], *, key: str, channel: Channel) -> None:
    payload = {
        "job_key": key,
        "channel": channel,
        "passed_guardrails": decision["passed_guardrails"],
        "failed_checks": decision["failed_checks"],
        "reasons": decision["reasons"],
        "quality_score": decision["quality_score"],
        "used_fallback": decision["used_fallback"],
        "injected": decision["injected"],
        "model": decision["model"],
    }
    if decision["passed_guardrails"] and decision["injected"]:
        audit_info("cover_letter", "accepted", **payload)
        return
    if decision["used_fallback"]:
        audit_warn("cover_letter", "fallback", **payload)
        return
    audit_warn("cover_letter", "rejected", **payload)


def prepare_for_channel(
    job: dict[str, Any],
    *,
    channel: Channel,
    email_cfg: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    track_id: str | None = None,
    root: Path | None = None,
    complete_fn: Any = None,
) -> dict[str, Any] | None:
    """Generate, validate, and optionally fall back. Returns None when disabled."""
    cfg = email_cfg if email_cfg is not None else load_email_config(track_id or job.get("track"))
    settings = cover_settings(cfg)
    if not settings["enabled"]:
        return None
    if channel == "linkedin" or not _channel_open(settings, channel):
        audit_warn("cover_letter", "channel_blocked", channel=channel, reason="channel_disabled")
        return None

    tid = track_id or job.get("track")
    person = profile if profile is not None else load_profile(tid)
    base = root or ROOT
    language = expected_language(job, settings)
    prompt = build_prompt(person, job, settings, language=language)
    model = str(settings["model"])
    cache_file = _cache_path(base)
    cache = _read_json(cache_file)
    cache_entries = cache.get("entries") if isinstance(cache.get("entries"), dict) else {}
    key = _cache_key(prompt, model)
    cached = cache_entries.get(key) if isinstance(cache_entries, dict) else None

    generated: str | None = None
    if isinstance(cached, dict) and cached.get("passed_guardrails") and cached.get("text"):
        generated = str(cached["text"])
    else:
        complete = complete_fn or chat_completion
        generated = complete(prompt, model=model)
        if generated:
            verdict = validate_cover_letter(generated, person, job, settings)
            if "G7" in verdict["failed_checks"] and "G4" not in verdict["failed_checks"]:
                retry_prompt = prompt + f"\nThe letter must be entirely in '{language}'.\n"
                retried = complete(retry_prompt, model=model)
                if retried:
                    retry_verdict = validate_cover_letter(retried, person, job, settings)
                    if len(retry_verdict["failed_checks"]) <= len(verdict["failed_checks"]):
                        generated = retried

    decision = _decide(generated, profile=person, job=job, settings=settings, channel=channel)
    if decision["passed_guardrails"] and decision["text"] and not decision["used_fallback"]:
        cache_entries[key] = {"text": decision["text"], "passed_guardrails": True, "model": model}
        _write_json(cache_file, {"entries": cache_entries})

    record_key = job_key(job)
    _persist(base, record_key, decision)
    _audit(decision, key=record_key, channel=channel)
    return decision


def overlay_form_cover(
    profile: dict[str, Any],
    job: dict[str, Any],
    *,
    track_id: str | None = None,
    email_cfg: dict[str, Any] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Replace the static form cover when the form channel is enabled."""
    decision = prepare_for_channel(
        job,
        channel="form",
        email_cfg=email_cfg,
        profile=profile,
        track_id=track_id,
        root=root,
    )
    if not decision or not decision.get("injected") or not decision.get("text"):
        return profile
    updated = dict(profile)
    updated["cover_letter_default"] = str(decision["text"])
    return updated
