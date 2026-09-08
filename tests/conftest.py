"""Pytest fixtures for jobsearch tests."""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def linkedin_html_dir() -> Path:
    return FIXTURES / "linkedin"


@pytest.fixture
def linkedin_jobs_html_dir() -> Path:
    return FIXTURES / "linkedin_jobs"


def _start_mock_ui_server(
    monkeypatch,
    *,
    today: str = "2026-09-06",
    has_research_today: bool = True,
    last_research_day: str | None = "2026-09-06",
    mock_research: bool = False,
    research_run_path: Path | None = None,
    snapshot_override: dict[str, Any] | None = None,
    bulk_dm: str = "mock",
    meta_override: dict[str, Any] | None = None,
    chameleon_generate: str = "mock",
) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """HTTP server with mocked action/snapshot handlers for UI e2e."""
    from tests.helpers.jobs import ui_snapshot

    job_key = "ai-engineer|linkedin|acme ai|ai engineer"
    snapshot = snapshot_override or ui_snapshot(job_key, day=today if has_research_today else last_research_day or today)
    research_snapshot = ui_snapshot(job_key, day=today)
    captured: dict[str, Any] = {
        "last_action": None,
        "last_bulk_action": None,
        "last_research": None,
        "last_chameleon": None,
        "apply_cmds": [],
    }

    if research_run_path:
        monkeypatch.setattr("research_log.RUN_PATH", research_run_path)

    def fake_run_action(action: str, jk: str, track=None):
        captured["last_action"] = {"action": action, "job_key": jk, "track": track}
        return {"ok": True, "message": "mock ok", "action": action, "job_key": jk}

    def fake_run_bulk_dm_followup(*, track=None, limit=0, job_keys=None):
        captured["last_bulk_action"] = {
            "action": "dm_process_all",
            "track": track,
            "limit": limit,
            "job_keys": job_keys or [],
        }
        return {
            "ok": True,
            "message": "mock bulk ok",
            "action": "dm_process_all",
            "track": track,
            "limit": limit,
        }

    def fake_run_bulk_email_apply(*, track=None, limit=0, job_keys=None):
        captured["last_bulk_action"] = {
            "action": "email_process_all",
            "track": track,
            "limit": limit,
            "job_keys": job_keys or [],
        }
        return {
            "ok": True,
            "message": "mock bulk email ok",
            "action": "email_process_all",
            "track": track,
            "limit": limit,
        }

    def fake_refresh():
        import copy

        from form_apply_state import load_form_submission_state

        data = copy.deepcopy(snapshot)
        urls, keys = load_form_submission_state()
        for row in data.get("jobs", []):
            form = (row.get("actions") or {}).get("form")
            if not form or not form.get("available"):
                continue
            apply = (row.get("apply_url") or "").strip()
            row_jk = row.get("job_key") or ""
            submitted = row_jk in keys or apply in urls
            form["done"] = submitted
            form["status_text"] = "submitted" if submitted else "not applied"
        return data

    sidebar_days: list[dict[str, Any]] = []
    if not has_research_today:
        sidebar_days.append({"day": today, "job_count": 0, "pending": True})
    if last_research_day:
        sidebar_days.append(
            {
                "day": last_research_day,
                "label": last_research_day,
                "job_count": 1,
                "generated_at": f"{last_research_day}T12:00:00",
                "pending": False,
            }
        )

    def fake_load_snapshot(day):
        if day == today and mock_research:
            return research_snapshot
        known = {snapshot.get("day"), "live", today, last_research_day}
        return snapshot if day in {d for d in known if d} else None

    def fake_run_daily_research(**_kwargs):
        from research_log import finish_research_run, set_research_step, start_research_run

        captured["last_research"] = {"started": True}
        start_research_run(today)
        set_research_step("linkedin_collect")
        time.sleep(1.2)
        set_research_step("generate_table")
        time.sleep(0.2)
        msg = f"Research complete for {today}: 1 roles in apply table."
        finish_research_run(ok=True, message=msg)
        for entry in sidebar_days:
            if entry.get("day") == today:
                entry["pending"] = False
                entry["job_count"] = 1
                entry["generated_at"] = f"{today}T12:00:00"
        captured["last_research"] = {"ok": True, "day": today, "message": msg}
        return {"ok": True, "message": msg, "day": today, "job_count": 1}

    import applications_ui_data
    import ui_server

    def fake_run_apply_cmd(cmd, *, inherit_stdio=False):
        captured["apply_cmds"].append(list(cmd))
        return MagicMock(returncode=0, stdout="[DRY RUN] checking 1 profile(s)\nSummary: ok", stderr="")

    def fake_find_job(job_key_value: str):
        from registry import job_key as registry_job_key
        from tests.helpers.jobs import linkedin_dm_job

        job = linkedin_dm_job()
        aliases = {
            registry_job_key(job),
            "ai-engineer|linkedin|acme ai|ai engineer",
        }
        return job if job_key_value in aliases else None

    monkeypatch.setattr(ui_server, "_find_job", fake_find_job)
    monkeypatch.setattr(ui_server, "run_action", fake_run_action)
    if bulk_dm == "mock":
        monkeypatch.setattr(ui_server, "run_bulk_dm_followup", fake_run_bulk_dm_followup)
        monkeypatch.setattr(ui_server, "run_bulk_email_apply", fake_run_bulk_email_apply)
        monkeypatch.setattr(ui_server, "_run_apply_cmd", fake_run_apply_cmd)
    else:
        import dm_state as dm_state_mod
        from registry import job_key as registry_job_key
        from tests.helpers.jobs import linkedin_dm_job

        reg_job = linkedin_dm_job()
        reg_jk = registry_job_key(reg_job)
        if snapshot_override is None:
            snapshot = ui_snapshot(reg_jk, day=today if has_research_today else last_research_day or today)
            research_snapshot = ui_snapshot(reg_jk, day=today)
        else:
            research_snapshot = snapshot_override

        profile = "https://www.linkedin.com/in/recruiter-test/"
        prof_key = dm_state_mod.normalize_profile_url(profile)
        if bulk_dm == "real":
            dm_data = {
                "profiles": {
                    prof_key: {
                        "company": "Acme AI",
                        "role": "AI Engineer",
                        "job_key": profile.rstrip("/"),  # legacy URL key — regression case
                        "profile_url": profile,
                        "connect_requested_at": "2026-09-07T12:00:00",
                        "accepted_at": None,
                        "message_sent_at": None,
                    }
                }
            }
        else:
            dm_data = {"profiles": {}}

        monkeypatch.setattr(dm_state_mod, "load", lambda: dm_data)
        monkeypatch.setattr("registry.load_registry", lambda: {"jobs": [reg_job]})
        monkeypatch.setattr(ui_server, "_browser_deps_ok", lambda: (True, ""))
        monkeypatch.setattr(ui_server, "_run_apply_cmd", fake_run_apply_cmd)
        monkeypatch.setattr(ui_server, "_find_job", lambda jk: reg_job if jk == reg_jk else None)
    monkeypatch.setattr(applications_ui_data, "refresh_live_snapshot", fake_refresh)
    monkeypatch.setattr(applications_ui_data, "list_snapshot_days", lambda: sidebar_days)
    monkeypatch.setattr(applications_ui_data, "load_snapshot", fake_load_snapshot)

    if mock_research:
        monkeypatch.setattr("daily_research.run_daily_research", fake_run_daily_research)

    def fake_set_disposition(jk, disp):
        return {"ok": True, "message": "mock disposition", "job_key": jk}

    monkeypatch.setattr(ui_server, "set_disposition", fake_set_disposition)

    if chameleon_generate == "mock":

        def fake_find_job_by_key(job_key_value: str):
            from registry import job_key as registry_job_key
            from tests.helpers.jobs import linkedin_dm_job

            job = linkedin_dm_job()
            aliases = {
                registry_job_key(job),
                "ai-engineer|linkedin|acme ai|ai engineer",
            }
            return job if job_key_value in aliases else None

        def fake_generate_for_job(job, *, track_id=None, master_id=None, download=True):
            from registry import job_key as registry_job_key

            jk = registry_job_key(job)
            captured["last_chameleon"] = {
                "job_key": jk,
                "track_id": track_id,
                "master_id": master_id,
                "download": download,
            }
            aliases = {
                jk,
                "ai-engineer|linkedin|acme ai|ai engineer",
            }
            ch_state = {
                "ready": True,
                "generated": True,
                "download_url": f"/api/chameleon/download?job_key={jk}",
                "role_keywords": ["python", "rag"],
                "role_keywords_count": 2,
            }
            for row in snapshot.get("jobs", []):
                row_key = row.get("job_key") or ""
                if row_key == jk or row_key in aliases:
                    row["chameleon"] = dict(ch_state)
                    row["chameleon"]["download_url"] = f"/api/chameleon/download?job_key={row_key}"
                    break
            return {
                "job_key": jk,
                "output_path": str(Path("/tmp/mock-chameleon.pdf")),
                "headline_edited": True,
                "skill_lines": ["Python | RAG"],
            }

        def fake_resolve_output_for_job(job_key_value, *, track_id=None):
            mock_path = Path("/tmp/mock-chameleon.pdf")
            if not mock_path.is_file():
                mock_path.write_bytes(b"%PDF-1.4\n% mock chameleon\n")
            aliases = {
                "ai-engineer|linkedin|acme ai|ai engineer",
            }
            last = captured.get("last_chameleon") or {}
            if job_key_value in aliases or last.get("job_key") == job_key_value:
                return mock_path
            return mock_path if last else None

        monkeypatch.setattr("resume_chameleon.generate_for_job", fake_generate_for_job)
        monkeypatch.setattr("resume_chameleon.resolve_output_for_job", fake_resolve_output_for_job)
        monkeypatch.setattr("resume_chameleon.find_job_by_key", fake_find_job_by_key)
        monkeypatch.setattr("resume_chameleon.chameleon_is_configured", lambda cfg=None, track_id=None: True)

    elif chameleon_generate == "off":

        def fake_find_job_by_key(job_key_value: str):
            from registry import job_key as registry_job_key
            from tests.helpers.jobs import linkedin_dm_job

            job = linkedin_dm_job()
            aliases = {
                registry_job_key(job),
                "ai-engineer|linkedin|acme ai|ai engineer",
            }
            return job if job_key_value in aliases else None

        monkeypatch.setattr("resume_chameleon.find_job_by_key", fake_find_job_by_key)

    import config_ui_data

    def fake_save_config_section(track_id, section, payload):
        if section not in ("profile", "linkedin", "linkedin_jobs", "email", "board", "google", "form_answers", "chameleon"):
            raise ValueError(f"Unknown config section: {section}")
        captured.setdefault("config_saves", []).append(
            {"track": track_id, "section": section, "payload": payload}
        )
        bundle = config_ui_data.load_config_bundle(track_id)
        if section == "profile":
            for group, fields in payload.items():
                if isinstance(fields, dict) and group in bundle.get("profile", {}):
                    bundle["profile"][group].update(fields)
        elif section == "linkedin":
            bundle["linkedin"].update(payload)
        elif section == "linkedin_jobs":
            bundle["linkedin_jobs"].update(payload)
        elif section == "email":
            bundle["email"].update(payload)
        elif section == "board":
            if "filters" in payload:
                bundle["board"]["filters"].update(payload["filters"])
            if "sources" in payload:
                for name, scfg in payload["sources"].items():
                    if name in bundle["board"]["sources"]:
                        bundle["board"]["sources"][name].update(scfg)
        elif section == "google":
            bundle["google"].update(payload)
        elif section == "form_answers":
            if "rules" in payload:
                bundle["form_answers"]["rules"] = payload["rules"]
                bundle["form_answers"]["rules_count"] = len(payload["rules"])
        return bundle

    monkeypatch.setattr(config_ui_data, "save_config_section", fake_save_config_section)

    from ui_server import UI_META

    def fake_meta_payload():
        from resume_chameleon import chameleon_status  # noqa: WPS433
        from track_store import default_track_id  # noqa: WPS433

        base = {
            **UI_META,
            "today": today,
            "has_research_today": has_research_today,
            "last_research_day": last_research_day,
            "last_research_at": f"{last_research_day}T12:00:00" if last_research_day else None,
            "research_days": [
                {
                    "day": last_research_day,
                    "job_count": 1,
                    "completed_at": f"{last_research_day}T12:00:00",
                }
            ]
            if last_research_day
            else [],
        }
        if meta_override:
            base.update(meta_override)
        if int(base.get("version") or 0) >= UI_META["version"]:
            base.setdefault("chameleon", chameleon_status(default_track_id()))
        return base

    monkeypatch.setattr(ui_server, "ui_meta_payload", fake_meta_payload)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.ApplicationsUIHandler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.15)
    try:
        yield port, captured
    finally:
        httpd.shutdown()
        captured.clear()


