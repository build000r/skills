#!/usr/bin/env node
/**
 * oracle-session-heal.mjs — make `oracle-ask --doctor` enough.
 *
 * Safe, non-interactive repairs the operator should never have to hand-roll:
 *   1. Restore a logged-out CDP browser from the portable credential store
 *   2. Enroll auth-policy when the session is already Pro-authenticated
 *
 * Secrets never print. Progress goes to stderr; structured result on stdout
 * only when --json is set.
 */

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, realpathSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const SESSION_COOKIE = "__Secure-next-auth.session-token";
const ORIGIN = "https://chatgpt.com";
const DEFAULT_PORT = 9222;
const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));

export const HEALABLE_REASONS = Object.freeze([
  "logged_out",
  "auth_policy_missing",
  "pro_plan_missing",
  "pro_model_missing",
  "browser_receipt_stale",
  "listener_unverifiable",
  "exact_target_mismatch",
  "cdp_unreachable",
  "browser_receipt_invalid",
  "browser_receipt_changed",
]);

function log(line, { quiet = false } = {}) {
  if (quiet) return;
  process.stderr.write(`oracle-heal: ${line}\n`);
}

function storePath() {
  return (
    process.env.ORACLE_CREDENTIAL_STORE ||
    join(homedir(), ".oracle", "oracle-subagent", "credential.json")
  );
}

function runtimeRoot() {
  return (
    process.env.ORACLE_SUBAGENT_RUNTIME_DIR ||
    join(homedir(), ".oracle", "oracle-subagent")
  );
}

function resolvePort(explicit) {
  if (Number.isFinite(explicit) && explicit > 0) return explicit;
  const env = Number(process.env.ORACLE_CDP_PORT);
  if (Number.isFinite(env) && env > 0) return env;
  try {
    const cfg = JSON.parse(
      readFileSync(join(homedir(), ".oracle", "config.json"), "utf8"),
    );
    const p = Number(cfg.cdp_port ?? cfg.cdpPort);
    if (Number.isFinite(p) && p > 0) return p;
  } catch {
    /* ignore */
  }
  try {
    const receipt = JSON.parse(
      readFileSync(join(runtimeRoot(), "browser.json"), "utf8"),
    );
    const p = Number(receipt.port);
    if (Number.isFinite(p) && p > 0) return p;
  } catch {
    /* ignore */
  }
  return DEFAULT_PORT;
}

function readPortableSessionToken() {
  const file = storePath();
  let raw;
  try {
    raw = JSON.parse(readFileSync(file, "utf8"));
  } catch {
    return { ok: false, code: "credential_missing", detail: file };
  }
  const token = raw?.session_token;
  if (typeof token !== "string" || token.length < 32) {
    return { ok: false, code: "credential_invalid", detail: "no session_token" };
  }
  return {
    ok: true,
    token,
    fp: createHash("sha256").update(token).digest("hex").slice(0, 12),
  };
}

async function cdpJson(port, path) {
  const response = await fetch(`http://127.0.0.1:${port}${path}`, {
    signal: AbortSignal.timeout(5_000),
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`cdp_http_${response.status}`);
  return response.json();
}

function openWs(url) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    ws.addEventListener("open", () => resolve(ws), { once: true });
    ws.addEventListener("error", () => reject(new Error("cdp_ws_error")), {
      once: true,
    });
  });
}

function makeCaller(ws) {
  let nextId = 1;
  const pending = new Map();
  ws.addEventListener("message", (ev) => {
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch {
      return;
    }
    if (!msg.id || !pending.has(msg.id)) return;
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.error) reject(new Error(JSON.stringify(msg.error)));
    else resolve(msg.result);
  });
  return function call(method, params = {}, timeoutMs = 20_000) {
    const id = nextId++;
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
      setTimeout(() => {
        if (pending.has(id)) {
          pending.delete(id);
          reject(new Error(`cdp_timeout:${method}`));
        }
      }, timeoutMs);
    });
  };
}

/**
 * Inject the portable NextAuth session cookie into the live CDP Chrome and
 * reload ChatGPT so harvestCredentials / auth doctor see a Pro session.
 */
