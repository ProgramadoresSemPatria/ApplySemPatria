"""PDF resume headline read/write for ResumeChameleon."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

try:
    import pymupdf as fitz  # PyMuPDF >= 1.24
except ImportError:  # pragma: no cover
    try:
        import fitz  # legacy import name
    except ImportError:
        fitz = None  # type: ignore[assignment,misc]

DEFAULT_PDF_FONT_PATH = "/System/Library/Fonts/Supplemental/Tahoma.ttf"
PDF_FONT_NAME = "ChameleonTahoma"


def _require_fitz() -> Any:
    if fitz is None:
        raise RuntimeError("PyMuPDF is required for PDF output. Install: pip install pymupdf")
    return fitz


def _line_text(line: dict[str, Any]) -> str:
    return "".join(span.get("text", "") for span in line.get("spans", [])).replace("\u200b", "").strip()


def _color_int_to_rgb(color: int) -> tuple[float, float, float]:
    red = ((color >> 16) & 255) / 255
    green = ((color >> 8) & 255) / 255
    blue = (color & 255) / 255
    return red, green, blue


def _resolve_font_path(cfg: dict[str, Any] | None) -> Path:
    data = cfg or {}
    raw = (data.get("pdf_font_path") or DEFAULT_PDF_FONT_PATH).strip()
    path = Path(raw).expanduser()
    if path.is_file():
        return path
    raise FileNotFoundError(
        f"Headline font not found: {path}. Set pdf_font_path in CV Chameleon config."
    )


def _line_style(line: dict[str, Any], *, font_path: Path) -> dict[str, Any]:
    span = (line.get("spans") or [{}])[0]
    size = float(span.get("size") or 11.5)
    color = int(span.get("color") or 7305336)
    return {
        "font_path": str(font_path),
        "font_size": size,
        "color": color,
        "rgb": _color_int_to_rgb(color),
    }


def _iter_lines(page: Any) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            lines.append(line)
    return lines


def _is_skill_line(text: str, y: float, *, skills_y_min: float, skills_y_max: float) -> bool:
    return skills_y_min <= y <= skills_y_max and "|" in text


def extract_pdf_headline(
    pdf_path: Path,
    *,
    skills_y_min: float = 65.0,
    skills_y_max: float = 95.0,
    title_y_max: float = 65.0,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return title line and skill lines with bbox + original font styling."""
    fitz_mod = _require_fitz()
    font_path = _resolve_font_path(cfg)
    page = fitz_mod.open(str(pdf_path))[0]
    title = ""
    skill_lines: list[dict[str, Any]] = []
    for line in _iter_lines(page):
        bbox = line.get("bbox") or (0, 0, 0, 0)
        y = bbox[1]
        text = _line_text(line)
        if not text:
            continue
        if y < title_y_max and "Engineer" in text and not title:
            title = text
        elif _is_skill_line(text, y, skills_y_min=skills_y_min, skills_y_max=skills_y_max):
            skill_lines.append(
                {
                    "text": text,
                    "bbox": list(bbox),
                    "style": _line_style(line, font_path=font_path),
                }
            )
    return {"title": title, "skill_lines": skill_lines}


def skills_from_pdf_headline(headline: dict[str, Any], separator: str = " | ") -> list[str]:
    skills: list[str] = []
    for row in headline.get("skill_lines") or []:
        skills.extend(part.strip() for part in str(row.get("text") or "").split(separator) if part.strip())
    return skills


def measure_text_width(text: str, *, font_path: Path, font_size: float) -> float:
    fitz_mod = _require_fitz()
    font = fitz_mod.Font(fontfile=str(font_path))
    return float(font.text_length(text, fontsize=font_size))


def distribute_skills_to_lines(
    skills: list[str],
    *,
    separator: str = " | ",
    max_lines: int = 2,
    max_chars_per_line: int = 95,
    font_path: Path | None = None,
    font_size: float = 11.5,
) -> list[str]:
    """Split merged skills across headline lines respecting visual width."""
    if not skills:
        return []
    fp = font_path or Path(DEFAULT_PDF_FONT_PATH)

    def line_width(text: str) -> float:
        if fp.is_file():
            try:
                return measure_text_width(text, font_path=fp, font_size=font_size)
            except Exception:  # noqa: BLE001
                return len(text) * 4.8
        return len(text) * 4.8

    max_width = max_chars_per_line * 4.8
    lines: list[str] = []
    current: list[str] = []

    for skill in skills:
        if len(lines) >= max_lines:
            current.append(skill)
            continue
        candidate = separator.join([*current, skill]) if current else skill
        if current and line_width(candidate) > max_width:
            lines.append(separator.join(current))
            current = [skill]
        else:
            current.append(skill)

    if current:
        if len(lines) < max_lines:
            lines.append(separator.join(current))
        else:
            joined = separator.join([lines[-1], separator.join(current)])
            lines[-1] = joined

    return lines[:max_lines]


