"""Mocked coverage for apply pipeline shims (dm, email, LinkedIn, URL)."""

from __future__ import annotations

import json
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dm_apply import (  # noqa: E402
    classify_affordance,
    collect_candidates,
    is_applied_skip,
    main as dm_apply_main,
    message_body,
    pretty_role,
    scan,
)
from dm_followup import (  # noqa: E402
    _audit_extra,
    _canonical_profiles_by_company,
    _profile_audit_context,
    filter_entries_by_job_keys,
    filter_entries_by_status,
    is_connected,
    main as dm_followup_main,
    pending_profiles,
    shows_pending,
)
from email_apply import (  # noqa: E402
    main as email_apply_main,
    send_gmail_api,
    send_smtp,
    test_job as email_test_job,
)
from linkedin_easy_apply import (  # noqa: E402
    click_wizard_button,
    detect_wizard_button,
    is_linkedin_job_url,
    modal_locator,
    modal_visible,
)
from linkedin_easy_apply_status import (  # noqa: E402
    _classify_controls,
    _is_applied_control,
    status_label,
)
from url_apply import run as url_apply_run  # noqa: E402


def _form_linkedin_job(**overrides):
    job = {
        "track": "ai-engineer",
        "source": "linkedin_posts",
        "url": "https://www.linkedin.com/in/nicolebarraconde/recent-activity/all/",
        "apply_url": "https://lnkd.in/e4m6CuUu",
        "role": "Ai Engineer",
        "company": "Nicole Barra",
        "recruiter_profile_url": "https://www.linkedin.com/in/nicolebarraconde/",
        "discovered_at": "2026-09-06T12:00:00-03:00",
        "filter_result": "eligible",
    }
    job.update(overrides)
    return job


# --- dm_followup job key filter ---


def test_filter_entries_by_job_keys(monkeypatch):
    job = _form_linkedin_job()
    from registry import job_key as registry_job_key

    jk = registry_job_key(job)
    entries = [
        {"job_key": jk, "profile_url": job["recruiter_profile_url"], "company": job["company"]},
        {"job_key": "other", "profile_url": "https://www.linkedin.com/in/other/", "company": "Other Co"},
    ]
    monkeypatch.setattr("registry.load_registry", lambda: {"jobs": [job]})
    monkeypatch.setattr("generate_applications.dm_profile_url", lambda j: j.get("recruiter_profile_url"))
    filtered = filter_entries_by_job_keys(entries, [jk])
    assert len(filtered) == 1
    assert filtered[0]["job_key"] == jk


@pytest.mark.asyncio
async def test_classify_affordance_connect_top():
    page = MagicMock()
    page.goto = AsyncMock()
    with patch("dm_apply.pause_page_settle", AsyncMock()):
        with patch("dm_apply.drift_mouse", AsyncMock()):
            with patch("dm_apply.dismiss_blocking_dialogs", AsyncMock()):
                with patch("linkedin_ui.has_connect_on_main", AsyncMock(return_value=True)):
                    kind = await classify_affordance(page, "https://www.linkedin.com/in/recruiter/")
    assert kind == "connect_top"


@pytest.mark.asyncio
async def test_classify_affordance_error():
    page = MagicMock()
    page.goto = AsyncMock(side_effect=RuntimeError("timeout"))
    kind = await classify_affordance(page, "https://www.linkedin.com/in/recruiter/")
    assert kind == "error"


@pytest.mark.asyncio
async def test_dm_scan_mocked(monkeypatch, tmp_path):
    job = _form_linkedin_job()
    monkeypatch.setattr("dm_apply.ROOT", tmp_path)
    monkeypatch.setattr("dm_apply.launch_context", AsyncMock(return_value=(MagicMock(), MagicMock(), AsyncMock(new_page=AsyncMock(return_value=MagicMock())))))
    monkeypatch.setattr("dm_apply.close_session", AsyncMock())
    monkeypatch.setattr("dm_apply.classify_affordance", AsyncMock(return_value="message"))
    monkeypatch.setattr("dm_apply.pause_between_reads", AsyncMock())
    await scan([job], headless=True)
    assert (tmp_path / "runs" / "dm-scan.json").exists()


