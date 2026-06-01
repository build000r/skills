---
name: unified-brand-system
description: Build a unified brand system from a brand brief + logo + domain. Produces shadcn-compatible design tokens (HSL CSS variables), typography pairing, spacing/radius/elevation scales, component primitives contract, and a rollout checklist. Use when establishing or re-platforming a brand for an Astro, Next, Vite, or any CSS-variable-based web project, or when the user asks to "unify the brand", "set up design tokens", "adopt shadcn styling", or "turn this logo and brief into a theme".
---

# Unified Brand System

Turn a brand brief + logo + domain into a consistent, shadcn-compatible token system that any web stack can consume. Output is not a pile of opinions — it is a concrete set of files that drop into the project.

## On Trigger

Start the first progress update with:

`Using unified-brand-system ...`

## Verification And Closeout

Before calling a brand system complete, verify:

- token files were written to the intended project paths
- every foreground/background pair named in the token contract passes the stated
  contrast floor
- typography, spacing, radius, and elevation have one declared source of truth
- hardcoded colors/radii/shadows targeted by the rollout were replaced or
  explicitly deferred
- the final response names the files changed and the next visual or build check
- any changed helper code or templates have a targeted `pytest` or project
  native test before closeout

If project files cannot be written or inspected, return the token contract as a
draft artifact and state which verification steps are still missing.

## What This Skill Owns

- **Tokens**: HSL CSS variables using shadcn's naming contract (`--background`, `--foreground`, `--primary`, etc.) so Radix-based shadcn components work without further mapping.
- **Typography**: display + body + mono pairing, modular scale, boomer-legibility overrides where called for.
- **Spacing & radius**: one radius scale, one spacing scale, no drift between components.
- **Elevation**: surface layers and shadow scale derived from the background token, not hardcoded colors.
- **Component primitives contract**: what tokens each primitive (button, card, input, dialog) is allowed to reference.
- **Rollout**: a concrete checklist for applying the system to an existing project without leaving orphan styles behind.

## What This Skill Does NOT Own

- Copy, content strategy, or marketing voice.
- Logo design or icon set generation.
- Data visualization — defer to `tufte-ui-review` for quant UI.
- Specific component implementations — the contract is the artifact, not the button markup.

## Workflow

### 1. Gather the brand brief

Ask for or infer these inputs. If the user gave a one-line brief, parse it for archetype, palette direction, audience, and constraints; do not ask five questions when one clarifying question will do.

- **Name**: brand or product name.
- **Archetype**: pick the closest match or name a hybrid. See [references/archetypes.md](references/archetypes.md).
- **Audience**: primary + secondary. Flag legibility constraints (older readers, low-vision, high-stakes finance, public sector).
- **Tone words**: 3-6 adjectives.
- **Domain**: finance, legal, healthcare, commerce, gov, etc. Drives trust cues and compliance-adjacent defaults.
- **Logo**: file path or description. Used for palette seeding and weight/line characteristics.
- **Hard constraints**: accessibility floor (WCAG AA/AAA), print/dark mode, existing brand lock-ins.

### 2. Define the palette

Follow [references/color-discovery.md](references/color-discovery.md). The short version:

- Start from the logo's dominant ink and background values, not a Pantone wish list.
- Work in HSL so the token file is human-editable and shadcn-compatible.
- Fix neutrals first (background, foreground, muted, border), then accent, then semantic (destructive, success, warning).
- Prove AA contrast for every foreground/background pair before moving on.
- Derive light and dark modes from the same hue pool — do not invent a second palette.

Output: the canonical HSL triplets for every token in [assets/templates/tokens.css](assets/templates/tokens.css).

### 3. Pair typography

Follow [references/type-pairings.md](references/type-pairings.md). Pick display + body + mono based on the archetype. For boomer-legibility or high-stakes finance domains, enforce:

- Body size floor of 17px on desktop, 16px on mobile.
- Minimum line-height 1.6 for long-form.
- Maximum line length 68ch for reading surfaces.
- No tracking below -0.01em on body; no all-caps for paragraphs.
- Headings use a display face with tabular figures enabled for any numeric page.

Output: `--font-display`, `--font-body`, `--font-mono`, and the modular scale tokens in tokens.css.

### 4. Fix the scales

