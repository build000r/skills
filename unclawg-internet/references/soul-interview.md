# Soul Interview (Ask-Cascade)

This phase defines the agent's complete personality — identity, voice, personas, engagement principles, and boundaries. The soul is the **single source of truth for all personality**. Skills read the soul to know how to behave. Client overlays and skill definitions are purely mechanical.

Apply ask-cascade rules throughout: strategic questions first and alone, tactical questions batched only when independent, re-evaluate after each answer.

**If the user's signup is pending human proof (202 in Step 4):** still run the full soul interview. The soul draft and client overlay can be prepared locally and published once the account is approved.

## The Separation Principle

| Concern | Where it lives | Examples |
|---------|---------------|----------|
| **Personality** | `soul_md` (this interview's output) | Voice, tone, reply archetypes, persona voice calibration, engagement principles, boundaries, off-limits topics |
| **Technical config** | `skillbox-config/clients/{client}/overlay.yaml` → `context.yaml` | Query packs, subreddit targets, ranking weights, platform API scope, exclusion regex, handoff schema |
| **Mechanics** | Skill SKILL.md files | API calls, loops, error handling, data flow, curl commands |

**Test:** if you swap the soul for a different one, the skills should still work mechanically — they just talk differently. If you swap the client overlay, the personality shouldn't change — just the search targets.

---

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

## Round 3 — Audience, Voice & Archetypes (depends on Round 2)

**Only for brand engagement or customer discovery goals.** Skip for operations/trading.

**Q1 and Q2** are independent and batchable. **Q3 and Q4** are independent and batchable. Ask them in two rounds or one if all four are clearly independent.

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
| **Empathetic educator** | "That's a real pattern. When your system is under that kind of load, it burns through resources faster than you'd expect — especially with everything else you're managing. Have you looked at what's actually going on under the surface?" |
| **Direct builder** | "Streaming responses are the gotcha here. Edge function + fetch event stream does the trick. I shipped exactly this pattern last week." |
| **Warm conversational** | "Oh I've been there! The 'everything looks fine on paper' thing is so frustrating. One thing that actually helped me was looking at the ratios between things, not just the individual numbers." |
| **Professional consultant** | "Based on what you're describing, there's likely an underlying imbalance that standard assessments don't capture. Deeper testing often reveals the patterns that explain exactly this." |

> Q3: "How should your agent vary its approach? Pick the reply styles it should use."

Options (multiselect via AskUserQuestion):

| Archetype | Description |
|-----------|-------------|
| **The Mechanism Drop** | Share one specific technical/science fact that reframes their problem |
| **The Reframe** | Validate frustration, offer a different lens on the situation |
| **The Question** | Ask something useful that makes them think differently |
| **The Quick Solve** | Give a specific, actionable answer (shows expertise) |
| **The Validate-Only** | Pure empathy, no pitch — just "I hear you" (use 1 in 4 replies) |
| **The "I Built This"** | When you've solved this exact problem before — share the specifics |

> Q4: "Any topics or behaviors that are absolutely off-limits for your agent?"

Free text. Examples: "never discuss competitors by name", "no medical claims", "don't engage with political content", "never claim personal health experience (agent is AI-drafted)".

Store `PLATFORMS`, `VOICE_STYLE`, `REPLY_ARCHETYPES`, `OFF_LIMITS`.

## Round 4 — Persona Generation (system-generated, user-validated)

**Only for brand engagement or customer discovery goals.**

Using all context from Rounds 1-3, generate 2-3 starter personas. Each persona includes **voice calibration** — this is personality, not config.

**If the user provided a website or product URL in Round 2:** the subagent research from that step informs persona generation. Use discovered audience signals, testimonials, feature pages, and existing marketing language to make personas concrete.

Present personas to the user:

```
Based on what you've told me, here are your starter personas:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

P1: [Name] — [1-sentence description]          [PRIORITY]
    Pain:       [What they're struggling with — in their words, not yours]
    Platforms:  [Where they are — from Round 3]
    Voice:      [How to talk to THIS persona — tone, length, warmth level]
    Archetypes: [Which reply styles work best — from Round 3 selections]
    Example:    "[A 1-2 sentence example reply to this persona in the agent's voice]"

P2: [Name] — [1-sentence description]
    Pain:       [...]
    Platforms:  [...]
    Voice:      [...]
    Archetypes: [...]
    Example:    [...]

P3: [Name] — [1-sentence description]
    Pain:       [...]
    Platforms:  [...]
    Voice:      [...]
    Archetypes: [...]
    Example:    [...]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Then ask:

> "Want to adjust these, add another, or go with these?"

Iterate until the user is satisfied. Keep persona count between 2-5.

**Persona query generation rules** (these go into the CLIENT OVERLAY, not the soul):
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

Free text. Examples: "other companies in our space", "anyone with competing professional credentials", "recruiters".

Store `API_KEYS_AVAILABLE`, `EXCLUSION_RULES`.

**Important:** Competitor exclusion has two sides:
- **Personality side** (goes in soul): "Never engage with direct competitors. Never claim credentials we don't have."
- **Technical side** (goes in client overlay): Regex patterns, bio keyword filters, account-type skip rules.

Generate both from the user's answer.

---

## Ask-Cascade Quick Reference

| Round | Type | Can batch? | Depends on |
|-------|------|-----------|------------|
| 1 — Goal | Strategic | No — ask alone | Nothing |
| 2 — Context | Tactical | Yes (Q1+Q2 independent) | Round 1 |
| 3 — Audience, Voice & Archetypes | Tactical | Yes (Q1+Q2 batchable, Q3+Q4 batchable) | Round 2 |
| 4 — Personas | System-generated | N/A — present for validation | Rounds 1-3 |
| 5 — Tools & Exclusions | Detail | Yes (Q1+Q2 independent) | Round 3 |

**Re-evaluate after every round.** If the user's answers in Round 2 reveal they already have a detailed persona doc or brand guide, skip Round 4 generation and ask to read their existing material instead (via subagent).

**If the user wants to skip the interview:** respect it. Write the default template soul (from `references/default-soul.md` bundled with this skill) and tell them they can refine it later through the approval feedback loop. The system learns either way — the interview just gives it a head start.
