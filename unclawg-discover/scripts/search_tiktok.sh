#!/bin/bash
# Search TikTok hashtags via Apify clockworks TikTok Hashtag Scraper.
# Usage: ./search_tiktok.sh <results_limit> <hashtag1> [hashtag2] [hashtag3] ...
#
# Requires: APIFY_API_KEY env var (free tier: $5/mo credits)
# Sign up: https://apify.com
# Scraper: https://apify.com/clockworks/tiktok-hashtag-scraper
#
# NOTE: Switched from apidojo~tiktok-scraper (2026-02-11) after two consecutive
# runs returning 0 results. clockworks actor has 125K+ users, daily updates,
# and better proxy handling. If this actor also fails, try clockworks~tiktok-scraper
# (general-purpose) or check if Apify residential proxies are needed.
#
# Examples:
#   ./search_tiktok.sh 20 perimenopause menopausesucks perimenopausesymptoms
#   ./search_tiktok.sh 30 brainfog
#   ./search_tiktok.sh 15 mineraldeficiency fatigue hairloss
#
# Smart freshness:
#   - Checks .search_log.json for last run time
#   - Applies jq post-filter on createTimeISO/createTime as date filter
#
# Output: JSON array of videos with author, description, likes, views, url

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

LIMIT="${1:?Usage: search_tiktok.sh <results_limit> <hashtag1> [hashtag2] ...}"
shift
if [ $# -eq 0 ]; then
  echo '{"error": "No hashtags provided. Usage: search_tiktok.sh <limit> <hashtag1> [hashtag2] ..."}'
  exit 1
fi

HASHTAGS=("$@")

if [ -z "$APIFY_API_KEY" ]; then
  export APIFY_API_KEY=$(grep 'APIFY_API_KEY' ~/.zshrc | grep -o '"[^"]*"' | tr -d '"')
fi

if [ -z "$APIFY_API_KEY" ]; then
  echo '{"error": "APIFY_API_KEY not set. Sign up at https://apify.com and add to ~/.zshrc: export APIFY_API_KEY=\"your-key\""}'
  exit 1
fi

# Determine freshness cutoff from search log
SINCE=""
for TAG in "${HASHTAGS[@]}"; do
  TAG_SINCE=$("${SCRIPT_DIR}/search_log.sh" get tiktok "$TAG")
  if [ "$TAG_SINCE" = "none" ]; then
    SINCE="none"
    break
  elif [ -z "$SINCE" ] || [[ "$TAG_SINCE" < "$SINCE" ]]; then
    SINCE="$TAG_SINCE"
  fi
done

# Set the jq filter cutoff
if [ "$SINCE" = "none" ] || [ -z "$SINCE" ]; then
  # First-time search: 7-day window
  SINCE=$(date -u -v-7d +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -d "7 days ago" +"%Y-%m-%dT%H:%M:%SZ")
  echo "First-time search, 7-day window (jq cutoff: ${SINCE})" >&2
else
  echo "Refresh search (jq cutoff: ${SINCE})" >&2
fi

# Check for reusable cached dataset before starting a new Apify run
CACHED_DATASET=$("${SCRIPT_DIR}/search_log.sh" get-dataset tiktok "${HASHTAGS[0]}")
DATASET_ID=""

if [ "$CACHED_DATASET" != "none" ]; then
  CACHE_STATUS=$("${SCRIPT_DIR}/search_log.sh" check-dataset "$CACHED_DATASET")
  if [ "$CACHE_STATUS" = "valid" ]; then
    echo "Reusing cached dataset ${CACHED_DATASET} (skipping Apify run)" >&2
    DATASET_ID="$CACHED_DATASET"
  else
    echo "Cached dataset expired, starting new run" >&2
  fi
fi

if [ -z "$DATASET_ID" ]; then
  # No cached dataset — start a new Apify run
  HASHTAGS_JSON=$(printf '%s\n' "${HASHTAGS[@]}" | jq -R . | jq -s .)

  RUN_RESPONSE=$(curl -s -X POST \
    "https://api.apify.com/v2/acts/clockworks~tiktok-hashtag-scraper/runs?token=${APIFY_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{
      \"hashtags\": ${HASHTAGS_JSON},
      \"numberOfVideos\": ${LIMIT}
    }")

  RUN_ID=$(echo "$RUN_RESPONSE" | jq -r '.data.id')

  if [ "$RUN_ID" = "null" ] || [ -z "$RUN_ID" ]; then
    echo '{"error": "Failed to start Apify run", "response": '"$RUN_RESPONSE"'}'
    exit 1
  fi

  echo "Waiting for Apify run ${RUN_ID}..." >&2

  # Poll until complete (max 120 seconds)
  STATUS=""
  for i in $(seq 1 24); do
    sleep 5
    STATUS=$(curl -s "https://api.apify.com/v2/actor-runs/${RUN_ID}?token=${APIFY_API_KEY}" | jq -r '.data.status')
    if [ "$STATUS" = "SUCCEEDED" ]; then
      break
    elif [ "$STATUS" = "FAILED" ] || [ "$STATUS" = "ABORTED" ]; then
      echo "{\"error\": \"Apify run ${STATUS}\", \"run_id\": \"${RUN_ID}\"}"
      exit 1
    fi
    echo "  Status: ${STATUS}..." >&2
  done

  if [ "$STATUS" != "SUCCEEDED" ]; then
    echo "{\"error\": \"Apify run timed out after 120s\", \"last_status\": \"${STATUS}\", \"run_id\": \"${RUN_ID}\"}"
    exit 1
  fi

  DATASET_ID=$(curl -s "https://api.apify.com/v2/actor-runs/${RUN_ID}?token=${APIFY_API_KEY}" | jq -r '.data.defaultDatasetId')
fi

# Map clockworks actor output fields to our standard format.
# The clockworks~tiktok-hashtag-scraper typically outputs fields like:
#   .authorMeta.name / .author        -> author username
#   .authorMeta.nickName / .nickname  -> author display name
#   .authorMeta.fans / .followers     -> follower count
#   .text / .desc / .description      -> video description/caption
#   .diggCount / .likes               -> likes
#   .commentCount / .comments         -> comments
#   .shareCount / .shares             -> shares
#   .playCount / .views               -> views
#   .webVideoUrl / .video.url         -> canonical video URL
#   .createTimeISO / .createTime      -> ISO timestamp
#   .hashtags[].name                  -> hashtag names
#
# NOTE: jq uses // (alternative operator) for common field name variants.
# If output is empty after a live run, inspect raw dataset items:
#   curl -s "https://api.apify.com/v2/datasets/${DATASET_ID}/items?token=${APIFY_API_KEY}&format=json&limit=2" | jq .[0]
# Then adjust the mapping below.
RESULT=$(curl -s "https://api.apify.com/v2/datasets/${DATASET_ID}/items?token=${APIFY_API_KEY}&format=json" | jq --arg since "$SINCE" '[
  .[] | select(
    (.createTimeISO // .createTime // "") > $since
  ) | {
    author: (.authorMeta.name // .author // .authorUniqueId // "unknown"),
    author_nickname: (.authorMeta.nickName // .authorMeta.nickname // .nickname // ""),
    author_followers: (.authorMeta.fans // .authorMeta.followers // 0),
    author_verified: (.authorMeta.verified // false),
    description: ((.text // .desc // .description // "")[:300]),
    likes: (.diggCount // .stats.diggCount // .likes // 0),
    comments: (.commentCount // .stats.commentCount // .comments // 0),
    shares: (.shareCount // .stats.shareCount // .shares // 0),
    views: (.playCount // .stats.playCount // .views // 0),
    url: (.webVideoUrl // .video.url // ("https://www.tiktok.com/@" + (.authorMeta.name // .author // "") + "/video/" + (.id // "" | tostring))),
    created: (.createTimeISO // .createTime // ""),
    hashtags: [(.hashtags // .challenges // [])[]? | (.name // .title // .)]
  }
] | sort_by(-.likes)')

RESULT_COUNT=$(echo "$RESULT" | jq 'length')

# 0-result detection: warn loudly so the operator can investigate
if [ "$RESULT_COUNT" = "0" ]; then
  echo "" >&2
  echo "⚠️  WARNING: 0 results after date filtering." >&2
  echo "   Possible causes:" >&2
  echo "   1. Actor returned data but all items were older than jq cutoff (${SINCE})" >&2
  echo "   2. Actor returned 0 items — may need Apify residential proxies" >&2
  echo "   3. Output field names changed — inspect raw dataset:" >&2
  echo "      curl -s 'https://api.apify.com/v2/datasets/${DATASET_ID}/items?token=\${APIFY_API_KEY}&format=json&limit=2' | jq '.[0] | keys'" >&2
  echo "   Fallback: try clockworks~tiktok-scraper (general-purpose, 125K users)" >&2
  echo "" >&2
fi

# Update search log for each hashtag (with dataset_id for future reuse)
for TAG in "${HASHTAGS[@]}"; do
  "${SCRIPT_DIR}/search_log.sh" set tiktok "$TAG" "$RESULT_COUNT" "$DATASET_ID"
done

echo "$RESULT"
