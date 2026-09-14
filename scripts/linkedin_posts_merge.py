#!/usr/bin/env python3
"""Merge LinkedIn post search results (JSON) into job-search registry and run file."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from filters import (  # noqa: E402
    evaluate_job,
    has_usd_salary,
    is_blacklisted_url,
    salary_sort_value,
    sort_jobs_by_salary,
)
from registry import (  # noqa: E402
    LOCAL_TZ,
    REGISTRY_PATH,
    RUNS_DIR,
    job_key,
    load_json,
    load_registry,
    merge_jobs,
    parse_posted_at,
    parse_since,
    save_json,
    save_registry,
)

RELATIVE_POSTED_RE = re.compile(
    r"(?:(?P<now>now)|(?P<num>\d+)\s*(?P<unit>m|h|d|w|mo))\s*(?:•|\||Edited|$)",
    re.IGNORECASE,
)

CONFIG_PATH = ROOT / "linkedin-posts-config.json"
LINKEDIN_STATE_PATH = ROOT / "state" / "linkedin-last-run.json"
LOGIN_SCRIPT = SCRIPTS / "linkedin-login.sh"
JOB_SEARCH_CONFIG = ROOT / "config.json"

from post_intent import (  # noqa: E402
    HIRING_HINTS,
    classify_linkedin_post_filter,
    should_ingest_linkedin_post,
)
from post_intent_classify import make_llm_classify_fn  # noqa: E402
APPLY_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
APPLY_URL = re.compile(r"https?://[^\s\)\]\"']+")
FEED_UPDATE_RE = re.compile(
    r"https?://(?:www\.)?linkedin\.com/feed/update/[^\s\)\]\"']+|"
    r"urn:li:(?:activity|share|ugcPost):[\d]+",
    re.IGNORECASE,
)
LNKD_RE = re.compile(r"https?://(?:www\.)?lnkd\.in/[A-Za-z0-9_-]+")
LINKEDIN_PROFILE_RE = re.compile(r"https://www\.linkedin\.com/in/[a-z0-9-]+/", re.IGNORECASE)
LINKEDIN_COMPANY_RE = re.compile(r"https://www\.linkedin\.com/company/[a-z0-9-]+/", re.IGNORECASE)
PLACEHOLDER_POST_URL_RE = re.compile(r"^linkedin-post:[0-9a-f]+$", re.IGNORECASE)
ACTIVITY_URN_RE = re.compile(
    r"urn(?:%3A|:)li(?:%3A|:)(activity|share|ugcPost)(?:%3A|:)(\d+)",
    re.IGNORECASE,
)
FEED_UPDATE_URL_RE = re.compile(
    r"https?://(?:www\.)?linkedin\.com/feed/update/urn:li:(activity|share|ugcPost):(\d+)/?",
    re.IGNORECASE,
)
POSTS_PERMALINK_RE = re.compile(
    r"https?://(?:[\w-]+\.)?linkedin\.com/posts/[^?\s\"']+",
    re.IGNORECASE,
)


def _abs_linkedin(path_or_url: str) -> str:
    if not path_or_url:
        return ""
    if path_or_url.startswith("http"):
        return path_or_url
    return f"https://www.linkedin.com{path_or_url}"


def _norm_author_name(name: str) -> str:
    cleaned = (name or "").strip()
    cleaned = re.sub(r"^~+\s*", "", cleaned)
    cleaned = re.sub(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.casefold()


def fallback_linkedin_post_search_url(author: str, role: str = "ai engineer") -> str:
    """Best-effort clickable URL when no permalink/profile match exists."""
    author_clean = re.sub(r"^~+\s*", "", (author or "").strip())
    author_clean = re.sub(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF]", " ", author_clean)
    author_clean = re.sub(r"\s+", " ", author_clean).strip()
    keywords = f'"{author_clean}" "{role}"' if author_clean else f'"{role}"'
    params = {
        "keywords": keywords,
        "origin": "FACETED_SEARCH",
        "sortBy": '["date_posted"]',
    }
    return "https://www.linkedin.com/search/results/content/?" + urllib.parse.urlencode(params)


def _slugify_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").casefold())


def _author_matches_profile_slug(author: str, ref_slug: str) -> bool:
    """True when a profile/post author slug aligns with the recruiter display name."""
    author_slug = _slugify_name(re.sub(r"^~+\s*", "", (author or "").strip()))
    ref_slug_norm = re.sub(r"[^a-z0-9]", "", (ref_slug or "").casefold())
    if not author_slug or not ref_slug_norm:
        return False
    if author_slug in ref_slug_norm or ref_slug_norm in author_slug:
        return True
    tokens = [t for t in re.split(r"[\s·|/]+", author) if len(t) > 2]
    if tokens:
        first = _slugify_name(tokens[0])
        last = _slugify_name(tokens[-1]) if len(tokens) > 1 else ""
        if first and first in ref_slug_norm:
            return True
        if last and last in ref_slug_norm:
            return True
    return False


def permalink_author_slug(post_url: str) -> str:
    """Extract author slug from linkedin.com/posts/{slug}_… URL."""
    match = re.search(r"linkedin\.com/posts/([a-z0-9-]+)_", (post_url or ""), re.I)
    return match.group(1).casefold() if match else ""


def permalink_matches_author(post_url: str, author: str) -> bool:
    """True when /posts/ slug aligns with recruiter/author name."""
    post_slug = permalink_author_slug(post_url)
    if not post_slug:
        return True
    author_slug = _slugify_name(re.sub(r"^~+\s*", "", (author or "").strip()))
    if not author_slug:
        return True
    if author_slug in post_slug or post_slug in author_slug:
        return True
    tokens = [t for t in re.split(r"[\s·|/]+", author) if len(t) > 2]
    if tokens:
        first = _slugify_name(tokens[0])
        last = _slugify_name(tokens[-1]) if len(tokens) > 1 else ""
        if first and first in post_slug:
            return True
        if last and last in post_slug:
            return True
    return False


def extract_post_salary(text: str, role: str = "") -> str | None:
    """Extract the best USD salary string from post text (avoids $2 from $2.1k)."""
    if not text or not has_usd_salary(text):
        return None

    role_lower = (role or "").casefold()
    if role_lower:
        for line in re.split(r"[\n\r]+", text):
            if role_lower in line.casefold() and has_usd_salary(line):
                found = _best_salary_match(line)
                if found:
                    return found

    return _best_salary_match(text)


def _best_salary_match(text: str) -> str | None:
    patterns = (
        re.compile(
            r"\$\s?(?:\d[\d,]*\.\d+\s*[kK]|\d[\d,]+\s*[kK]|\d{2,3}(?:,\d{3})+|\d{3,})"
            r"(?:\s?[-–]\s?\$?\s?(?:\d[\d,]*\.\d+\s*[kK]|\d[\d,]+\s*[kK]|\d{2,3}(?:,\d{3})+|\d{3,}))?"
            r"(?:\s*/?\s*(?:mo|mes|month|yr|year|annual))?",
            re.I,
        ),
        re.compile(
            r"USD\s?\d[\d,]*(?:\.\d+)?\s*[kK]?(?:\s?[-–]\s?USD?\s?\d[\d,]*(?:\.\d+)?\s*[kK]?)?",
            re.I,
        ),
    )
    best: str | None = None
    best_score = -1.0
    for pattern in patterns:
        for match in pattern.finditer(text):
            val = match.group(0).strip()
            score = salary_sort_value(val)
            if score > best_score:
                best_score = score
                best = val
    return best


def extract_role_apply_url(text: str, role: str) -> str:
    """Prefer apply link on the same line as the matched role (multi-job list posts)."""
    role_lower = (role or "").casefold()
    if role_lower:
        for line in re.split(r"[\n\r]+", text):
            if role_lower in line.casefold():
                lnkd = _first_lnkd_in(line)
                if lnkd:
                    return lnkd
                for match in APPLY_URL.finditer(line):
                    url = match.group(0)
                    if "linkedin.com" not in url and not is_blacklisted_url(url)[0]:
                        if not APPLY_EMAIL.match(url):
                            return url
    resolved = resolve_apply_url_from_text(text, None)
    if resolved and not APPLY_EMAIL.match(resolved):
        return resolved
    return ""


def split_apply_email(
    apply_url: str | None,
    text: str,
    role: str,
) -> tuple[str | None, str | None]:
    """Separate apply email from external apply URL."""
    from apply_email import extract_apply_email_from_text, is_email_address, normalize_email

    email = None
    url = (apply_url or "").strip()
    if is_email_address(url):
        email = normalize_email(url)
        url = ""
    if not email:
        email = extract_apply_email_from_text(text, role)
    if email and url.lower() == email:
        url = ""
    if url and APPLY_EMAIL.match(url):
        url = ""
    return email, url or None


def is_placeholder_post_url(url: str) -> bool:
    return bool(PLACEHOLDER_POST_URL_RE.match((url or "").strip()))


def is_apply_only_url(url: str) -> bool:
    url = (url or "").strip()
    if not url or is_placeholder_post_url(url):
        return False
    if "lnkd.in" in url:
        return True
    if "/jobs/view/" in url:
        return True
    if "linkedin.com" not in url:
        return True
    return False


def is_linkedin_post_url(url: str) -> bool:
    url = (url or "").strip()
    if not url:
        return False
    if is_placeholder_post_url(url) or is_apply_only_url(url):
        return False
    return "linkedin.com" in url


def is_feed_update_url(url: str) -> bool:
    return bool(FEED_UPDATE_URL_RE.search((url or "").strip()))


def is_posts_permalink(url: str) -> bool:
    return bool(POSTS_PERMALINK_RE.search((url or "").strip()))


def is_profile_fallback_url(url: str) -> bool:
    url = (url or "").strip()
    return "/recent-activity/" in url or ("/company/" in url and url.endswith("/posts/"))


def build_feed_update_url(urn_kind: str, activity_id: str) -> str:
    return f"https://www.linkedin.com/feed/update/urn:li:{urn_kind}:{activity_id}/"


def resolve_feed_update_to_posts_permalink(url: str, *, timeout: float = 15.0) -> str:
    """Resolve feed/update URL to canonical linkedin.com/posts/… permalink."""
    import subprocess

    url = (url or "").strip()
    if not url or is_posts_permalink(url):
        return url
    if not is_feed_update_url(url):
        return url

    curl = [
        "curl",
        "-sL",
        "-A",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "--max-time",
        str(int(timeout)),
        url,
    ]
    try:
        result = subprocess.run(curl, capture_output=True, text=True, check=False, timeout=timeout + 2)
    except (OSError, subprocess.TimeoutExpired):
        return url

    html = result.stdout or ""
    for pattern in (
        r'property="og:url"\s+content="([^"]+)"',
        r'rel="canonical"\s+href="([^"]+)"',
    ):
        match = re.search(pattern, html)
        if not match:
            continue
        location = match.group(1).split("?")[0]
        if "/posts/" not in location:
            continue
        location = re.sub(r"https://[\w-]+\.linkedin\.com", "https://www.linkedin.com", location)
        return location if location.endswith("/") else f"{location}/"

    for line in (result.stderr or "").splitlines():
        if line.lower().startswith("location:"):
            location = line.split(":", 1)[1].strip().split("?")[0]
            if "/posts/" in location:
                location = re.sub(r"https://[\w-]+\.linkedin\.com", "https://www.linkedin.com", location)
                return location if location.endswith("/") else f"{location}/"

    return url


def _author_map_key(author: str) -> str:
    return _norm_author_name(author)


def _html_post_matches_author(author: str, html_post: dict[str, Any]) -> bool:
    author_key = _author_map_key(author)
    if not author_key:
        return False
    ha = _author_map_key(html_post.get("author") or "")
    if ha and (ha == author_key or ha in author_key or author_key in ha):
        return True
    slug = (html_post.get("author_slug") or "").strip()
    return bool(slug and _author_matches_profile_slug(author, slug))


def _closest_link_slug(text: str, pos: int, pattern: re.Pattern[str], *, before: int = 500, after: int = 1200) -> str:
    """Return slug of the profile/company link nearest to ``pos`` in HTML."""
    window = text[max(0, pos - before) : pos + after]
    offset = max(0, pos - before)
    best_slug = ""
    best_dist = 10**9
    for link in pattern.finditer(window):
        dist = abs((offset + link.start()) - pos)
        if dist < best_dist:
            best_dist = dist
            best_slug = link.group(0).rstrip("/").split("/")[-1]
    return best_slug


def _author_name_near_urn(text: str, pos: int) -> str:
    """Extract display name from HTML immediately around a URN marker."""
    window_before = text[max(0, pos - 700) : pos]
    window_after = text[pos : pos + 500]
    author_patterns = (
        r'update-components-actor__title[^>]*>\s*<span[^>]*>([^<]{2,100})',
        r'feed-shared-actor__name[^>]*>([^<]{2,100})',
        r'aria-label="([^"]{2,100}?)\s*•',
        r'<strong[^>]*>([^<]{2,100})</strong>',
    )
    skip = {"follow", "connect", "like", "comment", "share"}
    for author_pat in author_patterns:
        author_m = re.search(author_pat, window_after, re.I | re.S)
        if not author_m:
            matches = list(re.finditer(author_pat, window_before, re.I | re.S))
            author_m = matches[-1] if matches else None
        if not author_m:
            continue
        author = re.sub(r"\s+", " ", author_m.group(1)).strip()
        if author.lower() not in skip:
            return author
    return ""


def extract_feed_posts_from_html(html: str) -> list[dict[str, Any]]:
    """Extract feed post cards from search HTML as author + feed/update URL pairs."""
    posts: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    text = html or ""

    patterns = (
        r'data-urn="(urn:li:(?:activity|share|ugcPost):\d+)"',
        r'"entityUrn"\s*:\s*"(urn:li:(?:activity|share|ugcPost):\d+)"',
        r'"activityUrn"\s*:\s*"(urn:li:(?:activity|share|ugcPost):\d+)"',
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            urn = match.group(1)
            urn_m = re.search(r"urn:li:(activity|share|ugcPost):(\d+)", urn, re.I)
            if not urn_m:
                continue
            act_id = urn_m.group(2)
            if act_id in seen_ids:
                continue
            seen_ids.add(act_id)
            pos = match.start()
            author_slug = _closest_link_slug(text, pos, LINKEDIN_PROFILE_RE)
            if not author_slug:
                author_slug = _closest_link_slug(text, pos, LINKEDIN_COMPANY_RE)
            author = _author_name_near_urn(text, pos)
            posts.append(
                {
                    "kind": "feed_post",
                    "author": author,
                    "author_slug": author_slug,
                    "url": build_feed_update_url(urn_m.group(1).lower(), act_id),
                    "activity_id": act_id,
                    "urn_kind": urn_m.group(1).lower(),
                }
            )
    return posts


def harvest_feed_posts_from_network_body(body: str) -> list[dict[str, Any]]:
    """Extract activity URNs + nearby actor names from LinkedIn voyager/graphql JSON."""
    posts: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    if not body or len(body) > 5_000_000:
        return posts
    skip_names = {"like", "comment", "share", "follow", "repost", "send", "true", "false"}
    for match in re.finditer(r'"entityUrn"\s*:\s*"(urn:li:(?:activity|share|ugcPost):\d+)"', body):
        urn = match.group(1)
        urn_m = re.search(r"urn:li:(activity|share|ugcPost):(\d+)", urn, re.I)
        if not urn_m:
            continue
        act_id = urn_m.group(2)
        if act_id in seen_ids:
            continue
        seen_ids.add(act_id)
        window = body[max(0, match.start() - 3000) : match.start() + 800]
        author = ""
        for name_m in re.finditer(r'"text"\s*:\s*"([^"\\]{2,120})"', window):
            candidate = re.sub(r"\s+", " ", name_m.group(1)).strip()
            if not candidate or candidate.lower() in skip_names:
                continue
            if any(x in candidate.lower() for x in ("urn:li", "http://", "https://", "• edited")):
                continue
            author = candidate
            break
        posts.append(
            {
                "kind": "feed_post",
                "author": author,
                "author_slug": "",
                "url": build_feed_update_url(urn_m.group(1).lower(), act_id),
                "activity_id": act_id,
                "urn_kind": urn_m.group(1).lower(),
            }
        )
    return posts


def register_author_post_urls(
    author_url_map: dict[str, str],
    html_posts: list[dict[str, Any]],
) -> None:
    """Merge html/network post cards into author → feed/update map."""
    for hp in html_posts:
        url = (hp.get("url") or "").strip()
        if not url:
            continue
        author = (hp.get("author") or "").strip()
        if author:
            author_url_map[_author_map_key(author)] = url
        slug = (hp.get("author_slug") or "").strip().lower()
        if slug:
            author_url_map.setdefault(f"slug:{slug}", url)


def resolve_author_post_url(
    author: str,
    *,
    html_posts: list[dict[str, Any]] | None = None,
    author_url_map: dict[str, str] | None = None,
    profile_refs: list[dict[str, Any]] | None = None,
    activity_refs: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """Best-effort post URL for one author using maps and visible HTML cards."""
    html_posts = html_posts or []
    author_url_map = author_url_map or {}
    profile_refs = profile_refs or []
    activity_refs = activity_refs or []

    key = _author_map_key(author)
    if key and author_url_map.get(key):
        return author_url_map[key], "author_map"

    prof = lookup_author_profile_ref(author, profile_refs)
    if prof:
        slug = prof.get("url", "").rstrip("/").split("/")[-1].lower()
        if slug and author_url_map.get(f"slug:{slug}"):
            return author_url_map[f"slug:{slug}"], "author_map_slug"

    for hp in html_posts:
        if _html_post_matches_author(author, hp) and hp.get("url"):
            return hp["url"], "html_card_author"

    matched_url, matched_source = match_author_activity_ref(author, activity_refs + html_posts)
    if matched_url:
        return matched_url, matched_source

    if prof:
        slug = prof.get("url", "").rstrip("/").split("/")[-1]
        for hp in html_posts:
            if hp.get("author_slug") == slug and hp.get("url"):
                return hp["url"], "html_card_slug"

    return "", ""


def extract_ordered_feed_update_urls(html: str) -> list[str]:
    """Extract feed/update (or /posts/) URLs from HTML in DOM order, deduped."""
    hits: list[tuple[int, str]] = []
    text = html or ""

    for match in FEED_UPDATE_URL_RE.finditer(text):
        url = match.group(0).split("?")[0]
        if not url.endswith("/"):
            url += "/"
        hits.append((match.start(), url))

    for match in ACTIVITY_URN_RE.finditer(text):
        hits.append((match.start(), build_feed_update_url(match.group(1).lower(), match.group(2))))

    for match in re.finditer(
        r'"(?:activityUrn|updateUrn|shareUrn)"\s*:\s*"(urn:li:(?:activity|share|ugcPost):\d+)"',
        text,
        re.I,
    ):
        urn_match = re.search(r"urn:li:(activity|share|ugcPost):(\d+)", match.group(1), re.I)
        if urn_match:
            hits.append(
                (
                    match.start(),
                    build_feed_update_url(urn_match.group(1).lower(), urn_match.group(2)),
                )
            )

    for match in re.finditer(r'data-urn="(urn:li:(?:activity|share|ugcPost):\d+)"', text, re.I):
        urn_match = re.search(r"urn:li:(activity|share|ugcPost):(\d+)", match.group(1), re.I)
        if urn_match:
            hits.append(
                (
                    match.start(),
                    build_feed_update_url(urn_match.group(1).lower(), urn_match.group(2)),
                )
            )

    for match in POSTS_PERMALINK_RE.finditer(text):
        url = match.group(0).split("?")[0]
        if not url.endswith("/"):
            url += "/"
        hits.append((match.start(), url))

    hits.sort(key=lambda item: item[0])
    ordered: list[str] = []
    seen: set[str] = set()
    for _, url in hits:
        if url in seen:
            continue
        seen.add(url)
        ordered.append(url)
    return ordered


def extract_activity_refs_from_html(html: str) -> list[dict[str, Any]]:
    """Extract feed activity URNs (incl. URL-encoded) and nearby author slugs from search HTML."""
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in ACTIVITY_URN_RE.finditer(html or ""):
        activity_id = match.group(2)
        if activity_id in seen:
            continue
        seen.add(activity_id)
        urn_kind = match.group(1).lower()
        window = html[max(0, match.start() - 5000) : match.start() + 5000]
        author_slug = ""
        author_kind = ""
        person = LINKEDIN_PROFILE_RE.search(window)
        if person:
            author_slug = person.group(0).rstrip("/").split("/")[-1]
            author_kind = "person"
        else:
            company = LINKEDIN_COMPANY_RE.search(window)
            if company:
                author_slug = company.group(0).rstrip("/").split("/")[-1]
                author_kind = "company"
        posts_match = re.search(r"https://www\.linkedin\.com/posts/[^\"\\?\s]+", window)
        feed_url = build_feed_update_url(urn_kind, activity_id)
        refs.append(
            {
                "kind": "feed_post",
                "url": posts_match.group(0).split("?")[0] if posts_match else feed_url,
                "text": author_slug,
                "activity_id": activity_id,
                "urn_kind": urn_kind,
                "author_slug": author_slug,
                "author_kind": author_kind,
            }
        )
    return refs


def match_author_feed_post_ref(author: str, refs: list[dict[str, Any]]) -> tuple[str, str]:
    """Match author to a feed_post ref (activity permalink)."""
    author_key = _norm_author_name(author)
    if not author_key or author_key == "unknown":
        return "", ""

    for ref in refs:
        if ref.get("kind") != "feed_post" or not ref.get("url"):
            continue
        url = (ref.get("url") or "").strip()
        if is_profile_fallback_url(url):
            continue
        ref_slug = ref.get("author_slug") or ref.get("text") or ""
        if _author_matches_profile_slug(author, ref_slug):
            return url, "feed_post_slug"

    for ref in refs:
        if ref.get("kind") != "feed_post" or not ref.get("url"):
            continue
        url = (ref.get("url") or "").strip()
        if is_profile_fallback_url(url):
            continue
        title = (ref.get("text") or "").strip()
        if title and title.lower() in author_key:
            return url, "feed_post_title"

    return "", ""


def lookup_author_profile_ref(author: str, refs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the person/company profile ref that best matches ``author``."""
    author_key = _norm_author_name(author)
    if not author_key or author_key == "unknown":
        return None

    best: dict[str, Any] | None = None
    best_score = 0
    for ref in refs:
        if ref.get("kind") not in {"person", "company"} or not ref.get("url"):
            continue
        slug = ref.get("url", "").rstrip("/").split("/")[-1]
        ref_name = _norm_author_name(ref.get("text") or "")
        score = 0
        if ref_name and (ref_name in author_key or author_key in ref_name):
            score = 3
        elif _author_matches_profile_slug(author, slug):
            score = 2
        elif ref_name and ref_name.split()[0] == author_key.split()[0]:
            score = 1
        if score > best_score:
            best_score = score
            best = ref
    return best if best_score > 0 else None


