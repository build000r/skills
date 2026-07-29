#!/usr/bin/env node
// Portable credential lane for the Oracle ChatGPT session.
//
// WHY THIS EXISTS
// The hidden-headful browser lane (launch-chatgpt-cdp.sh + oracle-subagent-auth.mjs)
// deliberately welds authentication to one macOS machine: Keychain-encrypted cookie
// DBs, a `uname -s = Darwin` gate, Gatekeeper/codesign attestation booleans, and a
// profile fingerprint of sha256("<absolute profile path>\0<profile dir>"). That is a
// defensible design for the *browser* lane, and this file does not touch it.
//
// This file adds a SECOND, portable lane beside it. It transports the one artifact
// that is genuinely portable — the NextAuth session cookie — instead of the profile
// directory, which is useless off-Mac.
//
// EMPIRICAL BASIS (measured 2026-07-28, read-only, against the live account):
//   * `__Secure-next-auth.session-token` alone, sent from a plain Node `fetch` with
//     no browser at all, returns HTTP 200 + a real `accessToken` from
//     https://chatgpt.com/api/auth/session. No Cloudflare challenge, no cf_clearance.
//   * A Linux Chrome User-Agent works identically to the macOS one. A non-browser
//     UA (literally "node") gets 403 — so a plausible UA is required, and that is
//     the ONLY machine-shaped requirement.
//   * The session cookie does NOT rotate. `/api/auth/session` sends no Set-Cookie
//     for it, and the original replays fine after many refreshes. This is the
//     opposite of the OpenAI *OAuth* refresh-token behaviour, so copies on several
//     boxes coexist instead of invalidating each other.
//   * `accessToken` is a JWT with a 10-day lifetime (iss auth.openai.com,
//     aud https://api.openai.com/v1) and works as a Bearer against backend-api.
//   * The session envelope carries a ~90-day sliding `expires`, and each response
//     body includes a freshly re-signed `sessionToken` usable as the next cookie
//     WITHOUT invalidating the current one — a browserless roll-forward.
//
// => d3 (portfolio-devbox) and d3c (conference1) can refresh self-sufficiently.
//    See references/oracle-credential-portability.md for the full write-up.
//
// DESIGN RULES HONOURED HERE
//   * Nothing in the stored envelope is path-, host-, or OS-derived. No fingerprint
//     welds it to /Users/b. Copy the file to any box and it works.
//   * 0600 file, 0700 directory, atomic writes, ownership + mode verified on read.
//   * Prefer a refresh-capable COMMAND over a frozen bearer (operator convention:
//     caam.zsh exports `spaps-token-fresh`, not a static token). `print-access-token`
//     auto-refreshes before serving, so a stale token can never shadow a good one —
//     the failure mode that caused an 8-week outage.
//   * Secret-emitting commands refuse a TTY unless forced, so tokens never land in
//     terminal scrollback. Nothing here writes a secret to a log or to the repo.
//
// USAGE
//   oracle-credential.mjs acquire            # from local authenticated browser (CDP)
//   oracle-credential.mjs refresh            # browserless renewal; works on d3/d3c
//   oracle-credential.mjs doctor [--json]    # validity/expiry, never leaks the secret
//   oracle-credential.mjs print-access-token # for $(...) substitution; auto-refreshes
//   oracle-credential.mjs export             # portable envelope on stdout, for transport
//   oracle-credential.mjs import             # read envelope from stdin, store 0600
//   oracle-credential.mjs path               # print the store path
//
// TRANSPORT TO A REMOTE BOX (never through a repo, a log, or an env var):
//   ./oracle-credential.mjs export | ssh d3 'ORACLE_CREDENTIAL_ALLOW_TTY=0 \
//       node ~/bin/oracle-credential.mjs import'
//   ssh d3 'node ~/bin/oracle-credential.mjs doctor'

import { createHash } from "node:crypto";
import { constants as fsConstants } from "node:fs";
import { chmod, mkdir, open, rename, stat, unlink } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

