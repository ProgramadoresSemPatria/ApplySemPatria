#!/usr/bin/env bash
# Run test tiers with optional stability repeats.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${PY:-python3}"
TIER="${1:-all}"
REPEATS="${REPEATS:-1}"

UNIT_ARGS=(-m "not integration and not playwright" --tb=short -q)
PW_ARGS=(--tb=short -q)
PW_PATHS=("tests/test_flow_linkedin_fixtures.py" "tests/e2e/")

run_unit() {
  "$PY" -m pytest tests/ "${UNIT_ARGS[@]}" "$@"
}

run_playwright() {
  "$PY" -m pytest "${PW_PATHS[@]}" "${PW_ARGS[@]}" "$@"
}

case "$TIER" in
  unit)
    for i in $(seq 1 "$REPEATS"); do
      echo "=== unit run $i/$REPEATS ==="
      run_unit
    done
    ;;
  playwright)
    for i in $(seq 1 "$REPEATS"); do
      echo "=== playwright run $i/$REPEATS ==="
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
    echo "Usage: $0 {unit|playwright|all|stable}" >&2
    exit 1
    ;;
esac

echo "OK ($TIER)"