@pytest.fixture
def mock_ui_server_stale_meta(monkeypatch) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Simulates an old UI server process missing bulk email support."""
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-06",
        has_research_today=True,
        last_research_day="2026-09-06",
        meta_override={
            "ui_approval": True,
            "version": 3,
            "bulk_actions": ["dm_process_all"],
        },
    )


@pytest.fixture
def mock_ui_server_duplicate_email(monkeypatch) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Two pending email rows sharing one apply address."""
    from tests.helpers.jobs import ui_snapshot_duplicate_email

    snapshot = ui_snapshot_duplicate_email(day="2026-09-06")
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-06",
        has_research_today=True,
        last_research_day="2026-09-06",
        snapshot_override=snapshot,
    )


@pytest.fixture
def mock_ui_server_email_sent(monkeypatch) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Dashboard with email already sent on the card."""
    from tests.helpers.jobs import ui_snapshot_with_email

    job_key = "ai-engineer|linkedin|acme ai|ai engineer"
    snapshot = ui_snapshot_with_email(job_key, day="2026-09-06", email_done=True)
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-06",
        has_research_today=True,
        last_research_day="2026-09-06",
        snapshot_override=snapshot,
    )


@pytest.fixture
def mock_ui_server_email(monkeypatch) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Dashboard with a pending email-apply role in the list."""
    from tests.helpers.jobs import ui_snapshot_with_email

    job_key = "ai-engineer|linkedin|acme ai|ai engineer"
    snapshot = ui_snapshot_with_email(job_key, day="2026-09-06")
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-06",
        has_research_today=True,
        last_research_day="2026-09-06",
        snapshot_override=snapshot,
    )


