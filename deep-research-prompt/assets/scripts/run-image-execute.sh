#!/usr/bin/env bash
# Shared ChatGPT Create image / Oracle runner for staged image-spec folders.
#
# Canonical caller contract:
#   run-image-execute.sh --run-dir <dir>
#
# Expected run-dir layout:
#   spec.md       prompt/spec submitted to ChatGPT
#   source/       optional attached reference files
#   result/       optional output directory
#   oracle.log    runner-created Oracle log

set -euo pipefail

usage() {
  cat <<'USAGE'
run-image-execute.sh --run-dir <dir> [options]

Required:
  --run-dir DIR          Directory containing spec.md and optional source/

Options:
  --spec FILE            Spec file (default: DIR/spec.md)
  --source-dir DIR       Source attachment dir (default: DIR/source)
  --result-dir DIR       Result dir (default: DIR/result)
  --slug SLUG            Oracle slug (default: basename DIR)
  --url-match TEXT       ORACLE_CHATGPT_URL_MATCH (default: SLUG)
  --chatgpt-url URL      ChatGPT URL opened by Oracle (default: https://chatgpt.com/?run=URL_MATCH)
  --log FILE             Oracle log file (default: DIR/oracle.log)
  --remote-chrome HOST   Remote Chrome endpoint (default: 127.0.0.1:9222)
  --browser-timeout DUR  Oracle browser timeout (default: 15m)
  --prepare-only         Run sizing/route checks and write command file, but do not launch Oracle
  -h, --help             Show this help

Environment:
  ORACLE_BIN             Oracle executable override (default: oracle)
  ORACLE_REMOTE_CHROME   Remote Chrome endpoint override
  ORACLE_BROWSER_TIMEOUT Browser timeout override
USAGE
}

die() {
  echo "error: $*" >&2
  exit 1
}

RUN_DIR=""
SPEC=""
SOURCE_DIR=""
RESULT_DIR=""
SLUG=""
URL_MATCH=""
CHATGPT_URL=""
LOG_FILE=""
REMOTE_CHROME="${ORACLE_REMOTE_CHROME:-127.0.0.1:9222}"
BROWSER_TIMEOUT="${ORACLE_BROWSER_TIMEOUT:-15m}"
ORACLE_BIN="${ORACLE_BIN:-oracle}"
PREPARE_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-dir)
      RUN_DIR="${2:-}"; shift 2 ;;
    --spec)
      SPEC="${2:-}"; shift 2 ;;
    --source-dir)
      SOURCE_DIR="${2:-}"; shift 2 ;;
    --result-dir)
      RESULT_DIR="${2:-}"; shift 2 ;;
    --slug)
      SLUG="${2:-}"; shift 2 ;;
    --url-match)
      URL_MATCH="${2:-}"; shift 2 ;;
    --chatgpt-url)
      CHATGPT_URL="${2:-}"; shift 2 ;;
    --log)
      LOG_FILE="${2:-}"; shift 2 ;;
    --remote-chrome)
      REMOTE_CHROME="${2:-}"; shift 2 ;;
    --browser-timeout)
      BROWSER_TIMEOUT="${2:-}"; shift 2 ;;
    --prepare-only)
      PREPARE_ONLY=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      die "unknown argument: $1" ;;
  esac
done

[[ -n "$RUN_DIR" ]] || { usage >&2; exit 64; }
[[ -d "$RUN_DIR" ]] || die "run dir does not exist: $RUN_DIR"

RUN_DIR="$(cd "$RUN_DIR" && pwd)"
if [[ -z "$SPEC" ]]; then SPEC="$RUN_DIR/spec.md"; fi
if [[ -z "$SOURCE_DIR" ]]; then SOURCE_DIR="$RUN_DIR/source"; fi
if [[ -z "$RESULT_DIR" ]]; then RESULT_DIR="$RUN_DIR/result"; fi
if [[ -z "$SLUG" ]]; then SLUG="$(basename "$RUN_DIR")"; fi
if [[ -z "$URL_MATCH" ]]; then URL_MATCH="$SLUG"; fi
if [[ -z "$CHATGPT_URL" ]]; then CHATGPT_URL="https://chatgpt.com/?run=$URL_MATCH"; fi
if [[ -z "$LOG_FILE" ]]; then LOG_FILE="$RUN_DIR/oracle.log"; fi

[[ -f "$SPEC" ]] || die "spec file does not exist: $SPEC"
mkdir -p "$RESULT_DIR" "$(dirname "$LOG_FILE")"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROUTE_GUARD="$SKILL_DIR/assets/scripts/check-oracle-tab-local-route.mjs"
IMAGE_TOGGLE="$SKILL_DIR/assets/scripts/toggle-chatgpt-image.mjs"
DRY_RUN_LOG="$RUN_DIR/oracle.dry-run.log"
GUARD_LOG="$RUN_DIR/oracle.route-guard.log"
COMMAND_FILE="$RUN_DIR/oracle.command.sh"
RESPONSE_FILE="$RESULT_DIR/oracle.response.md"

