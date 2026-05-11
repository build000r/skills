#!/usr/bin/env node
// Guard for ChatGPT tab-local tools (Deep research / Create image) with Oracle.
//
// The toggle helpers can enable a composer tool on a specific CDP target, but
// Oracle must submit in that same target. Some Oracle browser builds open a
// fresh dedicated ChatGPT tab for every remote run, which loses the tab-local
// tool state. This guard fails closed for those builds.

import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, realpathSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { exit } from 'node:process';

const JSON_MODE = process.argv.includes('--json');

function emit(payload) {
  if (JSON_MODE) {
    console.log(JSON.stringify(payload, null, 2));
    return;
  }
  const level = payload.safe ? 'safe' : 'blocked';
  console.log(`Oracle tab-local route guard: ${level}`);
  console.log(payload.reason);
  for (const note of payload.notes ?? []) {
    console.log(`- ${note}`);
  }
}

function whichOracle() {
  if (process.env.ORACLE_BIN) {
    return resolve(process.env.ORACLE_BIN);
  }
  return execFileSync('which', ['oracle'], { encoding: 'utf8' }).trim();
}

function findDistRoot(oracleBin) {
  let current = dirname(realpathSync(oracleBin));
  for (let i = 0; i < 8; i += 1) {
    const candidate = join(current, 'src', 'browser', 'chromeLifecycle.js');
    if (existsSync(candidate)) {
      return current;
    }
    current = dirname(current);
  }
  return null;
}

function main() {
  let oracleBin;
  let help = '';
  try {
    oracleBin = whichOracle();
    help = execFileSync(oracleBin, ['--help'], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    });
  } catch (error) {
    emit({
      safe: false,
      reason: `Unable to inspect oracle: ${error instanceof Error ? error.message : String(error)}`,
      notes: ['Do not launch a tab-local-tool run until oracle is available and inspected.'],
    });
    exit(5);
  }

  const hasTargetOption =
    /--(?:chatgpt|browser|remote-chrome)-(?:target|target-id)\b/.test(help) ||
    /--(?:chatgpt|browser)-reuse-(?:tab|target)\b/.test(help) ||
    /--pre-submit-hook\b/.test(help);

  if (hasTargetOption) {
    emit({
      safe: true,
      reason: 'Oracle exposes a target-selection or pre-submit hook option in --help.',
      notes: [
        'Use that option to submit in the exact CDP target where the composer tool was toggled.',
        'Do not rely on --chatgpt-url alone as proof of same-tab routing.',
      ],
    });
    exit(0);
  }

  const distRoot = findDistRoot(oracleBin);
  if (!distRoot) {
    emit({
      safe: false,
      reason: 'Oracle has no visible same-tab target option, and its installed browser source could not be inspected.',
      notes: [
        'Fail closed: do not submit a Deep research or Create image run automatically.',
        'Prepare the prompt/spec file and ask whether to use a manual fallback or a non-tab-local Oracle run.',
      ],
    });
    exit(9);
  }

  const lifecyclePath = join(distRoot, 'src', 'browser', 'chromeLifecycle.js');
  const lifecycle = readFileSync(lifecyclePath, 'utf8');
  const opensDedicatedRemoteTarget =
    /function\s+connectToRemoteChrome[\s\S]*connectToNewTarget\s*\(\s*host\s*,\s*port\s*,\s*targetUrl/.test(
      lifecycle,
    ) ||
    /if\s*\(\s*targetUrl\s*\)[\s\S]*CDP\.New\s*\(/.test(lifecycle);

  if (opensDedicatedRemoteTarget) {
    emit({
      safe: false,
      reason:
        'This Oracle browser build opens a fresh dedicated remote Chrome tab for the ChatGPT URL before submitting.',
      notes: [
        'Deep research and Create image are tab/composer-local, so a tab toggled before Oracle starts will not carry over.',
        'Do not run the automatic submit path; it can produce a normal non-Deep-Research text turn or a text-only image turn.',
        `Evidence: ${lifecyclePath}`,
      ],
    });
    exit(9);
  }

  emit({
    safe: false,
    reason: 'Oracle has no visible same-tab target option; same-tab routing is unproven.',
    notes: [
      'Fail closed until Oracle exposes target-id attachment, tab reuse, or a pre-submit hook.',
      `Inspected: ${lifecyclePath}`,
    ],
  });
  exit(9);
}

main();
