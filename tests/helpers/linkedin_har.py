"""HAR replay helpers for LinkedIn flow tests."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

from patchright.async_api import Browser, BrowserContext, Page, async_playwright

from tests.helpers.linkedin_mock_server import MOCK_HOST, MOCK_PORT, profile_url

HAR_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "har"

# Slugs align with linkedin_mock_server.PROFILE_MAP and *.har filenames.
HAR_SLUGS: dict[str, str] = {
    "profile-connect": "test-connect",
    "profile-message": "test-message",
    "profile-pending": "test-pending",
    "profile-connect-more": "test-connect-more",
    "profile-connected": "test-connected",
    "profile-connected-only": "test-connected-only",
}

T = TypeVar("T")


def mock_profile_url(slug: str) -> str:
    return profile_url(MOCK_HOST, MOCK_PORT, slug)


def har_path(name: str) -> Path:
    p = HAR_DIR / f"{name}.har"
    if not p.is_file():
        raise FileNotFoundError(f"Missing HAR fixture: {p} (run scripts/generate_linkedin_hars.py)")
    return p


def list_required_hars() -> list[Path]:
    return [har_path(name) for name in HAR_SLUGS]


async def run_with_har(
    har_name: str,
    url: str,
    fn: Callable[[Page], Awaitable[T]],
    *,
    fast_classify: bool = False,
) -> T:
    """Open page via HAR replay at ``url`` and run async callback."""
    if fast_classify:
        import dm_apply

        _orig_sleep = asyncio.sleep

        async def _fast_sleep(secs: float) -> None:
            await _orig_sleep(min(secs, 0.05))

        dm_apply.asyncio.sleep = _fast_sleep  # type: ignore[method-assign]

    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(headless=True)
        context: BrowserContext = await browser.new_context(service_workers="block")
        await context.route_from_har(
            str(har_path(har_name)),
            url="**/*",
            not_found="abort",
        )
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        result = await fn(page)
        await context.close()
        await browser.close()
        return result
