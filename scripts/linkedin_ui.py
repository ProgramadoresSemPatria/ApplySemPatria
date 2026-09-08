#!/usr/bin/env python3
"""LinkedIn UI dismiss helpers — Premium upsell, chat overlay close."""

from __future__ import annotations

import re
from typing import Any

PREMIUM_HINT = re.compile(r"Premium|Try 1 month|Unlock your next career", re.I)


async def dismiss_premium_modal(page) -> bool:
    """Click X on LinkedIn Premium / upsell modals if visible."""
    import asyncio

    try:
        dialog = page.locator("div[role='dialog']").filter(has_text=PREMIUM_HINT)
        if await dialog.count() == 0:
            dialog = page.locator(".artdeco-modal, [data-test-modal]").filter(has_text=PREMIUM_HINT)
        if await dialog.count() == 0:
            return False
        box = dialog.first
        for sel in (
            "button.artdeco-modal__dismiss",
            "button[aria-label='Dismiss']",
            "button[aria-label='Close']",
            "button[data-test-modal-close-btn]",
        ):
            btn = box.locator(sel)
            if await btn.count() > 0:
                await btn.first.click(timeout=5000)
                await asyncio.sleep(0.5)
                return True
        # Top-right icon-only close in modal header
        btn = box.locator("button").filter(has=page.locator("svg"))
        if await btn.count() > 0:
            await btn.first.click(timeout=5000)
            await asyncio.sleep(0.5)
            return True
    except Exception:  # noqa: BLE001
        pass
    # Global fallback (single visible dismiss on page)
    try:
        btn = page.locator(
            "button.artdeco-modal__dismiss, button[aria-label='Dismiss'][class*='artdeco']"
        )
        if await btn.count() > 0:
            await btn.first.click(timeout=5000)
            await asyncio.sleep(0.5)
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


async def close_message_thread(page) -> bool:
    """Close the messaging overlay (X on the chat bubble)."""
    import asyncio

    try:
        loc = page.get_by_role(
            "button", name=re.compile(r"Close your conversation", re.I)
        )
        if await loc.count() > 0:
            await loc.first.click(timeout=5000)
            await asyncio.sleep(0.4)
            return True
    except Exception:  # noqa: BLE001
        pass
    for sel in (
        "button.msg-overlay-bubble-header__control--close",
        "button[data-control-name='overlay.close_conversation_window']",
        ".msg-overlay-conversation-bubble-header button[aria-label*='Close']",
        "button.msg-overlay-bubble-header__controls button:last-child",
    ):
        try:
            btn = page.locator(sel)
            if await btn.count() > 0:
                await btn.first.click(timeout=5000)
                await asyncio.sleep(0.4)
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


async def dismiss_blocking_dialogs(page) -> list[str]:
    """Dismiss anything blocking the page (Premium modal, chat overlay, etc.)."""
    actions: list[str] = []
    if await close_message_thread(page):
        actions.append("chat_closed")
    if await dismiss_premium_modal(page):
        actions.append("premium_modal")
    return actions


async def wait_for_job_detail_ready(page, *, timeout_ms: int = 45000) -> bool:
    """Wait until a LinkedIn job detail page has loaded its primary actions."""
    import asyncio

    selectors = (
        "a[aria-label*='Easy Apply' i]",
        "button[aria-label*='Easy Apply' i]",
        "button[aria-label*='Applied' i]",
        "a[aria-label*='Applied' i]",
        "button.jobs-apply-button",
        "a.jobs-apply-button",
        ".jobs-unified-top-card",
        ".job-details-jobs-unified-top-card",
    )
    deadline = asyncio.get_event_loop().time() + timeout_ms / 1000
    while asyncio.get_event_loop().time() < deadline:
        for sel in selectors:
            loc = page.locator(sel)
            try:
                if await loc.count() > 0 and await loc.first.is_visible():
                    return True
            except Exception:  # noqa: BLE001
                continue
        await asyncio.sleep(0.4)
    return False


async def _click_first_visible(loc, *, name: str) -> dict[str, Any]:
    """Click the first visible, enabled match from a locator collection."""
    import asyncio

    count = await loc.count()
    last_error = ""
    for idx in range(count):
        btn = loc.nth(idx)
        try:
            if not await btn.is_visible():
                continue
            await btn.scroll_into_view_if_needed(timeout=8000)
            await asyncio.sleep(0.35)
            for _ in range(12):
                if await btn.is_enabled():
                    break
                await asyncio.sleep(0.25)
            await btn.click(timeout=15000)
            await asyncio.sleep(1.8)
            return {"clicked": True, "strategy": name, "index": idx}
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)[:160]
            try:
                await btn.click(force=True, timeout=8000)
                await asyncio.sleep(1.8)
                return {"clicked": True, "strategy": f"{name}_force", "index": idx}
            except Exception as force_exc:  # noqa: BLE001
                last_error = str(force_exc)[:160]
    return {"clicked": False, "error": last_error or f"{name} not clickable"}


async def click_easy_apply_button(page) -> dict[str, Any]:
    """Click LinkedIn's Easy Apply control (button or link) on a live job page."""
    import asyncio

    await dismiss_blocking_dialogs(page)
    await wait_for_job_detail_ready(page, timeout_ms=45000)

    strategies: list[tuple[str, Any]] = [
        ("link_aria_easy_apply", page.locator("a[aria-label*='Easy Apply' i]")),
        ("button_aria_easy_apply", page.locator("button[aria-label*='Easy Apply' i]")),
        ("role_link_easy_apply", page.get_by_role("link", name=re.compile(r"Easy Apply", re.I))),
        ("role_button_easy_apply", page.get_by_role("button", name=re.compile(r"Easy Apply", re.I))),
        ("jobs_apply_button", page.locator("button.jobs-apply-button, a.jobs-apply-button")),
        ("primary_apply", page.locator(".jobs-apply-button--top-card a, .jobs-apply-button--top-card button, .jobs-s-apply a, .jobs-s-apply button")),
        (
            "control_inapply",
            page.locator(
                "button[data-control-name='jobdetails_topcard_inapply'], "
                "a[data-control-name='jobdetails_topcard_inapply']"
            ),
        ),
        (
            "text_easy_apply",
            page.locator("a, button").filter(has_text=re.compile(r"^Easy Apply$", re.I)),
        ),
    ]

    last_error = ""
    for name, loc in strategies:
        try:
            if await loc.count() == 0:
                continue
            click = await _click_first_visible(loc, name=name)
            if click.get("clicked"):
                return click
            last_error = click.get("error") or last_error
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)[:160]
            continue

    return {"clicked": False, "error": last_error or "Easy Apply button not found"}


async def cleanup_after_message(page) -> list[str]:
    """After send or thread inspect: close chat + dismiss upsells."""
    actions: list[str] = []
    if await close_message_thread(page):
        actions.append("chat_closed")
    if await dismiss_premium_modal(page):
        actions.append("premium_modal")
    return actions
