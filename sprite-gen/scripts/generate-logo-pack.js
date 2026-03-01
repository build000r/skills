#!/usr/bin/env node
// Generate 4 thronglet SVG states from any logo/image (png/svg/webp/jpg).
// Output filenames match throngterm sprite contract.

const fs = require('fs');
const path = require('path');

function usage() {
  console.log('Usage: node generate-logo-pack.js --input <path> --output <dir> [--name <label>]');
  console.log('Example: node generate-logo-pack.js --input ../unclawg/public/larry.png --output ../unclawg/.throngterm/sprites --name Larry');
}

function argValue(args, key) {
  const i = args.indexOf(key);
  if (i === -1) return null;
  return args[i + 1] || null;
}

const args = process.argv.slice(2);
const inputPath = argValue(args, '--input') || argValue(args, '-i');
const outputDir = argValue(args, '--output') || argValue(args, '-o');
const label = argValue(args, '--name') || 'Custom';

if (!inputPath || !outputDir) {
  usage();
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
const mime = mimeByExt[ext] || 'application/octet-stream';
const dataUri = `data:${mime};base64,${fs.readFileSync(absInput).toString('base64')}`;

fs.mkdirSync(absOutput, { recursive: true });

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
    <image href="${dataUri}" x="48" y="48" width="416" height="416" preserveAspectRatio="xMidYMid meet"/>
  </g>`;

const drowsyBody = `  <g opacity="0.98" transform="translate(0,18)">
    <image href="${dataUri}" x="48" y="48" width="416" height="416" preserveAspectRatio="xMidYMid meet"/>
  </g>
  <rect x="110" y="118" width="292" height="68" fill="rgba(0,0,0,0.10)" rx="24"/>`;

const sleepingBody = `  <g transform="translate(256 256) rotate(90) translate(-256 -256)">
    <image href="${dataUri}" x="48" y="56" width="416" height="416" preserveAspectRatio="xMidYMid meet"/>
  </g>
${zText([{ x: 392, y: 92, size: 52, fill: '#A38B6B' }])}`;

const deepSleepBody = `  <g transform="translate(256 256) rotate(90) translate(-256 -256)">
    <image href="${dataUri}" x="48" y="64" width="416" height="416" preserveAspectRatio="xMidYMid meet"/>
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
