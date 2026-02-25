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

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/../.search_log.json"

# Initialize log file if missing
if [ ! -f "$LOG_FILE" ]; then
  echo '{}' > "$LOG_FILE"
fi

MODE="${1:?Usage: search_log.sh <get|get-dataset|set|check-dataset> <platform> <search_term> [result_count] [dataset_id]}"

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
    DATASET_ID="${2:?Missing dataset_id}"
    if [ -z "$APIFY_API_KEY" ]; then
      export APIFY_API_KEY=$(grep 'APIFY_API_KEY' ~/.zshrc | grep -o '"[^"]*"' | tr -d '"')
    fi
    if [ -z "$APIFY_API_KEY" ]; then
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
