"""Regression: Connect/Message must match the profile URL, not feed suggestions."""

from __future__ import annotations

import asyncio

import pytest
from patchright.async_api import async_playwright

pytestmark = pytest.mark.browser


def test_invite_href_vanity():
    from linkedin_ui import invite_href_vanity, profile_vanity_from_url

    url = "https://www.linkedin.com/in/ashish-upadhyay-monu/"
    assert profile_vanity_from_url(url) == "ashish-upadhyay-monu"
    assert invite_href_vanity("/preload/custom-invite/?vanityName=suraj-raveshia-38953613a") == "suraj-raveshia-38953613a"
    assert invite_href_vanity("/preload/custom-invite/?vanityName=ashish-upadhyay-monu") == "ashish-upadhyay-monu"


def test_clear_stale_acceptance_drops_false_accepted_at():
    import dm_state

    prof = "https://www.linkedin.com/in/ashish-upadhyay-monu/"
    key = dm_state.normalize_profile_url(prof)
    state = {
        "profiles": {
            key: {
                "profile_url": prof,
                "connect_requested_at": "2026-09-22T12:00:00",
                "accepted_at": "2026-09-22T12:05:00",
                "message_sent_at": None,
            }
        }
    }
    assert dm_state.clear_stale_acceptance(state, prof) is True
    assert dm_state.get(state, prof)["accepted_at"] is None
    assert dm_state.status_of(dm_state.get(state, prof)) == dm_state.STATUS_CONNECT_PENDING


@pytest.mark.asyncio
async def test_ashish_fixture_no_foreign_connect(linkedin_html_dir):
    from dm_apply import classify_affordance
    from dm_followup import is_connected
    from linkedin_ui import connect_locator_on_main, has_connect_on_main

    html_uri = (linkedin_html_dir / "profile-ashish-follow-compose.html").resolve().as_uri()
    prof_url = "https://www.linkedin.com/in/ashish-upadhyay-monu/"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(html_uri, wait_until="domcontentloaded")
        assert await has_connect_on_main(page, profile_url=prof_url) is False
        assert await connect_locator_on_main(page, profile_url=prof_url) is None
        assert await classify_affordance(page, prof_url, navigate_url=html_uri) == "message"
        ok, reason = await is_connected(page, prof_url, navigate_url=html_uri)
        assert ok is True
        assert "Message" in reason
        await browser.close()