def match_author_activity_ref(author: str, refs: list[dict[str, Any]]) -> tuple[str, str]:
    """Match author to a specific post URL (feed/update or /posts/) — never profile activity."""
    feed_url, feed_source = match_author_feed_post_ref(author, refs)
    if feed_url:
        return feed_url, feed_source

    if not _norm_author_name(author) or _norm_author_name(author) == "unknown":
        return "", ""

    profile = lookup_author_profile_ref(author, refs)
    profile_slug = ""
    if profile:
        profile_slug = profile.get("url", "").rstrip("/").split("/")[-1]

    for ref in refs:
        activity_id = ref.get("activity_id")
        if not activity_id:
            continue
        ref_slug = ref.get("author_slug") or ref.get("text") or ""
        if not _author_matches_profile_slug(author, ref_slug):
            if not profile_slug or ref_slug != profile_slug:
                continue
        url = (ref.get("url") or "").strip()
        if url and not is_profile_fallback_url(url):
            return url, "activity_ref_slug"
        urn_kind = (ref.get("urn_kind") or "activity").lower()
        return build_feed_update_url(urn_kind, str(activity_id)), "activity_ref_urn"

    if profile_slug:
        for ref in refs:
            if ref.get("kind") != "feed_post":
                continue
            url = (ref.get("url") or "").strip()
            if not url or is_profile_fallback_url(url):
                continue
            ref_slug = ref.get("author_slug") or ref.get("text") or ""
            if ref_slug == profile_slug or _author_matches_profile_slug(author, ref_slug):
                return url, "feed_post_profile"

    return "", ""


