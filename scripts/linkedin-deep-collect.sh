#!/usr/bin/env bash
# Deep LinkedIn content search via Patchright browser scroll.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$(dirname "$0")/linkedin_content_collect.py"
export PLAYWRIGHT_BROWSERS_PATH="${HOME}/.linkedin-mcp/patchright-browsers"
VENV_PY="$ROOT/.venv/bin/python3"
if [[ -x "$VENV_PY" ]]; then
  exec "$VENV_PY" "$SCRIPT" "$@"
fi
UVX="${UVX:-/Users/caio/.local/bin/uvx}"
exec "$UVX" --with patchright python3 "$SCRIPT" "$@"
