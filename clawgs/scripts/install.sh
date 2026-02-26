#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
skill_dir="$(cd "$script_dir/.." && pwd -P)"

if ! command -v cargo >/dev/null 2>&1; then
  echo "error: cargo not found. Install Rust toolchain first." >&2
  exit 1
fi

cd "$skill_dir"
cargo build --release

bin_path="$skill_dir/target/release/clawgs"
if [[ ! -x "$bin_path" ]]; then
  echo "error: build finished but binary not found at $bin_path" >&2
  exit 1
fi

echo "clawgs built successfully"
echo "binary: $bin_path"
echo "run:    $bin_path --help"
echo

echo "optional global symlink:"
echo "  mkdir -p \"$HOME/.local/bin\""
echo "  ln -sfn \"$bin_path\" \"$HOME/.local/bin/clawgs\""
echo "  export PATH=\"$HOME/.local/bin:$PATH\""
