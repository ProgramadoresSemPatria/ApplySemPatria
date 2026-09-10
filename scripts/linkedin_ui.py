#!/usr/bin/env python3
"""LinkedIn UI dismiss helpers — Premium upsell, chat overlay close."""

from __future__ import annotations

import re
from typing import Any

from human_pacing import human_click, pause_poll

PREMIUM_HINT = re.compile(r"Premium|Try 1 month|Unlock your next career", re.I)

# LinkedIn profile top-card Connect variants: "Connect", "+ Connect", "Invite … to connect"
CONNECT_BUTTON_NAME_RE = re.compile(r"^\+?\s*connect$|^invite.*to connect$", re.I)
CONNECT_AFFORDANCE_RE = re.compile(r"connect|invite.*to connect", re.I)
CONNECT_AFFORDANCE_SKIP_RE = re.compile(r"remove connection|following|pending", re.I)


def connect_button_name_pattern() -> str:
    """Playwright ``name_regex`` for profile Connect buttons."""
    return r"^\+?\s*connect$|^invite.*to connect$"


def main_profile_section(page):
    """Top-card action bar within ``<main>`` (not posts / chat dock)."""
    return page.locator("main section").first


def profile_action_scopes(page):
    """Likely containers for profile Connect / More (top card only)."""
    return [
        page.locator("main .pvs-profile-actions").first,
        page.locator("main .pv-top-card-v2-ctas").first,
        main_profile_section(page),
        page.locator("main").first,
    ]


def _connect_locator_candidates(scope) -> list:
    """Playwright locators for profile Connect, in priority order."""
    return [
        scope.get_by_role("button", name=CONNECT_BUTTON_NAME_RE),
        scope.get_by_role("link", name=CONNECT_BUTTON_NAME_RE),
        scope.locator(
            "button[aria-label*='Invite'][aria-label*='connect' i], "
            "a[aria-label*='Invite'][aria-label*='connect' i], "
            "button[aria-label*='to connect' i], a[aria-label*='to connect' i]"
        ),
        scope.locator("button, a").filter(has_text=re.compile(r"^\+?\s*Connect$", re.I)),
    ]


async def connect_locator_on_main(page):
    """First visible Connect control on the profile top card, or ``None``."""
    seen: set[str] = set()
    for scope in profile_action_scopes(page):
        try:
            if await scope.count() == 0:
                continue
        except Exception:  # noqa: BLE001
            continue
        for loc in _connect_locator_candidates(scope):
            try:
                count = await loc.count()
            except Exception:  # noqa: BLE001
                continue
            for idx in range(min(count, 5)):
                try:
                    node = loc.nth(idx)
                    if not await node.is_visible():
                        continue
                    label = " ".join(
                        (
                            (await node.get_attribute("aria-label"))
                            or (await node.inner_text())
                            or ""
                        ).split()
                    )
                    if not label or CONNECT_AFFORDANCE_SKIP_RE.search(label):
                        continue
                    if not (
                        CONNECT_BUTTON_NAME_RE.search(label)
                        or CONNECT_AFFORDANCE_RE.search(label)
                    ):
                        continue
                    key = f"{label}:{idx}"
                    if key in seen:
                        continue
                    seen.add(key)
                    return node
                except Exception:  # noqa: BLE001
                    continue
    return None


async def has_connect_on_main(page) -> bool:
    """True when a Connect / Invite affordance is visible on the profile top card."""
    return await connect_locator_on_main(page) is not None


async def click_connect_on_main(page) -> bool:
    """Click the profile top-card Connect / Invite control."""
    node = await connect_locator_on_main(page)
    if node is None:
        return False
    await human_click(page, node, timeout=15000)
    return True


async def has_more_on_top_card(page) -> bool:
    """True when the profile top card exposes a More actions button."""
    section = main_profile_section(page)
    more_re = re.compile(r"^More", re.I)
    if await section.get_by_role("button", name=more_re).count() > 0:
        return True
    return await page.locator("main").first.get_by_role("button", name=more_re).count() > 0


