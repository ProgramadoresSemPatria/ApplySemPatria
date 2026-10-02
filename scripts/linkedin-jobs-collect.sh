#!/usr/bin/env bash
# LinkedIn Jobs search via Patchright pagination.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$(dirname "$0")/linkedin_jobs_collect.py"
export PLAYWRIGHT_BROWSERS_PATH="${HOME}/.linkedin-mcp/patchright-browsers"
VENV_PY="$ROOT/.venv/bin/python3"
if [[ -x "$VENV_PY" ]]; then
  exec "$VENV_PY" "$SCRIPT" "$@"
fi

UVX="${UVX:-uvx}"
if ! command -v "$UVX" >/dev/null 2>&1; then
  echo "Patchright runner unavailable: install project dependencies with 'make install' or install uvx." >&2
  exit 127
fi
exec "$UVX" --with patchright python3 "$SCRIPT" "$@"
