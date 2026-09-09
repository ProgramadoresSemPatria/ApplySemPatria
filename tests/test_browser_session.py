"""Tests for browser_session Chrome resolution."""

from __future__ import annotations

from pathlib import Path

from browser_session import browser_launch_kwargs, resolve_chrome_executable


def test_prefers_real_chrome_over_test_bundle(monkeypatch, tmp_path: Path):
    fake_chrome = tmp_path / "Google Chrome"
    fake_chrome.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "browser_session.REAL_CHROME_CANDIDATES",
        (fake_chrome,),
    )
    monkeypatch.delenv("JOBSEARCH_CHROME_EXECUTABLE", raising=False)
    monkeypatch.delenv("JOBSEARCH_USE_TEST_CHROME", raising=False)
    assert resolve_chrome_executable() == str(fake_chrome)


def test_test_chrome_only_when_explicit(monkeypatch, tmp_path: Path):
    fake_test = tmp_path / "Chrome for Testing"
    fake_test.write_text("", encoding="utf-8")
    monkeypatch.setenv("JOBSEARCH_USE_TEST_CHROME", "1")
    monkeypatch.setattr("browser_session.TEST_CHROME_EXECUTABLE", fake_test)
    monkeypatch.setattr("browser_session.REAL_CHROME_CANDIDATES", ())
    assert resolve_chrome_executable() == str(fake_test)


def test_launch_kwargs_use_executable_when_found(monkeypatch, tmp_path: Path):
    fake = tmp_path / "chrome"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setenv("JOBSEARCH_CHROME_EXECUTABLE", str(fake))
    kwargs = browser_launch_kwargs(headless=False)
    assert kwargs["executable_path"] == str(fake)
    assert "channel" not in kwargs


def test_launch_kwargs_channel_when_no_executable(monkeypatch):
    monkeypatch.delenv("JOBSEARCH_CHROME_EXECUTABLE", raising=False)
    monkeypatch.setattr("browser_session.REAL_CHROME_CANDIDATES", ())
    kwargs = browser_launch_kwargs(headless=True)
    assert kwargs.get("channel") == "chrome"
