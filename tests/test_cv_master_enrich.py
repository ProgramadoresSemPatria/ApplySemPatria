"""CV profile enrichment and date normalization tests."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cv_master_enrich import enrich_cv_profile_from_track, normalize_linkedin_date_range  # noqa: E402
from cv_master_schema import CvContact, CvExperience, CvProfile  # noqa: E402


def test_normalize_linkedin_date_range_present():
    assert normalize_linkedin_date_range("December 2025 - Present (10 months)") == "12/2025 Present"
    assert normalize_linkedin_date_range("January 2024 - March 2025") == "01/2024 03/2025"


def test_normalize_linkedin_date_range_passthrough():
    assert normalize_linkedin_date_range("01/2024 Present") == "01/2024 Present"
    assert normalize_linkedin_date_range("") == ""


def test_enrich_fills_contact_from_track(monkeypatch):
    profile = CvProfile(
        full_name="",
        contact=CvContact(email="", phone="", linkedin_url=""),
        experience=[
            CvExperience(
                company="Acme",
                role="Engineer",
                date_range="December 2025 - Present",
                bullets=["Built things."],
            )
        ],
        summary="Summary text.",
        headline_line="Engineer | Python",
    )

    monkeypatch.setattr(
        "cv_master_enrich.load_profile",
        lambda track_id=None: {
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "+1 555 0100",
            "linkedin_url": "https://www.linkedin.com/in/jane-doe/",
            "location": "Remote",
        },
    )
    monkeypatch.setattr("cv_master_enrich.resolve_track", lambda track_id=None: "ai-engineer")

    enriched = enrich_cv_profile_from_track(profile, "ai-engineer")
    assert enriched.full_name == "Jane Doe"
    assert enriched.contact.email == "jane@example.com"
    assert enriched.contact.phone == "+1 555 0100"
    assert enriched.experience[0].date_range == "12/2025 Present"
