"""E2E-style scenario tests for DM connect → check → send pipeline fixes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import dm_state


def _connect_pending_entry(profile: str) -> dict:
    return {
        "company": "Acme AI",
        "role": "AI Engineer",
        "job_key": "jk-1",
        "profile_url": profile,
        "connect_requested_at": "2026-09-22T12:00:00",
        "accepted_at": None,
        "message_sent_at": None,
    }


def test_candidates_for_connect_action_includes_stale_connect_pending():
    from dm_apply import candidates_for_connect_action, profile_url_for
    from tests.helpers.jobs import linkedin_dm_job

    job = linkedin_dm_job()
    prof = profile_url_for(job)
    state = {
        "profiles": {
            dm_state.normalize_profile_url(prof): _connect_pending_entry(prof),
        }
    }
    out = candidates_for_connect_action(state, [job])
    assert len(out) == 1


def test_candidates_for_connect_action_excludes_message_sent():
    from dm_apply import candidates_for_connect_action, profile_url_for
    from tests.helpers.jobs import linkedin_dm_job

    job = linkedin_dm_job()
    prof = profile_url_for(job)
    key = dm_state.normalize_profile_url(prof)
    entry = _connect_pending_entry(prof)
    entry["message_sent_at"] = "2026-09-23T12:00:00"
    state = {"profiles": {key: entry}}
    assert candidates_for_connect_action(state, [job]) == []


def test_reset_stale_connect_pending():
    prof = "https://www.linkedin.com/in/recruiter-test/"
    state = {"profiles": {dm_state.normalize_profile_url(prof): _connect_pending_entry(prof)}}
    assert dm_state.reset_stale_connect_pending(state, prof) is True
    entry = dm_state.get(state, prof)
    assert entry is not None
    assert entry.get("connect_requested_at") is None
    assert dm_state.status_of(entry) == dm_state.STATUS_NONE


def test_reset_stale_connect_pending_noop_when_already_accepted():
    prof = "https://www.linkedin.com/in/recruiter-test/"
    entry = _connect_pending_entry(prof)
    entry["accepted_at"] = "2026-09-23T12:00:00"
    state = {"profiles": {dm_state.normalize_profile_url(prof): entry}}
    assert dm_state.reset_stale_connect_pending(state, prof) is False


@pytest.mark.asyncio
async def test_is_connected_connect_visible_not_accepted():
    import dm_followup

    page = MagicMock()
    page.goto = AsyncMock()
    with patch("dm_followup.pause_page_settle", AsyncMock()):
        with patch("dm_followup.drift_mouse", AsyncMock()):
            with patch("dm_followup.dismiss_blocking_dialogs", AsyncMock(return_value=False)):
                with patch("dm_followup.shows_pending", AsyncMock(return_value=False)):
                    with patch("linkedin_ui.has_connect_on_main", AsyncMock(return_value=True)):
                        ok, reason = await dm_followup.is_connected(page, "https://www.linkedin.com/in/r/")
    assert ok is False
    assert "Connect visible" in reason


@pytest.mark.asyncio
async def test_is_connected_message_on_top_card():
    import dm_followup

    page = MagicMock()
    page.goto = AsyncMock()
    with patch("dm_followup.pause_page_settle", AsyncMock()):
        with patch("dm_followup.drift_mouse", AsyncMock()):
            with patch("dm_followup.dismiss_blocking_dialogs", AsyncMock(return_value=False)):
                with patch("dm_followup.shows_pending", AsyncMock(return_value=False)):
                    with patch("linkedin_ui.has_connect_on_main", AsyncMock(return_value=False)):
                        with patch("dm_followup.has_top_card_message", AsyncMock(return_value=True)):
                            ok, reason = await dm_followup.is_connected(page, "https://www.linkedin.com/in/r/")
    assert ok is True
    assert "Message" in reason


@pytest.mark.asyncio
async def test_check_phase_resets_stale_connect_when_connect_visible(monkeypatch):
    import dm_followup

    prof = "https://www.linkedin.com/in/recruiter-test/"
    state = {"profiles": {dm_state.normalize_profile_url(prof): _connect_pending_entry(prof)}}
    saved: list[dict] = []

    monkeypatch.setattr(dm_state, "load", lambda: state)
    monkeypatch.setattr(dm_state, "save", lambda data: saved.append(data))
    monkeypatch.setattr(dm_followup, "load_track_profile", lambda _t: {"dm_message_template": "Hi {role}"})
    monkeypatch.setattr(dm_followup, "resolve_recipe", lambda *a, **k: {"name": "linkedin-message-only"})

    page = MagicMock()
    ctx = MagicMock()
    ctx.new_page = AsyncMock(return_value=page)
    monkeypatch.setattr(dm_followup, "launch_context", AsyncMock(return_value=(MagicMock(), MagicMock(), ctx)))
    monkeypatch.setattr(dm_followup, "close_session", AsyncMock())
    monkeypatch.setattr(
        dm_followup,
        "is_connected",
        AsyncMock(return_value=(False, "Connect visible — need to connect first")),
    )
    monkeypatch.setattr(dm_followup, "cleanup_after_message", AsyncMock(return_value=[]))
    monkeypatch.setattr("table_refresh.refresh_applications_table", lambda: None)

    entries = [_connect_pending_entry(prof)]
    entries[0]["profile_url"] = prof

    await dm_followup.run(entries, send=False, headless=True, phase="check")

    entry = dm_state.get(state, prof)
    assert entry is not None
    assert entry.get("connect_requested_at") is None
    assert saved


@patch("ui_server._run_apply_cmd")
def test_bulk_dm_connect_phase_when_only_stale_connect_pending(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
    from ui_server import run_bulk_dm_followup

    from tests.helpers.jobs import linkedin_dm_job

    job = linkedin_dm_job()
    prof = job["recruiter_profile_url"]
    dm_data = {
        "profiles": {
            dm_state.normalize_profile_url(prof): _connect_pending_entry(prof),
        }
    }

    keys = ["ai-engineer|linkedin|acme ai|ai engineer"]
    with patch("dm_state.load", return_value=dm_data):
        with patch("dm_apply.collect_candidates", return_value=[job]):
            with patch("dm_followup.pending_profiles", return_value=[]):
                with patch("dm_followup.filter_entries_by_job_keys", return_value=[]):
                    result = run_bulk_dm_followup(track="ai-engineer", job_keys=keys)

    assert result["ok"] is True
    assert mock_run.call_count >= 1
    connect_cmd = mock_run.call_args_list[0][0][0]
    assert "dm_apply.py" in " ".join(connect_cmd)


def test_dm_apply_main_includes_connect_pending(monkeypatch):
    import sys

    from dm_apply import candidates_for_connect_action, main as dm_apply_main
    from tests.helpers.jobs import linkedin_dm_job

    job = linkedin_dm_job()
    prof = job["recruiter_profile_url"]
    state = {"profiles": {dm_state.normalize_profile_url(prof): _connect_pending_entry(prof)}}
    ran: list[int] = []

    def fake_asyncio_run(coro):
        coro.close()
        return {"sent_actions": 0, "skipped": 0}

    monkeypatch.setattr(sys, "argv", ["dm_apply.py", "--send", "--limit", "1", "--force-send", "--ui-approved"])
    monkeypatch.setattr("dm_apply.dm_state.load", lambda: state)

    def _collect(**kw):
        ran.append(len(candidates_for_connect_action(state, [job])))
        return [job]

    monkeypatch.setattr("dm_apply.collect_candidates", _collect)
    monkeypatch.setattr("dm_apply.asyncio.run", fake_asyncio_run)
    monkeypatch.setattr(
        "linkedin_configure.linkedin_connect_allowed",
        lambda *a, **k: (True, ""),
    )

    monkeypatch.setattr("dm_apply.audit_info", lambda *a, **k: None)
    rc = dm_apply_main()
    assert rc == 0
    assert ran == [1]  # connect_pending still eligible for connect phase


@pytest.mark.asyncio
async def test_dm_apply_run_retries_connect_pending(monkeypatch):
    from dm_apply import run
    from tests.helpers.jobs import linkedin_dm_job

    job = linkedin_dm_job()
    prof = job["recruiter_profile_url"]
    state = {"profiles": {dm_state.normalize_profile_url(prof): _connect_pending_entry(prof)}}

    monkeypatch.setattr("dm_apply.dm_state.load", lambda: state)
    monkeypatch.setattr("dm_apply.load_track_profile", lambda _t: {"dm_message_template": "Hi {role}"})
    monkeypatch.setattr("dm_apply.resolve_recipe", lambda *a, **k: {"name": "linkedin-connect-or-message", "steps": []})
    monkeypatch.setattr("dm_apply.launch_context", AsyncMock(return_value=(MagicMock(), MagicMock(), MagicMock())))
    monkeypatch.setattr("dm_apply.close_session", AsyncMock())
    monkeypatch.setattr("dm_apply.audit_info", lambda *a, **k: None)
    monkeypatch.setattr("dm_apply.audit_warn", lambda *a, **k: None)

    page = MagicMock()
    page.goto = AsyncMock()
    ctx = MagicMock()
    ctx.new_page = AsyncMock(return_value=page)

    async def fake_launch(*args, **kwargs):
        return MagicMock(), MagicMock(), ctx

    monkeypatch.setattr("dm_apply.launch_context", fake_launch)
    monkeypatch.setattr(
        "dm_apply.run_recipe",
        AsyncMock(return_value={"branch": "steps", "committed": False, "steps": []}),
    )
    monkeypatch.setattr("linkedin_ui.wait_for_profile_top_card", AsyncMock())
    monkeypatch.setattr("linkedin_ui.dismiss_blocking_dialogs", AsyncMock())
    monkeypatch.setattr("dm_apply.drift_mouse", AsyncMock())
    monkeypatch.setattr("dm_apply.pause_page_settle", AsyncMock())

    result = await run([job], send=False, headless=True)
    assert result["skipped"] == 0