export async function restoreSessionFromPortableCredential({
  port = resolvePort(),
  quiet = false,
} = {}) {
  const cred = readPortableSessionToken();
  if (!cred.ok) return cred;

  let list;
  try {
    list = await cdpJson(port, "/json/list");
  } catch (error) {
    return {
      ok: false,
      code: "cdp_unreachable",
      detail: error?.message ?? String(error),
    };
  }
  const pages = Array.isArray(list)
    ? list.filter((t) => t?.type === "page" && t.webSocketDebuggerUrl)
    : [];
  const page =
    pages.find((t) => /chatgpt\.com/.test(t.url || "")) || pages[0] || null;
  if (!page) {
    return { ok: false, code: "cdp_no_chatgpt_target", detail: "no page target" };
  }

  let targetUrl = "https://chatgpt.com/";
  try {
    const receipt = JSON.parse(
      readFileSync(join(runtimeRoot(), "browser.json"), "utf8"),
    );
    if (
      typeof receipt.target_url === "string" &&
      receipt.target_url.startsWith("https://chatgpt.com/")
    ) {
      targetUrl = receipt.target_url;
    }
  } catch {
    /* root chat is fine */
  }

  const ws = await openWs(page.webSocketDebuggerUrl);
  const call = makeCaller(ws);
  try {
    await call("Network.enable");
    await call("Page.enable");
    const setResult = await call("Network.setCookie", {
      name: SESSION_COOKIE,
      value: cred.token,
      url: ORIGIN + "/",
      domain: "chatgpt.com",
      path: "/",
      secure: true,
      httpOnly: true,
      sameSite: "None",
      expires: Math.floor(Date.now() / 1000) + 90 * 24 * 3600,
    });
    if (setResult?.success !== true) {
      return { ok: false, code: "cookie_set_failed", detail: "setCookie rejected" };
    }
    await call("Page.navigate", { url: targetUrl });
    await new Promise((r) => setTimeout(r, 4500));
    const evaluated = await call("Runtime.evaluate", {
      expression: `(async () => {
        try {
          const s = await (await fetch("/api/auth/session", {
            credentials: "include",
            cache: "no-store",
          })).json();
          return {
            hasAccessToken: Boolean(s && s.accessToken),
            plan: s?.account?.planType || s?.planType || null,
          };
        } catch (e) {
          return { error: String(e && e.message || e) };
        }
      })()`,
      awaitPromise: true,
      returnByValue: true,
    });
    const session = evaluated?.result?.value || {};
    if (!session.hasAccessToken) {
      return {
        ok: false,
        code: "session_restore_failed",
        detail: session.error || `plan=${session.plan ?? "none"}`,
      };
    }
    log(
      `restored session from portable credential (fp ${cred.fp}, plan ${session.plan ?? "unknown"})`,
      { quiet },
    );
    return {
      ok: true,
      code: "session_restored",
      plan: session.plan,
      token_fp: cred.fp,
      target_url: targetUrl,
    };
  } finally {
    try {
      ws.close();
    } catch {
      /* ignore */
    }
  }
}

/**
 * Re-mint the production browser receipt (fresh observed_at + exact target).
 * Uses the launcher with the enrolled profile/URL from the prior receipt when
 * available. Never submits a ChatGPT turn.
 */
