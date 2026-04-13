# Color Discovery

How to turn a brand brief + logo into the HSL triplets that fill tokens.css.

## 1. Start from the logo, not from Pantone

Open the logo. Identify:

- **Ink**: the darkest committed color. Often near-black, not pure black.
- **Paper**: the lightest committed color. Often near-white, not pure white.
- **Signal**: any color that isn't ink or paper. If there are two or more, pick the one that carries the most visual weight.

For a pure black/white logo, ink = near-black, paper = near-white, signal = none yet — you will add it in step 3.

## 2. Fix neutrals first

Neutrals are the majority of the pixels. Get them right before touching accent.

- `--background`: the paper value. HSL with saturation ≤ 4% and lightness ≥ 96% for light mode; ≤ 8% and ≤ 10% for dark mode.
- `--foreground`: the ink value. Aim for AA on `--background` minimum; AAA for finance/legal/health.
- `--muted`: a desaturated, compressed range for body-secondary text. Shift lightness toward the background by ~35-45% of the range between `--foreground` and `--background`.
- `--muted-foreground`: the text color that sits on `--muted`. Must still pass AA on `--muted`.
- `--border`: a single hairline value. Often `foreground` at 10-15% alpha, but express as a solid HSL in the token file to keep things grep-able.
- `--input`: usually equal to `--border`; override only if the brief calls for it.
- `--ring`: focus ring color. Always distinct from `--border`. Usually a desaturated primary.

**Contrast check**: run every foreground/background pair through a WCAG calculator before writing them to tokens.css. A pretty palette that fails AA is not a palette.

## 3. Pick the accent

One primary accent. One.

- If the logo has a signal color, use it.
- If the logo is pure neutral, pick the accent from the archetype: trust-finance → navy or teal, architectural-minimalism → nothing or a single structural color, friendly-consumer → warm coral or green.
- The accent goes into `--primary`. Its legible text color goes into `--primary-foreground`. These must pass AA together.
- `--secondary` is almost always a neutral — a lifted version of `--muted`. Do not pick a second chromatic color unless you have a specific justification (e.g., a data-visualization surface that needs a paired category color).

## 4. Pick the semantics

- `--destructive`: warm red. Must pass AA on `--background` when used for text, and AA on itself for `--destructive-foreground`.
- `--success`: green. Optional; many brands reuse `--primary` as the positive signal to stay monochrome.
- `--warning`: amber. Optional. Do not add semantic colors you will not actually use.

## 5. Derive elevation

Do not invent three random greys for surface layers. Derive them.

- `--surface-1`: equal to `--background`.
- `--surface-2`: `--background` lightness shifted toward `--foreground` by 2-4% (light mode) or shifted away by the same amount (dark mode).
- `--surface-3`: shift again by the same delta.

This keeps elevation coherent across modes and themes.

## 6. Derive the dark mode

Dark mode is not a separate palette. It is the same hues with inverted lightness and retuned saturation.

- Swap `--background` and `--foreground` roles, then ease saturation on the dark background so it doesn't look murky.
- Keep `--primary` hue stable; adjust lightness so text on primary still passes AA.
- Re-derive `--muted`, `--border`, and elevation from the new background.

If the dark mode palette has any new hues that aren't present in light mode, you did it wrong.

## 7. Write the values

Fill in tokens.css. Use HSL triplets in the shadcn convention:

```css
--background: 0 0% 100%;
--foreground: 222.2 84% 4.9%;
```

Then in consuming code:

```css
background-color: hsl(var(--background));
color: hsl(var(--foreground));
```

This looks verbose but it is the contract shadcn components expect. Do not "simplify" it.

## Red flags

- More than two chromatic colors in the light palette. Reduce.
- `--border` and `--foreground` are the same color with alpha. Write them as solid HSL.
- Dark mode has hues the light mode doesn't. Rebuild from light.
- Any foreground/background pair fails AA. Fix before shipping.
- You picked an accent before you picked the neutrals. Start over.