export const CREDENTIAL_SCHEMA = "oracle-subagent.credential.v1";

const ORIGIN = "https://chatgpt.com";
const SESSION_PATH = "/api/auth/session";
const SESSION_COOKIE = "__Secure-next-auth.session-token";

// A plausible browser UA is required: a "node" UA is rejected with 403 by the edge.
// Deliberately NOT derived from the host OS — the stored credential must behave
// identically on macOS and Linux.
const DEFAULT_USER_AGENT =
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36";

// Serve a token only if it has comfortably more than this left; otherwise refresh
// first. Refresh-over-storage: never hand out a nearly-dead bearer.
const ACCESS_TOKEN_MIN_REMAINING_MS = 24 * 60 * 60 * 1000; // 24h
const NETWORK_TIMEOUT_MS = 20_000;

// Env vars that, if set, can shadow this store inside downstream tooling. Reported
// by `doctor` because a stale static token shadowing a refreshable one is a known,
// expensive failure mode.
const SHADOWING_ENV_VARS = [
  "OPENAI_API_KEY",
  "OPENAI_ACCESS_TOKEN",
  "OPENAI_SESSION_TOKEN",
  "CHATGPT_ACCESS_TOKEN",
  "CHATGPT_SESSION_TOKEN",
  "ORACLE_ACCESS_TOKEN",
  "ORACLE_SESSION_TOKEN",
];

class CredentialError extends Error {
  constructor(code, detail) {
    super(detail ? `${code}: ${detail}` : code);
    this.name = "CredentialError";
    this.code = code;
  }
}

/* ------------------------------------------------------------------ helpers */

function sha256Hex(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}

/** Short, non-reversible handle for a secret. Safe to log, print, and commit. */
export function fingerprint(value) {
  if (typeof value !== "string" || value.length === 0) return null;
  return sha256Hex(value).slice(0, 12);
}

/** Mask an email for human-readable output without disclosing the full address. */
export function maskEmail(email) {
  if (typeof email !== "string" || !email.includes("@")) return null;
  const [local, domain] = email.split("@");
  const head = local.slice(0, 2);
  return `${head}${"*".repeat(Math.max(1, local.length - 2))}@${domain}`;
}

function userAgent() {
  return process.env.ORACLE_CREDENTIAL_USER_AGENT || DEFAULT_USER_AGENT;
}

export function storePath() {
  if (process.env.ORACLE_CREDENTIAL_STORE) {
    return process.env.ORACLE_CREDENTIAL_STORE;
  }
  // Intentionally NOT XDG-derived. On conference1 the login shell sets
  // XDG_CONFIG_HOME, which silently relocates credential paths and has already
  // caused one confusing hunt. A fixed ~/.oracle path resolves identically on
  // every box and matches the existing oracle-subagent store convention.
  const home = process.env.ORACLE_HOME_DIR || join(homedir(), ".oracle");
  return join(home, "oracle-subagent", "credential.json");
}

/** Decode a JWT payload without verifying (we only need `exp`/`iat` metadata). */
export function decodeJwtPayload(token) {
  if (typeof token !== "string") return null;
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const json = Buffer.from(
      parts[1].replace(/-/g, "+").replace(/_/g, "/"),
      "base64",
    ).toString("utf8");
    const payload = JSON.parse(json);
    return typeof payload === "object" && payload !== null ? payload : null;
  } catch {
    return null;
  }
}

export function accessTokenExpiry(token) {
  const payload = decodeJwtPayload(token);
  if (!payload || !Number.isFinite(payload.exp)) return null;
  return payload.exp * 1000;
}

function isoOrNull(ms) {
  return Number.isFinite(ms) ? new Date(ms).toISOString() : null;
}