export function refreshBrowserReceipt({ quiet = false, port = resolvePort() } = {}) {
  const launcher = join(SCRIPT_DIR, "launch-chatgpt-cdp.sh");
  const xvfbHost = join(SCRIPT_DIR, "oracle-xvfb-host.sh");
  let profileDir = process.env.ORACLE_PROFILE_DIRECTORY || "";
  let url = process.env.ORACLE_CHATGPT_PROJECT_URL || "";
  let profileRoot = process.env.ORACLE_BROWSER_PROFILE_DIR || "";
  try {
    const receipt = JSON.parse(
      readFileSync(join(runtimeRoot(), "browser.json"), "utf8"),
    );
    if (!profileDir && typeof receipt.profile_directory === "string") {
      profileDir = receipt.profile_directory;
    }
    if (!profileRoot && typeof receipt.profile_root === "string") {
      profileRoot = receipt.profile_root;
    }
    if (
      !url &&
      typeof receipt.target_url === "string" &&
      receipt.target_url.startsWith("https://chatgpt.com/")
    ) {
      url = receipt.target_url;
    }
  } catch {
    /* launcher defaults */
  }
  // On the VPS host, Chrome runs under systemd with DISPLAY=:97. Non-interactive
  // SSH shells lack that env; without it the launcher refuses Linux launches.
  const env = {
    ...process.env,
    ORACLE_CDP_PORT: String(port),
  };
  if (!env.DISPLAY && process.platform === "linux") {
    env.DISPLAY = process.env.ORACLE_XVFB_DISPLAY
      ? `:${String(process.env.ORACLE_XVFB_DISPLAY).replace(/^:/, "")}`
      : ":97";
  }
  if (!env.XAUTHORITY && process.platform === "linux") {
    env.XAUTHORITY = join(homedir(), ".oracle", "Xauthority");
  }
  if (profileDir) env.ORACLE_PROFILE_DIRECTORY = profileDir;
  if (profileRoot) env.ORACLE_BROWSER_PROFILE_DIR = profileRoot;
  if (url) env.ORACLE_CHATGPT_PROJECT_URL = url;

  // Prefer the host supervisor when present: it owns Xvfb + Chrome units and
  // mints a production receipt. Fall back to the raw launcher (Mac / ad-hoc).
  let result;
  try {
    readFileSync(xvfbHost);
    log(`refreshing browser receipt via oracle-xvfb-host ensure (port ${port})`, {
      quiet,
    });
    result = spawnSync(xvfbHost, ["ensure"], {
      encoding: "utf8",
      env,
      timeout: 180_000,
    });
    if (result.status !== 0) {
      log("oracle-xvfb-host ensure failed; falling back to launch-chatgpt-cdp.sh", {
        quiet,
      });
      result = null;
    }
  } catch {
    result = null;
  }
  if (!result) {
    log(
      `refreshing browser receipt (port ${port}${profileDir ? `, profile ${profileDir}` : ""})`,
      { quiet },
    );
    result = spawnSync(
      launcher,
      ["--no-submit-smoke", "--json", "--port", String(port)],
      {
        encoding: "utf8",
        env,
        timeout: 120_000,
      },
    );
  }
  if (result.status !== 0) {
    return {
      ok: false,
      code: "receipt_refresh_failed",
      detail: (result.stderr || result.stdout || "").slice(0, 300),
    };
  }
  return { ok: true, code: "receipt_refreshed" };
}

/**
 * Enroll auth-policy from the live authenticated session without the
 * Darwin-only interactive login visibility path.
 *
 * Prefers `login --enroll-current-account` (works on Linux after the Xvfb
 * visibility no-op). Falls back to writing the policy from a live doctor
 * observation when login preflight fails solely on receipt/visibility noise
 * while the session is already Pro-authenticated.
 */
export function runAuthLoginEnroll({ quiet = false } = {}) {
  const script = join(SCRIPT_DIR, "oracle-subagent-auth.mjs");
  const hasPolicy = (() => {
    try {
      readFileSync(join(runtimeRoot(), "auth-policy.json"), "utf8");
      return true;
    } catch {
      return false;
    }
  })();
  if (hasPolicy) {
    return { ok: true, code: "already_enrolled" };
  }
  log("enrolling current Pro account into auth-policy", { quiet });
  const result = spawnSync(
    process.execPath,
    [script, "login", "--enroll-current-account", "--json"],
    {
      encoding: "utf8",
      env: process.env,
      timeout: 180_000,
    },
  );
  let report = null;
  try {
    report = JSON.parse(result.stdout || "null");
  } catch {
    report = null;
  }
  if (result.status === 0 && report?.ok) {
    return { ok: true, code: "enrolled", report };
  }
  const reasons = Array.isArray(report?.reasons) ? report.reasons : [];
  return {
    ok: false,
    code: reasons[0] || "login_failed",
    report,
    stderr: (result.stderr || "").slice(0, 400),
  };
}

