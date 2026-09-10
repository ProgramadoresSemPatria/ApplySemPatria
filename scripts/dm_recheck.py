#!/usr/bin/env python3
"""Rigorous, visible re-check of LinkedIn connect affordances.

Scopes to the profile top-card action bar (not random "More" buttons elsewhere)
and dumps the exact controls + the opened More-menu items, using broad regexes
for Connect / Invite. Proves whether a profile is connectable.
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from browser_session import close_session, launch_context  # noqa: E402
from linkedin_ui import CONNECT_BUTTON_NAME_RE, is_connect_affordance_label  # noqa: E402
MESSAGE_RE = re.compile(r"^message", re.I)

PROFILES = [
    "https://www.linkedin.com/in/isleenhc/",
    "https://www.linkedin.com/in/manuela-g%C3%A9nova/",
    "https://www.linkedin.com/in/marcelodesantis/",
    "https://www.linkedin.com/in/gustavogarozzo/",
    "https://www.linkedin.com/in/tomcleary/",
]


async def top_card_buttons(page):
    """Return (locator, list[str]) of buttons within the profile top card only."""
    # The top card is the first <section> in <main> that holds the name + actions.
    scope = page.locator("main section").first
    btns = scope.get_by_role("button")
    names = []
    n = await btns.count()
    for i in range(min(n, 25)):
        try:
            nm = (await btns.nth(i).get_attribute("aria-label")) or (await btns.nth(i).inner_text())
        except Exception:
            nm = ""
        nm = " ".join((nm or "").split())
        if nm:
            names.append(nm)
    return btns, names


async def check(page, url: str) -> None:
    print(f"\n=== {url} ===")
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await asyncio.sleep(2.5)
    btns, names = await top_card_buttons(page)
    print("  top-card buttons:", names)

    # Direct Connect on top card?
    connect = page.locator("main section").first.get_by_role("button", name=CONNECT_BUTTON_NAME_RE)
    if await connect.count() > 0:
        print("  -> HAS top-card Connect/Invite button:", await connect.first.get_attribute("aria-label") or await connect.first.inner_text())
        return
    if await page.locator("main section").first.get_by_role("button", name=MESSAGE_RE).count() > 0:
        print("  -> HAS Message button (connected/open profile)")
        return

    # Open the profile 'More actions' button (scoped to top card)
    more = page.locator("main section").first.get_by_role("button", name=re.compile(r"^more", re.I))
    print("  top-card 'More' buttons found:", await more.count())
    if await more.count() == 0:
        print("  -> no More in top card; follow-only")
        return
    await more.first.click()
    await asyncio.sleep(1.2)
    # Dump menu items (both menuitem role and buttons inside the dropdown)
    items = page.get_by_role("menuitem")
    labels = []
    for i in range(await items.count()):
        try:
            nm = (await items.nth(i).get_attribute("aria-label")) or (await items.nth(i).inner_text())
        except Exception:
            nm = ""
        nm = " ".join((nm or "").split())
        if nm:
            labels.append(nm)
    print("  More-menu items:", labels)
    has_connect = any(is_connect_affordance_label(x) for x in labels)
    print("  -> CONNECTABLE via More menu" if has_connect else "  -> follow-only (no Connect/Invite in menu)")
    await page.keyboard.press("Escape")
    await asyncio.sleep(0.5)


async def main() -> None:
    pw, browser, ctx = await launch_context(headless=False)
    try:
        page = await ctx.new_page()
        for url in PROFILES:
            try:
                await check(page, url)
            except Exception as exc:  # noqa: BLE001
                print(f"  error: {exc}")
        print("\n(Leaving browser open 8s so you can look.)")
        await asyncio.sleep(8)
    finally:
        await close_session(pw=pw, browser=browser, context=ctx)


if __name__ == "__main__":
    asyncio.run(main())