Spacing, radius, and elevation must each have exactly one source of truth. No component invents its own.

- **Spacing**: 4px base, scale `0, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32` (rem-normalized).
- **Radius**: pick one of `sharp (0)`, `slight (4px)`, `soft (8px)`, `pillowy (14px)`, or `pill (999px)` as the default; everything else derives from it via `calc(var(--radius) * N)`.
- **Elevation**: three surfaces (`--surface-1/2/3`) derived by shifting the background lightness. Shadows are token-level (`--shadow-sm/md/lg`) and must respect dark mode.

### 5. Write the component primitives contract

Define which tokens each primitive may read. This is a contract, not an implementation. Example rule: a `Button` reads `--primary`, `--primary-foreground`, `--radius`, and `--ring` — nothing else. See [references/primitives-contract.md](references/primitives-contract.md).

Enforce: if a component needs a color that isn't in the token set, add the token — do not hardcode.

### 6. Emit the files

Drop these into the target project:

- `src/styles/tokens.css` — copy of [assets/templates/tokens.css](assets/templates/tokens.css) with real values.
- `src/styles/fonts.css` — copy of [assets/templates/fonts.css](assets/templates/fonts.css) with the chosen stack.
- `tailwind.config.ts` (if Tailwind is present) — copy of [assets/templates/tailwind.config.ts](assets/templates/tailwind.config.ts).
- `src/styles/globals.css` — imports tokens + fonts in order, sets base element styles.

For stacks without Tailwind, tokens.css alone is enough — CSS variables are framework-agnostic.

### 7. Roll out to the existing project

Follow [references/rollout-checklist.md](references/rollout-checklist.md). The short version:

1. Add the new files without removing the old ones.
2. Switch the root layout to import tokens + fonts + globals in order.
3. Find every hardcoded color in the codebase; replace with token references.
4. Replace every hardcoded radius, shadow, and spacing literal with token references.
5. Delete the old styles file only after grep confirms zero references.
6. Visual-diff a handful of representative pages before committing.

## Non-Negotiables

1. Token names must match shadcn's contract for the overlap set. If the project later adds shadcn/ui components, they must work with zero remapping.
2. HSL everywhere. No hex in the token file. Hex is fine in comments for human reference.
3. Every foreground/background pair must pass WCAG AA at minimum. High-stakes domains (finance, healthcare, gov) aim for AAA on body copy.
4. Light and dark are derived from the same hues, not two parallel palettes.
5. No component hardcodes a color, radius, spacing, or shadow. If it needs one, add the token.
6. Typography is boomer-legible by default when the audience includes non-technical readers or older users. Opt out explicitly in the brief, not by accident.
7. The rollout is not complete until the old styles file is deleted and grep returns zero references to removed classes.

## Practical Rules

- Prefer semantic tokens over literal ones. `--border` beats `--gray-200`.
- Prefer one strong accent over three competing ones. Ambiguity erodes trust.
- Prefer high contrast over low contrast. "Subtle" is a luxury tax; most users just need to read the page.
- Prefer text over icons for primary navigation in finance/legal/healthcare — icons without labels fail boomer-legibility.
- Prefer system fonts as a fallback stack, not as a load-time flash target. Self-host variable fonts and preload.
- Prefer a single display face across the marketing site and the app. Split only when the app is dense enough to need a separate type scale.
- Prefer `calc(var(--radius) * N)` over a radius scale full of magic numbers.
- Prefer tabular-nums on any page that shows money, dates, or counts.
- Do not invent a new token family for "one special case" — extend an existing one or accept that the case was wrong.

## Output Format

When the skill finishes, report:

```markdown
Brand System: <name>

- Archetype: <archetype>
- Audience: <primary> / <secondary>
- Palette direction: <3-word summary>
- Type pairing: <display> / <body> / <mono>
- Radius default: <sharp|slight|soft|pillowy|pill>
- Contrast floor: <AA|AAA>

Files written
- <path>: <one-line description>
- <path>: <one-line description>

Rollout state
- <N> hardcoded colors replaced
- <N> hardcoded radii replaced
- <N> hardcoded shadows replaced
- Old styles file: <removed|kept, reason>

Next verification
- <command or visual check the user should run>
```

## Related

- [[skill-issue]]