@pytest.fixture
def mock_ui_server(monkeypatch) -> Generator[tuple[int, dict[str, Any]], None, None]:
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-06",
        has_research_today=True,
        last_research_day="2026-09-06",
    )


@pytest.fixture
def mock_ui_server_needs_research(monkeypatch) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Today has no research yet; yesterday's snapshot remains in the sidebar."""
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-07",
        has_research_today=False,
        last_research_day="2026-09-06",
    )


@pytest.fixture
def mock_ui_server_dm_sent(monkeypatch) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Dashboard with DM message already sent on the card."""
    from tests.helpers.jobs import ui_snapshot

    job_key = "ai-engineer|linkedin|acme ai|ai engineer"
    sent_actions = {
        "email": {"available": False, "done": False, "in_progress": False, "label": "Apply via email", "status_text": "not applied"},
        "form": {"available": True, "done": False, "in_progress": False, "label": "Apply via form", "status_text": "not applied"},
        "dm_connect": {"available": True, "done": True, "in_progress": False, "label": "Send connection", "status_text": "done"},
        "dm_check": {"available": False, "done": True, "in_progress": False, "label": "Check connection accepted", "status_text": "accepted"},
        "dm_message": {"available": True, "done": True, "in_progress": False, "label": "Send LinkedIn message", "status_text": "sent"},
    }
    snapshot = ui_snapshot(job_key, day="2026-09-06", actions=sent_actions)
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-06",
        has_research_today=True,
        last_research_day="2026-09-06",
        snapshot_override=snapshot,
    )


@pytest.fixture
def mock_ui_server_research_flow(monkeypatch, tmp_path) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Today pending with mock POST /api/research progress + completion."""
    run_path = tmp_path / "state" / "research-run.json"
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-07",
        has_research_today=False,
        last_research_day="2026-09-06",
        mock_research=True,
        research_run_path=run_path,
    )