@pytest.mark.asyncio
async def test_shows_pending_true():
    page = MagicMock()
    pending_loc = MagicMock()
    pending_loc.count = AsyncMock(return_value=1)
    top = MagicMock()
    top.locator = MagicMock(return_value=pending_loc)
    main_section = MagicMock()
    main_section.first = top
    page.locator = MagicMock(return_value=main_section)
    assert await shows_pending(page) is True


@pytest.mark.asyncio
async def test_is_connected_message_available():
    page = MagicMock()
    page.goto = AsyncMock()
    main = MagicMock()
    main.locator = MagicMock(return_value=MagicMock(count=AsyncMock(return_value=0)))
    page.locator = MagicMock(return_value=main)
    with patch("dm_followup.pause_page_settle", AsyncMock()):
        with patch("dm_followup.drift_mouse", AsyncMock()):
            with patch("dm_followup.dismiss_blocking_dialogs", AsyncMock(return_value=False)):
                with patch("dm_followup.shows_pending", AsyncMock(return_value=False)):
                    with patch("dm_followup.has_top_card_message", AsyncMock(return_value=True)):
                        ok, reason = await is_connected(page, "https://www.linkedin.com/in/r/")
    assert ok is True


def test_canonical_profiles_by_company(monkeypatch):
    job = _form_linkedin_job()
    from registry import job_key as registry_job_key

    jk = registry_job_key(job)
    monkeypatch.setattr("registry.load_registry", lambda: {"jobs": [job]})
    monkeypatch.setattr("generate_applications.dm_profile_url", lambda j: j.get("recruiter_profile_url"))
    canonical = _canonical_profiles_by_company({jk})
    assert job["company"].casefold().strip() in canonical


# --- dm_apply ---


def test_pretty_role_normalizes_ai():
    assert pretty_role("Ai Engineer") == "AI Engineer"
    assert pretty_role("staff ai engineer") == "staff AI engineer"


def test_is_applied_skip_blocklist():
    assert is_applied_skip({"company": "Jeeves AI"}) is True
    assert is_applied_skip({"company": "Fresh Startup", "description_snippet": "hiring"}) is False


def test_message_body_form_link_includes_apply_url(monkeypatch):
    job = _form_linkedin_job()
    profile = {"form_link_message_template": "Applied for {role} via {apply_url}"}
    monkeypatch.setattr(
        "linkedin_configure.load_linkedin_config_raw",
        lambda tid: {"form_link_message_enabled": True},
    )
    body = message_body(job, profile, track_id="ai-engineer")
    assert "AI Engineer" in body
    assert "lnkd.in" in body


def test_collect_candidates_actionable_only(tmp_path, monkeypatch):
    from datetime import datetime
    from registry import job_key

    actionable_job = _form_linkedin_job(company="Actionable Co")
    other_job = _form_linkedin_job(
        company="Other Co",
        recruiter_profile_url="https://www.linkedin.com/in/other-recruiter/",
        url="https://www.linkedin.com/in/other-recruiter/recent-activity/all/",
    )
    scan = {
        "results": [
            {"job_key": job_key(actionable_job), "actionable": True},
            {"job_key": job_key(other_job), "actionable": False},
        ]
    }
    scan_path = tmp_path / "runs" / "dm-scan.json"
    scan_path.parent.mkdir(parents=True)
    scan_path.write_text(json.dumps(scan), encoding="utf-8")

    monkeypatch.setattr("dm_apply.ROOT", tmp_path)
    monkeypatch.setattr("dm_apply.load_registry", lambda: {"jobs": [actionable_job, other_job]})
    monkeypatch.setattr("dm_apply.filter_jobs_by_track", lambda jobs, tid: jobs)
    monkeypatch.setattr("dm_apply.needs_recruiter_connect", lambda j: True)

    out = collect_candidates(
        table_only=False,
        limit=0,
        actionable_only=True,
        track_id="ai-engineer",
    )
    assert len(out) == 1
    assert out[0]["company"] == "Actionable Co"


