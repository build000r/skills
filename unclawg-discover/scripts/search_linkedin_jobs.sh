#!/bin/bash
# Search LinkedIn Jobs via Apify Rapid LinkedIn Jobs Scraper (no cookies needed).
# Usage: ./search_linkedin_jobs.sh <query> [results_limit] [job_type]
#
# Requires: APIFY_API_KEY env var
# Actor: https://apify.com/worldunboxer/rapid-linkedin-scraper
#
# Job types: F=Full-time, P=Part-time, C=Contract, T=Temporary, I=Internship
#
# Examples:
#   ./search_linkedin_jobs.sh "react developer" 20
#   ./search_linkedin_jobs.sh "freelance developer" 20 C
#   ./search_linkedin_jobs.sh "contract frontend developer" 15
#
# Output: JSON array of job listings with company, title, location, url

QUERY="${1:?Usage: search_linkedin_jobs.sh <query> [results_limit] [job_type]}"
LIMIT="${2:-20}"
JOB_TYPE="${3:-}"  # C=Contract, F=Full-time, etc.

if [ -z "$APIFY_API_KEY" ]; then
  export APIFY_API_KEY=$(grep 'APIFY_API_KEY' ~/.zshrc | grep -o '"[^"]*"' | tr -d '"')
fi

if [ -z "$APIFY_API_KEY" ]; then
  echo '{"error": "APIFY_API_KEY not set. Sign up at https://apify.com and add to ~/.zshrc: export APIFY_API_KEY=\"your-key\""}'
  exit 1
fi

# Build LinkedIn search URL with filters
BASE_URL="https://www.linkedin.com/jobs/search/?keywords=$(echo "$QUERY" | sed 's/ /+/g')&sortBy=DD"

if [ -n "$JOB_TYPE" ]; then
  BASE_URL="${BASE_URL}&f_JT=${JOB_TYPE}"
fi

# Start the scraper run
RUN_RESPONSE=$(curl -s -X POST \
  "https://api.apify.com/v2/acts/worldunboxer~rapid-linkedin-scraper/runs?token=${APIFY_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{
    \"urls\": [\"${BASE_URL}\"],
    \"maxItems\": ${LIMIT}
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
curl -s "https://api.apify.com/v2/datasets/${DATASET_ID}/items?token=${APIFY_API_KEY}&format=json" | jq '[
  .[] | {
    title: (.title // .jobTitle // .job_title // "unknown"),
    company: (.companyName // .company // .organization // "unknown"),
    company_url: (.companyUrl // .companyLink // .company_url // ""),
    location: (.location // .jobLocation // .place // "unknown"),
    salary: (.salary // .salaryRange // .compensation // ""),
    job_type: (.employmentType // .jobType // .type // ""),
    posted: (.postedDate // .publishedAt // .date // "unknown"),
    url: (.url // .jobUrl // .link // ""),
    description_snippet: (.description // .jobDescription // "" | tostring | .[0:300])
  }
]'