[[ -f "$ROUTE_GUARD" ]] || die "route guard missing: $ROUTE_GUARD"
[[ -f "$IMAGE_TOGGLE" ]] || die "image toggle helper missing: $IMAGE_TOGGLE"
command -v node >/dev/null 2>&1 || die "node is required for ChatGPT route/toggle helpers"
command -v "$ORACLE_BIN" >/dev/null 2>&1 || {
  echo "Mode: Image paste-mode fallback. Slug: $SLUG. Spec file: $SPEC."
  echo "Oracle executable not found: $ORACLE_BIN"
  echo "Open ChatGPT Create image manually, attach files from $SOURCE_DIR, and paste $SPEC."
  exit 69
}

echo "Mode: Image execute. Slug: $SLUG. Spec file: $SPEC."
echo "Run dir: $RUN_DIR"

echo "Sizing: oracle --dry-run summary --file $SPEC"
"$ORACLE_BIN" --dry-run summary --file "$SPEC" >"$DRY_RUN_LOG" 2>&1 || {
  echo "Sizing failed. Log: $DRY_RUN_LOG" >&2
  exit 70
}
echo "Sizing: ok ($DRY_RUN_LOG)"

echo "Route guard: node $ROUTE_GUARD"
ORACLE_BIN="$ORACLE_BIN" node "$ROUTE_GUARD" >"$GUARD_LOG" 2>&1 || {
  echo "Route-blocked Image execute attempt. No Oracle browser submission was made."
  echo "Guard log: $GUARD_LOG"
  sed -n '1,80p' "$GUARD_LOG" >&2
  exit 72
}
echo "Route guard: ok ($GUARD_LOG)"

ORACLE_HELP="$("$ORACLE_BIN" --help 2>&1 || true)"
if ! printf '%s\n' "$ORACLE_HELP" | grep -q -- '--pre-submit-hook'; then
  echo "Route-blocked Image execute attempt. No Oracle browser submission was made."
  echo "The shared runner currently requires Oracle --pre-submit-hook so Create image is toggled in the exact submit tab."
  echo "Upgrade/patch Oracle or use manual Image paste-mode fallback."
  exit 73
fi

ATTACHMENTS=()
if [[ -d "$SOURCE_DIR" ]]; then
  while IFS= read -r -d '' file; do
    ext="$(printf '%s' "${file##*.}" | tr '[:upper:]' '[:lower:]')"
    case "$ext" in
      png|jpg|jpeg|webp|gif|html|htm|pdf)
        ATTACHMENTS+=("$file")
        ;;
    esac
  done < <(find "$SOURCE_DIR" -maxdepth 1 -type f -print0)
fi

CMD=(
  "$ORACLE_BIN"
  --engine browser
  --remote-chrome "$REMOTE_CHROME"
  --browser-model-strategy ignore
  --browser-attachments always
  --pre-submit-hook "node $IMAGE_TOGGLE"
  --browser-timeout "$BROWSER_TIMEOUT"
  --slug "$SLUG"
)

if printf '%s\n' "$ORACLE_HELP" | grep -q -- '--chatgpt-url'; then
  CMD+=(--chatgpt-url "$CHATGPT_URL")
fi

if printf '%s\n' "$ORACLE_HELP" | grep -q -- '--write-output'; then
  CMD+=(--write-output "$RESPONSE_FILE")
fi

for file in "${ATTACHMENTS[@]}"; do
  CMD+=(--file "$file")
done

{
  echo "#!/usr/bin/env bash"
  echo "set -euo pipefail"
  printf 'SPEC=%q\n' "$SPEC"
  printf 'ORACLE_CHATGPT_URL_MATCH=%q ' "$URL_MATCH"
  for part in "${CMD[@]}"; do
    printf '%q ' "$part"
  done
  printf '%s\n' '-p "$(cat "$SPEC")"'
} >"$COMMAND_FILE"
chmod +x "$COMMAND_FILE"

echo "Attachments: ${#ATTACHMENTS[@]} file(s) from $SOURCE_DIR"
echo "Command: $COMMAND_FILE"

if [[ "$PREPARE_ONLY" -eq 1 ]]; then
  echo "Prepare-only: Oracle was not launched."
  exit 0
fi

PROMPT="$(cat "$SPEC")"
echo "Launching Oracle. Log: $LOG_FILE"
ORACLE_CHATGPT_URL_MATCH="$URL_MATCH" "${CMD[@]}" -p "$PROMPT" >"$LOG_FILE" 2>&1 || {
  echo "Oracle failed. Log: $LOG_FILE" >&2
  tail -40 "$LOG_FILE" >&2 || true
  exit 74
}

echo "Oracle session started. Reattach with: oracle session $SLUG"
echo "Image verification: confirm an image, not text, came back; re-run after re-toggling if it did not."