async def wait_for_profile_top_card(page, *, timeout_ms: int = 20000) -> bool:
    """Wait until the profile action bar exposes Connect, Message, More, or Pending."""
    import asyncio

    section = main_profile_section(page)
    deadline = asyncio.get_event_loop().time() + timeout_ms / 1000
    while asyncio.get_event_loop().time() < deadline:
        if await has_connect_on_main(page):
            return True
        for role, pattern in (
            ("button", re.compile(r"^Message", re.I)),
            ("button", re.compile(r"^More", re.I)),
            ("button", re.compile(r"^Pending", re.I)),
        ):
            try:
                if await section.get_by_role(role, name=pattern).count() > 0:
                    return True
            except Exception:  # noqa: BLE001
                pass
        await pause_poll(base=0.4)
    return False


async def more_menu_has_connect(page) -> bool:
    """Open profile More menu and return True if Connect / Invite is listed."""
    if await has_connect_on_main(page):
        return False
    section = main_profile_section(page)
    more = section.get_by_role("button", name=re.compile(r"^More", re.I))
    if await more.count() == 0:
        more = page.locator("main").first.get_by_role("button", name=re.compile(r"^More", re.I))
    if await more.count() == 0:
        return False
    try:
        await human_click(page, more, timeout=10000)
        await pause_poll(base=0.8)
        items = page.get_by_role("menuitem")
        labels: list[str] = []
        for i in range(await items.count()):
            try:
                nm = (await items.nth(i).get_attribute("aria-label")) or (await items.nth(i).inner_text())
            except Exception:  # noqa: BLE001
                nm = ""
            labels.append(" ".join((nm or "").split()))
        await page.keyboard.press("Escape")
        if any(re.search(r"remove connection|^following$", x, re.I) for x in labels):
            return False
        return any(is_connect_affordance_label(x) for x in labels)
    except Exception:  # noqa: BLE001
        try:
            await page.keyboard.press("Escape")
        except Exception:  # noqa: BLE001
            pass
        return False


def is_connect_affordance_label(label: str) -> bool:
    """True for Connect / Invite-to-connect menu labels (not Remove connection / Follow)."""
    text = " ".join((label or "").split())
    if not text or CONNECT_AFFORDANCE_SKIP_RE.search(text):
        return False
    return bool(CONNECT_AFFORDANCE_RE.search(text))


async def dismiss_premium_modal(page) -> bool:
    """Click X on LinkedIn Premium / upsell modals if visible."""
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
                await human_click(page, btn, timeout=5000)
                return True
        btn = box.locator("button").filter(has=page.locator("svg"))
        if await btn.count() > 0:
            await human_click(page, btn, timeout=5000)
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        btn = page.locator(
            "button.artdeco-modal__dismiss, button[aria-label='Dismiss'][class*='artdeco']"
        )
        if await btn.count() > 0:
            await human_click(page, btn, timeout=5000)
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


async def close_message_thread(page) -> bool:
    """Close the messaging overlay (X on the chat bubble)."""
    try:
        loc = page.get_by_role(
            "button", name=re.compile(r"Close your conversation", re.I)
        )
        if await loc.count() > 0:
            await human_click(page, loc, timeout=5000)
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
                await human_click(page, btn, timeout=5000)
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
        await pause_poll(base=0.4)
    return False


async def _click_first_visible(loc, page, *, name: str) -> dict[str, Any]:
    """Click the first visible, enabled match from a locator collection."""
    count = await loc.count()
    last_error = ""
    for idx in range(count):
        btn = loc.nth(idx)
        try:
            if not await btn.is_visible():
                continue
            for _ in range(12):
                if await btn.is_enabled():
                    break
                await pause_poll(base=0.25)
            await human_click(page, loc, index=idx, timeout=15000)
            return {"clicked": True, "strategy": name, "index": idx}
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)[:160]
            try:
                await human_click(page, loc, index=idx, timeout=8000, force=True)
                return {"clicked": True, "strategy": f"{name}_force", "index": idx}
            except Exception as force_exc:  # noqa: BLE001
                last_error = str(force_exc)[:160]
    return {"clicked": False, "error": last_error or f"{name} not clickable"}


async def click_easy_apply_button(page) -> dict[str, Any]:
    """Click LinkedIn's Easy Apply control (button or link) on a live job page."""
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
            click = await _click_first_visible(loc, page, name=name)
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
