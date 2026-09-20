#!/usr/bin/env python3
"""Download LinkedIn profile PDF via browser (Save to PDF menu or page.pdf fallback)."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from browser_session import COOKIES_PATH, close_session, launch_context  # noqa: E402

LINKEDIN_SLUG_RE = re.compile(r"linkedin\.com/in/([\w-]+)", re.I)
OVERFLOW_MENU_RE = re.compile(
    r'<button[^>]*(?:aria-label="([^"]*(?:More actions|More|Resources)[^"]*)"|>([^<]*(?:Resources|More)[^<]*)<)',
    re.I,
)
SAVE_PDF_RE = re.compile(
    r'(?:aria-label="([^"]*Save to PDF[^"]*)"|>([^<]*Save to PDF[^<]*)<)',
    re.I,
)

# Playwright selectors — LinkedIn DOM changes often; keep fallbacks in sync with tests/fixtures.
# Own profile (2025+): top-card overflow is labeled "Resources", not "More".
OVERFLOW_MENU_SELECTORS = (
    'main button:has-text("Resources")',
    'button[aria-label="Resources"]',
    'button[aria-label*="More actions"]',
    'main button[aria-label="More"]',
    'button[aria-label*="More"]',
    'main button.artdeco-dropdown__trigger',
    'section.pv-top-card button.artdeco-dropdown__trigger',
)
SAVE_TO_PDF_SELECTORS = (
    'div[role="menu"] span:has-text("Save to PDF")',
    'div.artdeco-dropdown__content span:has-text("Save to PDF")',
    'li span:has-text("Save to PDF")',
    '[role="menuitem"]:has-text("Save to PDF")',
)


@dataclass
class PdfDownloadResult:
    ok: bool
    path: Path
    message: str
    method: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["path"] = str(self.path)
        return data


def normalize_profile_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise ValueError("LinkedIn profile URL is required")
    if not raw.startswith("http"):
        raw = f"https://{raw.lstrip('/')}"
    parsed = urlparse(raw)
    if "linkedin.com" not in parsed.netloc:
        raise ValueError(f"Not a LinkedIn profile URL: {url}")
    slug = profile_slug(raw)
    return f"https://www.linkedin.com/in/{slug}/"


def profile_slug(profile_url: str) -> str:
    match = LINKEDIN_SLUG_RE.search(profile_url)
    if not match:
        raise ValueError(f"Could not parse LinkedIn slug from: {profile_url}")
    return match.group(1).lower()


def default_dest_path(profile_url: str, *, root: Path | None = None) -> Path:
    base = root or ROOT
    slug = profile_slug(profile_url)
    return base / "state" / "chameleon" / "imports" / f"{slug}-profile.pdf"


def find_more_button_candidates(html: str) -> list[str]:
    """Return overflow-menu button labels/text from static HTML (unit tests)."""
    labels: list[str] = []
    for aria, text in OVERFLOW_MENU_RE.findall(html or ""):
        label = (aria or text or "").strip()
        if label and label not in labels:
            labels.append(label)
    return labels


def find_save_to_pdf_candidates(html: str) -> list[str]:
    """Return Save to PDF menu labels from static HTML (unit tests)."""
    labels: list[str] = []
    for aria, text in SAVE_PDF_RE.findall(html or ""):
        label = (aria or text or "").strip()
        if label and label not in labels:
            labels.append(label)
    return labels


def menu_fixture_has_save_to_pdf(html: str) -> bool:
    return bool(find_save_to_pdf_candidates(html))


async def _wait_for_profile_shell(page: Any, *, timeout_ms: int) -> None:
    try:
        await page.set_viewport_size({"width": 1920, "height": 1080})
    except Exception:
        pass
    await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    try:
        await page.wait_for_selector("main", timeout=min(timeout_ms, 20_000))
    except Exception:
        pass
    try:
        await page.evaluate("window.scrollTo(0, 0)")
    except Exception:
        pass
    await asyncio.sleep(2.0)


async def _page_needs_login(page: Any) -> bool:
    url = (page.url or "").lower()
    if "/login" in url or "/checkpoint" in url:
        return True
    try:
        return bool(
            await page.evaluate(
                """() => {
                  const body = document.body?.innerText || '';
                  if (/sign in|join linkedin/i.test(body.slice(0, 1200))) return true;
                  return !!document.querySelector('form[action*="login"], input#session_key');
                }"""
            )
        )
    except Exception:
        return False


async def _locate_first_visible(page: Any, selectors: tuple[str, ...]) -> Any | None:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                continue
            if not await locator.is_visible():
                continue
            return locator
        except Exception:
            continue
    return None


async def _try_linkedin_save_to_pdf(page: Any, dest_path: Path, *, timeout_ms: int) -> PdfDownloadResult | None:
    overflow = await _locate_first_visible(page, OVERFLOW_MENU_SELECTORS)
    if overflow is None:
        # Role-based fallback (own profile "Resources" button).
        try:
            resources = page.get_by_role("button", name="Resources").first
            if await resources.count() > 0 and await resources.is_visible():
                overflow = resources
        except Exception:
            overflow = None
    if overflow is None:
        return None

    await overflow.click(timeout=5000)
    await asyncio.sleep(0.6)

    save_item = await _locate_first_visible(page, SAVE_TO_PDF_SELECTORS)
    if save_item is None:
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        return None

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with page.expect_download(timeout=timeout_ms) as download_info:
            await save_item.click(timeout=5000)
        download = await download_info.value
        await download.save_as(str(dest_path))
        if dest_path.is_file() and dest_path.stat().st_size > 500:
            return PdfDownloadResult(
                ok=True,
                path=dest_path,
                message="Downloaded via LinkedIn Resources/More → Save to PDF",
                method="linkedin_download",
            )
    except Exception:
        pass

    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass
    return None


async def _fallback_page_pdf(page: Any, dest_path: Path) -> PdfDownloadResult:
    """Print current page to PDF — layout differs from LinkedIn's official export."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    await page.emulate_media(media="print")
    await page.pdf(
        path=str(dest_path),
        format="A4",
        print_background=True,
        margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"},
    )
    if dest_path.is_file() and dest_path.stat().st_size > 500:
        return PdfDownloadResult(
            ok=True,
            path=dest_path,
            message=(
                "Saved via browser page.pdf() fallback — not LinkedIn's official Save to PDF layout; "
                "import quality may differ"
            ),
            method="page_pdf",
        )
    return PdfDownloadResult(
        ok=False,
        path=dest_path,
        message="page.pdf() produced an empty or missing file",
        method="page_pdf",
    )


