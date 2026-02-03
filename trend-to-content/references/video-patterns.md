# Video Content Patterns

Create video content from trends for maximum reach.

## Platform Specs

| Platform | Aspect | Length | Key Features |
|----------|--------|--------|--------------|
| TikTok | 9:16 | 15-60s | Fast cuts, captions required, trending audio |
| YouTube Shorts | 9:16 | 30-60s | Hook in 1s, loop-friendly |
| Instagram Reels | 9:16 | 15-30s | Trending audio, visual polish |
| YouTube | 16:9 | 8-15min | Structure, chapters, thumbnail |
| LinkedIn | 1:1 or 16:9 | 30s-3min | Professional tone, captions |

---

## The Hook (First 3 Seconds)

The hook determines if anyone watches. Test these formulas:

### Curiosity Hooks

```
"The real reason [outcome] happens isn't what you think"
"I was wrong about [common belief]"
"[Impressive result] — and it only took [surprisingly short time]"
```

### Contrarian Hooks

```
"[Common advice] is wrong. Here's why"
"Stop [common practice]. Do this instead"
"Unpopular opinion: [bold statement]"
```

### Story Hooks

```
"I almost [mistake/failure]"
"Last week, [unexpected thing] happened"
"3 years ago, I [past state]. Today, [current state]"
```

### Value Hooks

```
"How to [desirable outcome] (without [pain point])"
"[Number] [things] that [outcome]"
"The easiest way to [goal]"
```

### Pattern Interrupt

```
"Wait—" [dramatic pause]
"POV:" [scenario]
"This changed everything"
```

---

## Video Script Structure

### Short-Form (15-60s)

```
HOOK (0-3s)
"[Attention grabber]"

PROBLEM (3-10s)
"[Why this matters / pain point]"

SOLUTION (10-45s)
"[Your content / key points]"

CTA (45-60s)
"[Follow for more / comment / share]"
```

### Long-Form (8-15min)

```
HOOK (0-30s)
- Open with the best part / result
- Promise what they'll learn

INTRO (30s-2min)
- Establish credibility
- Preview structure

CONTENT (3-10min)
- 3-5 main points
- Each point: claim → evidence → example
- Visual variety every 30s

RECAP (1min)
- Summarize key takeaways
- Bridge to CTA

CTA (30s)
- Specific next action
- Related video suggestion
```

---

## Content Formats by Trend Type

| Trend Type | Best Format | Structure |
|------------|-------------|-----------|
| "How to" | Tutorial | Problem → Steps → Result |
| Controversy | Take/reaction | State position → Evidence → Rebuttals |
| New concept | Explainer | What → Why → How |
| Statistics | Data story | Hook → Data → Insight |
| Product buzz | Review/demo | First impression → Features → Verdict |
| Lifestyle | Day-in-life | Morning → Key moments → Evening |

---

## Trend → Video Workflow

### 1. Extract the Hook

From the trend, identify what makes people care:
- **Trending topic**: "AI coding agents"
- **Hook angle**: "The tool replacing junior devs (and it's not Copilot)"

### 2. Choose Format

Match trend type to format:
- Informational trend → Tutorial or Explainer
- Controversial trend → Take or Reaction
- Visual trend → Transformation or Demo

### 3. Script the Structure

```
Hook: [Extracted from trend]
Problem: [Why audience cares]
Content: [Your unique angle]
CTA: [Platform-appropriate action]
```

### 4. Add Visual Elements

- B-roll at key points
- Text overlays for emphasis
- Cut every 3-5 seconds (short-form)
- Captions always on

---

## Platform-Specific Tips

### TikTok

- Use trending sounds (even under voiceover)
- Text on screen from frame 1
- Hook must work on mute
- Hashtags: 3-5 relevant, 1 trending

### YouTube Shorts

- Optimize for the loop (end feeds into beginning)
- Title appears after 2 views—hook must work without it
- Link to long-form content in comments

### Instagram Reels

