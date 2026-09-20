"""CV master schema + DOCX parse/build tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cv_master_docx import (  # noqa: E402
    HEADLINE_PARAGRAPH_INDEX,
    DEFAULT_TEMPLATE,
    build_master_docx,
    parse_master_docx,
)
from cv_master_schema import CvContact, CvExperience, CvProfile, profile_is_complete, validate_cv_profile  # noqa: E402

MASTER_TEMPLATE = DEFAULT_TEMPLATE


@pytest.fixture
def minimal_profile() -> CvProfile:
    return CvProfile(
        full_name="Jane Doe",
        headline_line="Senior AI Engineer | Python | RAG | LangChain",
        contact=CvContact(
            phone="+1 555 0100",
            email="jane@example.com",
            linkedin_url="https://www.linkedin.com/in/jane-doe/",
            location="Remote, Worldwide",
        ),
        summary="Senior engineer with 8+ years building AI products.",
        experience=[
            CvExperience(
                company="Acme AI",
                location="Remote, USA",
                role="Senior AI Engineer",
                date_range="01/2024 Present",
                bullets=["Built RAG pipeline serving 1M queries/day."],
                stack="Python | LangChain | AWS",
            )
        ],
        programming_languages="• Python 8 years",
        spoken_languages="English Fluent",
    )


def test_validate_profile_requires_core_fields(minimal_profile: CvProfile):
    errors = validate_cv_profile(minimal_profile)
    assert errors == []
    assert profile_is_complete(minimal_profile)

    incomplete = minimal_profile.to_dict()
    incomplete["full_name"] = ""
    assert "full_name is required" in validate_cv_profile(incomplete)


@pytest.mark.skipif(not MASTER_TEMPLATE.is_file(), reason="MASTER_CV template not installed")
def test_parse_master_template_has_core_fields():
    profile = parse_master_docx(MASTER_TEMPLATE)
    assert profile.full_name.strip()
    assert profile.headline_line.strip()
    assert "|" in profile.headline_line
    assert profile.summary.strip()
    assert len(profile.experience) >= 3
    assert profile.experience[0].company.strip()
    assert profile.experience[0].role.strip()


@pytest.mark.skipif(not MASTER_TEMPLATE.is_file(), reason="MASTER_CV template not installed")
def test_build_round_trip_preserves_headline_and_summary(minimal_profile: CvProfile, tmp_path: Path):
    out = tmp_path / "built.docx"
    build_master_docx(minimal_profile, out, template=MASTER_TEMPLATE)
    assert out.is_file()
    rebuilt = parse_master_docx(out)
    assert rebuilt.full_name == minimal_profile.full_name
    assert rebuilt.headline_line == minimal_profile.headline_line
    assert minimal_profile.summary.split()[0] in rebuilt.summary
    assert len(rebuilt.experience) == 1
    assert rebuilt.experience[0].company == "Acme AI"
    assert rebuilt.experience[0].role == "Senior AI Engineer"


@pytest.mark.skipif(not MASTER_TEMPLATE.is_file(), reason="MASTER_CV template not installed")
def test_built_docx_headline_paragraph_index_matches_chameleon(minimal_profile: CvProfile, tmp_path: Path):
    from docx import Document

    out = tmp_path / "built.docx"
    build_master_docx(minimal_profile, out, template=MASTER_TEMPLATE)
    doc = Document(str(out))
    assert doc.paragraphs[HEADLINE_PARAGRAPH_INDEX].text == minimal_profile.headline_line
