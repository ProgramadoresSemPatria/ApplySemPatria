"""Load/save user configuration for the settings UI."""

from __future__ import annotations

import copy
from typing import Any

from track_store import (  # noqa: E402
    list_track_ids,
    load_board_config,
    load_email_config,
    load_form_answers,
    load_google_config,
    load_linkedin_config,
    load_profile,
    resolve_track,
    save_board_config,
    save_email_config,
    save_form_answers,
    save_google_config,
    save_linkedin_config,
    save_profile,
    track_label,
)

PROFILE_TEXT_FIELDS = (
    "full_name",
    "email",
    "phone",
    "location",
    "current_title",
    "linkedin_url",
    "github_url",
    "resume_path",
    "dm_message_template",
    "form_link_message_template",
    "cover_letter_default",
)

PROFILE_ANSWER_FIELDS = (
    "ai_experience_summary",
    "ml_production_answer",
    "data_pipelines_answer",
    "distributed_systems_answer",
    "python_answer",
    "multi_agent_production_answer",
    "mcp_production_answer",
    "agent_observability_answer",
    "work_authorization",
    "requires_sponsorship",
    "notice_period",
    "english_level",
    "hourly_rate_usd",
    "annual_salary_usd",
)

LINKEDIN_BOOL_FIELDS = (
    "require_usd_salary",
    "dm_apply_enabled",
    "form_link_message_enabled",
    "dm_message_confirmed",
    "form_link_message_confirmed",
    "llm_intent_classify_enabled",
)

LINKEDIN_CHOICE_FIELDS = {
    "dm_apply_mode": ("manual", "automatic"),
    "posts_default_filter_result": ("needs_review", "skipped"),
    "table_sort": ("date_posted", "salary"),
    "search_sort": ("date_posted", "salary"),
}

EMAIL_BOOL_FIELDS = ("email_apply_enabled", "email_message_confirmed", "skip_if_already_applied_in_applika", "log_to_applika")
EMAIL_CHOICE_FIELDS = {"email_apply_mode": ("manual", "automatic")}

BOARD_BOOL_FIELDS = (
    "filters.require_usd_salary",
    "filters.skip_eu_only",
    "filters.skip_us_only",
    "filters.skip_single_country_restrictions",
)

GOOGLE_BOOL_FIELDS = ("require_usd_salary",)