def normalize_linkedin_job_urls(
    job: dict[str, Any],
    refs: list[dict[str, Any]] | None = None,
    *,
    resolve_posts: bool = False,
) -> None:
    """Ensure LinkedIn jobs use post URL vs apply URL consistently."""
    refs = refs or []
    url = (job.get("url") or "").strip()
    apply = (job.get("apply_url") or "").strip()
    author = job.get("company") or ""
    role = job.get("role") or "ai engineer"

    if is_apply_only_url(url):
        if not apply:
            job["apply_url"] = url
        url = ""

    if is_profile_fallback_url(url):
        url = ""

    if not is_posts_permalink(url) and not is_feed_update_url(url):
        feed_url, feed_source = match_author_activity_ref(author, refs)
        if feed_url:
            url = feed_url
            job["url_source"] = feed_source

    if is_profile_fallback_url(url):
        url = ""

    if not is_linkedin_post_url(url):
        job["url"] = fallback_linkedin_post_search_url(author, role)
        job["url_source"] = job.get("url_source") or "content_search_fallback"
    else:
        job["url"] = url

    if resolve_posts and is_feed_update_url(job.get("url", "")):
        resolved = resolve_feed_update_to_posts_permalink(job["url"])
        if is_posts_permalink(resolved):
            job["url"] = resolved
            job["url_source"] = job.get("url_source") or "posts_permalink"

    if not job.get("apply_url"):
        resolved = resolve_apply_url_from_text(
            job.get("description_snippet") or "",
            job.get("apply_channel"),
        )
        if resolved:
            job["apply_url"] = resolved


