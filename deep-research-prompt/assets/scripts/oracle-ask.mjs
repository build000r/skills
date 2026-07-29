#!/usr/bin/env node
/**
 * oracle-ask.mjs — the one command. Prompt in, answer out.
 *
 *   node oracle-ask.mjs "Why is my p99 latency bimodal?"
 *
 * That is the whole contract for the common case: GPT-5 Pro, sensible timeout,
 * answer text on stdout, progress on stderr, non-zero exit with an actionable
 * remediation line when the lane is not ready.
 *
 * There is no SKILL_DIR resolution loop, no overlay-config `eval` precondition,
 * no launcher invocation, no `oracle --render` bundle step, and no DOM composer
 * choreography. Those remain the documented FALLBACK for the things this lane
 * genuinely cannot do (file attachments, Deep Research review cards).
 *
 * TRANSPORT
 *   Delegates to ./oracle-http-client.mjs, which submits to the ChatGPT backend
 *   over plain HTTPS with zero CSS selectors. The operator's already-signed-in
 *   Chrome is used only to broker credentials and mint one anti-abuse token per
 *   question over loopback CDP. Contract: ../../references/chatgpt-backend-api.md
 *
 * FAIL-CLOSED
 *   Every failure prints what broke and exactly what to do about it, then exits
 *   non-zero. This command never silently downgrades to a weaker model, never
 *   silently falls back to the DOM path, and never claims an answer it does not
 *   have.
 *
 * ENV
 *   ORACLE_CDP_PORT               loopback CDP port (default 9222)
 *   ORACLE_ASK_MODEL              default model slug/alias (default `pro`)
 *   ORACLE_ASK_TIMEOUT_SECONDS    answer deadline (default 900)
 *   ORACLE_PROFILE_DIRECTORY      Chrome subprofile for the launcher hint
 *   ORACLE_CHATGPT_PROJECT_URL    target URL for the launcher hint
 *   ORACLE_ASK_BIN_DIR            install destination (default ~/.local/bin)
 */

