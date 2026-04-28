#!/usr/bin/env bash
# Regression checks for scan.sh token filtering and large-result aggregation.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCAN="$SCRIPT_DIR/scan.sh"
CHECK="$SCRIPT_DIR/check.sh"

command -v jq >/dev/null || { echo "need jq" >&2; exit 2; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

assert_eq() {
  local expected="$1"
  local actual="$2"
  local label="$3"
  if [ "$expected" != "$actual" ]; then
    echo "FAIL $label: expected $expected, got $actual" >&2
    exit 1
  fi
  echo "OK   $label = $actual"
}

assert_ge() {
  local minimum="$1"
  local actual="$2"
  local label="$3"
  if [ "$actual" -lt "$minimum" ]; then
    echo "FAIL $label: expected >= $minimum, got $actual" >&2
    exit 1
  fi
  echo "OK   $label >= $minimum (got $actual)"
}

make_npx_stub() {
  local bin="$tmp/bin"
  mkdir -p "$bin"
  cat > "$bin/npx" <<'SH'
#!/usr/bin/env bash
exit 127
SH
  chmod +x "$bin/npx"
  printf '%s\n' "$bin"
}

scan_with_stubbed_npx() {
  local repo="$1"
  local out="$2"
  local stub_bin
  stub_bin="$(make_npx_stub)"
  PATH="$stub_bin:$PATH" "$SCAN" "$repo" --stack tsx --scope src > "$out"
  PATH="$stub_bin:$PATH" "$CHECK" "$repo" > "$out.check"
}

scan_default_scope_with_stubbed_npx() {
  local repo="$1"
  local out="$2"
  local stub_bin
  stub_bin="$(make_npx_stub)"
  PATH="$stub_bin:$PATH" "$SCAN" "$repo" --stack tsx > "$out"
  PATH="$stub_bin:$PATH" "$CHECK" "$repo" > "$out.check"
}

scan_auto_with_stubbed_npx() {
  local repo="$1"
  local out="$2"
  local stub_bin
  stub_bin="$(make_npx_stub)"
  PATH="$stub_bin:$PATH" "$SCAN" "$repo" > "$out"
  PATH="$stub_bin:$PATH" "$CHECK" "$repo" > "$out.check"
}

scan_custom_output_with_stubbed_npx() {
  local repo="$1"
  local out="$2"
  local scan_output="$3"
  local stub_bin
  stub_bin="$(make_npx_stub)"
  PATH="$stub_bin:$PATH" "$SCAN" "$repo" --stack tsx --scope src --output "$scan_output" > "$out"
}

scan_token_source_with_stubbed_npx() {
  local repo="$1"
  local out="$2"
  local scan_output="$3"
  local token_source="$4"
  local stub_bin
  stub_bin="$(make_npx_stub)"
  PATH="$stub_bin:$PATH" "$SCAN" "$repo" --stack tsx --scope src \
    --token-source "$token_source" --output "$scan_output" > "$out"
}

token_fixture="$tmp/token-filter-fixture"
mkdir -p "$token_fixture/src"
cat > "$token_fixture/src/App.tsx" <<'TSX'
export function App() {
  return (
    <>
      <div className="bg-[var(--brand)] text-[13px]" />
      <section className="text-[var(--type-scale)]" />
      <main style={{ backgroundColor: "hsl(var(--brand))", color: "#abcdef" }} />
      <aside style={{ borderColor: "rgb(var(--border-rgb))" }} />
    </>
  );
}
TSX

scan_with_stubbed_npx "$token_fixture" "$tmp/token.out"
assert_eq "1" "$(jq -r '.summary.tsx.tailwind_arbitrary' "$token_fixture/.drift/scan.json")" "mixed token tailwind line kept"
assert_eq "1" "$(jq -r '.summary.tsx.raw_color_literals' "$token_fixture/.drift/scan.json")" "mixed token color line kept"
assert_eq "1" "$(jq -r '.findings.tsx.tailwind_arbitrary[0].matches | length' "$token_fixture/.drift/scan.json")" "tailwind matches retained"

scan_custom_output_with_stubbed_npx "$token_fixture" "$tmp/token-custom.out" ".drift/custom-scan.json"
assert_eq "1" "$(jq -r '.summary.tsx.tailwind_arbitrary' "$token_fixture/.drift/custom-scan.json")" "custom output path"

cat > "$token_fixture/src/tokens.tsx" <<'TSX'
export const palette = {
  accent: "#123456",
};
TSX
scan_token_source_with_stubbed_npx "$token_fixture" "$tmp/token-source.out" ".drift/token-source-scan.json" "src/tokens.tsx"
assert_eq "1" "$(jq -r '.summary.tsx.raw_color_literals' "$token_fixture/.drift/token-source-scan.json")" "token source excluded"
assert_eq "src/tokens.tsx" "$(jq -r '.meta.token_sources[0]' "$token_fixture/.drift/token-source-scan.json")" "token source recorded"

variant_fixture="$tmp/data-variant-fixture"
mkdir -p "$variant_fixture/src"
cat > "$variant_fixture/src/App.tsx" <<'TSX'
export function App() {
  return (
    <div className="data-[state=open]:animate-in peer-data-[state=closed]:fade-out-0 text-[13px]" />
  );
}
TSX

scan_with_stubbed_npx "$variant_fixture" "$tmp/variant.out"
assert_eq "1" "$(jq -r '.summary.tsx.tailwind_arbitrary' "$variant_fixture/.drift/scan.json")" "data variants excluded from arbitrary tailwind count"
assert_eq "text-[13px]" "$(jq -r '.findings.tsx.tailwind_arbitrary[0].matches[0]' "$variant_fixture/.drift/scan.json")" "real arbitrary tailwind match retained"

prompt_fixture="$tmp/prompt-fixture"
mkdir -p "$prompt_fixture/src"
cat > "$prompt_fixture/src/prompts.ts" <<'TS'
export const prompts = {
  image_prompt: "Transparent background with solid #0B1020 fallback.",
  video_prompt:
    "Dark navy background (#0B1020) with layered parallax stars.",
};

export const actualUiColor = "#abcdef";
TS

scan_with_stubbed_npx "$prompt_fixture" "$tmp/prompt.out"
assert_eq "1" "$(jq -r '.summary.tsx.raw_color_literals' "$prompt_fixture/.drift/scan.json")" "prompt-content colors excluded from raw color count"
assert_eq "#abcdef" "$(jq -r '.findings.tsx.raw_color_literals[0].matches[0]' "$prompt_fixture/.drift/scan.json")" "non-prompt raw color retained"

ignore_fixture="$tmp/ignore-fixture"
mkdir -p "$ignore_fixture/src"
git -C "$ignore_fixture" init -q
cat > "$ignore_fixture/.gitignore" <<'EOF'
src/gitignored.tsx
EOF
cat > "$ignore_fixture/.driftignore" <<'EOF'
src/driftignored.tsx
EOF
cat > "$ignore_fixture/src/tracked.tsx" <<'TSX'
export const tracked = "#123456";
TSX
cat > "$ignore_fixture/src/gitignored.tsx" <<'TSX'
export const gitignored = "#abcdef";
TSX
cat > "$ignore_fixture/src/driftignored.tsx" <<'TSX'
export const driftignored = "#fedcba";
TSX

scan_with_stubbed_npx "$ignore_fixture" "$tmp/ignore.out"
assert_eq "1" "$(jq -r '.summary.tsx.raw_color_literals' "$ignore_fixture/.drift/scan.json")" "gitignored and .driftignore files excluded"
assert_eq "src/tracked.tsx" "$(jq -r '.findings.tsx.raw_color_literals[0].file' "$ignore_fixture/.drift/scan.json")" "tracked file survives ignore filters"

large_fixture="$tmp/large-fixture"
mkdir -p "$large_fixture/src"
{
  printf 'export const colors = [\n'
  for i in $(seq 1 1500); do
    printf '  "#%06x",\n' "$i"
  done
  printf '];\n'
} > "$large_fixture/src/colors.ts"

scan_with_stubbed_npx "$large_fixture" "$tmp/large.out"
assert_eq "1500" "$(jq -r '.summary.tsx.raw_color_literals' "$large_fixture/.drift/scan.json")" "large raw color aggregation"

# Default scope regression: a large src tree used to be skipped because
# `find | head | grep` returned SIGPIPE 141 under pipefail.
scope_fixture="$tmp/default-scope-fixture"
mkdir -p "$scope_fixture/src" "$scope_fixture/components" "$scope_fixture/pages"
for i in $(seq 1 400); do
  printf 'export const C%03d = () => <div />;\n' "$i" > "$scope_fixture/src/C${i}.tsx"
done
cat > "$scope_fixture/components/Buttonish.tsx" <<'TSX'
export function Buttonish() { return <button className="text-sm">Save</button>; }
TSX
cat > "$scope_fixture/pages/index.tsx" <<'TSX'
export default function Page() { return <button className="text-sm">Open</button>; }
TSX

scan_default_scope_with_stubbed_npx "$scope_fixture" "$tmp/default-scope.out"
assert_eq "src components pages" "$(jq -r '.meta.tsx_scope' "$scope_fixture/.drift/scan.json")" "default scope includes large src"
assert_eq "2" "$(jq -r '.summary.tsx.component_motifs' "$scope_fixture/.drift/scan.json")" "component motifs scan default scope"

# Generic frontend coverage: nested packages/sub-apps and non-React file
# formats should be included without per-repo special casing.
generic_fixture="$tmp/generic-frontend-fixture"
mkdir -p "$generic_fixture/src" "$generic_fixture/packages/site/src" "$generic_fixture/packages/site/node_modules/noisy/src" "$generic_fixture/apps/static"
cat > "$generic_fixture/src/App.vue" <<'VUE'
<template>
  <button class="text-base mt-4">Save</button>
</template>
VUE
cat > "$generic_fixture/packages/site/package.json" <<'JSON'
{"scripts":{"dev":"vite"}}
JSON
cat > "$generic_fixture/packages/site/src/App.svelte" <<'SVELTE'
<table><thead><tr><th class="uppercase border-l">Name</th></tr></thead></table>
SVELTE
cat > "$generic_fixture/packages/site/node_modules/noisy/src/Noisy.tsx" <<'TSX'
export function Noisy() { return <button className="text-base">Noisy</button>; }
TSX
cat > "$generic_fixture/apps/static/vite.config.js" <<'JS'
export default {};
JS
cat > "$generic_fixture/apps/static/index.html" <<'HTML'
<div class="rounded-lg border border-gray-300 text-sm">Static card</div>
HTML

scan_default_scope_with_stubbed_npx "$generic_fixture" "$tmp/generic.out"
assert_eq "true" "$(jq -r '.meta.tsx_scope | split(" ") | index("src") != null' "$generic_fixture/.drift/scan.json")" "generic scope includes root src"
assert_eq "true" "$(jq -r '.meta.tsx_scope | split(" ") | index("packages/site/src") != null' "$generic_fixture/.drift/scan.json")" "generic scope includes nested package src"
assert_eq "true" "$(jq -r '.meta.tsx_scope | split(" ") | index("apps/static") != null' "$generic_fixture/.drift/scan.json")" "generic scope includes static vite app"
assert_eq "false" "$(jq -r '.meta.tsx_scope | contains("node_modules")' "$generic_fixture/.drift/scan.json")" "generic scope excludes nested node_modules"
assert_ge "3" "$(jq -r '.summary.tsx.component_motifs' "$generic_fixture/.drift/scan.json")" "generic component motifs"
assert_ge "5" "$(jq -r '.summary.tsx.ui_guideline_violations' "$generic_fixture/.drift/scan.json")" "generic ui guideline violations"

static_fixture="$tmp/plain-static-fixture"
mkdir -p "$static_fixture"
cat > "$static_fixture/index.html" <<'HTML'
<button class="text-base bg-gradient-to-r">Static button</button>
HTML

scan_auto_with_stubbed_npx "$static_fixture" "$tmp/static.out"
assert_eq "tsx" "$(jq -r '.meta.stacks | join(",")' "$static_fixture/.drift/scan.json")" "plain static frontend auto-detected"
assert_eq "index.html" "$(jq -r '.meta.tsx_scope' "$static_fixture/.drift/scan.json")" "plain static scope"

# /ui guideline scanner: direct candidate checks for rules that regex can prove.
guideline_fixture="$tmp/ui-guideline-fixture"
mkdir -p "$guideline_fixture/src"
cat > "$guideline_fixture/src/App.tsx" <<'TSX'
export function App() {
  return (
    <main>
      <h2 className="font-bold">Title</h2>
      <span className="text-sm leading-5">Inline copy</span>
      <table><thead><tr><th className="uppercase border-l">NAME</th></tr></thead></table>
      <button className="text-base bg-gradient-to-r">Submit</button>
    </main>
  );
}
TSX

scan_with_stubbed_npx "$guideline_fixture" "$tmp/guideline.out"
assert_eq "7" "$(jq -r '.summary.tsx.ui_guideline_violations' "$guideline_fixture/.drift/scan.json")" "ui guideline violations"
assert_eq "button,table" "$(jq -r '.findings.tsx.component_motifs | map(.family) | unique | join(",")' "$guideline_fixture/.drift/scan.json")" "component motif families"

# unused_canonical: a canonical primitive folder exports TableSortButton; a
# sibling area renders <table motifs but does not import any canonical export.
# Expect one finding pointing at the bypassing file with TableSortButton in
# missing_exports.
unused_fixture="$tmp/unused-canonical-fixture"
mkdir -p "$unused_fixture/src/components/table" "$unused_fixture/src/features/billing"
cat > "$unused_fixture/src/components/table/TableControls.tsx" <<'TSX'
export function TableSortButton() { return null; }
export function TableMultiSelectFilterDropdown() { return null; }
TSX
cat > "$unused_fixture/src/features/billing/CanonicalConsumer.tsx" <<'TSX'
import { TableSortButton } from '../../components/table/TableControls';
export function CanonicalConsumer() {
  return (<table><thead><tr><th><TableSortButton /></th></tr></thead></table>);
}
TSX
cat > "$unused_fixture/src/features/billing/HandRolledTable.tsx" <<'TSX'
export function HandRolledTable() {
  return (
    <table>
      <thead><tr><th><button onClick={() => {}}>Sort</button></th></tr></thead>
      <tbody><tr><td>row</td></tr></tbody>
    </table>
  );
}
TSX

stub_bin="$(make_npx_stub)"
PATH="$stub_bin:$PATH" "$SCAN" "$unused_fixture" --stack tsx --scope src \
  --canonical-root src/components/table --canonical-root src/components/table > "$tmp/unused.out"

uc_count="$(jq -r '.summary.tsx.unused_canonical' "$unused_fixture/.drift/scan.json")"
assert_eq "1" "$uc_count" "unused_canonical count"
uc_file="$(jq -r '.findings.tsx.unused_canonical[0].file' "$unused_fixture/.drift/scan.json")"
assert_eq "src/features/billing/HandRolledTable.tsx" "$uc_file" "unused_canonical suspect file"
uc_family="$(jq -r '.findings.tsx.unused_canonical[0].family' "$unused_fixture/.drift/scan.json")"
assert_eq "table" "$uc_family" "unused_canonical family"
uc_root="$(jq -r '.findings.tsx.unused_canonical[0].canonical_root' "$unused_fixture/.drift/scan.json")"
assert_eq "src/components/table" "$uc_root" "unused_canonical canonical_root"
uc_roots="$(jq -r '.meta.tsx_canonical_roots | join(",")' "$unused_fixture/.drift/scan.json")"
assert_eq "src/components/table" "$uc_roots" "canonical roots deduped"
uc_missing="$(jq -r '.findings.tsx.unused_canonical[0].missing_exports | sort | join(",")' "$unused_fixture/.drift/scan.json")"
assert_eq "TableMultiSelectFilterDropdown,TableSortButton" "$uc_missing" "unused_canonical missing exports"

echo "drift-detector scan regression tests: pass"
