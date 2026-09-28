#!/usr/bin/env bash
# End-to-end smoke inside Docker: fresh tree → install → onboard → table → UI HTTP.
#   docker compose -f dev/docker-compose.yml run --rm e2e
#   USE_INPLACE=1 skips rsync (image already contains /app).
set -euo pipefail

REPO="${REPO_ROOT:-/app}"
FRESH="${JOBSEARCH_FRESH_DIR:-}"
USE_INPLACE="${USE_INPLACE:-0}"

if [[ "$USE_INPLACE" == "1" ]] || [[ -z "$FRESH" ]]; then
  FRESH="${REPO}"
  cd "$FRESH"
else
  rm -rf "$FRESH"
  mkdir -p "$FRESH"
  echo "→ Copying project to $FRESH …"
  rsync -a \
    --exclude '.venv' \
    --exclude '.venv-test' \
    --exclude '/registry' \
    --exclude '/runs' \
    --exclude '/state' \
    --exclude '/secrets' \
    --exclude '/tracks' \
    --exclude '.git' \
    "$REPO/" "$FRESH/"
  mkdir -p "$FRESH/registry" "$FRESH/state" "$FRESH/runs" "$FRESH/logs"
  echo '{"jobs":[]}' > "$FRESH/registry/jobs.json"
  cd "$FRESH"
  pip install --no-cache-dir -e ".[gmail]" >/dev/null
fi

mkdir -p registry state runs logs tracks
[[ -f registry/jobs.json ]] || echo '{"jobs":[]}' > registry/jobs.json

python3 - <<'PY'
from pathlib import Path
Path("/tmp/sample-resume.pdf").write_bytes(b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n")
PY

echo "→ jobsearch install --check-only"
jobsearch install --check-only

echo "→ jobsearch onboarding (ai-engineer, non-interactive)"
jobsearch onboarding --track ai-engineer --reset --yes \
  --resume /tmp/sample-resume.pdf \
  --full-name "Docker E2E User" \
  --email "docker-e2e@example.com" \
  --phone "+10000000001" \
  --linkedin-url "https://www.linkedin.com/in/docker-e2e/" \
  --current-title "AI Engineer" \
  --email-mode skip \
  --linkedin-mode skip

echo "→ jobsearch doctor"
jobsearch doctor

echo "→ jobsearch table"
jobsearch table --track ai-engineer

echo "→ UI server (background) + HTTP checks"
PY=python3
$PY scripts/ui_server.py --port 8765 --no-open --browser none &
UI_PID=$!
cleanup() { kill "$UI_PID" 2>/dev/null || true; }
trap cleanup EXIT

for i in $(seq 1 30); do
  if curl -sf -o /dev/null "http://127.0.0.1:8765/"; then
    break
  fi
  sleep 0.5
done

curl -sf -o /dev/null "http://127.0.0.1:8765/"
curl -sf "http://127.0.0.1:8765/api/meta" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('ui_version')"
curl -sf "http://127.0.0.1:8765/api/snapshot" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'jobs' in d"

echo
echo "============================================================"
echo "  ✓ docker e2e passed (install, onboard, table, UI HTTP)"
echo "============================================================"
