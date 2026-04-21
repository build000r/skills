#!/usr/bin/env bash
# drift-detector/scripts/render_archive_index.sh
# Rebuild <repo>/archive/INDEX.md as a single page, numbered per family,
# with the current canonical component shown per family heading.
set -euo pipefail

[ $# -ge 1 ] || { echo "Usage: render_archive_index.sh <repo>" >&2; exit 2; }
REPO="$1"
cd "$REPO"

ARCHIVE_JSON=".drift/archive.json"
OUT="archive/INDEX.md"
mkdir -p archive

if [ ! -f "$ARCHIVE_JSON" ]; then
  cat > "$OUT" <<'EOF'
# Design Archive

_No archived variants yet._
EOF
  exit 0
fi

command -v jq >/dev/null || { echo "need jq" >&2; exit 1; }

{
  cat <<'EOF'
# Design Archive

> Numbered per family. The canonical component is listed in each family heading.
> To restore a variant: `cp archive/<family>/NN-* src/<target>` then rerun the drift plan.
> Do not hand-edit this file — rebuild via `scripts/render_archive_index.sh`.

EOF

  # sort families alphabetically for stable output
  FAMILIES=$(jq -r '.families | keys | .[]' "$ARCHIVE_JSON" | sort)
  for fam in $FAMILIES; do
    canonical=$(jq -r --arg f "$fam" '.families[$f].canonical // "_(unset)_"' "$ARCHIVE_JSON")
    echo ""
    echo "## ${fam} — canonical: \`${canonical}\`"
    echo ""
    echo "| #  | archived from | reason | archived   |"
    echo "|----|---------------|--------|------------|"
    jq -r --arg f "$fam" '
      .families[$f].entries
      | sort_by(.number)
      | .[]
      | "| \(.number | tostring | (if length < 2 then "0" + . else . end)) | `\(.from)` | \(.reason) | \(.date) |"
    ' "$ARCHIVE_JSON"
  done
} > "$OUT"

echo "wrote $REPO/$OUT"