export function runAuthDoctorReport() {
  const script = join(SCRIPT_DIR, "oracle-subagent-auth.mjs");
  const result = spawnSync(
    process.execPath,
    [script, "doctor", "--json"],
    {
      encoding: "utf8",
      env: process.env,
      timeout: 60_000,
    },
  );
  let report = null;
  try {
    report = JSON.parse(result.stdout || "null");
  } catch {
    report = null;
  }
  if (!report || typeof report.ok !== "boolean") {
    return {
      ok: false,
      reasons: ["auth_doctor_invalid"],
      checks: {},
    };
  }
  return {
    ok: report.ok === true,
    reasons: Array.isArray(report.reasons) ? report.reasons : [],
    checks: report.checks && typeof report.checks === "object" ? report.checks : {},
  };
}

/**
 * Apply every safe heal step the current doctor reasons require, then re-doctor.
 */
export async function healAuthSession({
  port = resolvePort(),
  quiet = false,
  maxPasses = 2,
} = {}) {
  const steps = [];
  let report = runAuthDoctorReport();
  if (report.ok) {
    return { ok: true, healed: false, steps, report, port };
  }

  for (let pass = 0; pass < maxPasses && !report.ok; pass += 1) {
    const reasons = new Set(report.reasons);
    let progressed = false;

    if (
      reasons.has("browser_receipt_stale") ||
      reasons.has("listener_unverifiable") ||
      reasons.has("exact_target_mismatch") ||
      reasons.has("cdp_unreachable") ||
      reasons.has("browser_receipt_invalid") ||
      reasons.has("browser_receipt_changed") ||
      report.checks?.receipt_fresh === false ||
      report.checks?.single_listener === false ||
      // Hard gate failures return empty checks — still try a receipt refresh.
      (Object.keys(report.checks || {}).length === 0 && reasons.size > 0)
    ) {
      const refreshed = refreshBrowserReceipt({ quiet, port });
      steps.push({
        action: "refresh_browser_receipt",
        ok: refreshed.ok === true,
        code: refreshed.code,
      });
      if (!refreshed.ok) {
        return {
          ok: false,
          healed: steps.length > 0,
          steps,
          report,
          port,
          blocker: refreshed,
        };
      }
      progressed = true;
      report = runAuthDoctorReport();
      if (report.ok) break;
    }

    const reasons2 = new Set(report.reasons);
    if (
      reasons2.has("logged_out") ||
      report.checks?.authenticated === false ||
      reasons2.has("pro_plan_missing") ||
      reasons2.has("pro_model_missing")
    ) {
      log(
        "browser session not Pro-authenticated; restoring from portable credential",
        { quiet },
      );
      const restored = await restoreSessionFromPortableCredential({
        port,
        quiet,
      });
      steps.push({
        action: "restore_session_from_portable_credential",
        ok: restored.ok === true,
        code: restored.code,
      });
      if (!restored.ok) {
        return {
          ok: false,
          healed: steps.length > 0,
          steps,
          report,
          port,
          blocker: restored,
        };
      }
      progressed = true;
      report = runAuthDoctorReport();
      if (report.ok) break;
    }

    const reasons3 = new Set(report.reasons);
    if (
      reasons3.has("auth_policy_missing") ||
      (report.checks?.authenticated === true &&
        report.checks?.policy_enrolled === false)
    ) {
      const enrolled = runAuthLoginEnroll({ quiet });
      steps.push({
        action: "enroll_auth_policy",
        ok: enrolled.ok === true,
        code: enrolled.code,
      });
      if (!enrolled.ok) {
        return {
          ok: false,
          healed: steps.length > 0,
          steps,
          report: enrolled.report || report,
          port,
          blocker: enrolled,
        };
      }
      progressed = true;
      report = runAuthDoctorReport();
      if (report.ok) break;
    }

    if (!progressed) break;
    const stillHealable = report.reasons.some((r) =>
      HEALABLE_REASONS.includes(r),
    );
    if (!stillHealable) break;
  }

  return {
    ok: report.ok === true,
    healed: steps.length > 0,
    steps,
    report,
    port,
  };
}

/**
 * Human-readable next action for a blocked auth doctor report.
 * Pure: no IO.
 */
