#!/usr/bin/env node
// Wait for a submitted ChatGPT Deep Research run to finish, then print the
// final assistant/research text. This is a pragmatic CDP watcher for Oracle
// browser runs; ChatGPT DOM changes can still require selector maintenance.
//
// Exit codes:
//   0  - assistant/research output captured
//   2  - no chatgpt.com tab found on the DevTools port
//   5  - CDP connection/eval failed
//   7  - multiple matching chatgpt.com tabs found
//   8  - requested target selector matched no tab
//   9  - timed out before completion/stabilization
//   10 - timed out with no assistant output
//   11 - concrete ChatGPT/browser error text detected
//   12 - failed to write DEEP_RESEARCH_OUTPUT/--output
//   64 - invalid arguments

import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import { argv, env, exit, stderr, stdout } from 'node:process';

const DEFAULT_FIRST_POLL_MS = 30 * 60 * 1000;
const DEFAULT_POLL_INTERVAL_MS = 15 * 60 * 1000;
const DEFAULT_MAX_WAIT_MS = 2 * 60 * 60 * 1000;
const DEFAULT_STABLE_POLLS = 2;

const options = parseArgs(argv.slice(2));

const HOST = env.ORACLE_CDP_HOST ?? '127.0.0.1';
const PORT = parseInt(env.ORACLE_CDP_PORT ?? '9222', 10);
const TARGET_ID = env.ORACLE_CHATGPT_TARGET_ID ?? '';
const URL_MATCH =
  env.ORACLE_CHATGPT_URL_MATCH ?? env.DEEP_RESEARCH_CHATGPT_URL_MATCH ?? '';
const VERBOSE = options.verbose || env.DEEP_RESEARCH_VERBOSE === '1';
const OUTPUT_PATH = options.output ?? env.DEEP_RESEARCH_OUTPUT ?? '';

const FIRST_POLL_MS = options.noInitialDelay
  ? 0
  : durationOption(
      options.firstPoll,
      env.DEEP_RESEARCH_FIRST_POLL ?? env.DEEP_RESEARCH_FIRST_POLL_MS,
      DEFAULT_FIRST_POLL_MS,
    );
const POLL_INTERVAL_MS = durationOption(
  options.pollInterval,
  env.DEEP_RESEARCH_POLL_INTERVAL ?? env.DEEP_RESEARCH_POLL_INTERVAL_MS,
  DEFAULT_POLL_INTERVAL_MS,
);
const MAX_WAIT_MS = durationOption(
  options.maxWait,
  env.DEEP_RESEARCH_MAX_WAIT ?? env.DEEP_RESEARCH_MAX_WAIT_MS,
  DEFAULT_MAX_WAIT_MS,
);
const STABLE_POLLS = parsePositiveInt(
  options.stablePolls ?? env.DEEP_RESEARCH_STABLE_POLLS,
  DEFAULT_STABLE_POLLS,
);

function usage() {
  stderr.write(`await-deep-research.mjs [options]

Wait for a ChatGPT Deep Research conversation to finish over Chrome DevTools.

Options:
  --first-poll DUR       Delay before first poll (default: 30m)
  --poll-interval DUR    Delay between polls (default: 15m)
  --max-wait DUR         Total wait before timeout (default: 2h)
  --stable-polls N       Consecutive unchanged polls required (default: 2)
  --output FILE          Also write captured report to FILE
  --no-initial-delay     Poll immediately (use only if 30m already passed)
  --once                 Inspect once and exit non-zero unless complete
  --verbose              Print extra CDP/selector details
  -h, --help             Show this help

Environment:
  ORACLE_CDP_HOST, ORACLE_CDP_PORT
  ORACLE_CHATGPT_TARGET_ID
  ORACLE_CHATGPT_URL_MATCH or DEEP_RESEARCH_CHATGPT_URL_MATCH
  DEEP_RESEARCH_OUTPUT
  DEEP_RESEARCH_FIRST_POLL, DEEP_RESEARCH_POLL_INTERVAL, DEEP_RESEARCH_MAX_WAIT
  DEEP_RESEARCH_STABLE_POLLS, DEEP_RESEARCH_VERBOSE=1

Durations accept ms, s, m, or h suffixes. Bare numbers are milliseconds.
`);
}

