#!/usr/bin/env bash
set -u

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
helper="$script_dir/toggle-chatgpt-image.mjs"
log_file="${CHATGPT_IMAGE_HOOK_LOG:-${TMPDIR:-/tmp}/chatgpt-image-hook-${ORACLE_CHATGPT_TARGET_ID:-unknown}.log}"

mkdir -p "$(dirname "$log_file")"

{
  printf '=== chatgpt image hook %s ===\n' "$(date -u +%FT%TZ)"
  printf 'ORACLE_CDP_HOST=%s\n' "${ORACLE_CDP_HOST:-}"
  printf 'ORACLE_CDP_PORT=%s\n' "${ORACLE_CDP_PORT:-}"
  printf 'ORACLE_CHATGPT_TARGET_ID=%s\n' "${ORACLE_CHATGPT_TARGET_ID:-}"
  printf 'ORACLE_CHATGPT_URL=%s\n' "${ORACLE_CHATGPT_URL:-}"
  printf 'ORACLE_CHATGPT_URL_MATCH=%s\n' "${ORACLE_CHATGPT_URL_MATCH:-}"
  printf 'CHATGPT_IMAGE_URL_MATCH=%s\n' "${CHATGPT_IMAGE_URL_MATCH:-}"
  printf 'CHATGPT_IMAGE_VERBOSE=%s\n' "${CHATGPT_IMAGE_VERBOSE:-}"
  printf 'helper=%s\n' "$helper"
} >>"$log_file"

stdout_file="$(mktemp "${TMPDIR:-/tmp}/chatgpt-image-hook-stdout.XXXXXX")"
stderr_file="$(mktemp "${TMPDIR:-/tmp}/chatgpt-image-hook-stderr.XXXXXX")"

set +e
node "$helper" >"$stdout_file" 2>"$stderr_file"
rc=$?
set -e

{
  printf -- '--- stdout ---\n'
  sed -n '1,200p' "$stdout_file"
  printf -- '--- stderr ---\n'
  sed -n '1,200p' "$stderr_file"
  printf -- '--- exit %s ---\n' "$rc"
} >>"$log_file"

sed -n '1,200p' "$stdout_file"
sed -n '1,200p' "$stderr_file" >&2
rm -f "$stdout_file" "$stderr_file"

exit "$rc"