- Higher production value expected
- Trending audio boosts discovery
- Share to Stories with "New Reel" sticker
- Carousel posts can outperform Reels for information

### YouTube Long-Form

- Thumbnail + Title = 80% of click decision
- First 30s determines retention
- Chapters for navigation
- Cards/end screens for CTR

### LinkedIn

- Captions required (85% watch muted)
- Professional but not boring
- Native upload only (no YouTube links)
- Text post + video outperforms video alone

---

## Thumbnail Best Practices

For YouTube and cross-platform sharing:

### Elements

- **Face** with emotion (if personal brand)
- **Bold text** (3-4 words max)
- **Contrast** (bright vs dark)
- **Curiosity gap** (don't give away the answer)

### Technical

- 1280x720 minimum (1920x1080 preferred)
- Test at small size (mobile)
- Consistent style builds brand recognition

### A/B Test Patterns

- With face vs without
- Question vs statement
- Bright vs dark background
- Before/after vs single image

---

## Video SEO

### YouTube

- Keyword in title (front-loaded)
- Description: keyword in first 2 sentences
- Tags: primary keyword + 5-10 related
- Transcript/captions for indexing

### Schema Markup (for website embeds)

```json
{
  "@context": "https://schema.org",
  "@type": "VideoObject",
  "name": "Video Title",
  "description": "Description",
  "thumbnailUrl": "https://example.com/thumb.jpg",
  "uploadDate": "2026-01-15",
  "duration": "PT2M30S",
  "contentUrl": "https://example.com/video.mp4"
}
```

---

## Voiceover with ElevenLabs TTS

Generate voiceovers from video scripts using the ElevenLabs API.

### Step 1: Fetch voices and pick one based on content tone

Always list voices first — don't hardcode IDs, they may change.

```bash
# List available voices with metadata
curl -s -H "xi-api-key: $ELEVENLABS_API_KEY" \
  "https://api.elevenlabs.io/v1/voices" | jq '.voices[] | {voice_id, name, category, labels}'
```

Pick the voice that matches the video's tone:

| Content Tone | Look For | Example Match |
|-------------|----------|---------------|
| Energetic / social media | "energetic", "social media", young | Liam |
| Educational / explainer | "educator", "professional", clear | Alice, Matilda |
| Storytelling / narrative | "storyteller", "warm", "captivating" | George |
| Authoritative / serious | "dominant", "firm", "broadcaster" | Adam, Daniel |
| Casual / conversational | "laid-back", "casual", "relaxed" | Roger, River |

Match by checking voice `name` and `labels` (gender, age, accent, description) from the API response.

### Step 2: Generate speech

```bash
# Replace {voice_id} with the chosen voice's ID from step 1
curl -s -X POST \
  -H "xi-api-key: $ELEVENLABS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text": "Your script here", "model_id": "eleven_multilingual_v2", "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}' \
  "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}" \
  --output voiceover.mp3
```

If `$ELEVENLABS_API_KEY` is empty (Claude Code runs bash, not zsh — never `source ~/.zshrc`):
```bash
export ELEVENLABS_API_KEY=$(grep 'ELEVENLABS_API_KEY' ~/.zshrc | grep -o '"[^"]*"' | tr -d '"')
```

### Step 3: Assemble

1. Write script from trend (see Script Structure above)
2. Generate TTS for each section (hook, problem, solution, CTA) as separate files
3. Combine with Remotion composition or video editor

---

## Batch Production Workflow

Efficient video creation at scale:

### Week 1: Research + Script
- Identify 4 trends
- Write 4 scripts
- Create shot lists

### Week 2: Shoot
- Batch all A-roll in one session
- Capture B-roll for all 4 videos
- Record all voiceovers

### Week 3: Edit + Publish
- Edit all 4 videos
- Create thumbnails
- Schedule releases (1-2 per week)

### Week 4: Analyze + Plan
- Review performance
- Identify what worked
- Plan next batch based on learnings