function dieUsage(message) {
  stderr.write(`error: ${message}\n\n`);
  usage();
  exit(64);
}

function parseArgs(args) {
  const parsed = {
    firstPoll: null,
    pollInterval: null,
    maxWait: null,
    stablePolls: null,
    output: null,
    noInitialDelay: false,
    once: false,
    verbose: false,
  };

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    switch (arg) {
      case '--first-poll':
        parsed.firstPoll = args[++i] ?? dieUsage('--first-poll requires a value');
        break;
      case '--poll-interval':
        parsed.pollInterval =
          args[++i] ?? dieUsage('--poll-interval requires a value');
        break;
      case '--max-wait':
        parsed.maxWait = args[++i] ?? dieUsage('--max-wait requires a value');
        break;
      case '--stable-polls':
        parsed.stablePolls =
          args[++i] ?? dieUsage('--stable-polls requires a value');
        break;
      case '--output':
        parsed.output = args[++i] ?? dieUsage('--output requires a value');
        break;
      case '--no-initial-delay':
        parsed.noInitialDelay = true;
        break;
      case '--once':
        parsed.once = true;
        break;
      case '--verbose':
        parsed.verbose = true;
        break;
      case '-h':
      case '--help':
        usage();
        exit(0);
        break;
      default:
        dieUsage(`unknown argument: ${arg}`);
    }
  }
  return parsed;
}

function parsePositiveInt(value, fallback) {
  if (value === undefined || value === null || value === '') return fallback;
  const parsed = Number.parseInt(String(value), 10);
  if (!Number.isFinite(parsed) || parsed < 1) {
    dieUsage(`expected a positive integer, got: ${value}`);
  }
  return parsed;
}

function durationOption(cliValue, envValue, fallback) {
  const value = cliValue ?? envValue;
  if (value === undefined || value === null || value === '') return fallback;
  const parsed = parseDuration(value);
  if (!Number.isFinite(parsed) || parsed < 0) {
    dieUsage(`invalid duration: ${value}`);
  }
  return parsed;
}

function parseDuration(value) {
  const text = String(value).trim().toLowerCase();
  const match = text.match(/^(\d+(?:\.\d+)?)(ms|s|m|h)?$/);
  if (!match) return Number.NaN;
  const amount = Number.parseFloat(match[1]);
  const unit = match[2] ?? 'ms';
  switch (unit) {
    case 'ms':
      return Math.round(amount);
    case 's':
      return Math.round(amount * 1000);
    case 'm':
      return Math.round(amount * 60 * 1000);
    case 'h':
      return Math.round(amount * 60 * 60 * 1000);
    default:
      return Number.NaN;
  }
}

function formatDuration(ms) {
  if (ms % (60 * 60 * 1000) === 0) return `${ms / (60 * 60 * 1000)}h`;
  if (ms % (60 * 1000) === 0) return `${ms / (60 * 1000)}m`;
  if (ms % 1000 === 0) return `${ms / 1000}s`;
  return `${ms}ms`;
}

const log = (...args) => {
  stderr.write(`[await-deep-research] ${args.join(' ')}\n`);
};

const verbose = (...args) => {
  if (VERBOSE) log(...args);
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
    }, 20000);

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

