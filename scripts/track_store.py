"""Multi-track job search profiles (AI Engineer, Android Developer, …)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "tracks.json"
EXAMPLES_TRACKS = ROOT / "examples" / "tracks"
LEGACY_PROFILE = ROOT / "applicant-profile.json"
LEGACY_BOARD = ROOT / "config.json"
LEGACY_LINKEDIN = ROOT / "linkedin-posts-config.json"
LEGACY_GOOGLE = ROOT / "google-jobs-config.json"
LEGACY_EMAIL = ROOT / "email-apply-config.json"
LEGACY_FORM = ROOT / "form-answers.json"


def _load_json(path: Path, default: dict | list | None = None) -> dict | list:
    if not path.exists():
        return default if default is not None else {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest() -> dict[str, Any]:
    data = _load_json(MANIFEST_PATH, {})
    if not data.get("tracks"):
        return {
            "default_track": "ai-engineer",
            "tracks": {
                "ai-engineer": {
                    "label": "AI Engineer",
                    "profile_path": "applicant-profile.json",
                    "board_config_path": "config.json",
                    "linkedin_config_path": "linkedin-posts-config.json",
                    "google_config_path": "google-jobs-config.json",
                    "email_config_path": "email-apply-config.json",
                    "form_answers_path": "form-answers.json",
                }
            },
        }
    return data


def list_track_ids() -> list[str]:
    return list(load_manifest().get("tracks", {}).keys())


def default_track_id() -> str:
    manifest = load_manifest()
    return manifest.get("default_track") or next(iter(manifest.get("tracks", {})), "ai-engineer")


def resolve_track(track_id: str | None = None) -> str:
    tid = (track_id or default_track_id()).strip()
    tracks = load_manifest().get("tracks", {})
    if tid not in tracks:
        known = ", ".join(tracks) or "(none)"
        raise ValueError(f"Unknown track {tid!r}. Known: {known}")
    return tid


def track_meta(track_id: str | None = None) -> dict[str, Any]:
    tid = resolve_track(track_id)
    return load_manifest()["tracks"][tid]


def track_path(track_id: str | None, key: str) -> Path:
    rel = track_meta(track_id).get(key, "")
    if not rel:
        raise KeyError(f"Track {track_id!r} has no {key}")
    return ROOT / rel


def example_track_path(track_id: str | None, key: str) -> Path | None:
    """Committed example config for CI / fresh clones (tracks/ is gitignored locally)."""
    rel = track_meta(track_id).get(key, "")
    if not rel.startswith("tracks/"):
        return None
    candidate = EXAMPLES_TRACKS / rel.removeprefix("tracks/")
    return candidate if candidate.is_file() else None


def _load_track_json(track_id: str | None, key: str, *, legacy: Path | None = None) -> dict | list:
    path = track_path(track_id, key)
    if path.exists():
        return _load_json(path, {})
    if legacy and legacy.exists():
        return _load_json(legacy, {})
    example = example_track_path(track_id, key)
    if example:
        return _load_json(example, {})
    return _load_json(path, {})


def track_label(track_id: str | None = None) -> str:
    return track_meta(track_id).get("label") or resolve_track(track_id)


def load_profile(track_id: str | None = None) -> dict[str, Any]:
    return _load_track_json(track_id, "profile_path", legacy=LEGACY_PROFILE)


def load_board_config(track_id: str | None = None) -> dict[str, Any]:
    return _load_track_json(track_id, "board_config_path", legacy=LEGACY_BOARD)


def load_linkedin_config(track_id: str | None = None) -> dict[str, Any]:
    return _load_track_json(track_id, "linkedin_config_path", legacy=LEGACY_LINKEDIN)


def load_google_config(track_id: str | None = None) -> dict[str, Any]:
    return _load_track_json(track_id, "google_config_path", legacy=LEGACY_GOOGLE)


def load_email_config(track_id: str | None = None) -> dict[str, Any]:
    return _load_track_json(track_id, "email_config_path", legacy=LEGACY_EMAIL)


def load_form_answers(track_id: str | None = None) -> dict[str, Any]:
    return _load_track_json(track_id, "form_answers_path", legacy=LEGACY_FORM)


def save_profile(track_id: str | None, data: dict[str, Any]) -> None:
    path = track_path(track_id, "profile_path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def save_board_config(track_id: str | None, data: dict[str, Any]) -> None:
    path = track_path(track_id, "board_config_path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def save_linkedin_config(track_id: str | None, data: dict[str, Any]) -> None:
    path = track_path(track_id, "linkedin_config_path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def save_google_config(track_id: str | None, data: dict[str, Any]) -> None:
    path = track_path(track_id, "google_config_path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def save_email_config(track_id: str | None, data: dict[str, Any]) -> None:
    path = track_path(track_id, "email_config_path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def save_form_answers(track_id: str | None, data: dict[str, Any]) -> None:
    path = track_path(track_id, "form_answers_path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def infer_track(job: dict[str, Any]) -> str:
    explicit = (job.get("track") or "").strip()
    if explicit:
        return explicit
    search_role = (job.get("search_role") or "").strip().lower()
    manifest = load_manifest()
    for tid, meta in manifest.get("tracks", {}).items():
        cfg = _load_json(ROOT / meta.get("board_config_path", ""), {})
        keywords = [k.lower() for k in cfg.get("search", {}).get("title_keywords", [])]
        li_cfg = _load_json(ROOT / meta.get("linkedin_config_path", ""), {})
        roles = [r.lower() for r in li_cfg.get("roles", [])]
        role_text = (job.get("role") or "").lower()
        if search_role and (search_role in keywords or search_role in roles):
            return tid
        if any(k in role_text for k in keywords if len(k) > 4):
            return tid
    return default_track_id()


def job_track_label(job: dict[str, Any]) -> str:
    tid = infer_track(job)
    try:
        return track_label(tid)
    except ValueError:
        return tid


def filter_jobs_by_track(jobs: list[dict[str, Any]], track_id: str | None) -> list[dict[str, Any]]:
    if not track_id or track_id == "all":
        return jobs
    tid = resolve_track(track_id)
    return [j for j in jobs if infer_track(j) == tid]


def stamp_track(job: dict[str, Any], track_id: str) -> dict[str, Any]:
    job = dict(job)
    job["track"] = resolve_track(track_id)
    return job
