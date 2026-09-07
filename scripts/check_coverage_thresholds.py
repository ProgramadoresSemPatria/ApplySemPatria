#!/usr/bin/env python3
"""Fail if coverage.xml is below floors in coverage-thresholds.json."""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _load_file_rates(coverage_xml: Path) -> tuple[float, dict[str, float]]:
    root = ET.parse(coverage_xml).getroot()
    total = float(root.attrib["line-rate"])
    rates: dict[str, float] = {}
    for cls in root.iter("class"):
        filename = cls.attrib.get("filename", "")
        if filename:
            rates[filename] = float(cls.attrib.get("line-rate", 0))
    return total, rates


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    coverage_xml = Path(sys.argv[1]) if len(sys.argv) > 1 else repo / "coverage.xml"
    thresholds_path = repo / "coverage-thresholds.json"

    if not coverage_xml.is_file():
        print(f"Missing coverage report: {coverage_xml}", file=sys.stderr)
        return 1
    if not thresholds_path.is_file():
        print(f"Missing thresholds file: {thresholds_path}", file=sys.stderr)
        return 1

    thresholds = json.loads(thresholds_path.read_text(encoding="utf-8"))
    total_rate, file_rates = _load_file_rates(coverage_xml)
    failures: list[str] = []

    min_total = float(thresholds.get("total_line_rate_min", 0))
    if total_rate < min_total:
        failures.append(
            f"TOTAL: {total_rate * 100:.1f}% < {min_total * 100:.1f}% minimum"
        )

    for path, min_rate in thresholds.get("modules", {}).items():
        min_rate = float(min_rate)
        rate = file_rates.get(path)
        if rate is None:
            basename = Path(path).name
            rate = file_rates.get(basename)
        if rate is None:
            failures.append(f"{path}: not present in coverage.xml")
        elif rate < min_rate:
            failures.append(
                f"{path}: {rate * 100:.1f}% < {min_rate * 100:.1f}% minimum"
            )

    if failures:
        print("Coverage thresholds FAILED:", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        print(
            "\nAdd tests or update coverage-thresholds.json intentionally.",
            file=sys.stderr,
        )
        return 1

    module_count = len(thresholds.get("modules", {}))
    print(
        f"Coverage thresholds OK — total {total_rate * 100:.1f}% "
        f"({module_count} module floors checked)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
