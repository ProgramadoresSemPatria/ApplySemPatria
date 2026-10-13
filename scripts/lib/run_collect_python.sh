#!/usr/bin/env bash
# Run a scripts/*.py collect module with project .venv, then uvx fallback (no hardcoded paths).
set -euo pipefail

_collect_repo_root() {
  local here
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  if [[ -d "$here/scripts" && -f "$here/pyproject.toml" ]]; then
    echo "$here"
    return 0
  fi
  if [[ -d "$here/../scripts" && -f "$here/../pyproject.toml" ]]; then
    (cd "$here/.." && pwd)
    return 0
  fi
  echo "$here"
}

ROOT="$(_collect_repo_root)"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-${HOME}/.linkedin-mcp/patchright-browsers}"

run_collect_python() {
  local script_name="$1"
  shift
  local script_path="$ROOT/scripts/$script_name"
  if [[ ! -f "$script_path" ]]; then
    echo "✗ Missing script: $script_path" >&2
    exit 1
  fi
  local venv_py="$ROOT/.venv/bin/python3"
  if [[ -x "$venv_py" ]]; then
    exec "$venv_py" "$script_path" "$@"
  fi
  if [[ -n "${UVX:-}" ]] && [[ -x "$UVX" ]]; then
    exec "$UVX" --with patchright python3 "$script_path" "$@"
  fi
  if command -v uvx >/dev/null 2>&1; then
    exec uvx --with patchright python3 "$script_path" "$@"
  fi
  echo "✗ No runnable Python for LinkedIn collect." >&2
  echo "  From repo root run: make install   (creates .venv + patchright)" >&2
  echo "  Or install uvx on PATH and retry." >&2
  exit 1
}
