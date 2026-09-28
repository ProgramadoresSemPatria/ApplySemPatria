#!/usr/bin/env python3
"""LinkedIn UI dismiss helpers — Premium upsell, chat overlay close."""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

from human_pacing import human_click, pause_poll

PREMIUM_HINT = re.compile(r"Premium|Try 1 month|Unlock your next career", re.I)

# LinkedIn profile top-card Connect variants: "Connect", "+ Connect", "Invite … to connect"
CONNECT_BUTTON_NAME_RE = re.compile(r"^\+?\s*connect$|^invite.*to connect$", re.I)
CONNECT_AFFORDANCE_RE = re.compile(r"connect|invite.*to connect", re.I)
CONNECT_AFFORDANCE_SKIP_RE = re.compile(r"remove connection|following|pending", re.I)
MESSAGE_BUTTON_NAME_RE = re.compile(r"^Message", re.I)
MESSAGE_COMPOSE_HREF_RE = re.compile(r"messaging/(compose|thread)", re.I)


def connect_button_name_pattern() -> str:
    """Playwright ``name_regex`` for profile Connect buttons."""
    return r"^\+?\s*connect$|^invite.*to connect$"


def profile_vanity_from_url(url: str) -> str:
    m = re.search(r"linkedin\.com/in/([^/?#]+)", url or "", re.I)
    if m:
        return m.group(1).strip("/").lower()
    m = re.search(r"/in/([^/?#]+)/?", url or "", re.I)
    return m.group(1).strip("/").lower() if m else ""


def invite_href_vanity(href: str) -> str:
    m = re.search(r"[?&]vanityName=([^&]+)", href or "", re.I)
    if not m:
        return ""
    return urllib.parse.unquote(m.group(1)).strip().lower()


def _narrow_profile_scope(scope_index: int) -> bool:
    """Top-card scopes only — excludes whole-``main`` feed/recommendations."""
    return scope_index <= 4


def main_profile_section(page):
    """Top-card action bar within ``<main>`` (not posts / chat dock)."""
    return page.locator("main section").first


def profile_action_scopes(page):
    """Likely containers for profile Connect / More (top card only)."""
    return [
        page.locator("main .pvs-profile-actions").first,
        page.locator("main .pv-top-card-v2-ctas").first,
        page.locator("main .pv-top-card").first,
        main_profile_section(page),
        page.locator("main:has(> h1)").first,
        page.locator("main").first,
    ]


def _connect_locator_candidates(scope) -> list:
    """Playwright locators for profile Connect, in priority order."""
    return [
        scope.locator(
            "a[href*='custom-invite'], a[href*='preload/custom-invite'], "
            "a[componentkey*='ConnectButton' i]"
        ),
        scope.get_by_role("button", name=CONNECT_BUTTON_NAME_RE),
        scope.get_by_role("link", name=CONNECT_BUTTON_NAME_RE),
        scope.locator(
            "button[aria-label*='Invite'][aria-label*='connect' i], "
            "a[aria-label*='Invite'][aria-label*='connect' i], "
            "button[aria-label*='to connect' i], a[aria-label*='to connect' i]"
        ),
        scope.locator("button, a").filter(has_text=re.compile(r"^\+?\s*Connect$", re.I)),
    ]


async def _connect_matches_profile(
    node,
    *,
    target_vanity: str,
    scope_index: int,
) -> bool:
    href = (await node.get_attribute("href")) or ""
    link_vanity = invite_href_vanity(href)
    if link_vanity:
        return bool(target_vanity) and link_vanity == target_vanity
    if not _narrow_profile_scope(scope_index):
        return False
    return True


async def connect_locator_on_main(page, *, profile_url: str | None = None):
    """First visible Connect for the profile being viewed, or ``None``."""
    target_vanity = profile_vanity_from_url(profile_url or page.url)
    seen: set[str] = set()
    for scope_index, scope in enumerate(profile_action_scopes(page)):
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
            for idx in range(min(count, 8)):
                try:
                    node = loc.nth(idx)
                    if not await node.is_visible():
                        continue
                    if not await _connect_matches_profile(
                        node, target_vanity=target_vanity, scope_index=scope_index
                    ):
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
                    key = f"{label}:{idx}:{scope_index}"
                    if key in seen:
                        continue
                    seen.add(key)
                    return node
                except Exception:  # noqa: BLE001
                    continue
    return None


async def has_connect_on_main(page, *, profile_url: str | None = None) -> bool:
    """True when a Connect affordance exists for this profile (not feed suggestions)."""
    return await connect_locator_on_main(page, profile_url=profile_url) is not None


async def message_locator_on_main(page, *, profile_url: str | None = None):
    """First visible Message control on the profile top card, or ``None``."""
    _ = profile_url  # reserved for compose-recipient checks
    seen: set[str] = set()
    for scope_index, scope in enumerate(profile_action_scopes(page)):
        if not _narrow_profile_scope(scope_index):
            continue
        try:
            if await scope.count() == 0:
                continue
        except Exception:  # noqa: BLE001
            continue
        for role in ("button", "link"):
            try:
                loc = scope.get_by_role(role, name=MESSAGE_BUTTON_NAME_RE)
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
                    if not label or not MESSAGE_BUTTON_NAME_RE.search(label):
                        continue
                    key = f"{label}:{idx}"
                    if key in seen:
                        continue
                    seen.add(key)
                    return node
                except Exception:  # noqa: BLE001
                    continue
        try:
            compose = scope.locator(
                "a[href*='messaging/compose'][aria-label*='Message' i], "
                "a[href*='messaging/compose'][aria-label*='message' i], "
                "button[aria-label*='Message' i], a[aria-label*='Message' i]"
            )
            count = await compose.count()
        except Exception:  # noqa: BLE001
            continue
        for idx in range(min(count, 5)):
            try:
                node = compose.nth(idx)
                if not await node.is_visible():
                    continue
                href = (await node.get_attribute("href")) or ""
                if href and not MESSAGE_COMPOSE_HREF_RE.search(href):
                    continue
                aria = (await node.get_attribute("aria-label")) or ""
                text = (await node.inner_text()) or ""
                label = aria or text
                if not MESSAGE_BUTTON_NAME_RE.search(label):
                    continue
                key = f"compose:{href}:{idx}"
                if key in seen:
                    continue
                seen.add(key)
                return node
            except Exception:  # noqa: BLE001
                continue
    return None


async def has_message_on_main(page, *, profile_url: str | None = None) -> bool:
    """True when a Message affordance is visible on the profile top card only."""
    return await message_locator_on_main(page, profile_url=profile_url) is not None


INVITE_MODAL_BUTTON_RE = re.compile(r"Send without|Not now|Continue without Premium|Continue for free", re.I)


async def invite_modal_visible(page) -> bool:
    """True when the post-Connect invitation dialog is open."""
    try:
        if await page.get_by_role("button", name=INVITE_MODAL_BUTTON_RE).count() > 0:
            return True
        if await page.get_by_role("link", name=INVITE_MODAL_BUTTON_RE).count() > 0:
            return True
    except Exception:  # noqa: BLE001
        return False
    return False


async def click_connect_on_main(page, *, profile_url: str | None = None) -> bool:
    """Click the profile top-card Connect / Invite control."""
    node = await connect_locator_on_main(page, profile_url=profile_url or page.url)
    if node is None:
        return False
    await human_click(page, node, timeout=15000)
    for _ in range(25):
        if await invite_modal_visible(page):
            return True
        await pause_poll(base=0.15)
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