@pytest.fixture
def mock_ui_server_multi_dm(monkeypatch) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Two DM cards with no prior connect — bulk must pass both job_keys from the list."""
    from tests.helpers.jobs import ui_snapshot_multi_dm

    snapshot = ui_snapshot_multi_dm(day="2026-09-06")
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-06",
        has_research_today=True,
        last_research_day="2026-09-06",
        snapshot_override=snapshot,
    )


@pytest.fixture
def mock_ui_server_bulk_dm_legacy_match(monkeypatch) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Real bulk DM preflight: legacy profile-key entry must match list row."""
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-06",
        has_research_today=True,
        last_research_day="2026-09-06",
        bulk_dm="real",
    )


@pytest.fixture
def mock_ui_server_bulk_dm_empty_queue(monkeypatch) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Real bulk DM: empty follow-up queue still runs connect → check → send."""
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-06",
        has_research_today=True,
        last_research_day="2026-09-06",
        bulk_dm="real_empty",
    )


@pytest.fixture
def mock_ui_server_linkedin_jobs(monkeypatch) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Mixed LinkedIn posts + jobs for source / Posted 24h filter e2e."""
    from tests.helpers.jobs import ui_snapshot_linkedin_jobs_mixed

    snapshot = ui_snapshot_linkedin_jobs_mixed(day="2026-09-06")
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-06",
        has_research_today=True,
        last_research_day="2026-09-06",
        snapshot_override=snapshot,
    )


