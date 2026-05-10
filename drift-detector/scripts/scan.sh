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
                           [--canonical-root <repo-rel-path>]

Per-stack defaults:
  tsx    scope = source roots from {src, app, components, pages, public},
           nested package/app roots, and top-level index.html
  swift  scope = first of {Sources, App, <repo>/<repo>} containing .swift files

--output  repo-relative or absolute output path (default: .drift/scan.json)
--token-source  repo-relative token source file to exclude from violation findings
                (repeatable; Swift token files are auto-detected)
--canonical-root  repo-relative folder whose named exports are the canonical UI
                primitives. Repeatable. Falls back to default conventions
                (src/components/ui, components/ui, app/components/ui) when omitted.
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
CANONICAL_ROOTS=()
SCAN_ALL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --scope) USER_SCOPE="$2"; shift 2 ;;
    --stack) STACK="$2"; shift 2 ;;
    --tailwind-config) TW_CONFIG="$2"; shift 2 ;;
    --token-source) TOKEN_SOURCES+=("$2"); shift 2 ;;
    --canonical-root) CANONICAL_ROOTS+=("$2"); shift 2 ;;
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
mkdir -p "$(dirname "$OUT_FILE")"
REPO_LABEL="$(basename "$PWD")"
case "$OUT_FILE" in
  /*) OUT_DISPLAY="$OUT_FILE" ;;
  *) OUT_DISPLAY="$REPO/$OUT_FILE" ;;
esac

COMMON_RG_EXCLUDES=(
  -g '!node_modules/**'
  -g '!**/node_modules/**'
  -g '!dist/**'
  -g '!**/dist/**'
  -g '!dist-ssr/**'
  -g '!**/dist-ssr/**'
  -g '!build/**'
  -g '!**/build/**'
  -g '!coverage/**'
  -g '!**/coverage/**'
  -g '!.next/**'
  -g '!**/.next/**'
  -g '!.nuxt/**'
  -g '!**/.nuxt/**'
  -g '!storybook-static/**'
  -g '!**/storybook-static/**'
  -g '!archive/**'
  -g '!**/archive/**'
  -g '!.drift/**'
  -g '!**/.drift/**'
)

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

token_sources_meta_json() {
  if [ ${#TOKEN_SOURCES_UNIQUE[@]} -eq 0 ]; then
    echo "[]"
  else
    printf '%s\n' "${TOKEN_SOURCES_UNIQUE[@]}" | jq -R . | jq -s .
  fi
}

TOKEN_SOURCES_JSON="$(token_sources_json)"

# ---------- .driftignore loading ----------
# Repo-local ignore file. Each non-empty, non-comment line is an rg glob
# pattern. Prepended with `!` and passed as a -g exclude to every rg call
# via EXTRA_RG_ARGS. Lets consumers quiet per-repo false positives (e.g.
# gitignored scratch files rg's -g globs would otherwise re-include).
EXTRA_RG_ARGS=("${COMMON_RG_EXCLUDES[@]}")
DRIFTIGNORE_PATTERNS=()
if [ -f .driftignore ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    # strip comments + trim
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    line="${line#./}"
    [ -z "$line" ] && continue
    DRIFTIGNORE_PATTERNS+=("$line")
    EXTRA_RG_ARGS+=(-g "!$line")
  done < .driftignore
fi

# ---------- stack detection ----------
detect_stacks() {
  local stacks=()
  if [ -f package.json ] || \
     ls tsconfig*.json >/dev/null 2>&1 || \
     ls vite.config.* astro.config.* svelte.config.* vue.config.* next.config.* >/dev/null 2>&1 || \
     [ -f index.html ] || \
     [ -n "$(find . -maxdepth 4 \
       \( -path '*/node_modules' -o -path '*/dist' -o -path '*/dist-ssr' -o -path '*/build' -o -path '*/coverage' -o -path '*/.next' -o -path '*/.nuxt' -o -path '*/storybook-static' -o -path '*/archive' -o -path '*/.drift' \) -prune -o \
       -type f \( -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.jsx' -o -name '*.vue' -o -name '*.svelte' -o -name '*.astro' -o -name '*.html' -o -name '*.css' -o -name '*.scss' \) \
       -print -quit 2>/dev/null)" ]; then
    stacks+=("tsx")
  fi
  if ls *.xcodeproj >/dev/null 2>&1 || ls */Package.swift >/dev/null 2>&1 || [ -f Package.swift ] || \
     [ -n "$(find . -maxdepth 4 -name '*.swift' -not -path '*/.build/*' -not -path '*/Pods/*' -not -path '*/DerivedData*/*' -print -quit 2>/dev/null)" ]; then
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
is_frontend_file() {
  case "$1" in
    *.ts|*.tsx|*.js|*.jsx|*.vue|*.svelte|*.astro|*.html|*.css|*.scss) return 0 ;;
    *) return 1 ;;
  esac
}

