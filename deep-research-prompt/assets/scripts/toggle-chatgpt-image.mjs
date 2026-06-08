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
const CDP_COMMAND_TIMEOUT_MS = Number.parseInt(
  env.CHATGPT_IMAGE_CDP_TIMEOUT_MS ?? '45000',
  10,
);

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

async function activateTarget(targetId) {
  const res = await fetch(
    `http://${HOST}:${PORT}/json/activate/${encodeURIComponent(targetId)}`,
  );
  if (!res.ok) {
    throw new Error(`CDP activate returned ${res.status}`);
  }
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

async function cdpCommand(wsUrl, method, params = {}) {
  const WebSocketClient =
    globalThis.WebSocket ?? (await import('ws')).default;
  return new Promise((resolve, reject) => {
    const ws = new WebSocketClient(wsUrl);
    const messageId = 1;
    const timer = setTimeout(() => {
      ws.close();
      reject(new Error('CDP command timed out'));
    }, CDP_COMMAND_TIMEOUT_MS);

    const onOpen = () => {
      ws.send(
        JSON.stringify({
          id: messageId,
          method,
          params,
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
        resolve(msg.result);
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

async function cdpEval(wsUrl, expression) {
  const result = await cdpCommand(wsUrl, 'Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  return result?.result?.value;
}

async function cdpTrustedClick(wsUrl, rect) {
  const x = rect.x + rect.width / 2;
  const y = rect.y + rect.height / 2;
  await cdpCommand(wsUrl, 'Input.dispatchMouseEvent', {
    type: 'mouseMoved',
    x,
    y,
  });
  await cdpCommand(wsUrl, 'Input.dispatchMouseEvent', {
    type: 'mousePressed',
    x,
    y,
    button: 'left',
    buttons: 1,
    clickCount: 1,
  });
  await cdpCommand(wsUrl, 'Input.dispatchMouseEvent', {
    type: 'mouseReleased',
    x,
    y,
    button: 'left',
    buttons: 0,
    clickCount: 1,
  });
}

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

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

    // Find the composer "+" / tools button. Oracle can call the hook while the
    // target tab is still finishing a ChatGPT route/render, so poll briefly
    // instead of treating first-frame absence as a hard UI change.
    const findToolButton = () => {
      const toolButtonSelectors = [
        '[data-testid="composer-plus-btn"]',
        '[data-testid*="tools" i] button',
        'button[aria-label*="tools" i]',
        'button[aria-label*="add" i][aria-haspopup]',
        'button[aria-haspopup="menu"][aria-label*="attach" i]',
      ];
      for (const sel of toolButtonSelectors) {
        const btn = document.querySelector(sel);
        if (btn) return btn;
      }

      // Fallback: find any aria-haspopup button in the composer that isn't the
      // thinking pill.
      const composer = document.querySelector('[data-testid*="composer"]') || document.querySelector('form');
      if (composer) {
        for (const btn of composer.querySelectorAll('button[aria-haspopup]')) {
          const label = normalize(btn.getAttribute('aria-label') || btn.textContent || '');
          if (label.includes('thinking') || label.includes('pro')) continue;
          return btn;
        }
      }
      return null;
    };

    const waitForToolButton = () =>
      new Promise((resolve) => {
        const start = performance.now();
        const tick = () => {
          const btn = findToolButton();
          if (btn) return resolve(btn);
          if (performance.now() - start > 15000) return resolve(null);
          setTimeout(tick, 100);
        };
        tick();
      });

    const toolButton = await waitForToolButton();
    if (!toolButton) {
      return {
        status: 'tool-button-missing',
        detail: {
          url: location.href,
          title: document.title,
          textSample: (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 700),
        },
      };
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
            if (
              n.includes('create image') ||
              n.includes('generate image') ||
              n.split(' ').includes('image')
            ) {
              return resolve(menu);
            }
          }
          if (performance.now() - start > 8000) return resolve(null);
          setTimeout(tick, 100);
        };
        tick();
      });

    const menu = await waitForMenu();
    if (!menu) {
      return {
        status: 'menu-missing',
        detail: {
          url: location.href,
          title: document.title,
          menus: [...document.querySelectorAll('[role="menu"], [data-radix-menu-content], [data-testid*="menu"]')]
            .map((node) => (node.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 300)),
          recentButtons: [...document.querySelectorAll('button')]
            .slice(-20)
            .map((node) => ({
              text: (node.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 160),
              ariaLabel: node.getAttribute('aria-label') || '',
              testid: node.getAttribute('data-testid') || '',
              ariaHaspopup: node.getAttribute('aria-haspopup') || '',
            })),
          bodySample: (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 700),
        },
      };
    }

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

function trustedToolButtonScript() {
  return `(() => {
    const normalize = (s) =>
      (s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
    const rectFor = (node) => {
      const rect = node.getBoundingClientRect();
      return { x: rect.left, y: rect.top, width: rect.width, height: rect.height };
    };
    const composerIsOnImage = () => {
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
          if (label.includes('create image') || label.includes('generate image')) return true;
        }
      }
      const chips = document.querySelectorAll('[data-testid*="composer"] [role="button"], [data-testid*="composer"] button');
      for (const chip of chips) {
        const n = normalize(chip.textContent);
        if (n.includes('create image') || n.includes('generate image') || n === 'image') return true;
      }
      return false;
    };
    if (composerIsOnImage()) return { status: 'already-on' };

    const selectors = [
      '[data-testid="composer-plus-btn"]',
      '[data-testid*="tools" i] button',
      'button[aria-label*="tools" i]',
      'button[aria-label*="add" i][aria-haspopup]',
      'button[aria-haspopup="menu"][aria-label*="attach" i]',
    ];
    for (const sel of selectors) {
      const btn = document.querySelector(sel);
      if (btn) {
        btn.scrollIntoView({ block: 'center', inline: 'center' });
        return { status: 'tool-button', rect: rectFor(btn), selector: sel };
      }
    }
    const composer = document.querySelector('[data-testid*="composer"]') || document.querySelector('form');
    if (composer) {
      for (const btn of composer.querySelectorAll('button[aria-haspopup]')) {
        const label = normalize(btn.getAttribute('aria-label') || btn.textContent || '');
        if (label.includes('thinking') || label.includes('pro')) continue;
        btn.scrollIntoView({ block: 'center', inline: 'center' });
        return { status: 'tool-button', rect: rectFor(btn), selector: 'composer button[aria-haspopup]' };
      }
    }
    return {
      status: 'tool-button-missing',
      detail: {
        url: location.href,
        title: document.title,
        textSample: (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 700),
      },
    };
  })()`;
}

function trustedMenuItemScript() {
  return `(() => {
    const normalize = (s) =>
      (s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
    const rectFor = (node) => {
      const rect = node.getBoundingClientRect();
      return { x: rect.left, y: rect.top, width: rect.width, height: rect.height };
    };
    const menus = [...document.querySelectorAll('[role="menu"], [data-radix-menu-content], [data-testid*="menu"]')];
    for (const menu of menus) {
      const items = menu.querySelectorAll('[role="menuitem"], [role="menuitemcheckbox"], [role="menuitemradio"], button, li');
      for (const item of items) {
        const text = normalize(item.textContent);
        if (text.includes('create image') || text.includes('generate image') || text === 'image') {
          item.scrollIntoView({ block: 'center', inline: 'center' });
          return { status: 'option-found', rect: rectFor(item), text };
        }
      }
    }
    if (menus.length > 0) {
      return {
        status: 'option-missing',
        detail: {
          menus: menus.map((node) => (node.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 300)),
        },
      };
    }
    return {
      status: 'menu-missing',
      detail: {
        recentButtons: [...document.querySelectorAll('button')]
          .slice(-20)
          .map((node) => ({
            text: (node.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 160),
            ariaLabel: node.getAttribute('aria-label') || '',
            testid: node.getAttribute('data-testid') || '',
            ariaHaspopup: node.getAttribute('aria-haspopup') || '',
          })),
        bodySample: (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 700),
      },
    };
  })()`;
}

function verifyImageScript() {
  return `(() => {
    const normalize = (s) =>
      (s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
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
        if (label.includes('create image') || label.includes('generate image')) return true;
      }
    }
    const chips = document.querySelectorAll('[data-testid*="composer"] [role="button"], [data-testid*="composer"] button');
    for (const chip of chips) {
      const n = normalize(chip.textContent);
      if (n.includes('create image') || n.includes('generate image') || n === 'image') return true;
    }
    return false;
  })()`;
}

async function trustedClickFallback(tab) {
  const tool = await cdpEval(tab.webSocketDebuggerUrl, trustedToolButtonScript());
  if (tool?.status === 'already-on') return { status: 'already-on' };
  if (tool?.status !== 'tool-button' || !tool.rect) return tool;

  log('trusted-click tool button', tool.selector, tool.rect);
  await cdpTrustedClick(tab.webSocketDebuggerUrl, tool.rect);

  let menu = null;
  const deadline = Date.now() + 8000;
  while (Date.now() < deadline) {
    menu = await cdpEval(tab.webSocketDebuggerUrl, trustedMenuItemScript());
    if (menu?.status === 'option-found') break;
    await delay(100);
  }
  if (menu?.status !== 'option-found' || !menu.rect) return menu || { status: 'menu-missing' };

  log('trusted-click image menu item', menu.text, menu.rect);
  await cdpTrustedClick(tab.webSocketDebuggerUrl, menu.rect);
  await delay(400);

  if (await cdpEval(tab.webSocketDebuggerUrl, verifyImageScript())) {
    return { status: 'turned-on' };
  }
  return { status: 'verification-failed' };
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
  try {
    await activateTarget(tab.id);
    log('activated tab', tab.id);
  } catch (err) {
    log('target activation failed', err.message);
  }

  let result;
  try {
    result = await cdpEval(tab.webSocketDebuggerUrl, pageScript());
  } catch (err) {
    console.error('CDP eval failed:', err.message);
    exit(5);
  }

  log('result', result);
  if (['menu-missing', 'option-missing', 'verification-failed'].includes(result?.status)) {
    log('trying trusted-click fallback after', result.status);
    try {
      result = await trustedClickFallback(tab);
    } catch (err) {
      console.error('CDP trusted-click fallback failed:', err.message);
      exit(5);
    }
    log('trusted-click result', result);
  }

  switch (result?.status) {
    case 'already-on':
      console.log('Create image: already on');
      exit(0);
    case 'turned-on':
      console.log('Create image: turned on');
      exit(0);
    case 'tool-button-missing':
      console.error(
        'Create image: composer tool button not found',
        result.detail ? JSON.stringify(result.detail) : '',
      );
      exit(3);
    case 'menu-missing':
      console.error(
        'Create image: composer tool menu did not render',
        result.detail ? JSON.stringify(result.detail) : '',
      );
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
