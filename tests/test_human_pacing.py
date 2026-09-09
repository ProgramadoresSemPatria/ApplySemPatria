"""Tests for human_pacing jitter helpers."""

from __future__ import annotations

import os

import pytest

from human_pacing import (
    MIN_HUMAN_PAUSE,
    human_pacing_enabled,
    jitter_seconds,
    pause_human,
)


def test_jitter_stays_within_spread():
    base = 10.0
    samples = [jitter_seconds(base, spread=0.35) for _ in range(200)]
    assert all(6.5 <= s <= 13.5 for s in samples)


def test_jitter_respects_minimum():
    assert jitter_seconds(0.2, spread=0.5, minimum=1.0) >= 1.0


def test_pause_human_respects_minimum(monkeypatch):
    monkeypatch.setenv("JOBSEARCH_HUMAN_PACING", "1")
    import asyncio
    from unittest.mock import AsyncMock

    slept: list[float] = []

    async def fake_sleep(sec: float) -> None:
        slept.append(sec)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    asyncio.run(pause_human(base=2.0))
    assert slept[0] >= MIN_HUMAN_PAUSE


def test_pause_human_disabled_is_fast(monkeypatch):
    monkeypatch.setenv("JOBSEARCH_HUMAN_PACING", "0")
    assert human_pacing_enabled() is False