frontend_file_exists() {
  local root="$1"
  local maxdepth="${2:-8}"
  [ -e "$root" ] || return 1
  if [ -f "$root" ]; then
    is_frontend_file "$root"
    return $?
  fi
  [ -n "$(find "$root" -maxdepth "$maxdepth" \
      \( -path '*/node_modules' -o -path '*/dist' -o -path '*/dist-ssr' -o -path '*/build' -o -path '*/coverage' -o -path '*/.next' -o -path '*/.nuxt' -o -path '*/storybook-static' -o -path '*/archive' -o -path '*/.drift' \) -prune -o \
      -type f \( -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.jsx' -o -name '*.vue' -o -name '*.svelte' -o -name '*.astro' -o -name '*.html' -o -name '*.css' -o -name '*.scss' \) \
      -print -quit 2>/dev/null)" ]
}

normalize_scope_path() {
  local path="$1"
  path="${path#./}"
  path="${path%/}"
  [ -n "$path" ] && printf '%s\n' "$path"
}

add_scope() {
  local candidate selected keep=()
  candidate="$(normalize_scope_path "$1")"
  [ -n "$candidate" ] || return 0
  for selected in "${scopes[@]}"; do
    [ "$candidate" = "$selected" ] && return 0
    [[ "$candidate" == "$selected"/* ]] && return 0
  done
  for selected in "${scopes[@]}"; do
    if [[ "$selected" == "$candidate"/* ]]; then
      continue
    fi
    keep+=("$selected")
  done
  scopes=("${keep[@]}" "$candidate")
}

default_scope_tsx() {
  # Collect source scopes for generic web frontends: React/TSX, JS/JSX,
  # Vue/Svelte/Astro, plain HTML/CSS, Vite sub-apps, and monorepo packages.
  local d f dir root
  local -a scopes=()

  for d in src app components pages; do
    [ -d "$d" ] || continue
    frontend_file_exists "$d" 8 && add_scope "$d"
  done
  if [ -d public ] && frontend_file_exists public 4; then
    add_scope public
  fi
  [ -f index.html ] && add_scope index.html

  while IFS= read -r f; do
    dir="$(dirname "$f")"
    dir="${dir#./}"
    [ "$dir" = "." ] && continue
    for root in src app pages components; do
      [ -d "$dir/$root" ] || continue
      frontend_file_exists "$dir/$root" 8 && add_scope "$dir/$root"
    done
    if [ -f "$dir/index.html" ] && frontend_file_exists "$dir" 3; then
      add_scope "$dir"
    fi
  done < <(
    find . -maxdepth 5 \
      \( -path '*/node_modules' -o -path '*/dist' -o -path '*/dist-ssr' -o -path '*/build' -o -path '*/coverage' -o -path '*/.next' -o -path '*/.nuxt' -o -path '*/storybook-static' -o -path '*/archive' -o -path '*/.drift' \) -prune -o \
      -type f \( -name package.json -o -name 'vite.config.*' -o -name 'astro.config.*' -o -name 'svelte.config.*' -o -name 'vue.config.*' -o -name 'next.config.*' \) \
      -print 2>/dev/null
  )

  while IFS= read -r root; do
    root="${root#./}"
    frontend_file_exists "$root" 8 && add_scope "$root"
  done < <(
    find . -maxdepth 5 \
      \( -path '*/node_modules' -o -path '*/dist' -o -path '*/dist-ssr' -o -path '*/build' -o -path '*/coverage' -o -path '*/.next' -o -path '*/.nuxt' -o -path '*/storybook-static' -o -path '*/archive' -o -path '*/.drift' \) -prune -o \
      -type d \( -name src -o -name app -o -name pages -o -name components \) \
      -print 2>/dev/null
  )

  if [ ${#scopes[@]} -eq 0 ]; then echo "."; else
    # Space-separated: resolved into an array before passing to rg.
    printf '%s\n' "${scopes[@]}" | paste -sd' ' -
  fi
}

default_scope_swift() {
  local d repo_name scopes=()
  repo_name="$(basename "$PWD")"
  for d in Sources App "$repo_name"/"$repo_name" "$repo_name"; do
    [ -d "$d" ] || continue
    [ -n "$(find "$d" -maxdepth 6 -name '*.swift' \
      -not -path '*/.build/*' -not -path '*/Pods/*' -not -path '*/DerivedData*/*' \
      -print -quit 2>/dev/null)" ] && { scopes+=("$d"); break; }
  done
  if [ ${#scopes[@]} -eq 0 ]; then echo "."; else printf '%s\n' "${scopes[@]}" | paste -sd' ' -; fi
}

# ---------- adapters ----------
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

emit_matches() {
  # $1 = output jsonl file, $2+ = rg args
  local out="$1"; shift
  rg -n --no-heading --json "${EXTRA_RG_ARGS[@]}" "$@" 2>/dev/null \
    | jq -c 'select(.type=="match") | {
        file: .data.path.text,
        line: .data.line_number,
        matches: [.data.submatches[]?.match.text],
        value: .data.lines.text | gsub("^\\s+|\\s+$"; "")
      }' > "$out" || true
  filter_gitignored_matches "$out"
  filter_driftignored_matches "$out"
}

emit_tagged_matches() {
  # $1 = output jsonl file, $2 = key, $3 = value, $4+ = rg args.
  local out="$1"; shift
  local key="$1"; shift
  local value="$1"; shift
  local scratch="$tmp/$(basename "$out").${key}.${value}.jsonl"
  emit_matches "$scratch" "$@"
  [ -s "$scratch" ] || return 0
  jq -c --arg key "$key" --arg value "$value" '. + {($key): $value}' "$scratch" >> "$out"
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

filter_gitignored_matches() {
  local file="$1"
  local ignored_file="$tmp/$(basename "$file").gitignored"
  local ignored_json="$tmp/$(basename "$file").gitignored.json"
  local filtered="$tmp/$(basename "$file").gitignored.filtered"
  [ -s "$file" ] || return 0
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 0
  jq -r '.file' "$file" | sort -u | git check-ignore --stdin > "$ignored_file" 2>/dev/null || true
  [ -s "$ignored_file" ] || return 0
  jq -Rs 'split("\n") | map(select(length > 0))' "$ignored_file" > "$ignored_json"
  jq -c --slurpfile gitignored "$ignored_json" \
    'select((.file as $f | $gitignored[0] | index($f)) | not)' \
    "$file" > "$filtered"
  mv "$filtered" "$file"
}

filter_driftignored_matches() {
  local file="$1"
  local filtered="$tmp/$(basename "$file").driftignored.filtered"
  local path json ignored pattern
  [ -s "$file" ] || return 0
  [ ${#DRIFTIGNORE_PATTERNS[@]} -gt 0 ] || return 0
  : > "$filtered"
  while IFS= read -r json; do
    path="$(jq -r '.file' <<<"$json")"
    ignored=0
    for pattern in "${DRIFTIGNORE_PATTERNS[@]}"; do
      if [[ "$path" == $pattern ]]; then
        ignored=1
        break
      fi
    done
    [ "$ignored" = "1" ] || printf '%s\n' "$json" >> "$filtered"
  done < "$file"
  mv "$filtered" "$file"
}

prompt_content_lines_json() {
  local file="$1"
  local prompt_lines="$tmp/$(basename "$file").prompt-lines.tsv"
  [ -s "$file" ] || { echo "{}"; return 0; }
  rm -f "$prompt_lines"
  while IFS= read -r source_file; do
    local lines_csv
    lines_csv="$(
      awk '
        /(^|["'"'"'[:space:]])(image_prompt|video_prompt|keyPrompt)(["'"'"'[:space:]]*)[[:space:]]*:/ {
          print NR
          print NR + 1
        }
      ' "$source_file" \
        | awk '!seen[$0]++' \
        | paste -sd',' -
    )"
    [ -n "$lines_csv" ] || continue
    printf '%s\t%s\n' "$source_file" "$lines_csv" >> "$prompt_lines"
  done < <(jq -r '.file' "$file" | sort -u)

  [ -f "$prompt_lines" ] || { echo "{}"; return 0; }
  jq -Rn '
    reduce inputs as $line ({};
      ($line | split("\t")) as $parts
      | . + {
          ($parts[0]): (
            ($parts[1] // "")
            | split(",")
            | map(select(length > 0) | tonumber)
          )
        }
    )
  ' < "$prompt_lines"
}

filter_prompt_content_matches() {
  local file="$1"
  local filtered="$tmp/$(basename "$file").prompt.filtered"
  local prompt_lines_json
  [ -s "$file" ] || return 0
  prompt_lines_json="$(prompt_content_lines_json "$file")"
  [ "$prompt_lines_json" != "{}" ] || return 0
  jq -c --argjson prompt_lines "$prompt_lines_json" \
    'select((.line as $line | ($prompt_lines[.file] // []) | index($line)) | not)' \
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

discover_canonical_roots_tsx() {
  # Echo repo-relative canonical root directories or files, one per line.
  # Order: explicit --canonical-root flags first (also accept individual
  # canonical FILES, not just directories), then default convention folders.
  # Feature-local primitive roots should be passed explicitly or via overlay.
  # Auto-discovering every */components/<area>/index.ts barrel is too noisy:
  # feature modules often have barrels that would hide their own variants.
  local d
  {
    for d in "${CANONICAL_ROOTS[@]}"; do
      [ -n "$d" ] || continue
      if [ -d "$d" ] || [ -f "$d" ]; then
        printf '%s\n' "${d%/}"
      fi
    done
    for d in src/components/ui components/ui app/components/ui; do
      [ -d "$d" ] && printf '%s\n' "$d"
    done
  } | awk 'NF && !seen[$0]++ { print }'
}

tsx_canonical_roots_json() {
  discover_canonical_roots_tsx | jq -R . | jq -s .
}

extract_named_exports_tsx() {
  # $1 = canonical-root path (dir OR file). Echo "<file-rel-to-repo>\t<exported-name>" per line.
  # Picks up:
  #   export function Foo
  #   export const Foo
  #   export class Foo
  #   export { Foo, Bar as Baz } from './x'
  #   export { Foo } (re-exports without source)
  local root="$1"
  { rg -n --no-heading \
    -g '*.{ts,tsx,js,jsx}' \
    -e '^\s*export\s+(?:default\s+)?(?:async\s+)?function\s+([A-Z][A-Za-z0-9_]+)' \
    -e '^\s*export\s+(?:const|let|var)\s+([A-Z][A-Za-z0-9_]+)' \
    -e '^\s*export\s+class\s+([A-Z][A-Za-z0-9_]+)' \
    "$root" 2>/dev/null || true; } \
    | awk -F: '{
        path = $1
        sub(/^\.\//, "", path)
        n = index($0, ":")
        rest = substr($0, n + 1)
        n = index(rest, ":")
        line = substr(rest, n + 1)
        if (match(line, /(function|const|let|var|class)[[:space:]]+[A-Z][A-Za-z0-9_]+/)) {
          s = substr(line, RSTART, RLENGTH)
          sub(/^(function|const|let|var|class)[[:space:]]+/, "", s)
          print path "\t" s
        }
      }'

  # Re-exports: export { A, B as C } from "./x". Handles BOTH single-line
  # `export { Foo, Bar }` and multi-line `export {\n  Foo,\n  Bar,\n}` blocks
  # by using awk per-file to coalesce open/close braces. Per-file dispatch is
  # via rg -l so we only walk files that actually contain `export {`.
  { rg -lU --no-heading \
    -g '*.{ts,tsx,js,jsx}' \
    -e '^[[:space:]]*export[[:space:]]*\{' \
    "$root" 2>/dev/null || true; } \
    | while IFS= read -r file; do
        [ -n "$file" ] && [ -f "$file" ] || continue
        awk -v rel="${file#./}" '
          /^[[:space:]]*export[[:space:]]*\{/ { in_block=1; buf=""; }
          in_block {
            buf = buf " " $0
            if (index($0, "}") > 0) {
              in_block = 0
              s = buf
              sub(/.*\{/, "", s)
              sub(/\}.*/, "", s)
              n = split(s, items, /,/)
              for (i = 1; i <= n; i++) {
                item = items[i]
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", item)
                if (match(item, /[[:space:]]+as[[:space:]]+[A-Z][A-Za-z0-9_]+/)) {
                  alias = substr(item, RSTART, RLENGTH)
                  sub(/^[[:space:]]+as[[:space:]]+/, "", alias)
                  print rel "\t" alias
                } else if (match(item, /^[A-Z][A-Za-z0-9_]+$/)) {
                  print rel "\t" item
                }
              }
            }
          }
        ' "$file"
      done
}

canonical_family_for_export() {
  # Classify a canonical export into one or more UI families (newline-separated).
  # Most exports return a single family; "Widget"-prefixed primitives also emit
  # the implied family from their suffix (e.g. WidgetButton -> widget AND button)
  # so a file that imports WidgetButton clears BOTH the widget motif check and
  # the button motif check. "Widget" is treated as a generic primitive prefix —
  # domain prefixes like Table* keep single-family classification because their
  # prefix carries semantic meaning (TableSortButton is a table-family helper,
  # not a generic button).
  # Always candidate signals only; plan-writing still verifies source.
  local file="$1"
  local name="$2"
  local key
  key="$(printf '%s %s' "$file" "$name" | tr '[:upper:]' '[:lower:]')"
  local primary
  case "$key" in
    *widget*) primary="widget" ;;
    *table*|*column*|*sort*|*grid*) primary="table" ;;
    *card*|*panel*|*surface*) primary="card" ;;
    *input*|*textarea*|*select*|*field*|*label*|*switch*|*combobox*) primary="form-control" ;;
    *dropdown*|*menu*|*popover*|*command*) primary="dropdown" ;;
    *tab*) primary="tabs" ;;
    *pagination*|*pager*) primary="pagination" ;;
    *badge*|*chip*) primary="badge" ;;
    *avatar*) primary="avatar" ;;
    *dialog*|*modal*|*drawer*|*sheet*) primary="modal" ;;
    *button*|*toggle*) primary="button" ;;
    *filter*|*search*) primary="filter-bar" ;;
    *skeleton*|*loading*|*empty*|*error*) primary="state" ;;
    *) primary="unknown" ;;
  esac
  printf '%s\n' "$primary"
  # Secondary family for Widget-prefixed primitives, classified by stripped suffix.
  if [ "$primary" = "widget" ] && [[ "$name" =~ ^Widget ]]; then
    local suffix_name="${name#Widget}"
    local suffix_key
    suffix_key="$(printf '%s' "$suffix_name" | tr '[:upper:]' '[:lower:]')"
    local secondary
    case "$suffix_key" in
      *table*|*column*|*sort*|*grid*) secondary="table" ;;
      *card*|*panel*|*surface*) secondary="card" ;;
      *input*|*textarea*|*select*|*field*|*label*|*switch*|*combobox*) secondary="form-control" ;;
      *dropdown*|*menu*|*popover*|*command*) secondary="dropdown" ;;
      *tab*) secondary="tabs" ;;
      *pagination*|*pager*) secondary="pagination" ;;
      *badge*|*chip*) secondary="badge" ;;
      *avatar*) secondary="avatar" ;;
      *dialog*|*modal*|*drawer*|*sheet*) secondary="modal" ;;
      *button*|*toggle*) secondary="button" ;;
      *filter*|*search*) secondary="filter-bar" ;;
      *skeleton*|*loading*|*empty*|*error*) secondary="state" ;;
      *) secondary="" ;;
    esac
    [ -n "$secondary" ] && printf '%s\n' "$secondary"
  fi
}