import { mkdir, readFile, symlink, unlink, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

import {
  ORIGIN,
  OracleHttpError,
  askOracle,
  connectCdp,
  harvestCredentials,
  listModels,
} from "./oracle-http-client.mjs";

export const DEFAULT_PORT = 9222;
export const DEFAULT_TIMEOUT_SECONDS = 900;
export const INSTALL_NAME = "oracle-ask";

/**
 * Friendly names for the slugs a caller actually wants. Anything unrecognised
 * is passed through verbatim so a new slug never needs a code change here.
 * Catalogue: references/chatgpt-backend-api.md §3.
 */
export const MODEL_ALIASES = Object.freeze({
  pro: "gpt-5-6-pro",
  "gpt-5-pro": "gpt-5-6-pro",
  thinking: "gpt-5-6-thinking",
  instant: "gpt-5-5-instant",
  research: "research",
  "deep-research": "research",
});

export const DEFAULT_MODEL_ALIAS = "pro";

/** Slugs whose behaviour on this lane has never been exercised live. */
export const UNPROVEN_SLUGS = Object.freeze(["research"]);

export function resolveModel(value) {
  const raw = (value ?? "").trim();
  if (!raw) return MODEL_ALIASES[DEFAULT_MODEL_ALIAS];
  return MODEL_ALIASES[raw.toLowerCase()] ?? raw;
}

/* ------------------------------------------------------------------ *
 * Argument parsing (pure)
 * ------------------------------------------------------------------ */

export class UsageError extends Error {
  constructor(message) {
    super(message);
    this.name = "UsageError";
  }
}

const NEEDS_VALUE = new Set([
  "--model",
  "--timeout",
  "--port",
  "--prompt-file",
  "--out",
  "--project",
  "--conversation",
]);

/** Remembers the last thread so `--continue` needs no id. */
export const LAST_THREAD_PATH = join(
  homedir(),
  ".oracle",
  "oracle-subagent",
  "last-conversation.json",
);

/**
 * Positional words are the prompt. `--` ends option parsing so a prompt may
 * begin with a dash. Prompt text is never required to be quoted-as-one-arg.
 */
export function parseArgs(argv, env = {}) {
  const out = {
    model: env.ORACLE_ASK_MODEL || DEFAULT_MODEL_ALIAS,
    timeoutSeconds: Number(env.ORACLE_ASK_TIMEOUT_SECONDS || DEFAULT_TIMEOUT_SECONDS),
    port: Number(env.ORACLE_CDP_PORT || DEFAULT_PORT),
    // Answers file into this ChatGPT Project. Accepts a full project URL or a
    // bare g-p-… id. Without it the answer lands in root chat.
    project: env.ORACLE_CHATGPT_PROJECT_URL || null,
    // Every ask opens a new thread unless continuation is asked for.
    continueLast: false,
    conversationId: null,
    json: false,
    quiet: false,
    words: [],
  };
  let literal = false;
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (literal || !arg.startsWith("--")) {
      out.words.push(arg);
      continue;
    }
    if (arg === "--") {
      literal = true;
      continue;
    }
    if (NEEDS_VALUE.has(arg)) {
      const value = argv[i + 1];
      if (value === undefined) throw new UsageError(`${arg} needs a value`);
      i += 1;
      if (arg === "--model") out.model = value;
      else if (arg === "--timeout") out.timeoutSeconds = Number(value);
      else if (arg === "--port") out.port = Number(value);
      else if (arg === "--prompt-file") out.promptFile = value;
      else if (arg === "--out") out.out = value;
      else if (arg === "--project") out.project = value;
      else if (arg === "--conversation") out.conversationId = value;
      continue;
    }
    switch (arg) {
      case "--continue":
      case "--resume":
        out.continueLast = true;
        break;
      case "--new":
        // Explicit form of the default; useful to override a shell alias.
        out.continueLast = false;
        out.conversationId = null;
        break;
      case "--json":
        out.json = true;
        break;
      case "--quiet":
        out.quiet = true;
        break;
      case "--models":
        out.models = true;
        break;
      case "--doctor":
        out.doctor = true;
        break;
      case "--install":
        out.install = true;
        break;
      case "--help":
      case "-h":
        out.help = true;
        break;
      default:
        // An unknown flag is a typo, not prompt text. Failing here is cheaper
        // than silently asking the oracle a question containing "--modle".
        throw new UsageError(`unknown option ${arg}`);
    }
  }
  if (!Number.isFinite(out.timeoutSeconds) || out.timeoutSeconds <= 0) {
    throw new UsageError("--timeout must be a positive number of seconds");
  }
  if (!Number.isFinite(out.port) || out.port <= 0) {
    throw new UsageError("--port must be a positive number");
  }
  out.prompt = out.words.join(" ").trim();
  return out;
}

/**
 * Resolve the prompt from, in order: positional words, --prompt-file, stdin.
 * Exactly one source may supply it; two is an ambiguity worth failing on.
 */
export async function resolvePrompt(args, { readFileImpl = readFile, readStdin } = {}) {
  if (args.prompt && args.promptFile) {
    throw new UsageError("pass the prompt as text or with --prompt-file, not both");
  }
  if (args.prompt) return args.prompt;
  if (args.promptFile) {
    let text;
    try {
      text = await readFileImpl(args.promptFile, "utf8");
    } catch (cause) {
      throw new UsageError(`cannot read --prompt-file ${args.promptFile}: ${cause?.code ?? cause?.message}`);
    }
    const trimmed = text.trim();
    if (!trimmed) throw new UsageError(`--prompt-file ${args.promptFile} is empty`);
    return trimmed;
  }
  if (readStdin) {
    const text = (await readStdin()).trim();
    if (text) return text;
  }
  throw new UsageError("no prompt: pass it as an argument, with --prompt-file, or on stdin");
}

/* ------------------------------------------------------------------ *
 * Remediation — every failure code maps to one concrete next action
 * ------------------------------------------------------------------ */

export const EXIT = Object.freeze({
  ok: 0,
  failed: 1,
  usage: 2,
  notReady: 3,
  refused: 4,
  timeout: 5,
});

const LAUNCH_HINT = (env = process.env) => {
  const profile = env.ORACLE_PROFILE_DIRECTORY;
  const url = env.ORACLE_CHATGPT_PROJECT_URL;
  const lines = [];
  if (profile) lines.push(`ORACLE_PROFILE_DIRECTORY=${JSON.stringify(profile)} \\`);
  else lines.push('ORACLE_PROFILE_DIRECTORY="<subprofile holding the signed-in session>" \\');
  if (url) lines.push(`ORACLE_CHATGPT_PROJECT_URL=${JSON.stringify(url)} \\`);
  else lines.push('ORACLE_CHATGPT_PROJECT_URL="<project or conversation URL>" \\');
  lines.push(`${join(dirname(fileURLToPath(import.meta.url)), "launch-chatgpt-cdp.sh")}`);
  return lines.join("\n    ");
};

