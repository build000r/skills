#!/bin/bash
# Mine TikTok comments from target health profiles to find engagement opportunities.
# Two-step: scrape recent videos from curated profiles, then extract comments.
# Output is POST-LEVEL: each video with its customer-signal comment count + samples.
#
# Usage: ./search_tiktok_comments.sh <profile1> [profile2] ... [--newer-than TIMEFRAME] [--max-posts-per-profile N]
#
# Requires: APIFY_API_KEY env var
#
# Examples:
#   ./search_tiktok_comments.sh drstaceysims perimenopausecoach
#   ./search_tiktok_comments.sh drstaceysims --newer-than "3 days"
#   ./search_tiktok_comments.sh thyroidhealing menopausehealth --max-posts-per-profile 5
#
# Default --newer-than: uses search log (since last run), or "7 days" for first-time.
# Default --max-posts-per-profile: 3 (prevents any single profile from dominating results)
#
# Step 1: clockworks~tiktok-scraper (profiles mode — returns recent videos with URLs)
# Step 2: clockworks~tiktok-comments-scraper (extracts comments from individual video URLs)
#
# Output: JSON array of VIDEOS, each with:
#   - video_url, video_author, video_description, video_likes, video_comments (total)
#   - customer_signal_count (how many comments contain health pain-point language)
#   - sample_comments (up to 5 health-signal comments with commenter + text)
# Sorted by customer_signal_count (highest first).
# The VIDEO is the engagement target — comment there to reach real customers in the thread.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Parse args: profiles and optional --newer-than, --max-posts-per-profile
PROFILES=()
NEWER_THAN=""
MAX_POSTS_PER_PROFILE=3
COMMENTS_PER_POST=100
while [ $# -gt 0 ]; do
  case "$1" in
    --newer-than)
      NEWER_THAN="$2"
      shift 2
      ;;
    --max-posts-per-profile)
      MAX_POSTS_PER_PROFILE="$2"
      shift 2
      ;;
    --comments-per-post)
      COMMENTS_PER_POST="$2"
      shift 2
      ;;
    *)
      PROFILES+=("$1")
      shift
      ;;
  esac
done

