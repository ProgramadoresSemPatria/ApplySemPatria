"""Shared headed-browser session (patchright) with LinkedIn cookies.

Used by dm_apply.py and url_apply.py so the user can visually follow automation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

BROWSERS_PATH = Path.home() / ".linkedin-mcp/patchright-browsers"
CHROME_EXECUTABLE = (
    BROWSERS_PATH
    / "chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
)
# Legacy path name (~/.linkedin-mcp) — browser cookies only, no LinkedIn MCP server.
COOKIES_PATH = Path.home() / ".linkedin-mcp/cookies.json"


def load_cookies() -> list[dict[str, Any]]:
    if COOKIES_PATH.exists():
        try:
            return json.loads(COOKIES_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
    return []


async def launch_context(*, headless: bool = False, use_cookies: bool = True):
    """Launch a patchright chromium context. Returns (playwright, browser, context).

    Caller is responsible for closing browser and stopping playwright, e.g.:

        pw, browser, ctx = await launch_context(headless=False)
        try:
            page = await ctx.new_page()
            ...
        finally:
            await browser.close()
            await pw.stop()
    """
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS_PATH)
    from patchright.async_api import async_playwright

    pw = await async_playwright().start()
    launch_kwargs: dict[str, Any] = {"headless": headless}
    if CHROME_EXECUTABLE.exists():
        launch_kwargs["executable_path"] = str(CHROME_EXECUTABLE)
    browser = await pw.chromium.launch(**launch_kwargs)
    context = await browser.new_context(viewport={"width": 1360, "height": 940})
    if use_cookies:
        cookies = load_cookies()
        if cookies:
            await context.add_cookies(cookies)
    return pw, browser, context
