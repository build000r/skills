#!/bin/bash
# Mine Instagram comments from target health profiles to find engagement opportunities.
# Two-step: scrape recent posts from curated profiles, then extract comments.
# Output is POST-LEVEL: each post with its customer-signal comment count + samples.
#
# Usage: ./search_instagram_comments.sh <profile1> [profile2] ... [--newer-than TIMEFRAME] [--max-posts-per-profile N]
#
# Requires: APIFY_API_KEY env var
#
# Examples:
#   ./search_instagram_comments.sh drmaryhaire perimenopause.hub
#   ./search_instagram_comments.sh drmaryhaire --newer-than "3 days"
#   ./search_instagram_comments.sh momfatigue burnoutmomrecovery --newer-than "1 week"
#   ./search_instagram_comments.sh drangelalucterhand healthwithkelsey --max-posts-per-profile 3
#
# Default --newer-than: uses search log (since last run), or "7 days" for first-time.
# Default --max-posts-per-profile: 3 (prevents any single profile from dominating results)
#
# Step 1: apify~instagram-profile-scraper (returns latestPosts with URLs + timestamps)
# Step 2: apify~instagram-comment-scraper (extracts comments from individual post URLs)
#
# Output: JSON array of POSTS, each with:
#   - post_url, post_owner, post_caption, post_likes, post_comments (total)
#   - customer_signal_count (how many comments contain health pain-point language)
#   - sample_comments (up to 5 health-signal comments with commenter + text)
# Sorted by customer_signal_count (highest first).
# The POST is the engagement target — comment there to reach real customers in the thread.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Parse args: profiles and optional --newer-than, --max-posts-per-profile
PROFILES=()
NEWER_THAN=""
MAX_POSTS_PER_PROFILE=3
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
    *)
      PROFILES+=("$1")
      shift
      ;;
  esac
done

