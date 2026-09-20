"""LinkedIn PDF → master DOCX onboard pipeline tests (no network)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cv_master_docx import DEFAULT_TEMPLATE  # noqa: E402
from cv_master_schema import validate_cv_profile  # noqa: E402
from resume_chameleon import (  # noqa: E402
    chameleon_is_configured,
    run_import_linkedin_pdf_to_master,
    run_onboard_from_linkedin,
    run_sync_master_from_template,
)

FIXTURE_TEXT = Path(__file__).resolve().parent / "fixtures" / "cv-master" / "linkedin-profile.txt"
TEMPLATE_PDF = Path(__file__).resolve().parent.parent / "templates" / "cv-master" / "MASTER_CV.pdf"


@pytest.fixture
def linkedin_text() -> str:
    assert FIXTURE_TEXT.is_file()
    return FIXTURE_TEXT.read_text(encoding="utf-8")


@pytest.fixture
def fake_pdf(tmp_path: Path, linkedin_text: str, monkeypatch) -> Path:
    pdf_path = tmp_path / "profile.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        "cv_master_linkedin_pdf.extract_pdf_text",
        lambda _path: linkedin_text,
    )
    return pdf_path


@pytest.fixture
def chameleon_state(tmp_path: Path, monkeypatch) -> Path:
    state_root = tmp_path / "state"
    masters = state_root / "chameleon" / "masters" / "ai-engineer"
    masters.mkdir(parents=True)
    profile_dir = state_root / "chameleon" / "profile"
    profile_dir.mkdir(parents=True)
    config_path = tmp_path / "resume-chameleon-config.json"
    config_path.write_text(json.dumps({"enabled": True, "masters": []}) + "\n", encoding="utf-8")

    monkeypatch.setattr("resume_chameleon.ROOT", tmp_path)
    monkeypatch.setattr(
        "resume_chameleon._profile_json_path",
        lambda track_id: profile_dir / f"{track_id}.json",
    )
    monkeypatch.setattr(
        "resume_chameleon.chameleon_config_path",
        lambda track_id=None: config_path,
    )

    def _load(track_id=None):
        if config_path.is_file():
            return json.loads(config_path.read_text(encoding="utf-8"))
        return {"enabled": True, "masters": []}

    def _save(tid, cfg):
        config_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    monkeypatch.setattr("resume_chameleon.load_chameleon_config", _load)
    monkeypatch.setattr("resume_chameleon.save_chameleon_config", _save)
    monkeypatch.setattr("resume_chameleon.sync_master_keywords", lambda tid: None)
    monkeypatch.setattr(
        "resume_chameleon._linkedin_profile_json_path",
        lambda track_id: profile_dir / f"{track_id}-linkedin.json",
    )
    return tmp_path


@pytest.mark.skipif(
    not DEFAULT_TEMPLATE.is_file() or not TEMPLATE_PDF.is_file(),
    reason="MASTER_CV template missing",
)
def test_run_import_linkedin_pdf_uses_template_master(fake_pdf: Path, chameleon_state: Path, monkeypatch):
    monkeypatch.setattr("cv_master_pdf.DEFAULT_TEMPLATE_PDF", TEMPLATE_PDF)
    result = run_import_linkedin_pdf_to_master("ai-engineer", fake_pdf)
    assert result["ok"] is True, result
    master_pdf = Path(result["master_pdf_path"])
    assert master_pdf.is_file()
    assert master_pdf.stat().st_size == TEMPLATE_PDF.stat().st_size
    linkedin_json = Path(result["linkedin_profile_path"])
    assert linkedin_json.is_file()
    profile_json = Path(result["profile_path"])
    assert profile_json.is_file()
    profile_data = json.loads(profile_json.read_text(encoding="utf-8"))
    assert profile_data["full_name"] == "CAIO LIMA"
    cfg = json.loads((chameleon_state / "resume-chameleon-config.json").read_text(encoding="utf-8"))
    assert chameleon_is_configured(cfg)
    assert cfg["masters"][0]["format"] == "pdf"


@pytest.mark.skipif(
    not DEFAULT_TEMPLATE.is_file() or not TEMPLATE_PDF.is_file(),
    reason="MASTER_CV template missing",
)
def test_run_sync_master_from_template(fake_pdf: Path, chameleon_state: Path, monkeypatch):
    monkeypatch.setattr("cv_master_pdf.DEFAULT_TEMPLATE_PDF", TEMPLATE_PDF)
    result = run_sync_master_from_template("ai-engineer", copy_to_downloads=False)
    assert result["ok"] is True, result
    pdf = Path(result["master_pdf_path"])
    assert pdf.stat().st_size == TEMPLATE_PDF.stat().st_size
    profile_data = json.loads(Path(result["profile_path"]).read_text(encoding="utf-8"))
    assert not validate_cv_profile(profile_data)


def test_run_onboard_rejects_page_pdf_fallback(monkeypatch, fake_pdf: Path, chameleon_state: Path):
    from linkedin_profile_pdf_download import PdfDownloadResult  # noqa: E402

    monkeypatch.setattr(
        "resume_chameleon.run_import_linkedin_pdf_to_master",
        lambda *a, **k: {"ok": True, "message": "mock"},
    )

    async def fake_download(url, dest, *, headless=False, timeout_ms=90_000):
        return PdfDownloadResult(
            ok=True,
            path=dest,
            message="page snapshot",
            method="page_pdf",
        )

    monkeypatch.setattr("linkedin_profile_pdf_download.download_linkedin_profile_pdf", fake_download)
    monkeypatch.setattr(
        "linkedin_profile_pdf_download.resolve_linkedin_url",
        lambda url, tid: "https://www.linkedin.com/in/test/",
    )

    result = run_onboard_from_linkedin(
        "ai-engineer",
        linkedin_url="https://www.linkedin.com/in/test/",
        allow_page_pdf_fallback=False,
    )
    assert result["ok"] is False
    assert result.get("needs_linkedin_pdf") is True


def test_run_onboard_skip_download_uses_provided_pdf(
    monkeypatch, fake_pdf: Path, chameleon_state: Path
):
    monkeypatch.setattr(
        "resume_chameleon.run_import_linkedin_pdf_to_master",
        lambda tid, pdf, **kw: {
            "ok": True,
            "message": "ready",
            "master_path": str(chameleon_state / "master.docx"),
            "pdf_method": "provided",
        },
    )
    result = run_onboard_from_linkedin(
        "ai-engineer",
        pdf_path=fake_pdf,
        skip_download=True,
        linkedin_url="https://www.linkedin.com/in/test/",
    )
    assert result["ok"] is True
    assert result["pdf_method"] == "provided"