def _pick_fields(data: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {k: data.get(k, "") for k in keys}


def _nested_get(data: dict[str, Any], dotted: str) -> Any:
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _nested_set(data: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = data
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def load_config_bundle(track_id: str | None = None) -> dict[str, Any]:
    tid = resolve_track(track_id)
    profile = load_profile(tid)
    linkedin = load_linkedin_config(tid)
    email = load_email_config(tid)
    board = load_board_config(tid)
    google = load_google_config(tid)
    form = load_form_answers(tid)

    linkedin.setdefault("llm_intent_classify_enabled", False)
    linkedin.setdefault("llm_intent_model", "gpt-4o-mini")

    previews: dict[str, Any] = {}
    try:
        from linkedin_configure import preview_dm_message, preview_form_link_message  # noqa: WPS433

        previews["dm_message"] = preview_dm_message(tid)
        previews["form_link_message"] = preview_form_link_message(tid)
    except Exception:  # noqa: BLE001
        previews["dm_message"] = {"body": profile.get("dm_message_template", "")}
        previews["form_link_message"] = {"body": profile.get("form_link_message_template", "")}

    return {
        "track_id": tid,
        "track_label": track_label(tid),
        "tracks": [{"id": t, "label": track_label(t)} for t in list_track_ids()],
        "profile": {
            "identity": _pick_fields(profile, PROFILE_TEXT_FIELDS[:8]),
            "templates": _pick_fields(profile, PROFILE_TEXT_FIELDS[8:]),
            "answers": _pick_fields(profile, PROFILE_ANSWER_FIELDS),
        },
        "linkedin": {
            "roles": linkedin.get("roles") or [],
            "region_suffixes": linkedin.get("region_suffixes") or [],
            "require_usd_salary": bool(linkedin.get("require_usd_salary")),
            "posts_default_filter_result": linkedin.get("posts_default_filter_result", "needs_review"),
            "default_period_days": linkedin.get("default_period_days", 7),
            "default_max_pages": linkedin.get("default_max_pages", 10),
            "dm_apply_enabled": bool(linkedin.get("dm_apply_enabled")),
            "dm_apply_mode": linkedin.get("dm_apply_mode", "manual"),
            "dm_message_confirmed": bool(linkedin.get("dm_message_confirmed")),
            "form_link_message_enabled": bool(linkedin.get("form_link_message_enabled")),
            "form_link_message_confirmed": bool(linkedin.get("form_link_message_confirmed")),
            "llm_intent_classify_enabled": bool(linkedin.get("llm_intent_classify_enabled")),
            "llm_intent_model": linkedin.get("llm_intent_model", "gpt-4o-mini"),
            "table_sort": linkedin.get("table_sort", "date_posted"),
            "search_sort": linkedin.get("search_sort", "date_posted"),
        },
        "email": {
            "sender_email": email.get("sender_email", ""),
            "sender_name": email.get("sender_name", ""),
            "subject_template": email.get("subject_template", ""),
            "body_template_file": email.get("body_template_file", ""),
            "email_apply_enabled": bool(email.get("email_apply_enabled")),
            "email_apply_mode": email.get("email_apply_mode", "manual"),
            "email_message_confirmed": bool(email.get("email_message_confirmed")),
            "rate_limit_seconds": email.get("rate_limit_seconds", 45),
            "skip_if_already_applied_in_applika": bool(email.get("skip_if_already_applied_in_applika", True)),
            "log_to_applika": bool(email.get("log_to_applika", True)),
        },
        "board": {
            "filters": copy.deepcopy(board.get("filters") or {}),
            "sources": {
                name: {"enabled": bool((cfg or {}).get("enabled"))}
                for name, cfg in (board.get("sources") or {}).items()
            },
            "himalayas_max_age_days": board.get("himalayas_max_age_days", 14),
        },
        "google": {
            "require_usd_salary": bool(google.get("require_usd_salary")),
            "default_period_days": google.get("default_period_days", 14),
            "profile_match_keywords": google.get("profile_match_keywords") or [],
        },
        "form_answers": {
            "rules_count": len(form.get("rules") or []),
            "rules": form.get("rules") or [],
            "model_note": form.get("_doc", ""),
        },
        "previews": previews,
        "flags": {
            "post_intent_filter": True,
            "require_hiring_hint_ingest": True,
            "job_seeker_reject": True,
        },
    }


def save_config_section(track_id: str | None, section: str, payload: dict[str, Any]) -> dict[str, Any]:
    tid = resolve_track(track_id)
    section = (section or "").strip().lower()

    if section == "profile":
        profile = load_profile(tid)
        for group in ("identity", "templates", "answers"):
            for key, val in (payload.get(group) or {}).items():
                if key.startswith("_"):
                    continue
                profile[key] = val
        save_profile(tid, profile)
    elif section == "linkedin":
        cfg = load_linkedin_config(tid)
        for key, val in payload.items():
            if key in ("roles", "region_suffixes") and isinstance(val, list):
                cfg[key] = [str(v).strip() for v in val if str(v).strip()]
            elif key in LINKEDIN_BOOL_FIELDS:
                cfg[key] = bool(val)
            elif key in LINKEDIN_CHOICE_FIELDS:
                choices = LINKEDIN_CHOICE_FIELDS[key]
                cfg[key] = val if val in choices else choices[0]
            elif key in ("default_period_days", "default_max_pages"):
                cfg[key] = int(val)
            elif key == "llm_intent_model":
                cfg[key] = str(val or "gpt-4o-mini").strip()
        save_linkedin_config(tid, cfg)
    elif section == "email":
        cfg = load_email_config(tid)
        for key, val in payload.items():
            if key in EMAIL_BOOL_FIELDS:
                cfg[key] = bool(val)
            elif key in EMAIL_CHOICE_FIELDS:
                choices = EMAIL_CHOICE_FIELDS[key]
                cfg[key] = val if val in choices else choices[0]
            elif key == "rate_limit_seconds":
                cfg[key] = int(val)
            else:
                cfg[key] = val
        save_email_config(tid, cfg)
    elif section == "board":
        cfg = load_board_config(tid)
        filters = payload.get("filters") or {}
        if isinstance(filters, dict):
            cfg.setdefault("filters", {}).update(filters)
        sources = payload.get("sources") or {}
        if isinstance(sources, dict):
            cfg.setdefault("sources", {})
            for name, scfg in sources.items():
                if name in cfg["sources"] and isinstance(scfg, dict):
                    cfg["sources"][name]["enabled"] = bool(scfg.get("enabled"))
        if "himalayas_max_age_days" in payload:
            cfg["himalayas_max_age_days"] = int(payload["himalayas_max_age_days"])
        save_board_config(tid, cfg)
    elif section == "google":
        cfg = load_google_config(tid)
        if "require_usd_salary" in payload:
            cfg["require_usd_salary"] = bool(payload["require_usd_salary"])
        if "default_period_days" in payload:
            cfg["default_period_days"] = int(payload["default_period_days"])
        if "profile_match_keywords" in payload and isinstance(payload["profile_match_keywords"], list):
            cfg["profile_match_keywords"] = [str(v).strip() for v in payload["profile_match_keywords"] if str(v).strip()]
        save_google_config(tid, cfg)
    elif section == "form_answers":
        data = load_form_answers(tid)
        if "rules" in payload and isinstance(payload["rules"], list):
            data["rules"] = payload["rules"]
        save_form_answers(tid, data)
    else:
        raise ValueError(f"Unknown config section: {section}")

    return load_config_bundle(tid)
