"""Shared headed-browser session (patchright) with LinkedIn cookies.

Prefers the user's installed Google Chrome and a persistent profile directory
over Patchright's bundled "Chrome for Testing" automation build.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

BROWSERS_PATH = Path.home() / ".linkedin-mcp/patchright-browsers"
PROFILE_DIR = Path.home() / ".linkedin-mcp/profile"
COOKIES_PATH = Path.home() / ".linkedin-mcp/cookies.json"

# Patchright bundle — automation build; avoid unless explicitly requested.
TEST_CHROME_EXECUTABLE = (
    BROWSERS_PATH
    / "chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
)

REAL_CHROME_CANDIDATES = (
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary"),
    Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    Path("/usr/bin/google-chrome"),
    Path("/usr/bin/google-chrome-stable"),
    Path("/usr/bin/chromium-browser"),
)


def resolve_chrome_executable() -> str | None:
    """Return a real Chrome/Chromium binary, not Chrome for Testing by default."""
    override = os.environ.get("JOBSEARCH_CHROME_EXECUTABLE", "").strip()
    if override:
        path = Path(override).expanduser()
        return str(path) if path.is_file() else None

    if os.environ.get("JOBSEARCH_USE_TEST_CHROME") == "1" and TEST_CHROME_EXECUTABLE.is_file():
        return str(TEST_CHROME_EXECUTABLE)

    for candidate in REAL_CHROME_CANDIDATES:
        if candidate.is_file():
            return str(candidate)
    return None


def browser_launch_kwargs(*, headless: bool) -> dict[str, Any]:
    """Launch options: real Chrome > channel=chrome > Patchright default chromium."""
    kwargs: dict[str, Any] = {
        "headless": headless,
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    executable = resolve_chrome_executable()
    if executable:
        kwargs["executable_path"] = executable
        return kwargs

    channel = os.environ.get("JOBSEARCH_BROWSER_CHANNEL", "chrome").strip()
    if channel and channel.lower() not in {"off", "none", "0"}:
        kwargs["channel"] = channel
    return kwargs


def browser_mode_label() -> str:
    exe = resolve_chrome_executable()
    if exe:
        name = Path(exe).name
        if "Chrome for Testing" in exe:
            return "chrome-for-testing"
        return f"chrome ({name})"
    channel = os.environ.get("JOBSEARCH_BROWSER_CHANNEL", "chrome").strip()
    if channel and channel.lower() not in {"off", "none", "0"}:
        return f"channel={channel}"
    return "patchright-chromium"


def load_cookies() -> list[dict[str, Any]]:
    if COOKIES_PATH.exists():
        try:
            return json.loads(COOKIES_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
    return []


async def close_session(*, pw: Any, browser: Any | None, context: Any | None) -> None:
    try:
        if context is not None:
            await context.close()
        elif browser is not None:
            await browser.close()
    except Exception:
        pass
    await pw.stop()


async def launch_context(
    *,
    headless: bool = False,
    use_cookies: bool = True,
    use_profile: bool = True,
) -> tuple[Any, Any | None, Any]:
    """Launch patchright. Returns (playwright, browser, context).

    When *use_profile* and ~/.linkedin-mcp/profile exist, opens a persistent
    context (real session history + cookies). Otherwise injects cookies.json.

    Caller should finish with ``await close_session(pw=pw, browser=browser, context=ctx)``.
    """
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(BROWSERS_PATH))
    from patchright.async_api import async_playwright

    pw = await async_playwright().start()
    kwargs = browser_launch_kwargs(headless=headless)
    context_kwargs: dict[str, Any] = {
        "viewport": {"width": 1360, "height": 940},
        "locale": "en-US",
    }

    ephemeral = os.environ.get("JOBSEARCH_EPHEMERAL_BROWSER") == "1" or not use_profile
    if not ephemeral and PROFILE_DIR.exists():
        try:
            ctx = await pw.chromium.launch_persistent_context(
                str(PROFILE_DIR),
                **kwargs,
                **context_kwargs,
            )
            print(f"  browser: {browser_mode_label()} · persistent profile", file=sys.stderr)
            return pw, ctx.browser, ctx
        except Exception as exc:
            print(f"  browser: profile launch failed ({exc}); using ephemeral session", file=sys.stderr)

    launch_attempts: list[dict[str, Any]] = [kwargs]
    if "channel" in kwargs:
        fallback = {k: v for k, v in kwargs.items() if k != "channel"}
        launch_attempts.append(fallback)

    last_exc: Exception | None = None
    for attempt in launch_attempts:
        try:
            browser = await pw.chromium.launch(**attempt)
            ctx = await browser.new_context(**context_kwargs)
            if use_cookies:
                cookies = load_cookies()
                if cookies:
                    await ctx.add_cookies(cookies)
            print(f"  browser: {browser_mode_label()} · ephemeral + cookies", file=sys.stderr)
            return pw, browser, ctx
        except Exception as exc:
            last_exc = exc

    await pw.stop()
    raise RuntimeError(f"Could not launch browser ({last_exc})") from last_exc
