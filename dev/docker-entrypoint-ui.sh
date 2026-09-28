#!/usr/bin/env bash
# Long-running UI for manual testing in Docker (isolated data under /app).
set -euo pipefail
cd /app

mkdir -p registry state runs logs tracks
[[ -f registry/jobs.json ]] || echo '{"jobs":[]}' > registry/jobs.json

if [[ ! -f tracks/ai-engineer/applicant-profile.json ]]; then
  echo "→ First run: seeding track + jobsearch onboarding (ai-engineer) …"
  mkdir -p tracks/ai-engineer
  cp -R examples/tracks/ai-engineer/. tracks/ai-engineer/
  python3 - <<'PY'
from pathlib import Path
Path("/tmp/sample-resume.pdf").write_bytes(b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n")
PY
  jobsearch onboarding --track ai-engineer --reset --yes \
    --resume /tmp/sample-resume.pdf \
    --full-name "Docker UI User" \
    --email "docker-ui@example.com" \
    --phone "+10000000002" \
    --linkedin-url "https://www.linkedin.com/in/docker-ui/" \
    --current-title "AI Engineer" \
    --email-mode skip \
    --linkedin-mode skip
else
  echo "→ Track profile exists — skipping onboarding (delete container/volume to re-run)"
fi

[[ -f tracks/ai-engineer/config.json ]] || cp examples/tracks/ai-engineer/config.json tracks/ai-engineer/

echo "→ jobsearch table (refresh UI snapshot)"
jobsearch table --track ai-engineer || true

echo "Applications UI → http://127.0.0.1:8765/ (from host: mapped port)"
exec python3 scripts/ui_server.py --port 8765 --no-open --browser none
