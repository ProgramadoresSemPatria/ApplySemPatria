#!/usr/bin/env python3
"""CV master PDF — polished Word-export template is the source of truth."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE_PDF = ROOT / "templates" / "cv-master" / "MASTER_CV.pdf"
FALLBACK_TEMPLATE_PDF = Path.home() / "Downloads" / "MASTER_CV.docx.pdf"


def resolve_template_pdf_path(explicit: Path | str | None = None) -> Path:
    """Return the polished master PDF template (committed or ~/Downloads fallback)."""
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if path.is_file():
            return path
        raise FileNotFoundError(f"Master PDF template not found: {path}")
    for candidate in (DEFAULT_TEMPLATE_PDF, FALLBACK_TEMPLATE_PDF):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "Master PDF template missing. Export templates/cv-master/MASTER_CV.docx to PDF "
        "and save as templates/cv-master/MASTER_CV.pdf (or ~/Downloads/MASTER_CV.docx.pdf)."
    )


def default_template_pdf_path() -> Path:
    return resolve_template_pdf_path()


def copy_master_pdf_from_template(
    dest_pdf: Path | str,
    *,
    template: Path | str | None = None,
) -> Path:
    """Copy the polished template PDF — preserves layout, alignment, icons, columns."""
    src = resolve_template_pdf_path(template)
    out = Path(dest_pdf).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, out)
    if not out.is_file():
        raise RuntimeError(f"Failed to copy master PDF template → {out}")
    return out


def default_master_pdf_path(track_id: str) -> Path:
    return ROOT / "state" / "chameleon" / "masters" / track_id / "master.pdf"


def analyze_master_pdf_layout(pdf_path: Path | str) -> dict[str, Any]:
    """Extract layout metrics for regression tests (name center, location right, pages)."""
    import pymupdf as fitz  # noqa: WPS433

    path = Path(pdf_path).expanduser().resolve()
    doc = fitz.open(str(path))
    try:
        page = doc[0]
        page_width = float(page.rect.width)
        lines: list[dict[str, Any]] = []
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans") or []
                if not spans:
                    continue
                text = "".join(str(span.get("text") or "") for span in spans).replace("\u200b", "").strip()
                if not text:
                    continue
                bbox = line.get("bbox") or (0, 0, 0, 0)
                lines.append(
                    {
                        "text": text,
                        "x0": float(bbox[0]),
                        "y0": float(bbox[1]),
                        "x1": float(bbox[2]),
                        "size": float(spans[0].get("size") or 0),
                    }
                )

        name_line = next((ln for ln in lines if ln["y0"] < 45 and "LIMA" in ln["text"].upper()), None)
        skill_lines = [ln for ln in lines if 60 <= ln["y0"] <= 90 and "|" in ln["text"]]
        right_aligned_locations = [
            ln for ln in lines if ln["x0"] > page_width * 0.78 and ln["size"] >= 9.0 and ln["y0"] > 35
        ]
        return {
            "path": str(path),
            "page_count": doc.page_count,
            "page_width": page_width,
            "name_line": name_line,
            "skill_line_count": len(skill_lines),
            "right_aligned_location_count": len(right_aligned_locations),
            "has_summary_heading": any(ln["text"] == "Summary" for ln in lines),
            "has_experience_heading": any(ln["text"] == "Experience" for ln in lines),
        }
    finally:
        doc.close()


def build_master_pdf(
    dest_pdf: Path | str,
    *,
    template: Path | str | None = None,
) -> Path:
    """Build recruiter-ready master PDF from the polished template copy."""
    return copy_master_pdf_from_template(dest_pdf, template=template)