scan_tsx_component_motifs() {
  # Broad semantic UI motifs. These are intentionally candidates, not verdicts:
  # they let the LLM see families even when token-level duplication misses them.
  # File-glob scope is restricted to JSX-capable extensions (.tsx, .jsx, .html,
  # .vue, .svelte, .astro). Pure .ts / .js files describe logic, not UI motifs;
  # matching them produces large numbers of false positives where the regex
  # hits identifiers, string literals, or JSDoc rather than actual JSX usage.
  local -a scope=("$@")
  local out="$tmp/tsx_component_motifs.jsonl"
  : > "$out"
  local jsx_glob='*.{tsx,jsx,html,vue,svelte,astro}'

  emit_tagged_matches "$out" family button \
    -g "$jsx_glob" \
    -e '<button\b' \
    -e '\bButton\b' \
    -e 'role=("|\x27)button' \
    "${scope[@]}"
  emit_tagged_matches "$out" family card \
    -g "$jsx_glob" \
    -e '\b(Card|CardHeader|CardContent|CardFooter|CardTitle|CardDescription)\b' \
    -e '\b(rounded-[^"\x27\x60]*\s+(border|shadow|bg-)|(border|shadow|bg-)[^"\x27\x60]*\s+rounded-)' \
    "${scope[@]}"
  emit_tagged_matches "$out" family form-control \
    -g "$jsx_glob" \
    -e '<(input|textarea|select)\b' \
    -e '\b(Input|Textarea|Select|Field|Label|Switch|Combobox)\b' \
    "${scope[@]}"
  emit_tagged_matches "$out" family dropdown \
    -g "$jsx_glob" \
    -e '\b(DropdownMenu|Dropdown|Popover|Command|Combobox|Menu)\b' \
    -e 'aria-haspopup=' \
    "${scope[@]}"
  emit_tagged_matches "$out" family table \
    -g "$jsx_glob" \
    -e '<table\b' \
    -e 'BillingTable\b' \
    -e 'DataTable\b' \
    -e '\bTable(Shell|HeadRow|Body|Row|Cell)\b' \
    "${scope[@]}"
  emit_tagged_matches "$out" family tabs \
    -g "$jsx_glob" \
    -e '\bTabs(List|Trigger|Content)?\b' \
    -e 'role=("|\x27)tab' \
    "${scope[@]}"
  emit_tagged_matches "$out" family pagination \
    -g "$jsx_glob" \
    -e '\b(Pagination|pageSize|nextPage|previousPage|canNextPage|canPreviousPage)\b' \
    -e 'aria-label=("|\x27)[^"\x27]*(pagination|next page|previous page)' \
    "${scope[@]}"
  emit_tagged_matches "$out" family badge \
    -g "$jsx_glob" \
    -e '\b(Badge|Chip)\b' \
    -e '\brounded-full\b[^"\x27\x60]*\btext-(xs|sm)\b' \
    "${scope[@]}"
  emit_tagged_matches "$out" family modal \
    -g "$jsx_glob" \
    -e '\b(Dialog|Modal|Drawer|Sheet)(Content|Header|Footer|Title|Description)?\b' \
    -e 'role=("|\x27)dialog' \
    "${scope[@]}"
  emit_tagged_matches "$out" family filter-bar \
    -g "$jsx_glob" \
    -e '\b(Filter|Search|Sort|Toolbar)\b' \
    -e 'aria-label=("|\x27)[^"\x27]*(filter|search|sort)' \
    "${scope[@]}"
  emit_tagged_matches "$out" family widget \
    -g "$jsx_glob" \
    -e '\bWidget[A-Z][A-Za-z0-9_]*\b' \
    -e '\b(FloatingActionDock|OrbitLoader)\b' \
    "${scope[@]}"

  filter_token_sources "$out"
}

