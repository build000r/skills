# Typography Pairings

Pick display + body + mono. Do not improvise. Each pairing has been chosen to be internally consistent at a given archetype.

## Archetype → Pairing

| Archetype | Display | Body | Mono | Notes |
|---|---|---|---|---|
| architectural-minimalism | Inter Display, Söhne, GT America | Inter, Söhne, Work Sans | JetBrains Mono, IBM Plex Mono | Sharp geometric display, humanist body. |
| warm-papered | Fraunces, Tiempos Headline, Canela | Inter, Work Sans | IBM Plex Mono | Serif display + sans body is the classic editorial pairing. |
| technical-industrial | GT America Mono, Space Grotesk | Inter, Söhne | JetBrains Mono, Berkeley Mono | Mono accents for engineering feel. |
| luxury-editorial | Canela, Ogg, GT Super | Söhne, Inter | IBM Plex Mono | High-contrast serif display, neutral sans body. |
| trust-finance | Tiempos Headline, Canela, GT Super | Inter, Söhne | IBM Plex Mono | Serif display signals institutional gravity. |
| civic-utility | Public Sans, Source Sans | Public Sans, Source Sans | IBM Plex Mono | Same family for display and body — simplicity reads as trust. |
| friendly-consumer | DM Serif Display, Nunito | DM Sans, Nunito | IBM Plex Mono | Rounded, warm, approachable. |

Open-source alternatives (Google Fonts / Fontsource) when licensed fonts aren't available:

- Inter Display → **Inter** (same family, tighter display cut)
- Söhne / GT America → **Work Sans** (humanist) or **DM Sans** (geometric)
- Fraunces / Tiempos → **Fraunces** (free on Fontsource)
- Canela / Ogg / GT Super → **Playfair Display** (free, similar contrast)
- JetBrains Mono → free everywhere
- IBM Plex Mono → free everywhere

## Modular Scale

Pick one scale ratio per project. The ratio multiplies successive sizes.

| Density | Ratio | Use case |
|---|---|---|
| 1.125 (major second) | dense admin dashboards | many values on one screen |
| 1.2 (minor third) | standard app | balanced |
| 1.25 (major third) | marketing + app blend | default for most projects |
| 1.333 (perfect fourth) | content-heavy marketing | long-form, articles |
| 1.414 (augmented fourth) | dramatic editorial | landing pages with few words |

Base body size:

- Boomer-legible default: **18px**.
- Standard app: **16px**.
- Dense admin: **14px** (but only when the audience is power users).

Line heights:

- Display: 0.95-1.05.
- Body: 1.5-1.7. Long-form reading sets ≥ 1.65.
- UI (buttons, labels): 1.2-1.3.

Tracking:

- Display: -0.03em to -0.02em (tighten large sizes).
- Body: -0.01em to 0em.
- UI caps/eyebrows: 0.08em-0.18em.

## Hard Rules for Boomer-Legibility Mode

Opt in whenever the audience includes non-technical readers, older users, or anyone who will read the page in daylight on a phone.

1. Body floor: 17px desktop, 16px mobile.
2. Line-height floor: 1.6 on long-form.
3. Max line length 68ch on reading surfaces.
4. No all-caps for paragraphs. Caps are reserved for eyebrows, max 4-5 words.
5. Tabular numerals enabled on any page showing money, dates, or counts:
   ```css
   font-feature-settings: "tnum" 1;
   font-variant-numeric: tabular-nums;
   ```
6. Number-adjacent labels use the body face, not the display face.
7. Links are underlined (or border-bottom) in body copy. Color-only links fail non-color-perceivers.
8. Minimum touch target 44x44px.
9. No type below 14px anywhere. Ever. Even footnotes.

## Token Names

Write these into tokens.css:

```css
--font-display: "Display Face Variable", Georgia, serif;
--font-body: "Body Face Variable", system-ui, sans-serif;
--font-mono: "Mono Face Variable", ui-monospace, monospace;

--text-xs: 0.8125rem;   /* 13px — never use in boomer-legible mode */
--text-sm: 0.9375rem;   /* 15px */
--text-base: 1.0625rem; /* 17px — boomer-legible default */
--text-lg: 1.25rem;
--text-xl: 1.5rem;
--text-2xl: 1.875rem;
--text-3xl: 2.25rem;
--text-4xl: 3rem;
--text-5xl: 3.75rem;
--text-6xl: 4.75rem;

--leading-tight: 1.05;
--leading-snug: 1.25;
--leading-normal: 1.5;
--leading-relaxed: 1.65;
```

Every component consumes from this set. If a component wants a size that isn't here, the answer is usually "use the closest step," not "add a new one."
