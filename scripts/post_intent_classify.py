"""Optional LLM classifier for borderline LinkedIn posts (cached, cheap model)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "state" / "post-intent-cache.json"

VALID_INTENTS = frozenset({"hiring", "job_seeker", "noise", "ambiguous"})

SYSTEM_PROMPT = """You classify LinkedIn feed posts for a job-search pipeline.
Reply with exactly one word: hiring, job_seeker, noise, or ambiguous.

- hiring: a company/recruiter is advertising open roles or asking candidates to apply
- job_seeker: the author is looking for work, open to opportunities, or not a recruiter
- noise: unrelated content, celebrations, product promos, no job involved
- ambiguous: mentions a role but unclear if hiring or seeking"""


def _cache_key(text: str) -> str:
    digest = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
    return digest[:24]


def load_cache() -> dict[str, str]:
    if not CACHE_PATH.exists():
        return {}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in (data.get("entries") or {}).items()}
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(entries: dict[str, str]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps({"entries": entries}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _normalize_intent(raw: str) -> str | None:
    val = (raw or "").strip().lower()
    val = re.sub(r"[^a-z_]", "", val.replace("-", "_"))
    if val in VALID_INTENTS:
        return val
    aliases = {
        "recruiter": "hiring",
        "candidate": "job_seeker",
        "seeker": "job_seeker",
        "jobseeker": "job_seeker",
        "promo": "noise",
        "unknown": "ambiguous",
    }
    return aliases.get(val)


def classify_with_openai(
    text: str,
    *,
    model: str = "gpt-4o-mini",
    api_key: str | None = None,
) -> str | None:
    key = api_key or os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return None

    snippet = text[:2000]
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Post text:\n\n{snippet}"},
        ],
        "temperature": 0,
        "max_tokens": 8,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        return _normalize_intent(content)
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError, IndexError):
        return None


def classify_post_llm(
    text: str,
    author_headline: str | None = None,
    *,
    cfg: dict[str, Any] | None = None,
    use_cache: bool = True,
) -> str | None:
    """Classify with cache + optional OpenAI. Returns intent or None if disabled/unavailable."""
    cfg = cfg or {}
    if not cfg.get("llm_intent_classify_enabled"):
        return None

    combined = f"{text or ''}\n{author_headline or ''}".strip()
    if not combined:
        return None

    key = _cache_key(combined)
    cache = load_cache() if use_cache else {}
    if key in cache:
        return cache.get(key)

    model = str(cfg.get("llm_intent_model") or "gpt-4o-mini")
    intent = classify_with_openai(combined, model=model)
    if intent and use_cache:
        cache[key] = intent
        save_cache(cache)
    return intent


def make_llm_classify_fn(cfg: dict[str, Any]):
    """Factory for post_intent.should_ingest_linkedin_post llm_classify callback."""

    def _fn(text: str, author_headline: str | None) -> str | None:
        return classify_post_llm(text, author_headline, cfg=cfg)

    return _fn