def _fit_font_size(
    text: str,
    *,
    font_path: Path,
    max_size: float,
    min_size: float,
    max_width: float,
) -> float:
    for size in [max_size] + [round(max_size - i * 0.5, 1) for i in range(1, 8)]:
        if size < min_size:
            break
        if measure_text_width(text, font_path=font_path, font_size=size) <= max_width * 0.97:
            return size
    return min_size


def _page_content_bounds(page: Any) -> tuple[float, float, int]:
    """Return min_y, max_y, and visible character count for a page."""
    min_y = float("inf")
    max_y = 0.0
    chars = 0
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                bbox = span.get("bbox") or (0, 0, 0, 0)
                min_y = min(min_y, float(bbox[1]))
                max_y = max(max_y, float(bbox[3]))
                chars += len(str(span.get("text") or "").strip())
    if min_y == float("inf"):
        return 0.0, 0.0, 0
    return min_y, max_y, chars


def _page_is_blank(page: Any, *, min_chars: int = 5) -> bool:
    _, _, chars = _page_content_bounds(page)
    return chars < min_chars


def trim_blank_trailing_pages(doc: Any, *, max_pages: int | None = None) -> int:
    """Remove empty trailing pages and never exceed max_pages when set."""
    fitz_mod = _require_fitz()
    removed = 0
    while doc.page_count > 0:
        if max_pages is not None and doc.page_count <= max_pages:
            break
        if not _page_is_blank(doc[-1]):
            break
        doc.delete_page(doc.page_count - 1)
        removed += 1
    if max_pages is not None:
        while doc.page_count > max_pages:
            if _page_is_blank(doc[-1]):
                doc.delete_page(doc.page_count - 1)
                removed += 1
                continue
            break
    return removed


def compact_sparse_trailing_pages(doc: Any, *, cfg: dict[str, Any] | None = None) -> int:
    """Merge a short tail page onto the previous page when it fits."""
    fitz_mod = _require_fitz()
    data = cfg or {}
    if not data.get("compact_trailing_pages", True):
        return 0

    sparse_tail_max_y = float(data.get("pdf_sparse_tail_max_y", 220.0))
    merge_gap = float(data.get("pdf_tail_merge_gap", 16.0))
    bottom_margin = float(data.get("pdf_bottom_margin", 36.0))
    prev_min_fill_ratio = float(data.get("pdf_prev_page_min_fill_ratio", 0.55))
    merged = 0

    while doc.page_count > 1:
        tail_idx = doc.page_count - 1
        prev = doc[tail_idx - 1]
        tail = doc[tail_idx]
        _, prev_max_y, _ = _page_content_bounds(prev)
        tail_min_y, tail_max_y, tail_chars = _page_content_bounds(tail)
        if tail_chars < 5 or tail_max_y > sparse_tail_max_y:
            break
        if prev.rect.height <= 0 or (prev_max_y / prev.rect.height) < prev_min_fill_ratio:
            break

        tail_height = tail_max_y - tail_min_y
        target_y = prev_max_y + merge_gap
        if target_y + tail_height > prev.rect.height - bottom_margin:
            break

        tail_doc = fitz_mod.open()
        tail_doc.insert_pdf(doc, from_page=tail_idx, to_page=tail_idx)
        target_rect = fitz_mod.Rect(0, target_y, prev.rect.width, target_y + tail_height + 10)
        clip = fitz_mod.Rect(0, tail_min_y, tail.rect.width, tail_max_y + 5)
        prev.show_pdf_page(target_rect, tail_doc, 0, clip=clip)
        tail_doc.close()
        doc.delete_page(tail_idx)
        merged += 1

    return merged


