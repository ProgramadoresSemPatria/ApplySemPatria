#!/usr/bin/env python3
"""LinkedIn DM thread helpers — detect recent messages before re-sending."""

from __future__ import annotations

import re
from typing import Any

from human_pacing import (
    drift_mouse,
    human_click,
    human_fill,
    human_scroll,
    pause_human,
    pause_page_settle,
    pause_poll,
)
from linkedin_ui import cleanup_after_message, dismiss_blocking_dialogs

MESSAGE_AFFORDANCE = "main a:has-text('Message'), main button:has-text('Message')"

RECENT_HEADER_RE = re.compile(
    r"^(today|yesterday|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)$",
    re.I,
)

OLDER_HEADER_RE = re.compile(
    r"^(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+\d{1,2}$",
    re.I,
)


def classify_header(text: str) -> str:
    t = (text or "").strip()
    if RECENT_HEADER_RE.match(t):
        return "recent"
    if OLDER_HEADER_RE.match(t):
        return "older"
    return "other"


def latest_header_is_recent(headers: list[str]) -> tuple[bool, str, str]:
    """Return (is_recent, last_header, reason). Uses the last header in thread order."""
    relevant = [h for h in headers if classify_header(h) in ("recent", "older")]
    if not relevant:
        return False, "", "no date headers in thread"
    last = relevant[-1]
    if classify_header(last) == "recent":
        return True, last, f"latest thread header is '{last}' (< 1 week on LinkedIn)"
    return False, last, f"latest thread header is '{last}' (older bucket — ok to message)"


def _abs_linkedin_url(href: str) -> str:
    if href.startswith("http"):
        return href
    return f"https://www.linkedin.com{href if href.startswith('/') else '/' + href}"


async def _top_compose_href(page) -> str | None:
    loc = page.locator("main a[href*='messaging/compose']:not([aria-label])")
    if await loc.count() == 0:
        loc = page.locator("main a[href*='messaging/compose'], main a[href*='messaging/thread']")
    if await loc.count() == 0:
        return None
    href = await loc.first.get_attribute("href")
    return _abs_linkedin_url(href) if href else None


async def _composer_visible(page) -> bool:
    loc = page.locator("div.msg-form__contenteditable[contenteditable='true']")
    return await loc.count() > 0


async def _thread_panel_visible(page) -> bool:
    if await _composer_visible(page):
        return True
    for sel in (
        ".msg-s-message-list-content",
        ".msg-convo-wrapper .msg-s-message-list-content",
        ".msg-overlay-conversation-bubble",
        ".msg-overlay",
    ):
        try:
            if await page.locator(sel).count() > 0:
                await page.locator(sel).first.wait_for(state="visible", timeout=8000)
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


async def open_message_thread(page) -> bool:
    """Click Message on profile top card and wait for the chat overlay."""
    await page.evaluate("window.scrollTo(0, 0)")
    await pause_poll(base=0.4)
    await dismiss_blocking_dialogs(page)
    await drift_mouse(page)

    compose_url = await _top_compose_href(page)
    loc = page.locator("main a[href*='messaging/compose']:not([aria-label])")
    if await loc.count() == 0:
        loc = page.locator("main a[href*='messaging/compose'], main a[href*='messaging/thread']")
    if await loc.count() == 0:
        loc = page.locator("main").get_by_role("link", name=re.compile(r"^Message", re.I))
    if await loc.count() == 0:
        loc = page.locator("main").get_by_role("button", name=re.compile(r"^Message", re.I))
    if await loc.count() == 0:
        return False

    try:
        await human_click(page, loc, timeout=15000)
    except Exception:  # noqa: BLE001
        if compose_url:
            await page.goto(compose_url, wait_until="domcontentloaded", timeout=60000)
            await pause_page_settle()
        else:
            return False

    await pause_page_settle(base=6.5)
    await dismiss_blocking_dialogs(page)

    if await _thread_panel_visible(page):
        return True

    if compose_url:
        await page.goto(compose_url, wait_until="domcontentloaded", timeout=60000)
        await pause_page_settle(base=6.5)
        await dismiss_blocking_dialogs(page)
        return await _thread_panel_visible(page)

    return False


async def read_thread_headers(page) -> list[str]:
    """Read date bucket headers from the open message list only."""
    try:
        raw = await page.locator(".msg-s-message-list-content").first.inner_text()
    except Exception:  # noqa: BLE001
        return []
    headers: list[str] = []
    for line in raw.splitlines():
        t = line.strip()
        if classify_header(t) != "other":
            headers.append(t)
    return headers


async def send_message(page, text: str, *, send: bool) -> tuple[bool, str]:
    """Fill the open composer and click Send. Thread should already be open."""
    if not await _composer_visible(page):
        opened = await open_message_thread(page)
        if not opened or not await _composer_visible(page):
            return False, "composer not found"
    composer = page.locator("div.msg-form__contenteditable[contenteditable='true']")
    if not send:
        return True, "DRY: would send message"
    try:
        await human_fill(page, composer, text)
        await pause_human(base=6.0)
        btn = page.locator(
            "button.msg-form__send-button, button.msg-form__send-btn, "
            ".msg-form button[type='submit']"
        )
        if await btn.count() == 0:
            return False, "Send button not found"
        await human_click(page, btn, timeout=10000)
        closed = await cleanup_after_message(page)
        suffix = f" · cleanup: {', '.join(closed)}" if closed else ""
        return True, f"sent{suffix}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:120]


async def inspect_thread(page) -> dict[str, Any]:
    """Open message thread and detect whether the latest bucket is recent."""
    opened = await open_message_thread(page)
    if not opened:
        return {"opened": False, "headers": [], "recent": False, "reason": "message thread did not open"}

    try:
        await human_scroll(page)
        await page.evaluate(
            "() => { const el = document.querySelector('.msg-s-message-list-content'); if (el) el.scrollTop = el.scrollHeight; }"
        )
        await pause_human(base=5.5)
    except Exception:  # noqa: BLE001
        pass

    headers = await read_thread_headers(page)
    recent, last_hdr, reason = latest_header_is_recent(headers)
    return {
        "opened": True,
        "headers": headers,
        "recent": recent,
        "last_header": last_hdr,
        "reason": reason,
    }