scan_tsx_ui_guidelines() {
  # Direct checks for the highest-signal /ui Tailwind guidelines. Absence-style
  # rules are intentionally omitted because regex cannot prove them safely.
  local -a scope=("$@")
  local out="$tmp/tsx_ui_guideline_violations.jsonl"
  : > "$out"

  emit_tagged_matches "$out" rule_id inline_text_size \
    -g '*.{tsx,jsx,html,vue,svelte,astro}' \
    -e '<(span|a|strong|em|code)\b[^>]*\b(className|class)=("|\x27|\x60)[^"\x27\x60]*\b(text|leading)-' \
    "${scope[@]}"
  emit_tagged_matches "$out" rule_id redundant_display \
    -g '*.{tsx,jsx,html,vue,svelte,astro}' \
    -e '<(div|p|h[1-6])\b[^>]*\b(className|class)=("|\x27|\x60)[^"\x27\x60]*\bblock\b' \
    -e '<(span|a)\b[^>]*\b(className|class)=("|\x27|\x60)[^"\x27\x60]*\binline\b' \
    -e '<(button|input|select)\b[^>]*\b(className|class)=("|\x27|\x60)[^"\x27\x60]*\binline-block\b' \
    "${scope[@]}"
  emit_tagged_matches "$out" rule_id deprecated_tailwind \
    -g '*.{ts,tsx,js,jsx,css,scss,html,vue,svelte,astro}' \
    -e '\b(min-h-screen|bg-gradient-|flex-shrink-|flex-grow-|leading-(tight|snug|relaxed)|theme\()' \
    "${scope[@]}"
  emit_tagged_matches "$out" rule_id small_default_text_review \
    -g '*.{tsx,jsx,html,vue,svelte,astro}' \
    -e '\b(className|class)=("|\x27|\x60)[^"\x27\x60]*\btext-(xs|sm)\b' \
    "${scope[@]}"
  emit_tagged_matches "$out" rule_id heading_font_bold \
    -g '*.{tsx,jsx,html,vue,svelte,astro}' \
    -e '<h[1-6]\b[^>]*\b(className|class)=("|\x27|\x60)[^"\x27\x60]*\bfont-bold\b' \
    "${scope[@]}"
  emit_tagged_matches "$out" rule_id solid_divider_color \
    -g '*.{tsx,jsx,html,vue,svelte,astro}' \
    -e '\b(border|divide)-(gray|slate|zinc|neutral)-(200|300|400)\b' \
    "${scope[@]}"
  emit_tagged_matches "$out" rule_id table_heading_uppercase \
    -g '*.{tsx,jsx,html,vue,svelte,astro}' \
    -e '<th\b[^>]*\b(className|class)=("|\x27|\x60)[^"\x27\x60]*\buppercase\b' \
    "${scope[@]}"
  emit_tagged_matches "$out" rule_id table_vertical_divider \
    -g '*.{tsx,jsx,html,vue,svelte,astro}' \
    -e '\b(border-l|border-r|divide-x)\b' \
    "${scope[@]}"
  emit_tagged_matches "$out" rule_id button_text_base \
    -g '*.{tsx,jsx,html,vue,svelte,astro}' \
    -e '<button\b[^>]*\b(className|class)=("|\x27|\x60)[^"\x27\x60]*\btext-base\b' \
    -e '<Button\b[^>]*\bclassName=("|\x27|\x60)[^"\x27\x60]*\btext-base\b' \
    "${scope[@]}"
  emit_tagged_matches "$out" rule_id margin_layout_candidate \
    -g '*.{tsx,jsx,html,vue,svelte,astro}' \
    -e '\b(className|class)=("|\x27|\x60)[^"\x27\x60]*\bm[trblxy]-' \
    "${scope[@]}"

  filter_token_sources "$out"
}