def test_dm_apply_main_list(monkeypatch, capsys):
    job = _form_linkedin_job()
    monkeypatch.setattr("dm_apply.collect_candidates", lambda **kwargs: [job])
    monkeypatch.setattr("sys.argv", ["dm_apply.py", "--list"])
    assert dm_apply_main() == 0
    out = capsys.readouterr().out
    assert "DM candidates" in out
    assert "nicolebarraconde" in out.lower() or "Nicole" in out


# --- dm_followup ---


def test_profile_audit_context_pure_helpers():
    entry = {
        "job_key": "jk-1",
        "company": "Acme",
        "role": "AI Engineer",
        "profile_url": "https://www.linkedin.com/in/recruiter/",
        "connect_requested_at": "2026-09-01T12:00:00",
    }
    ctx = _profile_audit_context(entry)
    assert ctx["job_key"] == "jk-1"
    merged = _audit_extra(ctx, outcome="accepted")
    assert merged["outcome"] == "accepted"
    assert merged["company"] == "Acme"


def test_dm_followup_collect_candidates():
    """Main() builds its queue from pending_profiles + phase filters."""
    import dm_state

    state = {
        "profiles": {
            "https://www.linkedin.com/in/a/": {
                "profile_url": "https://www.linkedin.com/in/a/",
                "connect_requested_at": "2026-09-01T12:00:00",
            },
            "https://www.linkedin.com/in/b/": {
                "profile_url": "https://www.linkedin.com/in/b/",
                "accepted_at": "2026-09-02T12:00:00",
            },
        }
    }
    entries = pending_profiles(state)
    check_phase = filter_entries_by_status(entries, phase="check")
    send_phase = filter_entries_by_status(entries, phase="send")
    assert len(check_phase) == 1
    assert dm_state.status_of(check_phase[0]) == dm_state.STATUS_CONNECT_PENDING
    assert len(send_phase) == 1
    assert dm_state.status_of(send_phase[0]) == dm_state.STATUS_ACCEPTED_MSG_PENDING


def test_pending_profiles_collects_awaiting_message():
    import dm_state

    state = {
        "profiles": {
            "https://www.linkedin.com/in/a/": {
                "profile_url": "https://www.linkedin.com/in/a/",
                "connect_requested_at": "2026-09-01T12:00:00",
            },
            "https://www.linkedin.com/in/b/": {
                "profile_url": "https://www.linkedin.com/in/b/",
                "accepted_at": "2026-09-02T12:00:00",
            },
            "https://www.linkedin.com/in/c/": {
                "profile_url": "https://www.linkedin.com/in/c/",
                "message_sent_at": "2026-09-03T12:00:00",
            },
        }
    }
    pending = pending_profiles(state)
    assert len(pending) == 2
    statuses = {dm_state.status_of(e) for e in pending}
    assert dm_state.STATUS_CONNECT_PENDING in statuses
    assert dm_state.STATUS_ACCEPTED_MSG_PENDING in statuses


def test_filter_entries_by_status_phases():
    import dm_state

    rows = [
        {"profile_url": "https://www.linkedin.com/in/a/", "connect_requested_at": "x"},
        {"profile_url": "https://www.linkedin.com/in/b/", "accepted_at": "x"},
    ]
    check = filter_entries_by_status(rows, phase="check")
    send = filter_entries_by_status(rows, phase="send")
    assert len(check) == 1
    assert dm_state.status_of(check[0]) == dm_state.STATUS_CONNECT_PENDING
    assert len(send) == 1
    assert dm_state.status_of(send[0]) == dm_state.STATUS_ACCEPTED_MSG_PENDING


def test_dm_followup_main_list(monkeypatch, capsys):
    import dm_state

    entries = [
        {
            "company": "Acme AI",
            "role": "AI Engineer",
            "job_key": "jk-1",
            "profile_url": "https://www.linkedin.com/in/recruiter-test/",
            "connect_requested_at": "2026-09-01T12:00:00",
        }
    ]
    state = {"profiles": {dm_state.normalize_profile_url(e["profile_url"]): e for e in entries}}
    monkeypatch.setattr("dm_followup.dm_state.load", lambda: state)
    monkeypatch.setattr("sys.argv", ["dm_followup.py", "--list"])
    assert dm_followup_main() == 0
    out = capsys.readouterr().out
    assert "Awaiting message" in out
    assert "Acme AI" in out


