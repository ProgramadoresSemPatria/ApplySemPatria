"""Feature tests for tag-as-applied and Applika sync steps."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import applied_state
import applika_apply
from applications_ui_data import _tracking_action_states, job_to_card
from tests.helpers.jobs import linkedin_dm_job


def test_tracking_states_untagged_with_applika(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(applied_state, "APPLIED_PATH", tmp_path / "applied.json")
    job = linkedin_dm_job()
    states = _tracking_action_states(job, {}, applika_on=True)
    assert states["tag_applied"]["done"] is False
    assert states["tag_applied"]["available"] is True
    assert states["applika"]["done"] is False
    assert states["applika"]["status_text"] == "tag first"


def test_tracking_states_tagged_and_sent(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(applied_state, "APPLIED_PATH", tmp_path / "applied.json")
    from registry import job_key

    job = linkedin_dm_job()
    jk = job_key(job)
    applied_state.tag_job(jk)
    applied_state.set_applika_result(jk, status=applied_state.APPLIKA_SENT)
    states = _tracking_action_states(job, applied_state.load_applied_entries(), applika_on=True)
    assert states["tag_applied"]["done"] is True
    assert states["applika"]["done"] is True


def test_tracking_on_all_cards_even_when_human_review(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(applied_state, "APPLIED_PATH", tmp_path / "applied.json")
    job = linkedin_dm_job(filter_result="needs_review")
    card = job_to_card(
        job,
        section="linkedin_review",
        dm={"profiles": {}},
        email_to=set(),
        email_keys=set(),
        url_done=set(),
        li_cfg={"form_link_message_enabled": True},
        applied_entries={},
        applika_on=True,
    )
    assert card["application_steps_enabled"] is False
    assert card["actions"]["tag_applied"]["available"] is True
    assert card["actions"]["applika"]["status_text"] == "tag first"


def test_tag_and_sync_calls_applika_when_enabled(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(applied_state, "APPLIED_PATH", tmp_path / "applied.json")
    job = linkedin_dm_job()
    with patch.object(applika_apply, "applika_sync_enabled", return_value=True), patch.object(
        applika_apply, "send_job_to_applika", return_value={"ok": True, "message": "Sent to Applika."}
    ) as send_mock:
        result = applika_apply.tag_and_sync(job, track_id="ai-engineer")
    assert result["ok"] is True
    assert "Applika" in result["message"]
    send_mock.assert_called_once()


def test_tag_without_applika_enabled(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(applied_state, "APPLIED_PATH", tmp_path / "applied.json")
    job = linkedin_dm_job()
    with patch.object(applika_apply, "applika_sync_enabled", return_value=False):
        result = applika_apply.tag_and_sync(job, track_id="ai-engineer")
    assert result["ok"] is True
    assert result["message"] == "Tagged as applied."


def test_ui_server_tracking_actions(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(applied_state, "APPLIED_PATH", tmp_path / "applied.json")
    from ui_server import run_action

    job = linkedin_dm_job()
    jk = "https://www.linkedin.com/posts/test-activity-123"
    with patch("ui_server._find_job", return_value=job), patch.object(
        applika_apply, "tag_and_sync", return_value={"ok": True, "message": "Tagged as applied and sent to Applika."}
    ) as tag_mock:
        result = run_action("tag_applied", jk)
    assert result["ok"] is True
    tag_mock.assert_called_once()

    applied_state.tag_job(jk)
    with patch("ui_server._find_job", return_value=job), patch.object(
        applika_apply, "send_job_to_applika", return_value={"ok": False, "message": "CLI failed"}
    ) as send_mock:
        result = run_action("applika_send", jk)
    assert result["ok"] is False
    send_mock.assert_called_once()
