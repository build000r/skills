#!/bin/bash
# Search Hacker News via Algolia API (free, no key required).
# Usage: ./search_hn.sh <query> [days_back] [limit]
#
# Examples:
#   ./search_hn.sh "human in the loop AI agent" 7 25
#   ./search_hn.sh "autonomous agent guardrails" 14 20
#   ./search_hn.sh "trading bot" 7 15
#
# Smart freshness: checks .search_log.json for last run time.
#   - First-time query: fetches posts from last N days
#   - Repeat query: filters to posts newer than last run
#
# Output: JSON array of stories/comments with title, author, points, url

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

QUERY="${1:?Usage: search_hn.sh <query> [days_back] [limit]}"
DAYS_BACK="${2:-7}"
LIMIT="${3:-25}"

# Check search log for freshness
SEARCH_KEY="hn:${QUERY}"
SINCE=$("${SCRIPT_DIR}/search_log.sh" get hn "$SEARCH_KEY")

if [ "$SINCE" = "none" ]; then
  # First time: use days_back
  TIMESTAMP=$(date -v-${DAYS_BACK}d +%s 2>/dev/null || date -d "${DAYS_BACK} days ago" +%s)
  echo "First-time search for '${QUERY}' on HN, last ${DAYS_BACK} days" >&2
else
  # Refresh: use last run timestamp
  TIMESTAMP=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$SINCE" +%s 2>/dev/null || date -d "$SINCE" +%s)
  echo "Refresh search, filtering to posts since ${SINCE}" >&2
fi

# URL-encode the query safely (handles apostrophes and shell-sensitive chars)
ENCODED_QUERY=$(python3 - "$QUERY" <<'PY'
import sys
import urllib.parse

print(urllib.parse.quote(sys.argv[1]))
PY
)

# Search stories (posts)
STORIES=$(curl -s "https://hn.algolia.com/api/v1/search?query=${ENCODED_QUERY}&tags=story&numericFilters=created_at_i%3E${TIMESTAMP}&hitsPerPage=${LIMIT}" | jq '[
  .hits[] | {
    type: "story",
    title: .title,
    author: .author,
    points: .points,
    num_comments: .num_comments,
    created_at: .created_at,
    url: ("https://news.ycombinator.com/item?id=" + (.objectID | tostring)),
    story_url: .url
  }
] | sort_by(-.points)')

# Search comments (often where the real pain lives)
COMMENTS=$(curl -s "https://hn.algolia.com/api/v1/search?query=${ENCODED_QUERY}&tags=comment&numericFilters=created_at_i%3E${TIMESTAMP}&hitsPerPage=${LIMIT}" | jq '[
  .hits[] | {
    type: "comment",
    author: .author,
    points: (.points // 0),
    created_at: .created_at,
    comment_preview: (.comment_text[:300]),
    story_title: .story_title,
    url: ("https://news.ycombinator.com/item?id=" + (.objectID | tostring)),
    story_url: ("https://news.ycombinator.com/item?id=" + (.story_id | tostring))
  }
] | sort_by(-.points)')

# Merge stories + comments, sort by points
RESULT=$(echo "$STORIES $COMMENTS" | jq -s 'add | sort_by(-.points)')

RESULT_COUNT=$(echo "$RESULT" | jq 'length')

# Update search log
"${SCRIPT_DIR}/search_log.sh" set hn "$SEARCH_KEY" "$RESULT_COUNT"

echo "$RESULT"