# --- email_apply ---


@pytest.fixture
def email_cfg(tmp_path: Path) -> dict:
    template = tmp_path / "body.txt"
    template.write_text("Hello,\n\nApplying for {role}.\n", encoding="utf-8")
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4")
    return {
        "body_template_file": str(template),
        "subject_template": "Application for {role}",
        "sender_name": "Test User",
        "sender_email": "test@gmail.com",
        "resume_path": str(resume),
        "sent_log_path": "state/email-sent.json",
        "gmail_token_path": "secrets/gmail-token.json",
        "rate_limit_seconds": 0,
        "skip_if_already_applied_in_applika": False,
        "log_to_applika": False,
    }


def test_send_smtp(monkeypatch, email_cfg):
    msg = MIMEMultipart()
    msg.attach(MIMEText("body", "plain"))
    msg["From"] = email_cfg["sender_email"]
    msg["To"] = "recruiter@acme.ai"

    smtp_instance = MagicMock()
    smtp_ctx = MagicMock()
    smtp_ctx.__enter__ = MagicMock(return_value=smtp_instance)
    smtp_ctx.__exit__ = MagicMock(return_value=False)

    monkeypatch.setattr("email_apply._gmail_app_password", lambda: "app-password")
    monkeypatch.setattr("smtplib.SMTP_SSL", lambda *a, **k: smtp_ctx)

    assert send_smtp(email_cfg, msg) == "smtp-sent"
    smtp_instance.login.assert_called_once_with(email_cfg["sender_email"], "app-password")
    smtp_instance.send_message.assert_called_once_with(msg)


def test_send_gmail_api_mock(email_cfg, tmp_path, monkeypatch):
    token = tmp_path / "secrets" / "gmail-token.json"
    token.parent.mkdir(parents=True)
    token.write_text('{"token": "x"}', encoding="utf-8")
    email_cfg = {**email_cfg, "gmail_token_path": "secrets/gmail-token.json"}
    monkeypatch.setattr("email_apply.ROOT", tmp_path)

    msg = MIMEMultipart()
    msg.attach(MIMEText("body", "plain"))

    send_result = MagicMock()
    send_result.execute = MagicMock(return_value={"id": "msg-123"})
    mock_service = MagicMock()
    mock_service.users.return_value.messages.return_value.send.return_value = send_result

    creds_mod = MagicMock()
    creds_mod.Credentials.from_authorized_user_file = MagicMock(return_value=MagicMock())
    oauth2_mod = MagicMock()
    oauth2_mod.credentials = creds_mod
    discovery_mod = MagicMock()
    discovery_mod.build = MagicMock(return_value=mock_service)
    googleapiclient_mod = MagicMock()
    googleapiclient_mod.discovery = discovery_mod

    monkeypatch.setitem(sys.modules, "google", MagicMock(oauth2=oauth2_mod))
    monkeypatch.setitem(sys.modules, "google.oauth2", oauth2_mod)
    monkeypatch.setitem(sys.modules, "google.oauth2.credentials", creds_mod)
    monkeypatch.setitem(sys.modules, "googleapiclient", googleapiclient_mod)
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", discovery_mod)

    assert send_gmail_api(email_cfg, msg) == "msg-123"
    send_result.execute.assert_called_once()


