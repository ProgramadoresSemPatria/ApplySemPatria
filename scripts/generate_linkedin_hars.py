#!/usr/bin/env python3
"""Record HAR fixtures from the local LinkedIn profile mock server.

Usage:
  python scripts/generate_linkedin_hars.py

Writes tests/fixtures/har/*.har — commit these files after updating HTML fixtures.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from tests.helpers.linkedin_har import HAR_DIR, HAR_SLUGS  # noqa: E402
from tests.helpers.linkedin_mock_server import MOCK_HOST, MOCK_PORT, LinkedInMockServer, profile_url  # noqa: E402


async def _record(har_name: str, url: str, out: Path) -> None:
    from patchright.async_api import async_playwright

    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            record_har_path=str(out),
            record_har_mode="minimal",
            service_workers="block",
        )
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(200)
        await context.close()
        await browser.close()

    if not out.is_file() or out.stat().st_size < 50:
        raise RuntimeError(f"HAR not written: {out}")


def main() -> int:
    server = LinkedInMockServer()
    server.start()
    try:
        for har_name, slug in HAR_SLUGS.items():
            url = profile_url(MOCK_HOST, MOCK_PORT, slug)
            out = HAR_DIR / f"{har_name}.har"
            print(f"Recording {har_name} ← {url}")
            asyncio.run(_record(har_name, url, out))
            print(f"  → {out} ({out.stat().st_size} bytes)")
    finally:
        server.stop()
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