function remainingText(ms) {
  if (!Number.isFinite(ms)) return "unknown";
  const delta = ms - Date.now();
  if (delta <= 0) return "EXPIRED";
  const days = delta / 86_400_000;
  if (days >= 1) return `${days.toFixed(1)}d`;
  return `${(delta / 3_600_000).toFixed(1)}h`;
}

/* -------------------------------------------------------------------- store */

async function ensureStoreDir(file) {
  const dir = dirname(file);
  await mkdir(dir, { recursive: true, mode: 0o700 });
  try {
    await chmod(dir, 0o700);
  } catch {
    /* best effort: a pre-existing dir we do not own will fail the read check */
  }
}

/**
 * Atomic 0600 write. The temp file is created with the final mode so the secret is
 * never briefly world-readable.
 */
async function writePrivateJson(file, value) {
  await ensureStoreDir(file);
  const tmp = `${file}.tmp-${process.pid}`;
  const body = `${JSON.stringify(value, null, 2)}\n`;
  let handle;
  try {
    handle = await open(
      tmp,
      fsConstants.O_WRONLY | fsConstants.O_CREAT | fsConstants.O_EXCL,
      0o600,
    );
    await handle.writeFile(body, "utf8");
    await handle.sync().catch(() => {});
  } finally {
    await handle?.close();
  }
  try {
    await rename(tmp, file);
  } catch (error) {
    await unlink(tmp).catch(() => {});
    throw error;
  }
  await chmod(file, 0o600);
}

async function readStore(file, { optional = false } = {}) {
  let meta;
  try {
    meta = await stat(file);
  } catch (error) {
    if (optional && error?.code === "ENOENT") return null;
    throw new CredentialError(
      "credential_missing",
      `no credential at ${file} — run 'acquire' on the Mac, or 'import' here`,
    );
  }
  if (!meta.isFile()) {
    throw new CredentialError("credential_invalid", "store is not a regular file");
  }
  if (typeof process.getuid === "function" && meta.uid !== process.getuid()) {
    throw new CredentialError("credential_insecure", "store is owned by another user");
  }
  if ((meta.mode & 0o077) !== 0) {
    throw new CredentialError(
      "credential_insecure",
      `store is group/world accessible (mode ${(meta.mode & 0o777).toString(8)}); run: chmod 600 ${file}`,
    );
  }
  let handle;
  let raw;
  try {
    handle = await open(file, "r");
    raw = await handle.readFile("utf8");
  } finally {
    await handle?.close();
  }
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new CredentialError("credential_invalid", "store is not valid JSON");
  }
  if (parsed?.schema !== CREDENTIAL_SCHEMA) {
    throw new CredentialError("credential_invalid", "unexpected credential schema");
  }
  if (typeof parsed.session_token !== "string" || parsed.session_token.length < 32) {
    throw new CredentialError("credential_invalid", "missing session token");
  }
  return parsed;
}

/* ------------------------------------------------------- envelope assembly */

/**
 * Build the portable envelope. Deliberately contains no absolute path, hostname,
 * OS name, profile fingerprint, or any other value that would weld it to one box.
 */
export function buildEnvelope(session, sessionToken, previous = null) {
  const accessExp = accessTokenExpiry(session?.accessToken);
  const now = new Date().toISOString();
  return {
    schema: CREDENTIAL_SCHEMA,
    origin: ORIGIN,
    // Identity hints only — enough to tell two accounts apart, never enough to
    // reconstruct the account or the secret.
    account_email_masked: maskEmail(session?.user?.email),
    account_id_fp: session?.user?.id ? fingerprint(session.user.id) : null,
    auth_provider: session?.authProvider ?? null,
    session_token: sessionToken,
    session_token_fp: fingerprint(sessionToken),
    session_expires: session?.expires ?? null,
    access_token: session?.accessToken ?? null,
    access_token_fp: fingerprint(session?.accessToken),
    access_token_expires: isoOrNull(accessExp),
    acquired_at: previous?.acquired_at ?? now,
    refreshed_at: now,
    refresh_count: (previous?.refresh_count ?? 0) + (previous ? 1 : 0),
  };
}

