#!/usr/bin/env node
// Generate 4 thronglet SVG states from any logo/image (png/svg/webp/jpg).
// Output filenames match throngterm sprite contract.

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

function usage() {
  console.log('Usage: node generate-logo-pack.js --input <path> --output <dir> [--name <label>] [--bg-to-alpha] [--bg-threshold <0-255>] [--scale <0-1>]');
  console.log('Example: node generate-logo-pack.js --input ../unclawg/public/larry.png --output ../unclawg/.throngterm/sprites --name Larry --bg-to-alpha');
}

function argValue(args, key) {
  const i = args.indexOf(key);
  if (i === -1) return null;
  return args[i + 1] || null;
}

function hasFlag(args, key) {
  return args.includes(key);
}

const args = process.argv.slice(2);
const inputPath = argValue(args, '--input') || argValue(args, '-i');
const outputDir = argValue(args, '--output') || argValue(args, '-o');
const label = argValue(args, '--name') || 'Custom';
const bgToAlpha = hasFlag(args, '--bg-to-alpha');
const bgThresholdRaw = argValue(args, '--bg-threshold');
const bgThreshold = bgThresholdRaw ? Number(bgThresholdRaw) : 16;
const scaleRaw = argValue(args, '--scale');
const scale = scaleRaw ? Number(scaleRaw) : 0.8;

if (!inputPath || !outputDir) {
  usage();
  process.exit(1);
}

if (!Number.isInteger(bgThreshold) || bgThreshold < 0 || bgThreshold > 255) {
  console.error('--bg-threshold must be an integer between 0 and 255.');
  process.exit(1);
}

if (!Number.isFinite(scale) || scale <= 0 || scale > 1) {
  console.error('--scale must be a number > 0 and <= 1.');
  process.exit(1);
}

const absInput = path.resolve(process.cwd(), inputPath);
const absOutput = path.resolve(process.cwd(), outputDir);

if (!fs.existsSync(absInput)) {
  console.error(`Input not found: ${absInput}`);
  process.exit(1);
}

const ext = path.extname(absInput).toLowerCase();
const mimeByExt = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.svg': 'image/svg+xml',
};

function maybeConvertBgToAlpha(inputPathAbs, inputExt, threshold) {
  const rasterExts = new Set(['.png', '.jpg', '.jpeg', '.webp']);
  if (!rasterExts.has(inputExt)) {
    console.warn(`--bg-to-alpha ignored for non-raster input: ${inputExt}`);
    return { mime: mimeByExt[inputExt] || 'application/octet-stream', bytes: fs.readFileSync(inputPathAbs) };
  }

  const tmpOut = path.join(
    os.tmpdir(),
    `sprite-gen-alpha-${process.pid}-${Date.now()}-${Math.random().toString(16).slice(2)}.png`,
  );

  // Flood-fill near-black pixels connected to the image border and set them transparent.
  const pyScript = `
import sys
from collections import deque
try:
    from PIL import Image
except Exception:
    sys.stderr.write("Pillow is required for --bg-to-alpha. Install with: python3 -m pip install pillow\\n")
    sys.exit(2)

inp = sys.argv[1]
thr = int(sys.argv[2])
out = sys.argv[3]

img = Image.open(inp).convert("RGBA")
w, h = img.size
pix = img.load()

def is_bg(x, y):
    r, g, b, _a = pix[x, y]
    return r <= thr and g <= thr and b <= thr

bg = [[False] * w for _ in range(h)]
q = deque()

for x in range(w):
    for y in (0, h - 1):
        if is_bg(x, y) and not bg[y][x]:
            bg[y][x] = True
            q.append((x, y))

for y in range(h):
    for x in (0, w - 1):
        if is_bg(x, y) and not bg[y][x]:
            bg[y][x] = True
            q.append((x, y))

while q:
    x, y = q.popleft()
    for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
        if 0 <= nx < w and 0 <= ny < h and not bg[ny][nx] and is_bg(nx, ny):
            bg[ny][nx] = True
            q.append((nx, ny))

for y in range(h):
    for x in range(w):
        r, g, b, a = pix[x, y]
        if bg[y][x]:
            pix[x, y] = (r, g, b, 0)

img.save(out, format="PNG")
`;

  const result = spawnSync('python3', ['-c', pyScript, inputPathAbs, String(threshold), tmpOut], {
    encoding: 'utf8',
  });

  if (result.status !== 0) {
    if (result.stderr) process.stderr.write(result.stderr);
    console.error('--bg-to-alpha failed.');
    process.exit(1);
  }

  const bytes = fs.readFileSync(tmpOut);
  fs.unlinkSync(tmpOut);
  return { mime: 'image/png', bytes };
}

