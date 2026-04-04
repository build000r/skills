#!/usr/bin/env bash
# audit_freshness.sh — Check a GitHub profile README for stale project references
#
# Usage: ./audit_freshness.sh <path-to-README.md> <repos-dir> [days-threshold]
#
# Extracts project references from the README, checks their last commit date
# in the local repos directory, and flags anything older than the threshold.

set -euo pipefail

README="${1:?Usage: audit_freshness.sh <README.md> <repos-dir> [days-threshold]}"
REPOS_DIR="${2:?Usage: audit_freshness.sh <README.md> <repos-dir> [days-threshold]}"
THRESHOLD="${3:-90}"

if [ ! -f "$README" ]; then
  echo "ERROR: README not found at $README" >&2
  exit 1
fi

if [ ! -d "$REPOS_DIR" ]; then
  echo "ERROR: Repos directory not found at $REPOS_DIR" >&2
  exit 1
fi

NOW=$(date +%s)
STALE=0
FRESH=0
MISSING=0

echo "=== Profile README Freshness Audit ==="
echo "README:    $README"
echo "Repos:     $REPOS_DIR"
echo "Threshold: ${THRESHOLD} days"
echo ""

# Extract likely repo/project references from the README
# Looks for: github.com/user/repo links, [text](url) markdown links, and
# words that match local directory names
extract_references() {
  # GitHub repo links
  grep -oP 'github\.com/[a-zA-Z0-9_-]+/\K[a-zA-Z0-9_-]+' "$README" 2>/dev/null || true
  # Markdown link text that matches a local repo
  for dir in "$REPOS_DIR"/*/; do
    repo=$(basename "$dir")
    if grep -qi "$repo" "$README" 2>/dev/null; then
      echo "$repo"
    fi
  done
}

references=$(extract_references | sort -u)

if [ -z "$references" ]; then
  echo "No project references found in README."
  exit 0
fi

echo "Projects referenced in README:"
echo "-------------------------------"

while IFS= read -r repo; do
  repo_path="$REPOS_DIR/$repo"
  if [ -d "$repo_path/.git" ]; then
    last_commit=$(git -C "$repo_path" log -1 --format="%ct" 2>/dev/null || echo "0")
    last_date=$(git -C "$repo_path" log -1 --format="%ci" 2>/dev/null | cut -d' ' -f1)
    days_ago=$(( (NOW - last_commit) / 86400 ))

    if [ "$days_ago" -gt "$THRESHOLD" ]; then
      echo "  STALE  $repo — last commit $last_date ($days_ago days ago)"
      STALE=$((STALE + 1))
    else
      echo "  FRESH  $repo — last commit $last_date ($days_ago days ago)"
      FRESH=$((FRESH + 1))
    fi
  else
    echo "  MISSING $repo — not found locally"
    MISSING=$((MISSING + 1))
  fi
done <<< "$references"

echo ""
echo "--- Summary ---"
echo "Fresh:   $FRESH"
echo "Stale:   $STALE (>${THRESHOLD} days)"
echo "Missing: $MISSING"

if [ "$STALE" -gt 0 ]; then
  echo ""
  echo "ACTION: Update or remove stale project references."
  exit 1
fi
