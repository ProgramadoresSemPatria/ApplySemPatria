"""PDF-first master CV tests — polished Word-export template."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cv_master_pdf import (  # noqa: E402
    analyze_master_pdf_layout,
    build_master_pdf,
    default_template_pdf_path,
    resolve_template_pdf_path,
)

TEMPLATE_PDF = Path(__file__).resolve().parent.parent / "templates" / "cv-master" / "MASTER_CV.pdf"


@pytest.mark.skipif(not TEMPLATE_PDF.is_file(), reason="MASTER_CV.pdf template missing")
def test_template_pdf_has_polished_layout():
    layout = analyze_master_pdf_layout(TEMPLATE_PDF)
    assert layout["page_count"] == 3
    assert layout["has_summary_heading"] is True
    assert layout["has_experience_heading"] is True
    assert layout["skill_line_count"] >= 2
    assert layout["right_aligned_location_count"] >= 1
    name = layout["name_line"]
    assert name is not None
    assert "LIMA" in name["text"].upper()
    # Name is centered on A4 (~596pt wide)
    center = (name["x0"] + name["x1"]) / 2
    assert 250 < center < 350


@pytest.mark.skipif(not TEMPLATE_PDF.is_file(), reason="MASTER_CV.pdf template missing")
def test_build_master_pdf_copies_template_bytes(tmp_path: Path):
    dest = tmp_path / "master.pdf"
    build_master_pdf(dest)
    assert dest.is_file()
    assert dest.stat().st_size == TEMPLATE_PDF.stat().st_size
    built_layout = analyze_master_pdf_layout(dest)
    template_layout = analyze_master_pdf_layout(TEMPLATE_PDF)
    assert built_layout["page_count"] == template_layout["page_count"]
    assert built_layout["skill_line_count"] == template_layout["skill_line_count"]


def test_resolve_template_pdf_prefers_committed_template(tmp_path: Path, monkeypatch):
    committed = tmp_path / "templates" / "cv-master" / "MASTER_CV.pdf"
    committed.parent.mkdir(parents=True)
    committed.write_bytes(b"%PDF-1.4\n% test\n")
    fallback = tmp_path / "Downloads" / "MASTER_CV.docx.pdf"
    fallback.parent.mkdir(parents=True)
    fallback.write_bytes(b"%PDF-1.4\n% fallback\n")

    monkeypatch.setattr("cv_master_pdf.DEFAULT_TEMPLATE_PDF", committed)
    monkeypatch.setattr("cv_master_pdf.FALLBACK_TEMPLATE_PDF", fallback)
    assert resolve_template_pdf_path() == committed.resolve()


@pytest.mark.skipif(not TEMPLATE_PDF.is_file(), reason="MASTER_CV.pdf template missing")
def test_default_template_pdf_path_points_to_committed_file():
    assert default_template_pdf_path().name == "MASTER_CV.pdf"
    assert default_template_pdf_path().is_file()
