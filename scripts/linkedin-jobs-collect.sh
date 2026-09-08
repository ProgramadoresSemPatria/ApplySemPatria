#!/usr/bin/env bash
# LinkedIn Jobs search via Patchright pagination.
set -euo pipefail
UVX="${UVX:-/Users/caio/.local/bin/uvx}"
export PLAYWRIGHT_BROWSERS_PATH="${HOME}/.linkedin-mcp/patchright-browsers"
exec "$UVX" --with patchright python3 "$(dirname "$0")/linkedin_jobs_collect.py" "$@"
