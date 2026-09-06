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
# file:// HTML baseline + HAR replay + UI e2e
PW_PATHS=(
  "tests/test_flow_linkedin_fixtures.py"
  "tests/test_flow_linkedin_har.py"
  "tests/e2e/"
)

run_unit() {
  "$PY" -m pytest tests/ "${UNIT_ARGS[@]}" "$@"
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
    echo "Usage: $0 {unit|playwright|har|verify-hars|all|stable}" >&2
    exit 1
    ;;
esac

echo "OK ($TIER)"
