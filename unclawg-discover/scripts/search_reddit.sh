#!/bin/bash
# Search Reddit subreddits for AI agent builders with safety/approval pain.
# Usage: ./search_reddit.sh <query> <subreddit> [time_filter] [limit]
#
# Examples:
#   ./search_reddit.sh "ai agent guardrails" LocalLLaMA week 25
#   ./search_reddit.sh "trading bot approval" algotrading month 25
#   ./search_reddit.sh "agent went rogue" programming week 25
#
# Smart freshness: checks .search_log.json for last run time.
#   - First-time query: uses time_filter as-is (default: week)
#   - Repeat query: filters results to only posts newer than last run
#
# Output: JSON array of posts with title, author, score, url, selftext preview

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

QUERY="${1:?Usage: search_reddit.sh <query> <subreddit> [time_filter] [limit]}"
SUBREDDIT="${2:?Usage: search_reddit.sh <query> <subreddit> [time_filter] [limit]}"
TIME_FILTER="${3:-week}"
LIMIT="${4:-25}"

# Check search log for freshness
SEARCH_KEY="${SUBREDDIT}:${QUERY}"
SINCE=$("${SCRIPT_DIR}/search_log.sh" get reddit "$SEARCH_KEY")

if [ "$SINCE" = "none" ]; then
  echo "First-time search for '${QUERY}' in r/${SUBREDDIT}, using t=${TIME_FILTER}" >&2
else
  echo "Refresh search, filtering to posts since ${SINCE}" >&2
fi

# URL-encode the query safely (handles apostrophes and shell-sensitive chars)
ENCODED_QUERY=$(python3 - "$QUERY" <<'PY'
import sys
import urllib.parse

print(urllib.parse.quote(sys.argv[1]))
PY
)

URL="https://www.reddit.com/r/${SUBREDDIT}/search.json?q=${ENCODED_QUERY}&sort=relevance&t=${TIME_FILTER}&limit=${LIMIT}&restrict_sr=on"

if [ "$SINCE" = "none" ]; then
  RESULT=$(curl -s -H "User-Agent: FindCustomersResearch/1.0" "$URL" | jq '[
    .data.children[] | .data | {
      title,
      author,
      score,
      num_comments,
      created_utc: (.created_utc | todate),
      url: ("https://reddit.com" + .permalink),
      selftext_preview: (.selftext[:300])
    }
  ] | sort_by(-.score)')
else
  RESULT=$(curl -s -H "User-Agent: FindCustomersResearch/1.0" "$URL" | jq --arg since "$SINCE" '[
    .data.children[] | .data |
    select((.created_utc | todate) > $since) |
    {
      title,
      author,
      score,
      num_comments,
      created_utc: (.created_utc | todate),
      url: ("https://reddit.com" + .permalink),
      selftext_preview: (.selftext[:300])
    }
  ] | sort_by(-.score)')
fi

RESULT_COUNT=$(echo "$RESULT" | jq 'length')

# Update search log
"${SCRIPT_DIR}/search_log.sh" set reddit "$SEARCH_KEY" "$RESULT_COUNT"

echo "$RESULT"
