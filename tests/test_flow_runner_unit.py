"""Flow runner unit tests — LI recipe resolution and dry-run."""

from __future__ import annotations

import pytest

from flow_runner import load_recipes, resolve_recipe, _subst


def test_resolve_linkedin_connect_recipe():
    recipe = resolve_recipe("https://www.linkedin.com/in/test/", name="linkedin-connect-or-message")
    assert recipe is not None
    assert recipe["name"] == "linkedin-connect-or-message"
    steps = recipe.get("steps") or []
    assert any(s.get("action") == "click_connect" for s in steps)
    assert any(s.get("commit_kind") == "connect" for s in steps)
    more_idx = next(i for i, s in enumerate(steps) if s.get("name_regex") == "^More")
    connect_idx = next(i for i, s in enumerate(steps) if s.get("action") == "click_connect")
    assert connect_idx < more_idx


def test_subst_variables():
    assert _subst("Hello {name}", {"name": "World"}) == "Hello World"


def test_load_recipes_includes_ats():
    names = {r.get("name") for r in load_recipes()}
    assert "linkedin-connect-or-message" in names
    assert "linkedin-message-only" in names
