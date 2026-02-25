#!/bin/bash
# Package a public-safe .skill bundle by excluding local mode overlays.
# Usage:
#   ./scripts/package_public.sh <path-to-package_skill.py> [output_dir]
#   PACKAGE_SKILL_PY=/path/to/package_skill.py ./scripts/package_public.sh [output_dir]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SKILL_NAME="$(basename "$SKILL_DIR")"

PACKAGER="${PACKAGE_SKILL_PY:-}"
OUTPUT_DIR=""

if [ $# -ge 1 ] && [ -n "${1:-}" ]; then
  if [[ "$1" == *.py ]]; then
    PACKAGER="$1"
    OUTPUT_DIR="${2:-}"
  else
    OUTPUT_DIR="$1"
  fi
fi

if [ -z "$PACKAGER" ]; then
  echo "ERROR: missing packager path."
  echo "Set PACKAGE_SKILL_PY or pass path-to-package_skill.py as arg 1."
  exit 1
fi

if [ -z "$OUTPUT_DIR" ]; then
  OUTPUT_DIR="$(pwd)"
fi

STAGE_ROOT="$(mktemp -d)"
trap 'rm -rf "$STAGE_ROOT"' EXIT
STAGE_SKILL_DIR="${STAGE_ROOT}/${SKILL_NAME}"

mkdir -p "$STAGE_SKILL_DIR"

rsync -a \
  --exclude 'modes/' \
  --exclude 'briefs/*.md' \
  --exclude '*.skill' \
  --exclude '*.zip' \
  "${SKILL_DIR}/" "${STAGE_SKILL_DIR}/"

python3 "$PACKAGER" "$STAGE_SKILL_DIR" "$OUTPUT_DIR"