async def download_linkedin_profile_pdf(
    profile_url: str,
    dest_path: Path | str,
    *,
    headless: bool = False,
    timeout_ms: int = 90_000,
    use_cookies: bool = True,
) -> PdfDownloadResult:
    """Navigate to a LinkedIn profile and save a PDF to *dest_path*."""
    url = normalize_profile_url(profile_url)
    out = Path(dest_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    if use_cookies and not COOKIES_PATH.exists():
        return PdfDownloadResult(
            ok=False,
            path=out,
            message=f"LinkedIn cookies not found at {COOKIES_PATH} — run linkedin-login first",
            method="error",
        )

    pw: Any | None = None
    browser: Any | None = None
    ctx: Any | None = None
    try:
        pw, browser, ctx = await launch_context(headless=headless, use_cookies=use_cookies)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        await _wait_for_profile_shell(page, timeout_ms=timeout_ms)

        if await _page_needs_login(page):
            return PdfDownloadResult(
                ok=False,
                path=out,
                message="LinkedIn session expired or not logged in — refresh cookies via linkedin-login",
                method="error",
            )

        menu_result = await _try_linkedin_save_to_pdf(page, out, timeout_ms=min(timeout_ms, 45_000))
        if menu_result and menu_result.ok:
            return menu_result

        fallback = await _fallback_page_pdf(page, out)
        if fallback.ok:
            return fallback

        detail = "Could not find Resources/More → Save to PDF"
        if menu_result is None:
            detail = "Resources/More → Save to PDF menu not found (works on your own profile when logged in)"
        return PdfDownloadResult(ok=False, path=out, message=detail, method="error")
    except Exception as exc:
        return PdfDownloadResult(ok=False, path=out, message=str(exc), method="error")
    finally:
        if pw is not None:
            await close_session(pw=pw, browser=browser, context=ctx)


def resolve_linkedin_url(explicit: str, track_id: str | None) -> str:
    if explicit.strip():
        return normalize_profile_url(explicit)
    from track_store import load_profile, resolve_track  # noqa: WPS433

    prof = load_profile(resolve_track(track_id))
    url = str(prof.get("linkedin_url") or "").strip()
    if not url:
        raise ValueError("Pass --linkedin-url or set linkedin_url in applicant-profile.json")
    return normalize_profile_url(url)


async def _cli_async(args: argparse.Namespace) -> int:
    url = resolve_linkedin_url(args.linkedin_url or "", args.track)
    dest = Path(args.output).expanduser() if args.output else default_dest_path(url)
    result = await download_linkedin_profile_pdf(
        url,
        dest,
        headless=args.headless,
        timeout_ms=args.timeout_ms,
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    elif result.ok:
        print(f"Saved LinkedIn profile PDF → {result.path}")
        print(f"  method: {result.method}")
        if result.method == "page_pdf":
            print(f"  note: {result.message}")
    else:
        print(f"ERROR: {result.message}", file=sys.stderr)
    return 0 if result.ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download LinkedIn profile PDF via browser")
    parser.add_argument("--linkedin-url", default="", help="Profile URL (default: track applicant-profile)")
    parser.add_argument("--track", default=None, help="Career track for default LinkedIn URL")
    parser.add_argument("--output", default="", help="Destination PDF path")
    parser.add_argument("--headless", action="store_true", help="Run browser headless")
    parser.add_argument("--timeout-ms", type=int, default=90_000, dest="timeout_ms")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return asyncio.run(_cli_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
