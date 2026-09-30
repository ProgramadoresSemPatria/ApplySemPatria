#!/usr/bin/env bash
# LinkedIn browser session setup (cookies for Patchright — no Cursor MCP required).
set -euo pipefail

if [[ -n "${UVX:-}" ]] && [[ -x "$UVX" ]]; then
  :
elif command -v uvx >/dev/null 2>&1; then
  UVX="$(command -v uvx)"
else
  echo "✗ uvx not found. Install uv or set UVX to your uvx binary." >&2
  exit 1
fi
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