def profile_ref_to_post_url(kind: str, url: str) -> str:
    base = _abs_linkedin(url).split("?")[0].rstrip("/")
    if kind == "company" or "/company/" in base:
        return f"{base}/posts/"
    return f"{base}/recent-activity/all/"


def extract_profile_refs_from_html(html: str) -> list[dict[str, Any]]:
    """Extract person/company profile links embedded in LinkedIn search HTML."""
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    patterns = (
        ("person", LINKEDIN_PROFILE_RE),
        ("company", LINKEDIN_COMPANY_RE),
    )
    for kind, pattern in patterns:
        for match in pattern.finditer(html or ""):
            url = match.group(0).split("?")[0]
            if url in seen:
                continue
            seen.add(url)
            chunk = html[max(0, match.start() - 220) : match.start() + 320]
            strong = re.search(r"<strong>([^<]{2,100})</strong>", chunk)
            aria = re.search(r'aria-label="([^"]{2,100})"', chunk)
            label = strong.group(1) if strong else (aria.group(1) if aria else "")
            text = re.sub(r"\s+", " ", label).strip() or url.rstrip("/").split("/")[-1]
            refs.append({"kind": kind, "url": url, "text": text})
    return refs


def match_author_profile_ref(
    author: str,
    refs: list[dict[str, Any]],
) -> tuple[str, str]:
    """Match a post author/recruiter name to a profile ref → post URL."""
    author_key = _norm_author_name(author)
    author_slug = _slugify_name(author)
    if not author_key or author_key == "unknown":
        return "", ""

    for ref in refs:
        if ref.get("kind") not in {"person", "company"} or not ref.get("url"):
            continue
        ref_name = _norm_author_name(ref.get("text") or "")
        if ref_name and ref_name == author_key:
            return profile_ref_to_post_url(ref["kind"], ref["url"]), f"{ref['kind']}_name"

    if author_slug:
        for ref in refs:
            if ref.get("kind") not in {"person", "company"} or not ref.get("url"):
                continue
            slug = ref["url"].rstrip("/").split("/")[-1]
            slug_core = re.sub(r"-\d+$", "", slug)
            slug_norm = re.sub(r"[^a-z0-9]", "", slug_core.casefold())
            if author_slug in slug_norm or slug_norm in author_slug:
                return profile_ref_to_post_url(ref["kind"], ref["url"]), f"{ref['kind']}_slug"

    if author_slug:
        for ref in refs:
            if ref.get("kind") not in {"person", "company"} or not ref.get("url"):
                continue
            ref_name = _norm_author_name(ref.get("text") or "")
            ref_slug = _slugify_name(ref_name)
            if ref_slug and (author_slug in ref_slug or ref_slug in author_slug):
                return profile_ref_to_post_url(ref["kind"], ref["url"]), f"{ref['kind']}_fuzzy"

    author_tokens = [t for t in author_key.split() if len(t) > 2]
    if len(author_tokens) >= 2:
        for ref in refs:
            if ref.get("kind") not in {"person", "company"} or not ref.get("url"):
                continue
            ref_name = _norm_author_name(ref.get("text") or "")
            if all(token in ref_name for token in (author_tokens[0], author_tokens[-1])):
                return profile_ref_to_post_url(ref["kind"], ref["url"]), f"{ref['kind']}_token"

    return "", ""


