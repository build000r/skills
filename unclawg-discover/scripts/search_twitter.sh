#!/bin/bash
# Search Twitter/X via Apify X Twitter Advanced Search.
# Usage: ./search_twitter.sh <query> [results_limit] [days_ago]
#
# Actor: api-ninja/x-twitter-advanced-search (4.93 rating, CU-based)
# Requires: APIFY_API_KEY
#
# Examples:
#   ./search_twitter.sh "claude code deleted" 20 7
#   ./search_twitter.sh "workflow failed in production" 20 7
#   ./search_twitter.sh "ai agent guardrails" 20 14
#
# Smart freshness: checks .search_log.json for last run time.
#
# Output: JSON array of tweets with author, text, likes, replies, url

set -euo pipefail

usage() {
  echo "Usage: search_twitter.sh <query> [results_limit] [days_ago]" >&2
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

require_tool curl
require_tool jq

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

QUERY="$1"
LIMIT="${2:-20}"
DAYS_AGO="${3:-7}"

if ! [[ "${LIMIT}" =~ ^[0-9]+$ ]]; then
  echo "results_limit must be an integer: ${LIMIT}" >&2
  exit 1
fi

if ! [[ "${DAYS_AGO}" =~ ^[0-9]+$ ]]; then
  echo "days_ago must be an integer: ${DAYS_AGO}" >&2
  exit 1
fi

# Actor requires numberOfTweets >= 20
if [ "$LIMIT" -lt 20 ]; then
  LIMIT=20
fi

load_apify_key_from_zshrc

if [ -z "${APIFY_API_KEY:-}" ]; then
  echo '{"error": "APIFY_API_KEY not set. Sign up at https://apify.com and add to ~/.zshrc: export APIFY_API_KEY=\"your-key\""}'
  exit 1
fi

# Check search log for freshness
SEARCH_KEY="twitter:${QUERY}"
SINCE=$("${SCRIPT_DIR}/search_log.sh" get twitter "$SEARCH_KEY")

if [ "$SINCE" = "none" ]; then
  START_DATE=$(date -u -v-${DAYS_AGO}d +"%Y-%m-%d" 2>/dev/null || date -u -d "${DAYS_AGO} days ago" +"%Y-%m-%d")
  echo "First-time search for '${QUERY}' on Twitter, since ${START_DATE}" >&2
else
  START_DATE=$(echo "$SINCE" | cut -d'T' -f1)
  echo "Refresh search, filtering to tweets since ${START_DATE}" >&2
fi

END_DATE=$(date -u +"%Y-%m-%d")

# Start the scraper run
# Actor updated to build 0.0.115 on 2026-02-13 — new field names:
#   searchQuery -> query, maxItems -> numberOfTweets,
#   startDate -> timeSince, endDate -> timeUntil, sort -> search_type
RUN_RESPONSE=$(curl -s -X POST \
  "https://api.apify.com/v2/acts/api-ninja~x-twitter-advanced-search/runs?token=${APIFY_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"${QUERY}\",
    \"numberOfTweets\": ${LIMIT},
    \"timeSince\": \"${START_DATE}\",
    \"timeUntil\": \"${END_DATE}\",
    \"search_type\": \"Latest\"
  }")

RUN_ID=$(echo "$RUN_RESPONSE" | jq -r '.data.id')

if [ "$RUN_ID" = "null" ] || [ -z "$RUN_ID" ]; then
  echo '{"error": "Failed to start Apify run", "response": '"$RUN_RESPONSE"'}'
  exit 1
fi

echo "Waiting for Apify run ${RUN_ID}..." >&2

# Poll until complete (max 120 seconds)
for i in $(seq 1 24); do
  sleep 5
  STATUS=$(curl -s "https://api.apify.com/v2/actor-runs/${RUN_ID}?token=${APIFY_API_KEY}" | jq -r '.data.status')
  if [ "$STATUS" = "SUCCEEDED" ]; then
    break
  elif [ "$STATUS" = "FAILED" ] || [ "$STATUS" = "ABORTED" ]; then
    echo "{\"error\": \"Apify run ${STATUS}\"}"
    exit 1
  fi
  echo "  Status: ${STATUS}..." >&2
done

# Fetch results from the default dataset
DATASET_ID=$(curl -s "https://api.apify.com/v2/actor-runs/${RUN_ID}?token=${APIFY_API_KEY}" | jq -r '.data.defaultDatasetId')

# Normalize output — actor build 0.0.115 field names:
#   screen_name, favorites, replies, retweets, views, text, url, created_at, user_info
RESULT=$(curl -s "https://api.apify.com/v2/datasets/${DATASET_ID}/items?token=${APIFY_API_KEY}&format=json" | jq '[
  .[] | {
    author: (.screen_name // .author.userName // .user_screen_name // "unknown"),
    author_name: (.user_info.name // .author.name // .user_name // "unknown"),
    author_followers: (.user_info.followers_count // .author.followers // .user_followers_count // 0),
    author_bio: (.user_info.description // .author.description // .user_description // ""),
    text: (.text // .full_text // .tweet_text // ""),
    likes: (.favorites // .likeCount // .favorite_count // 0),
    replies: (.replies // .replyCount // .reply_count // 0),
    retweets: (.retweets // .retweetCount // .retweet_count // 0),
    views: (.views // 0),
    url: (.url // .tweet_url // ("https://x.com/" + (.screen_name // "unknown") + "/status/" + (.tweet_id // .id // "unknown"))),
    created: (.created_at // .createdAt // .date // "unknown")
  }
] | sort_by(-.likes)')

RESULT_COUNT=$(echo "$RESULT" | jq 'length')
echo "Found ${RESULT_COUNT} tweets" >&2

# Update search log
"${SCRIPT_DIR}/search_log.sh" set twitter "$SEARCH_KEY" "$RESULT_COUNT"

echo "$RESULT"
