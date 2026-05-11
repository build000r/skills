#!/usr/bin/env node
// Toggle ChatGPT's "Create image" tool on the currently focused composer.
//
// Sibling of toggle-deep-research.mjs. Same CDP pattern:
// connects to a running Chrome via DevTools (default 127.0.0.1:9222),
// finds a chatgpt.com tab, opens the composer tool picker ("+" button),
// and clicks the "Create image" (or "Image") menu item.
//
// Intended flow (see references/chatgpt-image-toggle.md):
//   1. Skill launches Chrome headful with --remote-debugging-port=9222 using
//      the user's logged-in ChatGPT profile.
//   2. Skill opens the intended ChatGPT tab(s).
//   3. Skill runs this script to turn Image mode on for the chosen tab,
//      passing ORACLE_CHATGPT_TARGET_ID or ORACLE_CHATGPT_URL_MATCH when more
//      than one chatgpt.com tab is open. The script REFUSES to silently pick
//      one of N matching tabs; it must be told which.
//   4. Skill runs `oracle --remote-chrome 127.0.0.1:9222 --browser-model-strategy ignore ...`
//      only when check-oracle-tab-local-route.mjs proves Oracle can submit in
//      the exact target where this helper toggled image mode.
//
// Parallel runs: spawn one chatgpt.com tab per run, give each a unique URL
// fragment or query string, and set ORACLE_CHATGPT_URL_MATCH to that unique
// substring before invoking this helper for the corresponding run. Each run
// then runs the route guard before any Oracle submission. The shared env var
// pair (ORACLE_CHATGPT_TARGET_ID / ORACLE_CHATGPT_URL_MATCH) is the same one
// honored by toggle-deep-research.mjs, so helper-side targeting is uniform.
//
// Exit codes:
//   0 — Image mode is on (either toggled by us or already selected).
//   2 — chatgpt.com tab not found.
//   3 — composer tool menu ("+") not found.
//   4 — "Create image" menu item not found.
//   5 — CDP connection failed.
//   6 — verification failed (click dispatched but indicator says off).
//   7 — multiple matching chatgpt.com tabs found; submit tab is ambiguous.
//   8 — requested ChatGPT target selector matched no tab.

import { argv, exit, env } from 'node:process';

const HOST = env.ORACLE_CDP_HOST ?? '127.0.0.1';
const PORT = parseInt(env.ORACLE_CDP_PORT ?? '9222', 10);
const TARGET_ID = env.ORACLE_CHATGPT_TARGET_ID ?? '';
const URL_MATCH =
  env.ORACLE_CHATGPT_URL_MATCH ?? env.CHATGPT_IMAGE_URL_MATCH ?? '';
const VERBOSE = argv.includes('--verbose') || env.CHATGPT_IMAGE_VERBOSE === '1';

const log = (...args) => {
  if (VERBOSE) console.error('[toggle-chatgpt-image]', ...args);
};

async function fetchTargets() {
  const res = await fetch(`http://${HOST}:${PORT}/json`);
  if (!res.ok) {
    throw new Error(`CDP /json returned ${res.status}`);
  }
  return res.json();
}

function chatGPTTargets(targets) {
  return targets.filter(
    (t) => t.type === 'page' && /chatgpt\.com/.test(t.url ?? ''),
  );
}

function describeTarget(target) {
  return `${target.id} ${target.url} ${target.title ?? ''}`.trim();
}

function selectChatGPTTarget(targets) {
  const tabs = chatGPTTargets(targets);
  if (tabs.length === 0) {
    return { status: 'none', candidates: [] };
  }

  if (TARGET_ID) {
    const matches = tabs.filter((t) => t.id === TARGET_ID);
    if (matches.length === 1) {
      return { status: 'selected', tab: matches[0], candidates: matches };
    }
    return { status: 'selector-missing', candidates: tabs };
  }

  const candidates = URL_MATCH
    ? tabs.filter((t) => (t.url ?? '').includes(URL_MATCH))
    : tabs;

  if (candidates.length === 0) {
    return { status: URL_MATCH ? 'selector-missing' : 'none', candidates: tabs };
  }
  if (candidates.length === 1) {
    return { status: 'selected', tab: candidates[0], candidates };
  }
  return { status: 'ambiguous', candidates };
}

