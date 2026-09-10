"""LinkedIn flow dry-run against static HTML fixtures — LI-01, LI-02."""

from __future__ import annotations

import asyncio

import pytest
from patchright.async_api import async_playwright

pytestmark = [pytest.mark.browser]


async def _connect_dry_run(html_uri: str) -> dict:
    from flow_runner import resolve_recipe, run_recipe

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(html_uri, wait_until="domcontentloaded")
        recipe = resolve_recipe("https://www.linkedin.com/in/test/", name="linkedin-connect-or-message")
        assert recipe is not None
        result = await run_recipe(
            page,
            recipe,
            variables={"profile_url": html_uri, "message": "Hi test"},
            profile={},
            send=False,
        )
        await browser.close()
    return result


async def _message_dry_run(html_uri: str) -> dict:
    from flow_runner import resolve_recipe, run_recipe

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(html_uri, wait_until="domcontentloaded")
        recipe = resolve_recipe("https://www.linkedin.com/in/test/", name="linkedin-connect-or-message")
        result = await run_recipe(
            page,
            recipe,
            variables={"profile_url": html_uri, "message": "Hi recruiter"},
            profile={},
            send=False,
        )
        await browser.close()
    return result


async def _classify(html_uri: str) -> str:
    from dm_apply import classify_affordance

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        kind = await classify_affordance(page, html_uri)
        await browser.close()
    return kind


def test_connect_fixture_dry_run_commit(linkedin_html_dir):
    html_uri = (linkedin_html_dir / "profile-connect.html").resolve().as_uri()
    result = asyncio.run(_connect_dry_run(html_uri))
    log = result["steps"]
    assert result.get("committed") or any(e.get("committed") for e in log)
    assert result.get("commit_kind") == "connect" or any(e.get("commit_kind") == "connect" for e in log)


def test_message_fixture_dry_run_commit(linkedin_html_dir):
    html_uri = (linkedin_html_dir / "profile-message.html").resolve().as_uri()
    result = asyncio.run(_message_dry_run(html_uri))
    log = result["steps"]
    assert any(e.get("commit_kind") == "message" for e in log if e.get("committed"))


def test_classify_connect_fixture(linkedin_html_dir):
    html_uri = (linkedin_html_dir / "profile-connect.html").resolve().as_uri()
    assert asyncio.run(_classify(html_uri)) == "connect_top"


def test_classify_message_fixture(linkedin_html_dir):
    html_uri = (linkedin_html_dir / "profile-message.html").resolve().as_uri()
    assert asyncio.run(_classify(html_uri)) == "message"


def test_classify_message_and_connect_prefers_connect(linkedin_html_dir):
    html_uri = (linkedin_html_dir / "profile-message-and-connect.html").resolve().as_uri()
    assert asyncio.run(_classify(html_uri)) == "connect_top"


def test_message_and_connect_fixture_never_clicks_message(linkedin_html_dir):
    html_uri = (linkedin_html_dir / "profile-message-and-connect.html").resolve().as_uri()
    result = asyncio.run(_connect_dry_run(html_uri))
    actions = [s.get("action") for s in result.get("steps", [])]
    assert "click_connect" in actions
    assert "fill" not in actions
    assert any(s.get("action") == "abort_if_connect_on_main" for s in result["steps"])
    assert not any(
        s.get("action") == "click" and s.get("name_regex") == "^More" and s.get("ok")
        for s in result["steps"]
    )


def test_connect_link_fixture_uses_top_card_not_more_menu(linkedin_html_dir):
    html_uri = (linkedin_html_dir / "profile-connect-link.html").resolve().as_uri()
    result = asyncio.run(_connect_dry_run(html_uri))
    assert any(s.get("action") == "click_connect" for s in result["steps"])
    assert not any(
        s.get("action") == "click" and s.get("name_regex") == "^More" and s.get("ok")
        for s in result["steps"]
    )


def test_connect_more_fixture_still_uses_menu_path(linkedin_html_dir):
    html_uri = (linkedin_html_dir / "profile-connect-more.html").resolve().as_uri()
    result = asyncio.run(_connect_dry_run(html_uri))
    steps = result["steps"]
    assert any(s.get("action") == "click_connect" for s in steps)
    assert any(
        s.get("action") == "click" and s.get("name_regex") == "^More" and s.get("ok")
        for s in steps
    )
    assert any(
        s.get("action") == "click" and s.get("role") == "menuitem" and s.get("ok")
        for s in steps
    )


def test_classify_connect_link_fixture(linkedin_html_dir):
    html_uri = (linkedin_html_dir / "profile-connect-link.html").resolve().as_uri()
    assert asyncio.run(_classify(html_uri)) == "connect_top"
