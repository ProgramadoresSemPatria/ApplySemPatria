#!/usr/bin/env python3
"""Import LinkedIn 'Save to PDF' profile export into CvProfile."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from cv_master_schema import CvContact, CvEducation, CvExperience, CvProfile

DATE_RANGE_RE = re.compile(
    r"^(?P<start>[A-Za-z]+ \d{4})\s*-\s*(?P<end>Present|[A-Za-z]+ \d{4})\s*"
    r"(?:\((?P<duration>[^)]+)\))?\s*$"
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
LINKEDIN_SLUG_RE = re.compile(r"linkedin\.com/in/([\w-]+)", re.I)

SECTION_MARKERS = ("Experience", "Education", "Licenses & Certifications", "Volunteering")


def _clean_line(line: str) -> str:
    return (line or "").replace("\u00a0", " ").strip()


def _nonempty_lines(text: str) -> list[str]:
    return [_clean_line(ln) for ln in text.splitlines() if _clean_line(ln)]


def _split_sections(lines: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Return (header, experience, education) line groups."""
    exp_idx = next((i for i, ln in enumerate(lines) if ln == "Experience"), None)
    edu_idx = next((i for i, ln in enumerate(lines) if ln == "Education"), None)
    if exp_idx is None:
        return lines, [], []
    header = lines[:exp_idx]
    exp_end = edu_idx if edu_idx is not None and edu_idx > exp_idx else len(lines)
    experience = lines[exp_idx + 1 : exp_end]
    education = lines[edu_idx + 1 :] if edu_idx is not None else []
    return header, experience, education


def _looks_like_job_start(lines: list[str], idx: int) -> bool:
    if idx + 2 >= len(lines):
        return False
    return bool(DATE_RANGE_RE.match(lines[idx + 2]))


def _parse_header(lines: list[str]) -> CvProfile:
    contact = CvContact()
    top_skills: list[str] = []
    spoken_languages = ""
    summary_parts: list[str] = []

    summary_idx = next((i for i, ln in enumerate(lines) if ln == "Summary"), len(lines))
    pre_summary = lines[:summary_idx]
    summary_tail = lines[summary_idx + 1 :]
    for ln in summary_tail:
        if ln in SECTION_MARKERS or ln.startswith("Page "):
            break
        summary_parts.append(ln)

    linkedin_parts: list[str] = []
    mode = ""
    identity_block: list[str] = []
    for ln in pre_summary:
        if ln == "Contact":
            mode = "contact"
            continue
        if ln == "Top Skills":
            mode = "skills"
            continue
        if ln == "Languages":
            mode = "languages"
            continue
        if ln.startswith("Page "):
            continue

        if mode == "contact":
            if EMAIL_RE.search(ln):
                contact.email = EMAIL_RE.search(ln).group(0)  # type: ignore[union-attr]
            elif PHONE_RE.search(ln):
                contact.phone = PHONE_RE.search(ln).group(0).strip()  # type: ignore[union-attr]
            elif "linkedin" in ln.lower():
                linkedin_parts.append(ln.replace(" (LinkedIn)", "").strip())
            continue
        if mode == "skills":
            top_skills.append(ln)
            continue
        if mode == "languages":
            if "(" in ln and ")" in ln:
                spoken_languages = f"{spoken_languages} {ln}".strip() if spoken_languages else ln
                continue
            mode = "identity"
        identity_block.append(ln)

    if linkedin_parts:
        joined = "".join(linkedin_parts).replace(" ", "")
        slug = LINKEDIN_SLUG_RE.search(joined)
        if slug:
            contact.linkedin_url = f"https://www.linkedin.com/in/{slug.group(1)}/"
        elif "linkedin.com/in/" in joined.lower():
            contact.linkedin_url = "https://" + joined.lstrip("/")

    full_name = identity_block[0] if identity_block else ""
    location = ""
    headline_parts: list[str] = []
    for ln in identity_block[1:]:
        if ln in ("Brazil", "Worldwide", "United States") or ("," in ln and "|" not in ln):
            location = ln
            continue
        headline_parts.append(ln)
    headline_line = " ".join(headline_parts).replace("  ", " ").strip()
    if not location and len(identity_block) >= 2:
        tail = identity_block[-1]
        if tail not in headline_line and "|" not in tail and tail != full_name:
            location = tail

    programming = " • ".join(top_skills) if top_skills else ""
    if programming and not programming.startswith("•"):
        programming = "• " + "  • ".join(top_skills)

    return CvProfile(
        full_name=full_name,
        headline_line=headline_line,
        contact=CvContact(
            phone=contact.phone,
            email=contact.email,
            linkedin_url=contact.linkedin_url,
            location=location,
        ),
        summary=" ".join(summary_parts).strip(),
        programming_languages=programming,
        spoken_languages=spoken_languages,
    )


