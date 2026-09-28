#!/usr/bin/env bash
# Remove local-only data (tracks, registry, state, secrets, runs, logs).
# Does NOT remove .venv, source code, or pip install.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CONFIRM="${CONFIRM:-}"
BACKUP="${BACKUP:-1}"
RESET_LINKEDIN="${RESET_LINKEDIN:-1}"
RESET_BROWSER="${RESET_BROWSER:-0}"
BACKUP_DIR="${BACKUP_DIR:-}"

if [[ "$CONFIRM" != "1" ]]; then
  cat <<EOF
This will delete local job-search data under:
  $ROOT

  • tracks/          (profiles, configs)
  • registry/        (discovered jobs)
  • state/           (tokens, apply progress)
  • secrets/         (Gmail app password, OAuth client copies)
  • runs/            (tables, audits, collect output)
  • logs/
  • legacy root JSON configs (applicant-profile.json, etc.)
$( [[ "$RESET_LINKEDIN" == "1" ]] && echo "  • ~/.linkedin-mcp/  (LinkedIn session)" )
$( [[ "$RESET_BROWSER" == "1" ]] && echo "  • patchright-profile/  (local browser profile in repo)" )

Keeps: .venv, examples/, code, registry/.gitkeep, runs/tables/README.md

To proceed:
  make reset-data CONFIRM=1
  make reset-data CONFIRM=1 BACKUP=0              # no backup
  make reset-data CONFIRM=1 RESET_LINKEDIN=0      # keep LinkedIn cookies
EOF
  exit 1
fi

if [[ "$BACKUP" == "1" ]]; then
  if [[ -z "$BACKUP_DIR" ]]; then
    BACKUP_DIR="$(dirname "$ROOT")/job-search-data-backup-$(date +%Y-%m-%d-%H%M%S)"
  fi
  mkdir -p "$BACKUP_DIR"
  echo "Backing up to $BACKUP_DIR …"
  for name in tracks registry state secrets runs logs; do
    if [[ -d "$ROOT/$name" ]] && [[ -n "$(ls -A "$ROOT/$name" 2>/dev/null || true)" ]]; then
      cp -R "$ROOT/$name" "$BACKUP_DIR/"
    fi
  done
  for f in applicant-profile.json profile.json config.json email-apply-config.json \
    linkedin-posts-config.json google-jobs-config.json form-answers.json resume-chameleon-config.json; do
    if [[ -f "$ROOT/$f" ]]; then
      mkdir -p "$BACKUP_DIR/root-legacy"
      cp "$ROOT/$f" "$BACKUP_DIR/root-legacy/"
    fi
  done
  if [[ "$RESET_LINKEDIN" == "1" ]] && [[ -d "$HOME/.linkedin-mcp" ]]; then
    cp -R "$HOME/.linkedin-mcp" "$BACKUP_DIR/linkedin-mcp-host"
  fi
  echo "  ✓ Backup done"
fi

echo "Resetting local data …"

find "$ROOT/tracks" -mindepth 1 ! -name '.gitkeep' -exec rm -rf {} + 2>/dev/null || true
mkdir -p "$ROOT/tracks"

mkdir -p "$ROOT/registry"
echo '{"jobs":[]}' > "$ROOT/registry/jobs.json"
touch "$ROOT/registry/.gitkeep" 2>/dev/null || true

find "$ROOT/state" -mindepth 1 ! -name '.gitkeep' -delete 2>/dev/null || true
mkdir -p "$ROOT/state"
touch "$ROOT/state/.gitkeep" 2>/dev/null || true

rm -rf "$ROOT/secrets"
mkdir -p "$ROOT/logs"
find "$ROOT/logs" -mindepth 1 ! -name '.gitkeep' -delete 2>/dev/null || true
touch "$ROOT/logs/.gitkeep" 2>/dev/null || true

mkdir -p "$ROOT/runs/tables"
find "$ROOT/runs" -mindepth 1 -maxdepth 1 ! -name 'tables' -exec rm -rf {} + 2>/dev/null || true
find "$ROOT/runs/tables" -mindepth 1 ! -name 'README.md' -delete 2>/dev/null || true

for f in applicant-profile.json profile.json config.json email-apply-config.json \
  linkedin-posts-config.json google-jobs-config.json form-answers.json resume-chameleon-config.json; do
  rm -f "$ROOT/$f"
done

if [[ "$RESET_LINKEDIN" == "1" ]] && [[ -d "$HOME/.linkedin-mcp" ]]; then
  rm -rf "$HOME/.linkedin-mcp"
  echo "  ✓ Removed ~/.linkedin-mcp"
fi

if [[ "$RESET_BROWSER" == "1" ]]; then
  rm -rf "$ROOT/patchright-profile" "$ROOT/.playwright"
  echo "  ✓ Removed local browser profile dirs"
fi

echo ""
echo "✓ Local data cleared — first-run empty state."
echo ""
echo "Next:"
echo "  make quickstart && make onboarding"
echo "  # if install fails: make clean-venv && make quickstart"