def resolve_apply_url_from_text(text: str, apply_channel: str | None = None) -> str:
    """Extract external apply link or email from post text."""
    if apply_channel == "email":
        match = APPLY_EMAIL.search(text or "")
        if match:
            return match.group(0)
    lnkd = _first_lnkd_in(text or "")
    if lnkd:
        return lnkd
    for match in APPLY_URL.finditer(text or ""):
        url = match.group(0)
        if "linkedin.com" in url or is_blacklisted_url(url)[0]:
            continue
        if "/jobs/view/" in url or "lnkd.in" in url:
            return url
    return ""


def _first_lnkd_in(text: str) -> str:
    match = LNKD_RE.search(text or "")
    return match.group(0) if match else ""


def _first_feed_update(text: str) -> str:
    match = FEED_UPDATE_RE.search(text or "")
    if not match:
        return ""
    val = match.group(0)
    if val.startswith("urn:"):
        return f"https://www.linkedin.com/feed/update/{val}/"
    return val


def resolve_post_urls(
    chunk: str,
    author: str,
    refs: list[dict[str, Any]],
    *,
    feed_post_urls: list[str],
    feed_post_by_title: dict[str, str],
    feed_idx: int,
    job_urls: list[str],
    job_idx: int,
    author_url_map: dict[str, str] | None = None,
    chunk_url: str = "",
) -> tuple[str, str, str, int, int]:
    """Resolve post URL, apply URL, and source label for one search result chunk."""
    text = chunk or ""
    post_url = ""
    apply_url = ""
    source = ""

    index_url = ""
    if feed_idx < len(feed_post_urls):
        index_url = (feed_post_urls[feed_idx] or "").strip()
        feed_idx += 1

    post_url = _first_feed_update(text)
    if post_url:
        source = "text_feed_update"
    elif (chunk_url or "").strip() and not is_profile_fallback_url(chunk_url):
        post_url = chunk_url.strip()
        source = "collect_chunk_url"
    elif index_url and not is_profile_fallback_url(index_url):
        post_url = index_url
        source = "feed_post_index"

    if not post_url and author_url_map:
        mapped_url, mapped_source = resolve_author_post_url(
            author,
            author_url_map=author_url_map,
            profile_refs=[r for r in refs if r.get("kind") in {"person", "company"}],
            activity_refs=[r for r in refs if r.get("kind") == "feed_post"],
        )
        if mapped_url:
            post_url = mapped_url
            source = mapped_source

    if not post_url:
        matched_url, matched_source = match_author_activity_ref(author, refs)
        if matched_url:
            post_url = matched_url
            source = matched_source

    if not post_url:
        for title, url in feed_post_by_title.items():
            if title and title.lower() in text.lower() and not is_profile_fallback_url(url):
                post_url = url
                source = "feed_post_title"
                break

    if not post_url and "View job" in text and job_idx < len(job_urls):
        apply_url = job_urls[job_idx]
        job_idx += 1

    if not apply_url:
        apply_url = _first_lnkd_in(text)

    if not apply_url:
        apply_url = resolve_apply_url_from_text(text)

    if not post_url and not apply_url:
        source = "none"

    return post_url, apply_url, source, feed_idx, job_idx


def load_linkedin_config(track_id: str | None = None) -> dict[str, Any]:
    if track_id:
        from track_store import load_linkedin_config as load_track_li  # noqa: WPS433

        return load_track_li(track_id)
    return load_json(CONFIG_PATH, {})


def period_to_recency(days: int, cfg: dict[str, Any]) -> str:
    mapping = cfg.get("recency_map") or cfg.get("mcp_recency_map", {"1": "past-24h", "7": "past-week", "30": "past-month"})
    key = str(days)
    if key in mapping:
        return mapping[key]
    if days <= 1:
        return "past-24h"
    if days <= 7:
        return "past-week"
    return "past-month"


def build_query_string(role: str, region: str, cfg: dict[str, Any]) -> str:
    template = cfg.get("query_template", '"{role}" + "{region}"')
    return template.format(role=role, region=region)


