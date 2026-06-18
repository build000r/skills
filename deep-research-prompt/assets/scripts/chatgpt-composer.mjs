#!/usr/bin/env node
// chatgpt-composer.mjs — DOM-verified control of the ChatGPT composer over CDP.
//
// Why this exists: Oracle v0.9.x browser mode cannot be trusted to select the
// Pro model or the Deep research tool. Observed June 2026: its model picker
// fails with "Unable to locate the ChatGPT model selector button",
// `--browser-model-strategy ignore` submits whatever the composer happens to
// have (Instant, no Deep research), and `--pre-submit-hook` fired only after
// the send click. This helper makes every selection a verifiable DOM step so
// the agent proves Pro + Deep research BEFORE sending.
//
// Target selection (same contract as the sibling toggle/await helpers):
//   ORACLE_CDP_HOST (default 127.0.0.1), ORACLE_CDP_PORT (default 9222),
//   ORACLE_CHATGPT_TARGET_ID (exact CDP target id), or
//   ORACLE_CHATGPT_URL_MATCH (substring matching exactly one chatgpt.com tab).
//
// Commands (each prints JSON; exits 1 when result.ok === false):
//   state          — url/title, prompt text, model pills, deep-research flag
//   clear          — empty the composer prompt field
//   open-model     — open the model picker, list its items (diagnostic)
//   select-pro     — open the model picker and click the Pro row
//   verify-ready   — ok only when model pill says Pro AND Deep research is on
//   paste-file <p> — paste a file's contents into the composer
//   paste-text <t> — paste a literal string
//   send           — click the send button
//   start-research — click the Deep Research review card's Start button;
//                    ok with alreadyStarted=true when research already runs
//   verify-started — ok when generation evidence is visible (researching UI,
//                    stop button, or progress card)
//   screenshot [p] — capture the page (default /tmp/chatgpt-composer.png)
import { readFileSync, writeFileSync } from 'node:fs';
import { argv, env, exit, stderr, stdout } from 'node:process';

const HOST = env.ORACLE_CDP_HOST || '127.0.0.1';
const PORT = env.ORACLE_CDP_PORT || '9222';
const TARGET_ID = env.ORACLE_CHATGPT_TARGET_ID || '';
const URL_MATCH = env.ORACLE_CHATGPT_URL_MATCH || env.DEEP_RESEARCH_CHATGPT_URL_MATCH || '';

const command = argv[2] || 'state';
const arg = argv[3] || '';

function usage() {
  stderr.write('chatgpt-composer.mjs <state|clear|open-model|select-pro|verify-ready|paste-file|paste-text|send|start-research|verify-started|screenshot> [arg]\n');
}

async function fetchTargets() {
  const res = await fetch(`http://${HOST}:${PORT}/json`);
  if (!res.ok) throw new Error(`CDP /json returned ${res.status}`);
  return res.json();
}

function selectTarget(targets) {
  const tabs = targets.filter((t) => t.type === 'page' && /chatgpt\.com/.test(t.url || ''));
  if (TARGET_ID) {
    const tab = tabs.find((t) => t.id === TARGET_ID);
    if (!tab) throw new Error(`No ChatGPT tab matched ORACLE_CHATGPT_TARGET_ID=${TARGET_ID}`);
    return tab;
  }
  const candidates = URL_MATCH ? tabs.filter((t) => (t.url || '').includes(URL_MATCH)) : tabs;
  if (candidates.length !== 1) {
    throw new Error(`Expected exactly one ChatGPT tab, found ${candidates.length}: ${candidates.map((t) => `${t.id} ${t.url}`).join(' | ')}`);
  }
  return candidates[0];
}

async function cdpCall(ws, method, params = {}) {
  const id = ++cdpCall.id;
  return new Promise((resolve, reject) => {
    const onMessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id !== id) return;
      ws.removeEventListener('message', onMessage);
      if (msg.error) reject(new Error(JSON.stringify(msg.error)));
      else resolve(msg.result);
    };
    ws.addEventListener('message', onMessage);
    ws.send(JSON.stringify({ id, method, params }));
  });
}
cdpCall.id = 0;