const inputPayload = bgToAlpha
  ? maybeConvertBgToAlpha(absInput, ext, bgThreshold)
  : { mime: mimeByExt[ext] || 'application/octet-stream', bytes: fs.readFileSync(absInput) };

if (bgToAlpha) {
  console.log(`Background alpha key: enabled (threshold ${bgThreshold})`);
}

const dataUri = `data:${inputPayload.mime};base64,${inputPayload.bytes.toString('base64')}`;

fs.mkdirSync(absOutput, { recursive: true });

const CANVAS = 512;
const size = Math.round(CANVAS * scale);
const baseX = Math.round((CANVAS - size) / 2);
const baseY = baseX;
const sleepY = baseY + 8;
const deepSleepY = baseY + 16;

console.log(`Scale: ${scale} (image box ${size}x${size})`);

function zText(lines) {
  return lines
    .map((line) => `    <text x="${line.x}" y="${line.y}" fill="${line.fill}" font-size="${line.size}" font-family="monospace" font-weight="700">Z</text>`)
    .join('\n');
}

function makeSvg(title, body) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512" role="img" aria-label="${title}">
  <title>${title}</title>
${body}
</svg>\n`;
}

const activeBody = `  <g>
    <image href="${dataUri}" x="${baseX}" y="${baseY}" width="${size}" height="${size}" preserveAspectRatio="xMidYMid meet"/>
  </g>`;

const drowsyBody = `  <g opacity="0.98" transform="translate(0,18)">
    <image href="${dataUri}" x="${baseX}" y="${baseY}" width="${size}" height="${size}" preserveAspectRatio="xMidYMid meet"/>
  </g>
  <rect x="110" y="118" width="292" height="68" fill="rgba(0,0,0,0.10)" rx="24"/>`;

const sleepingBody = `  <g transform="translate(256 256) rotate(90) translate(-256 -256)">
    <image href="${dataUri}" x="${baseX}" y="${sleepY}" width="${size}" height="${size}" preserveAspectRatio="xMidYMid meet"/>
  </g>
${zText([{ x: 392, y: 92, size: 52, fill: '#A38B6B' }])}`;

const deepSleepBody = `  <g transform="translate(256 256) rotate(90) translate(-256 -256)">
    <image href="${dataUri}" x="${baseX}" y="${deepSleepY}" width="${size}" height="${size}" preserveAspectRatio="xMidYMid meet"/>
  </g>
  <rect x="0" y="0" width="512" height="512" fill="rgba(0,0,0,0.06)"/>
${zText([
  { x: 368, y: 70, size: 42, fill: '#8A7356' },
  { x: 412, y: 122, size: 56, fill: '#6D5A46' },
  { x: 452, y: 186, size: 70, fill: '#4F4033' },
])}`;

const files = [
  ['active.svg', makeSvg(`${label} Thronglet - Active`, activeBody)],
  ['drowsy.svg', makeSvg(`${label} Thronglet - Drowsy`, drowsyBody)],
  ['sleeping.svg', makeSvg(`${label} Thronglet - Sleeping`, sleepingBody)],
  ['deep_sleep.svg', makeSvg(`${label} Thronglet - Deep Sleep`, deepSleepBody)],
];

for (const [name, contents] of files) {
  fs.writeFileSync(path.join(absOutput, name), contents, 'utf8');
  console.log(`wrote ${path.join(absOutput, name)}`);
}

console.log('\nDone.');
