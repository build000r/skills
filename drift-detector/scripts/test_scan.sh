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
