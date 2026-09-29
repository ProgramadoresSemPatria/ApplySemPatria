"""Repo-root settings file (YAML or JSON). Local-only — see examples/jobsearch.settings.yaml."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from retrieval._paths import ROOT

SETTINGS_YAML = ROOT / "jobsearch.settings.yaml"
SETTINGS_JSON = ROOT / "jobsearch.settings.json"


def _nested_get(data: dict[str, Any], *keys: str) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # noqa: WPS433
    except ImportError as exc:
        raise RuntimeError(
            "jobsearch.settings.yaml requires PyYAML. Run: pip install pyyaml "
            "(included in pip install -e '.[browser]'), or use jobsearch.settings.json instead."
        ) from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def load_settings() -> dict[str, Any]:
    if SETTINGS_YAML.is_file():
        return _load_yaml(SETTINGS_YAML)
    if SETTINGS_JSON.is_file():
        try:
            data = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def linkedin_collect_visible_from_settings() -> bool | None:
    """True/False from settings file; None if unset."""
    raw = _nested_get(load_settings(), "browser", "linkedin_collect_visible")
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return bool(raw)


def settings_path_in_use() -> Path | None:
    if SETTINGS_YAML.is_file():
        return SETTINGS_YAML
    if SETTINGS_JSON.is_file():
        return SETTINGS_JSON
    return None
