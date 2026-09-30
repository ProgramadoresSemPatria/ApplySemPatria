#!/usr/bin/env bash
# Deep LinkedIn content search via Patchright browser scroll.
set -euo pipefail
# shellcheck source=lib/run_collect_python.sh
source "$(cd "$(dirname "$0")" && pwd)/lib/run_collect_python.sh"
run_collect_python linkedin_content_collect.py "$@"