@pytest.fixture
def mock_ui_server_chameleon(monkeypatch) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Dashboard with CV Chameleon ready on cards and in /api/meta."""
    from tests.helpers.jobs import ui_snapshot

    job_key = "ai-engineer|linkedin|acme ai|ai engineer"
    chameleon = {
        "ready": True,
        "generated": False,
        "download_url": "",
        "role_keywords": ["python", "rag"],
        "role_keywords_count": 2,
    }
    snapshot = ui_snapshot(job_key, day="2026-09-06", chameleon=chameleon)
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-06",
        has_research_today=True,
        last_research_day="2026-09-06",
        snapshot_override=snapshot,
        meta_override={
            "chameleon": {
                "ready": True,
                "message": "1 master CV(s) ready.",
                "masters_count": 1,
                "track_id": "ai-engineer",
            }
        },
        chameleon_generate="mock",
    )


@pytest.fixture
def mock_ui_server_chameleon_not_ready(monkeypatch) -> Generator[tuple[int, dict[str, Any]], None, None]:
    from tests.helpers.jobs import ui_snapshot

    job_key = "ai-engineer|linkedin|acme ai|ai engineer"
    chameleon = {
        "ready": False,
        "generated": False,
        "download_url": "",
        "role_keywords": [],
        "role_keywords_count": 0,
    }
    snapshot = ui_snapshot(job_key, day="2026-09-06", chameleon=chameleon)

    def fake_is_configured(cfg=None, track_id=None):
        return False

    monkeypatch.setattr("resume_chameleon.chameleon_is_configured", fake_is_configured)
    yield from _start_mock_ui_server(
        monkeypatch,
        today="2026-09-06",
        has_research_today=True,
        last_research_day="2026-09-06",
        snapshot_override=snapshot,
        meta_override={
            "chameleon": {
                "ready": False,
                "message": "Master CV path(s) missing — update CV Chameleon settings.",
                "masters_count": 0,
                "track_id": "ai-engineer",
            }
        },
        chameleon_generate="off",
    )