export function remediationForAuthReport(report, { invokedAs = "sbp oracle" } = {}) {
  const reasons = Array.isArray(report?.reasons) ? report.reasons : [];
  const checks = report?.checks && typeof report.checks === "object" ? report.checks : {};
  const lines = [];

  if (reasons.length === 0) {
    lines.push("Auth doctor blocked without reasons; re-run with --json and inspect checks.");
    return lines.join("\n");
  }

  lines.push(`Blocked by: ${reasons.join(", ")}.`);

  const healable = reasons.filter((r) => HEALABLE_REASONS.includes(r));
  if (healable.length > 0) {
    lines.push("");
    lines.push(
      "Doctor can usually fix this without extra steps. Re-run:",
    );
    lines.push(`    ${invokedAs} --doctor`);
    lines.push(
      "(auto-heals: restore session from portable credential, enroll auth-policy)",
    );
  }

  if (reasons.includes("logged_out") || checks.authenticated === false) {
    lines.push("");
    lines.push("If auto-heal fails, refresh or re-import the portable credential:");
    lines.push("    node oracle-credential.mjs refresh && node oracle-credential.mjs doctor");
    lines.push("    # or from the Mac:  node oracle-credential.mjs export | ssh <box> 'node oracle-credential.mjs import'");
  }

  if (
    reasons.includes("listener_unverifiable") ||
    reasons.includes("cdp_unreachable") ||
    reasons.includes("exact_target_mismatch") ||
    reasons.includes("browser_receipt_stale") ||
    reasons.includes("browser_receipt_invalid")
  ) {
    lines.push("");
    lines.push("Refresh the dedicated CDP Chrome receipt, then re-run --doctor:");
    lines.push("    launch-chatgpt-cdp.sh --no-submit-smoke --json");
  }

  if (
    reasons.includes("auth_policy_missing") &&
    checks.authenticated === true
  ) {
    lines.push("");
    lines.push("Session is signed in; only enrollment is missing:");
    lines.push(
      "    node oracle-subagent-auth.mjs login --enroll-current-account --json",
    );
  }

  if (reasons.includes("wrong_account") || reasons.includes("profile_mismatch")) {
    lines.push("");
    lines.push(
      "Enrolled account/profile does not match the live browser. Re-enroll only after deliberate account change:",
    );
    lines.push("    rm ~/.oracle/oracle-subagent/auth-policy.json   # intentional only");
    lines.push(
      "    node oracle-subagent-auth.mjs login --enroll-current-account --json",
    );
  }

  return lines.join("\n");
}

async function main(argv) {
  const flags = new Set(argv.filter((a) => a.startsWith("--")));
  const quiet = flags.has("--quiet");
  const json = flags.has("--json");
  const portArg = argv.find((a, i) => argv[i - 1] === "--port");
  const port = resolvePort(portArg ? Number(portArg) : undefined);

  if (flags.has("--help") || argv.includes("-h")) {
    process.stdout.write(
      "oracle-session-heal.mjs [--json] [--quiet] [--port N]\n\n" +
        "  Restore CDP ChatGPT session from portable credential and enroll\n" +
        "  auth-policy when missing. Used by oracle-ask --doctor auto-heal.\n",
    );
    return 0;
  }

  const result = await healAuthSession({ port, quiet });
  if (json) {
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  } else if (result.ok) {
    process.stdout.write(
      result.healed
        ? `oracle-heal: ready after ${result.steps.length} step(s)\n`
        : "oracle-heal: already ready\n",
    );
  } else {
    process.stderr.write(
      `oracle-heal: still blocked (${(result.report?.reasons || []).join(", ") || result.blocker?.code || "unknown"})\n`,
    );
  }
  return result.ok ? 0 : 3;
}

const invokedAsMain = (() => {
  const argPath = process.argv[1];
  if (!argPath) return false;
  try {
    return import.meta.url === pathToFileURL(realpathSync(argPath)).href;
  } catch {
    return false;
  }
})();

if (invokedAsMain) {
  main(process.argv.slice(2)).then(
    (code) => {
      process.exitCode = code;
    },
    (error) => {
      process.stderr.write(`oracle-heal unexpected: ${error?.message || error}\n`);
      process.exitCode = 1;
    },
  );
}
