#!/usr/bin/env bash
# drift-detector/scripts/archive.sh
# Archive a variant file under <repo>/archive/<family>/NN-<basename>.
# Appends to <repo>/.drift/archive.json and re-renders archive/INDEX.md.
# Never invoked by the LLM directly on the filesystem — always through this script.
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: archive.sh <repo> <family> <source-file> --reason "<short description>" [--canonical <path>]

Moves <source-file> to <repo>/archive/<family>/NN-<basename> (next zero-padded number),
records metadata in <repo>/.drift/archive.json, rebuilds <repo>/archive/INDEX.md.
EOF
  exit 2
}

[ $# -ge 3 ] || usage
REPO="$1"; FAMILY="$2"; SOURCE="$3"; shift 3
REASON=""
CANONICAL=""
while [ $# -gt 0 ]; do
  case "$1" in
    --reason) REASON="$2"; shift 2 ;;
    --canonical) CANONICAL="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "unknown arg: $1" >&2; usage ;;
  esac
done

[ -d "$REPO" ] || { echo "repo not a directory: $REPO" >&2; exit 1; }
[ -n "$FAMILY" ] || { echo "family required" >&2; exit 1; }
[ -n "$REASON" ] || { echo "--reason required" >&2; exit 1; }
command -v jq >/dev/null || { echo "need jq" >&2; exit 1; }

cd "$REPO"
[ -f "$SOURCE" ] || { echo "source not found: $SOURCE" >&2; exit 1; }

mkdir -p "archive/$FAMILY" ".drift"
ARCHIVE_JSON=".drift/archive.json"
[ -f "$ARCHIVE_JSON" ] || echo '{"families":{}}' > "$ARCHIVE_JSON"

# next number in family
NEXT=$(jq -r --arg f "$FAMILY" '
  (.families[$f].entries // []) | map(.number) | (max // 0) + 1
' "$ARCHIVE_JSON")
NN=$(printf "%02d" "$NEXT")
BASE="$(basename "$SOURCE")"
DEST="archive/$FAMILY/${NN}-${BASE}"

SHA="$(git rev-parse --short HEAD 2>/dev/null || echo 'no-git')"
DATE="$(date -u +%Y-%m-%d)"

# Prefer git mv when inside a git worktree so history follows the file.
if [ "$SHA" != "no-git" ] && git ls-files --error-unmatch "$SOURCE" >/dev/null 2>&1; then
  git mv "$SOURCE" "$DEST"
  MOVE_METHOD="git-mv"
else
  cp "$SOURCE" "$DEST"
  MOVE_METHOD="cp-rm"
fi

jq --arg f "$FAMILY" \
   --argjson n "$NEXT" \
   --arg from "$SOURCE" \
   --arg dest "$DEST" \
   --arg reason "$REASON" \
   --arg canonical "$CANONICAL" \
   --arg date "$DATE" \
   --arg sha "$SHA" \
   --arg method "$MOVE_METHOD" \
   '
   .families[$f].canonical = (if $canonical == "" then (.families[$f].canonical // null) else $canonical end)
   | .families[$f].entries = ((.families[$f].entries // []) + [{
       number: $n,
       from: $from,
       archived_path: $dest,
       reason: $reason,
       date: $date,
       sha: $sha,
       move_method: $method
     }])
   ' "$ARCHIVE_JSON" > "$ARCHIVE_JSON.tmp"
mv "$ARCHIVE_JSON.tmp" "$ARCHIVE_JSON"

# For cp-rm path, the original still exists — remove it here. git mv already moved it.
if [ "$MOVE_METHOD" = "cp-rm" ] && [ -f "$SOURCE" ]; then
  rm "$SOURCE"
fi

# rebuild index
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
"$SCRIPT_DIR/render_archive_index.sh" "$REPO"

echo "archived $SOURCE -> $DEST (family=$FAMILY, #$NN)"
