#!/usr/bin/env bash
# drift-detector/scripts/scan.sh
# Deterministic UI-drift scan with stack adapters.
# Auto-detects stack (tsx, swift, or both) and applies per-stack defaults.
# Writes <repo>/.drift/scan.json.
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: scan.sh <repo-path> [--scope <subpath>] [--stack auto|tsx|swift]
                           [--tailwind-config <path>] [--token-source <path>]
                           [--output <path>] [--all]

Per-stack defaults:
  tsx    scope = first of {src, app, components, pages} that exists
  swift  scope = first of {Sources, App, <repo>/<repo>} containing .swift files

--output  repo-relative or absolute output path (default: .drift/scan.json)
--token-source  repo-relative token source file to exclude from violation findings
                (repeatable; Swift token files are auto-detected)
--all     bypass per-stack defaults and scan the whole repo (noisy).
Requires: jq, rg. Optional: node+npx for jscpd / knip.
EOF
  exit 2
}

[ $# -ge 1 ] || usage
REPO="$1"; shift
USER_SCOPE=""
STACK="auto"
TW_CONFIG=""
OUT_FILE=".drift/scan.json"
TOKEN_SOURCES=()
SCAN_ALL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --scope) USER_SCOPE="$2"; shift 2 ;;
    --stack) STACK="$2"; shift 2 ;;
    --tailwind-config) TW_CONFIG="$2"; shift 2 ;;
    --token-source) TOKEN_SOURCES+=("$2"); shift 2 ;;
    --output) OUT_FILE="$2"; shift 2 ;;
    --all) SCAN_ALL=1; shift ;;
    -h|--help) usage ;;
    *) echo "unknown arg: $1" >&2; usage ;;
  esac
done

[ -d "$REPO" ] || { echo "not a directory: $REPO" >&2; exit 1; }
command -v jq >/dev/null || { echo "need jq" >&2; exit 1; }
command -v rg >/dev/null || { echo "need ripgrep (rg)" >&2; exit 1; }

cd "$REPO"
mkdir -p .drift
mkdir -p "$(dirname "$OUT_FILE")"
REPO_LABEL="$(basename "$PWD")"
case "$OUT_FILE" in
  /*) OUT_DISPLAY="$OUT_FILE" ;;
  *) OUT_DISPLAY="$REPO/$OUT_FILE" ;;
esac

detect_swift_token_sources() {
  find . -type f \( \
      -name '*Colors.swift' -o \
      -name '*Typography.swift' -o \
      -name '*DesignTokens.swift' -o \
      -name '*Theme.swift' \
    \) \
    -not -path '*/.build/*' \
    -not -path '*/DerivedData*/*' \
    -not -path '*/Pods/*' \
    2>/dev/null \
    | sed 's#^\./##'
}

mapfile -t AUTO_SWIFT_TOKEN_SOURCES < <(detect_swift_token_sources)
TOKEN_SOURCES+=("${AUTO_SWIFT_TOKEN_SOURCES[@]}")
mapfile -t TOKEN_SOURCES_UNIQUE < <(
  printf '%s\n' "${TOKEN_SOURCES[@]}" \
    | sed 's#^\./##' \
    | awk 'NF && !seen[$0]++ { print }'
)

token_sources_json() {
  if [ ${#TOKEN_SOURCES_UNIQUE[@]} -eq 0 ]; then
    echo "[]"
  else
    printf '%s\n' "${TOKEN_SOURCES_UNIQUE[@]}" \
      | awk '{ print $0; print "./" $0 }' \
      | jq -R . \
      | jq -s .
  fi
}

TOKEN_SOURCES_JSON="$(token_sources_json)"

# ---------- stack detection ----------
detect_stacks() {
  local stacks=()
  if [ -f package.json ] || ls tsconfig*.json >/dev/null 2>&1 || \
     compgen -G "**/*.tsx" >/dev/null 2>&1 || \
     find . -maxdepth 4 -name '*.tsx' -not -path '*/node_modules/*' -not -path '*/.next/*' -not -path '*/dist/*' 2>/dev/null | head -1 | grep -q .; then
    stacks+=("tsx")
  fi
  if ls *.xcodeproj >/dev/null 2>&1 || ls */Package.swift >/dev/null 2>&1 || [ -f Package.swift ] || \
     find . -maxdepth 4 -name '*.swift' -not -path '*/.build/*' -not -path '*/Pods/*' -not -path '*/DerivedData*/*' 2>/dev/null | head -1 | grep -q .; then
    stacks+=("swift")
  fi
  printf '%s\n' "${stacks[@]}"
}

