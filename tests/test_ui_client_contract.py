"""Keep bundled UI and ui_server API contract in sync (version + bulk actions)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_HTML = ROOT / "ui" / "applications" / "index.html"


def _read_ui_constants() -> tuple[int, list[str]]:
    text = UI_HTML.read_text(encoding="utf-8")
    version_match = re.search(r"const UI_CLIENT_VERSION = (\d+);", text)
    actions_match = re.search(r"const REQUIRED_BULK_ACTIONS = (\[[^\]]+\]);", text)
    assert version_match, "UI_CLIENT_VERSION missing from index.html"
    assert actions_match, "REQUIRED_BULK_ACTIONS missing from index.html"
    version = int(version_match.group(1))
    actions = ast.literal_eval(actions_match.group(1))
    assert isinstance(actions, list)
    return version, actions


def test_ui_html_matches_server_api_contract():
    from ui_server import SUPPORTED_BULK_ACTIONS, UI_VERSION

    client_version, required_actions = _read_ui_constants()
    assert client_version == UI_VERSION
    assert list(required_actions) == list(SUPPORTED_BULK_ACTIONS)


def test_server_supports_current_meta():
    from ui_server import SUPPORTED_BULK_ACTIONS, UI_VERSION, server_supports_client, ui_meta_payload

    meta = ui_meta_payload()
    assert meta["version"] == UI_VERSION
    assert meta["bulk_actions"] == list(SUPPORTED_BULK_ACTIONS)
    assert server_supports_client(meta) is True


def test_server_supports_client_rejects_old_meta():
    from ui_server import server_supports_client

    assert server_supports_client({"ui_approval": True, "version": 3, "bulk_actions": ["dm_process_all"]}) is False
    assert server_supports_client({"ui_approval": True, "version": 4, "bulk_actions": ["dm_process_all", "email_process_all"]}) is False
    assert server_supports_client({"ui_approval": True, "version": 5, "bulk_actions": ["dm_process_all"]}) is False
