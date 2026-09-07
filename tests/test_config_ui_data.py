"""Unit tests for config_ui_data load/save helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


@pytest.fixture
def isolated_track_tree(tmp_path, monkeypatch):
    """Minimal track layout under a temp ROOT."""
    track_dir = tmp_path / "tracks" / "ai-engineer"
    track_dir.mkdir(parents=True)

    manifest = {
        "default_track": "ai-engineer",
        "tracks": {
            "ai-engineer": {
                "label": "AI Engineer",
                "profile_path": "tracks/ai-engineer/applicant-profile.json",
                "board_config_path": "tracks/ai-engineer/config.json",
                "linkedin_config_path": "tracks/ai-engineer/linkedin-posts-config.json",
                "google_config_path": "tracks/ai-engineer/google-jobs-config.json",
                "email_config_path": "tracks/ai-engineer/email-apply-config.json",
                "form_answers_path": "tracks/ai-engineer/form-answers.json",
            }
        },
    }
    (tmp_path / "tracks.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    (track_dir / "applicant-profile.json").write_text(
        json.dumps(
            {
                "full_name": "Test User",
                "email": "test@example.com",
                "dm_message_template": "Hi {role}",
                "ai_experience_summary": "Yes",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (track_dir / "linkedin-posts-config.json").write_text(
        json.dumps(
            {
                "roles": ["ai engineer"],
                "region_suffixes": ["latam"],
                "llm_intent_classify_enabled": False,
                "dm_apply_enabled": True,
                "dm_apply_mode": "manual",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (track_dir / "email-apply-config.json").write_text(
        json.dumps({"email_apply_enabled": True, "email_apply_mode": "manual"}, indent=2) + "\n",
        encoding="utf-8",
    )
    (track_dir / "config.json").write_text(
        json.dumps(
            {
                "filters": {"require_usd_salary": True, "skip_eu_only": True},
                "sources": {"remoteok": {"enabled": True}, "himalayas": {"enabled": False}},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (track_dir / "google-jobs-config.json").write_text(
        json.dumps({"require_usd_salary": False, "profile_match_keywords": ["rag"]}, indent=2) + "\n",
        encoding="utf-8",
    )
    (track_dir / "form-answers.json").write_text(
        json.dumps({"rules": [{"q": "email", "profile_key": "email"}]}, indent=2) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("track_store.ROOT", tmp_path)
    return tmp_path


def test_load_config_bundle_structure(isolated_track_tree):
    from config_ui_data import load_config_bundle

    bundle = load_config_bundle("ai-engineer")
    assert bundle["track_id"] == "ai-engineer"
    assert bundle["profile"]["identity"]["full_name"] == "Test User"
    assert bundle["linkedin"]["roles"] == ["ai engineer"]
    assert bundle["email"]["email_apply_enabled"] is True
    assert bundle["form_answers"]["rules_count"] == 1
    assert bundle["flags"]["job_seeker_reject"] is True
    assert "previews" in bundle


def test_save_profile_identity(isolated_track_tree):
    from config_ui_data import load_config_bundle, save_config_section

    save_config_section(
        "ai-engineer",
        "profile",
        {"identity": {"full_name": "Updated Name", "email": "new@example.com"}},
    )
    bundle = load_config_bundle("ai-engineer")
    assert bundle["profile"]["identity"]["full_name"] == "Updated Name"
    assert bundle["profile"]["identity"]["email"] == "new@example.com"


def test_save_linkedin_toggle_persists(isolated_track_tree):
    from config_ui_data import load_config_bundle, save_config_section

    save_config_section(
        "ai-engineer",
        "linkedin",
        {"llm_intent_classify_enabled": True, "llm_intent_model": "gpt-4o-mini"},
    )
    bundle = load_config_bundle("ai-engineer")
    assert bundle["linkedin"]["llm_intent_classify_enabled"] is True
    assert bundle["linkedin"]["llm_intent_model"] == "gpt-4o-mini"


def test_save_email_mode(isolated_track_tree):
    from config_ui_data import load_config_bundle, save_config_section

    save_config_section("ai-engineer", "email", {"email_apply_mode": "automatic"})
    assert load_config_bundle("ai-engineer")["email"]["email_apply_mode"] == "automatic"


def test_save_board_source_toggle(isolated_track_tree):
    from config_ui_data import load_config_bundle, save_config_section

    save_config_section(
        "ai-engineer",
        "board",
        {"sources": {"himalayas": {"enabled": True}}, "filters": {"skip_eu_only": False}},
    )
    bundle = load_config_bundle("ai-engineer")
    assert bundle["board"]["sources"]["himalayas"]["enabled"] is True
    assert bundle["board"]["filters"]["skip_eu_only"] is False


def test_save_form_rules(isolated_track_tree):
    from config_ui_data import load_config_bundle, save_config_section

    rules = [{"q": "phone", "profile_key": "phone"}, {"q": "email", "profile_key": "email"}]
    save_config_section("ai-engineer", "form_answers", {"rules": rules})
    assert load_config_bundle("ai-engineer")["form_answers"]["rules_count"] == 2


def test_save_unknown_section_raises(isolated_track_tree):
    from config_ui_data import save_config_section

    with pytest.raises(ValueError, match="Unknown config section"):
        save_config_section("ai-engineer", "not_a_section", {})


def test_save_google_config(isolated_track_tree):
    from config_ui_data import load_config_bundle, save_config_section

    save_config_section(
        "ai-engineer",
        "google",
        {"require_usd_salary": True, "default_period_days": 21, "profile_match_keywords": ["rag", "llm"]},
    )
    bundle = load_config_bundle("ai-engineer")
    assert bundle["google"]["require_usd_salary"] is True
    assert bundle["google"]["default_period_days"] == 21
    assert "llm" in bundle["google"]["profile_match_keywords"]


def test_save_linkedin_invalid_choice_falls_back(isolated_track_tree):
    from config_ui_data import load_config_bundle, save_config_section

    save_config_section("ai-engineer", "linkedin", {"dm_apply_mode": "not-valid"})
    assert load_config_bundle("ai-engineer")["linkedin"]["dm_apply_mode"] == "manual"


def test_load_config_bundle_preview_fallback(isolated_track_tree, monkeypatch):
    from config_ui_data import load_config_bundle

    def boom(_tid):
        raise RuntimeError("preview unavailable")

    monkeypatch.setattr("linkedin_configure.preview_dm_message", boom)
    monkeypatch.setattr("linkedin_configure.preview_form_link_message", boom)
    bundle = load_config_bundle("ai-engineer")
    assert bundle["previews"]["dm_message"]["body"] == "Hi {role}"
