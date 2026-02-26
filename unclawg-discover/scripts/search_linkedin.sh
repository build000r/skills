#!/bin/bash
# Search LinkedIn Posts via Apify Posts Search Scraper (no cookies needed).
# Usage: ./search_linkedin.sh <query> [total_posts] [sort_by]
#
# Actor: apimaestro/linkedin-posts-search-scraper-no-cookies (4.14 rating, no login)
# Requires: APIFY_API_KEY
# Pricing: ~$5 per 1,000 posts
#
# sort_by: "relevance" (default) or "date_posted"
#
# Examples:
#   ./search_linkedin.sh "claude code broke production" 20
#   ./search_linkedin.sh "ai agent guardrails" 20 date_posted
#   ./search_linkedin.sh "cursor deleted my code" 15
#
# Smart freshness: checks .search_log.json for last run time.
#
# Output: JSON array of posts with author, text, reactions, url

set -euo pipefail

usage() {
  echo "Usage: search_linkedin.sh <query> [total_posts] [sort_by]" >&2
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
TOTAL="${2:-20}"
SORT="${3:-date_posted}"

if ! [[ "${TOTAL}" =~ ^[0-9]+$ ]]; then
  echo "total_posts must be an integer: ${TOTAL}" >&2
  exit 1
fi

load_apify_key_from_zshrc

if [ -z "${APIFY_API_KEY:-}" ]; then
  echo '{"error": "APIFY_API_KEY not set. Sign up at https://apify.com and add to ~/.zshrc: export APIFY_API_KEY=\"your-key\""}'
  exit 1
fi

# Check search log for freshness
SEARCH_KEY="linkedin:${QUERY}"
SINCE=$("${SCRIPT_DIR}/search_log.sh" get linkedin "$SEARCH_KEY")

if [ "$SINCE" = "none" ]; then
  echo "First-time search for '${QUERY}' on LinkedIn" >&2
else
  echo "Refresh search (last run: ${SINCE})" >&2
fi

# Start the scraper run
RUN_RESPONSE=$(curl -s -X POST \
  "https://api.apify.com/v2/acts/apimaestro~linkedin-posts-search-scraper-no-cookies/runs?token=${APIFY_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{
    \"searchQuery\": \"${QUERY}\",
    \"totalPosts\": ${TOTAL},
    \"sort_by\": \"${SORT}\"
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

# Fetch results
DATASET_ID=$(curl -s "https://api.apify.com/v2/actor-runs/${RUN_ID}?token=${APIFY_API_KEY}" | jq -r '.data.defaultDatasetId')

# Normalize output — field names vary, try common patterns
RESULT=$(curl -s "https://api.apify.com/v2/datasets/${DATASET_ID}/items?token=${APIFY_API_KEY}&format=json" | jq '[
  .[] | {
    author_name: (.authorName // .author_name // .author.name // "unknown"),
    author_headline: (.authorHeadline // .author_headline // .author.headline // ""),
    author_profile: (.authorProfileUrl // .author_profile_url // .authorUrl // ""),
    author_followers: (.authorFollowers // .author_followers // .followers // null),
    text: (.postText // .text // .content // .body // ""),
    reactions: (.totalReactions // .reactions // .likeCount // .likes // 0),
    comments: (.totalComments // .comments // .commentCount // 0),
    reposts: (.totalReposts // .reposts // .shareCount // 0),
    posted: (.postedAt // .publishedAt // .date // .created_at // "unknown"),
    url: (.postUrl // .url // .link // "")
  }
] | sort_by(-.reactions)')

RESULT_COUNT=$(echo "$RESULT" | jq 'length')
echo "Found ${RESULT_COUNT} LinkedIn posts" >&2

# Update search log
"${SCRIPT_DIR}/search_log.sh" set linkedin "$SEARCH_KEY" "$RESULT_COUNT"

echo "$RESULT"
