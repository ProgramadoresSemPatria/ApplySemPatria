"""Tests for scripts/check_retrieval_coverage.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "check_retrieval_coverage.py"


RETRIEVAL_XML = """<?xml version="1.0" ?>
<coverage line-rate="0.5" branch-rate="0.5" lines-valid="4" lines-covered="2">
  <sources>
    <source>{source}</source>
  </sources>
  <packages>
    <package name=".">
      <classes>
        <class name="mod.py" filename="mod.py" line-rate="0.5" branch-rate="0.5">
          <lines>
            <line number="1" hits="1"/>
            <line number="2" hits="1"/>
            <line number="3" hits="0"/>
            <line number="4" hits="0" condition-coverage="50% (1/2)"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
"""


@pytest.fixture
def tmp_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "coverage-retrieval.json"
    cfg.write_text(json.dumps({"line_rate_min": 1.0, "branch_rate_min": 1.0}), encoding="utf-8")
    return cfg


def test_checker_passes_report_only(tmp_path: Path, monkeypatch):
    xml = tmp_path / "coverage.xml"
    xml.write_text(
        RETRIEVAL_XML.format(source=str(ROOT / "scripts" / "retrieval")),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    (tmp_path / "coverage-retrieval.json").write_text(
        json.dumps({"line_rate_min": 0.0, "branch_rate_min": 0.0}),
        encoding="utf-8",
    )
    # symlink script expectations: checker reads config from repo root parent of scripts
    # Run via import for report-only path
    sys.path.insert(0, str(ROOT / "scripts"))
    import check_retrieval_coverage as crc

    monkeypatch.setattr(crc, "__file__", str(ROOT / "scripts" / "check_retrieval_coverage.py"))
    files = crc.parse_retrieval_files(xml, set())
    assert "retrieval/mod.py" in files
    assert files["retrieval/mod.py"].line_rate == 0.5


def test_checker_fails_below_100(tmp_path: Path):
    xml = tmp_path / "coverage.xml"
    xml.write_text(
        RETRIEVAL_XML.format(source=str(ROOT / "scripts" / "retrieval")),
        encoding="utf-8",
    )
    cfg = ROOT / "coverage-retrieval.json"
    proc = subprocess.run(
        [sys.executable, str(CHECK), str(xml)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "Retrieval coverage FAILED" in proc.stderr
    assert cfg.is_file()