scan_tsx_unused_canonical() {
  # Emits one JSONL record per (canonical family, suspect_file) pair.
  # Record shape:
  #   { file, family, canonical_root, canonical_file, missing_exports[], motif_signals[] }
  # Disable set -e inside this function — many sub-pipelines may exit non-zero
  # on no-match (rg, jq) and we treat those as valid empty results.
  set +e
  set +o pipefail
  local out="$tmp/tsx_unused_canonical.jsonl"
  : > "$out"

  mapfile -t roots < <(discover_canonical_roots_tsx)
  [ ${#roots[@]} -gt 0 ] || return 0

  # Build canonical export map: per root + family, collect exports separately.
  # Aggregation is per-family (NOT per-root): a suspect file clears the family
  # bypass if it references ANY canonical export from ANY root that owns that
  # family. This matches drift-detection intent — a file using any canonical
  # primitive for the family is not bypassing canonicals. The earlier per-root
  # semantics emitted parallel findings for every root when projects had
  # multiple canonical roots in the same family (e.g. ui/Button + WidgetButton).
  local exports_tsv="$tmp/tsx_canonical_exports.tsv"
  : > "$exports_tsv"
  local root export_file export_name family
  for root in "${roots[@]}"; do
    while IFS=$'\t' read -r export_file export_name; do
      [ -n "$export_file" ] && [ -n "$export_name" ] || continue
      # canonical_family_for_export may emit multiple families (one per line)
      while IFS= read -r family; do
        [ -n "$family" ] || continue
        [ "$family" = "unknown" ] && continue
        printf '%s\t%s\t%s\t%s\n' "$root" "$export_file" "$export_name" "$family" >> "$exports_tsv"
      done < <(canonical_family_for_export "$export_file" "$export_name")
    done < <(extract_named_exports_tsx "$root")
  done
  [ -s "$exports_tsv" ] || return 0

  local motif_pairs="$tmp/tsx_motif_pairs.tsv"
  if [ -s "$tmp/tsx_component_motifs.jsonl" ]; then
    jq -r '[.file, .family] | @tsv' "$tmp/tsx_component_motifs.jsonl" | sort -u > "$motif_pairs"
  else
    : > "$motif_pairs"
  fi
  [ -s "$motif_pairs" ] || return 0

  # Build canonical-root prefix list (so we can exclude files inside canonical roots)
  local roots_alt
  roots_alt=$(printf '%s\n' "${roots[@]}" | sed 's#/$##' | sed 's#[.[\*^$()+?{}|\\]#\\&#g' | paste -sd'|' -)

  local suspect suspect_family
  while IFS=$'\t' read -r suspect suspect_family; do
    # Skip files inside a canonical root
    if [[ "$suspect" =~ ^($roots_alt)(/|$) ]]; then continue; fi
    # Skip test/stories/spec files: their JSX usually lives inside vi.mock or
    # fixture render trees that intentionally bypass canonical primitives.
    # Treating them as bypass produces noise without surfacing real drift.
    case "$suspect" in
      *.test.tsx|*.test.jsx|*.test.ts|*.test.js) continue ;;
      *.stories.tsx|*.stories.jsx|*.stories.ts|*.stories.js) continue ;;
      *.spec.tsx|*.spec.jsx|*.spec.ts|*.spec.js) continue ;;
      */__tests__/*|*/__mocks__/*) continue ;;
    esac
    [ -f "$suspect" ] || continue
    # Capture motif signals once
    local motifs_json
    motifs_json=$(
      jq -c --arg file "$suspect" --arg family "$suspect_family" \
        'select(.file == $file and .family == $family) | {line, matches, value}' \
        "$tmp/tsx_component_motifs.jsonl" \
        | jq -cs '. // []'
    )
    [ -n "$motifs_json" ] || motifs_json="[]"

    # Aggregate canonical exports for this family across ALL roots.
    local family_exports
    family_exports=$(awk -F'\t' -v fam="$suspect_family" '$4==fam {print $3}' "$exports_tsv" | awk 'NF && !seen[$0]++')
    [ -n "$family_exports" ] || continue
    local family_alt
    family_alt=$(printf '%s\n' "$family_exports" | sed 's#[.[\*^$()+?{}|\\]#\\&#g' | paste -sd'|' -)
    [ -n "$family_alt" ] || continue
    if rg -q "(^|[^A-Za-z0-9_])($family_alt)([^A-Za-z0-9_]|$)" "$suspect" 2>/dev/null; then
      continue
    fi
    # Pick a representative canonical_root + canonical_file (first matching root).
    local rep_root rep_file
    rep_root=$(awk -F'\t' -v fam="$suspect_family" '$4==fam {print $1; exit}' "$exports_tsv")
    rep_file=$(awk -F'\t' -v fam="$suspect_family" -v r="$rep_root" '$1==r && $4==fam {print $2; exit}' "$exports_tsv")
    local missing_json
    missing_json=$(printf '%s\n' "$family_exports" | jq -R . | jq -s .)
    local rec
    rec=$(jq -nc \
      --arg suspect "$suspect" \
      --arg family "$suspect_family" \
      --arg root "$rep_root" \
      --arg canonical_file "$rep_file" \
      --argjson missing "$missing_json" \
      --argjson motifs "$motifs_json" \
      '{
        file: $suspect,
        family: $family,
        canonical_root: $root,
        canonical_file: $canonical_file,
        missing_exports: $missing,
        motif_signals: $motifs
      }')
    printf '%s\n' "$rec" >> "$out"
  done < "$motif_pairs"

  set -e
  set -o pipefail
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
  filter_matches "$tmp/tsx_tailwind_arbitrary.jsonl" \
    '.matches = [.matches[] | select((startswith("data-[") or startswith("group-data-[") or startswith("peer-data-[")) | not)] | select(.matches | length > 0)'
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
  filter_prompt_content_matches "$tmp/tsx_raw_color_literals.jsonl"
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
    -g '*.{tsx,jsx,html,vue,svelte,astro}' \
    -e 'style=\{\{' \
    -e 'style=("|\x27)[^"\x27]*[:;]' \
    "${scope[@]}"
  filter_token_sources "$tmp/tsx_inline_styles.jsonl"
  # class/className soup: 12+ whitespace-separated tokens in a class attribute string
  emit_matches "$tmp/tsx_classname_soup.jsonl" \
    -g '*.{tsx,jsx,html,vue,svelte,astro}' \
    -e '\b(className|class)=("|\x27|\x60)(?:[^"\x27\x60]*\s){12,}[^"\x27\x60]*("|\x27|\x60)' \
    "${scope[@]}"
  filter_token_sources "$tmp/tsx_classname_soup.jsonl"
  # semantic component-family motif candidates
  scan_tsx_component_motifs "${scope[@]}"
  # /ui guideline candidate violations
  scan_tsx_ui_guidelines "${scope[@]}"
  # jscpd
  echo '{"statistics":{"total":{"clones":0}},"duplicates":[]}' > "$tmp/tsx_clone_clusters.json"
  if command -v npx >/dev/null 2>&1; then
    npx --yes jscpd@3 "${scope[@]}" \
      --reporters json \
      --output "$tmp/jscpd_tsx" \
      --min-lines 8 --min-tokens 60 \
      --pattern '**/*.{ts,tsx,js,jsx,vue,svelte,astro,html,css,scss}' \
      --ignore '**/node_modules/**,**/dist/**,**/dist-ssr/**,**/.next/**,**/.nuxt/**,**/build/**,**/coverage/**,**/storybook-static/**,**/archive/**,**/.drift/**' \
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
      scan_tsx_unused_canonical "${_tsx_scope[@]}"
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
TSX_MOTIF_FILE="$tmp/tsx_component_motifs.array.json"; jsonl_to_array_file "$tmp/tsx_component_motifs.jsonl" "$TSX_MOTIF_FILE"
TSX_UI_GUIDE_FILE="$tmp/tsx_ui_guideline_violations.array.json"; jsonl_to_array_file "$tmp/tsx_ui_guideline_violations.jsonl" "$TSX_UI_GUIDE_FILE"
TSX_CLONE_FILE="$tmp/tsx_clone_clusters.json"
[ -f "$TSX_CLONE_FILE" ] || { TSX_CLONE_FILE="$tmp/_empty_jscpd_tsx.json"; empty_jscpd > "$TSX_CLONE_FILE"; }
sanitize_clone_file "$TSX_CLONE_FILE"
TSX_ORPH_FILE="$tmp/tsx_orphan_primitives.json"
[ -f "$TSX_ORPH_FILE" ] || { TSX_ORPH_FILE="$tmp/_empty_knip.json"; echo '{"files":[],"exports":[]}' > "$TSX_ORPH_FILE"; }
ensure_json_file_or_empty "$TSX_ORPH_FILE" '{"files":[],"exports":[]}'
TSX_UNCAN_FILE="$tmp/tsx_unused_canonical.array.json"; jsonl_to_array_file "$tmp/tsx_unused_canonical.jsonl" "$TSX_UNCAN_FILE"

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
  --argjson token_sources "$(token_sources_meta_json)" \
  --argjson tsx_canonical_roots "$(tsx_canonical_roots_json)" \
  --argjson stacks "$(printf '%s\n' "${DETECTED[@]}" | jq -R . | jq -s .)" \
  --slurpfile tsx_tw "$TSX_TW_FILE" \
  --slurpfile tsx_col "$TSX_COL_FILE" \
  --slurpfile tsx_spa "$TSX_SPA_FILE" \
  --slurpfile tsx_typ "$TSX_TYP_FILE" \
  --slurpfile tsx_inl "$TSX_INL_FILE" \
  --slurpfile tsx_soup "$TSX_SOUP_FILE" \
  --slurpfile tsx_motif "$TSX_MOTIF_FILE" \
  --slurpfile tsx_ui_guide "$TSX_UI_GUIDE_FILE" \
  --slurpfile tsx_clone "$TSX_CLONE_FILE" \
  --slurpfile tsx_orph "$TSX_ORPH_FILE" \
  --slurpfile tsx_uncan "$TSX_UNCAN_FILE" \
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
      tsx_canonical_roots: $tsx_canonical_roots,
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
        component_motifs: $tsx_motif[0],
        ui_guideline_violations: $tsx_ui_guide[0],
        clone_clusters: $tsx_clone[0],
        orphan_primitives: $tsx_orph[0],
        unused_canonical: $tsx_uncan[0]
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
        component_motifs: ($tsx_motif[0] | length),
        ui_guideline_violations: ($tsx_ui_guide[0] | length),
        clone_clusters: ($tsx_clone[0].duplicates | length? // 0),
        orphan_primitives: (($tsx_orph[0].files | length? // 0) + ($tsx_orph[0].exports | length? // 0)),
        unused_canonical: ($tsx_uncan[0] | length)
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
