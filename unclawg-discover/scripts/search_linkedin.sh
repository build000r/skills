#!/bin/bash
# Search LinkedIn Posts via Apify Posts Search Scraper (no cookies needed).
# Usage: ./search_linkedin.sh <query> [total_posts] [sort_by] [max_age_hours]
#
# Actor: apimaestro/linkedin-posts-search-scraper-no-cookies (4.14 rating, no login)
# Requires: APIFY_API_KEY
# Pricing: ~$5 per 1,000 posts
#
# sort_by: "relevance" (default) or "date_posted"
#
# Examples:
#   ./search_linkedin.sh "claude code broke production" 20 date_posted 6
#   ./search_linkedin.sh "ai agent guardrails" 20 date_posted 4
#   ./search_linkedin.sh "cursor deleted my code" 15 relevance 6
#
# Smart freshness: checks .search_log.json for last run time.
#
# Output: JSON array of posts with author, text, reactions, url

set -euo pipefail

usage() {
  echo "Usage: search_linkedin.sh <query> [total_posts] [sort_by] [max_age_hours]" >&2
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
MAX_AGE_HOURS="${4:-6}"

if ! [[ "${TOTAL}" =~ ^[0-9]+$ ]]; then
  echo "total_posts must be an integer: ${TOTAL}" >&2
  exit 1
fi

# Backward compatibility:
# If third arg is numeric (older call style), treat it as max_age_hours.
if [[ "${SORT}" =~ ^[0-9]+$ ]] && [[ $# -eq 3 ]]; then
  MAX_AGE_HOURS="${SORT}"
  SORT="date_posted"
fi

if [[ "${SORT}" != "relevance" && "${SORT}" != "date_posted" ]]; then
  echo "sort_by must be 'relevance' or 'date_posted': ${SORT}" >&2
  exit 1
fi

if ! [[ "${MAX_AGE_HOURS}" =~ ^[0-9]+$ ]] || [ "${MAX_AGE_HOURS}" -lt 1 ]; then
  echo "max_age_hours must be an integer >= 1: ${MAX_AGE_HOURS}" >&2
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

# Fetch raw results
RAW=$(curl -s "https://api.apify.com/v2/datasets/${DATASET_ID}/items?token=${APIFY_API_KEY}&format=json")
TOTAL_COUNT=$(echo "$RAW" | jq 'length')

# Log raw field names for first item (debugging)
echo "Raw fields sample: $(echo "$RAW" | jq -r '.[0] | keys | join(", ")' 2>/dev/null)" >&2

# Normalize output — actor returns flat camelCase fields.
# Known field names (as of 2026-02):
#   text/postText, authorName, authorHeadline, authorProfileUrl,
#   totalReactions/numLikes, totalComments/numComments, totalReposts/numShares,
#   postedAt/postedDate, postUrl/post_url
# WARNING: This actor frequently returns empty postUrl fields.
# Downstream consumers MUST NOT use unique_by(.url) — use
# unique_by(.text[0:100] + .author_name) instead.
RESULT=$(echo "$RAW" | jq --argjson max_age "${MAX_AGE_HOURS}" ' 
def abs_age_hours:
  if . == null or . == "" or . == "unknown" then null
  elif type == "number" then ((now - .) / 3600)
  elif test("^[0-9]+$") then ((now - (tonumber)) / 3600)
  elif test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T") then ((now - (fromdateiso8601? // now + 9999999)) / 3600)
  elif test("^[0-9]{4}-[0-9]{2}-[0-9]{2} ") then ((now - (((gsub(" "; "T") | gsub("\\+00:00$"; "Z")) | fromdateiso8601?) // now + 9999999)) / 3600)
  elif test("^[A-Za-z]{3} [A-Za-z]{3} [ 0-9][0-9] [0-9:]{8} [+-][0-9]{4} [0-9]{4}$") then ((now - (strptime("%a %b %d %H:%M:%S %z %Y") | mktime)) / 3600)
  else null
  end;

def rel_age_hours:
  if . == null or . == "" or . == "unknown" then null
  elif test("^[0-9]+[smhdw]$"; "i") then
    (capture("(?<n>[0-9]+)(?<u>[smhdw])") | (.n|tonumber) as $n | .u as $u |
      if ($u|ascii_downcase) == "s" then ($n / 3600)
      elif ($u|ascii_downcase) == "m" then ($n / 60)
      elif ($u|ascii_downcase) == "h" then $n
      elif ($u|ascii_downcase) == "d" then ($n * 24)
      else ($n * 24 * 7)
      end)
  elif test("^[0-9]+\\s*(sec|secs|second|seconds|min|mins|minute|minutes|hour|hours|hr|hrs|day|days|week|weeks|month|months)\\s*ago$"; "i") then
    (capture("(?<n>[0-9]+)\\s*(?<u>sec|secs|second|seconds|min|mins|minute|minutes|hour|hours|hr|hrs|day|days|week|weeks|month|months)\\s*ago") |
      (.n|tonumber) as $n | (.u|ascii_downcase) as $u |
      if ($u == "sec" or $u == "secs" or $u == "second" or $u == "seconds") then ($n / 3600)
      elif ($u == "min" or $u == "mins" or $u == "minute" or $u == "minutes") then ($n / 60)
      elif ($u == "hour" or $u == "hours" or $u == "hr" or $u == "hrs") then $n
      elif ($u == "day" or $u == "days") then ($n * 24)
      elif ($u == "week" or $u == "weeks") then ($n * 24 * 7)
      else ($n * 24 * 30)
      end)
  else null
  end;

[
  .[] | {
    author_name: (.authorName // .author_name // .name // "unknown"),
    author_headline: (.authorHeadline // .headline // .author_headline // ""),
    author_profile: (.authorProfileUrl // .profileUrl // .author_profile_url // ""),
    author_followers: (.authorFollowers // .followersCount // .followers // null),
    text: (.text // .postText // .content // .body // ""),
    reactions: (.totalReactions // .numLikes // .reactions // .likeCount // 0),
    comments: (.totalComments // .numComments // .comments // .commentCount // 0),
    reposts: (.totalReposts // .numShares // .reposts // .shareCount // 0),
    posted: (.postedAt // .postedDate // .publishedAt // .date // "unknown"),
    url: (.postUrl // .post_url // .url // .link // ""),
    _raw_id: (.id // .postId // .urn // null)
  }
  | ._age_hours = ((.posted | rel_age_hours) // (.posted | abs_age_hours))
  | ._engagement = ((.reactions // 0) + (.comments // 0) * 2 + (.reposts // 0) * 2)
  | select(._age_hours != null and ._age_hours >= 0 and ._age_hours <= $max_age)
  | .age_hours = ((._age_hours * 10 | floor) / 10)
  | .recency_bucket = (
      if ._age_hours <= 2 then "0-2h"
      elif ._age_hours <= 4 then "2-4h"
      else "4-6h"
      end
    )
  | del(._age_hours, ._engagement)
] | sort_by(.age_hours, -.reactions, -.comments, -.reposts)')

RESULT_COUNT=$(echo "$RESULT" | jq 'length')
EMPTY_URLS=$(echo "$RESULT" | jq '[.[] | select(.url == "" or .url == null)] | length')
FILTERED_OUT=$((TOTAL_COUNT - RESULT_COUNT))
echo "Found ${RESULT_COUNT}/${TOTAL_COUNT} LinkedIn posts within last ${MAX_AGE_HOURS}h (${EMPTY_URLS} with empty URLs, dropped ${FILTERED_OUT})" >&2

if [ "$EMPTY_URLS" -gt 0 ]; then
  echo "WARNING: ${EMPTY_URLS}/${RESULT_COUNT} posts have empty URLs. Use text+author dedup, not URL dedup." >&2
fi

# Update search log
"${SCRIPT_DIR}/search_log.sh" set linkedin "$SEARCH_KEY" "$RESULT_COUNT"

echo "$RESULT"
