"""Extended coverage for email_apply pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from email_apply import (  # noqa: E402
    build_message,
    collect_candidates,
    email_apply_done,
    is_applied_skip,
    load_sent_log,
    pending_send_candidates,
    render_body,
    save_sent_log,
    sent_recipient_emails,
    test_job as sample_email_test_job,
)


@pytest.fixture
def email_cfg(tmp_path: Path) -> dict:
    template = tmp_path / "body.txt"
    template.write_text("Hello,\n\nApplying for {role}.\n", encoding="utf-8")
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4")
    return {
        "body_template_file": str(template.relative_to(tmp_path)),
        "subject_template": "Application for {role}",
        "sender_name": "Test User",
        "sender_email": "test@gmail.com",
        "resume_path": str(resume),
        "sent_log_path": "state/email-sent.json",
        "rate_limit_seconds": 0,
        "skip_if_already_applied_in_applika": False,
        "log_to_applika": False,
    }


def test_load_and_save_sent_log(tmp_path: Path, monkeypatch):
    path = tmp_path / "sent.json"
    assert load_sent_log(path) == {"sent": []}
    save_sent_log(path, {"sent": [{"to": "a@b.com"}]})
    assert load_sent_log(path)["sent"][0]["to"] == "a@b.com"


def test_sent_recipient_emails():
    log = {"sent": [{"to": "A@Example.com"}, {"to": ""}, {"job_key": "x"}]}
    assert sent_recipient_emails(log) == {"a@example.com"}


def test_email_apply_done_by_key_and_address():
    job = {"source": "linkedin_posts", "url": "https://li/posts/1", "apply_email": "r@acme.ai"}
    from registry import job_key

    jk = job_key(job)
    assert email_apply_done(job, email_keys={jk}, email_to=set()) is True
    assert email_apply_done(job, email_keys=set(), email_to={"r@acme.ai"}) is True
    assert email_apply_done(job, email_keys=set(), email_to=set()) is False


def test_render_body():
    cfg = {}
    job = {"role": "Staff AI Engineer"}
    assert "Staff AI Engineer" in render_body(cfg, job, "Role: {role}")


def test_build_message(tmp_path: Path, email_cfg):
    email_cfg["body_template_file"] = str(tmp_path / email_cfg["body_template_file"])
    email_cfg["resume_path"] = str(tmp_path / "resume.pdf")
    job = {"role": "AI Engineer", "company": "Acme"}
    msg = build_message(email_cfg, job, "recruiter@acme.ai")
    assert msg["Subject"] == "Application for AI Engineer"
    assert msg.get_payload()[1].get_content_type() == "application/pdf"


def test_is_applied_skip_blocklist():
    assert is_applied_skip({"company": "Jeeves AI", "description_snippet": ""}) is True
    assert is_applied_skip({"company": "Fresh Co", "description_snippet": "hiring"}) is False


def test_collect_candidates_table_only(monkeypatch):
    since = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    job = {
        "source": "linkedin_posts",
        "company": "Acme",
        "role": "AI Engineer",
        "url": "https://www.linkedin.com/posts/x",
        "apply_email": "r@acme.ai",
        "filter_result": "eligible",
        "discovered_at": since.isoformat(),
        "track": "ai-engineer",
    }
    monkeypatch.setattr("email_apply.load_registry", lambda: {"jobs": [job]})
    monkeypatch.setattr("email_apply.filter_jobs_by_track", lambda jobs, tid: jobs)
    monkeypatch.setattr("table_window.table_since", lambda: since.replace(year=since.year - 1))
    monkeypatch.setattr("linkedin_posts_merge.sort_jobs_by_recency", lambda xs: xs)

    out = collect_candidates(table_only=True, limit=0, track_id="ai-engineer")
    assert len(out) == 1


def test_pending_send_candidates_filters_sent():
    job = {
        "track": "ai-engineer",
        "source": "linkedin_posts",
        "company": "Acme AI",
        "role": "AI Engineer",
        "url": "https://www.linkedin.com/posts/test-activity-123",
        "apply_email": "recruiter@acme.ai",
        "filter_result": "eligible",
    }
    from registry import job_key

    jk = job_key(job)
    sent = {"sent": [{"job_key": jk, "to": "recruiter@acme.ai"}]}
    with patch("email_apply.load_registry", return_value={"jobs": [job]}):
        with patch("email_apply.load_config", return_value={"sent_log_path": "state/x.json"}):
            with patch("email_apply.load_sent_log", return_value=sent):
                pending = pending_send_candidates(track_id="ai-engineer", job_keys=[jk], sent_log=sent)
    assert pending == []


def test_sample_test_job_shape():
    j = sample_email_test_job()
    assert j["source"] == "email_test"


def test_main_list_mode(monkeypatch, capsys):
    job = {
        "source": "linkedin_posts",
        "company": "Acme",
        "role": "AI Engineer",
        "url": "https://www.linkedin.com/posts/x",
        "apply_email": "r@acme.ai",
        "track": "ai-engineer",
    }
    monkeypatch.setattr("email_apply.load_config", lambda *_a: {"sent_log_path": "state/email-sent.json"})
    monkeypatch.setattr("email_apply.load_sent_log", lambda *_a: {"sent": []})
    monkeypatch.setattr("email_apply.collect_candidates", lambda **kwargs: [job])
    monkeypatch.setattr("sys.argv", ["email_apply.py", "--list"])
    from email_apply import main

    assert main() == 0
    assert "Email-apply candidates" in capsys.readouterr().out


def test_main_dry_run_batch(monkeypatch, capsys, tmp_path: Path, email_cfg):
    job = sample_email_test_job()
    job["apply_email"] = "r@acme.ai"
    email_cfg["body_template_file"] = str(tmp_path / "body.txt")
    (tmp_path / "body.txt").write_text("Hi {role}", encoding="utf-8")
    email_cfg["resume_path"] = str(tmp_path / "resume.pdf")
    (tmp_path / "resume.pdf").write_bytes(b"%PDF")

    monkeypatch.setattr("email_apply.ROOT", tmp_path)
    monkeypatch.setattr("email_apply.load_config", lambda *_a: {**email_cfg, "sent_log_path": "state/sent.json"})
    monkeypatch.setattr("email_apply.load_sent_log", lambda *_a: {"sent": []})
    monkeypatch.setattr("email_apply.collect_candidates", lambda **kwargs: [job])
    monkeypatch.setattr("email_apply.audit_info", lambda *a, **k: None)
    monkeypatch.setattr("sys.argv", ["email_apply.py", "--dry-run"])
    from email_apply import main

    assert main() == 0
    assert "DRY RUN" in capsys.readouterr().out
