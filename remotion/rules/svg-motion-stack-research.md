---
name: svg-motion-stack-research
description: How to architect SVG-first motion systems around Remotion, including spec-first hybrid stacks, preview adapters, and research output expectations.
metadata:
  tags: svg, motion-spec, gsap, animejs, lottie, architecture
---

# SVG Motion Stack Research for Remotion

Use this rule when the user asks about stack selection, render authority, preview/runtime separation, or how to combine Remotion with GSAP, Anime.js, Lottie, Motion Canvas, Playwright, or Puppeteer for SVG-heavy motion work.

## Core timing rule

Remotion must be the final render authority.

- Final animation state must come from `useCurrentFrame()`, `useVideoConfig()`, `interpolate()`, `spring()`, and `<Sequence>`.
- Do not let GSAP, Anime.js, CSS transitions, Lottie playback, or browser-only timelines become the canonical source of final timing inside Remotion.
- Preview engines may help with authoring and easing exploration, but the Remotion interpreter owns exported frames.

See [animations.md](animations.md), [timing.md](timing.md), and [lottie.md](lottie.md) for the underlying implementation primitives this rule builds on.

## Preferred architecture

For most advanced SVG motion work, recommend a spec-first stack instead of an engine-first stack:

1. Remotion as the only final renderer
2. Native React and inline or imported SVG as the scene graph
3. A small typed motion-spec DSL or TypeScript object model as the source of truth
4. A browser-time preview adapter that reads the same spec
5. Narrow helper libraries for specific problems such as path morphing, easing, or layout transitions
6. Playwright or Puppeteer only for QA or fallback capture, and Lottie only for import or interchange

If the user wants the "best of both worlds", be explicit that the answer is a shared motion spec compiled into two targets: preview-time behavior and Remotion frame math.

## Candidate roles

- `Remotion`: Final timing owner and video renderer. Use it for deterministic frame math and export.
- `React/SVG`: Primary scene graph. Keep visuals editable as normal components instead of burying them in generated payloads.
- `GSAP`: Default preview adapter when rich timelines and easing exploration matter most. Treat it as an authoring-time interpreter, not the final render clock.
- `Anime.js`: Strong permissive-OSS preview alternative with good SVG helpers. Use it when MIT licensing matters more than the GSAP ecosystem.
- `Lottie`: Import bridge for After Effects or designer handoff. Keep it off the hot path for custom SVG films.
- `Motion Canvas`: Alternate full stack or design reference when the user wants a more code-first OSS runtime instead of Remotion-centered rendering.
- `Playwright`: Preferred QA and preview-regression layer.
- `Puppeteer` and `FFmpeg`: Low-level browser-capture and assembly fallback when raster capture is the actual requirement.

## Decision rules

Ask these questions in order:

1. Who must own final time?
2. Must the output be deterministic video rather than browser playback?
3. Must the visuals stay editable as React and SVG code?
4. Does the user care about permissive OSS licensing?
5. Does the workflow need Lottie or After Effects interchange?
6. Does Codex need a small typed target instead of large generated JSON?

Default to the architecture that keeps the source of truth small and semantic. Prefer adding narrow helpers such as path-morph or easing utilities over adding a second all-purpose runtime for every effect.

## Default recommendations

- Hybrid default: `Remotion + React/SVG + motion-spec DSL + GSAP preview adapter`
- Permissive-OSS fallback: `Remotion + React/SVG + motion-spec DSL + Anime.js preview adapter`
- Alternate full stack when Remotion is not required: `Motion Canvas`
- Import-heavy workflow: Use Lottie selectively and keep imported assets isolated from the core motion language
- QA and capture: Prefer Playwright; use Puppeteer and FFmpeg only when browser capture is the real deliverable

## Research output contract

When answering architecture or stack-comparison questions, structure the response like this:

1. One short recommendation paragraph
2. The render-authority rule
3. Candidate roles and tradeoffs
4. A spec-first architecture sketch or pipeline
5. The first implementation step

For unstable facts such as licensing, pricing, release cadence, stars, package status, or official integrations, browse the latest official docs or repository pages first and cite them. Separate stable architecture guidance from those time-sensitive claims.
