"""Shared paths for the retrieval layer."""

from __future__ import annotations

from pathlib import Path

RETRIEVAL = Path(__file__).resolve().parent
SCRIPTS = RETRIEVAL.parent
ROOT = SCRIPTS.parent
