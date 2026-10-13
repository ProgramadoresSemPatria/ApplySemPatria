"""Debug report bundle (no PII)."""

from __future__ import annotations

import json

from retrieval.shared.support_bundle import build_debug_report, sanitize_text


def test_sanitize_strips_urls():
    assert "<url>" in sanitize_text("failed at https://example.com/path")


def test_build_debug_report_shape(tmp_path, monkeypatch):
    import retrieval.shared.support_bundle as sb

    monkeypatch.setattr(sb, "ROOT", tmp_path)
    (tmp_path / "logs").mkdir()
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / "state" / "research-run.json").write_text(
        json.dumps({"running": False, "ok": False, "message": "https://secret.test"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "research_log.RUN_PATH",
        tmp_path / "state" / "research-run.json",
    )
    monkeypatch.setattr("research_log.ROOT", tmp_path)

    report = build_debug_report()
    assert report["schema"] == 1
    assert report["kind"] == "applysempatria_debug_report"
    assert "research_run" in report
    msg = report["research_run"].get("message") or ""
    assert "secret.test" not in msg
