"""HAR + fixture regression: Ursula-style profile (Connect link + Message compose).

LinkedIn often renders Connect as ``<a href=\"/preload/custom-invite/...\">`` alongside
a Message compose link. Must classify as connect_top, not connected, and commit connect.
"""

from __future__ import annotations

import asyncio

import pytest

from tests.helpers.judge import expect_classify, expect_flow_commit
from tests.helpers.linkedin_har import mock_profile_url, run_with_har

pytestmark = pytest.mark.har

URSULA_SLUG = "ursula-morales-03328283"


async def _flow_dry_run(page):
    from flow_runner import resolve_recipe, run_recipe

    recipe = resolve_recipe("https://www.linkedin.com/in/test/", name="linkedin-connect-or-message")
    assert recipe is not None
    return await run_recipe(
        page,
        recipe,
        variables={"profile_url": page.url, "message": "Hi Ursula"},
        profile={},
        send=False,
    )


async def _classify(page, url: str) -> str:
    from dm_apply import classify_affordance

    return await classify_affordance(page, url)


async def _is_connected(page, url: str):
    from dm_followup import is_connected

    return await is_connected(page, url)


def test_ursula_har_classify_connect_top():
    url = mock_profile_url(URSULA_SLUG)
    kind = asyncio.run(run_with_har("profile-ursula-connect-link", url, lambda p: _classify(p, url), fast_classify=True))
    verdict = expect_classify(kind, "connect_top")
    assert verdict, verdict.reason


def test_ursula_har_is_not_connected_yet():
    url = mock_profile_url(URSULA_SLUG)

    async def _run(page):
        return await _is_connected(page, url)

    ok, reason = asyncio.run(run_with_har("profile-ursula-connect-link", url, _run, fast_classify=True))
    assert ok is False
    assert "Connect visible" in reason


def test_ursula_har_flow_commits_connect_not_message():
    url = mock_profile_url(URSULA_SLUG)
    result = asyncio.run(run_with_har("profile-ursula-connect-link", url, _flow_dry_run))
    verdict = expect_flow_commit(result, "connect")
    assert verdict, verdict.reason
    assert not any(s.get("commit_kind") == "message" and s.get("committed") for s in result.get("steps", []))


def test_ursula_fixture_click_connect_opens_invite_modal(linkedin_html_dir):
    from linkedin_ui import click_connect_on_main, invite_modal_visible

    html_uri = (linkedin_html_dir / "profile-ursula-connect-link.html").resolve().as_uri()

    async def _run() -> bool:
        from patchright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(html_uri, wait_until="domcontentloaded")
            prof = "https://www.linkedin.com/in/ursula-morales-03328283/"
            clicked = await click_connect_on_main(page, profile_url=prof)
            modal = await invite_modal_visible(page)
            await browser.close()
        return clicked and modal

    assert asyncio.run(_run())
