#!/usr/bin/env bash
# drift-detector/scripts/check.sh
# Self-check for drift artifacts in <repo>. Exits non-zero on inconsistency.
set -euo pipefail

REPO="${1:-.}"
[ -d "$REPO" ] || { echo "not a directory: $REPO" >&2; exit 2; }
command -v jq >/dev/null || { echo "need jq" >&2; exit 2; }

cd "$REPO"
errs=0

if [ -f .drift/scan.json ]; then
  if ! jq -e '.meta.stacks and .findings and .summary' .drift/scan.json >/dev/null; then
    echo "FAIL .drift/scan.json missing required top-level keys (meta.stacks, findings, summary)"
    errs=$((errs+1))
  else
    echo "OK   .drift/scan.json structure (stacks=$(jq -r '.meta.stacks | join(",")' .drift/scan.json))"
  fi
else
  echo "SKIP .drift/scan.json not present (run scripts/scan.sh first)"
fi

if [ -f .drift/archive.json ]; then
  if ! jq -e '.families' .drift/archive.json >/dev/null; then
    echo "FAIL .drift/archive.json missing .families"
    errs=$((errs+1))
  else
    # every archived_path must exist on disk
    while IFS= read -r p; do
      if [ -n "$p" ] && [ ! -f "$p" ]; then
        echo "FAIL archived path missing on disk: $p"
        errs=$((errs+1))
      fi
    done < <(jq -r '.families | to_entries[].value.entries[].archived_path' .drift/archive.json)
    echo "OK   .drift/archive.json entries resolve to files"

    # every canonical (if set) must exist on disk
    while IFS= read -r c; do
      if [ -n "$c" ] && [ "$c" != "null" ] && [ ! -f "$c" ]; then
        echo "FAIL canonical path missing on disk: $c"
        errs=$((errs+1))
      fi
    done < <(jq -r '.families | to_entries[].value.canonical // empty' .drift/archive.json)
    echo "OK   .drift/archive.json canonical paths resolve"
  fi
fi

if [ -f archive/INDEX.md ] && [ ! -f .drift/archive.json ]; then
  echo "FAIL archive/INDEX.md exists but .drift/archive.json does not"
  errs=$((errs+1))
fi

if [ "$errs" -gt 0 ]; then
  echo "drift-detector check: $errs failure(s)"
  exit 1
fi
echo "drift-detector check: pass"
