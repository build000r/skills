#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
skill_dir="$(cd "$script_dir/.." && pwd -P)"
bin_path="${CLAWGS_BIN:-$skill_dir/target/release/clawgs}"

if [[ ! -x "$bin_path" ]]; then
  echo "error: binary not found at $bin_path" >&2
  echo "run: bash scripts/install.sh" >&2
  exit 1
fi

if ! "$bin_path" --help >/dev/null 2>&1; then
  echo "error: clawgs --help failed" >&2
  exit 1
fi

tmp_file="$(mktemp)"
trap 'rm -f "$tmp_file"' EXIT

cat > "$tmp_file" <<'JSONL'
{"type":"session_meta","payload":{"cwd":"/tmp/example"}}
{"type":"event_msg","payload":{"type":"user_message","message":"extract this"}}
{"type":"response","payload":{"usage":{"input_tokens":123}}}
{"type":"response_item","payload":{"type":"function_call","name":"exec_command","arguments":"{\"command\":\"ls -la\"}"}}
JSONL

if ! output="$($bin_path extract --tool codex --input "$tmp_file" 2>/dev/null)"; then
  echo "error: smoke extraction failed" >&2
  exit 1
fi

if ! printf '%s' "$output" | grep -q '"schema_version":"clawgs.v1"'; then
  echo "error: smoke extraction returned unexpected output" >&2
  exit 1
fi

echo "clawgs check passed"
