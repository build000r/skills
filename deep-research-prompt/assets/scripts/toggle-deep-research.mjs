#!/usr/bin/env node
// Toggle ChatGPT's "Deep research" tool on the currently focused composer.
//
// Connects to a running Chrome via the DevTools Protocol (default
// 127.0.0.1:9222), finds a chatgpt.com tab, opens the composer tool picker
// ("+" button), and clicks the "Deep research" menu item.
//
// Intended flow (see references/deep-research-tool-toggle.md):
//   1. Skill launches Chrome headful with --remote-debugging-port=9222 using
//      the user's logged-in ChatGPT profile.
//   2. Skill opens a new tab to https://chatgpt.com/.
//   3. Skill runs this script to turn Deep research on for the tab.
//   4. Skill runs `oracle --remote-chrome 127.0.0.1:9222 --browser-model-strategy current ...`
//      so Oracle attaches to the same Chrome and uses the already-toggled tab.
//
// Exit codes:
//   0 — Deep research is on (either toggled by us or already selected).
//   2 — chatgpt.com tab not found.
//   3 — composer tool menu ("+") not found.
//   4 — "Deep research" menu item not found.
//   5 — CDP connection failed.
//   6 — verification failed (click dispatched but indicator says off).

import { argv, exit, env } from 'node:process';

const HOST = env.ORACLE_CDP_HOST ?? '127.0.0.1';
const PORT = parseInt(env.ORACLE_CDP_PORT ?? '9222', 10);
const VERBOSE = argv.includes('--verbose') || env.DEEP_RESEARCH_VERBOSE === '1';

const log = (...args) => {
  if (VERBOSE) console.error('[toggle-deep-research]', ...args);
};

async function fetchTargets() {
  const res = await fetch(`http://${HOST}:${PORT}/json`);
  if (!res.ok) {
    throw new Error(`CDP /json returned ${res.status}`);
  }
  return res.json();
}

function pickChatGPTTarget(targets) {
  return targets.find(
    (t) => t.type === 'page' && /chatgpt\.com/.test(t.url ?? ''),
  );
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

    const composerIsOnDeepResearch = () => {
      // When Deep research is enabled, ChatGPT renders a pill/chip in the composer
      // with aria-label, data-testid, or visible text containing "deep research".
      const selectors = [
        '[aria-label*="deep research" i]',
        '[data-testid*="deep-research" i]',
        'button[aria-pressed="true"]',
      ];
      for (const sel of selectors) {
        for (const node of document.querySelectorAll(sel)) {
          const label = normalize(
            (node.getAttribute('aria-label') || '') + ' ' + (node.textContent || ''),
          );
          if (label.includes('deep research')) return true;
        }
      }
      // Also check the composer chip row.
      const chips = document.querySelectorAll('[data-testid*="composer"] [role="button"], [data-testid*="composer"] button');
      for (const chip of chips) {
        if (normalize(chip.textContent).includes('deep research')) return true;
      }
      return false;
    };

    if (composerIsOnDeepResearch()) {
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

    // Wait for the menu to render.
    const waitForMenu = () =>
      new Promise((resolve) => {
        const start = performance.now();
        const tick = () => {
          const menus = document.querySelectorAll(
            '[role="menu"], [data-radix-menu-content], [data-testid*="menu"]',
          );
          for (const menu of menus) {
            if (normalize(menu.textContent).includes('deep research')) {
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

    // Find the Deep research menu item.
    let target = null;
    for (const item of menu.querySelectorAll('[role="menuitem"], [role="menuitemcheckbox"], [role="menuitemradio"], button, li')) {
      const text = normalize(item.textContent);
      if (text.includes('deep research')) {
        target = item;
        break;
      }
    }
    if (!target) return { status: 'option-missing' };

    dispatchClick(target);

    // Give the composer a moment to re-render the active-tool chip.
    await new Promise((resolve) => setTimeout(resolve, 400));

    if (!composerIsOnDeepResearch()) {
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

  const tab = pickChatGPTTarget(targets);
  if (!tab) {
    console.error(`No chatgpt.com tab found on ${HOST}:${PORT}.`);
    exit(2);
  }
  log('found tab', tab.url);

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
      console.log('Deep research: already on');
      exit(0);
    case 'turned-on':
      console.log('Deep research: turned on');
      exit(0);
    case 'tool-button-missing':
      console.error('Deep research: composer tool button not found');
      exit(3);
    case 'menu-missing':
      console.error('Deep research: composer tool menu did not render');
      exit(3);
    case 'option-missing':
      console.error('Deep research: menu item not found (ChatGPT UI may have changed)');
      exit(4);
    case 'verification-failed':
      console.error('Deep research: click dispatched but composer did not pick it up');
      exit(6);
    default:
      console.error('Deep research: unknown outcome', result);
      exit(6);
  }
}

main();
