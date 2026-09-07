"""Helpers for applications dashboard Playwright e2e tests."""

from __future__ import annotations

import time
from typing import Any

import pytest
from playwright.sync_api import Page


def wait_for_mock_action(
    captured: dict[str, Any],
    page: Page,
    *,
    timeout_ms: int = 30_000,
) -> dict[str, Any]:
    """Poll mock UI server until run_action records an action."""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        action = captured.get("last_action")
        if action:
            return action
        page.wait_for_timeout(50)
    pytest.fail(f"mock action not recorded within {timeout_ms}ms")


def wait_for_mock_bulk_action(
    captured: dict[str, Any],
    page: Page,
    *,
    timeout_ms: int = 30_000,
) -> dict[str, Any]:
    """Poll mock UI server until bulk DM follow-up is recorded."""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        bulk = captured.get("last_bulk_action")
        if bulk:
            return bulk
        page.wait_for_timeout(50)
    pytest.fail(f"mock bulk action not recorded within {timeout_ms}ms")
