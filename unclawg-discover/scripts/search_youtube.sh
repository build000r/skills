#!/bin/bash
# Search YouTube for small creators posting about a topic.
# Usage: ./search_youtube.sh <query> [max_days_ago] [max_results]
#
# Requires: YOUTUBE_API_KEY env var
# If empty: export YOUTUBE_API_KEY=$(grep 'YOUTUBE_API_KEY' ~/.zshrc | grep -o '"[^"]*"' | tr -d '"')
#
# Examples:
#   ./search_youtube.sh "customer interview workflow" 30 20
#   ./search_youtube.sh "small business automation" 60 15
#   ./search_youtube.sh "freelancer operations stack" 30 20
#
# Smart freshness: checks .search_log.json for last run time.
#   - First-time query: uses max_days_ago (default: 7)
#   - Repeat query: uses last run timestamp as publishedAfter
#
# Output: JSON with video title, channel, view count, subscriber count

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

QUERY="${1:?Usage: search_youtube.sh <query> [max_days_ago] [max_results]}"
DAYS_AGO="${2:-7}"
MAX_RESULTS="${3:-20}"

if [ -z "$YOUTUBE_API_KEY" ]; then
  export YOUTUBE_API_KEY=$(grep 'YOUTUBE_API_KEY' ~/.zshrc | grep -o '"[^"]*"' | tr -d '"')
fi

if [ -z "$YOUTUBE_API_KEY" ]; then
  echo '{"error": "YOUTUBE_API_KEY not set. Add to ~/.zshrc: export YOUTUBE_API_KEY=\"your-key\""}'
  exit 1
fi

# Check search log for freshness — YouTube supports native date filtering
SINCE=$("${SCRIPT_DIR}/search_log.sh" get youtube "$QUERY")

if [ "$SINCE" = "none" ]; then
  # First-time search: use days_ago param (default 7)
  PUBLISHED_AFTER=$(date -u -v-${DAYS_AGO}d +"%Y-%m-%dT00:00:00Z" 2>/dev/null || date -u -d "${DAYS_AGO} days ago" +"%Y-%m-%dT00:00:00Z")
  echo "First-time search, using ${DAYS_AGO}-day window (since ${PUBLISHED_AFTER})" >&2
else
  # Refresh: use last run timestamp directly
  PUBLISHED_AFTER="$SINCE"
  echo "Refresh search, fetching since ${PUBLISHED_AFTER}" >&2
fi

ENCODED_QUERY=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$QUERY'))")

# Step 1: Search for videos
SEARCH_RESULT=$(curl -s "https://www.googleapis.com/youtube/v3/search?part=snippet&q=${ENCODED_QUERY}&type=video&order=date&maxResults=${MAX_RESULTS}&publishedAfter=${PUBLISHED_AFTER}&key=${YOUTUBE_API_KEY}")

# Extract video IDs and channel IDs
VIDEO_IDS=$(echo "$SEARCH_RESULT" | jq -r '[.items[].id.videoId] | join(",")')
CHANNEL_IDS=$(echo "$SEARCH_RESULT" | jq -r '[.items[].snippet.channelId] | unique | join(",")')

if [ -z "$VIDEO_IDS" ] || [ "$VIDEO_IDS" = "null" ]; then
  echo '{"results": [], "note": "No videos found"}'
  "${SCRIPT_DIR}/search_log.sh" set youtube "$QUERY" 0
  exit 0
fi

# Step 2: Get video statistics (view counts)
VIDEO_STATS=$(curl -s "https://www.googleapis.com/youtube/v3/videos?part=statistics&id=${VIDEO_IDS}&key=${YOUTUBE_API_KEY}")

# Step 3: Get channel statistics (subscriber counts)
CHANNEL_STATS=$(curl -s "https://www.googleapis.com/youtube/v3/channels?part=statistics,snippet&id=${CHANNEL_IDS}&key=${YOUTUBE_API_KEY}")

# Combine everything with jq
RESULT=$(echo "$SEARCH_RESULT" | jq --argjson vstats "$VIDEO_STATS" --argjson cstats "$CHANNEL_STATS" '
[.items[] | {
  title: .snippet.title,
  description: (.snippet.description[:200]),
  channel_name: .snippet.channelTitle,
  channel_id: .snippet.channelId,
  video_id: .id.videoId,
  published: .snippet.publishedAt,
  video_url: ("https://youtube.com/watch?v=" + .id.videoId),
  channel_url: ("https://youtube.com/channel/" + .snippet.channelId),
  view_count: ([$vstats.items[] | select(.id == .id)] | first | .statistics.viewCount // "unknown"),
  subscriber_count: ([$cstats.items[] | select(.id == .snippet.channelId)] | first | .statistics.subscriberCount // "unknown")
}] | sort_by(.subscriber_count | tonumber? // 999999)')

RESULT_COUNT=$(echo "$RESULT" | jq 'length')

# Update search log
"${SCRIPT_DIR}/search_log.sh" set youtube "$QUERY" "$RESULT_COUNT"

echo "$RESULT"