def finalize_pdf_page_layout(
    doc: Any,
    *,
    master_page_count: int,
    cfg: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Keep edited PDFs from growing and compact sparse tail pages when possible."""
    blank_removed = trim_blank_trailing_pages(doc, max_pages=master_page_count)
    merged = compact_sparse_trailing_pages(doc, cfg=cfg)
    blank_removed += trim_blank_trailing_pages(doc, max_pages=master_page_count)
    return {
        "master_pages": master_page_count,
        "output_pages": doc.page_count,
        "blank_pages_removed": blank_removed,
        "tail_pages_merged": merged,
    }


def _insert_styled_line(
    page: Any,
    bbox: list[float],
    text: str,
    style: dict[str, Any],
    *,
    min_size: float = 8.0,
) -> float:
    fitz_mod = _require_fitz()
    font_path = Path(style.get("font_path") or DEFAULT_PDF_FONT_PATH)
    base_size = float(style.get("font_size") or 11.5)
    rgb = style.get("rgb") or _color_int_to_rgb(int(style.get("color") or 7305336))
    rect = fitz_mod.Rect(bbox)
    size = _fit_font_size(
        text,
        font_path=font_path,
        max_size=base_size,
        min_size=min(min_size, base_size),
        max_width=rect.width,
    )
    font = fitz_mod.Font(fontfile=str(font_path))
    text_width = font.text_length(text, fontsize=size)
    x = rect.x0 + max((rect.width - text_width) / 2, 0)
    y = rect.y1 - 2
    page.insert_text(
        (x, y),
        text,
        fontname=PDF_FONT_NAME,
        fontfile=str(font_path),
        fontsize=size,
        color=rgb,
    )
    return size


def replace_pdf_skill_lines(
    src_pdf: Path,
    dest_pdf: Path,
    new_skill_lines: list[str],
    *,
    skills_y_min: float = 65.0,
    skills_y_max: float = 95.0,
    cfg: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Replace only the skill headline lines, preserving font, color, and centering."""
    fitz_mod = _require_fitz()
    data = cfg or {}
    font_path = _resolve_font_path(data)
    headline = extract_pdf_headline(
        src_pdf,
        skills_y_min=skills_y_min,
        skills_y_max=skills_y_max,
        cfg=data,
    )
    original_lines = headline.get("skill_lines") or []
    if not original_lines:
        raise RuntimeError("No skill headline lines found in master PDF.")

    dest_pdf.parent.mkdir(parents=True, exist_ok=True)
    src_pdf = src_pdf.resolve()
    dest_pdf = dest_pdf.resolve()
    master_doc = fitz_mod.open(str(src_pdf))
    master_page_count = master_doc.page_count
    master_doc.close()

    if dest_pdf != src_pdf:
        shutil.copy2(src_pdf, dest_pdf)
        doc = fitz_mod.open(str(dest_pdf))
        save_incremental = True
    else:
        doc = fitz_mod.open(str(src_pdf))
        save_incremental = False

    page = doc[0]

    targets: list[tuple[list[float], dict[str, Any], str]] = []
    for idx, row in enumerate(original_lines):
        if idx >= len(new_skill_lines):
            break
        targets.append((list(row.get("bbox") or []), dict(row.get("style") or {}), new_skill_lines[idx]))

    for bbox, _, _ in targets:
        page.add_redact_annot(fitz_mod.Rect(bbox), fill=(1, 1, 1))
    page.apply_redactions()

    min_size = float(data.get("pdf_headline_min_font_size", 8.0))
    for bbox, style, new_text in targets:
        if not style:
            style = _line_style({"spans": [{"size": 11.5, "color": 7305336}]}, font_path=font_path)
        _insert_styled_line(page, bbox, new_text, style, min_size=min_size)

    layout = finalize_pdf_page_layout(doc, master_page_count=master_page_count, cfg=data)

    if save_incremental:
        doc.saveIncr()
        doc.close()
    else:
        temp = dest_pdf.with_suffix(".building.pdf")
        doc.save(str(temp), garbage=3, deflate=True)
        doc.close()
        temp.replace(dest_pdf)

    return layout


def generate_pdf_from_master(
    master_pdf: Path,
    dest_pdf: Path,
    skill_lines: list[str],
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, int]:
    data = cfg or {}
    return replace_pdf_skill_lines(
        master_pdf,
        dest_pdf,
        skill_lines,
        skills_y_min=float(data.get("pdf_skills_y_min", 65.0)),
        skills_y_max=float(data.get("pdf_skills_y_max", 95.0)),
        cfg=data,
    )
