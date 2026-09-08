"""Paths to committed example configs (used when local track data is absent)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLE_TRACK = ROOT / "examples" / "tracks" / "ai-engineer"


def example_linkedin_config_path() -> Path:
    return EXAMPLE_TRACK / "linkedin-posts-config.json"


def example_linkedin_jobs_config_path() -> Path:
    return EXAMPLE_TRACK / "linkedin-jobs-config.json"


def example_board_config_path() -> Path:
    return EXAMPLE_TRACK / "config.json"


def load_example_linkedin_config() -> dict[str, Any]:
    return json.loads(example_linkedin_config_path().read_text(encoding="utf-8"))


def load_example_linkedin_jobs_config() -> dict[str, Any]:
    return json.loads(example_linkedin_jobs_config_path().read_text(encoding="utf-8"))


def load_example_board_config() -> dict[str, Any]:
    return json.loads(example_board_config_path().read_text(encoding="utf-8"))
