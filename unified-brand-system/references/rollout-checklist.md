# Rollout Checklist

How to replace an existing brand system with the new one without breaking the site or leaving orphan styles behind.

## Before You Start

1. Confirm the project has a single root layout that imports global CSS. Branded rollout is hard when there are 4 competing style entry points.
2. Run `git status` — the rollout should be one clean commit or one clean branch.
3. Identify every place the old palette is referenced:
   ```bash
   # Find every old color literal
   rg -n '#[0-9a-fA-F]{3,8}' src/
   rg -n 'rgba?\(' src/
   # Find every use of old CSS variables
   rg -n 'var\(--' src/
   ```
   Save the counts. You'll check them again at the end.

## 1. Drop in the new files

Add, do not replace yet:

- `src/styles/tokens.css` — from assets/templates/tokens.css with real values.
- `src/styles/fonts.css` — from assets/templates/fonts.css.
- `src/styles/globals.css` — imports tokens + fonts + base element resets.
- `tailwind.config.ts` — from assets/templates/tailwind.config.ts, only if the project uses Tailwind.

## 2. Add Tailwind if the project doesn't have it (optional)

Only if the user asked for shadcn component compatibility or the project will benefit from utility classes.

For Astro:
```bash
npm install -D @tailwindcss/vite tailwindcss
```

Then edit `astro.config.mjs`:
```js
import tailwind from '@tailwindcss/vite';
// ...
export default defineConfig({
  vite: { plugins: [tailwind()] },
});
```

For Next/Vite, follow the official Tailwind v4 setup. Do not invent your own setup.

If the project already has vanilla CSS and the user does not want Tailwind, skip this step entirely. Tokens.css alone gives you a unified brand system. Tailwind adds utility ergonomics on top, nothing more.

## 3. Wire the new styles into the root layout

Find the root layout (Astro: `src/layouts/BaseLayout.astro`; Next: `app/layout.tsx`; Vite: `src/main.ts`). Add the imports in this exact order:

```js
import '../styles/tokens.css';  // 1. tokens first
import '../styles/fonts.css';    // 2. font faces
import '../styles/globals.css';  // 3. base element styles + Tailwind directives
```

Order matters. Tokens must be defined before anything consumes them.

## 4. Replace hardcoded colors

Use your `rg` counts from "Before You Start." Walk every match:

- `#16211b` → `hsl(var(--foreground))`
- `#efe4d2` → `hsl(var(--background))`
- `rgba(22, 33, 27, 0.12)` → `hsl(var(--border))` (express as solid first; use alpha only via an overlay token)
- `linear-gradient(..., #0f766e, ...)` → either a token gradient or a flat `--primary` background, depending on archetype
- Brand accents in hero blocks → `hsl(var(--primary))`

After the sweep:
```bash
rg -n '#[0-9a-fA-F]{3,8}' src/  # should return close to zero
```

The only acceptable hex that survives is (a) SVG inline fills that truly are part of an icon, and (b) hex values inside comments.

## 5. Replace hardcoded radii

```bash
rg -n 'border-radius:' src/
```

Walk every match. Replace with `var(--radius)`, `calc(var(--radius) * N)`, or `9999px` (only for pills).

## 6. Replace hardcoded shadows

```bash
rg -n 'box-shadow:' src/
```

Replace with `var(--shadow-sm)`, `var(--shadow-md)`, or `var(--shadow-lg)`. If a unique shadow is needed, add a new token — do not leave a literal.

## 7. Replace hardcoded fonts

```bash
rg -n 'font-family:' src/
```

Every match should become `var(--font-display)`, `var(--font-body)`, or `var(--font-mono)`. The only exception is the `@font-face` block in fonts.css.

## 8. Replace hardcoded text sizes

```bash
rg -n 'font-size:' src/
```

Every match should become one of the `--text-*` tokens. For `clamp()` responsive sizes, derive from the tokens:

```css
font-size: clamp(var(--text-2xl), 5vw, var(--text-5xl));
```

## 9. Visually diff the site

Start the dev server. Walk at least these routes:

- Homepage / landing
- A content detail page
- A form page
- Any dashboard or app surface
- Mobile width at each of the above

Note anything that looks wrong. Fix token-level mistakes at the token file, not in the component.

## 10. Delete the old styles

Only after:

- `rg '#[0-9a-fA-F]{3,8}' src/` returns near-zero (icon exceptions only)
- `rg 'font-family:' src/styles/` matches zero outside `fonts.css`
- `rg 'border-radius:' src/` returns zero literals that aren't `9999px`
- The visual diff looks right

...do this:

```bash
git rm src/styles/global.css  # or whatever the old file was
```

And confirm:
```bash
rg -n 'global\.css' src/  # should return zero
npm run build              # should succeed
```

## 11. Commit

One clean commit. Message like:

```
feat(brand): adopt unified brand system (<archetype>)

- Add shadcn-compatible token set (tokens.css, fonts.css, globals.css)
- Replace hardcoded colors/radii/shadows with token references
- Retire src/styles/global.css
```

## Red Flags During Rollout

- Build succeeds but visual diff is wrong in only one place → component is probably hardcoding a value that slipped past the grep. Search harder.
- Tokens.css works in dev but not in production build → you're likely not importing tokens.css at all, or the import order is wrong.
- Dark mode looks correct but light mode doesn't → you derived light from dark instead of the other way around. Rebuild light first.
- A page looks "unstyled" → globals.css reset is too aggressive. Tune the reset, do not add component-level overrides.
- You're tempted to leave the old global.css "just for a few classes" → find those classes, port them, delete the file. Two style files = future drift.