async function cdpEval(wsUrl, expression) {
  const WebSocketClient =
    globalThis.WebSocket ?? (await import('ws')).default;
  return new Promise((resolve, reject) => {
    const ws = new WebSocketClient(wsUrl);
    const messageId = 1;
    const timer = setTimeout(() => {
      ws.close();
      reject(new Error('CDP eval timed out'));
    }, 15000);

    const onOpen = () => {
      ws.send(
        JSON.stringify({
          id: messageId,
          method: 'Runtime.evaluate',
          params: {
            expression,
            awaitPromise: true,
            returnByValue: true,
          },
        }),
      );
    };

    const onMessage = (raw) => {
      const data = raw?.data ?? raw;
      const msg = JSON.parse(
        typeof data === 'string' ? data : Buffer.from(data).toString(),
      );
      if (msg.id === messageId) {
        clearTimeout(timer);
        ws.close();
        if (msg.error) return reject(new Error(msg.error.message));
        resolve(msg.result?.result?.value);
      }
    };

    const onError = (err) => {
      clearTimeout(timer);
      reject(err?.error ?? err);
    };

    if (typeof ws.addEventListener === 'function') {
      ws.addEventListener('open', onOpen);
      ws.addEventListener('message', onMessage);
      ws.addEventListener('error', onError);
    } else {
      ws.on('open', onOpen);
      ws.on('message', onMessage);
      ws.on('error', onError);
    }
  });
}

// Runs inside the ChatGPT page. Returns one of:
//   { status: 'already-on' | 'turned-on' | 'tool-button-missing' | 'menu-missing' | 'option-missing' | 'verification-failed', detail? }
function pageScript() {
  return `(async () => {
    const normalize = (s) =>
      (s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();

    // Labels ChatGPT has used for the image tool — match any of them.
    const IMAGE_LABELS = ['create image', 'image', 'create an image', 'generate image'];
    const matchesImage = (text) => {
      const n = normalize(text);
      // 'image' alone is ambiguous; only accept it on a menu item, not on the composer pill.
      return IMAGE_LABELS.some((label) => n.includes(label));
    };

    const dispatchClick = (el) => {
      if (!el) return;
      el.scrollIntoView({ block: 'center', inline: 'center' });
      const rect = el.getBoundingClientRect();
      const x = rect.left + rect.width / 2;
      const y = rect.top + rect.height / 2;
      for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
        el.dispatchEvent(
          new PointerEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0 }),
        );
      }
    };

    const composerIsOnImage = () => {
      // When Image mode is enabled, ChatGPT renders a pill/chip in the composer
      // with aria-label, data-testid, or visible text containing "image".
      const selectors = [
        '[aria-label*="create image" i]',
        '[aria-label*="image" i][aria-pressed="true"]',
        '[data-testid*="create-image" i]',
        '[data-testid*="image" i][aria-pressed="true"]',
        'button[aria-pressed="true"]',
      ];
      for (const sel of selectors) {
        for (const node of document.querySelectorAll(sel)) {
          const label = normalize(
            (node.getAttribute('aria-label') || '') + ' ' + (node.textContent || ''),
          );
          // Only trust specific phrasings on the active composer chip.
          if (label.includes('create image') || label.includes('generate image')) return true;
        }
      }
      // Also check the composer chip row.
      const chips = document.querySelectorAll('[data-testid*="composer"] [role="button"], [data-testid*="composer"] button');
      for (const chip of chips) {
        const n = normalize(chip.textContent);
        if (n.includes('create image') || n.includes('generate image') || n === 'image') return true;
      }
      return false;
    };

    if (composerIsOnImage()) {
      return { status: 'already-on' };
    }

    // Find the composer "+" / tools button.
    const toolButtonSelectors = [
      '[data-testid="composer-plus-btn"]',
      '[data-testid*="tools" i] button',
      'button[aria-label*="tools" i]',
      'button[aria-label*="add" i][aria-haspopup]',
      'button[aria-haspopup="menu"][aria-label*="attach" i]',
    ];
    let toolButton = null;
    for (const sel of toolButtonSelectors) {
      const btn = document.querySelector(sel);
      if (btn) {
        toolButton = btn;
        break;
      }
    }
    // Fallback: find any aria-haspopup button in the composer that isn't the thinking pill.
    if (!toolButton) {
      const composer = document.querySelector('[data-testid*="composer"]') || document.querySelector('form');
      if (composer) {
        for (const btn of composer.querySelectorAll('button[aria-haspopup]')) {
          const label = normalize(btn.getAttribute('aria-label') || btn.textContent || '');
          if (label.includes('thinking') || label.includes('pro')) continue;
          toolButton = btn;
          break;
        }
      }
    }
    if (!toolButton) {
      return { status: 'tool-button-missing' };
    }

    dispatchClick(toolButton);

    // Wait for the menu to render with a "Create image" item.
    const waitForMenu = () =>
      new Promise((resolve) => {
        const start = performance.now();
        const tick = () => {
          const menus = document.querySelectorAll(
            '[role="menu"], [data-radix-menu-content], [data-testid*="menu"]',
          );
          for (const menu of menus) {
            const n = normalize(menu.textContent);
            if (n.includes('create image') || n.includes('generate image')) {
              return resolve(menu);
            }
          }
          if (performance.now() - start > 8000) return resolve(null);
          setTimeout(tick, 100);
        };
        tick();
      });

    const menu = await waitForMenu();
    if (!menu) return { status: 'menu-missing' };

    // Find the image menu item.
    let target = null;
    for (const item of menu.querySelectorAll('[role="menuitem"], [role="menuitemcheckbox"], [role="menuitemradio"], button, li')) {
      const text = normalize(item.textContent);
      if (text.includes('create image') || text.includes('generate image')) {
        target = item;
        break;
      }
    }
    // Secondary pass: some builds label it just "Image".
    if (!target) {
      for (const item of menu.querySelectorAll('[role="menuitem"], [role="menuitemcheckbox"], [role="menuitemradio"], button, li')) {
        if (normalize(item.textContent) === 'image') {
          target = item;
          break;
        }
      }
    }
    if (!target) return { status: 'option-missing' };

    dispatchClick(target);

    // Give the composer a moment to re-render the active-tool chip.
    await new Promise((resolve) => setTimeout(resolve, 400));

    if (!composerIsOnImage()) {
      return { status: 'verification-failed' };
    }
    return { status: 'turned-on' };
  })()`;
}

