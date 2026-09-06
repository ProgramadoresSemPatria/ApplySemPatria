#!/usr/bin/env bash
# Copy example track configs into tracks/ (safe to re-run; skips existing files).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TRACK="${1:-ai-engineer}"
SRC="$ROOT/examples/tracks/$TRACK"
DST="$ROOT/tracks/$TRACK"

if [[ ! -d "$SRC" ]]; then
  echo "Unknown track: $TRACK (no $SRC)" >&2
  exit 1
fi

mkdir -p "$DST"
copied=0
skipped=0
for f in "$SRC"/*; do
  base="$(basename "$f")"
  dest="$DST/$base"
  if [[ -e "$dest" ]]; then
    echo "skip  $dest (already exists)"
    skipped=$((skipped + 1))
  else
    cp "$f" "$dest"
    echo "copy  $dest"
    copied=$((copied + 1))
  fi
done
echo "Done: $copied copied, $skipped skipped for track $TRACK"
echo "Edit $DST/applicant-profile.json then: jobsearch onboarding --track $TRACK"
