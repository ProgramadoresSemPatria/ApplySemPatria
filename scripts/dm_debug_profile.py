#!/usr/bin/env python3
"""Debug Message affordance on a LinkedIn profile (headed)."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from browser_session import close_session, launch_context  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.linkedin.com/in/luciadeledda/"


async def main() -> None:
    pw, browser, ctx = await launch_context(headless=False)
    try:
        page = await ctx.new_page()
        print(f"goto {URL}")
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(4)
        info = await page.evaluate(
            """() => {
              const main = document.querySelector('main');
              const links = [...(main?.querySelectorAll('a') || [])].filter(a =>
                /message/i.test(a.innerText || a.getAttribute('aria-label') || ''));
              const buttons = [...(main?.querySelectorAll('button') || [])].filter(b =>
                /message/i.test(b.innerText || b.getAttribute('aria-label') || ''));
              return {
                title: document.title,
                links: links.slice(0, 8).map(a => ({
                  text: (a.innerText || '').trim().slice(0, 60),
                  href: a.href,
                  aria: a.getAttribute('aria-label'),
                })),
                buttons: buttons.slice(0, 8).map(b => ({
                  text: (b.innerText || '').trim().slice(0, 60),
                  aria: b.getAttribute('aria-label'),
                })),
                pending: !!(main?.innerText || '').match(/Pending/i),
                premium: !!document.body.innerText.match(/Try 1 month|Unlock your next career move/i),
              };
            }"""
        )
        print(json.dumps(info, indent=2))
        await asyncio.sleep(8)
    finally:
        await close_session(pw=pw, browser=browser, context=ctx)


if __name__ == "__main__":
    asyncio.run(main())