def linkedin_content_search_url(query: str, *, recency: str = "past-week") -> str:
    """Build LinkedIn content search URL matching manual UI (date posted, sort by date)."""
    recency_map = {
        "past-24h": "past-24h",
        "past-week": "past-week",
        "past-month": "past-month",
    }
    date_posted = recency_map.get(recency, "past-week")
    params = {
        "keywords": query,
        "origin": "FACETED_SEARCH",
        "sortBy": '["date_posted"]',
        "datePosted": f'["{date_posted}"]',
    }
    return "https://www.linkedin.com/search/results/content/?" + urllib.parse.urlencode(params)


def parse_linkedin_relative_posted_at(text: str, *, now: datetime | None = None) -> datetime | None:
    """Parse LinkedIn post recency markers like '13h •', '2d •', 'now •' from post text."""
    if not text:
        return None
    ref = now or datetime.now(LOCAL_TZ)
    for line in text.split("\n")[:20]:
        line = line.strip()
        if not line:
            continue
        match = RELATIVE_POSTED_RE.search(line)
        if not match:
            continue
        if match.group("now"):
            return ref
        num = int(match.group("num"))
        unit = match.group("unit").lower()
        if unit == "m":
            return ref - timedelta(minutes=num)
        if unit == "h":
            return ref - timedelta(hours=num)
        if unit == "d":
            return ref - timedelta(days=num)
        if unit == "w":
            return ref - timedelta(weeks=num)
        if unit == "mo":
            return ref - timedelta(days=num * 30)
    return None


