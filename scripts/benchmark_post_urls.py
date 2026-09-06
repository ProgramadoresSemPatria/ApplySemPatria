#!/usr/bin/env python3
"""Benchmark LinkedIn post URL resolution strategies on saved MCP responses."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from linkedin_posts_merge import parse_feed_search_posts  # noqa: E402

ROOT = SCRIPTS.parent
QUOTED_DIR = ROOT / "runs" / "mcp-responses-2026-08-27-quoted"
AUG24_SAMPLE = ROOT / "runs" / "mcp-responses-2026-08-24" / "q04-agent-engineer-worldwide.json"

FEED_UPDATE_RE = re.compile(
    r"https?://(?:www\.)?linkedin\.com/feed/update/[^\s\)\]\"']+|"
    r"urn:li:(?:activity|share|ugcPost):[\d]+",
    re.IGNORECASE,
)
LNKD_RE = re.compile(r"https?://(?:www\.)?lnkd\.in/[A-Za-z0-9_-]+")
LINKEDIN_HTTP_RE = re.compile(r"https?://(?:www\.)?linkedin\.com/[^\s\)\]\"']+")


def _abs_linkedin(path_or_url: str) -> str:
    if not path_or_url:
        return ""
    if path_or_url.startswith("http"):
        return path_or_url
    return f"https://www.linkedin.com{path_or_url}"


def _norm_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip()).casefold()


def approach_a_feed_post_index(mcp: dict, posts: list[dict]) -> list[str]:
    """MCP feed_post refs in document order (current parser behavior)."""
    refs = (mcp.get("references") or {}).get("search_results") or []
    feed_urls = [
        _abs_linkedin(r["url"])
        for r in refs
        if r.get("kind") == "feed_post" and r.get("url")
    ]
    out: list[str] = []
    for i, _post in enumerate(posts):
        out.append(feed_urls[i] if i < len(feed_urls) else "")
    return out


def approach_b_feed_post_title_match(mcp: dict, posts: list[dict]) -> list[str]:
    """Match feed_post ref text to post body."""
    refs = (mcp.get("references") or {}).get("search_results") or []
    feed_refs = [r for r in refs if r.get("kind") == "feed_post" and r.get("url")]
    used: set[int] = set()
    out: list[str] = []
    for post in posts:
        text = post.get("text") or ""
        url = ""
        for i, ref in enumerate(feed_refs):
            if i in used:
                continue
            title = (ref.get("text") or "").strip()
            if title and title.lower() in text.lower():
                url = _abs_linkedin(ref["url"])
                used.add(i)
                break
        out.append(url)
    return out


def approach_c_text_feed_update(posts: list[dict]) -> list[str]:
    """Extract feed/update or urn:li:activity from post text."""
    out: list[str] = []
    for post in posts:
        text = post.get("text") or ""
        m = FEED_UPDATE_RE.search(text)
        if not m:
            out.append("")
            continue
        val = m.group(0)
        if val.startswith("urn:"):
            val = f"https://www.linkedin.com/feed/update/{val}/"
        out.append(val)
    return out


def approach_d_job_ref_when_view_job(mcp: dict, posts: list[dict]) -> list[str]:
    """Use jobs/view ref when chunk mentions View job (apply link, not post)."""
    refs = (mcp.get("references") or {}).get("search_results") or []
    job_urls = [
        _abs_linkedin(r["url"])
        for r in refs
        if r.get("kind") == "job" and r.get("url")
    ]
    job_idx = 0
    out: list[str] = []
    for post in posts:
        text = post.get("text") or ""
        if "View job" in text and job_idx < len(job_urls):
            out.append(job_urls[job_idx])
            job_idx += 1
        else:
            out.append("")
    return out


def approach_e_lnkd_in_text(posts: list[dict]) -> list[str]:
    """First lnkd.in short link in post text."""
    out: list[str] = []
    for post in posts:
        m = LNKD_RE.search(post.get("text") or "")
        out.append(m.group(0) if m else "")
    return out


def approach_f_company_posts_page(mcp: dict, posts: list[dict]) -> list[str]:
    """Company /posts/ page when author matches company ref."""
    refs = (mcp.get("references") or {}).get("search_results") or []
    company_by_name: dict[str, str] = {}
    for ref in refs:
        if ref.get("kind") == "company" and ref.get("text") and ref.get("url"):
            slug = ref["url"].strip("/").split("/")[-1]
            company_by_name[_norm_name(ref["text"])] = f"https://www.linkedin.com/company/{slug}/posts/"
    out: list[str] = []
    for post in posts:
        author = _norm_name(post.get("author") or "")
        out.append(company_by_name.get(author, ""))
    return out


def approach_g_recent_activity(mcp: dict, posts: list[dict]) -> list[str]:
    """Person /recent-activity/all/ instead of profile."""
    refs = (mcp.get("references") or {}).get("search_results") or []
    person_by_name: dict[str, str] = {}
    for ref in refs:
        if ref.get("kind") == "person" and ref.get("text") and ref.get("url"):
            base = _abs_linkedin(ref["url"]).rstrip("/")
            person_by_name[_norm_name(ref["text"])] = f"{base}/recent-activity/all/"
    out: list[str] = []
    for post in posts:
        author = _norm_name(post.get("author") or "")
        out.append(person_by_name.get(author, ""))
    return out


def approach_h_combined(mcp: dict, posts: list[dict]) -> list[tuple[str, str]]:
    """Best-effort chain: feed_post → text urn → job card → lnkd.in → company posts → activity."""
    a = approach_a_feed_post_index(mcp, posts)
    b = approach_b_feed_post_title_match(mcp, posts)
    c = approach_c_text_feed_update(posts)
    d = approach_d_job_ref_when_view_job(mcp, posts)
    e = approach_e_lnkd_in_text(posts)
    f = approach_f_company_posts_page(mcp, posts)
    g = approach_g_recent_activity(mcp, posts)

    out: list[tuple[str, str]] = []
    for i, _post in enumerate(posts):
        for label, url in (
            ("feed_post_index", a[i]),
            ("feed_post_title", b[i]),
            ("text_feed_update", c[i]),
            ("job_view_card", d[i]),
            ("lnkd_in", e[i]),
            ("company_posts", f[i]),
            ("recent_activity", g[i]),
        ):
            if url:
                out.append((url, label))
                break
        else:
            out.append(("", "none"))
    return out


def is_post_url(url: str) -> bool:
    if not url:
        return False
    if "/feed/update/" in url or "urn:li:" in url:
        return True
    if "/recent-activity/" in url:
        return True  # activity feed, not profile
    if "/company/" in url and url.endswith("/posts/"):
        return True
    if "/in/" in url and not url.rstrip("/").endswith("/recent-activity/all"):
        return False
    if "lnkd.in" in url or "/jobs/view/" in url:
        return False
    return False


def score_urls(urls: list[str]) -> dict[str, int]:
    filled = sum(1 for u in urls if u)
    post_like = sum(1 for u in urls if is_post_url(u))
    profiles = sum(
        1
        for u in urls
        if u and "/in/" in u and "/recent-activity/" not in u and "/feed/update/" not in u
    )
    apply_links = sum(1 for u in urls if u and ("lnkd.in" in u or "/jobs/view/" in u))
    return {
        "filled": filled,
        "post_like": post_like,
        "profiles": profiles,
        "apply_links": apply_links,
        "total": len(urls),
    }


def run_file(path: Path) -> dict[str, dict[str, int]]:
    mcp = json.loads(path.read_text(encoding="utf-8"))
    posts = parse_feed_search_posts(mcp)
    if not posts:
        return {}

    strategies = {
        "A_feed_post_index": approach_a_feed_post_index(mcp, posts),
        "B_feed_post_title": approach_b_feed_post_title_match(mcp, posts),
        "C_text_feed_update": approach_c_text_feed_update(posts),
        "D_job_view_card": approach_d_job_ref_when_view_job(mcp, posts),
        "E_lnkd_in": approach_e_lnkd_in_text(posts),
        "F_company_posts": approach_f_company_posts_page(mcp, posts),
        "G_recent_activity": approach_g_recent_activity(mcp, posts),
    }
    combined = approach_h_combined(mcp, posts)
    strategies["H_combined"] = [u for u, _ in combined]

    return {name: score_urls(urls) for name, urls in strategies.items()}


def main() -> None:
    files = sorted(QUOTED_DIR.glob("q*.json"))
    if AUG24_SAMPLE.exists():
        files.append(AUG24_SAMPLE)

    totals: dict[str, dict[str, int]] = {}
    for path in files:
        print(f"\n=== {path.name} ===")
        scores = run_file(path)
        for name, s in scores.items():
            print(
                f"  {name}: filled={s['filled']}/{s['total']} "
                f"post_like={s['post_like']} apply={s['apply_links']} profile={s['profiles']}"
            )
            acc = totals.setdefault(name, {"filled": 0, "post_like": 0, "apply_links": 0, "profiles": 0, "total": 0})
            for k in acc:
                acc[k] += s[k]

    print("\n=== TOTAL across files ===")
    for name, s in sorted(totals.items()):
        print(
            f"  {name}: filled={s['filled']}/{s['total']} "
            f"post_like={s['post_like']} apply={s['apply_links']} profile={s['profiles']}"
        )

    # Show combined resolution detail for quoted q01
    q01 = json.loads((QUOTED_DIR / "q01-ai-engineer-latam.json").read_text(encoding="utf-8"))
    posts = parse_feed_search_posts(q01)
    combined = approach_h_combined(q01, posts)
    print("\n=== H_combined samples (q01) ===")
    for post, (url, src) in zip(posts, combined):
        author = post.get("author", "?")
        print(f"  {author[:30]:30} | {src:18} | {url[:70] if url else '—'}")


if __name__ == "__main__":
    main()
