"""Coverage for form_answers resolver."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from form_answers import add_rule, bank_path, load_bank, resolve  # noqa: E402


def test_load_bank_missing_returns_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("form_answers.ROOT", tmp_path)
    monkeypatch.setattr("form_answers.bank_path", lambda *_a: tmp_path / "missing.json")
    assert load_bank() == []


def test_load_bank_reads_rules(tmp_path: Path, monkeypatch):
    path = tmp_path / "form-answers.json"
    path.write_text(json.dumps({"rules": [{"q": "email", "profile_key": "email"}]}), encoding="utf-8")
    monkeypatch.setattr("form_answers.bank_path", lambda *_a: path)
    assert load_bank()[0]["profile_key"] == "email"


def test_resolve_from_explicit_answers():
    field = {"name": "email", "label": "Email", "type": "text"}
    out = resolve(field, {}, answers={"email": "a@b.com"})
    assert out["status"] == "ok"
    assert out["value"] == "a@b.com"


def test_resolve_from_rule_profile_key():
    field = {"label": "Email address", "type": "text"}
    rules = [{"q": "email", "profile_key": "email"}]
    out = resolve(field, {"email": "user@test.com"}, rules=rules)
    assert out["status"] == "ok"


def test_resolve_empty_profile_key():
    field = {"label": "Phone number", "type": "text"}
    rules = [{"q": "phone", "profile_key": "phone"}]
    out = resolve(field, {}, rules=rules)
    assert out["status"] == "empty"


def test_resolve_no_match():
    field = {"label": "Favorite color", "type": "text"}
    out = resolve(field, {}, rules=[])
    assert out["status"] == "none"


def test_add_rule_appends(tmp_path: Path, monkeypatch):
    path = tmp_path / "form-answers.json"
    path.write_text(json.dumps({"rules": []}), encoding="utf-8")
    monkeypatch.setattr("form_answers.bank_path", lambda *_a: path)
    add_rule("linkedin", profile_key="linkedin_url", prepend=False)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["rules"][-1]["profile_key"] == "linkedin_url"
