#!/usr/bin/env bash
# LinkedIn Jobs search via Patchright pagination.
set -euo pipefail
# shellcheck source=lib/run_collect_python.sh
source "$(cd "$(dirname "$0")" && pwd)/lib/run_collect_python.sh"
run_collect_python linkedin_jobs_collect.py "$@"
