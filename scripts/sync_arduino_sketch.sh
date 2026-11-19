#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Synchronize esp32-firmware into Arduino IDE PenAndPaperPuzzles sketch folder
# Usage:
#   ./scripts/sync_arduino_sketch.sh          # Sync files and prune orphans
#   ./scripts/sync_arduino_sketch.sh --check  # Verify parity without mutating repo
# ==============================================================================

CHECK_ONLY=false
if [[ "${1:-}" == "--check" ]]; then
  CHECK_ONLY=true
elif [[ -n "${1:-}" ]]; then
  echo "Usage: $0 [--check]" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKETCH_DIR="$ROOT_DIR/PenAndPaperPuzzles"
FW_DIR="$ROOT_DIR/esp32-firmware"

STAGING_DIR="$(mktemp -d "${TMPDIR:-/tmp}/arduino_sketch_sync.XXXXXX")"
trap 'rm -rf "$STAGING_DIR"' EXIT

sed_inplace_ere() {
  if [[ "$(uname -s)" == "Darwin" ]]; then
    sed -E -i '' "$@"
  else
    sed -E -i "$@"
  fi
}

# Copy config, drivers, generators, and main sketch into clean staging folder
cp "$FW_DIR/include/config.h" "$STAGING_DIR/"
cp "$FW_DIR/src/config/"* "$STAGING_DIR/"
cp "$FW_DIR/src/printer/"* "$STAGING_DIR/"
cp "$FW_DIR/src/time/"* "$STAGING_DIR/"
cp "$FW_DIR/src/generators/"* "$STAGING_DIR/"
cp "$FW_DIR/src/main.cpp" "$STAGING_DIR/PenAndPaperPuzzles.ino"

# Flatten relative include paths for Arduino IDE single-folder compilation
shopt -s nullglob
sketch_files=("$STAGING_DIR"/*.h "$STAGING_DIR"/*.cpp "$STAGING_DIR"/*.ino)
shopt -u nullglob

if (( ${#sketch_files[@]} > 0 )); then
  sed_inplace_ere 's~#include "\.\./config\.h"~#include "config.h"~g' "${sketch_files[@]}"
  sed_inplace_ere 's~#include "(\.\./)?(printer|time|config|generators)/([^"]+)"~#include "\3"~g' "${sketch_files[@]}"
fi

if [[ "$CHECK_ONLY" == "true" ]]; then
  if [[ ! -d "$SKETCH_DIR" ]]; then
    echo "ERROR: Arduino sketch directory $SKETCH_DIR does not exist." >&2
    exit 1
  fi
  if ! diff_out="$(diff -rq "$STAGING_DIR" "$SKETCH_DIR" 2>&1)"; then
    echo "ERROR: PenAndPaperPuzzles/ is out of sync with esp32-firmware/:" >&2
    echo "$diff_out" >&2
    echo "Run './scripts/sync_arduino_sketch.sh' to synchronize." >&2
    exit 1
  fi
  echo "Verified PenAndPaperPuzzles/ matches esp32-firmware/ (zero drift)."
  exit 0
fi

echo "Syncing esp32-firmware -> PenAndPaperPuzzles Arduino sketch..."
mkdir -p "$SKETCH_DIR"

# Prune orphaned files in PenAndPaperPuzzles/ not present in staging
for existing in "$SKETCH_DIR"/*; do
  [[ -e "$existing" ]] || continue
  base="$(basename "$existing")"
  if [[ ! -e "$STAGING_DIR/$base" ]]; then
    echo "  Pruning orphaned file: $base"
    rm -rf "$existing"
  fi
done

cp -R "$STAGING_DIR"/. "$SKETCH_DIR"/
echo "Successfully synchronized PenAndPaperPuzzles Arduino sketch!"
