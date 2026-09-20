"""LinkedIn profile PDF → CvProfile import tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cv_master_linkedin_pdf import parse_linkedin_profile_pdf, parse_linkedin_profile_text  # noqa: E402
from cv_master_schema import profile_is_complete  # noqa: E402

FIXTURE_TEXT = Path(__file__).resolve().parent / "fixtures" / "cv-master" / "linkedin-profile.txt"
USER_PDF = Path("/Users/caio/Downloads/Profile.pdf")


@pytest.fixture
def linkedin_text() -> str:
    assert FIXTURE_TEXT.is_file(), "missing linkedin profile text fixture"
    return FIXTURE_TEXT.read_text(encoding="utf-8")


def test_parse_linkedin_profile_text_fixture(linkedin_text: str):
    profile = parse_linkedin_profile_text(linkedin_text)
    assert profile.full_name == "Caio Lima"
    assert "RAG" in profile.headline_line or "AI" in profile.headline_line
    assert profile.contact.email == "caiohandradelima@gmail.com"
    assert "linkedin.com/in/caiohandradelima" in profile.contact.linkedin_url
    assert profile.summary.strip()
    assert len(profile.experience) >= 5
    assert profile.experience[0].company == "Borderless Coding"
    assert profile.experience[0].role == "Senior AI Data Engineer"
    assert profile.education
    assert "Eniac" in profile.education[0].institution


@pytest.mark.skipif(not USER_PDF.is_file(), reason="local LinkedIn Profile.pdf not present")
def test_parse_real_linkedin_profile_pdf():
    profile = parse_linkedin_profile_pdf(USER_PDF)
    assert profile.full_name
    assert len(profile.experience) >= 8
    assert profile.contact.email


def test_profile_mostly_complete_after_linkedin_import(linkedin_text: str):
    profile = parse_linkedin_profile_text(linkedin_text)
    errors = __import__("cv_master_schema", fromlist=["validate_cv_profile"]).validate_cv_profile(profile)
    assert not errors, errors
