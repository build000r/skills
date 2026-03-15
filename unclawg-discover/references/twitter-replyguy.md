# Twitter/X Reply-Guy Discovery Strategy

Reference doc for discovering high-value reply targets on Twitter/X. Used by any agent persona doing reply-guy growth.

This file lives in the **skill** (how to find targets). The **soul** decides how to talk to them.

## Algorithm Signal Weights

| Action | Relative Weight | Notes |
|--------|----------------|-------|
| Reply | ~27x a retweet | Highest single signal |
| Reply that gets author response | ~75x a retweet | The holy grail — back-and-forth conversation |
| Quote tweet with commentary | ~2x a standard tweet | Independent distribution + context |
| Like | ~0.5x a retweet | Low weight — don't optimize for this |
| Retweet | 1x (baseline) | Decent but passive |
| Profile click | High | Hard to engineer, but strong signal |
| Dwell time | High | Threads and visual content win here |

## Discovery Target Criteria

### Account Selection (who to reply to)

Find tweets from accounts matching ALL of:
- **Follower count:** 5K-500K (sweet spot: 10K-100K — big enough for reach, small enough that replies aren't buried instantly)
- **Post frequency:** 2-5x/day (enough daily opportunities)
- **Reply behavior:** Author actually reads and responds to replies (enables the 75x signal)
- **Audience overlap:** Followers match the soul's target personas
- **Niche match:** Posts about topics the soul's personas care about

### Tweet Selection (which tweets to reply to)

From those accounts, surface tweets matching ALL of:
- **Freshness:** Posted within last 1-2 hours (early replies get top placement)
- **Reply count:** Under 30-50 replies (after this, new replies are buried)
- **Engagement trajectory:** Already gaining likes/engagement (signals it will be shown to more people)
- **Reply-worthy:** Has a clear hook for a funny, insightful, or challenging response
- **Not low-substance:** Skip "good morning" tweets, pure links, RT-bait

### Anti-Patterns (skip these)

- Tweets already at 50+ replies — you're buried
- Engagement bait with no substance ("like if you agree")
- Threads where the author is venting about something personal/sensitive
- Competitor accounts or their employees
- Political, medical, legal, financial topics
- Tweets from accounts that have blocked/muted the agent before

## Discovery Query Packs (template)

Adapt these per soul persona. Replace `{topic_terms}` with persona-specific keywords.

### High-Signal Queries

```yaml
twitter_replyguy:
  # Persona-mapped queries — match to soul personas
  - query: "{topic_terms} -filter:replies"
    sort: latest
    limit: 20
    days_ago: 1
    min_followers: 5000
    notes: "Fresh original tweets from big accounts"

  # Trending topic riding
  - query: "{trending_topic}"
    sort: latest
    limit: 20
    days_ago: 1
    notes: "Ride whatever's trending in the niche today"

  # Author-response mining (find accounts that reply to replies)
  - query: "from:{target_handle} -filter:replies"
    sort: latest
    limit: 10
    days_ago: 1
    notes: "Latest from specific high-value accounts"
```

### Example: Persona Query Mapping

```yaml
P1_ai_builder:
  - "claude code" OR "cursor" OR "codex" OR "ai agent" -filter:replies
  - "just shipped" OR "just launched" OR "built this" -filter:replies min_faves:5
  - from:yacineMTB OR from:levelsio OR from:ChrisJBakke -filter:replies

P2_startup_shitposter:
  - "indie hacker" OR "solopreneur" OR "bootstrapped" -filter:replies min_faves:10
  - from:george__mack OR from:awilkinson OR from:gregisenberg -filter:replies

P3_dev_tool_launcher:
  - from:stripe OR from:suaborrowase OR from:vercel OR from:linear -filter:replies
  - "new logo" OR "rebrand" OR "just launched" (dev tool) -filter:replies min_faves:5
```

## Scoring & Ranking

When scoring discovered tweets for reply priority:

| Factor | Weight | Signal |
|--------|--------|--------|
| Author follower count | 25% | More followers = more eyeballs on your reply |
| Tweet freshness | 25% | Newer = higher chance of being in first 10 replies |
| Current reply count | 20% | Lower is better (under 30 = visible, under 10 = prime) |
| Early engagement rate | 15% | Likes/engagement appearing fast = algorithm will push it |
| Author reply behavior | 15% | Authors who respond to replies = 75x signal potential |

### Score Formula (simplified)

```
score = (
  follower_score(5K=0.3, 50K=0.8, 100K=1.0, 500K+=0.7) * 0.25 +
  freshness_score(0-30min=1.0, 30-60min=0.8, 1-2hr=0.5, 2hr+=0.2) * 0.25 +
  reply_headroom(0-5=1.0, 5-15=0.8, 15-30=0.5, 30+=0.1) * 0.20 +
  engagement_velocity(likes_per_minute > 1 = 1.0, else scaled) * 0.15 +
  author_reply_rate(responds_to_replies_often=1.0, rarely=0.3) * 0.15
)
```

## Daily Cadence

For the skill's scheduling/batching:

| Time Window | Activity | Volume |
|-------------|----------|--------|
| Morning (8-10am ET) | Reply blitz — fresh tweets from overnight | 3-5 replies |
| Midday (11am-1pm ET) | Peak activity — biggest accounts posting | 3-5 replies |
| Evening (6-8pm ET) | Catch trending topics + conversation loops | 2-3 replies |
| Async | Respond to replies on your own tweets | As needed |

**Total: 5-10 precision replies/day.** Not 50. Quality over volume.

## Conversation Loop Monitoring

After replies are posted and approved, the discovery pipeline should also surface:

1. **Author responses to your replies** — highest priority, always respond back
2. **Likes/engagement on your replies** — consider follow-up if engagement is strong
3. **New tweets from accounts you've engaged with** — RealGraph affinity means replying to the same accounts repeatedly builds algorithmic relationship

This creates a feedback loop: discover → reply → monitor → re-engage.

## Integration with Soul Personas

The discovery skill finds candidates. The soul decides how to reply.

**The handoff contract should include:**

```yaml
- source_platform: twitter
- source_post_url: https://x.com/...
- source_post_text: "..."
- source_author_handle: "@..."
- source_author_followers: 45000
- tweet_age_minutes: 12
- current_reply_count: 7
- engagement_velocity: 3.2  # likes per minute
- persona_hint: P1  # mapped to soul persona
- reply_strategy: conversational_hook  # suggested archetype from soul
- priority_score: 0.87
- action: propose_reply
```

The feed skill then uses the soul's persona voice adjustment + archetype to generate the actual reply text.

## Analytics-to-Soul Feedback Loop

Periodically (weekly), analyze reply performance to refine the soul:

1. **Export analytics CSV** (impressions, likes, engagements per tweet)
2. **Tag each reply** with archetype used, persona targeted, account replied to
3. **Identify patterns:**
   - Which archetypes get the most engagement?
   - Which personas/account types yield the best impression-to-follower conversion?
   - What reply length performs best?
   - Do image replies consistently outperform text-only?
4. **Update the soul's mix guidance** based on what actually works
5. **Update discovery queries** based on which account types yield the best results

This loop turns the soul from a static doc into a continuously improving engagement strategy.