/* ------------------------------------------------------- network: refresh */

/**
 * Browserless session fetch. This is the whole portability thesis: cookie in,
 * fresh accessToken out, no browser and no macOS anywhere in the path.
 */
export async function fetchSession(sessionToken, { fetchImpl = fetch } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), NETWORK_TIMEOUT_MS);
  let response;
  try {
    response = await fetchImpl(`${ORIGIN}${SESSION_PATH}`, {
      headers: {
        cookie: `${SESSION_COOKIE}=${sessionToken}`,
        "user-agent": userAgent(),
        accept: "*/*",
        "accept-language": "en-US,en;q=0.9",
        referer: `${ORIGIN}/`,
      },
      redirect: "manual",
      signal: controller.signal,
    });
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new CredentialError("refresh_timeout", `no response in ${NETWORK_TIMEOUT_MS}ms`);
    }
    throw new CredentialError("refresh_unreachable", error?.message);
  } finally {
    clearTimeout(timer);
  }

  if (response.status === 403) {
    throw new CredentialError(
      "refresh_forbidden",
      "edge rejected the request (403) — usually a non-browser User-Agent; set ORACLE_CREDENTIAL_USER_AGENT",
    );
  }
  if (response.status !== 200) {
    throw new CredentialError("refresh_failed", `HTTP ${response.status}`);
  }

  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new CredentialError("refresh_failed", "response was not JSON");
  }
  // An expired/revoked session returns 200 with an empty object rather than an error.
  if (!payload || typeof payload !== "object" || !payload.accessToken) {
    throw new CredentialError(
      "session_expired",
      "session token no longer mints an access token — re-acquire from the browser",
    );
  }
  return payload;
}

/* ---------------------------------------------------------- network: CDP */

/** Minimal CDP client over the browser's WebSocket endpoint. */
async function cdpConnect(wsUrl) {
  if (typeof WebSocket !== "function") {
    throw new CredentialError(
      "cdp_unsupported",
      "no global WebSocket — acquire needs Node >= 22 (refresh does not)",
    );
  }
  return await new Promise((resolve, reject) => {
    const socket = new WebSocket(wsUrl);
    const pending = new Map();
    let nextId = 0;
    const failAll = (error) => {
      for (const { reject: rej } of pending.values()) rej(error);
      pending.clear();
    };
    socket.onopen = () =>
      resolve({
        send(method, params = {}) {
          const id = ++nextId;
          socket.send(JSON.stringify({ id, method, params }));
          return new Promise((res, rej) => {
            pending.set(id, { resolve: res, reject: rej });
            setTimeout(() => {
              if (pending.delete(id)) rej(new CredentialError("cdp_timeout", method));
            }, NETWORK_TIMEOUT_MS);
          });
        },
        close: () => socket.close(),
      });
    socket.onerror = () =>
      reject(new CredentialError("cdp_unreachable", "websocket error"));
    socket.onclose = () => failAll(new CredentialError("cdp_closed", "connection closed"));
    socket.onmessage = (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      const entry = message.id != null ? pending.get(message.id) : null;
      if (!entry) return;
      pending.delete(message.id);
      if (message.error) entry.reject(new CredentialError("cdp_error", JSON.stringify(message.error)));
      else entry.resolve(message.result);
    };
  });
}

/**
 * Pull the session cookie from the already-running, already-authenticated browser.
 * Read-only: reads cookies, never navigates, types, clicks, or submits anything.
 */
