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

echo "drift-detector scan regression tests: pass"