def test_email_apply_main_send(monkeypatch, tmp_path, email_cfg, capsys):
    job = email_test_job()
    job["apply_email"] = "recruiter@acme.ai"
    job["track"] = "ai-engineer"

    monkeypatch.setattr("email_apply.ROOT", tmp_path)
    monkeypatch.setattr("email_apply.load_config", lambda *_a: email_cfg)
    monkeypatch.setattr("email_apply.load_sent_log", lambda *_a: {"sent": []})
    monkeypatch.setattr("email_apply.collect_candidates", lambda **kwargs: [job])
    monkeypatch.setattr("gmail_configure.email_send_allowed", lambda *a, **k: (True, ""))
    monkeypatch.setattr("email_apply.send_gmail_api", lambda cfg, msg: "gmail-id-1")
    monkeypatch.setattr("email_apply.log_applika", lambda *a, **k: None)
    monkeypatch.setattr("email_apply.audit_info", lambda *a, **k: None)
    monkeypatch.setattr("email_apply.audit_warn", lambda *a, **k: None)
    monkeypatch.setattr("email_apply.audit_error", lambda *a, **k: None)
    monkeypatch.setattr("email_apply.time.sleep", lambda *_a: None)
    monkeypatch.setattr("table_refresh.refresh_applications_table", lambda: None)
    monkeypatch.setattr("sys.argv", ["email_apply.py", "--send"])

    assert email_apply_main() == 0
    out = capsys.readouterr().out
    assert "SENT" in out
    sent_path = tmp_path / email_cfg["sent_log_path"]
    assert sent_path.is_file()
    assert json.loads(sent_path.read_text(encoding="utf-8"))["sent"][0]["gmail_message_id"] == "gmail-id-1"


def test_email_apply_main_force_send(monkeypatch, tmp_path, email_cfg):
    from registry import job_key

    job = email_test_job()
    job["apply_email"] = "recruiter@acme.ai"
    job["track"] = "ai-engineer"
    jk = job_key(job)
    sent_log = {"sent": [{"job_key": jk, "to": "recruiter@acme.ai"}]}

    monkeypatch.setattr("email_apply.ROOT", tmp_path)
    monkeypatch.setattr("email_apply.load_config", lambda *_a: email_cfg)
    monkeypatch.setattr("email_apply.load_sent_log", lambda *_a: sent_log)
    monkeypatch.setattr("email_apply.collect_candidates", lambda **kwargs: [job])
    monkeypatch.setattr(
        "gmail_configure.email_send_allowed",
        lambda tid, cli_force=False, ui_approved=False: (True, "forced") if cli_force else (False, "blocked"),
    )
    monkeypatch.setattr("email_apply.send_gmail_api", lambda cfg, msg: "gmail-id-2")
    monkeypatch.setattr("email_apply.log_applika", lambda *a, **k: None)
    monkeypatch.setattr("email_apply.audit_info", lambda *a, **k: None)
    monkeypatch.setattr("email_apply.audit_warn", lambda *a, **k: None)
    monkeypatch.setattr("email_apply.time.sleep", lambda *_a: None)
    monkeypatch.setattr("table_refresh.refresh_applications_table", lambda: None)
    monkeypatch.setattr("sys.argv", ["email_apply.py", "--send", "--force", "--force-send"])

    assert email_apply_main() == 0
    data = json.loads((tmp_path / email_cfg["sent_log_path"]).read_text(encoding="utf-8"))
    assert len(data["sent"]) == 2


# --- linkedin_easy_apply ---


def test_is_linkedin_job_url():
    assert is_linkedin_job_url("https://www.linkedin.com/jobs/view/1234567890/") is True
    assert is_linkedin_job_url("https://example.com/jobs/1") is False


@pytest.mark.asyncio
async def test_detect_wizard_button_submit():
    page = MagicMock()
    btn = MagicMock()
    btn.count = AsyncMock(return_value=1)
    btn.first.is_visible = AsyncMock(return_value=True)
    page.get_by_role = MagicMock(return_value=btn)
    page.locator = MagicMock(return_value=MagicMock(count=AsyncMock(return_value=0)))

    with patch("linkedin_easy_apply.modal_locator", AsyncMock(return_value=None)):
        kind = await detect_wizard_button(page)
    assert kind == "submit"


@pytest.mark.asyncio
async def test_click_wizard_button_dry_run():
    page = MagicMock()
    btn = MagicMock()
    btn.count = AsyncMock(return_value=1)
    btn.first = btn
    page.get_by_role = MagicMock(return_value=btn)

    with patch("linkedin_easy_apply.modal_locator", AsyncMock(return_value=None)):
        rec = await click_wizard_button(page, "submit", send=False)

    assert rec["dry_run"] is True
    assert "would submit" in rec["note"].lower()


