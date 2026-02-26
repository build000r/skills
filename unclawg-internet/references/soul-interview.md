# Soul Interview (Ask-Cascade)

This phase defines the agent's identity, target market, and engagement strategy through a structured question cascade. Apply ask-cascade rules throughout: strategic questions first and alone, tactical questions batched only when independent, re-evaluate after each answer.

**If the user's signup is pending human proof (202 in Step 4):** still run the full soul interview. The soul draft and mode file can be prepared locally and published once the account is approved.

## Round 1 — Goal (Strategic, ask alone)

This answer determines every subsequent question. Ask alone:

> "What's the primary goal for this agent?"

Options (via AskUserQuestion):

| Option | Description |
|--------|-------------|
| **Brand engagement** | Connect with customers and community on social platforms |
| **Customer discovery** | Find leads and research markets — no autonomous posting |
| **Operations** | Internal monitoring, alerting, workflows with approval gates |
| **Trading / financial** | Autonomous actions requiring transaction-level approval |

Store as `AGENT_GOAL`. Do not proceed until answered.

## Round 2 — Context (depends on Round 1)

**If brand engagement or customer discovery:**

Ask two questions (batchable — independent of each other):

> Q1: "Describe your ideal customer in 1-2 sentences. Who are they, and what's their day like?"
>
> Q2: "What problem do you solve for them? What does life look like before vs. after your product?"

**If the user mentions a website, product name, or URL:** launch a **Task subagent** to research it. The subagent should fetch the site, extract the value proposition, target audience signals, and any existing brand voice. Feed results back into persona generation (Round 4).

**If operations:**

Ask two questions (batchable):

> Q1: "What systems does your agent monitor or operate on?"
>
> Q2: "What actions should require human approval before executing?"

**If trading / financial:**

Ask two questions (batchable):

> Q1: "What markets or platforms? (e.g., crypto exchanges, prediction markets, DeFi protocols)"
>
> Q2: "What's the maximum action the agent should take without asking you first?"

Store all answers. These feed into soul generation.

## Round 3 — Audience & Voice (depends on Round 2)

**Only for brand engagement or customer discovery goals.** Skip for operations/trading.

Ask three questions (Q1 and Q2 are independent, batchable; Q3 is independent):

> Q1: "Where does your audience hang out online?"

Options (multiselect via AskUserQuestion):
- Reddit
- Twitter / X
- LinkedIn
- TikTok
- Instagram
- YouTube
- Hacker News

> Q2: "Which voice feels right for your agent?"

Options (via AskUserQuestion with markdown previews):

| Option | Preview |
|--------|---------|
| **Empathetic educator** | "That 3pm crash is real. Your body is burning through magnesium faster than you're replacing it — especially with the stress load you're describing. Have you looked at your mineral balance?" |
| **Direct builder** | "Streaming responses are the gotcha here. Edge function + fetch event stream does the trick. I shipped exactly this pattern last week." |
| **Warm conversational** | "Oh I've been there! The 'labs are normal' thing is so frustrating. One thing that actually helped me understand what was going on was looking at the mineral ratios, not just individual levels." |
| **Professional consultant** | "Based on the symptoms you're describing, there's likely a mineral imbalance that standard blood panels don't capture. HTMA testing reveals ratios that explain exactly this pattern." |

> Q3: "Any topics or behaviors that are absolutely off-limits for your agent?"

Free text. Examples: "never discuss competitors by name", "no medical claims", "don't engage with political content".

Store `PLATFORMS`, `VOICE_STYLE`, `OFF_LIMITS`.

## Round 4 — Persona Generation (system-generated, user-validated)

**Only for brand engagement or customer discovery goals.**

Using all context from Rounds 1-3, generate 2-3 starter personas. Follow the structure from the unclawg-discover persona framework.

**If the user provided a website or product URL in Round 2:** the subagent research from that step informs persona generation. Use discovered audience signals, testimonials, feature pages, and existing marketing language to make personas concrete.

Present personas to the user:

```
Based on what you've told me, here are your starter personas:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

P1: [Name] — [1-sentence description]          [PRIORITY]
    Pain:      [What they're struggling with]
    Platforms: [Where they are — from Round 3]
    Queries:   ["exact search query 1", "exact search query 2"]
    Voice:     [How to talk to this persona specifically]

P2: [Name] — [1-sentence description]
    Pain:      [...]
    Platforms: [...]
    Queries:   [...]
    Voice:     [...]

P3: [Name] — [1-sentence description]
    Pain:      [...]
    Platforms: [...]
    Queries:   [...]
    Voice:     [...]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Then ask:

> "Want to adjust these, add another, or go with these?"

Iterate until the user is satisfied. Keep persona count between 2-5.

**Persona query generation rules:**
- Use colloquial language matching real user pain, not clinical/marketing terms
- Include platform-specific query formats (Reddit: subreddit + query, Twitter: keyword phrase, HN: topic query, LinkedIn: professional context query)
- Each persona gets 2-4 queries per platform they're active on
- Queries should find people with the problem, not people selling solutions

## Round 5 — Tools & Exclusions (detail tier, batchable)

**Only for brand engagement or customer discovery goals.**

Ask two questions (independent, batchable):

> Q1: "Do you have API keys for paid discovery platforms?"

Options (multiselect via AskUserQuestion):
- **Apify** ($29/mo starter) — unlocks Twitter/X, LinkedIn, Instagram comments, TikTok comments
- **Virlo** (free tier available) — unlocks trending topic discovery
- **None yet** — we'll use Reddit + Hacker News (free) to start

> Q2: "Any competitors or types of accounts your agent should never engage with?"

Free text. Examples: "other mineral testing companies", "anyone with RD/RDN credentials selling services", "recruiters".

Store `API_KEYS_AVAILABLE`, `EXCLUSION_RULES`.

## Ask-Cascade Quick Reference

| Round | Type | Can batch? | Depends on |
|-------|------|-----------|------------|
| 1 — Goal | Strategic | No — ask alone | Nothing |
| 2 — Context | Tactical | Yes (Q1+Q2 independent) | Round 1 |
| 3 — Audience & Voice | Tactical | Yes (Q1+Q2+Q3 independent) | Round 2 |
| 4 — Personas | System-generated | N/A — present for validation | Rounds 1-3 |
| 5 — Tools & Exclusions | Detail | Yes (Q1+Q2 independent) | Round 3 |

**Re-evaluate after every round.** If the user's answers in Round 2 reveal they already have a detailed persona doc or brand guide, skip Round 4 generation and ask to read their existing material instead (via subagent).

**If the user wants to skip the interview:** respect it. Write the default template soul (from `references/default-soul.md` bundled with this skill) and tell them they can refine it later through the approval feedback loop. The system learns either way — the interview just gives it a head start.
