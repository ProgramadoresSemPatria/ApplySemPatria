"""Regression: LinkedIn Connect button labels include '+ Connect' variant."""

from __future__ import annotations

import re

from linkedin_ui import (
    CONNECT_BUTTON_NAME_RE,
    connect_button_name_pattern,
    is_connect_affordance_label,
)


def test_connect_button_name_matches_plus_prefix():
    for label in ("Connect", "+ Connect", "+  Connect", "Invite Gabriela to connect", "Invite to connect"):
        assert CONNECT_BUTTON_NAME_RE.search(label), label


def test_connect_button_name_rejects_follow_and_remove():
    for label in ("+ Follow", "Remove connection", "Following", "Pending"):
        assert not CONNECT_BUTTON_NAME_RE.search(label), label


def test_connect_menu_affordance_labels():
    assert is_connect_affordance_label("+ Connect")
    assert is_connect_affordance_label("Invite John to connect")
    assert not is_connect_affordance_label("+ Follow")
    assert not is_connect_affordance_label("Remove connection")


def test_flow_recipe_tries_top_card_connect_before_more_menu():
    from flow_runner import resolve_recipe

    recipe = resolve_recipe("https://www.linkedin.com/in/test/", name="linkedin-connect-or-message")
    steps = recipe["steps"]
    assert any(s.get("action") == "click_connect" for s in steps)
    more_idx = next(i for i, s in enumerate(steps) if s.get("name_regex") == "^More")
    connect_idx = next(i for i, s in enumerate(steps) if s.get("action") == "click_connect")
    assert connect_idx < more_idx
    menu_connect = [
        s for s in steps if s.get("role") == "menuitem" and "connect" in (s.get("name_regex") or "").lower()
    ]
    assert menu_connect
