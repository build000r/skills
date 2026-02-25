#!/bin/bash
# Resolve a mode file from ./modes/*.md using cwd_match prefix rules.
# Usage:
#   ./scripts/select_mode.sh [cwd]
# Output:
#   one matching file path on stdout, or "none", or "ambiguous:<count>".

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
MODES_DIR="${SKILL_DIR}/modes"
TARGET_CWD="${1:-$(pwd)}"

if [ ! -d "${MODES_DIR}" ]; then
  echo "none"
  exit 0
fi

shopt -s nullglob
files=("${MODES_DIR}"/*.md)
shopt -u nullglob

if [ ${#files[@]} -eq 0 ]; then
  echo "none"
  exit 0
fi

matches=()
for file in "${files[@]}"; do
  # Parse the first cwd_match line. Expected format: cwd_match: /path/prefix
  cwd_match=$(grep -E '^cwd_match:' "$file" | head -n1 | sed -E 's/^cwd_match:[[:space:]]*//')
  if [ -z "${cwd_match}" ]; then
    continue
  fi

  if [[ "${TARGET_CWD}" == "${cwd_match}"* ]]; then
    matches+=("${file}")
  fi
done

if [ ${#matches[@]} -eq 0 ]; then
  echo "none"
  exit 0
fi

if [ ${#matches[@]} -gt 1 ]; then
  echo "ambiguous:${#matches[@]}"
  printf '%s\n' "${matches[@]}" >&2
  exit 0
fi

echo "${matches[0]}"
