"""Cover letter generation, guardrails, and email/form injection."""

from __future__ import annotations

import json
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Any

import pytest

import urllib.error

from cover_letter import (
    chat_completion,
    cover_settings,
    fallback_text,
    overlay_form_cover,
    prepare_for_channel,
    validate_cover_letter,
    word_count,
)


PROFILE: dict[str, Any] = {
    "full_name": "Ana Silva",
    "current_title": "AI Engineer",
    "years_experience": "6",
    "ai_experience_summary": (
        "Built production RAG pipelines and evaluation harnesses for support agents."
    ),
    "skills": ["RAG", "Python", "evaluation"],
    "achievements": ["Shipped retrieval quality checks for a support agent"],
    "cover_letter_default": (
        "Hi,\n\nI have the qualifications for the {role} role and I am available to discuss next steps."
    ),
}

JOB: dict[str, Any] = {
    "source": "himalayas",
    "role": "AI Engineer",
    "company": "Northwind",
    "url": "https://example.com/jobs/northwind-ai",
    "description_snippet": (
        "Own retrieval quality and RAG evaluation for our support agent platform."
    ),
    "track": "ai-engineer",
}

SETTINGS = cover_settings(
    {
        "cover_letter": {
            "enabled": True,
            "auto_inject": True,
            "min_words": 120,
            "max_words": 220,
            "quality_threshold": 0.7,
            "allow_fallback": True,
            "language": "en",
            "model": "gpt-4o-mini",
            "channels": {"email": True, "form": False, "linkedin": False},
        }
    }
)


def _good_letter() -> str:
    sentence = (
        "I am an AI Engineer with 6 years building production RAG pipelines and "
        "evaluation harnesses for support agents. "
        "My work uses Python to measure retrieval quality so the support agent cites the right context. "
    )
    body = " ".join([sentence] * 3)
    return (
        "Hello Northwind team,\n\n"
        f"{body}\n\n"
        "This maps to your Northwind role owning retrieval quality and RAG evaluation "
        "for the support agent.\n\n"
        "I am available to discuss next steps.\n"
    )


def _message_body(msg: MIMEMultipart) -> str:
    part = msg.get_payload()[0]
    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8")


def test_good_letter_passes_guardrails():
    letter = _good_letter()
    assert 120 <= word_count(letter) <= 220
    verdict = validate_cover_letter(letter, PROFILE, JOB, SETTINGS)
    assert verdict["passed"] is True, verdict
    assert verdict["quality_score"] >= 0.7


def test_short_letter_fails_size():
    verdict = validate_cover_letter("Hello Northwind. I am available.", PROFILE, JOB, SETTINGS)
    assert "G1" in verdict["failed_checks"]
    assert verdict["passed"] is False


def test_cliche_fails():
    letter = _good_letter().replace(
        "I am an AI Engineer",
        "I am a passionate AI Engineer",
    )
    verdict = validate_cover_letter(letter, PROFILE, JOB, SETTINGS)
    assert "G5" in verdict["failed_checks"]


def test_invented_number_and_company_fail_g4():
    letter = _good_letter().replace("6 years", "40 years").replace("Northwind", "Initech")
    verdict = validate_cover_letter(letter, PROFILE, JOB, SETTINGS)
    assert "G4" in verdict["failed_checks"]


def test_language_mismatch_fails_g7():
    letter = " ".join(["Olá equipe, gostaria de falar sobre a vaga e a minha experiência."] * 30)
    verdict = validate_cover_letter(letter, PROFILE, JOB, SETTINGS)
    assert "G7" in verdict["failed_checks"]


def test_fallback_is_short_and_uses_role():
    text = fallback_text(PROFILE, JOB)
    assert word_count(text) <= 80
    assert "AI Engineer" in text
    assert "40" not in text


def test_disabled_skips_generation(monkeypatch: pytest.MonkeyPatch):
    def _boom(**_kwargs: Any) -> str:
        raise AssertionError("LLM should not be called")

    monkeypatch.setattr("cover_letter.chat_completion", _boom)
    decision = prepare_for_channel(JOB, channel="email", email_cfg={}, profile=PROFILE)
    assert decision is None


def test_llm_failure_uses_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("cover_letter.chat_completion", lambda *_args, **_kwargs: None)
    decision = prepare_for_channel(
        JOB,
        channel="email",
        email_cfg={"cover_letter": SETTINGS},
        profile=PROFILE,
        root=tmp_path,
    )
    assert decision is not None
    assert decision["used_fallback"] is True
    assert decision["injected"] is True
    assert decision["passed_guardrails"] is False
    assert "qualifications" in decision["text"]
    stored = json.loads((tmp_path / "state" / "cover-letters.json").read_text(encoding="utf-8"))
    assert stored["entries"]


def test_g4_never_injects_invented_letter(tmp_path: Path):
    invented = _good_letter().replace("6 years", "40 years") + " I worked at Initech."
    decision = prepare_for_channel(
        JOB,
        channel="email",
        email_cfg={"cover_letter": {**SETTINGS, "allow_fallback": True}},
        profile=PROFILE,
        root=tmp_path,
        complete_fn=lambda *_a, **_k: invented,
    )
    assert decision is not None
    assert "G4" in decision["failed_checks"]
    assert "Initech" not in decision["text"]
    assert "40" not in decision["text"]
    assert decision["used_fallback"] is True
    assert "Initech" in decision["rejected_text"]


