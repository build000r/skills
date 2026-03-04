#!/bin/bash
# Search Indeed Jobs via Apify Indeed Scraper.
# Usage: ./search_indeed.sh <position> [location] [results_limit] [country]
#
# Requires: APIFY_API_KEY env var
# Actor: https://apify.com/misceres/indeed-scraper
# Pricing: ~$5 per 1,000 results
#
# Examples:
#   ./search_indeed.sh "contract react developer" "remote" 20
#   ./search_indeed.sh "freelance developer" "New York" 15 US
#   ./search_indeed.sh "short term developer" "" 20
#
# Output: JSON array of job listings with company, title, location, salary, url

POSITION="${1:?Usage: search_indeed.sh <position> [location] [results_limit] [country]}"
LOCATION="${2:-}"
LIMIT="${3:-20}"
COUNTRY="${4:-US}"

if [ -z "$APIFY_API_KEY" ]; then
  export APIFY_API_KEY=$(grep 'APIFY_API_KEY' ~/.zshrc | grep -o '"[^"]*"' | tr -d '"')
fi

if [ -z "$APIFY_API_KEY" ]; then
  echo '{"error": "APIFY_API_KEY not set. Sign up at https://apify.com and add to ~/.zshrc: export APIFY_API_KEY=\"your-key\""}'
  exit 1
fi

# Build input JSON
INPUT="{
  \"position\": \"${POSITION}\",
  \"country\": \"${COUNTRY}\",
  \"maxItems\": ${LIMIT}"

if [ -n "$LOCATION" ]; then
  INPUT="${INPUT}, \"location\": \"${LOCATION}\""
fi

INPUT="${INPUT}}"

# Start the scraper run
RUN_RESPONSE=$(curl -s -X POST \
  "https://api.apify.com/v2/acts/misceres~indeed-scraper/runs?token=${APIFY_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "$INPUT")

RUN_ID=$(echo "$RUN_RESPONSE" | jq -r '.data.id')

if [ "$RUN_ID" = "null" ] || [ -z "$RUN_ID" ]; then
  echo '{"error": "Failed to start Apify run", "response": '"$RUN_RESPONSE"'}'
  exit 1
fi

echo "Waiting for Apify run ${RUN_ID}..." >&2

# Poll until complete (max 180 seconds — Indeed can be slower)
for i in $(seq 1 36); do
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

# Normalize output
curl -s "https://api.apify.com/v2/datasets/${DATASET_ID}/items?token=${APIFY_API_KEY}&format=json" | jq '[
  .[] | {
    title: (.positionName // .title // .jobTitle // "unknown"),
    company: (.company // .companyName // "unknown"),
    company_url: (.companyUrl // .externalApplyLink // ""),
    location: (.location // .jobLocation // "unknown"),
    location_type: (.locationType // .workType // ""),
    salary: (.salary // .salaryRange // ""),
    salary_min: (.salaryMin // null),
    salary_max: (.salaryMax // null),
    job_type: (.jobType // .employmentType // ""),
    posted: (.postedAt // .datePosted // .date // "unknown"),
    url: (.url // .externalApplyLink // ""),
    description_snippet: (.description // "" | tostring | .[0:300])
  }
]'
