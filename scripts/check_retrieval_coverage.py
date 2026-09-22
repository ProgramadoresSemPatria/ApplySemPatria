#!/usr/bin/env python3
"""Measure and enforce coverage floors for scripts/retrieval/."""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


RETRIEVAL_MARKER = "retrieval/"


def _sources_are_retrieval_only(root: ET.Element) -> bool:
    for source in root.findall("./sources/source"):
        text = (source.text or "").replace("\\", "/").rstrip("/")
        if text.endswith("/scripts/retrieval") or text.endswith("/retrieval"):
            return True
    return False


@dataclass
class FileCoverage:
    filename: str
    lines: int = 0
    covered: int = 0
    branches: int = 0
    covered_branches: int = 0
    missed_lines: list[int] = field(default_factory=list)

    @property
    def line_rate(self) -> float:
        return self.covered / self.lines if self.lines else 1.0

    @property
    def branch_rate(self) -> float:
        return self.covered_branches / self.branches if self.branches else 1.0

    @property
    def missed(self) -> int:
        return self.lines - self.covered


def _normalize_filename(raw: str, *, retrieval_only_report: bool) -> str | None:
    path = raw.replace("\\", "/").lstrip("/")
    if retrieval_only_report:
        return f"retrieval/{path}" if path else "retrieval/"
    idx = path.find(RETRIEVAL_MARKER)
    if idx < 0:
        return None
    return path[idx:]


def _parse_branch(line_el: ET.Element) -> tuple[int, int]:
    cond = line_el.attrib.get("condition-coverage", "")
    if not cond or "(" not in cond:
        return 0, 0
    try:
        inner = cond.split("(", 1)[1].split(")", 1)[0]
        covered, total = inner.split("/")
        return int(total), int(covered)
    except (IndexError, ValueError):
        return 0, 0


def parse_retrieval_files(coverage_xml: Path, exclude: set[str]) -> dict[str, FileCoverage]:
    root = ET.parse(coverage_xml).getroot()
    retrieval_only = _sources_are_retrieval_only(root)
    files: dict[str, FileCoverage] = {}

    for cls in root.iter("class"):
        rel = _normalize_filename(cls.attrib.get("filename", ""), retrieval_only_report=retrieval_only)
        if not rel or rel in exclude:
            continue

        lines_el = cls.find("lines")
        if lines_el is None:
            continue

        fc = files.setdefault(rel, FileCoverage(filename=rel))
        for line in lines_el.findall("line"):
            num = int(line.attrib["number"])
            hits = int(line.attrib.get("hits", 0))
            fc.lines += 1
            if hits > 0:
                fc.covered += 1
            else:
                fc.missed_lines.append(num)
            b_total, b_cov = _parse_branch(line)
            fc.branches += b_total
            fc.covered_branches += b_cov

    return files


def aggregate(files: dict[str, FileCoverage]) -> tuple[int, int, int, int]:
    lines = covered = branches = covered_branches = 0
    for fc in files.values():
        lines += fc.lines
        covered += fc.covered
        branches += fc.branches
        covered_branches += fc.covered_branches
    return lines, covered, branches, covered_branches


def _rate(covered: int, total: int) -> float:
    return covered / total if total else 1.0


def _print_report(
    files: dict[str, FileCoverage],
    *,
    top_gaps: int,
    line_rate: float,
    branch_rate: float,
) -> None:
    print(
        f"Retrieval coverage: {line_rate * 100:.2f}% line "
        f"({sum(fc.covered for fc in files.values())}/{sum(fc.lines for fc in files.values())} lines), "
        f"{branch_rate * 100:.2f}% branch"
    )
    print(f"Files measured: {len(files)}")

    worst = sorted(files.values(), key=lambda fc: (-fc.missed, fc.filename))[:top_gaps]
    if worst and worst[0].missed:
        print("\nLargest gaps (by missed lines):")
        for fc in worst:
            if fc.missed <= 0:
                continue
            preview = fc.missed_lines[:8]
            suffix = "…" if len(fc.missed_lines) > 8 else ""
            print(
                f"  {fc.filename}: {fc.line_rate * 100:.1f}% "
                f"({fc.missed} missed) lines {preview}{suffix}"
            )


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    coverage_xml = Path(sys.argv[1]) if len(sys.argv) > 1 else repo / "coverage.xml"
    config_path = repo / "coverage-retrieval.json"
    report_only = "--report-only" in sys.argv

    if not coverage_xml.is_file():
        print(f"Missing coverage report: {coverage_xml}", file=sys.stderr)
        return 1
    if not config_path.is_file():
        print(f"Missing thresholds file: {config_path}", file=sys.stderr)
        return 1

    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    exclude = set(cfg.get("exclude", []))
    files = parse_retrieval_files(coverage_xml, exclude)
    if not files:
        print("No retrieval/ files found in coverage.xml", file=sys.stderr)
        return 1

    total_lines, covered_lines, total_branches, covered_branches = aggregate(files)
    line_rate = _rate(covered_lines, total_lines)
    branch_rate = _rate(covered_branches, total_branches)

    _print_report(
        files,
        top_gaps=int(cfg.get("report_top_gaps", 15)),
        line_rate=line_rate,
        branch_rate=branch_rate,
    )

    if report_only:
        return 0

    failures: list[str] = []
    min_line = float(cfg.get("line_rate_min", 1.0))
    min_branch = float(cfg.get("branch_rate_min", 1.0))

    if line_rate < min_line:
        failures.append(
            f"TOTAL line: {line_rate * 100:.2f}% < {min_line * 100:.2f}% minimum"
        )
    if total_branches and branch_rate < min_branch:
        failures.append(
            f"TOTAL branch: {branch_rate * 100:.2f}% < {min_branch * 100:.2f}% minimum"
        )

    for path, min_rate in cfg.get("modules", {}).items():
        min_rate = float(min_rate)
        fc = files.get(path)
        if fc is None:
            failures.append(f"{path}: not present in coverage.xml")
        elif fc.line_rate < min_rate:
            failures.append(
                f"{path}: {fc.line_rate * 100:.2f}% < {min_rate * 100:.2f}% minimum"
            )

    if failures:
        print("\nRetrieval coverage FAILED:", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        print(
            "\nRun: ./scripts/run_tests.sh retrieval-coverage",
            file=sys.stderr,
        )
        print("Add tests in tests/retrieval/ or update coverage-retrieval.json intentionally.", file=sys.stderr)
        return 1

    module_count = len(cfg.get("modules", {}))
    extra = f", {module_count} module floors" if module_count else ""
    print(f"Retrieval coverage OK — 100% gate passed{extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