/**
 * Map an OracleHttpError code to (exit code, human remediation).
 * Pure apart from the launcher-path/env hint, which is injected for tests.
 */
export function diagnose(code, { env = process.env, launchHint = LAUNCH_HINT } = {}) {
  const launch = () => `Start the signed-in CDP Chrome, then re-run:\n\n    ${launchHint(env)}\n`;
  switch (code) {
    case "cdp_unreachable":
    case "cdp_no_chatgpt_target":
    case "cdp_failed":
      return {
        exit: EXIT.notReady,
        summary: "no signed-in ChatGPT browser on the loopback CDP port",
        action: launch(),
      };
    case "session_unavailable":
    case "cookies_unavailable":
      return {
        exit: EXIT.notReady,
        summary: "the CDP browser is running but is not signed in to ChatGPT",
        action:
          "Open chatgpt.com in that Chrome window and sign in, then re-run.\n" +
          "Check which profile is actually enrolled before relaunching.\n",
      };
    case "auth_expired":
      return {
        exit: EXIT.refused,
        summary: "ChatGPT rejected the session token",
        action:
          "Reload chatgpt.com in the CDP browser to re-mint the session, then re-run.\n" +
          "For a remote box, refresh the portable credential:\n" +
          "    node oracle-credential.mjs refresh && node oracle-credential.mjs doctor\n",
      };
    case "sentinel_rejected":
    case "sentinel_missing":
    case "mint_timeout":
    case "mint_trigger_failed":
    case "harvest_busy":
      return {
        exit: EXIT.refused,
        summary: "the anti-abuse gate refused this submission",
        action:
          "Bring the CDP ChatGPT tab to a normal conversation view (not a modal,\n" +
          "not a logged-out page), wait a few seconds, and re-run. If it persists,\n" +
          "use the DOM fallback lane documented in\n" +
          "references/deep-research-tool-toggle.md -> Verified composer flow.\n",
      };
    case "answer_timeout":
      return {
        exit: EXIT.timeout,
        summary: "the model did not finish inside the deadline",
        action:
          "The turn may still be running in the conversation. Re-run with a longer\n" +
          "deadline, e.g. --timeout 3600, or read the conversation directly.\n",
      };
    case "stream_error":
    case "conversation_post_failed":
    case "conversation_read_failed":
    case "models_failed":
      return {
        exit: EXIT.failed,
        summary: "ChatGPT returned an error for this turn",
        action: "Retry once. If it repeats, use the DOM fallback lane.\n",
      };
    default:
      return {
        exit: EXIT.failed,
        summary: "the ask failed",
        action: "Re-run with --doctor to see which precondition is missing.\n",
      };
  }
}

/* ------------------------------------------------------------------ *
 * Readiness
 * ------------------------------------------------------------------ */

/**
 * Prove the lane can answer before spending a submission: CDP reachable,
 * a chatgpt.com page target present, and the session resolving to a real
 * (non-guest) plan. The guest downgrade is an HTTP 200, so it is checked
 * explicitly — see references/chatgpt-backend-api.md §7.
 */
export async function checkReady({ port = DEFAULT_PORT, connect = connectCdp, harvest = harvestCredentials } = {}) {
  let cdp;
  try {
    cdp = await connect(port);
  } catch (error) {
    return { ready: false, code: error?.code ?? "cdp_unreachable", detail: error?.detail ?? error?.message ?? null };
  }
  try {
    const creds = await harvest(cdp);
    const planType = creds?.planType ?? null;
    if (!planType || planType === "guest") {
      return { ready: false, code: "session_unavailable", detail: `plan_type=${planType ?? "none"}`, target: cdp.url };
    }
    return { ready: true, planType, target: cdp.url, port };
  } catch (error) {
    return { ready: false, code: error?.code ?? "session_unavailable", detail: error?.detail ?? error?.message ?? null };
  } finally {
    cdp?.close?.();
  }
}

/* ------------------------------------------------------------------ *
 * Install (optional): make the one command literally one word
 * ------------------------------------------------------------------ */

export function installTargetPath(env = process.env) {
  const dir = env.ORACLE_ASK_BIN_DIR || join(env.HOME || homedir(), ".local", "bin");
  return join(dir, INSTALL_NAME);
}