async function acquireFromBrowser() {
  const host = process.env.ORACLE_CDP_HOST || "127.0.0.1";
  const port = Number(process.env.ORACLE_CDP_PORT || 9222);
  let targets;
  try {
    const response = await fetch(`http://${host}:${port}/json/list`, {
      signal: AbortSignal.timeout(5000),
    });
    targets = await response.json();
  } catch (error) {
    throw new CredentialError(
      "browser_unreachable",
      `no CDP endpoint at ${host}:${port} — start the hidden-headful browser first (${error?.message})`,
    );
  }
  const target = targets.find(
    (item) => item.type === "page" && String(item.url).includes("chatgpt.com"),
  );
  if (!target?.webSocketDebuggerUrl) {
    throw new CredentialError("browser_no_target", "no chatgpt.com page target is open");
  }

  const client = await cdpConnect(target.webSocketDebuggerUrl);
  let cookies;
  try {
    const result = await client.send("Network.getCookies", { urls: [`${ORIGIN}/`] });
    cookies = result?.cookies ?? [];
  } finally {
    client.close();
  }
  const cookie = cookies.find((item) => item.name === SESSION_COOKIE);
  if (!cookie?.value) {
    throw new CredentialError(
      "browser_not_authenticated",
      `no ${SESSION_COOKIE} cookie — log in inside the Oracle browser first`,
    );
  }
  return cookie.value;
}

/* ----------------------------------------------------------------- guards */

/** Refuse to print a secret into terminal scrollback unless explicitly forced. */
function assertSecretSinkAllowed(flags) {
  const forced =
    flags.force || process.env.ORACLE_CREDENTIAL_ALLOW_TTY === "1";
  if (process.stdout.isTTY && !forced) {
    throw new CredentialError(
      "refusing_tty_output",
      "stdout is a terminal; pipe this command or pass --force. Secrets must not enter scrollback",
    );
  }
}

/* --------------------------------------------------------------- commands */

async function cmdAcquire(flags) {
  const file = storePath();
  const sessionToken = await acquireFromBrowser();
  const session = await fetchSession(sessionToken);
  const previous = await readStore(file, { optional: true }).catch(() => null);
  const envelope = buildEnvelope(session, sessionToken, previous ? { acquired_at: previous.acquired_at, refresh_count: previous.refresh_count } : null);
  await writePrivateJson(file, envelope);
  report("acquired", envelope, file, flags);
}

async function cmdRefresh(flags) {
  const file = storePath();
  const current = await readStore(file);
  const session = await fetchSession(current.session_token);
  // Roll the session token forward when the server offers a re-signed one. This
  // slides the ~90-day window without a browser. Verified: adopting the rolled
  // token does NOT invalidate the previous one, so other boxes keep working.
  const rolled =
    typeof session.sessionToken === "string" && session.sessionToken.length >= 32
      ? session.sessionToken
      : current.session_token;
  const envelope = buildEnvelope(session, flags["no-roll"] ? current.session_token : rolled, current);
  await writePrivateJson(file, envelope);
  report("refreshed", envelope, file, flags);
}

async function cmdPrintAccessToken(flags) {
  assertSecretSinkAllowed(flags);
  const file = storePath();
  const current = await readStore(file);
  const expiry = Date.parse(current.access_token_expires ?? "");
  const stale =
    !current.access_token ||
    !Number.isFinite(expiry) ||
    expiry - Date.now() < ACCESS_TOKEN_MIN_REMAINING_MS;

  let token = current.access_token;
  if (stale && !flags["no-refresh"]) {
    // Refresh-over-storage: a stale stored token must never be served, because a
    // stale token silently shadowing a refreshable one is the known outage mode.
    const session = await fetchSession(current.session_token);
    const rolled =
      typeof session.sessionToken === "string" && session.sessionToken.length >= 32
        ? session.sessionToken
        : current.session_token;
    const envelope = buildEnvelope(session, rolled, current);
    await writePrivateJson(file, envelope);
    token = envelope.access_token;
  }
  if (!token) throw new CredentialError("no_access_token", "store holds no access token");
  process.stdout.write(token);
  if (process.stdout.isTTY) process.stdout.write("\n");
}

async function cmdExport(flags) {
  assertSecretSinkAllowed(flags);
  const current = await readStore(storePath());
  process.stdout.write(`${JSON.stringify(current)}\n`);
}

