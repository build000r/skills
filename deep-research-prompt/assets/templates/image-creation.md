# Image creation prompt template

Starting skeleton for high-detail image generation prompts intended for ChatGPT image creation (gpt-image / DALL-E surface) via Oracle browser handoff. Same hygiene rules as research prompts: self-announcing first line, single fenced code block, no terminal chrome, copy instructions outside the block.

The point of this template is to spec the image at the same level of mechanical specificity a deep research prompt specs an N-entity report. Vague image prompts produce generic stock-art results; this template forces the layered detail (composition, lighting, style, palette, atmosphere, constraints) that a serious image generation tool can actually act on.

---

```
You are an image generation tool. Produce one image matching the specification below. Generate the image — do not produce a written description in lieu of the image, and do not ask clarifying questions before generating. If a field is genuinely impossible, generate the closest faithful version and note the deviation in the caption afterward.

# Subject
[The primary subject. Who or what, doing what. Include concrete physical description: build, posture, clothing, expression, action mid-frame. Avoid abstractions like "powerful" or "elegant" — describe what would be visible.]

# Composition and framing
- Shot type: [extreme close-up / close-up / medium / medium-wide / wide / establishing]
- Camera angle: [eye-level / low-angle / high-angle / overhead / dutch / over-the-shoulder]
- Focal length character: [wide ~24mm / normal ~50mm / portrait ~85mm / telephoto ~135mm+]
- Depth of field: [shallow with subject isolation / moderate / deep with everything sharp]
- Subject placement: [centered / rule-of-thirds left / rule-of-thirds right / leading-lines toward subject]
- Foreground / midground / background contents: [name what occupies each layer]

# Setting and environment
[Location. Time of day. Weather. Architectural or natural context. Ambient objects that anchor the scene. Be specific enough that a stock-photo result is clearly wrong.]

# Lighting
- Primary light source: [sun / window / practical lamp / off-camera key / overcast sky / etc.]
- Direction: [front / side / back / top / 45° key]
- Quality: [hard / soft / diffused / dappled]
- Color temperature: [warm tungsten ~3200K / neutral daylight ~5600K / cool overcast ~7000K / mixed]
- Shadow behavior: [deep contrast / soft falloff / fill from secondary source]
- Mood of light: [golden hour / blue hour / harsh noon / candlelit / neon-lit / studio]

# Style and medium
[Pick one and commit. Examples:
- Photographic: name a film stock or digital aesthetic (e.g., "Kodak Portra 400 character," "modern mirrorless clean digital," "wet-plate collodion"). Include lens character if relevant (vintage swirly bokeh, anamorphic flare, clinical sharpness).
- Illustration: named style or movement (e.g., "ligne claire," "mid-century UPA flat," "Studio Ghibli background painting"). Line weight, shading approach (cel / painterly / cross-hatched).
- 3D render: rendering aesthetic (e.g., "Pixar-character render," "Octane product render," "low-poly PS1-era").
- Painterly: medium (oil, gouache, watercolor) and named tradition or artist tendency.
Do NOT mix mediums unless the mix is the point.]

# Color palette
- Dominant colors: [2-3 named colors with rough proportion]
- Accent colors: [1-2 colors used sparingly for emphasis]
- Harmony: [complementary / analogous / triadic / split-complementary / monochrome]
- Saturation: [muted / natural / saturated / hyper-saturated]
- Contrast: [low / medium / high]

# Mood and atmosphere
[Emotional register in one or two sentences. What should the viewer feel in the first second? Energy level? Narrative implication — what just happened or is about to happen?]

# Detail and texture
[Surface materials and how they should read (matte / glossy / weathered / pristine). Texture density. How much background detail vs intentional negative space. Micro-detail to emphasize (skin pores, fabric weave, paint cracks, dust motes in light).]

# Aspect ratio and resolution
- Aspect ratio: [16:9 / 1:1 / 4:3 / 3:4 / 9:16 / 2:3 / 3:2]
- Orientation: [landscape / portrait / square]
- Intended use: [hero banner / social card / print / app icon / etc. — drives crop safety]

# Text in image
[Pick one:
- "No text, letters, numerals, watermarks, signatures, or logos in the image."
- Or: exact text in double quotes, with placement, language, and typographic intent (serif / sans / display / hand-lettered, weight, size relative to frame).]

# Source visual assets
[Use this section only when the request depends on visual references. List attached source image files first. Put source URLs, Midjourney `/styles/...` links, or `--sref` values under metadata only; do not rely on those links as the visual source.]

Bullet hygiene: write each entry as `path/to/image.ext — one-line role/purpose`, not just the bare path. When Oracle also passes the same path with `--file`, ChatGPT's composer sometimes swallows bare-path bullets (the line collapses to an empty `- `). The em-dash + role text survives that rendering.

- Attached source images: [for example, `/tmp/<slug>-source/portrait.webp — primary subject reference, derive expression and lighting only`]
- Source metadata: [original URL, Midjourney style URL, `/styles/...`, `--sref`, or "none"]
- How to use the source: [derive composition/palette/texture/shape logic from the attached images; do not copy literal motifs unless explicitly requested]

# Hard constraints
- Do NOT include: watermarks, signatures, logos, captions, borders, or stock-photo overlays unless explicitly specified above.
- Do NOT default to: [enumerate the generic drift modes for this subject — e.g., "smiling stock-photo poses," "lens flares as a substitute for atmosphere," "extra fingers or malformed hands," "AI-uncanny symmetric faces"].
- Stay within the named style. Do not blend with [ADJACENT STYLE THAT WOULD DILUTE IT].
- For unspecified regions, default to clean negative space or natural background extension. Do not invent additional subjects, props, or focal points beyond the spec.
- Anatomy and physics must be plausible unless the style explicitly permits stylization (and even then, name the stylization).
- If source visual assets are listed, use the attached images as the source of visual evidence. Do not assume a URL or Midjourney reference can be opened or remembered.

# What to return
The image, plus a short caption (3-5 sentences) describing what was actually generated so I can verify it matched the spec. If any element of the spec was impossible or had to be approximated, name it explicitly in the caption — do not silently substitute.
```

---

## How to use this template

1. Copy everything between the triple-backtick markers above.
2. Replace every `[BRACKETED PLACEHOLDER]` with concrete, visualizable detail. Vague placeholders ("a person doing something interesting") defeat the template.
3. If a section genuinely does not apply to the subject (e.g., "Text in image" for a pure landscape), still keep the section and write "Not applicable — pure landscape, no text expected" rather than deleting it. The structural completeness is part of what makes the prompt land.
4. Read the filled-in prompt top-to-bottom and check the validation list in `SKILL.md`. Fix anything that fails.
5. Wrap with copy instructions above the block and post-block notes below.
6. If shipping as Image creation handoff mode, also attach the Oracle wrapper (prompt file path, source image `--file` flags when applicable, run command, verification note) outside the block.
