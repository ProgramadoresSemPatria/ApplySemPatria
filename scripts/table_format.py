"""Markdown table cell formatting and display normalization."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from registry import parse_posted_at


def md_cell(value: object) -> str:
    """Escape a value for markdown pipe tables (prevents column shift)."""
    text = str(value if value not in (None, "") else "—").strip()
    text = text.replace("|", "·")
    text = re.sub(r"\s+", " ", text)
    return text or "—"


def format_posted(job: dict[str, Any]) -> str:
    """Human-readable posted time (LinkedIn-style relative or YYYY-MM-DD)."""
    label = job.get("posted_label")
    if label:
        return str(label).strip()

    dt = parse_posted_at(job.get("posted_at"))
    if dt is None:
        raw = job.get("posted_at")
        if raw not in (None, ""):
            text = str(raw).strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text[:10]):
                return text[:10]
        return "—"

    now = datetime.now(timezone.utc)
    secs = int((now - dt).total_seconds())
    if secs < 0:
        return dt.strftime("%Y-%m-%d")
    if secs < 3600:
        return f"{max(1, secs // 60)}m"
    if secs < 86400:
        return f"{max(1, secs // 3600)}h"
    if secs < 7 * 86400:
        return f"{max(1, secs // 86400)}d"
    return dt.strftime("%Y-%m-%d")


def normalize_company_display(name: str) -> str:
    """Clean recruiter/company label for tables."""
    text = (name or "").strip()
    text = re.sub(r"^~+\s*", "", text)
    text = re.sub(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or "Unknown"
