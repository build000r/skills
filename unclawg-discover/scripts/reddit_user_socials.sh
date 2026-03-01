#!/bin/bash
# Check a Reddit user's profile for social media links.
# Usage: ./reddit_user_socials.sh <username>
#
# Returns: JSON with user karma, account age, and any linked social accounts

USERNAME="${1:?Usage: reddit_user_socials.sh <username>}"

curl -s -H "User-Agent: OpenClawDiscovery/1.0" \
  "https://www.reddit.com/user/${USERNAME}/about.json" | jq '{
    name: .data.name,
    total_karma: .data.total_karma,
    created: (.data.created_utc | todate),
    has_verified_email: .data.has_verified_email,
    subreddit_display_name: .data.subreddit.display_name_prefixed,
    subreddit_title: .data.subreddit.title,
    public_description: .data.subreddit.public_description
  }'
