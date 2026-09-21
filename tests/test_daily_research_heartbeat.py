"""Regression: long research steps must heartbeat updated_at."""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

TZ = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def research_env(tmp_path, monkeypatch):
    run = tmp_path / "state" / "research-run.json"
    monkeypatch.setattr("research_log.RUN_PATH", run)
    monkeypatch.setattr("research_log.ROOT", tmp_path)
    monkeypatch.setattr("daily_research.STEP_HEARTBEAT_SEC", 0.05)
    monkeypatch.setattr("daily_research.STEP_TIMEOUT_SEC", {"slow_step": 30})
    return run


def test_run_step_heartbeats_during_long_command(research_env, monkeypatch):
    from daily_research import _run_step
    from research_log import join_research_run, load_research_run, set_research_step

    join_research_run("2026-09-09")
    set_research_step("slow_step", detail="starting")
    initial = load_research_run()["updated_at"]

    cmd = [sys.executable, "-c", "import time; time.sleep(0.2)"]
    steps: list[str] = []
    errors: list[str] = []
    result = _run_step(
        cmd,
        step_key="slow_step",
        steps=steps,
        errors=errors,
        detail="collecting",
    )

    assert result is not None
    assert result.returncode == 0
    assert not errors
    final = load_research_run()
    assert final["updated_at"] != initial
    assert final["step"] == "slow_step"
    assert "collecting" in (final.get("detail") or "") or "running" in (final.get("detail") or "")


def test_run_step_timeout_still_records_failure(research_env, monkeypatch):
    from daily_research import _run_step

    monkeypatch.setattr("daily_research.STEP_TIMEOUT_SEC", {"slow_step": 1})
    monkeypatch.setattr("daily_research.STEP_HEARTBEAT_SEC", 0)

    cmd = [sys.executable, "-c", "import time; time.sleep(2)"]
    steps: list[str] = []
    errors: list[str] = []
    result = _run_step(cmd, step_key="slow_step", steps=steps, errors=errors)

    assert result is None
    assert any("timed out" in err for err in errors)
