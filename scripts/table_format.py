"""Markdown table cell formatting and display normalization."""

from __future__ import annotations

import re


def md_cell(value: object) -> str:
    """Escape a value for markdown pipe tables (prevents column shift)."""
    text = str(value if value not in (None, "") else "—").strip()
    text = text.replace("|", "·")
    text = re.sub(r"\s+", " ", text)
    return text or "—"


def normalize_company_display(name: str) -> str:
    """Clean recruiter/company label for tables."""
    text = (name or "").strip()
    text = re.sub(r"^~+\s*", "", text)
    text = re.sub(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or "Unknown"
