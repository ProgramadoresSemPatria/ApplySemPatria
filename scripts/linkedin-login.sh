#!/usr/bin/env bash
# LinkedIn browser session setup (cookies for Patchright — no Cursor MCP required).
set -euo pipefail

UVX="${UVX:-/Users/caio/.local/bin/uvx}"
# Cookie helper from upstream package; we do NOT use LinkedIn MCP in Cursor.
PKG="mcp-server-linkedin@4.23.1"

usage() {
  cat <<EOF
Usage: $(basename "$0") <command>

Commands:
  login       Open browser to sign in to LinkedIn
  import      Import session from local browser (Chrome/Brave/Edge)
  status      Check if LinkedIn session is valid
  logout      Clear stored session

Cookies saved to ~/.linkedin-mcp/cookies.json for Patchright (DM, discovery, forms).

Optional: remove the linkedin server from ~/.cursor/mcp.json if still configured.
EOF
}

cmd="${1:-}"
case "$cmd" in
  login)  "$UVX" "$PKG" --login ;;
  import) "$UVX" "$PKG" --import-from-browser auto ;;
  status) "$UVX" "$PKG" --status ;;
  logout) "$UVX" "$PKG" --logout ;;
  *) usage; exit 1 ;;
esac
