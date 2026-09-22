"""Coverage for url_apply pipeline (mocked Playwright)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from url_apply import (  # noqa: E402
    _pick_option,
    autofill,
    extract_fields,
    fill_country_dropdown,
    log_submission,
    notify_form_change,
    print_autofill_report,
    resolve_shortlink,
    reveal_form,
    try_submit,
)


def test_pick_option_exact_and_substring():
    opts = ["Brazil", "United States", "Argentina"]
    assert _pick_option(opts, "Brazil", None) == "Brazil"
    assert _pick_option(opts, "united", None) == "United States"
    assert _pick_option(opts, "Chile", None) is None


def test_pick_option_regex():
    opts = ["Yes, I agree", "No"]
    assert _pick_option(opts, "x", r"^Yes") == "Yes, I agree"


def test_pick_option_invalid_regex_falls_back():
    opts = ["A", "B"]
    assert _pick_option(opts, "a", "[invalid") == "A"


@pytest.mark.asyncio
async def test_extract_fields_returns_eval_result():
    page = MagicMock()
    page.evaluate = AsyncMock(return_value=[{"idx": 0, "type": "text", "label": "Name"}])
    fields = await extract_fields(page)
    assert fields[0]["label"] == "Name"


@pytest.mark.asyncio
async def test_extract_fields_swallows_errors():
    page = MagicMock()
    page.evaluate = AsyncMock(side_effect=RuntimeError("boom"))
    assert await extract_fields(page) == []


@pytest.mark.asyncio
async def test_autofill_text_select_radio_and_file(tmp_path: Path, monkeypatch):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF")
    profile = {"resume_path": str(resume), "full_name": "Test User", "email": "t@example.com"}

    fields = [
        {"idx": 0, "type": "text", "tag": "input", "label": "Full name", "name": "name"},
        {"idx": 1, "type": "select", "tag": "select", "label": "Country", "options": ["Brazil", "US"]},
        {"idx": 2, "type": "radio", "tag": "input", "label": "Remote?", "option": "Yes", "group": "remote"},
        {"idx": 3, "type": "file", "tag": "input", "label": "Resume"},
    ]

    page = MagicMock()
    page.set_input_files = AsyncMock()
    page.eval_on_selector = AsyncMock()
    page.fill = AsyncMock()
    page.select_option = AsyncMock()
    page.check = AsyncMock()

    def fake_resolve(field, prof, answers, rules):
        if field["idx"] == 0:
            return {"status": "ok", "value": "Test User", "source": "profile"}
        if field["idx"] == 1:
            return {"status": "ok", "value": "Brazil", "source": "profile"}
        if field["idx"] == 2:
            return {"status": "ok", "value": "Yes", "source": "answers", "option_regex": None}
        return {"status": "none", "value": None, "source": None, "reason": "unmapped"}

    monkeypatch.setattr("form_answers.resolve", fake_resolve)
    monkeypatch.setattr("form_answers.load_bank", lambda *_a: [])

    report = await autofill(page, fields, profile, {}, track_id=None)
    assert report["resume_uploaded"] is True
    assert len(report["filled"]) >= 2
    page.fill.assert_awaited()
    page.select_option.assert_awaited()


@pytest.mark.asyncio
async def test_autofill_needs_input_and_unmapped():
    page = MagicMock()
    fields = [{"idx": 0, "type": "text", "tag": "input", "label": "Secret", "required": True}]
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "form_answers.resolve",
        lambda *a, **k: {"status": "empty", "value": None, "source": "profile.phone", "reason": ""},
    )
    monkeypatch.setattr("form_answers.load_bank", lambda *_a: [])
    report = await autofill(page, fields, {}, {}, track_id=None)
    assert report["needs_input"]
    monkeypatch.undo()


def test_print_autofill_report(capsys):
    print_autofill_report(
        {
            "filled": [{"idx": 0, "label": "Name", "value": "A", "source": "profile"}],
            "needs_input": [{"idx": 1, "label": "Phone", "required": True, "source": "profile.phone"}],
            "unmapped": [{"idx": 2, "label": "Weird", "type": "text", "required": False}],
            "resume_uploaded": True,
        }
    )
    out = capsys.readouterr().out
    assert "filled 1" in out
    assert "NEEDS INPUT" in out
    assert "UNMAPPED" in out


def test_log_submission(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("url_apply.ROOT", tmp_path)
    log_submission("https://apply.example/a", "https://apply.example/a", company="Acme", role="AI", confirmed=True, job_key="jk1")
    data = json.loads((tmp_path / "state" / "url-applications.json").read_text(encoding="utf-8"))
    assert data["submitted"][0]["job_key"] == "jk1"
    assert data["submitted"][0]["confirmed"] is True


@pytest.mark.asyncio
async def test_resolve_shortlink_follows_external_href():
    page = MagicMock()
    page.url = "https://lnkd.in/abc"
    page.eval_on_selector_all = AsyncMock(return_value=["https://careers.example.com/apply"])
    page.goto = AsyncMock()
    with patch("url_apply.asyncio.sleep", new=AsyncMock()):
        await resolve_shortlink(page)
    page.goto.assert_awaited()


@pytest.mark.asyncio
async def test_reveal_form_clicks_apply_cta():
    page = MagicMock()
    page.evaluate = AsyncMock()
    with patch("url_apply.extract_fields", AsyncMock(return_value=[{"type": "hidden"}])):
        loc = MagicMock()
        loc.count = AsyncMock(return_value=1)
        loc.first.click = AsyncMock()
        page.get_by_role = MagicMock(return_value=loc)
        with patch("url_apply.asyncio.sleep", new=AsyncMock()):
            await reveal_form(page)
    loc.first.click.assert_awaited()


@pytest.mark.asyncio
async def test_fill_country_dropdown():
    page = MagicMock()
    btn = MagicMock()
    btn.count = AsyncMock(return_value=1)
    btn.first.click = AsyncMock()
    opt = MagicMock()
    opt.count = AsyncMock(return_value=1)
    opt.nth.return_value.inner_text = AsyncMock(return_value="Brazil")
    opt.nth.return_value.click = AsyncMock()
    page.get_by_role = MagicMock(return_value=btn)
    page.get_by_text = MagicMock(return_value=opt)
    with patch("url_apply.asyncio.sleep", new=AsyncMock()):
        ok = await fill_country_dropdown(page, "Brazil")
    assert ok is True


@pytest.mark.asyncio
async def test_try_submit_success():
    page = MagicMock()
    page.url = "https://apply.example.com/form"
    btn = MagicMock()
    btn.count = AsyncMock(return_value=1)
    btn.first.wait_for = AsyncMock()
    btn.first.is_enabled = AsyncMock(return_value=True)
    btn.first.click = AsyncMock()
    page.get_by_role = MagicMock(return_value=btn)
    page.inner_text = AsyncMock(return_value="Thank you for applying")
    with patch("url_apply.asyncio.sleep", new=AsyncMock()):
        res = await try_submit(page)
    assert res["confirmed"] is True


@pytest.mark.asyncio
async def test_notify_form_change():
    page = MagicMock()
    page.evaluate = AsyncMock()
    with patch("url_apply.asyncio.sleep", new=AsyncMock()):
        await notify_form_change(page)
    page.evaluate.assert_awaited()