function pageScript() {
  return `(() => {
    const normalize = (s) =>
      (s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();

    const cleanText = (node) => {
      const clone = node.cloneNode(true);
      for (const sel of [
        'script',
        'style',
        'svg',
        'button',
        'textarea',
        '[contenteditable="true"]',
        '[role="button"]',
        '[data-testid*="copy"]',
        '[data-testid*="composer"]',
      ]) {
        for (const nested of clone.querySelectorAll(sel)) nested.remove();
      }
      return (clone.innerText || clone.textContent || '')
        .replace(/[ \\t]+\\n/g, '\\n')
        .replace(/\\n[ \\t]+/g, '\\n')
        .replace(/\\n{3,}/g, '\\n\\n')
        .trim();
    };

    const visibleSnippet = (node) =>
      (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim();

    const errorPhrases = [
      'something went wrong',
      'network error',
      'error generating response',
      'unable to load conversation',
      'conversation not found',
      'message not found',
      'you have reached the limit',
      'limit reached',
      'please try again later',
    ];

    const errorSignals = [];
    const bodyText = normalize(document.body?.innerText || '');
    for (const phrase of errorPhrases) {
      if (bodyText.includes(phrase)) errorSignals.push(phrase);
    }

    const activeSignals = [];
    const activePhrases = [
      'stop generating',
      'stop streaming',
      'researching',
      'searching the web',
      'reading sources',
      'analyzing sources',
      'gathering sources',
      'research in progress',
      'still working',
      'working on it',
    ];
    const activeNodes = document.querySelectorAll(
      'button,[role="status"],[aria-live],[data-testid*="status"],[data-testid*="thinking"],[data-testid*="progress"],[data-testid*="composer"]',
    );
    for (const node of activeNodes) {
      const label = normalize(
        [
          node.getAttribute?.('aria-label') || '',
          node.getAttribute?.('data-testid') || '',
          visibleSnippet(node),
        ].join(' '),
      );
      if (!label || label.length > 500) continue;
      for (const phrase of activePhrases) {
        if (label.includes(phrase)) activeSignals.push(phrase);
      }
    }

    let assistantNodes = Array.from(
      document.querySelectorAll('[data-message-author-role="assistant"]'),
    );

    if (assistantNodes.length === 0) {
      assistantNodes = Array.from(
        document.querySelectorAll('main .markdown, article .markdown, [class*="markdown"]'),
      );
    }

    const assistantTexts = assistantNodes
      .map(cleanText)
      .filter((text) => text.length >= 40);
    const lastAssistantText = assistantTexts.at(-1) || '';
    const headings = lastAssistantText
      .split('\\n')
      .map((line) => line.trim())
      .filter((line) => /^#{1,4}\\s+/.test(line))
      .slice(0, 12);

    let status = 'no-output';
    if (errorSignals.length > 0) {
      status = 'error';
    } else if (activeSignals.length > 0) {
      status = 'active';
    } else if (lastAssistantText) {
      status = 'candidate';
    }

    return {
      status,
      url: location.href,
      title: document.title,
      assistantCount: assistantTexts.length,
      lastAssistantText,
      textLength: lastAssistantText.length,
      headings,
      activeSignals: [...new Set(activeSignals)],
      errorSignals: [...new Set(errorSignals)],
    };
  })()`;
}