export async function install({ env = process.env, scriptPath, fs = { mkdir, symlink, unlink, writeFile } } = {}) {
  const target = installTargetPath(env);
  const source = scriptPath ?? fileURLToPath(import.meta.url);
  await fs.mkdir(dirname(target), { recursive: true });
  await fs.unlink(target).catch(() => {});
  // A shim, not a symlink: the script imports a sibling module by relative
  // path, and a symlinked entrypoint resolves imports from the real path
  // anyway — but a shim also survives the skill dir being re-linked.
  await fs.writeFile(target, `#!/bin/sh\nexec node ${JSON.stringify(resolve(source))} "$@"\n`, { mode: 0o755 });
  return { target, source: resolve(source) };
}

/* ------------------------------------------------------------------ *
 * CLI
 * ------------------------------------------------------------------ */

export const USAGE = `oracle-ask — ask GPT-5 Pro one question; get the answer on stdout.

  oracle-ask "why is my p99 latency bimodal?"
  oracle-ask --prompt-file /tmp/question.md --out /tmp/answer.md
  cat question.md | oracle-ask

Options
  --model <slug|alias>   pro (default) | thinking | instant | research | raw slug
  --timeout <seconds>    answer deadline (default ${DEFAULT_TIMEOUT_SECONDS})
  --port <n>             loopback CDP port (default ${DEFAULT_PORT})
  --project <url|g-p-id> file the answer into a ChatGPT Project
                         (default \$ORACLE_CHATGPT_PROJECT_URL; else root chat)
  --continue             continue the last thread (default: start a new one)
  --conversation <id>    continue this specific thread
  --new                  explicit form of the default
  --prompt-file <path>   read the prompt from a file instead of argv
  --out <path>           also write the answer text to a file
  --json                 emit the full result object instead of bare text
  --quiet                suppress progress lines on stderr
  --doctor               check readiness only; submit nothing
  --models               list the model slugs this account can select
  --install              write a PATH shim so the command is just \`oracle-ask\`

Requires a signed-in Chrome exposing loopback CDP. Attachments and Deep
Research review cards are NOT on this lane — use the DOM fallback documented in
references/deep-research-tool-toggle.md for those.
`;

function readStdinText() {
  return new Promise((resolveText) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      data += chunk;
    });
    process.stdin.on("end", () => resolveText(data));
    process.stdin.on("error", () => resolveText(""));
  });
}

function reportFailure(code, detail) {
  const { exit, summary, action } = diagnose(code);
  process.stderr.write(`\noracle-ask: ${summary} [${code}]\n`);
  if (detail) process.stderr.write(`  detail: ${detail}\n`);
  process.stderr.write(`\n${action}\nNothing was submitted for this attempt.\n`);
  return exit;
}

