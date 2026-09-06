#!/usr/bin/env bash
# Deep LinkedIn content search via Patchright browser scroll.
set -euo pipefail
UVX="${UVX:-/Users/caio/.local/bin/uvx}"
export PLAYWRIGHT_BROWSERS_PATH="${HOME}/.linkedin-mcp/patchright-browsers"
exec "$UVX" --with patchright python3 "$(dirname "$0")/linkedin_content_collect.py" "$@"
