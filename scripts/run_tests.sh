#!/usr/bin/env bash
# Run test tiers with optional stability repeats.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${PY:-python3}"
TIER="${1:-all}"
REPEATS="${REPEATS:-1}"

UNIT_ARGS=(-m "not integration and not playwright and not har and not browser" --tb=short -q)
PW_ARGS=(--tb=short -q)
COV_ARGS=(
  --cov=scripts
  --cov-report=term-missing:skip-covered
  --cov-report=html:htmlcov
  --cov-report=xml:coverage.xml
)
# file:// HTML baseline + HAR replay + UI e2e
PW_PATHS=(
  "tests/test_flow_linkedin_fixtures.py"
  "tests/test_flow_linkedin_har.py"
  "tests/e2e/"
)

run_unit() {
  "$PY" -m pytest tests/ "${UNIT_ARGS[@]}" "$@"
}

run_coverage_unit() {
  echo "=== coverage (unit tier) ==="
  "$PY" -m pytest tests/ "${UNIT_ARGS[@]}" "${COV_ARGS[@]}"
}

run_coverage_all() {
  echo "=== coverage (unit + browser, combined) ==="
  rm -f .coverage coverage.xml
  "$PY" -m pytest tests/ "${UNIT_ARGS[@]}" --cov=scripts --cov-report=
  "$PY" -m pytest "${PW_PATHS[@]}" --cov=scripts --cov-append --cov-report= "${PW_ARGS[@]}"
  "$PY" -m coverage report --skip-covered
  "$PY" -m coverage html
  "$PY" -m coverage xml -o coverage.xml
}

print_coverage_summary() {
  if [[ -f coverage.xml ]]; then
    "$PY" - <<'PY'
import xml.etree.ElementTree as ET
from pathlib import Path

root = ET.parse(Path("coverage.xml")).getroot()
rate = float(root.attrib.get("line-rate", 0)) * 100
lines = root.attrib.get("lines-valid", "?")
covered = root.attrib.get("lines-covered", "?")
print(f"Total line coverage: {rate:.1f}% ({covered}/{lines} lines)")
PY
  fi
}

verify_hars() {
  echo "=== verify HAR fixtures ==="
  for name in profile-connect profile-message profile-pending profile-connect-more profile-connected profile-connected-only; do
    f="tests/fixtures/har/${name}.har"
    if [[ ! -s "$f" ]]; then
      echo "Missing HAR: $f — run: python scripts/generate_linkedin_hars.py" >&2
      exit 1
    fi
  done
  "$PY" -m pytest tests/test_har_fixtures.py -q --tb=short
}

run_playwright() {
  verify_hars
  "$PY" -m pytest "${PW_PATHS[@]}" "${PW_ARGS[@]}" "$@"
}

case "$TIER" in
  verify-hars)
    verify_hars
    ;;
  unit)
    for i in $(seq 1 "$REPEATS"); do
      echo "=== unit run $i/$REPEATS ==="
      run_unit
    done
    ;;
  coverage)
    run_coverage_unit
    print_coverage_summary
    echo "HTML report: htmlcov/index.html"
    ;;
  coverage-all)
    verify_hars
    run_coverage_all
    print_coverage_summary
    echo "HTML report: htmlcov/index.html"
    ;;
  playwright|har)
    for i in $(seq 1 "$REPEATS"); do
      echo "=== browser run $i/$REPEATS ==="
      run_playwright
    done
    ;;
  stable)
    REPEATS=5 run_unit
    REPEATS=3 run_playwright
    ;;
  all)
    run_unit
    run_playwright
    ;;
  *)
    echo "Usage: $0 {unit|playwright|har|verify-hars|coverage|coverage-all|all|stable}" >&2
    exit 1
    ;;
esac

echo "OK ($TIER)"
