"""Structured CV master profile — validated before DOCX build."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CvContact:
    phone: str = ""
    email: str = ""
    linkedin_url: str = ""
    portfolio_url: str = ""
    location: str = ""


@dataclass
class CvAchievement:
    title: str
    body: str = ""


@dataclass
class CvExperience:
    company: str
    location: str = ""
    role: str = ""
    date_range: str = ""
    context: str = ""
    bullets: list[str] = field(default_factory=list)
    stack: str = ""


@dataclass
class CvProject:
    title: str
    description: str = ""


@dataclass
class CvEducation:
    institution: str = ""
    degree: str = ""
    date_range: str = ""


@dataclass
class CvProfile:
    full_name: str = ""
    headline_line: str = ""
    contact: CvContact = field(default_factory=CvContact)
    summary: str = ""
    achievements: list[CvAchievement] = field(default_factory=list)
    experience: list[CvExperience] = field(default_factory=list)
    programming_languages: str = ""
    projects: list[CvProject] = field(default_factory=list)
    education: list[CvEducation] = field(default_factory=list)
    spoken_languages: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CvProfile:
        contact_raw = data.get("contact") or {}
        contact = CvContact(
            phone=str(contact_raw.get("phone") or ""),
            email=str(contact_raw.get("email") or ""),
            linkedin_url=str(contact_raw.get("linkedin_url") or ""),
            portfolio_url=str(contact_raw.get("portfolio_url") or ""),
            location=str(contact_raw.get("location") or ""),
        )
        achievements = [
            CvAchievement(title=str(a.get("title") or ""), body=str(a.get("body") or ""))
            for a in (data.get("achievements") or [])
        ]
        experience = []
        for row in data.get("experience") or []:
            experience.append(
                CvExperience(
                    company=str(row.get("company") or ""),
                    location=str(row.get("location") or ""),
                    role=str(row.get("role") or ""),
                    date_range=str(row.get("date_range") or ""),
                    context=str(row.get("context") or ""),
                    bullets=[str(b) for b in (row.get("bullets") or []) if str(b).strip()],
                    stack=str(row.get("stack") or ""),
                )
            )
        projects = [
            CvProject(title=str(p.get("title") or ""), description=str(p.get("description") or ""))
            for p in (data.get("projects") or [])
        ]
        education = [
            CvEducation(
                institution=str(e.get("institution") or ""),
                degree=str(e.get("degree") or ""),
                date_range=str(e.get("date_range") or ""),
            )
            for e in (data.get("education") or [])
        ]
        return cls(
            full_name=str(data.get("full_name") or ""),
            headline_line=str(data.get("headline_line") or ""),
            contact=contact,
            summary=str(data.get("summary") or ""),
            achievements=achievements,
            experience=experience,
            programming_languages=str(data.get("programming_languages") or ""),
            projects=projects,
            education=education,
            spoken_languages=str(data.get("spoken_languages") or ""),
        )


def validate_cv_profile(profile: CvProfile | dict[str, Any]) -> list[str]:
    """Return human-readable missing/invalid field messages (empty = ok)."""
    p = profile if isinstance(profile, CvProfile) else CvProfile.from_dict(profile)
    errors: list[str] = []

    if not p.full_name.strip():
        errors.append("full_name is required")
    if not p.headline_line.strip():
        errors.append("headline_line is required (titles + skills, pipe-separated)")
    if not p.contact.email.strip():
        errors.append("contact.email is required")
    if not p.contact.linkedin_url.strip():
        errors.append("contact.linkedin_url is required")
    if not p.summary.strip():
        errors.append("summary is required")
    if not p.experience:
        errors.append("at least one experience entry is required")
    else:
        for i, exp in enumerate(p.experience):
            prefix = f"experience[{i}]"
            if not exp.company.strip():
                errors.append(f"{prefix}.company is required")
            if not exp.role.strip():
                errors.append(f"{prefix}.role is required")
            if not exp.date_range.strip():
                errors.append(f"{prefix}.date_range is required")
            if not exp.bullets and not exp.stack.strip():
                errors.append(f"{prefix} needs at least one bullet or a stack line")

    return errors


def profile_is_complete(profile: CvProfile | dict[str, Any]) -> bool:
    return not validate_cv_profile(profile)