if [ ${#PROFILES[@]} -eq 0 ]; then
  echo '{"error": "No profiles provided. Usage: search_tiktok_comments.sh <profile1> [profile2] ... [--newer-than TIMEFRAME]"}'
  exit 1
fi

if [ -z "$APIFY_API_KEY" ]; then
  export APIFY_API_KEY=$(grep 'APIFY_API_KEY' ~/.zshrc | grep -o '"[^"]*"' | tr -d '"')
fi

if [ -z "$APIFY_API_KEY" ]; then
  echo '{"error": "APIFY_API_KEY not set. Sign up at https://apify.com and add to ~/.zshrc: export APIFY_API_KEY=\"your-key\""}'
  exit 1
fi

# Determine freshness window from search log or --newer-than flag
if [ -n "$NEWER_THAN" ]; then
  ONLY_NEWER="$NEWER_THAN"
  echo "Using explicit --newer-than: ${ONLY_NEWER}" >&2
else
  # Check search log for the first profile as proxy
  SINCE=$("${SCRIPT_DIR}/search_log.sh" get tiktok-comments "${PROFILES[0]}")
  if [ "$SINCE" = "none" ]; then
    ONLY_NEWER="7 days"
    echo "First-time comment mining, using 7-day window" >&2
  else
    # Calculate relative time from last run
    NOW_EPOCH=$(date -u +%s)
    SINCE_EPOCH=$(date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$SINCE" +%s 2>/dev/null || date -u -d "$SINCE" +%s 2>/dev/null || echo 0)
    DAYS_AGO=$(( (NOW_EPOCH - SINCE_EPOCH) / 86400 ))
    if [ "$DAYS_AGO" -le 0 ]; then
      ONLY_NEWER="1 day"
    else
      ONLY_NEWER="${DAYS_AGO} days"
    fi
    echo "Refresh: last run ${DAYS_AGO}d ago, using ${ONLY_NEWER} window" >&2
  fi
fi

# Build profiles JSON array for the TikTok scraper
PROFILES_JSON=$(printf '%s\n' "${PROFILES[@]}" | jq -R . | jq -s .)

echo "=== STEP 1: Scraping recent videos from ${#PROFILES[@]} profiles ===" >&2

# Check for reusable cached profile dataset
CACHED_PROFILE_DS=$("${SCRIPT_DIR}/search_log.sh" get-dataset tiktok-profiles "${PROFILES[0]}")
VIDEO_DATASET_ID=""

if [ "$CACHED_PROFILE_DS" != "none" ]; then
  CACHE_STATUS=$("${SCRIPT_DIR}/search_log.sh" check-dataset "$CACHED_PROFILE_DS")
  if [ "$CACHE_STATUS" = "valid" ]; then
    echo "Reusing cached profile dataset ${CACHED_PROFILE_DS} (skipping profile scraper run)" >&2
    VIDEO_DATASET_ID="$CACHED_PROFILE_DS"
  else
    echo "Cached profile dataset expired, starting new run" >&2
  fi
fi

if [ -z "$VIDEO_DATASET_ID" ]; then
  # No cached dataset — start a new TikTok scraper run (profiles mode)
  # Uses clockworks~tiktok-scraper (general-purpose, 5K+ monthly users)
  # NOT clockworks~tiktok-profile-scraper (has proxy issues as of Feb 2026)
  VIDEO_RUN_RESPONSE=$(curl -s -X POST \
    "https://api.apify.com/v2/acts/clockworks~tiktok-scraper/runs?token=${APIFY_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{
      \"profiles\": ${PROFILES_JSON},
      \"resultsPerPage\": $((MAX_POSTS_PER_PROFILE * 2))
    }")

  VIDEO_RUN_ID=$(echo "$VIDEO_RUN_RESPONSE" | jq -r '.data.id')

  if [ "$VIDEO_RUN_ID" = "null" ] || [ -z "$VIDEO_RUN_ID" ]; then
    echo '{"error": "Failed to start video scraper run", "response": '"$VIDEO_RUN_RESPONSE"'}'
    exit 1
  fi

  echo "Waiting for video scraper run ${VIDEO_RUN_ID}..." >&2

  # Poll video scraper (max 180 seconds — profile scraping can be slower)
  VIDEO_STATUS=""
  for i in $(seq 1 36); do
    sleep 5
    VIDEO_STATUS=$(curl -s "https://api.apify.com/v2/actor-runs/${VIDEO_RUN_ID}?token=${APIFY_API_KEY}" | jq -r '.data.status')
    if [ "$VIDEO_STATUS" = "SUCCEEDED" ]; then
      break
    elif [ "$VIDEO_STATUS" = "FAILED" ] || [ "$VIDEO_STATUS" = "ABORTED" ]; then
      echo "{\"error\": \"Video scraper run ${VIDEO_STATUS}\", \"run_id\": \"${VIDEO_RUN_ID}\"}"
      exit 1
    fi
    echo "  Video scraper: ${VIDEO_STATUS}..." >&2
  done

  if [ "$VIDEO_STATUS" != "SUCCEEDED" ]; then
    echo "{\"error\": \"Video scraper timed out after 180s\", \"last_status\": \"${VIDEO_STATUS}\", \"run_id\": \"${VIDEO_RUN_ID}\"}"
    exit 1
  fi

  VIDEO_DATASET_ID=$(curl -s "https://api.apify.com/v2/actor-runs/${VIDEO_RUN_ID}?token=${APIFY_API_KEY}" | jq -r '.data.defaultDatasetId')

  # Cache the profile dataset for reuse
  for P in "${PROFILES[@]}"; do
    "${SCRIPT_DIR}/search_log.sh" set tiktok-profiles "$P" 0 "$VIDEO_DATASET_ID"
  done
fi

VIDEO_DATA=$(curl -s "https://api.apify.com/v2/datasets/${VIDEO_DATASET_ID}/items?token=${APIFY_API_KEY}&format=json")

# Calculate freshness cutoff as ISO timestamp for jq filtering
DAYS_NUM=$(echo "$ONLY_NEWER" | grep -o '[0-9]*')
DAYS_NUM=${DAYS_NUM:-7}
CUTOFF=$(date -u -v-${DAYS_NUM}d +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -d "${DAYS_NUM} days ago" +"%Y-%m-%dT%H:%M:%SZ")
echo "Filtering videos newer than: ${CUTOFF}" >&2

# Report any profiles that returned errors
FAILED_PROFILES=$(echo "$VIDEO_DATA" | jq -r '[.[] | select(.error != null) | .input // .url] | join(", ")')
if [ -n "$FAILED_PROFILES" ] && [ "$FAILED_PROFILES" != "" ]; then
  echo "  Warning: could not access profiles: ${FAILED_PROFILES}" >&2
fi

# Extract video URLs from results, filtered by timestamp.
# Cap at MAX_POSTS_PER_PROFILE per profile.
# TikTok scraper output uses: webVideoUrl, createTimeISO, authorMeta.name
echo "Max posts per profile: ${MAX_POSTS_PER_PROFILE}" >&2
VIDEO_URLS=$(echo "$VIDEO_DATA" | jq --arg cutoff "$CUTOFF" --argjson maxpp "$MAX_POSTS_PER_PROFILE" '[
  .[] | select(.error == null) | select((.createTimeISO // "") > $cutoff)
] | group_by(.authorMeta.name // .input) | [
  .[] | sort_by(.createTimeISO) | reverse | .[:$maxpp][]
] | [.[].webVideoUrl] | unique')
VIDEO_COUNT=$(echo "$VIDEO_URLS" | jq 'length')

# Extract video metadata for enriching output
VIDEO_META=$(echo "$VIDEO_DATA" | jq --arg cutoff "$CUTOFF" --argjson maxpp "$MAX_POSTS_PER_PROFILE" '[
  .[] | select(.error == null) | select((.createTimeISO // "") > $cutoff)
] | group_by(.authorMeta.name // .input) | [
  .[] | sort_by(.createTimeISO) | reverse | .[:$maxpp][]
] | [.[] | {
  url: .webVideoUrl,
  owner: (.authorMeta.name // .input // "unknown"),
  description: ((.text // .desc // "")[:300]),
  likes: (.diggCount // 0),
  comments: (.commentCount // 0),
  shares: (.shareCount // 0),
  views: (.playCount // 0),
  timestamp: (.createTimeISO // "")
}]')

echo "Found ${VIDEO_COUNT} recent videos" >&2

if [ "$VIDEO_COUNT" = "0" ] || [ "$VIDEO_COUNT" = "null" ]; then
  echo '{"videos_found": 0, "results": [], "note": "No recent videos found for these profiles. Check that handles exist on TikTok."}'
  for P in "${PROFILES[@]}"; do
    "${SCRIPT_DIR}/search_log.sh" set tiktok-comments "$P" 0 ""
  done
  exit 0
fi

echo "=== STEP 2: Extracting comments from ${VIDEO_COUNT} videos ===" >&2

# Step 2: Scrape comments from those videos
# Uses clockworks~tiktok-comments-scraper (21K+ users, 831K runs/month)
COMMENT_RUN_RESPONSE=$(curl -s -X POST \
  "https://api.apify.com/v2/acts/clockworks~tiktok-comments-scraper/runs?token=${APIFY_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{
    \"postURLs\": ${VIDEO_URLS},
    \"commentsPerPost\": ${COMMENTS_PER_POST},
    \"maxRepliesPerComment\": 0
  }")

COMMENT_RUN_ID=$(echo "$COMMENT_RUN_RESPONSE" | jq -r '.data.id')

if [ "$COMMENT_RUN_ID" = "null" ] || [ -z "$COMMENT_RUN_ID" ]; then
  echo '{"error": "Failed to start comment scraper run", "response": '"$COMMENT_RUN_RESPONSE"'}'
  exit 1
fi

echo "Waiting for comment scraper run ${COMMENT_RUN_ID}..." >&2

# Poll comment scraper (max 180 seconds)
COMMENT_STATUS=""
for i in $(seq 1 36); do
  sleep 5
  COMMENT_STATUS=$(curl -s "https://api.apify.com/v2/actor-runs/${COMMENT_RUN_ID}?token=${APIFY_API_KEY}" | jq -r '.data.status')
  if [ "$COMMENT_STATUS" = "SUCCEEDED" ]; then
    break
  elif [ "$COMMENT_STATUS" = "FAILED" ] || [ "$COMMENT_STATUS" = "ABORTED" ]; then
    echo "{\"error\": \"Comment scraper run ${COMMENT_STATUS}\", \"run_id\": \"${COMMENT_RUN_ID}\"}"
    exit 1
  fi
  echo "  Comment scraper: ${COMMENT_STATUS}..." >&2
done

if [ "$COMMENT_STATUS" != "SUCCEEDED" ]; then
  echo "{\"error\": \"Comment scraper timed out after 180s\", \"last_status\": \"${COMMENT_STATUS}\", \"run_id\": \"${COMMENT_RUN_ID}\"}"
  exit 1
fi

# Fetch comments
COMMENT_DATASET_ID=$(curl -s "https://api.apify.com/v2/actor-runs/${COMMENT_RUN_ID}?token=${APIFY_API_KEY}" | jq -r '.data.defaultDatasetId')
ALL_COMMENTS=$(curl -s "https://api.apify.com/v2/datasets/${COMMENT_DATASET_ID}/items?token=${APIFY_API_KEY}&format=json")

TOTAL_COMMENTS=$(echo "$ALL_COMMENTS" | jq '[.[] | select(.error == null)] | length')
echo "Total comments scraped: ${TOTAL_COMMENTS}" >&2

# Write the jq script to a temp file to avoid shell escaping issues
JQ_SCRIPT=$(mktemp)
cat > "$JQ_SCRIPT" << 'JQEOF'
# Args: $videos (video metadata array)

# Step 1: Extract valid comments with health-signal flag
# TikTok comment fields: uniqueId (commenter), text, diggCount (likes), videoWebUrl (post URL)
[.[] | select(.error == null) | {
  commenter: (.uniqueId // "unknown"),
  text: (.text // ""),
  timestamp: (.createTimeISO // ""),
  likes: (.diggCount // 0),
  video_url: (.videoWebUrl // .submittedVideoUrl // "")
}] |

# Step 2: Split into signal vs total, grouped by video
group_by(.video_url) |

# Step 3: For each video, count signals and build summary
[.[] |
  . as $all_comments |
  ($all_comments[0].video_url) as $url |

  # Find matching video metadata
  ($videos | map(select(.url == $url)) | .[0] // {}) as $meta |

  # Filter for health pain-point keywords (same regex as IG comment mining)
  [$all_comments[] | select(
    .text | test(
      "hair.*(loss|fall|thin)|fatigue|exhausted|tired all|brain fog|can.t focus|can.t think|perimenopause|menopause|thyroid|mineral|magnesium|supplement.*(not|didn|help)|doctor.*fine|bloodwork.*normal|labs.*normal|what helped|any(one|body) tried|same here|me too|going through this|how did you|what did you|struggling|symptoms|diagnosed|flare|weight.*(gain|won|plateau)|night sweats|hot flash|anxiety|insomnia|burnout|adrenal|cortisol|hormone|pcos|pmdd|gut.*(health|issue|problem)";
      "i"
    )
  )] as $signals |

  # Only include videos that have at least 1 signal comment
  select(($signals | length) > 0) |

  {
    video_url: $url,
    video_author: ($meta.owner // "unknown"),
    video_description: ($meta.description // ""),
    video_likes: ($meta.likes // 0),
    video_comments_total: ($meta.comments // ($all_comments | length)),
    video_views: ($meta.views // 0),
    customer_signal_count: ($signals | length),
    total_comments_scraped: ($all_comments | length),
    sample_comments: [$signals | sort_by(-.likes) | .[:5][] | {
      commenter: .commenter,
      text: (.text[:200]),
      likes: .likes
    }]
  }
] | sort_by(-.customer_signal_count)
JQEOF

RESULT=$(echo "$ALL_COMMENTS" | jq --argjson videos "$VIDEO_META" -f "$JQ_SCRIPT")
rm -f "$JQ_SCRIPT"

SIGNAL_VIDEOS=$(echo "$RESULT" | jq 'length')
TOTAL_SIGNALS=$(echo "$RESULT" | jq '[.[].customer_signal_count] | add // 0')

echo "Found ${SIGNAL_VIDEOS} videos with customer signals (${TOTAL_SIGNALS} signal comments total)" >&2

# Update search log for each profile
for P in "${PROFILES[@]}"; do
  "${SCRIPT_DIR}/search_log.sh" set tiktok-comments "$P" "$TOTAL_SIGNALS" "$COMMENT_DATASET_ID"
done

echo "$RESULT"