async function cmdImport(flags) {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  const raw = Buffer.concat(chunks).toString("utf8").trim();
  if (!raw) throw new CredentialError("import_empty", "no envelope on stdin");
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new CredentialError("import_invalid", "stdin was not valid JSON");
  }
  if (parsed?.schema !== CREDENTIAL_SCHEMA || typeof parsed.session_token !== "string") {
    throw new CredentialError("import_invalid", "not an oracle credential envelope");
  }
  const file = storePath();
  // Validate against the live service before trusting an imported credential, so a
  // dead copy is never installed and later mistaken for working auth.
  let envelope = parsed;
  if (!flags["no-verify"]) {
    const session = await fetchSession(parsed.session_token);
    envelope = buildEnvelope(session, parsed.session_token, parsed);
  }
  await writePrivateJson(file, envelope);
  report("imported", envelope, file, flags);
}

async function cmdDoctor(flags) {
  const file = storePath();
  const checks = [];
  const add = (name, status, detail) => checks.push({ name, status, detail });

  let current = null;
  try {
    current = await readStore(file);
    add("store_present", "pass", file);
  } catch (error) {
    add("store_present", "fail", error.message);
  }

  let liveOk = false;
  let live = null;
  if (current) {
    try {
      const meta = await stat(file);
      const mode = (meta.mode & 0o777).toString(8);
      add("store_permissions", (meta.mode & 0o077) === 0 ? "pass" : "fail", `mode ${mode}`);
    } catch {
      add("store_permissions", "fail", "could not stat store");
    }

    // Portability assertion: prove nothing in the envelope binds it to this box.
    const serialized = JSON.stringify(current);
    const bindings = [];
    if (serialized.includes(homedir())) bindings.push("home directory path");
    if (/"(profile_root|profile_fingerprint|uname|hostname|platform)"/.test(serialized)) {
      bindings.push("machine-specific field");
    }
    add(
      "portable",
      bindings.length === 0 ? "pass" : "fail",
      bindings.length === 0
        ? "no host/path/OS binding in envelope"
        : `envelope contains ${bindings.join(", ")}`,
    );

    const accessExp = Date.parse(current.access_token_expires ?? "");
    const accessAlive = Number.isFinite(accessExp) && accessExp > Date.now();
    add(
      "access_token",
      accessAlive
        ? accessExp - Date.now() < ACCESS_TOKEN_MIN_REMAINING_MS
          ? "warn"
          : "pass"
        : "warn",
      `fp ${current.access_token_fp ?? "none"} · expires ${current.access_token_expires ?? "unknown"} · ${remainingText(accessExp)} left${accessAlive ? "" : " (refresh will mint a new one)"}`,
    );

    const sessionExp = Date.parse(current.session_expires ?? "");
    add(
      "session_token",
      Number.isFinite(sessionExp) && sessionExp > Date.now() ? "pass" : "warn",
      `fp ${current.session_token_fp ?? "none"} · expires ${current.session_expires ?? "unknown"} · ${remainingText(sessionExp)} left`,
    );

    if (!flags.offline) {
      try {
        live = await fetchSession(current.session_token);
        liveOk = Boolean(live?.accessToken);
        add(
          "live_refresh",
          "pass",
          `browserless refresh works · account ${maskEmail(live?.user?.email) ?? "unknown"}`,
        );
      } catch (error) {
        add("live_refresh", "fail", error.message);
      }
    }

    if (live && current.account_id_fp && live.user?.id) {
      const same = fingerprint(live.user.id) === current.account_id_fp;
      add("account_match", same ? "pass" : "fail", same ? "same account" : "STORE POINTS AT A DIFFERENT ACCOUNT");
    }
  }

  // Stale-static-token shadowing check (the 8-week-outage failure mode).
  const shadowing = SHADOWING_ENV_VARS.filter((name) => process.env[name]);
  add(
    "no_env_shadowing",
    shadowing.length === 0 ? "pass" : "warn",
    shadowing.length === 0
      ? "no static token env vars set"
      : `set: ${shadowing.join(", ")} — a static value here can shadow this refreshable store`,
  );

  const failed = checks.filter((c) => c.status === "fail");
  const state = failed.length ? "blocked" : liveOk || flags.offline ? "ready" : "degraded";

  if (flags.json) {
    process.stdout.write(
      `${JSON.stringify({ schema: "oracle-subagent.credential-doctor.v1", state, store: file, checks }, null, 2)}\n`,
    );
  } else {
    const mark = { pass: "ok  ", warn: "warn", fail: "FAIL" };
    process.stdout.write(`oracle credential doctor: ${state}\nstore: ${file}\n\n`);
    for (const check of checks) {
      process.stdout.write(`  [${mark[check.status]}] ${check.name}: ${check.detail}\n`);
    }
    process.stdout.write("\n");
  }
  if (failed.length) process.exitCode = 1;
}