async function main() {
  let targets;
  try {
    targets = await fetchTargets();
  } catch (err) {
    console.error(`Failed to reach Chrome DevTools at ${HOST}:${PORT}:`, err.message);
    exit(5);
  }

  const selection = selectChatGPTTarget(targets);
  if (selection.status === 'none') {
    console.error(`No chatgpt.com tab found on ${HOST}:${PORT}.`);
    exit(2);
  }
  if (selection.status === 'selector-missing') {
    const which = TARGET_ID
      ? `ORACLE_CHATGPT_TARGET_ID=${TARGET_ID}`
      : `ORACLE_CHATGPT_URL_MATCH=${URL_MATCH}`;
    console.error(
      `Selector ${which} matched no chatgpt.com tab on ${HOST}:${PORT}.`,
    );
    console.error('Available chatgpt.com tabs:');
    for (const t of selection.candidates) console.error('  -', describeTarget(t));
    exit(8);
  }
  if (selection.status === 'ambiguous') {
    console.error(
      `Multiple chatgpt.com tabs on ${HOST}:${PORT}; refusing to pick one.`,
    );
    console.error('Set ORACLE_CHATGPT_TARGET_ID or ORACLE_CHATGPT_URL_MATCH to disambiguate.');
    console.error('Candidates:');
    for (const t of selection.candidates) console.error('  -', describeTarget(t));
    exit(7);
  }
  const tab = selection.tab;
  log('selected tab', describeTarget(tab));

  let result;
  try {
    result = await cdpEval(tab.webSocketDebuggerUrl, pageScript());
  } catch (err) {
    console.error('CDP eval failed:', err.message);
    exit(5);
  }

  log('result', result);

  switch (result?.status) {
    case 'already-on':
      console.log('Create image: already on');
      exit(0);
    case 'turned-on':
      console.log('Create image: turned on');
      exit(0);
    case 'tool-button-missing':
      console.error('Create image: composer tool button not found');
      exit(3);
    case 'menu-missing':
      console.error('Create image: composer tool menu did not render');
      exit(3);
    case 'option-missing':
      console.error('Create image: menu item not found (ChatGPT UI may have changed)');
      exit(4);
    case 'verification-failed':
      console.error('Create image: click dispatched but composer did not pick it up');
      exit(6);
    default:
      console.error('Create image: unknown outcome', result);
      exit(6);
  }
}

main();
