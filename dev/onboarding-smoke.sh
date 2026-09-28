#!/usr/bin/env bash
# Smoke test: fresh copy of job-search → install → onboarding → doctor → discover dry-run.
# Usage (from repo root):
#   docker compose -f dev/docker-compose.yml run --rm onboarding-smoke
set -euo pipefail

REPO="${REPO_ROOT:-/repo}"
FRESH="/tmp/job-search-fresh"

echo "============================================================"
echo "  onboarding smoke (clean environment)"
echo "============================================================"
echo

rm -rf "$FRESH"
mkdir -p "$FRESH"

echo "→ Copying minimal project tree to $FRESH …"
if command -v rsync >/dev/null 2>&1; then
  rsync -a \
    --exclude '.venv' \
    --exclude '/registry' \
    --exclude '/runs' \
    --exclude '/state' \
    --exclude '/secrets' \
    --exclude '/tracks' \
    --exclude '.git' \
    "$REPO/" "$FRESH/"
else
  tar -C "$REPO" \
    --exclude='.venv' \
    --exclude='./registry' \
    --exclude='./runs' \
    --exclude='./state' \
    --exclude='./secrets' \
    --exclude='./tracks' \
    --exclude='.git' \
    -cf - . | tar -C "$FRESH" -xf -
fi

mkdir -p "$FRESH/registry" "$FRESH/state" "$FRESH/runs"

# Minimal empty registry so discover can run
echo '{"jobs":[]}' > "$FRESH/registry/jobs.json"

# Dummy resume for validation
python3 - <<'PY'
from pathlib import Path
# Smallest valid-enough PDF header for path existence checks
pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
Path("/tmp/sample-resume.pdf").write_bytes(pdf)
PY

cd "$FRESH"

echo
echo "→ pip install -e . (same as README quick start)"
python3 -m pip install --no-cache-dir -e ".[gmail]" >/dev/null

echo
echo "→ jobsearch install --check-only"
jobsearch install --check-only

echo
echo "→ jobsearch onboarding (non-interactive, AI Engineer)"
jobsearch onboarding --track ai-engineer --reset --yes \
  --resume /tmp/sample-resume.pdf \
  --full-name "Smoke Test User" \
  --email "smoke@example.com" \
  --phone "+10000000000" \
  --linkedin-url "https://www.linkedin.com/in/smoke-test/" \
  --current-title "AI Engineer" \
  --email-mode skip \
  --linkedin-mode skip

echo
echo "→ jobsearch configure linkedin --status (disabled by default after onboarding skip)"
jobsearch configure linkedin --track ai-engineer --status
jobsearch doctor

if [[ ! -f tracks/ai-engineer/config.json ]]; then
  cp examples/tracks/ai-engineer/config.json tracks/ai-engineer/
fi

echo
echo "→ jobsearch discover --dry-run --track ai-engineer --since 7d"
jobsearch discover --dry-run --track ai-engineer --since 7d

echo
echo "→ jobsearch tracks list"
jobsearch tracks list

echo
echo "============================================================"
echo "  ✓ onboarding smoke passed"
echo "============================================================"