if [ "$STACK" = "auto" ]; then
  mapfile -t DETECTED < <(detect_stacks)
  [ ${#DETECTED[@]} -gt 0 ] || { echo "no supported stack detected in $REPO" >&2; exit 1; }
else
  DETECTED=("$STACK")
fi

# ---------- default scope selection per stack ----------
default_scope_tsx() {
  # Collect scopes that actually contain tsx/jsx (not empty placeholders).
  local d scopes=()
  for d in src app components pages; do
    [ -d "$d" ] || continue
    find "$d" -maxdepth 6 -type f \( -name '*.tsx' -o -name '*.jsx' -o -name '*.ts' \) \
      -not -path '*/node_modules/*' -not -path '*/.next/*' -not -path '*/dist/*' \
      2>/dev/null | head -1 | grep -q . && scopes+=("$d")
  done
  if [ ${#scopes[@]} -eq 0 ]; then echo "."; else
    # Space-separated: rg accepts multiple paths positionally via eval
    printf '%s\n' "${scopes[@]}" | paste -sd' ' -
  fi
}

default_scope_swift() {
  local d repo_name scopes=()
  repo_name="$(basename "$PWD")"
  for d in Sources App "$repo_name"/"$repo_name" "$repo_name"; do
    [ -d "$d" ] || continue
    find "$d" -maxdepth 6 -name '*.swift' \
      -not -path '*/.build/*' -not -path '*/Pods/*' -not -path '*/DerivedData*/*' \
      2>/dev/null | head -1 | grep -q . && { scopes+=("$d"); break; }
  done
  if [ ${#scopes[@]} -eq 0 ]; then echo "."; else printf '%s\n' "${scopes[@]}" | paste -sd' ' -; fi
}

# ---------- adapters ----------
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

emit_matches() {
  # $1 = output jsonl file, $2+ = rg args
  local out="$1"; shift
  rg -n --no-heading --json "$@" 2>/dev/null \
    | jq -c 'select(.type=="match") | {
        file: .data.path.text,
        line: .data.line_number,
        matches: [.data.submatches[]?.match.text],
        value: .data.lines.text | gsub("^\\s+|\\s+$"; "")
      }' > "$out" || true
}

filter_matches() {
  # $1 = input/output jsonl file, $2 = jq select/filter expression.
  local file="$1"; shift
  local expr="$1"
  local filtered="$tmp/$(basename "$file").filtered"
  [ -s "$file" ] || return 0
  jq -c "$expr" "$file" > "$filtered"
  mv "$filtered" "$file"
}

filter_token_sources() {
  local file="$1"
  local filtered="$tmp/$(basename "$file").token-filtered"
  [ -s "$file" ] || return 0
  jq -c --argjson token_sources "$TOKEN_SOURCES_JSON" \
    'select((.file as $f | $token_sources | index($f)) | not)' \
    "$file" > "$filtered"
  mv "$filtered" "$file"
}

jsonl_to_array_file() {
  local src="$1"
  local dst="$2"
  if [ -s "$src" ]; then
    jq -cs '.' < "$src" > "$dst"
  else
    echo "[]" > "$dst"
  fi
}

ensure_json_file_or_empty() {
  # Optional tool output must not corrupt scan.json when the tool prints logs/errors.
  local file="$1"
  local fallback="$2"
  if [ ! -s "$file" ] || ! jq -e . "$file" >/dev/null 2>&1; then
    printf '%s\n' "$fallback" > "$file"
  fi
}

sanitize_clone_file() {
  # jscpd embeds full duplicated source fragments, which can leak unrelated
  # source text into generated scan artifacts. Keep locations and counts only.
  local file="$1"
  local sanitized="$tmp/$(basename "$file").sanitized"
  ensure_json_file_or_empty "$file" '{"statistics":{"total":{"clones":0}},"duplicates":[]}'
  jq 'if (.duplicates | type) == "array" then .duplicates |= map(del(.fragment)) else . end' \
    "$file" > "$sanitized"
  mv "$sanitized" "$file"
}

scan_tsx() {
  local -a scope=("$@")
  # tailwind arbitrary values
  emit_matches "$tmp/tsx_tailwind_arbitrary.jsonl" \
    -g '*.{ts,tsx,js,jsx,html,vue,svelte,astro}' \
    -e '\b(?:[a-z-]+)-\[[^\]]+\]' \
    "${scope[@]}"
  # Token references such as bg-[var(--brand)] are already design-token usage,
  # not arbitrary literal drift.
  filter_matches "$tmp/tsx_tailwind_arbitrary.jsonl" \
    '.matches = [.matches[] | select((test("\\[[^\\]]*var\\(--")) | not)] | select(.matches | length > 0)'
  filter_token_sources "$tmp/tsx_tailwind_arbitrary.jsonl"
  # raw color literals
  emit_matches "$tmp/tsx_raw_color_literals.jsonl" \
    -g '*.{ts,tsx,js,jsx,css,scss,vue,svelte,astro}' \
    -e '#[0-9a-fA-F]{3,8}\b' \
    -e 'rgba?\([^)]+\)' \
    -e 'hsla?\([^)]+\)' \
    "${scope[@]}"
  # CSS custom property color functions are token reads, not raw color values.
  filter_matches "$tmp/tsx_raw_color_literals.jsonl" \
    '.matches = [.matches[] | select((test("\\b(?:rgb|rgba|hsl|hsla)\\(\\s*var\\("; "i")) | not)] | select(.matches | length > 0)'
  filter_token_sources "$tmp/tsx_raw_color_literals.jsonl"
  # off-scale spacing (px values in declarations)
  emit_matches "$tmp/tsx_off_scale_spacing.jsonl" \
    -g '*.{ts,tsx,js,jsx,css,scss,vue,svelte,astro}' \
    -e '\b(margin|padding|gap|top|left|right|bottom|width|height)(-[a-z]+)?:\s*-?\d+(\.\d+)?px' \
    "${scope[@]}"
  filter_token_sources "$tmp/tsx_off_scale_spacing.jsonl"
  # off-scale typography
  emit_matches "$tmp/tsx_off_scale_typography.jsonl" \
    -g '*.{ts,tsx,js,jsx,css,scss,vue,svelte,astro}' \
    -e '\bfont-size:\s*\d' \
    -e '\bfont-weight:\s*\d' \
    -e '\bline-height:\s*\d' \
    "${scope[@]}"
  filter_token_sources "$tmp/tsx_off_scale_typography.jsonl"
  # inline styles
  emit_matches "$tmp/tsx_inline_styles.jsonl" \
    -g '*.{tsx,jsx,vue,svelte,astro}' \
    -e 'style=\{\{' \
    "${scope[@]}"
  filter_token_sources "$tmp/tsx_inline_styles.jsonl"
  # className soup: 12+ whitespace-separated tokens in a className string
  emit_matches "$tmp/tsx_classname_soup.jsonl" \
    -g '*.{tsx,jsx,vue,svelte,astro}' \
    -e 'className=("|\x27|\x60)(?:[^"\x27\x60]*\s){12,}[^"\x27\x60]*("|\x27|\x60)' \
    "${scope[@]}"
  filter_token_sources "$tmp/tsx_classname_soup.jsonl"
  # jscpd
  echo '{"statistics":{"total":{"clones":0}},"duplicates":[]}' > "$tmp/tsx_clone_clusters.json"
  if command -v npx >/dev/null 2>&1; then
    npx --yes jscpd@3 "${scope[@]}" \
      --reporters json \
      --output "$tmp/jscpd_tsx" \
      --min-lines 8 --min-tokens 60 \
      --pattern '**/*.{ts,tsx,jsx,vue,svelte,astro}' \
      --ignore '**/node_modules/**,**/dist/**,**/.next/**,**/build/**' \
      >/dev/null 2>&1 || true
    [ -f "$tmp/jscpd_tsx/jscpd-report.json" ] && cp "$tmp/jscpd_tsx/jscpd-report.json" "$tmp/tsx_clone_clusters.json" || true
  fi
  # knip orphans
  echo '{"files":[],"exports":[]}' > "$tmp/tsx_orphan_primitives.json"
  if command -v npx >/dev/null 2>&1 && [ -f package.json ]; then
    npx --yes knip --reporter json > "$tmp/knip.json" 2>/dev/null || true
    ensure_json_file_or_empty "$tmp/knip.json" '{"files":[],"exports":[]}'
    cp "$tmp/knip.json" "$tmp/tsx_orphan_primitives.json"
  fi
}

scan_swift() {
  local -a scope=("$@")
  # arbitrary values in SwiftUI modifiers: .padding(12), .frame(width: 237), .font(.system(size: 14))
  emit_matches "$tmp/swift_arbitrary_modifiers.jsonl" \
    -g '*.swift' \
    -e '\.padding\(\s*-?\d' \
    -e '\.frame\([^)]*(width|height|minWidth|maxWidth|minHeight|maxHeight)\s*:\s*-?\d' \
    -e '\.font\(\s*\.system\(\s*size\s*:\s*-?\d' \
    -e '\.offset\(\s*[xy]?:?\s*-?\d' \
    -e '\.spacing\(\s*-?\d' \
    "${scope[@]}"
  filter_token_sources "$tmp/swift_arbitrary_modifiers.jsonl"
  # raw color literals: #hex, Color(red:green:blue:), UIColor(red:...), Color(hex:)
  emit_matches "$tmp/swift_raw_color_literals.jsonl" \
    -g '*.swift' \
    -e '#[0-9a-fA-F]{6,8}\b' \
    -e '\bColor\(\s*red\s*:' \
    -e '\bUIColor\(\s*red\s*:' \
    -e '\bColor\(\s*hex\s*:' \
    -e '\bColor\(\s*white\s*:\s*\d' \
    "${scope[@]}"
  filter_token_sources "$tmp/swift_raw_color_literals.jsonl"
  # off-scale typography (raw font sizes outside .font(.body) / .largeTitle etc.)
  emit_matches "$tmp/swift_off_scale_typography.jsonl" \
    -g '*.swift' \
    -e '\.font\(\s*\.system\(\s*size\s*:\s*-?\d' \
    -e '\bFont\.system\(\s*size\s*:\s*-?\d' \
    "${scope[@]}"
  filter_token_sources "$tmp/swift_off_scale_typography.jsonl"
  # "inline styles" analog: long chained modifier runs on a single View — proxy: 6+ dots
  emit_matches "$tmp/swift_modifier_soup.jsonl" \
    -g '*.swift' \
    -e '(?:\.[a-zA-Z]+\([^)]*\)\s*){6,}' \
    "${scope[@]}"
  filter_token_sources "$tmp/swift_modifier_soup.jsonl"
  # jscpd for swift
  echo '{"statistics":{"total":{"clones":0}},"duplicates":[]}' > "$tmp/swift_clone_clusters.json"
  if command -v npx >/dev/null 2>&1; then
    npx --yes jscpd@3 "${scope[@]}" \
      --reporters json \
      --output "$tmp/jscpd_swift" \
      --min-lines 8 --min-tokens 50 \
      --format swift \
      --pattern '**/*.swift' \
      --ignore '**/.build/**,**/Pods/**,**/DerivedData*/**,**/Preview Content/**' \
      >/dev/null 2>&1 || true
    [ -f "$tmp/jscpd_swift/jscpd-report.json" ] && cp "$tmp/jscpd_swift/jscpd-report.json" "$tmp/swift_clone_clusters.json" || true
  fi
}

# ---------- resolve scope + run adapters ----------
if [ -z "$TW_CONFIG" ]; then
  TW_CONFIG="$(ls tailwind.config.{js,ts,cjs,mjs} 2>/dev/null | head -1 || true)"
fi

TSX_SCOPE=""
SWIFT_SCOPE=""

for s in "${DETECTED[@]}"; do
  case "$s" in
    tsx)
      if [ -n "$USER_SCOPE" ]; then TSX_SCOPE="$USER_SCOPE"
      elif [ "$SCAN_ALL" = "1" ]; then TSX_SCOPE="."
      else TSX_SCOPE="$(default_scope_tsx)"; fi
      echo "scan[tsx]   scope=$TSX_SCOPE"
      # shellcheck disable=SC2086
      read -ra _tsx_scope <<<"$TSX_SCOPE"
      scan_tsx "${_tsx_scope[@]}"
      ;;
    swift)
      if [ -n "$USER_SCOPE" ]; then SWIFT_SCOPE="$USER_SCOPE"
      elif [ "$SCAN_ALL" = "1" ]; then SWIFT_SCOPE="."
      else SWIFT_SCOPE="$(default_scope_swift)"; fi
      echo "scan[swift] scope=$SWIFT_SCOPE"
      read -ra _swift_scope <<<"$SWIFT_SCOPE"
      scan_swift "${_swift_scope[@]}"
      ;;
  esac
done

# ---------- aggregate ----------
empty_jscpd() { echo '{"statistics":{"total":{"clones":0}},"duplicates":[]}'; }

# tsx defaults
TSX_TW_FILE="$tmp/tsx_tailwind_arbitrary.array.json"; jsonl_to_array_file "$tmp/tsx_tailwind_arbitrary.jsonl" "$TSX_TW_FILE"
TSX_COL_FILE="$tmp/tsx_raw_color_literals.array.json"; jsonl_to_array_file "$tmp/tsx_raw_color_literals.jsonl" "$TSX_COL_FILE"
TSX_SPA_FILE="$tmp/tsx_off_scale_spacing.array.json"; jsonl_to_array_file "$tmp/tsx_off_scale_spacing.jsonl" "$TSX_SPA_FILE"
TSX_TYP_FILE="$tmp/tsx_off_scale_typography.array.json"; jsonl_to_array_file "$tmp/tsx_off_scale_typography.jsonl" "$TSX_TYP_FILE"
TSX_INL_FILE="$tmp/tsx_inline_styles.array.json"; jsonl_to_array_file "$tmp/tsx_inline_styles.jsonl" "$TSX_INL_FILE"
TSX_SOUP_FILE="$tmp/tsx_classname_soup.array.json"; jsonl_to_array_file "$tmp/tsx_classname_soup.jsonl" "$TSX_SOUP_FILE"
TSX_CLONE_FILE="$tmp/tsx_clone_clusters.json"
[ -f "$TSX_CLONE_FILE" ] || { TSX_CLONE_FILE="$tmp/_empty_jscpd_tsx.json"; empty_jscpd > "$TSX_CLONE_FILE"; }
sanitize_clone_file "$TSX_CLONE_FILE"
TSX_ORPH_FILE="$tmp/tsx_orphan_primitives.json"
[ -f "$TSX_ORPH_FILE" ] || { TSX_ORPH_FILE="$tmp/_empty_knip.json"; echo '{"files":[],"exports":[]}' > "$TSX_ORPH_FILE"; }
ensure_json_file_or_empty "$TSX_ORPH_FILE" '{"files":[],"exports":[]}'

# swift defaults
SW_ARB_FILE="$tmp/swift_arbitrary_modifiers.array.json"; jsonl_to_array_file "$tmp/swift_arbitrary_modifiers.jsonl" "$SW_ARB_FILE"
SW_COL_FILE="$tmp/swift_raw_color_literals.array.json"; jsonl_to_array_file "$tmp/swift_raw_color_literals.jsonl" "$SW_COL_FILE"
SW_TYP_FILE="$tmp/swift_off_scale_typography.array.json"; jsonl_to_array_file "$tmp/swift_off_scale_typography.jsonl" "$SW_TYP_FILE"
SW_SOUP_FILE="$tmp/swift_modifier_soup.array.json"; jsonl_to_array_file "$tmp/swift_modifier_soup.jsonl" "$SW_SOUP_FILE"
SW_CLONE_FILE="$tmp/swift_clone_clusters.json"
[ -f "$SW_CLONE_FILE" ] || { SW_CLONE_FILE="$tmp/_empty_jscpd_sw.json"; empty_jscpd > "$SW_CLONE_FILE"; }
sanitize_clone_file "$SW_CLONE_FILE"

jq -n \
  --arg repo "$REPO_LABEL" \
  --arg date "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg tw_config "$TW_CONFIG" \
  --arg tsx_scope "$TSX_SCOPE" \
  --arg swift_scope "$SWIFT_SCOPE" \
  --argjson token_sources "$(printf '%s\n' "${TOKEN_SOURCES_UNIQUE[@]}" | jq -R . | jq -s .)" \
  --argjson stacks "$(printf '%s\n' "${DETECTED[@]}" | jq -R . | jq -s .)" \
  --slurpfile tsx_tw "$TSX_TW_FILE" \
  --slurpfile tsx_col "$TSX_COL_FILE" \
  --slurpfile tsx_spa "$TSX_SPA_FILE" \
  --slurpfile tsx_typ "$TSX_TYP_FILE" \
  --slurpfile tsx_inl "$TSX_INL_FILE" \
  --slurpfile tsx_soup "$TSX_SOUP_FILE" \
  --slurpfile tsx_clone "$TSX_CLONE_FILE" \
  --slurpfile tsx_orph "$TSX_ORPH_FILE" \
  --slurpfile sw_arb "$SW_ARB_FILE" \
  --slurpfile sw_col "$SW_COL_FILE" \
  --slurpfile sw_typ "$SW_TYP_FILE" \
  --slurpfile sw_soup "$SW_SOUP_FILE" \
  --slurpfile sw_clone "$SW_CLONE_FILE" \
  '{
    meta: {
      repo: $repo,
      stacks: $stacks,
      tsx_scope: $tsx_scope,
      swift_scope: $swift_scope,
      tailwind_config: $tw_config,
      token_sources: $token_sources,
      scanned_at: $date
    },
    findings: {
      tsx: {
        tailwind_arbitrary: $tsx_tw[0],
        raw_color_literals: $tsx_col[0],
        off_scale_spacing: $tsx_spa[0],
        off_scale_typography: $tsx_typ[0],
        inline_styles: $tsx_inl[0],
        classname_soup: $tsx_soup[0],
        clone_clusters: $tsx_clone[0],
        orphan_primitives: $tsx_orph[0]
      },
      swift: {
        arbitrary_modifiers: $sw_arb[0],
        raw_color_literals: $sw_col[0],
        off_scale_typography: $sw_typ[0],
        modifier_soup: $sw_soup[0],
        clone_clusters: $sw_clone[0]
      }
    },
    summary: {
      tsx: {
        tailwind_arbitrary: ($tsx_tw[0] | length),
        raw_color_literals: ($tsx_col[0] | length),
        off_scale_spacing: ($tsx_spa[0] | length),
        off_scale_typography: ($tsx_typ[0] | length),
        inline_styles: ($tsx_inl[0] | length),
        classname_soup: ($tsx_soup[0] | length),
        clone_clusters: ($tsx_clone[0].duplicates | length? // 0),
        orphan_primitives: (($tsx_orph[0].files | length? // 0) + ($tsx_orph[0].exports | length? // 0))
      },
      swift: {
        arbitrary_modifiers: ($sw_arb[0] | length),
        raw_color_literals: ($sw_col[0] | length),
        off_scale_typography: ($sw_typ[0] | length),
        modifier_soup: ($sw_soup[0] | length),
        clone_clusters: ($sw_clone[0].duplicates | length? // 0)
      }
    }
  }' > "$OUT_FILE"

jq '{stacks: .meta.stacks, summary: .summary}' "$OUT_FILE"
echo "wrote $OUT_DISPLAY"