@pytest.mark.asyncio
async def test_modal_visible_false_when_no_modal():
    with patch("linkedin_easy_apply.modal_locator", AsyncMock(return_value=None)):
        assert await modal_visible(MagicMock()) is False


@pytest.mark.asyncio
async def test_modal_locator_finds_visible():
    page = MagicMock()
    loc = MagicMock()
    loc.count = AsyncMock(return_value=1)
    loc.first = loc
    loc.is_visible = AsyncMock(return_value=True)
    page.locator = MagicMock(return_value=loc)
    found = await modal_locator(page)
    assert found is loc


@pytest.mark.asyncio
async def test_detect_wizard_button_submit():
    page = MagicMock()
    btn = MagicMock()
    btn.count = AsyncMock(return_value=1)
    btn.first = btn
    btn.is_visible = AsyncMock(return_value=True)
    scope = MagicMock()
    scope.get_by_role = MagicMock(return_value=btn)
    scope.locator = MagicMock(return_value=btn)
    with patch("linkedin_easy_apply.modal_locator", AsyncMock(return_value=scope)):
        assert await detect_wizard_button(page) == "submit"


# --- linkedin_easy_apply_status ---


def test_status_label_mapping():
    assert status_label("available") == "Easy Apply open"
    assert status_label("applied") == "Applied on LinkedIn"
    assert status_label("unknown") == "Status unknown"


def test_is_applied_control():
    assert _is_applied_control({"text": "Applied", "aria": ""}) is True
    assert _is_applied_control({"text": "Easy Apply", "aria": ""}) is False


def test_classify_controls_available():
    controls = [{"text": "Easy Apply", "aria": "", "visible": True, "disabled": False}]
    result = _classify_controls(controls, "Join our team")
    assert result["status"] == "available"
    assert result["easy_apply_enabled"] is True


def test_classify_controls_closed_body():
    result = _classify_controls([], "This role is no longer accepting applications")
    assert result["status"] == "closed"


# --- url_apply run ---


@pytest.mark.asyncio
async def test_url_apply_run_fully_mocked(monkeypatch, tmp_path):
    page = MagicMock()
    page.url = "https://careers.example.com/apply"
    page.goto = AsyncMock()
    page.evaluate = AsyncMock()
    page.inner_text = AsyncMock(return_value="Thank you for applying")

    ctx = MagicMock()
    ctx.new_page = AsyncMock(return_value=page)
    pw = MagicMock()
    browser = MagicMock()

    monkeypatch.setattr(
        "url_apply.launch_context",
        AsyncMock(return_value=(pw, browser, ctx)),
    )
    monkeypatch.setattr("url_apply.close_session", AsyncMock())
    monkeypatch.setattr("url_apply.load_profile", lambda tid=None: {"country": "Brazil", "full_name": "Test"})
    monkeypatch.setattr("url_apply.resolve_shortlink", AsyncMock())
    monkeypatch.setattr("url_apply.reveal_form", AsyncMock())
    monkeypatch.setattr("url_apply.resolve_recipe", lambda url: None)
    monkeypatch.setattr(
        "url_apply.extract_fields",
        AsyncMock(return_value=[{"idx": 0, "type": "text", "label": "Name", "required": True}]),
    )
    monkeypatch.setattr(
        "url_apply.autofill",
        AsyncMock(return_value={"filled": [{"idx": 0}], "needs_input": [], "unmapped": [], "resume_uploaded": False}),
    )
    monkeypatch.setattr("url_apply.fill_country_dropdown", AsyncMock(return_value=False))
    monkeypatch.setattr("url_apply.notify_form_change", AsyncMock())
    monkeypatch.setattr("url_apply.print_autofill_report", lambda report: None)
    monkeypatch.setattr("url_apply.asyncio.sleep", AsyncMock())

    await url_apply_run(
        "inspect",
        "https://careers.example.com/apply",
        answers={},
        hold=0,
        submit=False,
        company="Acme",
        role="AI Engineer",
        track_id="ai-engineer",
    )

    page.goto.assert_awaited()
    ctx.new_page.assert_awaited()
