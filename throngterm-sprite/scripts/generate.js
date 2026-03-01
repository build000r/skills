#!/usr/bin/env node
// Generate thronglet state-variant SVGs from a master pixel-art SVG.
//
// Usage:
//   node generate.js [path/to/thronglet.svg]
//
// If no argument given, searches for .throngterm/thronglet.svg by walking
// up from cwd.
//
// Outputs to .throngterm/sprites/:
//   active.svg, drowsy.svg, sleeping.svg, deep_sleep.svg
//
// Reads .throngterm/colors.json (if present) to override default colors.
// The master SVG must be a 512x512 pixel grid composed of 16x16 <rect> elements.

const fs = require("fs");
const path = require("path");

// ---- Resolve input ----

function findMasterSvg() {
  let dir = process.cwd();
  while (true) {
    const candidate = path.join(dir, ".throngterm", "thronglet.svg");
    if (fs.existsSync(candidate)) return candidate;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

const inputArg = process.argv[2];
const srcPath = inputArg || findMasterSvg();

if (!srcPath) {
  console.error("Error: No master SVG found.");
  console.error("Place your pixel-art SVG at .throngterm/thronglet.svg");
  console.error("or pass the path as an argument.");
  process.exit(1);
}

if (!fs.existsSync(srcPath)) {
  console.error(`Error: File not found: ${srcPath}`);
  process.exit(1);
}

// Output dir is always .throngterm/sprites/ relative to where the master SVG lives
const throngtermDir = path.dirname(srcPath);
const outDir = path.join(throngtermDir, "sprites");
fs.mkdirSync(outDir, { recursive: true });

console.log(`Master SVG: ${srcPath}`);
console.log(`Output dir: ${outDir}`);

// ---- Load color config ----
// .throngterm/colors.json overrides default fallback colors in generated SVGs.
// All fields optional. Format:
// {
//   "body": "#hex",      // main body color (CSS var --thr-body)
//   "outline": "#hex",   // outline/border (CSS var --thr-outline)
//   "accent": "#hex",    // darkest details (CSS var --thr-accent)
//   "skin": "#hex",      // face/belly skin tone
//   "white": "#hex",     // eye whites
//   "tan": "#hex",       // eye shadow
//   "black": "#hex",     // pupils, nose, feet
//   "shirt": "#hex"      // clothing (CSS var --thr-shirt)
// }

const DEFAULTS = {
  body: "#E07B39",
  outline: "#8B3D1F",
  accent: "#6B2A12",
  skin: "#F5C4A1",
  white: "#FFFFFF",
  tan: "#D9C8B8",
  black: "#1A1A1A",
  shirt: "#7AAFC8",
};

const colorsPath = path.join(throngtermDir, "colors.json");
let colors = { ...DEFAULTS };
if (fs.existsSync(colorsPath)) {
  try {
    const userColors = JSON.parse(fs.readFileSync(colorsPath, "utf8"));
    colors = { ...DEFAULTS, ...userColors };
    console.log(`Colors:     ${colorsPath}`);
  } catch (err) {
    console.warn(`Warning: Could not parse colors.json: ${err.message}`);
    console.warn("Using default colors.");
  }
} else {
  console.log("Colors:     defaults (no colors.json found)");
}

// ---- Parse SVG ----

const raw = fs.readFileSync(srcPath, "utf8");
const rects = [];
const re =
  /<rect x="(\d+)" y="(\d+)" width="16" height="16" fill="(#[A-Fa-f0-9]+)"\/>/g;
let m;
while ((m = re.exec(raw)) !== null) {
  rects.push({ x: +m[1], y: +m[2], fill: m[3] });
}

if (rects.length === 0) {
  console.error("Error: No 16x16 rects found in master SVG.");
  console.error("The SVG must contain <rect> elements with width/height 16.");
  process.exit(1);
}

console.log(`Parsed ${rects.length} rects`);

// ---- Color mapping ----
// Maps fill colors in the master SVG to short CSS class names.
// The master SVG should use the STANDARD hex colors below.

const FILL_TO_CLASS = {
  "#E07B39": "b",
  "#8B3D1F": "o",
  "#6B2A12": "a",
  "#F5C4A1": "s",
  "#FFFFFF": "w",
  "#D9C8B8": "t",
  "#1A1A1A": "k",
  "#7AAFC8": "c",
};

// Build style block using the resolved colors (defaults or overrides)
const STYLE_BLOCK = `  <style>
    .b { fill: var(--thr-body, ${colors.body}); }
    .o { fill: var(--thr-outline, ${colors.outline}); }
    .a { fill: var(--thr-accent, ${colors.accent}); }
    .s { fill: ${colors.skin}; }
    .w { fill: ${colors.white}; }
    .t { fill: ${colors.tan}; }
    .k { fill: ${colors.black}; }
    .c { fill: var(--thr-shirt, ${colors.shirt}); }
  </style>`;

const baseRects = rects.map((r) => ({
  x: r.x,
  y: r.y,
  cls: FILL_TO_CLASS[r.fill] || "k",
}));

// ---- Helpers ----

function key(x, y) {
  return `${x},${y}`;
}

function applyOverrides(rects, overrides) {
  return rects.map((r) => {
    const k = key(r.x, r.y);
    return k in overrides ? { ...r, cls: overrides[k] } : r;
  });
}

function addRects(rects, extras) {
  return [...rects, ...extras];
}

function buildSvg(title, rectData) {
  const lines = rectData
    .map(
      (r) =>
        `  <rect x="${r.x}" y="${r.y}" width="16" height="16" class="${r.cls}"/>`,
    )
    .join("\n");

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512" shape-rendering="crispEdges">
  <title>${title}</title>
${STYLE_BLOCK}
${lines}
</svg>
`;
}

// ---- Pixel art "z" letter (3x4 at 16px grid) ----

function zPixels(bx, by, cls = "o") {
  return [
    { x: bx, y: by, cls },
    { x: bx + 16, y: by, cls },
    { x: bx + 32, y: by, cls },
    { x: bx + 16, y: by + 16, cls },
    { x: bx, y: by + 32, cls },
    { x: bx, y: by + 48, cls },
    { x: bx + 16, y: by + 48, cls },
    { x: bx + 32, y: by + 48, cls },
  ];
}

// ---- Posture transforms ----

function sittingTransform(rects) {
  const loweredBody = rects
    .filter((r) => r.y < 400)
    .map((r) => ({ ...r, y: r.y + 16 }));

  return addRects(loweredBody, [
    { x: 112, y: 400, cls: "o" },
    { x: 128, y: 400, cls: "o" },
    { x: 144, y: 400, cls: "o" },
    { x: 368, y: 400, cls: "o" },
    { x: 384, y: 400, cls: "o" },
    { x: 400, y: 400, cls: "o" },
    { x: 96, y: 416, cls: "b" },
    { x: 112, y: 416, cls: "b" },
    { x: 128, y: 416, cls: "o" },
    { x: 384, y: 416, cls: "o" },
    { x: 400, y: 416, cls: "b" },
    { x: 416, y: 416, cls: "b" },
    { x: 80, y: 432, cls: "k" },
    { x: 96, y: 432, cls: "k" },
    { x: 416, y: 432, cls: "k" },
    { x: 432, y: 432, cls: "k" },
  ]);
}

function layingTransform(rects) {
  return rects.map((r) => ({
    x: 496 - r.y,
    y: r.x,
    cls: r.cls,
  }));
}

// ---- State variants ----

const activeRects = baseRects;

const drowsyOverrides = {
  [key(192, 208)]: "a",
  [key(208, 208)]: "a",
  [key(224, 208)]: "a",
  [key(288, 208)]: "a",
  [key(304, 208)]: "a",
  [key(320, 208)]: "a",
  [key(192, 224)]: "s",
  [key(208, 224)]: "s",
  [key(304, 224)]: "s",
  [key(320, 224)]: "s",
};
const drowsyRects = sittingTransform(
  applyOverrides(baseRects, drowsyOverrides),
);

const sleepOverrides = {
  [key(192, 208)]: "s",
  [key(208, 208)]: "s",
  [key(224, 208)]: "s",
  [key(192, 224)]: "s",
  [key(208, 224)]: "s",
  [key(224, 224)]: "s",
  [key(192, 240)]: "s",
  [key(208, 240)]: "a",
  [key(224, 240)]: "a",
  [key(192, 256)]: "s",
  [key(208, 256)]: "s",
  [key(224, 256)]: "s",
  [key(288, 208)]: "s",
  [key(304, 208)]: "s",
  [key(320, 208)]: "s",
  [key(288, 224)]: "s",
  [key(304, 224)]: "s",
  [key(320, 224)]: "s",
  [key(288, 240)]: "a",
  [key(304, 240)]: "a",
  [key(320, 240)]: "s",
  [key(288, 256)]: "s",
  [key(304, 256)]: "s",
  [key(320, 256)]: "s",
};
const sleepLaying = layingTransform(
  applyOverrides(baseRects, sleepOverrides),
);
const sleepRects = addRects(sleepLaying, zPixels(384, 48));

const deepSleepOverrides = {
  ...sleepOverrides,
  [key(240, 304)]: "k",
  [key(256, 304)]: "k",
  [key(272, 304)]: "k",
  [key(256, 320)]: "k",
};
const deepSleepLaying = layingTransform(
  applyOverrides(baseRects, deepSleepOverrides),
);
const deepSleepRects = addRects(deepSleepLaying, [
  ...zPixels(432, 0, "o"),
  ...zPixels(384, 32, "a"),
  ...zPixels(464, 48, "a"),
]);

// ---- Write output ----

const variants = [
  { name: "active.svg", title: "Thronglet - Active", data: activeRects },
  { name: "drowsy.svg", title: "Thronglet - Drowsy", data: drowsyRects },
  { name: "sleeping.svg", title: "Thronglet - Sleeping", data: sleepRects },
  {
    name: "deep_sleep.svg",
    title: "Thronglet - Deep Sleep",
    data: deepSleepRects,
  },
];

for (const v of variants) {
  const svg = buildSvg(v.title, v.data);
  const out = path.join(outDir, v.name);
  fs.writeFileSync(out, svg);
  console.log(`  ${v.name} (${v.data.length} rects)`);
}

console.log("\nDone! Generated 4 state variants in .throngterm/sprites/");
console.log("Baked-in colors (override at runtime via CSS vars):");
console.log(`  --thr-body     ${colors.body}`);
console.log(`  --thr-outline  ${colors.outline}`);
console.log(`  --thr-accent   ${colors.accent}`);
console.log(`  --thr-shirt    ${colors.shirt}`);
if (colors.skin !== DEFAULTS.skin) console.log(`  skin           ${colors.skin}`);
if (colors.black !== DEFAULTS.black)
  console.log(`  black          ${colors.black}`);
