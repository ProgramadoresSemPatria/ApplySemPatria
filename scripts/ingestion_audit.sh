#!/usr/bin/env bash
# One-shot ingestion health snapshot (append to logs/ingestion-watch.log via cron or watch loop).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STAMP="$(date '+%Y-%m-%d %H:%M:%S %z')"
echo "=== ingestion audit $STAMP ==="

if curl -sf http://127.0.0.1:8765/api/research/status >/tmp/jobsearch-research-status.json 2>/dev/null; then
  python3 -c "
import json
from pathlib import Path
d=json.loads(Path('/tmp/jobsearch-research-status.json').read_text())
print('research:', json.dumps(d, indent=2))
running=d.get('running')
step=d.get('step')
detail=d.get('detail','')
if running and step=='linkedin_collect' and 'running' in str(detail):
    sec=int(''.join(c for c in str(detail).split() if c.isdigit()) or '0')
    if sec > 2700:
        print('WARN: linkedin_collect over 45m — consider cancel + headed debug')
"
else
  echo "UI not reachable on :8765"
fi

python3 -c "
import json
from pathlib import Path
p=Path('registry/jobs.json')
if p.exists():
    n=len(json.loads(p.read_text()).get('jobs',[]))
    print(f'registry jobs: {n}')
"

pgrep -fl 'daily_research|linkedin_content_collect' 2>/dev/null | head -5 || echo "no research PIDs"

collect="$(find runs -maxdepth 1 -name 'browser-collect-*' -type d 2>/dev/null | wc -l | tr -d ' ')"
echo "browser-collect dirs: $collect"

if [[ -f logs/audit-$(date +%Y-%m-%d).jsonl ]]; then
  echo "last audit events:"
  tail -3 "logs/audit-$(date +%Y-%m-%d).jsonl"
fi
echo ""
