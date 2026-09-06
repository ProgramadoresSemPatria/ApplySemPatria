#!/usr/bin/env python3
"""LinkedIn UI dismiss helpers — Premium upsell, chat overlay close."""

from __future__ import annotations

import re

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
    """Dismiss anything blocking the page (Premium modal, etc.)."""
    actions: list[str] = []
    if await dismiss_premium_modal(page):
        actions.append("premium_modal")
    return actions


async def cleanup_after_message(page) -> list[str]:
    """After send or thread inspect: close chat + dismiss upsells."""
    actions: list[str] = []
    if await close_message_thread(page):
        actions.append("chat_closed")
    if await dismiss_premium_modal(page):
        actions.append("premium_modal")
    return actions