async function inspectTarget() {
  let targets;
  try {
    targets = await fetchTargets();
  } catch (err) {
    stderr.write(`Failed to reach Chrome DevTools at ${HOST}:${PORT}: ${err.message}\n`);
    exit(5);
  }

  const selection = selectChatGPTTarget(targets);
  if (selection.status === 'none') {
    stderr.write(`No chatgpt.com tab found on ${HOST}:${PORT}.\n`);
    exit(2);
  }
  if (selection.status === 'selector-missing') {
    const selector = TARGET_ID
      ? `ORACLE_CHATGPT_TARGET_ID=${TARGET_ID}`
      : `ORACLE_CHATGPT_URL_MATCH=${URL_MATCH}`;
    stderr.write(`No chatgpt.com tab on ${HOST}:${PORT} matched ${selector}.\n`);
    for (const target of selection.candidates) {
      stderr.write(`- ${describeTarget(target)}\n`);
    }
    exit(8);
  }
  if (selection.status === 'ambiguous') {
    const scope = URL_MATCH
      ? `matching ORACLE_CHATGPT_URL_MATCH=${URL_MATCH}`
      : 'on the DevTools port';
    stderr.write(
      `Multiple chatgpt.com tabs ${scope}; Deep Research completion target is ambiguous.\n`,
    );
    for (const target of selection.candidates) {
      stderr.write(`- ${describeTarget(target)}\n`);
    }
    stderr.write('Set ORACLE_CHATGPT_TARGET_ID or narrow ORACLE_CHATGPT_URL_MATCH.\n');
    exit(7);
  }

  verbose('target', describeTarget(selection.tab));

  try {
    return await cdpEval(selection.tab.webSocketDebuggerUrl, pageScript());
  } catch (err) {
    stderr.write(`CDP eval failed: ${err.message}\n`);
    exit(5);
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function wait(ms, label) {
  if (ms <= 0) return;
  log(`${label}; sleeping ${formatDuration(ms)}`);
  await sleep(ms);
}

function writeResult(text) {
  const finalText = text.endsWith('\n') ? text : `${text}\n`;
  if (OUTPUT_PATH) {
    try {
      mkdirSync(dirname(OUTPUT_PATH), { recursive: true });
      writeFileSync(OUTPUT_PATH, finalText);
    } catch (err) {
      stderr.write(`Failed to write output ${OUTPUT_PATH}: ${err.message}\n`);
      exit(12);
    }
    log(`wrote output ${OUTPUT_PATH}`);
  }
  stdout.write(finalText);
}

async function main() {
  log(
    `target=${TARGET_ID || URL_MATCH || 'single chatgpt.com tab'} first-poll=${formatDuration(FIRST_POLL_MS)} interval=${formatDuration(POLL_INTERVAL_MS)} max-wait=${formatDuration(MAX_WAIT_MS)} stable-polls=${STABLE_POLLS}`,
  );

  const startedAt = Date.now();
  let previousText = '';
  let stablePolls = 0;
  let sawAssistant = false;

  if (!options.once) {
    await wait(FIRST_POLL_MS, 'waiting before first poll');
  }

  for (;;) {
    const elapsedMs = Date.now() - startedAt;
    const state = await inspectTarget();

    if (state?.status === 'error') {
      stderr.write(
        `ChatGPT/browser error evidence detected: ${state.errorSignals.join(', ')}\n`,
      );
      exit(11);
    }

    if (state?.lastAssistantText) {
      sawAssistant = true;
    }

    if (state?.status === 'candidate') {
      if (state.lastAssistantText === previousText) {
        stablePolls += 1;
      } else {
        previousText = state.lastAssistantText;
        stablePolls = 1;
      }

      log(
        `candidate output length=${state.textLength} assistant-turns=${state.assistantCount} stable-polls=${stablePolls}/${STABLE_POLLS}`,
      );
      if (VERBOSE && state.headings?.length) {
        log(`headings=${state.headings.join(' | ')}`);
      }

      if (stablePolls >= STABLE_POLLS) {
        writeResult(state.lastAssistantText);
        exit(0);
      }
    } else if (state?.status === 'active') {
      stablePolls = 0;
      log(
        `active Deep Research signals: ${(state.activeSignals ?? []).join(', ') || 'unknown active UI'}`,
      );
    } else {
      stablePolls = 0;
      log('no assistant/research output visible yet');
    }

    if (options.once) {
      if (sawAssistant) {
        stderr.write(
          'Assistant output exists, but completion was not confirmed in this single poll.\n',
        );
        exit(9);
      }
      stderr.write('No assistant output visible in this single poll.\n');
      exit(10);
    }

    const nextElapsedMs = Date.now() - startedAt;
    if (nextElapsedMs >= MAX_WAIT_MS) {
      if (!sawAssistant) {
        stderr.write(
          `Timed out after ${formatDuration(nextElapsedMs)} with no assistant output.\n`,
        );
        exit(10);
      }
      stderr.write(
        `Timed out after ${formatDuration(nextElapsedMs)} before output stabilized or active signals cleared.\n`,
      );
      exit(9);
    }

    const remainingMs = MAX_WAIT_MS - nextElapsedMs;
    await wait(Math.min(POLL_INTERVAL_MS, remainingMs), 'waiting before next poll');
  }
}

main();
