"""Bulk DM must not launch the browser when no resolvable profile URLs exist."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tests.helpers.jobs import linkedin_dm_job


def _connect_job():
    return linkedin_dm_job()


@patch("ui_server._run_apply_cmd")
def test_bulk_dm_skips_browser_when_no_profile_and_no_queue(mock_run):
    from ui_server import run_bulk_dm_followup

    keys = ["linkedin-post:366db93d"]
    no_profile_job = {
        "source": "linkedin_posts",
        "company": "Monika Kuqi",
        "role": "Ai Engineer",
        "url": "linkedin-post:366db93d",
        "apply_channel": "external_url",
        "filter_result": "eligible",
    }

    with patch("ui_server._find_job", return_value=no_profile_job):
        with patch("dm_apply.collect_candidates", return_value=[]):
            with patch("dm_followup.pending_profiles", return_value=[]):
                with patch("dm_followup.filter_entries_by_job_keys", return_value=[]):
                    result = run_bulk_dm_followup(track="ai-engineer", job_keys=keys)

    assert result["ok"] is False
    assert "Can't auto-connect" in result["message"]
    assert result["skipped_no_profile"] == ["Monika Kuqi"]
    mock_run.assert_not_called()


@patch("ui_server._run_apply_cmd")
def test_bulk_dm_runs_connect_when_profile_exists_even_if_queue_empty(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="processing 1", stderr="")
    from ui_server import run_bulk_dm_followup

    keys = ["ai-engineer|linkedin|acme ai|ai engineer"]
    job = _connect_job()

    with patch("ui_server._find_job", return_value=job):
        with patch("dm_apply.collect_candidates", return_value=[job]):
            with patch("dm_followup.pending_profiles", return_value=[]):
                with patch("dm_followup.filter_entries_by_job_keys", return_value=[]):
                    result = run_bulk_dm_followup(track="ai-engineer", job_keys=keys)

    assert result["ok"] is True
    assert mock_run.call_count == 1
    assert "dm_apply.py" in " ".join(mock_run.call_args_list[0][0][0])


@patch("ui_server._run_apply_cmd")
def test_bulk_dm_runs_check_without_connect_when_only_pending(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
    from ui_server import run_bulk_dm_followup

    keys = ["ai-engineer|linkedin|acme ai|ai engineer"]
    pending = [
        {
            "profile_url": "https://www.linkedin.com/in/recruiter-test/",
            "job_key": keys[0],
            "company": "Acme AI",
            "connect_requested_at": "2026-09-14T12:00:00",
        }
    ]

    def _status(entries, *, phase):
        return entries if phase == "check" else []

    with patch("dm_apply.collect_candidates", return_value=[]):
        with patch("dm_followup.pending_profiles", return_value=pending):
            with patch("dm_followup.filter_entries_by_job_keys", return_value=pending):
                with patch("dm_followup.filter_entries_by_status", side_effect=_status):
                    result = run_bulk_dm_followup(track="ai-engineer", job_keys=keys)

    assert result["ok"] is True
    assert mock_run.call_count == 1
    cmd = mock_run.call_args_list[0][0][0]
    assert "dm_followup.py" in " ".join(cmd)
    assert "--phase" in cmd and "check" in cmd
