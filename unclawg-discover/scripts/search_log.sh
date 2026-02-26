#!/bin/bash
# Track search runs to avoid redundant API calls.
# Usage:
#   ./search_log.sh get <platform> <search_term>       → prints ISO timestamp or "none"
#   ./search_log.sh get-dataset <platform> <search_term> → prints dataset_id or "none"
#   ./search_log.sh set <platform> <search_term> <result_count> [dataset_id]  → updates log
#   ./search_log.sh check-dataset <dataset_id>          → prints "valid" or "expired"
#
# Log file: .search_log.json in the skill directory (sibling to scripts/)
# Key format: "platform:search_term" → { "last_run": "ISO", "result_count": N, "dataset_id": "..." }
#
# Smart freshness logic:
#   - "none" → first-time search, caller should use default time window
#   - timestamp → refresh search, caller should use this as "since" cutoff

set -euo pipefail

usage() {
  echo "Usage: search_log.sh <get|get-dataset|set|check-dataset> <platform> <search_term> [result_count] [dataset_id]" >&2
}

require_tool() {
  local tool="$1"
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing required tool: $tool" >&2
    exit 1
  fi
}

load_apify_key_from_zshrc() {
  if [[ -n "${APIFY_API_KEY:-}" ]]; then
    return
  fi
  if [[ ! -f "${HOME}/.zshrc" ]]; then
    return
  fi
  local extracted
  extracted="$(
    awk '/^[[:space:]]*export[[:space:]]+APIFY_API_KEY=/{line=$0; sub(/^[^=]*=/, "", line); print line}' "${HOME}/.zshrc" \
      | tail -n1 \
      | sed -E "s/^[\"']|[\"']$//g"
  )"
  if [[ -n "${extracted}" ]]; then
    export APIFY_API_KEY="${extracted}"
  fi
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

require_tool jq

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/../.search_log.json"

# Initialize log file if missing
if [ ! -f "$LOG_FILE" ]; then
  echo '{}' > "$LOG_FILE"
fi

MODE="$1"

case "$MODE" in
  get)
    PLATFORM="${2:?Missing platform}"
    SEARCH_TERM="${3:?Missing search term}"
    KEY="${PLATFORM}:${SEARCH_TERM}"
    jq -r --arg key "$KEY" '.[$key].last_run // "none"' "$LOG_FILE"
    ;;

  get-dataset)
    PLATFORM="${2:?Missing platform}"
    SEARCH_TERM="${3:?Missing search term}"
    KEY="${PLATFORM}:${SEARCH_TERM}"
    jq -r --arg key "$KEY" '.[$key].dataset_id // "none"' "$LOG_FILE"
    ;;

  set)
    PLATFORM="${2:?Missing platform}"
    SEARCH_TERM="${3:?Missing search term}"
    COUNT="${4:-0}"
    DATASET_ID="${5:-}"
    KEY="${PLATFORM}:${SEARCH_TERM}"
    NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    if [ -n "$DATASET_ID" ]; then
      jq --arg key "$KEY" --arg ts "$NOW" --argjson count "$COUNT" --arg ds "$DATASET_ID" \
        '.[$key] = {"last_run": $ts, "result_count": $count, "dataset_id": $ds}' \
        "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
      echo "Logged: ${KEY} at ${NOW} (${COUNT} results, dataset: ${DATASET_ID})" >&2
    else
      jq --arg key "$KEY" --arg ts "$NOW" --argjson count "$COUNT" \
        '.[$key] = {"last_run": $ts, "result_count": $count}' \
        "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
      echo "Logged: ${KEY} at ${NOW} (${COUNT} results)" >&2
    fi
    ;;

  check-dataset)
    require_tool curl
    DATASET_ID="${2:?Missing dataset_id}"
    load_apify_key_from_zshrc
    if [ -z "${APIFY_API_KEY:-}" ]; then
      echo "expired"
      exit 0
    fi
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
      "https://api.apify.com/v2/datasets/${DATASET_ID}?token=${APIFY_API_KEY}")
    if [ "$HTTP_STATUS" = "200" ]; then
      echo "valid"
    else
      echo "expired"
    fi
    ;;

  *)
    echo "Unknown mode: $MODE. Use 'get', 'get-dataset', 'set', or 'check-dataset'." >&2
    exit 1
    ;;
esac
