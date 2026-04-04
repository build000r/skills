# Profile README Patterns

Curated patterns from builder-focused GitHub profiles. These are principles
extracted from profiles that work, not templates to copy.

---

## Tier 1: The Minimalist Builder

**Pattern:** Identity + current work + one link. Nothing else.

**Why it works:** Treats the profile like a business card. Assumes the visitor
will click through to repos or the website for depth. Respects the reader's
time.

**Structure:**
```
one-liner about what you build
link to where the real work lives
```

**Examples of this energy:**
- Pieter Levels: leads with products shipped, links to live sites
- DHH: one sentence, links to Basecamp/HEY
- Antirez: brief identity, links to current project

**When to use:** When your repos and website speak for themselves. When you
have a strong public identity outside GitHub.

---

## Tier 2: The Project Showcase

**Pattern:** Identity + 2-4 current projects with one-line descriptions +
domain context for private work.

**Why it works:** Gives enough context to understand breadth without
overwhelming. Each project link goes to a live product or well-documented repo.

**Structure:**
```
who you are (one line)

what you're building:
- project A: what it does (link)
- project B: what it does (link)
- project C: what it does (link)

also working on: domain X, domain Y (closed source)

site: yoursite.com
```

**When to use:** When you're actively shipping multiple things and want to
show range. When you have closed-source work worth mentioning by domain.

---

## Tier 3: The Auto-Updater

**Pattern:** Static identity block + dynamic sections updated by GitHub Actions.

**Examples of dynamic content that works:**
- Latest blog posts (via RSS feed action)
- Recent releases across repos
- "Last shipped" timestamp

**Examples of dynamic content that doesn't work:**
- Contribution graphs (activity != impact)
- Language pie charts (noise)
- Spotify now-playing (irrelevant)
- Snake animations (gimmick)

**When to use:** When you publish regularly and want the profile to stay fresh
without manual updates. Only automate sections that reflect real output.

---

## Anti-Patterns Gallery

### The Badge Wall
```
![Python](badge) ![JavaScript](badge) ![Go](badge) ![Rust](badge)
![Docker](badge) ![AWS](badge) ![React](badge) ![Node](badge)
```
**Why it fails:** Lists capabilities without evidence. Every developer's badge
wall looks the same. Tells the visitor nothing about what you actually build.

### The Stats Dashboard
```
![GitHub Stats](stats-card)
![Top Languages](language-card)
![Streak](streak-card)
```
**Why it fails:** Contribution count rewards activity, not impact. Language
breakdown is meaningless (a repo with one large file skews everything). Streak
counter incentivizes gaming, not building.

### The Resume
```
## About Me
I am a passionate full-stack developer with 5 years of experience...

## Skills
- Languages: Python, JavaScript, Go, Rust
- Frameworks: React, Django, FastAPI
- Tools: Docker, Kubernetes, Terraform
```
**Why it fails:** This is a LinkedIn profile, not a GitHub profile. The
visitor is already on GitHub — they can see your repos. Tell them what you're
building, not what you know.

### The Stale Showcase
```
## Projects
- Cool App (last commit: 2022)
- Old Library (archived)
- Hackathon Project (3 commits total)
```
**Why it fails:** Showcasing dormant work signals you're not currently active.
Better to show nothing than to show abandoned projects.

---

## Principles (Stack-Ranked)

1. **Freshness over completeness** — A README with 2 current projects beats
   one with 10 stale ones
2. **Products over repos** — Link to the live thing, not just the source code
3. **Domains over technologies** — "I build health analytics tools" > "I know
   Python and React"
4. **Brevity over thoroughness** — Under 40 rendered lines. The profile is a
   teaser, not a portfolio site
5. **Voice over template** — Sound like yourself. If you write lowercase
   commit messages, write a lowercase README
6. **Funnel, don't replicate** — Point to your website for the full story