/** Human/JSON summary that reports fingerprints and expiries but never a secret. */
function report(action, envelope, file, flags) {
  const summary = {
    schema: "oracle-subagent.credential-report.v1",
    action,
    store: file,
    account_email_masked: envelope.account_email_masked,
    account_id_fp: envelope.account_id_fp,
    session_token_fp: envelope.session_token_fp,
    session_expires: envelope.session_expires,
    access_token_fp: envelope.access_token_fp,
    access_token_expires: envelope.access_token_expires,
    refresh_count: envelope.refresh_count,
  };
  if (flags.json) {
    process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
    return;
  }
  process.stdout.write(
    `${action}: ${file}\n` +
      `  account       ${summary.account_email_masked ?? "unknown"} (${summary.account_id_fp ?? "?"})\n` +
      `  session token ${summary.session_token_fp} · expires ${summary.session_expires ?? "unknown"} (${remainingText(Date.parse(summary.session_expires ?? ""))})\n` +
      `  access token  ${summary.access_token_fp} · expires ${summary.access_token_expires ?? "unknown"} (${remainingText(Date.parse(summary.access_token_expires ?? ""))})\n`,
  );
}

/* -------------------------------------------------------------------- main */

const COMMANDS = {
  acquire: cmdAcquire,
  refresh: cmdRefresh,
  doctor: cmdDoctor,
  "print-access-token": cmdPrintAccessToken,
  export: cmdExport,
  import: cmdImport,
  path: async () => process.stdout.write(`${storePath()}\n`),
};

function parseArgs(argv) {
  const flags = {};
  const positional = [];
  for (const arg of argv) {
    if (arg.startsWith("--")) flags[arg.slice(2)] = true;
    else positional.push(arg);
  }
  return { command: positional[0], flags };
}

async function main(argv) {
  const { command, flags } = parseArgs(argv);
  if (!command || flags.help) {
    process.stdout.write(
      "oracle-credential.mjs <command> [--json] [--force] [--offline] [--no-roll] [--no-verify]\n\n" +
        "  acquire             pull the session credential from the local authenticated browser (CDP)\n" +
        "  refresh             browserless renewal — works on d3/d3c with no browser and no macOS\n" +
        "  doctor              validity/expiry report; never prints the secret\n" +
        "  print-access-token  emit the access token for $(...) use; auto-refreshes when stale\n" +
        "  export              portable envelope on stdout, for transport to another box\n" +
        "  import              read an envelope from stdin and store it 0600\n" +
        "  path                print the store path\n",
    );
    return;
  }
  const handler = COMMANDS[command];
  if (!handler) throw new CredentialError("unknown_command", command);
  await handler(flags);
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  main(process.argv.slice(2)).catch((error) => {
    const code = error instanceof CredentialError ? error.code : "unexpected_error";
    process.stderr.write(`oracle-credential ${code}: ${error.message}\n`);
    process.exitCode = 1;
  });
}
