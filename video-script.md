# Demo Video Script: "This Video Was Made by the Skills It's About"

**Length**: 2:45
**Aspect**: 16:9 (GitHub README embed)
**Format**: Screen capture (terminal) + TTS voiceover + caption overlays

## Voice Direction

Pick voice via ElevenLabs API — match tone to content:

| Content Tone | This Video's Tone | Recommended Match |
|-------------|-------------------|-------------------|
| Casual / conversational | Yes — dry, developer humor | "laid-back", "casual", "relaxed" |
| Educational / explainer | Yes — walking through a workflow | "educator", "professional", "clear" |

**Best fit**: A voice with both "casual" and "clear" labels. Check `labels.description`
for "conversational" or "relaxed" — avoid "energetic" or "broadcaster" (too polished
for a README demo). Male or female both work; prioritize natural pacing over drama.

```bash
# List voices, filter for casual/educational tone
curl -s -H "xi-api-key: $ELEVENLABS_API_KEY" \
  "https://api.elevenlabs.io/v1/voices" | \
  jq '.voices[] | select(.labels.description | test("casual|conversational|relaxed|laid-back"; "i")) | {voice_id, name, labels}'
```

Generate each act as a separate audio file, then combine in editing.

---

## Script

### HOOK (0:00-0:08)

**[SCREEN: Terminal, blank. Text types itself on screen as caption.]**

> This video was planned and scripted by the skills in this repo.

**[BEAT — 1 second pause]**

> Here's the proof.

---

### CONTEXT (0:08-0:30)

**[SCREEN: `ls` showing the 4 skill directories]**

> This repo has 4 Claude Code skills. Three of them chain together into a single workflow — and that workflow produced everything you're watching right now.

**[SCREEN: Quick flash of each SKILL.md frontmatter as they're named]**

> `skill-issue` reviews skills. `divide-and-conquer` parallelizes work across agents. `trend-to-content` turns research into content.

> Let's run them.

---

### ACT 1: SKILL-ISSUE REVIEWS THE REPO (0:30-1:10)

**[SCREEN: Terminal — invoke `/skill-issue`]**

> First, I ask skill-issue to review every skill in this directory.

**[SCREEN: Output streaming. Highlight captions overlay each issue as found:]**

- `nested duplicate directory`
- `bare except: on line 219`
- `missing licenses`
- `duplicated hook formulas`
- `no root README`

> It found 12 issues across all 4 skills. Real problems — not lint noise. Structural duplication, missing licenses, inconsistent packaging.

> Now I need to fix all of them. But they're spread across 4 different directories.

---

### ACT 2: DIVIDE-AND-CONQUER PARALLELIZES (1:10-1:50)

**[SCREEN: Terminal — invoke `/divide-and-conquer`]**

> So I invoke divide-and-conquer. It reads the issues and splits them into 4 independent agents — one per directory.

**[SCREEN: The agent plan appears. Highlight the Conflict Check section.]**

> Each agent owns its own files. The conflict check confirms zero write overlap. Zero data dependencies.

**[SCREEN: All 4 Task tool calls fire simultaneously. Terminal shows parallel output.]**

> All 4 agents launch in a single message. They run at the same time.

**[SPEED RAMP: 2x as agent outputs stream back]**

> Nested duplicates — deleted. Bare except — fixed. Licenses — created. Hook formulas — deduplicated. Root README — written.

**[SCREEN: Normal speed. All agents show "completed".]**

> Done. Every issue resolved, no conflicts.

---

### ACT 3: THE INCEPTION (1:50-2:25)

**[SCREEN: Terminal — invoke `/trend-to-content`]**

> Here's where it gets recursive.

> I invoke trend-to-content and ask it to research video angles for a README demo. It searches for what's trending in the Claude Code skills space...

**[SCREEN: WebSearch results streaming — marketplace stats, tutorial articles]**

> ...finds that skills orchestration is the content gap nobody's covering...

**[SCREEN: The video concept output — "Inception" angle selected]**

> ...and recommends the exact concept you're watching right now. A self-referential demo where the video is made by its own subject.

**[BEAT — 1 second pause]**

> The script you're hearing? Written by the output of that workflow.

---

### CTA (2:25-2:45)

**[SCREEN: Terminal showing install commands, one per line]**

```
npx skills add build000r/skill-issue
npx skills add build000r/divide-and-conquer
npx skills add build000r/trend-to-content
npx skills add build000r/prompt-reviewer
```

> All 4 skills are open source and work with any Claude Code project.

**[SCREEN: GitHub repo page with star count]**

> Star the repo. Install a skill. Build something recursive.

**[END CARD: github.com/build000r/skills]**

---

## Production Checklist

- [ ] Record terminal session (or re-record clean version of each act)
- [ ] Generate TTS for each act using ElevenLabs (see Voice Direction above)
- [ ] Add caption overlays for issue labels (Act 1) and install commands (CTA)
- [ ] Speed ramp parallel agent execution to 2x (Act 2)
- [ ] Add minimal ambient music (electronic/lo-fi, under voiceover)
- [ ] Export 1920x1080, embed in README via YouTube/Loom link
- [ ] Create social preview thumbnail: terminal + "SKILLS THAT FIX THEMSELVES"