def _parse_experience_lines(lines: list[str]) -> list[CvExperience]:
    jobs: list[CvExperience] = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("Page ") or lines[i] in SECTION_MARKERS:
            i += 1
            continue
        if not _looks_like_job_start(lines, i):
            i += 1
            continue
        company = lines[i]
        role = lines[i + 1]
        date_range = lines[i + 2]
        i += 3
        location = ""
        if i < len(lines) and not lines[i].startswith(("Achievements", "Context", "technologies", "Activities", "Page ")):
            if not DATE_RANGE_RE.match(lines[i]) and not _looks_like_job_start(lines, i):
                location = lines[i]
                i += 1

        achievements: list[str] = []
        context = ""
        stack = ""
        activities: list[str] = []
        prose: list[str] = []
        mode = "prose"
        while i < len(lines):
            if lines[i].startswith("Page "):
                i += 1
                continue
            if _looks_like_job_start(lines, i):
                break
            cur = lines[i]
            if cur in ("Achievements:", "Context:", "technologies:", "Activities:"):
                mode = cur.rstrip(":").lower()
                i += 1
                continue
            if mode == "achievements":
                achievements.append(cur.lstrip("- ").strip())
            elif mode == "context":
                context = f"{context} {cur}".strip() if context else cur
            elif mode == "technologies":
                stack = f"{stack} {cur}".strip() if stack else cur
            elif mode == "activities":
                activities.append(cur.lstrip("- ").strip())
            else:
                prose.append(cur)
            i += 1

        bullets = achievements + activities + prose
        jobs.append(
            CvExperience(
                company=company,
                location=location,
                role=role,
                date_range=date_range,
                context=context,
                bullets=bullets,
                stack=stack.replace("technologies:", "").strip(),
            )
        )
    return jobs


def _parse_education_lines(lines: list[str]) -> list[CvEducation]:
    rows: list[CvEducation] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("Page ") or not ln:
            i += 1
            continue
        institution = ln
        degree = ""
        date_range = ""
        i += 1
        if i < len(lines):
            nxt = lines[i]
            if "·" in nxt or "\u00b7" in nxt:
                parts = re.split(r"\s*[·\u00b7]\s*", nxt)
                if parts:
                    degree = parts[0].strip().rstrip(",")
                if len(parts) > 1:
                    date_range = parts[-1].strip("() ")
                i += 1
        rows.append(CvEducation(institution=institution, degree=degree, date_range=date_range))
    return rows


def parse_linkedin_profile_text(text: str) -> CvProfile:
    """Parse plain text extracted from LinkedIn profile PDF."""
    lines = _nonempty_lines(text)
    header, exp_lines, edu_lines = _split_sections(lines)
    profile = _parse_header(header)
    profile.experience = _parse_experience_lines(exp_lines)
    profile.education = _parse_education_lines(edu_lines)
    return profile


def extract_pdf_text(pdf_path: Path | str) -> str:
    try:
        import pymupdf as fitz  # noqa: WPS433
    except ImportError:  # pragma: no cover
        import fitz  # type: ignore[no-redef]  # noqa: WPS433

    doc = fitz.open(str(pdf_path))
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def parse_linkedin_profile_pdf(pdf_path: Path | str) -> CvProfile:
    return parse_linkedin_profile_text(extract_pdf_text(pdf_path))


def import_linkedin_pdf_to_profile(
    pdf_path: Path | str,
    *,
    linkedin_url: str = "",
    overrides: dict[str, Any] | None = None,
) -> CvProfile:
    profile = parse_linkedin_profile_pdf(pdf_path)
    if linkedin_url.strip():
        profile.contact.linkedin_url = linkedin_url.strip()
    if overrides:
        merged = profile.to_dict()
        for key, val in overrides.items():
            if key == "contact" and isinstance(val, dict):
                merged["contact"] = {**(merged.get("contact") or {}), **val}
            else:
                merged[key] = val
        profile = CvProfile.from_dict(merged)
    return profile
