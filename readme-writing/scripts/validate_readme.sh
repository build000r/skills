#!/usr/bin/env bash
set -euo pipefail

# validate_readme.sh — structural checks for a README.md
# Usage: validate_readme.sh [path/to/README.md]

README="${1:-README.md}"
ERRORS=0
WARNS=0

if [[ ! -f "$README" ]]; then
  echo "FAIL: $README not found"
  exit 1
fi

fail() { echo "FAIL: $1"; ERRORS=$((ERRORS + 1)); }
warn() { echo "WARN: $1"; WARNS=$((WARNS + 1)); }
pass() { echo "  OK: $1"; }

echo "Validating: $README"
echo "---"

# Required sections (case-insensitive heading search)
for section in "TL;DR|The Problem|The Solution" "Quick Example|Quick Start" "Comparison|Alternatives" "Installation|Getting Started" "Troubleshooting" "Limitations" "Contributions|Contributing"; do
  if grep -qiE "^#{1,3} .*(${section})" "$README"; then
    pass "Section found: $section"
  else
    fail "Missing section matching: $section"
  fi
done

# Badge syntax check
if grep -qE '!\[.*\]\(https://img\.shields\.io' "$README"; then
  pass "Badges present"
else
  warn "No shields.io badges found"
fi

# Code blocks: check fences are balanced
OPEN=$(grep -c '```' "$README" || true)
if (( OPEN % 2 != 0 )); then
  fail "Unbalanced code fences (found $OPEN triple-backtick lines)"
else
  pass "Code fences balanced ($((OPEN / 2)) blocks)"
fi

# Contributions policy text (check for the key phrase)
if grep -q "don't take this the wrong way" "$README"; then
  pass "Contributions policy text present"
else
  warn "Contributions policy text not found (check if EXACT text is used)"
fi

# Internal links: check that [text](path) targets exist for relative paths
BROKEN=0
while IFS= read -r link; do
  # Extract relative path, skip URLs and anchors
  path=$(echo "$link" | sed -n 's/.*](\([^)]*\)).*/\1/p' | head -1)
  [[ -z "$path" ]] && continue
  [[ "$path" == http* ]] && continue
  [[ "$path" == \#* ]] && continue
  # Strip anchor from path
  filepath="${path%%#*}"
  # Resolve relative to README directory
  dir=$(dirname "$README")
  if [[ ! -e "$dir/$filepath" ]]; then
    fail "Broken internal link: $path"
    BROKEN=$((BROKEN + 1))
  fi
done < <(grep -oE '\[[^]]*\]\([^)]+\)' "$README" || true)
if (( BROKEN == 0 )); then
  pass "All internal links resolve"
fi

# Hero section: check for centered div or h1 near the top
if head -20 "$README" | grep -qiE '<div align="center">|^# '; then
  pass "Hero section detected"
else
  warn "No hero section in first 20 lines"
fi

# Summary
echo "---"
echo "Errors: $ERRORS | Warnings: $WARNS"
if (( ERRORS > 0 )); then
  exit 1
else
  exit 0
fi