async function main(argv) {
  let args;
  try {
    args = parseArgs(argv, process.env);
  } catch (error) {
    process.stderr.write(`oracle-ask: ${error.message}\n\n${USAGE}`);
    return EXIT.usage;
  }
  if (args.help) {
    process.stdout.write(USAGE);
    return EXIT.ok;
  }
  if (args.install) {
    const { target, source } = await install();
    process.stdout.write(`installed ${target} -> ${source}\n`);
    process.stderr.write(`Ensure ${dirname(target)} is on PATH, then run: ${INSTALL_NAME} "your question"\n`);
    return EXIT.ok;
  }

  if (args.doctor) {
    const status = await checkReady({ port: args.port });
    if (!status.ready) {
      process.stdout.write(JSON.stringify({ ready: false, code: status.code, detail: status.detail }, null, 2) + "\n");
      return reportFailure(status.code, status.detail);
    }
    process.stdout.write(
      JSON.stringify({ ready: true, plan_type: status.planType, port: status.port, target: status.target }, null, 2) +
        "\n",
    );
    return EXIT.ok;
  }

  if (args.models) {
    const cdp = await connectCdp(args.port);
    try {
      const creds = await harvestCredentials(cdp);
      const models = await listModels(creds);
      process.stdout.write(JSON.stringify({ plan_type: creds.planType, models }, null, 2) + "\n");
    } finally {
      cdp.close();
    }
    return EXIT.ok;
  }

  let prompt;
  try {
    prompt = await resolvePrompt(args, { readStdin: process.stdin.isTTY ? null : readStdinText });
  } catch (error) {
    process.stderr.write(`oracle-ask: ${error.message}\n\n${USAGE}`);
    return EXIT.usage;
  }

  const model = resolveModel(args.model);
  const log = args.quiet ? () => {} : (line) => process.stderr.write(`oracle-ask: ${line}\n`);
  if (UNPROVEN_SLUGS.includes(model)) {
    process.stderr.write(
      `oracle-ask: warning — the '${model}' slug has never been exercised on this lane; ` +
        `if it misbehaves use the DOM fallback.\n`,
    );
  }

  // Fresh thread unless continuation was requested. An explicit id wins over
  // --continue; --continue with no remembered thread is an error rather than a
  // silent new chat, so "continue" never quietly means "start over".
  let conversationId = args.conversationId;
  if (!conversationId && args.continueLast) {
    try {
      const raw = JSON.parse(await readFile(LAST_THREAD_PATH, "utf8"));
      conversationId = typeof raw?.conversation_id === "string" ? raw.conversation_id : null;
    } catch {
      conversationId = null;
    }
    if (!conversationId) {
      throw new UsageError(
        "--continue: no remembered thread yet; ask once without it, or pass --conversation <id>",
      );
    }
  }

  log(`asking ${model} (${prompt.length} chars, deadline ${args.timeoutSeconds}s)`);
  const result = await askOracle({
    prompt,
    model,
    conversationId,
    port: args.port,
    timeoutMs: args.timeoutSeconds * 1000,
    project: args.project,
    onProgress: (p) => {
      if (p.phase === "credentials") log(`session ok (plan ${p.planType ?? "unknown"})`);
      else if (p.phase === "sentinel") log("submission token minted");
      else if (p.phase === "target") log(`${p.thread} thread in ${p.project}`);
      else if (p.phase === "stream") log(p.handoff ? "handed off; waiting for the answer" : "streaming");
      else if (p.phase === "poll")
        log(
          `${p.generating ? "still generating" : "waiting for the answer"} (${Math.round(p.elapsedMs / 1000)}s)`,
        );
    },
  });

  // Remember the thread so --continue works next time. Best effort: failing to
  // record it must not lose an answer we already have.
  if (result.conversationId) {
    try {
      await mkdir(dirname(LAST_THREAD_PATH), { recursive: true, mode: 0o700 });
      await writeFile(
        LAST_THREAD_PATH,
        `${JSON.stringify({ conversation_id: result.conversationId, model, at: new Date().toISOString() })}\n`,
        { encoding: "utf8", mode: 0o600 },
      );
    } catch {
      log("note: could not record this thread for --continue");
    }
  }

  if (args.out) await writeFile(args.out, `${result.text}\n`, "utf8");
  process.stdout.write(args.json ? JSON.stringify(result, null, 2) + "\n" : `${result.text}\n`);
  log(`answered in ${(result.elapsedMs / 1000).toFixed(1)}s via ${result.source}`);
  if (args.out) log(`written to ${args.out}`);

  // Last line, so the follow-up is the thing left on screen. Named exactly as
  // invoked (sbp oracle / oracle-ask / node …) so it pastes without editing.
  // --json callers already have conversationId in the payload.
  if (!args.json && result.conversationId) {
    const as = process.env.ORACLE_ASK_INVOKED_AS || "oracle-ask";
    const model = args.model === DEFAULT_MODEL_ALIAS ? "" : ` --model ${args.model}`;
    process.stderr.write(
      `\ncontinue this thread:\n  ${as} --continue${model} "your follow-up"\n` +
        `  ${as} --conversation ${result.conversationId}${model} "your follow-up"\n`,
    );
  }
  return EXIT.ok;
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  main(process.argv.slice(2))
    .then((code) => {
      process.exitCode = code;
    })
    .catch((error) => {
      if (error instanceof OracleHttpError) {
        process.exitCode = reportFailure(error.code, error.detail);
        return;
      }
      // Usage problems raised after arg parsing (e.g. --continue with no
      // remembered thread) are still usage, not an internal failure.
      if (error instanceof UsageError) {
        process.stderr.write(`oracle-ask: ${error.message}\n`);
        process.exitCode = EXIT.usage;
        return;
      }
      process.stderr.write(`oracle-ask: unexpected error: ${error?.message ?? error}\n`);
      process.exitCode = EXIT.failed;
    });
}
