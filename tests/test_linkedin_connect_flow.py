"""Regression suite: LinkedIn connect flow guarantees.

Locks in behavior from the connect-flow fix:
  - Top-card Connect is detected (button, link, + Connect, pvs-profile-actions).
  - click_connect runs before the More-menu path in the recipe.
  - When Connect is on the profile, More menu and Message paths are skipped.
  - When Connect is only in More, the menu path still runs.
  - Flow execution never probes More during branch/recipe matching.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest
from patchright.async_api import async_playwright

pytestmark = [pytest.mark.browser]


async def _run_flow(html_uri: str, *, monkeypatch: pytest.MonkeyPatch | None = None) -> dict[str, Any]:
    from flow_runner import resolve_recipe, run_recipe

    if monkeypatch is not None:

        async def _forbidden_probe(_page):  # noqa: ANN001
            raise AssertionError("more_menu_has_connect must not run during flow execution")

        monkeypatch.setattr("linkedin_ui.more_menu_has_connect", _forbidden_probe)

    recipe = resolve_recipe("https://www.linkedin.com/in/test/", name="linkedin-connect-or-message")
    assert recipe is not None
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(html_uri, wait_until="domcontentloaded")
        result = await run_recipe(
            page,
            recipe,
            variables={"profile_url": html_uri, "message": "Hi test"},
            profile={},
            send=False,
        )
        await browser.close()
    return result


def _step_names(result: dict[str, Any]) -> list[str]:
    return [str(s.get("action")) for s in result.get("steps", [])]


def test_recipe_linear_with_guards_before_more_and_message():
    from flow_runner import resolve_recipe

    steps = resolve_recipe("https://www.linkedin.com/in/x/", name="linkedin-connect-or-message")["steps"]
    connect_idx = next(i for i, s in enumerate(steps) if s.get("action") == "click_connect")
    more_idx = next(i for i, s in enumerate(steps) if s.get("name_regex") == "^More")
    msg_idx = next(i for i, s in enumerate(steps) if "Message" in (s.get("selector") or ""))
    abort_idxs = [i for i, s in enumerate(steps) if s.get("action") == "abort_if_connect_on_main"]

    assert connect_idx < more_idx < msg_idx
    assert len(abort_idxs) == 2
    assert abort_idxs[0] < more_idx
    assert abort_idxs[1] < msg_idx
    assert "branches" not in resolve_recipe("https://www.linkedin.com/in/x/", name="linkedin-connect-or-message")
    menu_steps = [s for s in steps if s.get("role") == "menuitem"]
    assert menu_steps and "connect" in menu_steps[0]["name_regex"].lower()


@pytest.mark.parametrize(
    "fixture_name",
    [
        "profile-connect.html",
        "profile-connect-plus.html",
        "profile-connect-link.html",
        "profile-connect-pvs-actions.html",
        "profile-message-and-connect.html",
    ],
)
def test_top_card_connect_fixtures_detect_and_skip_more_menu(
    linkedin_html_dir, fixture_name: str, monkeypatch: pytest.MonkeyPatch
):
    html_uri = (linkedin_html_dir / fixture_name).resolve().as_uri()
    result = asyncio.run(_run_flow(html_uri, monkeypatch=monkeypatch))

    assert "click_connect" in _step_names(result)
    assert any(s.get("action") == "click_connect" and "clicked" in s.get("note", "") for s in result["steps"])
    assert not any(
        s.get("action") == "click" and s.get("name_regex") == "^More" and s.get("ok")
        for s in result["steps"]
    )
    assert "fill" not in _step_names(result)


def test_menu_only_fixture_still_opens_more_and_clicks_menuitem(
    linkedin_html_dir, monkeypatch: pytest.MonkeyPatch
):
    html_uri = (linkedin_html_dir / "profile-connect-more.html").resolve().as_uri()
    result = asyncio.run(_run_flow(html_uri, monkeypatch=monkeypatch))
    steps = result["steps"]

    assert any(s.get("action") == "click_connect" and s.get("note") == "connect not found" for s in steps)
    assert any(s.get("action") == "click" and s.get("name_regex") == "^More" and s.get("ok") for s in steps)
    assert any(s.get("action") == "click" and s.get("role") == "menuitem" and s.get("ok") for s in steps)


def test_message_only_fixture_commits_message_not_connect(linkedin_html_dir, monkeypatch: pytest.MonkeyPatch):
    html_uri = (linkedin_html_dir / "profile-message.html").resolve().as_uri()
    result = asyncio.run(_run_flow(html_uri, monkeypatch=monkeypatch))

    assert any(s.get("action") == "click_connect" and s.get("note") == "connect not found" for s in result["steps"])
    assert any(s.get("committed") and s.get("commit_kind") == "message" for s in result["steps"])
    assert not any(s.get("commit_kind") == "connect" and s.get("committed") for s in result["steps"])


async def _ui_probe(html_uri: str) -> dict[str, bool]:
    from linkedin_ui import has_connect_on_main, has_more_on_top_card

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(html_uri, wait_until="domcontentloaded")
        out = {
            "connect": await has_connect_on_main(page),
            "more": await has_more_on_top_card(page),
        }
        await browser.close()
    return out


def test_has_connect_on_main_for_pvs_actions_bar(linkedin_html_dir):
    html_uri = (linkedin_html_dir / "profile-connect-pvs-actions.html").resolve().as_uri()
    probes = asyncio.run(_ui_probe(html_uri))
    assert probes["connect"] is True
    assert probes["more"] is True


def test_has_connect_on_main_false_when_only_in_menu(linkedin_html_dir):
    html_uri = (linkedin_html_dir / "profile-connect-more.html").resolve().as_uri()
    probes = asyncio.run(_ui_probe(html_uri))
    assert probes["connect"] is False
    assert probes["more"] is True


@pytest.mark.parametrize(
    "fixture_name,expected",
    [
        ("profile-connect.html", "connect_top"),
        ("profile-connect-more.html", "connect_more"),
        ("profile-message.html", "message"),
        ("profile-message-and-connect.html", "connect_top"),
    ],
)
def test_classify_affordance_priority(linkedin_html_dir, fixture_name: str, expected: str):
    from dm_apply import classify_affordance

    html_uri = (linkedin_html_dir / fixture_name).resolve().as_uri()

    async def _run() -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            kind = await classify_affordance(page, html_uri)
            await browser.close()
        return kind

    assert asyncio.run(_run()) == expected


def test_branch_when_matching_is_side_effect_free(monkeypatch: pytest.MonkeyPatch):
    """Branch helper must not open More — connect_more uses static More presence only."""

    async def _run() -> None:
        from flow_runner import _branch_when_matches

        page = AsyncMock()
        probe = AsyncMock(side_effect=AssertionError("must not probe menu"))
        monkeypatch.setattr("linkedin_ui.more_menu_has_connect", probe)
        monkeypatch.setattr("linkedin_ui.has_connect_on_main", AsyncMock(return_value=False))
        monkeypatch.setattr("linkedin_ui.has_more_on_top_card", AsyncMock(return_value=True))

        matched = await _branch_when_matches(
            page,
            {"more_on_top_card": True, "not_connect_on_main": True},
            {},
        )
        assert matched is True
        probe.assert_not_called()

    asyncio.run(_run())