if [ ${#PROFILES[@]} -eq 0 ]; then
  echo '{"error": "No profiles provided. Usage: search_instagram_comments.sh <profile1> [profile2] ... [--newer-than TIMEFRAME]"}'
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
  SINCE=$("${SCRIPT_DIR}/search_log.sh" get instagram-comments "${PROFILES[0]}")
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

# Build usernames JSON array for the post scraper
USERNAMES_JSON=$(printf '%s\n' "${PROFILES[@]}" | jq -R . | jq -s .)

echo "=== STEP 1: Scraping recent posts from ${#PROFILES[@]} profiles ===" >&2

# Check for reusable cached profile dataset
CACHED_PROFILE_DS=$("${SCRIPT_DIR}/search_log.sh" get-dataset instagram-profiles "${PROFILES[0]}")
POST_DATASET_ID=""

if [ "$CACHED_PROFILE_DS" != "none" ]; then
  CACHE_STATUS=$("${SCRIPT_DIR}/search_log.sh" check-dataset "$CACHED_PROFILE_DS")
  if [ "$CACHE_STATUS" = "valid" ]; then
    echo "Reusing cached profile dataset ${CACHED_PROFILE_DS} (skipping profile scraper run)" >&2
    POST_DATASET_ID="$CACHED_PROFILE_DS"
  else
    echo "Cached profile dataset expired, starting new run" >&2
  fi
fi

if [ -z "$POST_DATASET_ID" ]; then
  # No cached dataset — start a new profile scraper run
  POST_RUN_RESPONSE=$(curl -s -X POST \
    "https://api.apify.com/v2/acts/apify~instagram-profile-scraper/runs?token=${APIFY_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{
      \"usernames\": ${USERNAMES_JSON}
    }")

  POST_RUN_ID=$(echo "$POST_RUN_RESPONSE" | jq -r '.data.id')

  if [ "$POST_RUN_ID" = "null" ] || [ -z "$POST_RUN_ID" ]; then
    echo '{"error": "Failed to start post scraper run", "response": '"$POST_RUN_RESPONSE"'}'
    exit 1
  fi

  echo "Waiting for post scraper run ${POST_RUN_ID}..." >&2

  # Poll post scraper (max 180 seconds — profile scraping can be slower)
  POST_STATUS=""
  for i in $(seq 1 36); do
    sleep 5
    POST_STATUS=$(curl -s "https://api.apify.com/v2/actor-runs/${POST_RUN_ID}?token=${APIFY_API_KEY}" | jq -r '.data.status')
    if [ "$POST_STATUS" = "SUCCEEDED" ]; then
      break
    elif [ "$POST_STATUS" = "FAILED" ] || [ "$POST_STATUS" = "ABORTED" ]; then
      echo "{\"error\": \"Post scraper run ${POST_STATUS}\", \"run_id\": \"${POST_RUN_ID}\"}"
      exit 1
    fi
    echo "  Post scraper: ${POST_STATUS}..." >&2
  done

  if [ "$POST_STATUS" != "SUCCEEDED" ]; then
    echo "{\"error\": \"Post scraper timed out after 180s\", \"last_status\": \"${POST_STATUS}\", \"run_id\": \"${POST_RUN_ID}\"}"
    exit 1
  fi

  POST_DATASET_ID=$(curl -s "https://api.apify.com/v2/actor-runs/${POST_RUN_ID}?token=${APIFY_API_KEY}" | jq -r '.data.defaultDatasetId')

  # Cache the profile dataset for reuse
  for P in "${PROFILES[@]}"; do
    "${SCRIPT_DIR}/search_log.sh" set instagram-profiles "$P" 0 "$POST_DATASET_ID"
  done
fi

POST_DATA=$(curl -s "https://api.apify.com/v2/datasets/${POST_DATASET_ID}/items?token=${APIFY_API_KEY}&format=json")

# Calculate freshness cutoff as ISO timestamp for jq filtering
# ONLY_NEWER is like "7 days" or "1 day" — extract the number
DAYS_NUM=$(echo "$ONLY_NEWER" | grep -o '[0-9]*')
DAYS_NUM=${DAYS_NUM:-7}
CUTOFF=$(date -u -v-${DAYS_NUM}d +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -d "${DAYS_NUM} days ago" +"%Y-%m-%dT%H:%M:%SZ")
echo "Filtering posts newer than: ${CUTOFF}" >&2

# Report any profiles that returned errors
FAILED_PROFILES=$(echo "$POST_DATA" | jq -r '[.[] | select(.error != null) | .username // .url] | join(", ")')
if [ -n "$FAILED_PROFILES" ] && [ "$FAILED_PROFILES" != "" ]; then
  echo "  Warning: could not access profiles: ${FAILED_PROFILES}" >&2
fi

# Extract post URLs from latestPosts arrays, filtered by timestamp.
# Cap at MAX_POSTS_PER_PROFILE per profile to prevent any single account from dominating.
# Posts are sorted newest-first per profile, so the cap keeps the freshest content.
echo "Max posts per profile: ${MAX_POSTS_PER_PROFILE}" >&2
POST_URLS=$(echo "$POST_DATA" | jq --arg cutoff "$CUTOFF" --argjson maxpp "$MAX_POSTS_PER_PROFILE" '[
  .[] | select(.error == null) |
  [.latestPosts[]? | select(.timestamp > $cutoff)] |
  sort_by(.timestamp) | reverse | .[:$maxpp][] | .url
] | unique')
POST_COUNT=$(echo "$POST_URLS" | jq 'length')

# Extract post metadata for enriching output (caption, likes, comments count)
# Same per-profile cap applied here
POST_META=$(echo "$POST_DATA" | jq --arg cutoff "$CUTOFF" --argjson maxpp "$MAX_POSTS_PER_PROFILE" '[
  .[] | select(.error == null) | . as $profile |
  [.latestPosts[]? | select(.timestamp > $cutoff)] |
  sort_by(.timestamp) | reverse | .[:$maxpp][] | {
    url: .url,
    owner: $profile.username,
    caption: (.caption[:300] // ""),
    likes: (.likesCount // 0),
    comments: (.commentsCount // 0),
    timestamp: .timestamp
  }
]')

echo "Found ${POST_COUNT} recent posts" >&2

if [ "$POST_COUNT" = "0" ] || [ "$POST_COUNT" = "null" ]; then
  echo '{"posts_found": 0, "comments": [], "note": "No recent posts found for these profiles"}'
  for P in "${PROFILES[@]}"; do
    "${SCRIPT_DIR}/search_log.sh" set instagram-comments "$P" 0 ""
  done
  exit 0
fi

echo "=== STEP 2: Extracting comments from ${POST_COUNT} posts ===" >&2

# Step 2: Scrape comments from those posts
# POST_URLS is already a JSON array of URL strings — pass directly
DIRECT_URLS="$POST_URLS"

COMMENT_RUN_RESPONSE=$(curl -s -X POST \
  "https://api.apify.com/v2/acts/apify~instagram-comment-scraper/runs?token=${APIFY_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{
    \"directUrls\": ${DIRECT_URLS},
    \"resultsLimit\": 100
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
# Args: $posts (post metadata array)

# Step 1: Extract valid comments with health-signal flag
[.[] | select(.error == null) | {
  commenter: (.ownerUsername // .username // "unknown"),
  text: (.text // .body // ""),
  timestamp: (.timestamp // .created_at // ""),
  likes: (.likesCount // .likes // 0),
  post_url: (.postUrl // .inputUrl // "")
}] |

# Step 2: Split into signal vs total, grouped by post
group_by(.post_url) |

# Step 3: For each post, count signals and build summary
[.[] |
  . as $all_comments |
  ($all_comments[0].post_url) as $url |

  # Find matching post metadata
  ($posts | map(select(.url == $url)) | .[0] // {}) as $meta |

  # Filter for health pain-point keywords
  [$all_comments[] | select(
    .text | test(
      "hair.*(loss|fall|thin)|fatigue|exhausted|tired all|brain fog|can.t focus|can.t think|perimenopause|menopause|thyroid|mineral|magnesium|supplement.*(not|didn|help)|doctor.*fine|bloodwork.*normal|labs.*normal|what helped|any(one|body) tried|same here|me too|going through this|how did you|what did you|struggling|symptoms|diagnosed|flare";
      "i"
    )
  )] as $signals |

  # Only include posts that have at least 1 signal comment
  select(($signals | length) > 0) |

  {
    post_url: $url,
    post_owner: ($meta.owner // "unknown"),
    post_caption: ($meta.caption // ""),
    post_likes: ($meta.likes // 0),
    post_comments_total: ($meta.comments // ($all_comments | length)),
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

RESULT=$(echo "$ALL_COMMENTS" | jq --argjson posts "$POST_META" -f "$JQ_SCRIPT")
rm -f "$JQ_SCRIPT"

SIGNAL_POSTS=$(echo "$RESULT" | jq 'length')
TOTAL_SIGNALS=$(echo "$RESULT" | jq '[.[].customer_signal_count] | add // 0')

echo "Found ${SIGNAL_POSTS} posts with customer signals (${TOTAL_SIGNALS} signal comments total)" >&2

# Update search log for each profile (with comment dataset_id for future reuse)
for P in "${PROFILES[@]}"; do
  "${SCRIPT_DIR}/search_log.sh" set instagram-comments "$P" "$TOTAL_SIGNALS" "$COMMENT_DATASET_ID"
done

echo "$RESULT"
