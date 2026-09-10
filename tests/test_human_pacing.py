"""Tests for human_pacing jitter helpers."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from human_pacing import (
    MAX_HUMAN_PAUSE,
    MIN_HUMAN_PAUSE,
    cap_pause,
    human_pacing_enabled,
    jitter_seconds,
    pause_human,
)


def test_jitter_capped_at_max():
    samples = [jitter_seconds(10.0, spread=0.35) for _ in range(200)]
    assert all(s <= MAX_HUMAN_PAUSE for s in samples)


def test_cap_pause_clamps():
    assert cap_pause(0.1) == MIN_HUMAN_PAUSE
    assert cap_pause(10.0) == MAX_HUMAN_PAUSE
    assert cap_pause(2.0) == 2.0


def test_pause_human_respects_bounds(monkeypatch):
    monkeypatch.setenv("JOBSEARCH_HUMAN_PACING", "1")
    slept: list[float] = []

    async def fake_sleep(sec: float) -> None:
        slept.append(sec)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    asyncio.run(pause_human(base=10.0))
    assert MIN_HUMAN_PAUSE <= slept[0] <= MAX_HUMAN_PAUSE


def test_pause_human_disabled_is_fast(monkeypatch):
    monkeypatch.setenv("JOBSEARCH_HUMAN_PACING", "0")
    assert human_pacing_enabled() is False