def sort_jobs_by_recency(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort jobs newest-first (LinkedIn date_posted order)."""

    def _key(job: dict[str, Any]) -> tuple[int, float, int]:
        posted = parse_posted_at(job.get("posted_at"))
        if posted:
            return (0, -posted.timestamp(), job.get("discovery_index", 0))
        idx = job.get("discovery_index")
        if idx is not None:
            return (1, float(idx), 0)
        return (2, 0.0, 0)

    return sorted(jobs, key=_key)


def rank_jobs_for_table(jobs: list[dict[str, Any]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    sort_mode = cfg.get("table_sort", "date_posted")
    if sort_mode == "salary":
        return sort_jobs_by_salary(jobs)
    return sort_jobs_by_recency(jobs)


def build_queries(cfg: dict[str, Any]) -> list[dict[str, str]]:
    roles = cfg.get("roles", ["ai engineer"])
    suffixes = cfg.get("region_suffixes", ["latam", "worldwide"])
    recency = period_to_recency(int(cfg.get("default_period_days", 7)), cfg)
    queries = []
    for role in roles:
        for suffix in suffixes:
            query = build_query_string(role, suffix, cfg)
            queries.append(
                {
                    "query": query,
                    "role_keyword": role,
                    "region": suffix,
                    "linkedin_url": linkedin_content_search_url(query, recency=recency),
                }
            )
    return queries


def check_linkedin_session() -> tuple[bool, str]:
    if not LOGIN_SCRIPT.exists():
        return False, f"Login script missing: {LOGIN_SCRIPT}"
    try:
        result = subprocess.run(
            [str(LOGIN_SCRIPT), "status"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode == 0 and ("valid" in output.lower() or "✅" in output):
            return True, output.strip()
        return False, output.strip() or "No valid LinkedIn session"
    except subprocess.TimeoutExpired:
        return False, "LinkedIn session check timed out"
    except OSError as exc:
        return False, str(exc)


def _pick_str(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        val = data.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


def _extract_post_url(post: dict[str, Any]) -> str:
    for key in ("url", "post_url", "postUrl", "link", "permalink"):
        val = post.get(key)
        if val:
            return str(val)
    urn = post.get("urn") or post.get("activityUrn")
    if urn:
        return f"https://www.linkedin.com/feed/update/{urn}/"
    return ""


def _extract_post_text(post: dict[str, Any]) -> str:
    parts = []
    for key in ("text", "content", "commentary", "description", "body"):
        val = post.get(key)
        if isinstance(val, str):
            parts.append(val)
        elif isinstance(val, dict):
            parts.append(json.dumps(val))
    return " ".join(parts).strip()


def _role_keyword_in_text(text: str, role_keyword: str) -> bool:
    """Match role keyword even when extra words appear (e.g. agentic AI engineer)."""
    if not role_keyword or not text:
        return False
    lowered = text.lower()
    key = role_keyword.lower()
    if key in lowered:
        return True
    words = key.split()
    if len(words) == 1:
        return bool(re.search(rf"\b{re.escape(words[0])}\b", lowered))
    pattern = r"\b" + r"\b.{0,30}\b".join(re.escape(word) for word in words) + r"\b"
    return bool(re.search(pattern, lowered, re.DOTALL))


def _guess_role(text: str, role_keyword: str) -> str:
    title_match = re.search(
        rf"({re.escape(role_keyword)}[^\n\.|]{0,40})",
        text,
        re.IGNORECASE,
    )
    if title_match:
        return title_match.group(1).strip(" :-")
    return role_keyword.title()


def _guess_company(post: dict[str, Any], text: str) -> str:
    from table_format import normalize_company_display

    author = post.get("author") or post.get("authorName") or post.get("poster")
    if isinstance(author, dict):
        name = author.get("name") or author.get("title")
        if name:
            return normalize_company_display(str(name))
    if isinstance(author, str) and author.strip():
        return normalize_company_display(author.strip())
    company = _pick_str(post, "company", "companyName")
    if company:
        return normalize_company_display(company)
    return "Unknown"


def _guess_apply_channel(text: str) -> str:
    if APPLY_EMAIL.search(text):
        return "email"
    if re.search(r"\b(dm|message me|inbox|reach out)\b", text, re.IGNORECASE):
        return "chat"
    if APPLY_URL.search(text):
        return "external_url"
    return "linkedin_post"


def post_to_job(
    post: dict[str, Any],
    query_meta: dict[str, str],
    cfg: dict[str, Any],
    job_search_config: dict[str, Any],
) -> dict[str, Any] | None:
    text = _extract_post_text(post)
    url = _extract_post_url(post)
    apply_url = _pick_str(post, "apply_url") or ""
    url_source = _pick_str(post, "url_source") or ""
    if not text and not url and not apply_url:
        return None

    for candidate in (url, apply_url):
        if not candidate:
            continue
        blocked, _ = is_blacklisted_url(candidate)
        if blocked:
            return None
    for match in APPLY_URL.finditer(text or ""):
        if is_blacklisted_url(match.group(0))[0]:
            return None

    llm_fn = make_llm_classify_fn(cfg) if cfg.get("llm_intent_classify_enabled") else None
    author_headline = _pick_str(post, "author_headline", "headline") or ""
    ingest, ingest_reason = should_ingest_linkedin_post(
        text,
        author_headline=author_headline or None,
        cfg=cfg,
        llm_classify=llm_fn,
    )
    if not ingest:
        return None

    salary_usd = None
    if text:
        salary_usd = extract_post_salary(text, _guess_role(text, query_meta.get("role_keyword", "AI Engineer")))
    region = query_meta.get("region", "")
    location_note = "LATAM" if region == "latam" else "Worldwide"

    post_url = url or ""
    if is_profile_fallback_url(post_url):
        post_url = _first_feed_update(text) or ""
        if post_url:
            url_source = url_source or "text_feed_update_repair"
    if not apply_url:
        apply_url = extract_role_apply_url(text, query_meta.get("role_keyword", "AI Engineer"))
        if not apply_url:
            apply_url = resolve_apply_url_from_text(text, _guess_apply_channel(text))
    role_guess = _guess_role(text, query_meta.get("role_keyword", "AI Engineer"))
    apply_email, apply_url = split_apply_email(apply_url, text, role_guess)
    if not post_url:
        post_url = f"linkedin-post:{hash(text) & 0xFFFFFFFF:x}"
        url_source = url_source or "placeholder"

    posted_at = _pick_str(post, "posted_at", "publishedAt", "createdAt", "date", "time")
    posted_label = None
    if not posted_at and text:
        rel_dt = parse_linkedin_relative_posted_at(text)
        if rel_dt:
            posted_at = rel_dt.isoformat()
        rel_match = RELATIVE_POSTED_RE.search(text)
        if rel_match:
            posted_label = rel_match.group(0).split("•")[0].strip()

    job: dict[str, Any] = {
        "source": "linkedin_posts",
        "url": post_url,
        "apply_url": apply_url,
        "apply_email": apply_email,
        "url_source": url_source or None,
        "role": role_guess,
        "company": _guess_company(post, text),
        "salary_usd": salary_usd,
        "currency": "USD" if salary_usd else None,
        "location_note": location_note,
        "posted_at": posted_at,
        "posted_label": posted_label,
        "apply_channel": _guess_apply_channel(text),
        "description_snippet": text[:500] if text else "",
        "search_query": query_meta.get("query"),
        "region_tag": region,
    }
    if query_meta.get("track"):
        job["track"] = query_meta["track"]
    if post.get("discovery_index") is not None:
        job["discovery_index"] = post["discovery_index"]

    post_intent = "hiring" if ingest_reason.startswith(("hiring", "llm_hiring")) else "ambiguous"
    if cfg.get("require_usd_salary", False):
        evaluate_job(job, job_search_config)
        job["post_intent"] = post_intent
    else:
        filt = classify_linkedin_post_filter(
            text,
            salary_usd,
            cfg,
            author_headline=author_headline or None,
            post_intent=post_intent,
        )
        job["filter_result"] = filt.filter_result
        job["skip_reason"] = filt.skip_reason
        job["post_intent"] = filt.post_intent

    return job


def parse_feed_search_posts(feed_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse LinkedIn content-search innerText + refs (browser collect export)."""
    raw = (feed_payload.get("sections") or {}).get("search_results") or ""
    refs = (feed_payload.get("references") or {}).get("search_results") or []
    author_url_map: dict[str, str] = dict(feed_payload.get("author_post_urls") or {})
    chunk_urls: list[str] = list(feed_payload.get("chunk_post_urls") or [])

    if raw.startswith("Did you mean"):
        raw = re.sub(r"^Did you mean[^\n]*\n+", "", raw, count=1)

    feed_post_urls: list[str] = []
    feed_post_by_title: dict[str, str] = {}
    job_urls: list[str] = []
    for ref in refs:
        kind = ref.get("kind")
        url = _abs_linkedin(ref.get("url") or "")
        if kind == "feed_post":
            feed_post_urls.append(url)
            title = (ref.get("text") or ref.get("author_slug") or "").strip()
            if title and url:
                feed_post_by_title[title] = url
        if kind == "job" and url:
            job_urls.append(url)

    posts: list[dict[str, Any]] = []
    chunks = re.split(r"(?:^|\n)Feed post\n", raw)
    feed_idx = 0
    job_idx = 0
    discovery_index = 0

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk or chunk.startswith("Are these results helpful?"):
            continue

        lines = [line.strip() for line in chunk.split("\n") if line.strip()]
        author = "Unknown"
        for line in lines[:12]:
            if line in {"Follow", "Show translation", "Visit my website", "View my services"}:
                continue
            if re.search(r"\b(1st|2nd|3rd\+?)\b", line):
                continue
            if re.match(r"^\d+[hmdw]\b", line) or "Edited •" in line:
                continue
            if len(line) > 2 and not line.startswith("#"):
                author = re.sub(r"\s+•.*", "", line).strip()
                break

        post_url, apply_url, url_source, feed_idx, job_idx = resolve_post_urls(
            chunk,
            author,
            refs,
            feed_post_urls=feed_post_urls,
            feed_post_by_title=feed_post_by_title,
            feed_idx=feed_idx,
            job_urls=job_urls,
            job_idx=job_idx,
            author_url_map=author_url_map,
            chunk_url=chunk_urls[discovery_index] if discovery_index < len(chunk_urls) else "",
        )

        posts.append(
            {
                "text": chunk,
                "url": post_url,
                "apply_url": apply_url,
                "url_source": url_source,
                "author": author,
                "discovery_index": discovery_index,
            }
        )
        discovery_index += 1

    return posts


def normalize_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten browser-collect JSON into list of {query_meta, post} entries."""
    items: list[dict[str, Any]] = []

    if "queries" in payload:
        for block in payload["queries"]:
            meta = {
                "query": block.get("query", ""),
                "role_keyword": block.get("role_keyword", ""),
                "region": block.get("region", ""),
                "track": block.get("track"),
            }
            posts = block.get("posts") or block.get("results") or []
            if not posts:
                for legacy_key in ("feed_payload", "feed_response", "mcp_response"):
                    nested = block.get(legacy_key)
                    if nested:
                        posts = parse_feed_search_posts(nested)
                        break
            for post in posts:
                if isinstance(post, dict):
                    items.append({"query_meta": meta, "post": post})
        return items

    if "posts" in payload and isinstance(payload["posts"], list):
        meta = {
            "query": payload.get("query", ""),
            "role_keyword": payload.get("role_keyword", ""),
            "region": payload.get("region", ""),
        }
        for post in payload["posts"]:
            if isinstance(post, dict):
                items.append({"query_meta": meta, "post": post})
        return items

    if payload.get("sections") and payload.get("references"):
        meta = {
            "query": payload.get("query", ""),
            "role_keyword": payload.get("role_keyword", ""),
            "region": payload.get("region", ""),
            "track": payload.get("track"),
        }
        for post in parse_feed_search_posts(payload):
            items.append({"query_meta": meta, "post": post})
        return items

    return items


def write_linkedin_run_markdown(
    run_path: Path,
    since: datetime,
    all_jobs: list[dict[str, Any]],
    new_jobs: list[dict[str, Any]],
    period_days: int,
    recency: str,
    queries_run: int,
    cfg: dict[str, Any] | None = None,
) -> None:
    """Write LinkedIn run table sorted by recency (newest first) or salary."""
    cfg = cfg or load_linkedin_config()
    run_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(LOCAL_TZ)
    new_keys = {job_key(j) for j in new_jobs}
    ranked = rank_jobs_for_table(all_jobs, cfg)
    sort_mode = cfg.get("table_sort", "date_posted")

    eligible = [j for j in ranked if j.get("filter_result") == "eligible"]
    review = [j for j in ranked if j.get("filter_result") == "needs_review"]
    skipped = [j for j in ranked if j.get("filter_result") == "skipped"]

    sort_note = "newest first (date posted ↓)" if sort_mode == "date_posted" else "salary (highest first)"

    lines = [
        f"# LinkedIn posts run — {now.strftime('%Y-%m-%d %H:%M %Z')}",
        "",
        f"**Period:** {period_days} days ({recency}) · **Queries:** {queries_run}",
        f"**Since (dedup):** {since.isoformat()}",
        "",
        "_Query: `\"role\" + \"region\"` · Filter: past-week · Sort: **latest → oldest**._",
        "",
        "## Summary",
        "",
        f"- Posts matched: **{len(ranked)}**",
        f"- New to registry: **{len(new_jobs)}**",
        f"- Eligible (USD in post): **{len(eligible)}**",
        f"- Needs review: **{len(review)}**",
        f"- Skipped: **{len(skipped)}**",
        "",
        f"_Sorted by {sort_note} — apply from top down._",
        "",
        f"## All posts ({'date ↓' if sort_mode == 'date_posted' else 'salary ↓'})",
        "",
        "| ☐ | # | Posted | Role | Company | Salary (post) | Est. USD/yr | Location | Status | New | Post URL | Apply URL | Apply Email |",
        "|---|---|--------|------|---------|---------------|-------------|----------|--------|-----|----------|-----------|-------------|",
    ]

    for idx, job in enumerate(ranked, start=1):
        from apply_email import apply_email_display  # noqa: E402
        from table_format import md_cell, normalize_company_display

        salary = job.get("salary_usd") or "—"
        est = salary_sort_value(salary)
        est_label = f"~${est:,.0f}" if est >= 0 else "—"
        location = job.get("location_note") or "—"
        is_new = "yes" if job_key(job) in new_keys else "—"
        post_url = job.get("url") or "—"
        apply_url = job.get("apply_url") or "—"
        posted = job.get("posted_label") or "—"
        if posted == "—" and job.get("posted_at"):
            posted = str(job.get("posted_at"))[:10]
        lines.append(
            f"| ☐ | {idx} | {md_cell(posted)} | {md_cell(job.get('role', '—'))} | "
            f"{md_cell(normalize_company_display(job.get('company', '—')))} | "
            f"{md_cell(salary)} | {md_cell(est_label)} | {md_cell(location)} | "
            f"{md_cell(job.get('filter_result', '—'))} | {md_cell(is_new)} | "
            f"{md_cell(post_url)} | {md_cell(apply_url)} | {md_cell(apply_email_display(job))} |"
        )

    run_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def merge_payload(
    payload: dict[str, Any],
    period_days: int,
    since_arg: str | None = None,
) -> dict[str, Any]:
    cfg = load_linkedin_config()
    job_search_config = load_json(JOB_SEARCH_CONFIG, {})
    linkedin_state = load_json(LINKEDIN_STATE_PATH, {"last_run_at": None})

    period_days = int(payload.get("period_days") or period_days)
    since = parse_since(since_arg or f"{period_days}d", linkedin_state.get("last_run_at"))

    registry = load_registry()
    incoming: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    for item in normalize_payload(payload):
        job = post_to_job(item["post"], item["query_meta"], cfg, job_search_config)
        if not job:
            continue
        key = job_key(job)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        incoming.append(job)

    registry, new_jobs = merge_jobs(registry, incoming, since)
    now = datetime.now(LOCAL_TZ)
    run_path = RUNS_DIR / f"linkedin-posts-{now.strftime('%Y-%m-%dT%H-%M')}.md"

    source_stats = {
        "linkedin_posts": {
            "fetched": len(incoming),
            "new": len(new_jobs),
            "eligible": len([j for j in new_jobs if j.get("filter_result") == "eligible"]),
            "error": None,
        }
    }

    save_registry(registry)
    write_linkedin_run_markdown(
        run_path,
        since,
        incoming,
        new_jobs,
        period_days,
        period_to_recency(period_days, cfg),
        len(payload.get("queries", [])),
        cfg,
    )
    save_json(LINKEDIN_STATE_PATH, {"last_run_at": now.isoformat()})

    result = {
        "run_path": str(run_path),
        "registry_path": str(REGISTRY_PATH),
        "period_days": period_days,
        "recency": period_to_recency(period_days, cfg),
        "queries_run": len(payload.get("queries", [])),
        "posts_parsed": len(incoming),
        "new_total": len(new_jobs),
        "eligible": len([j for j in new_jobs if j.get("filter_result") == "eligible"]),
        "needs_review": len([j for j in new_jobs if j.get("filter_result") == "needs_review"]),
    }
    from audit_log import info as audit_info  # noqa: WPS433

    since_label = since.isoformat() if isinstance(since, datetime) else since
    audit_info("linkedin_posts_merge", "merge_complete", since=since_label, **result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge LinkedIn posts JSON into job-search registry.")
    parser.add_argument("--input", "-i", help="JSON file with browser collect results")
    parser.add_argument("--period", type=int, default=None, help="Period in days (default: 7 → past-week)")
    parser.add_argument("--since", help='Dedup window: "last-run", "7d", or ISO date')
    parser.add_argument("--print-queries", action="store_true", help="Print search query list and recency")
    parser.add_argument("--check-session", action="store_true", help="Check LinkedIn login only")
    args = parser.parse_args()

    if args.check_session:
        ok, msg = check_linkedin_session()
        print(msg)
        return 0 if ok else 1

    if args.print_queries:
        cfg = load_linkedin_config()
        period = args.period or cfg.get("default_period_days", 7)
        print(
            json.dumps(
                {
                    "period_days": period,
                    "recency": period_to_recency(period, cfg),
                    "max_pages": cfg.get("default_max_pages", 5),
                    "queries": build_queries(cfg),
                },
                indent=2,
            )
        )
        return 0

    if not args.input:
        parser.error("--input is required unless using --print-queries or --check-session")

    cfg = load_linkedin_config()
    default_period = cfg.get("default_period_days", 7)
    period = args.period if args.period is not None else default_period
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    payload.setdefault("period_days", period)
    result = merge_payload(payload, period, args.since)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