async function evalInPage(ws, cmd, payload = null) {
  const expression = `(${pageScript})(${JSON.stringify(cmd)}, ${JSON.stringify(payload)})`;
  const result = await cdpCall(ws, 'Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  return result.result.value;
}

function pageScript(command, payload) {
  const normalize = (s) => (s || '').toLowerCase().replace(/[^a-z0-9.+]+/g, ' ').trim();
  const textOf = (el) => (el?.innerText || el?.textContent || el?.value || '').replace(/\s+/g, ' ').trim();
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    return rect.width > 1 && rect.height > 1;
  };
  const byArea = (a, b) => {
    const ar = a.getBoundingClientRect();
    const br = b.getBoundingClientRect();
    return (ar.width * ar.height) - (br.width * br.height);
  };

  const click = (el) => {
    if (!el) return false;
    el.scrollIntoView({ block: 'center', inline: 'center' });
    const rect = el.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
      el.dispatchEvent(new PointerEvent(type, {
        bubbles: true,
        cancelable: true,
        clientX: x,
        clientY: y,
        button: 0,
      }));
    }
    return true;
  };

  const promptNode = () => document.querySelector('#prompt-textarea[contenteditable="true"], [contenteditable="true"][role="textbox"]');
  const composer = () => document.querySelector('form') || document.querySelector('[data-testid*="composer"]') || document.body;
  const buttons = () => Array.from(document.querySelectorAll('button,[role="button"],a,[aria-label]'));
  const menus = () => Array.from(document.querySelectorAll('[role="menu"], [data-radix-menu-content], [data-testid*="menu"], [cmdk-list], [role="listbox"]'));
  // The model menu is the one listing Instant / Thinking / Pro / Configure.
  // Filtering on all four avoids the account menu (which also says "Pro")
  // and sidebar entries like "Projects".
  const modelMenus = () => menus().filter((m) => {
    const label = normalize(textOf(m));
    return label.includes('instant') && label.includes('thinking') && label.includes('pro') && label.includes('configure');
  });

  const modelPills = () => {
    const comp = composer();
    return buttons()
      .filter((el) => comp.contains(el))
      .map((el) => ({
        text: textOf(el),
        aria: el.getAttribute('aria-label') || '',
        testid: el.getAttribute('data-testid') || '',
        id: el.id || '',
      }))
      .filter((b) => /instant|thinking|pro|gpt|model|auto|5[.\s]*[0-9]/i.test(`${b.text} ${b.aria} ${b.testid}`));
  };

  const deepResearchOn = () => {
    for (const el of buttons()) {
      const label = normalize(`${textOf(el)} ${el.getAttribute('aria-label') || ''} ${el.getAttribute('data-testid') || ''}`);
      if (label.includes('deep research')) return true;
    }
    return normalize(document.body.innerText || '').includes('deep research');
  };

  const generationSignals = () => {
    const body = document.body.innerText || '';
    const signals = [];
    if (/researching|using direct search|browsing the web|stop generating|sources? found/i.test(body)) signals.push('active-research-text');
    if (document.querySelector('button[aria-label*="Stop" i], [data-testid="stop-button"]')) signals.push('stop-button');
    if (/get a detailed report/i.test(body) && /update/i.test(body)) signals.push('research-card');
    return signals;
  };

  const state = () => ({
    url: location.href,
    title: document.title,
    promptText: textOf(promptNode()),
    modelPills: modelPills(),
    deepResearchOn: deepResearchOn(),
    bodyTail: (document.body.innerText || '').slice(-2000),
    menus: menus().map((m) => textOf(m)).filter(Boolean).slice(0, 20),
  });

  const clearPrompt = async () => {
    const node = promptNode();
    if (!node) return { ok: false, reason: 'prompt-not-found', state: state() };
    node.focus();
    document.execCommand('selectAll', false, null);
    document.execCommand('delete', false, null);
    node.textContent = '';
    node.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'deleteContentBackward', data: null }));
    await sleep(150);
    return { ok: textOf(node) === '', state: state() };
  };

  const openModelMenu = async () => {
    // Close any stray open menu first (an open account menu makes "Pro"
    // matching ambiguous).
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
    await sleep(150);
    const comp = composer();
    let candidates = buttons().filter((el) => comp.contains(el)).filter((el) => {
      const label = normalize(`${textOf(el)} ${el.getAttribute('aria-label') || ''} ${el.getAttribute('data-testid') || ''}`);
      if (!label) return false;
      if (label.includes('instant') || label.includes('thinking') || label === 'pro') return true;
      if (label.includes('model') && !label.includes('profile')) return true;
      return false;
    });
    candidates = candidates.filter((el) => !normalize(el.getAttribute('aria-label') || '').includes('profile'));
    const target = candidates[0];
    if (!target) return { ok: false, reason: 'model-button-not-found', state: state() };
    click(target);
    await sleep(700);
    const roots = modelMenus();
    const itemRoots = roots.length ? roots : menus();
    const items = itemRoots.flatMap((root) => Array.from(root.querySelectorAll('[role="menuitem"], [role="option"], [cmdk-item], button, [role="button"], li, a, *'))).map((el) => ({
      text: textOf(el),
      aria: el.getAttribute('aria-label') || '',
      role: el.getAttribute('role') || '',
      testid: el.getAttribute('data-testid') || '',
    })).filter((x) => /instant|thinking|pro|gpt|5[.\s]*[0-9]|model/i.test(`${x.text} ${x.aria} ${x.testid}`));
    return { ok: true, clicked: textOf(target) || target.getAttribute('aria-label') || target.id, items, state: state() };
  };

  const selectPro = async () => {
    const opened = await openModelMenu();
    if (!opened.ok) return opened;
    await sleep(300);
    const menuRoots = modelMenus();
    const searchRoots = menuRoots.length ? menuRoots : [document.body];
    // Click the smallest visible element whose exact text is "Pro" — that is
    // the row label. The row's trailing sliders icon opens the effort submenu
    // (Standard / Extended) instead of switching the model, and the account
    // menu has its own "Pro" badge; both are excluded by exact-text + area.
    const textCandidates = searchRoots.flatMap((root) => Array.from(root.querySelectorAll('*')))
      .filter((el) => visible(el) && /^pro$/i.test(textOf(el).trim()))
      .sort(byArea);
    let candidates = textCandidates;
    if (candidates.length === 0) {
      candidates = searchRoots.flatMap((root) =>
        Array.from(root.querySelectorAll('[role="menuitem"], [role="option"], [cmdk-item], button, [role="button"], li, a')),
      ).filter((el) => {
        const rawText = textOf(el);
        const testid = el.getAttribute('data-testid') || '';
        const aria = el.getAttribute('aria-label') || '';
        const isModelSwitcherPro = /model-switcher/i.test(testid) && /pro/i.test(testid);
        const isVisiblePro = /^pro$/i.test(rawText.trim()) || /\bpro\b/i.test(aria);
        if (!isModelSwitcherPro && !isVisiblePro) return false;
        if (/\b(profile|account|upgrade|project|projects)\b/i.test(`${rawText} ${aria} ${testid}`)) return false;
        return true;
      });
    }
    const preferred = candidates.find((el) => /^pro$/i.test(textOf(el).trim())) ||
      candidates.find((el) => /model-switcher/i.test(el.getAttribute('data-testid') || '')) ||
      candidates[0];
    if (!preferred) return { ok: false, reason: 'pro-option-not-found', opened, state: state() };
    const selected = textOf(preferred) || preferred.getAttribute('aria-label') || preferred.getAttribute('data-testid') || '';
    click(preferred);
    await sleep(900);
    return { ok: true, selected, state: state() };
  };

  const pasteText = async (text) => {
    const node = promptNode();
    if (!node) return { ok: false, reason: 'prompt-not-found', state: state() };
    node.focus();
    document.execCommand('selectAll', false, null);
    document.execCommand('delete', false, null);
    const data = new DataTransfer();
    data.setData('text/plain', text);
    node.dispatchEvent(new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: data }));
    if (!textOf(node)) {
      node.textContent = text;
      node.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text.slice(0, 1) }));
    }
    await sleep(500);
    const pastedLength = textOf(node).length;
    // ChatGPT may fold a long paste into a "Pasted text" attachment chip, in
    // which case the visible prompt text is shorter than the input; require
    // either substantial visible text or the attachment chip.
    const hasAttachmentChip = /pasted text/i.test(document.body.innerText || '');
    return { ok: pastedLength > 0 || hasAttachmentChip, promptLength: pastedLength, attachmentChip: hasAttachmentChip, state: state() };
  };

  const sendPrompt = async () => {
    const btn = document.querySelector('[data-testid="send-button"], #composer-submit-button, button[aria-label*="Send prompt" i]');
    if (!btn) return { ok: false, reason: 'send-button-not-found', state: state() };
    click(btn);
    await sleep(1200);
    return { ok: true, state: state() };
  };

  const startResearch = async () => {
    // Deep Research inserts a review card (title + plan bullets +
    // Edit/Cancel/Start). The Start button shows a countdown and auto-starts
    // when it expires. Match VISIBLE TEXT only: the mic button's aria-label is
    // "Start dictation" and must never match. Smallest area = the label node.
    const signals = generationSignals();
    if (signals.length) return { ok: true, alreadyStarted: true, signals, state: state() };
    const candidates = Array.from(document.querySelectorAll('*')).filter((el) => {
      const label = textOf(el);
      return /^start\b/i.test(label) && !/dictation/i.test(label) && visible(el);
    }).sort(byArea);
    const btn = candidates[0];
    if (!btn) {
      const after = generationSignals();
      if (after.length) return { ok: true, alreadyStarted: true, signals: after, state: state() };
      return { ok: false, reason: 'start-button-not-found', state: state() };
    }
    const clicked = textOf(btn) || btn.getAttribute('aria-label') || '';
    click(btn);
    await sleep(1500);
    return { ok: true, clicked, signals: generationSignals(), state: state() };
  };

  const verifyReady = () => {
    const st = state();
    const modelText = st.modelPills.map((p) => `${p.text} ${p.aria}`).join(' ');
    return {
      ok: /pro/i.test(modelText) && st.deepResearchOn,
      modelText,
      deepResearchOn: st.deepResearchOn,
      state: st,
    };
  };

  const verifyStarted = () => {
    const signals = generationSignals();
    return { ok: signals.length > 0, signals, state: state() };
  };

  if (command === 'state') return state();
  if (command === 'clear') return clearPrompt();
  if (command === 'open-model') return openModelMenu();
  if (command === 'select-pro') return selectPro();
  if (command === 'paste-text') return pasteText(payload || '');
  if (command === 'send') return sendPrompt();
  if (command === 'start-research') return startResearch();
  if (command === 'verify-ready') return verifyReady();
  if (command === 'verify-started') return verifyStarted();
  return { ok: false, reason: `unknown-command-${command}`, state: state() };
}

async function main() {
  if (argv.includes('--help')) {
    usage();
    exit(0);
  }
  const targets = await fetchTargets();
  const target = selectTarget(targets);
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve) => ws.addEventListener('open', resolve, { once: true }));
  await cdpCall(ws, 'Runtime.enable');

  if (command === 'screenshot') {
    await cdpCall(ws, 'Page.enable');
    const result = await cdpCall(ws, 'Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
    const out = arg || '/tmp/chatgpt-composer.png';
    writeFileSync(out, Buffer.from(result.data, 'base64'));
    stdout.write(`${out}\n`);
    ws.close();
    return;
  }

  let result;
  if (command === 'paste-file') {
    if (!arg) throw new Error('paste-file requires a path');
    result = await evalInPage(ws, 'paste-text', readFileSync(arg, 'utf8'));
  } else {
    result = await evalInPage(ws, command, arg || null);
  }
  stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  ws.close();
  if (result?.ok === false) exit(1);
}

main().catch((err) => {
  stderr.write(`${err.stack || err.message}\n`);
  exit(1);
});
