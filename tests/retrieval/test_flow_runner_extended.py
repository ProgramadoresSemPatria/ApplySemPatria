"""Extended flow_runner coverage."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from flow_runner import (  # noqa: E402
    _branch_when_matches,
    _exists,
    _locator,
    _run_steps,
    _subst,
    load_recipes,
    resolve_recipe,
)


def test_load_recipes_skips_bad_json(tmp_path, monkeypatch):
    flows = tmp_path / "flows"
    flows.mkdir()
    (flows / "good.json").write_text(json.dumps({"name": "test", "match": {}}), encoding="utf-8")
    (flows / "bad.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr("flow_runner.FLOWS_DIR", flows)
    monkeypatch.setattr("flow_runner.LEARNED_DIR", tmp_path / "learned")
    recipes = load_recipes()
    assert any(r.get("name") == "test" for r in recipes)


def test_resolve_recipe_by_domain(tmp_path, monkeypatch):
    flows = tmp_path / "flows"
    flows.mkdir()
    (flows / "gh.json").write_text(
        json.dumps({"name": "gh", "match": {"domains": ["greenhouse.io"]}, "steps": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr("flow_runner.FLOWS_DIR", flows)
    monkeypatch.setattr("flow_runner.LEARNED_DIR", tmp_path / "learned")
    recipe = resolve_recipe("https://boards.greenhouse.io/acme/jobs/1")
    assert recipe and recipe["name"] == "gh"


@pytest.mark.asyncio
async def test_exists_and_branch_when():
    page = MagicMock()
    loc = MagicMock()
    loc.count = AsyncMock(return_value=1)
    page.get_by_role = MagicMock(return_value=loc)
    assert await _exists(page, {"always": True}, {}) is True
    assert await _exists(page, {"exists": {"role": "button", "name_regex": "^Connect"}}, {}) is True
    with patch("linkedin_ui.has_connect_on_main", AsyncMock(return_value=True)):
        assert await _branch_when_matches(page, {"connect_on_main": True}, {}) is True


@pytest.mark.asyncio
async def test_run_steps_goto_and_sleep():
    page = MagicMock()
    page.goto = AsyncMock()
    log: list = []
    steps = [
        {"action": "goto", "target": "https://example.com"},
        {"action": "sleep", "seconds": 0.01},
    ]
    with patch("asyncio.sleep", new=AsyncMock()):
        await _run_steps(page, steps, variables={}, profile={}, send=False, log=log)
    assert page.goto.await_count >= 1
    assert log


def test_locator_selector():
    page = MagicMock()
    page.locator.return_value = MagicMock()
    _locator(page, {"selector": "#email"}, {})
    page.locator.assert_called()


@pytest.mark.asyncio
async def test_run_steps_click_fill_upload(tmp_path, monkeypatch):
    page = MagicMock()
    loc = MagicMock()
    loc.count = AsyncMock(return_value=1)
    nth = MagicMock()
    nth.click = AsyncMock()
    nth.fill = AsyncMock()
    loc.nth = MagicMock(return_value=nth)
    loc.first = loc
    loc.set_input_files = AsyncMock()
    page.locator = MagicMock(return_value=loc)
    page.get_by_role = MagicMock(return_value=loc)
    page.get_by_label = MagicMock(return_value=loc)
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF")

    log: list = []
    steps = [
        {"action": "click", "role": "button", "name_regex": "^Submit", "destructive": True},
        {"action": "fill", "selector": "#name", "value": "Test User"},
        {"action": "upload", "selector": "input[type=file]", "profile_key": "resume_path"},
        {"action": "select", "selector": "#country", "value": "Brazil"},
        {"action": "check", "selector": "#terms"},
        {"action": "assert_visible", "selector": "#done"},
    ]
    profile = {"resume_path": str(resume)}
    await _run_steps(page, steps, variables={}, profile=profile, send=False, log=log)
    assert len(log) >= 5
    assert any(r["action"] == "click" for r in log)


@pytest.mark.asyncio
async def test_run_steps_linkedin_actions():
    page = MagicMock()
    log: list = []
    steps = [
        {"action": "abort_if_connect_on_main", "optional": True},
        {"action": "dismiss_premium", "optional": True},
        {"action": "close_chat", "optional": True},
    ]
    with patch("linkedin_ui.has_connect_on_main", AsyncMock(return_value=False)):
        with patch("linkedin_ui.dismiss_premium_modal", AsyncMock(return_value=False)):
            with patch("linkedin_ui.close_message_thread", AsyncMock(return_value=False)):
                await _run_steps(page, steps, variables={}, profile={}, send=False, log=log)
    assert len(log) == 3


def test_subst_variables():
    assert _subst("Hello {name}", {"name": "World"}) == "Hello World"
