"""LinkedIn Easy Apply flow dry-run against static HTML fixtures."""

from __future__ import annotations

import asyncio

import pytest

pytestmark = [pytest.mark.browser]


async def _run_open(html_uri: str, job_url: str) -> dict:
    from flow_runner import resolve_recipe, run_recipe
    from linkedin_easy_apply import modal_visible
    from patchright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(html_uri, wait_until="domcontentloaded")
        recipe = resolve_recipe(job_url, name="linkedin-easy-apply-open")
        assert recipe is not None
        result = await run_recipe(
            page,
            recipe,
            variables={"job_url": html_uri},
            profile={},
            send=False,
        )
        visible = await modal_visible(page)
        await browser.close()
    return {"flow": result, "modal_visible": visible}


def test_easy_apply_open_fixture(linkedin_html_dir):
    html_uri = (linkedin_html_dir / "job-easy-apply-step1.html").resolve().as_uri()
    out = asyncio.run(_run_open(html_uri, "https://www.linkedin.com/jobs/view/4100012345/"))
    assert out["modal_visible"] is True
