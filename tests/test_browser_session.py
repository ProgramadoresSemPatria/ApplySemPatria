"""Tests for browser_session Chrome resolution."""

from __future__ import annotations

from pathlib import Path

from browser_session import (
    browser_launch_kwargs,
    headless_chromium_executable,
    headless_chromium_missing_message,
    headless_chromium_ready,
    resolve_chrome_executable,
)


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


def test_launch_kwargs_headless_uses_patchright_chromium(monkeypatch):
    monkeypatch.setenv("JOBSEARCH_CHROME_EXECUTABLE", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    kwargs = browser_launch_kwargs(headless=True)
    assert "executable_path" not in kwargs
    assert "channel" not in kwargs


def test_launch_kwargs_headed_prefers_real_chrome(monkeypatch, tmp_path):
    fake = tmp_path / "Google Chrome"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr("browser_session.REAL_CHROME_CANDIDATES", (fake,))
    monkeypatch.delenv("JOBSEARCH_CHROME_EXECUTABLE", raising=False)
    kwargs = browser_launch_kwargs(headless=False)
    assert kwargs["executable_path"] == str(fake)


def test_headless_chromium_ready_when_shell_installed(monkeypatch, tmp_path: Path):
    shell = tmp_path / "chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell"
    shell.parent.mkdir(parents=True)
    shell.write_text("", encoding="utf-8")
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    assert headless_chromium_ready() is True
    assert headless_chromium_executable() == shell


def test_headless_chromium_missing_when_not_installed(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    assert headless_chromium_ready() is False
    msg = headless_chromium_missing_message()
    assert "patchright install chromium" in msg
    assert str(tmp_path) in msg
