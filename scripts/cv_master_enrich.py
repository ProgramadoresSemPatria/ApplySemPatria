#!/usr/bin/env python3
"""Enrich CvProfile from track applicant-profile and normalize LinkedIn dates."""

from __future__ import annotations

import re

from cv_master_schema import CvProfile
from track_store import load_profile, resolve_track

MONTHS = {
    "january": "01",
    "february": "02",
    "march": "03",
    "april": "04",
    "may": "05",
    "june": "06",
    "july": "07",
    "august": "08",
    "september": "09",
    "october": "10",
    "november": "11",
    "december": "12",
}

LINKEDIN_DATE_RANGE_RE = re.compile(
    r"^(?P<start>[A-Za-z]+ \d{4})\s*-\s*(?P<end>Present|[A-Za-z]+ \d{4})\s*"
    r"(?:\((?P<duration>[^)]+)\))?\s*$",
    re.I,
)


def _month_year_to_mm_yyyy(value: str) -> str:
    parts = (value or "").strip().split()
    if len(parts) != 2:
        return value.strip()
    month_name, year = parts[0].lower(), parts[1]
    mm = MONTHS.get(month_name, "")
    if not mm or not year.isdigit():
        return value.strip()
    return f"{mm}/{year}"


def normalize_linkedin_date_range(date_range: str) -> str:
    """Convert LinkedIn PDF dates to MASTER format (e.g. 12/2025 Present)."""
    raw = (date_range or "").strip()
    if not raw:
        return raw
    match = LINKEDIN_DATE_RANGE_RE.match(raw)
    if not match:
        return raw
    start = _month_year_to_mm_yyyy(match.group("start"))
    end_raw = match.group("end")
    end = "Present" if end_raw.lower() == "present" else _month_year_to_mm_yyyy(end_raw)
    return f"{start} {end}".strip()


def enrich_cv_profile_from_track(profile: CvProfile, track_id: str | None = None) -> CvProfile:
    """Fill gaps from tracks/{id}/applicant-profile.json and normalize dates."""
    tid = resolve_track(track_id)
    data = load_profile(tid)

    if not profile.full_name.strip():
        profile.full_name = str(data.get("full_name") or "").strip()
    if not profile.contact.email.strip():
        profile.contact.email = str(data.get("email") or "").strip()
    if not profile.contact.phone.strip():
        profile.contact.phone = str(data.get("phone") or "").strip()
    if not profile.contact.linkedin_url.strip():
        profile.contact.linkedin_url = str(data.get("linkedin_url") or "").strip()
    if not profile.contact.location.strip():
        profile.contact.location = str(data.get("location") or "").strip()
    if not profile.contact.portfolio_url.strip():
        profile.contact.portfolio_url = str(data.get("portfolio_url") or data.get("website") or "").strip()

    for exp in profile.experience:
        exp.date_range = normalize_linkedin_date_range(exp.date_range)
    for edu in profile.education:
        edu.date_range = normalize_linkedin_date_range(edu.date_range)

    return profile