def test_g4_without_fallback_injects_nothing(tmp_path: Path):
    invented = _good_letter() + " I led 40 engineers at Initech."
    decision = prepare_for_channel(
        JOB,
        channel="email",
        email_cfg={"cover_letter": {**SETTINGS, "allow_fallback": False}},
        profile=PROFILE,
        root=tmp_path,
        complete_fn=lambda *_a, **_k: invented,
    )
    assert decision is not None
    assert decision["injected"] is False
    assert decision["text"] == ""
    assert decision["used_fallback"] is False


def test_approved_letter_is_injected_and_cached(tmp_path: Path):
    calls = {"n": 0}
    letter = _good_letter()

    def _complete(*_args: Any, **_kwargs: Any) -> str:
        calls["n"] += 1
        return letter

    decision = prepare_for_channel(
        JOB,
        channel="email",
        email_cfg={"cover_letter": SETTINGS},
        profile=PROFILE,
        root=tmp_path,
        complete_fn=_complete,
    )
    assert decision is not None
    assert decision["passed_guardrails"] is True
    assert decision["injected"] is True
    assert "RAG" in decision["text"]
    assert calls["n"] == 1

    again = prepare_for_channel(
        JOB,
        channel="email",
        email_cfg={"cover_letter": SETTINGS},
        profile=PROFILE,
        root=tmp_path,
        complete_fn=_complete,
    )
    assert again is not None
    assert again["text"] == letter
    assert calls["n"] == 1


def test_email_body_uses_cover_when_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    letter = _good_letter()
    template = tmp_path / "body.txt"
    template.write_text("Hello,\n\nApplying for {role}.\n", encoding="utf-8")
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4")
    cfg = {
        "body_template_file": str(template),
        "subject_template": "Application for {role}",
        "sender_name": "Test User",
        "sender_email": "test@gmail.com",
        "resume_path": str(resume),
        "cover_letter": SETTINGS,
    }
    monkeypatch.setattr("email_apply.ROOT", tmp_path)
    monkeypatch.setattr("cover_letter.load_profile", lambda *_a, **_k: PROFILE)
    monkeypatch.setattr("cover_letter.chat_completion", lambda *_a, **_k: letter)

    from email_apply import build_message

    msg = build_message(cfg, JOB, "recruiter@northwind.ai")
    body = _message_body(msg)
    assert "RAG pipelines" in body
    assert "Applying for" not in body
    assert msg.cover_decision["injected"] is True  # type: ignore[attr-defined]


def test_email_body_unchanged_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    template = tmp_path / "body.txt"
    template.write_text("Hello,\n\nApplying for {role}.\n", encoding="utf-8")
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4")
    cfg = {
        "body_template_file": str(template),
        "subject_template": "Application for {role}",
        "sender_name": "Test User",
        "sender_email": "test@gmail.com",
        "resume_path": str(resume),
    }

    def _boom(**_kwargs: Any) -> str:
        raise AssertionError("LLM should not be called")

    monkeypatch.setattr("email_apply.ROOT", tmp_path)
    monkeypatch.setattr("cover_letter.chat_completion", _boom)
    from email_apply import build_message

    msg = build_message(cfg, {"role": "AI Engineer", "company": "Acme"}, "recruiter@acme.ai")
    assert "Applying for AI Engineer" in _message_body(msg)


def test_form_overlay_injects_when_channel_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    letter = _good_letter()
    monkeypatch.setattr("cover_letter.chat_completion", lambda *_a, **_k: letter)
    cfg = {"cover_letter": {**SETTINGS, "channels": {"email": False, "form": True, "linkedin": False}}}
    updated = overlay_form_cover(PROFILE, JOB, email_cfg=cfg, root=tmp_path)
    assert updated["cover_letter_default"] == letter
    assert updated is not PROFILE


def test_form_overlay_keeps_static_cover_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def _boom(**_kwargs: Any) -> str:
        raise AssertionError("LLM should not be called")

    monkeypatch.setattr("cover_letter.chat_completion", _boom)
    updated = overlay_form_cover(PROFILE, JOB, email_cfg={}, root=tmp_path)
    assert updated["cover_letter_default"] == PROFILE["cover_letter_default"]


def test_chat_completion_retries_429(monkeypatch: pytest.MonkeyPatch):
    calls = {"n": 0}

    class _Resp:
        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

        def read(self) -> bytes:
            body = {"choices": [{"message": {"content": "Hello there"}}]}
            return json.dumps(body).encode("utf-8")

    def _urlopen(req: Any, timeout: int = 30) -> _Resp:
        del timeout
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "rate", hdrs=None, fp=None)
        return _Resp()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("cover_letter.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("cover_letter.urllib.request.urlopen", _urlopen)
    assert chat_completion("Say hello", model="gpt-4o-mini") == "Hello there"
    assert calls["n"] == 2


def test_linkedin_channel_is_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def _boom(**_kwargs: Any) -> str:
        raise AssertionError("LLM should not be called")

    monkeypatch.setattr("cover_letter.chat_completion", _boom)
    cfg = {"cover_letter": {**SETTINGS, "channels": {"email": False, "form": False, "linkedin": True}}}
    decision = prepare_for_channel(
        JOB,
        channel="linkedin",
        email_cfg=cfg,
        profile=PROFILE,
        root=tmp_path,
    )
    assert decision is None
