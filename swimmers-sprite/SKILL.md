---
name: swimmers-sprite
description: Generate thronglet state-variant SVG packs from a master pixel-art SVG or logo asset for per-repo swimmers overrides. Use for "generate sprites", "thronglet sprites", "swimmers-sprite", "/sprite-gen", custom thronglet work, or setting up .throngterm in a repo.
---

# Sprite Gen

Generate the 4 thronglet state-variant SVGs from either:

- a master pixel-art SVG (`.throngterm/thronglet.svg`)
- any logo/image asset (png/svg/webp/jpg)

## Quick Start

```bash
# Pixel-art master mode
node {skill_dir}/scripts/generate.js

# Logo/image mode
node {skill_dir}/scripts/generate-logo-pack.js \
  --input /abs/path/to/logo.png \
  --output /abs/path/to/repo/.throngterm/sprites \
  --name "RepoName" \
  --scale 0.8
```

If your source logo is a non-transparent PNG/JPG with a dark baked background,
add:

```bash
  --bg-to-alpha --bg-threshold 16
```

Finds `.throngterm/thronglet.svg` by walking up from cwd, outputs to
`.throngterm/sprites/`:

| File | State | Pose |
|------|-------|------|
| `active.svg` | Standing, eyes open | Upright |
| `drowsy.svg` | Sitting, heavy eyelids | Lowered body, folded legs |
| `sleeping.svg` | Laying, eyes closed, one Z | Rotated 90° CW |
| `deep_sleep.svg` | Laying, mouth open, three Z's | Rotated 90° CW |

## Setup for a New Repo

### Option A: Pixel-art master (existing behavior)

1. Create the convention directory and master SVG:

```bash
mkdir -p .throngterm
# Place or create a 512x512 pixel-art SVG at:
# .throngterm/thronglet.svg
```

2. Run the generator:

```bash
node {skill_dir}/scripts/generate.js
```

3. Verify outputs exist:

```bash
ls .throngterm/sprites/
# active.svg  drowsy.svg  sleeping.svg  deep_sleep.svg
```

4. Optionally gitignore the generated files (regenerate on demand):

```gitignore
.throngterm/sprites/
```

### Option B: Logo/image-based character (new behavior)

Use this when your repo already has a logo/mascot asset (for example
`public/logo.png`, `public/mascot.png`, `public/brand.svg`):

```bash
mkdir -p .throngterm/sprites
node {skill_dir}/scripts/generate-logo-pack.js \
  --input ./public/logo.png \
  --output ./.throngterm/sprites \
  --name "MyRepo" \
  --scale 0.8
```

For non-transparent logos with a dark background:

```bash
node {skill_dir}/scripts/generate-logo-pack.js \
  --input ./public/logo.png \
  --output ./.throngterm/sprites \
  --name "MyRepo" \
  --scale 0.8 \
  --bg-to-alpha \
  --bg-threshold 16
```

`--bg-to-alpha` flood-fills near-black pixels connected to the image border and
makes them transparent before embedding. Increase threshold (for example `20`)
if the background is dark gray; decrease it if interior dark pixels are being
removed.

`--scale` controls the image box size inside the 512x512 sprite canvas. `0.8`
is a good default for slightly smaller logo characters.

This writes:

- `active.svg`
- `drowsy.svg`
- `sleeping.svg`
- `deep_sleep.svg`

with the same naming/state contract expected by swimmers.

## Master SVG Format

The master SVG must be a **512x512 pixel grid** composed of `<rect>` elements:

- Each rect: `width="16" height="16"` (32x32 tile grid)
- Colors map to CSS classes with custom property support:

| Hex Color | Role | CSS Variable |
|-----------|------|-------------|
| `#E07B39` | Body | `--thr-body` |
| `#8B3D1F` | Outline | `--thr-outline` |
| `#6B2A12` | Accent | `--thr-accent` |
| `#F5C4A1` | Skin | (fixed) |
| `#FFFFFF` | Eye whites | (fixed) |
| `#D9C8B8` | Eye shadow | (fixed) |
| `#1A1A1A` | Black (pupils, feet) | (fixed) |
| `#7AAFC8` | Clothing | `--thr-shirt` |

Use the standard hex values above. Unmapped colors default to black.

## Self-Contained SVG Rule (Important)

Generated/committed sprite SVGs must be self-contained.

Do not rely on external `<image href="/logo.png">` paths inside sprite SVGs,
because swimmers injects SVG inline from another app context and those URLs
can resolve to the wrong origin, rendering blank sprites.

Validation checks:

```bash
# Should print nothing for valid self-contained packs
rg -n '<image[^>]+href="/' .throngterm/sprites
rg -n '<image[^>]+href="./' .throngterm/sprites
```

## Custom Brand Colors

Create `.throngterm/colors.json` to override default colors with your brand
palette. All fields are optional — only override what you need:

```json
{
  "body": "#b89875",
  "outline": "#3d2f24",
  "accent": "#1d1914",
  "skin": "#f7f4df",
  "tan": "#ece2cf",
  "black": "#111111",
  "shirt": "#aa9370"
}
```

Colors are baked into the generated SVGs as CSS `var()` fallbacks. Swimmers
can still override them at runtime via CSS custom properties (`--thr-body`,
`--thr-outline`, `--thr-accent`, `--thr-shirt`).

To brand a repo: copy the standard master SVG, create `colors.json` with your
palette, and run the generator. The thronglet keeps its character shape but
wears your brand.

## How Swimmers Uses These

When Swimmers backend detects a `.throngterm/sprites/` directory in a
session's working directory (or any ancestor), it reads the 4 SVGs and serves
them inline via the bootstrap API. The frontend renders them instead of the
built-in defaults, preserving the idle-depth progression
(active -> drowsy -> sleeping -> deep_sleep) and tool-based CSS recoloring.
