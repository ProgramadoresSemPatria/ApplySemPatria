#!/usr/bin/env python3
"""Extract LinkedIn post permalinks from feed cards (SDUI + legacy DOM + Copy link menu)."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from linkedin_posts_merge import (  # noqa: E402
    LNKD_RE,
    POSTS_PERMALINK_RE,
    _author_map_key,
    build_feed_update_url,
    is_feed_update_url,
    is_posts_permalink,
    resolve_feed_update_to_posts_permalink,
)

COPY_LINK_LABEL_RE = re.compile(
    r'(?:aria-label="([^"]*Copy link to post[^"]*)"|>([^<]*Copy link to post[^<]*)<)',
    re.I,
)
POST_OVERFLOW_RE = re.compile(
    r'aria-label="(Open control menu for post by [^"]+)"',
    re.I,
)
FEED_POST_HEADING_RE = re.compile(r">Feed post<", re.I)
SDUI_LISTITEM_RE = re.compile(
    r'(<div\b[^>]*role="listitem"[^>]*>.*?</div>\s*(?=<div\b[^>]*role="listitem"|<div class="be5680d4|$))',
    re.I | re.S,
)

POST_CARD_SELECTOR = (
    'main div[role="listitem"]:has(h2 span:text-is("Feed post")), '
    'main article[data-urn], main div.feed-shared-update-v2[data-urn], '
    'main div[data-urn^="urn:li:activity"], main div[data-urn^="urn:li:share"]'
)
POST_OVERFLOW_SELECTORS = (
    'button[aria-label*="Open control menu for post by"]',
    'button[aria-label*="control menu for post"]',
    'button[aria-label*="Open control menu"]',
    'button.feed-shared-control-menu__trigger',
    'button.artdeco-dropdown__trigger',
)
CLIPBOARD_HOOK_INIT_SCRIPT = """
() => {
  if (window.__linkedinCopyHookInstalled) return;
  window.__linkedinCopyHookInstalled = true;
  window.__lastCopiedText = "";
  const assign = (text) => {
    window.__lastCopiedText = String(text || "");
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    const orig = navigator.clipboard.writeText.bind(navigator.clipboard);
    navigator.clipboard.writeText = async (text) => {
      assign(text);
      try { return await orig(text); } catch (e) { return undefined; }
    };
  }
  document.addEventListener("copy", (event) => {
    try {
      const text = event.clipboardData && event.clipboardData.getData("text/plain");
      if (text) assign(text);
    } catch (e) {}
  }, true);
}
"""

COPY_LINK_SELECTORS = (
    '[role="menuitem"]:has-text("Copy link to post")',
    'div[role="button"]:has-text("Copy link to post")',
    'span:text-is("Copy link to post")',
    'li span:has-text("Copy link to post")',
)


def find_copy_link_menu_labels(html: str) -> list[str]:
    labels: list[str] = []
    for aria, text in COPY_LINK_LABEL_RE.findall(html or ""):
        label = (aria or text or "").strip()
        if label and label not in labels:
            labels.append(label)
    return labels


def find_post_overflow_labels(html: str) -> list[str]:
    return [m.group(1).strip() for m in POST_OVERFLOW_RE.finditer(html or "")]


def _author_from_sdui_block(block: str) -> str:
    match = re.search(r'aria-label="([^,"]+),', block)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()
    for pat in (
        r'update-components-actor__title[^>]*>\s*<span[^>]*>([^<]{2,100})',
        r'feed-shared-actor__name[^>]*>([^<]{2,100})',
        r"<span>([^<]{2,80})</span></p></div></div></a>",
    ):
        match = re.search(pat, block, re.I | re.S)
        if match:
            author = re.sub(r"\s+", " ", match.group(1)).strip()
            if author.lower() not in {"follow", "like", "comment", "share"}:
                return author
    return ""


def _urn_from_fragment(fragment: str) -> str:
    match = re.search(r'data-urn="(urn:li:(?:activity|share|ugcPost):\d+)"', fragment or "", re.I)
    return match.group(1) if match else ""


def post_url_from_article_html(fragment: str) -> str:
    """Best post URL from one feed card HTML fragment."""
    text = fragment or ""
    for match in POSTS_PERMALINK_RE.finditer(text):
        url = match.group(0).split("?")[0]
        return url if url.endswith("/") else f"{url}/"
    urn = _urn_from_fragment(text)
    if urn:
        urn_m = re.search(r"urn:li:(activity|share|ugcPost):(\d+)", urn, re.I)
        if urn_m:
            return build_feed_update_url(urn_m.group(1).lower(), urn_m.group(2))
    match = re.search(
        r"https?://(?:www\.)?linkedin\.com/feed/update/urn:li:(activity|share|ugcPost):(\d+)/?",
        text,
        re.I,
    )
    if match:
        return build_feed_update_url(match.group(1).lower(), match.group(2))
    return ""


def extract_ordered_article_post_cards(html: str) -> list[dict[str, str]]:
    """Feed cards in DOM order — legacy article/data-urn and LinkedIn SDUI listitems."""
    text = html or ""
    cards: list[dict[str, str]] = []
    seen_authors: set[str] = set()

    for part in re.split(r"(?=<article\b)", text, flags=re.I):
        if part.strip() and "data-urn" in part:
            url = post_url_from_article_html(part)
            author = _author_from_sdui_block(part)
            if url or author:
                key = _author_map_key(author)
                if key in seen_authors and not url:
                    continue
                seen_authors.add(key)
                cards.append({"url": url, "author": author})

    if not cards:
        for match in re.finditer(
            r'<div\b[^>]*role="listitem"[^>]*componentkey="update-card-focus[^"]*"[^>]*>',
            text,
            re.I,
        ):
            start = match.start()
            end = min(len(text), start + 25000)
            block = text[start:end]
            if not FEED_POST_HEADING_RE.search(block):
                continue
            author = _author_from_sdui_block(block)
            url = post_url_from_article_html(block)
            key = _author_map_key(author)
            if not author:
                continue
            if key in seen_authors:
                continue
            seen_authors.add(key)
            cards.append({"url": url, "author": author})

    return cards


def is_copyable_post_url(url: str) -> bool:
    url = (url or "").strip()
    if not url:
        return False
    return bool(
        is_posts_permalink(url)
        or is_feed_update_url(url)
        or LNKD_RE.search(url)
        or ("linkedin.com/" in url and "search/results/content" not in url)
    )


def normalize_copied_post_url(url: str, *, timeout: float = 15.0) -> str:
    """Turn clipboard output (often lnkd.in) into canonical linkedin.com/posts/… URL."""
    import subprocess

    url = (url or "").strip().split("?")[0]
    if not url:
        return ""
    if is_posts_permalink(url):
        return url if url.endswith("/") else f"{url}/"
    if is_feed_update_url(url):
        return resolve_feed_update_to_posts_permalink(url, timeout=timeout)

    if not (LNKD_RE.search(url) or "linkedin.com/" in url):
        return ""

    curl = [
        "curl",
        "-sI",
        "-L",
        "-A",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "--max-time",
        str(int(timeout)),
        url,
    ]
    try:
        result = subprocess.run(curl, capture_output=True, text=True, check=False, timeout=timeout + 2)
    except (OSError, subprocess.TimeoutExpired):
        return ""

    final = ""
    for line in reversed((result.stdout or "").splitlines()):
        if line.lower().startswith("location:"):
            final = line.split(":", 1)[1].strip().split("?")[0]
            break
    if not final:
        return ""
    if is_posts_permalink(final):
        final = re.sub(r"https://[\w-]+\.linkedin\.com", "https://www.linkedin.com", final)
        return final if final.endswith("/") else f"{final}/"
    if is_feed_update_url(final):
        return resolve_feed_update_to_posts_permalink(final, timeout=timeout)
    return ""


async def copy_post_link_from_card(page: Any, card: Any, *, timeout_ms: int = 8000) -> str:
    """Open post overflow menu and read Copy link to post from clipboard."""
    try:
        urn = await card.get_attribute("data-urn")
    except Exception:
        urn = None
    if urn:
        urn_m = re.search(r"urn:li:(activity|share|ugcPost):(\d+)", urn, re.I)
        if urn_m:
            return build_feed_update_url(urn_m.group(1).lower(), urn_m.group(2))

    try:
        await page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    except Exception:
        pass

    overflow = None
    for sel in POST_OVERFLOW_SELECTORS:
        loc = card.locator(sel).first
        try:
            if await loc.count() > 0:
                overflow = loc
                break
        except Exception:
            continue
    if overflow is None:
        return ""

    try:
        await overflow.click(timeout=timeout_ms)
    except Exception:
        return ""

    copy_btn = page.get_by_text("Copy link to post", exact=True).first
    if await copy_btn.count() == 0:
        copy_btn = None
        for sel in COPY_LINK_SELECTORS:
            loc = page.locator(sel).first
            try:
                if await loc.count() > 0:
                    copy_btn = loc
                    break
            except Exception:
                continue
    if copy_btn is None or await copy_btn.count() == 0:
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        return ""

    try:
        await copy_btn.click(timeout=timeout_ms)
        await asyncio.sleep(0.35)
        url = await page.evaluate("() => navigator.clipboard.readText()")
    except Exception:
        url = ""
    finally:
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass

    if not is_copyable_post_url(url):
        return ""
    return normalize_copied_post_url(url)


async def install_copy_link_hook(page: Any) -> None:
    try:
        await page.add_init_script(CLIPBOARD_HOOK_INIT_SCRIPT)
    except Exception:
        pass


async def read_captured_copy_text(page: Any) -> str:
    try:
        await page.evaluate("() => { window.__lastCopiedText = ''; }")
    except Exception:
        pass
    return ""


async def copy_post_link_for_author(page: Any, author: str, *, timeout_ms: int = 8000) -> str:
    """Copy link to post for the feed card whose overflow menu names *author*."""
    author = (author or "").strip()
    if not author:
        return ""

    first_name = author.split()[0]
    candidates = [
        f'main button[aria-label="Open control menu for post by {author}"]',
        f'main button[aria-label*="Open control menu for post by {author}"]',
        f'main button[aria-label*="control menu for post by {author}"]',
    ]
    if first_name and first_name != author:
        candidates.append(f'main button[aria-label*="Open control menu for post by {first_name}"]')

    for sel in candidates:
        btn = page.locator(sel).first
        try:
            if await btn.count() == 0:
                continue
            await page.evaluate("() => { window.__lastCopiedText = ''; }")
            await btn.click(timeout=timeout_ms)
            menu = page.locator('div[role="menu"]').last
            try:
                await menu.wait_for(state="visible", timeout=timeout_ms)
            except Exception:
                await page.keyboard.press("Escape")
                continue
            copy_btn = menu.get_by_text("Copy link to post", exact=True).first
            if await copy_btn.count() == 0:
                copy_btn = page.get_by_text("Copy link to post", exact=True).first
            if await copy_btn.count() == 0:
                await page.keyboard.press("Escape")
                continue
            await copy_btn.click(timeout=timeout_ms)
            await asyncio.sleep(0.35)
            raw = await page.evaluate(
                "() => window.__lastCopiedText || (navigator.clipboard && navigator.clipboard.readText ? '' : '')"
            )
            if not raw:
                try:
                    raw = await page.evaluate("() => navigator.clipboard.readText()")
                except Exception:
                    raw = ""
            if not raw:
                raw = await page.evaluate("() => window.__lastCopiedText || ''")
            await page.keyboard.press("Escape")
            return normalize_copied_post_url(raw)
        except Exception:
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass
            continue
    return ""


async def resolve_chunk_post_url_via_copy_link(
    page: Any,
    author: str,
    *,
    timeout_ms: int = 8000,
) -> str:
    """Primary SDUI path when HTML lacks data-urn — mirrors manual Copy link to post."""
    return await copy_post_link_for_author(page, author, timeout_ms=timeout_ms)


async def backfill_missing_chunk_urls_via_copy_link(
    page: Any,
    chunks: list[str],
    chunk_post_urls: list[str],
    *,
    limit: int = 25,
    extract_author,
) -> int:
    """Fill empty chunk_post_urls by Copy link to post on visible cards."""
    if limit <= 0:
        return 0

    filled = 0
    for i, chunk in enumerate(chunks):
        if filled >= limit:
            break
        if (chunk_post_urls[i] if i < len(chunk_post_urls) else "").strip():
            continue
        author = extract_author(chunk)
        url = await copy_post_link_for_author(page, author)
        if url:
            while len(chunk_post_urls) <= i:
                chunk_post_urls.append("")
            chunk_post_urls[i] = url
            filled += 1
    return filled
