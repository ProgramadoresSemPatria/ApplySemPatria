"""Playwright e2e: bulk DM pipeline runs connect for stale connect_pending rows."""

from __future__ import annotations

from playwright.sync_api import Page, expect

from tests.e2e.test_ui_dashboard import wait_for_toast_text


def test_bulk_dm_stale_connect_pending_still_runs_connect_phase(
    mock_ui_server_bulk_dm_legacy_match, page: Page
):
    """Regression: connect_pending in state must not skip the connect subprocess."""
    port, captured = mock_ui_server_bulk_dm_legacy_match
    page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
    page.locator("#bulkDmBtn").click()
    wait_for_toast_text(page, "send_connections")
    assert captured["apply_cmds"], "expected at least connect subprocess"
    connect_cmd = captured["apply_cmds"][0]
    joined = " ".join(str(part) for part in connect_cmd)
    assert "dm_apply.py" in joined
    assert "--send" in joined
    expect(page.locator("#bulkDmBtn")).not_to_be_disabled()
