#!/usr/bin/env node
// Secret-free authentication and Pro-capability gate for the dedicated
// hidden-headful ChatGPT browser. The steady-state doctor is observation-only:
// it never reads cookies/storage, types, clicks, or sends a message.

import { createHash, randomUUID } from "node:crypto";
import { spawnSync } from "node:child_process";
import {
  accessSync,
  constants as fsConstants,
  readdirSync,
  readFileSync,
  readlinkSync,
  realpathSync,
  statSync,
} from "node:fs";
import {
  link,
  lstat,
  open,
  realpath,
  stat,
  unlink,
} from "node:fs/promises";
import { homedir } from "node:os";
import {
  dirname,
  isAbsolute,
  join,
  resolve,
} from "node:path";
import { pathToFileURL } from "node:url";
import process from "node:process";

export const AUTH_OBSERVATION_SCHEMA = "oracle-subagent.auth-observation.v1";
export const AUTH_POLICY_SCHEMA = "oracle-subagent.auth-policy.v1";
export const AUTH_REPORT_SCHEMA = "oracle-subagent.auth-report.v1";

const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const TARGET_ID_PATTERN = /^[A-Fa-f0-9]{16,128}$/;
const SESSION_STATES = new Set(["authenticated", "guest", "ambiguous"]);
const PROJECT_STATES = new Set([
  "not_requested",
  "granted",
  "denied",
  "ambiguous",
]);
const RECEIPT_MAX_AGE_MS = 15 * 60 * 1000;
const OBSERVATION_MAX_AGE_MS = 30 * 1000;
const CHALLENGE_MAX_AGE_MS = 2 * 60 * 1000;

class AuthGateError extends Error {
  constructor(code) {
    super("oracle-subagent auth gate failed");
    this.name = "AuthGateError";
    this.code = code;
  }
}

function gateError(code) {
  throw new AuthGateError(code);
}

function isPlainObject(value) {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.getPrototypeOf(value) === Object.prototype
  );
}

function exactObject(value, keys, label) {
  if (!isPlainObject(value)) gateError(`${label}_invalid`);
  if (
    Object.keys(value).length !== keys.length ||
    keys.some((key) => !Object.hasOwn(value, key))
  ) {
    gateError(`${label}_invalid`);
  }
  return value;
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function requireSha256(value, code) {
  if (typeof value !== "string" || !SHA256_PATTERN.test(value)) {
    gateError(code);
  }
  return value;
}

function parseTimestamp(value, code) {
  if (typeof value !== "string") gateError(code);
  const milliseconds = Date.parse(value);
  const canonical = Number.isFinite(milliseconds)
    ? new Date(milliseconds).toISOString()
    : "";
  const canonicalWholeSecond = canonical.endsWith(".000Z")
    ? canonical.replace(".000Z", "Z")
    : canonical;
  if (
    !Number.isFinite(milliseconds) ||
    (value !== canonical && value !== canonicalWholeSecond)
  ) {
    gateError(code);
  }
  return milliseconds;
}

function ageIsFresh(timestamp, nowMs, maximumAgeMs) {
  const age = nowMs - timestamp;
  return age >= -5_000 && age <= maximumAgeMs;
}

export function normalizeChatGptUrl(
  value,
  code = "browser_receipt_invalid",
) {
  if (typeof value !== "string") gateError(code);
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    gateError(code);
  }
  if (
    parsed.protocol !== "https:" ||
    parsed.hostname !== "chatgpt.com" ||
    parsed.port ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash ||
    parsed.origin !== "https://chatgpt.com" ||
    parsed.href !== value ||
    value !== `${parsed.origin}${parsed.pathname}`
  ) {
    gateError(code);
  }
  if (
    parsed.pathname !== "/" &&
    !/^\/g\/g-p-[A-Za-z0-9_-]{8,128}\/project$/.test(parsed.pathname)
  ) {
    gateError(code);
  }
  return parsed.href;
}

export function isPermittedLoginTarget(
  requestedTargetUrl,
  observedTargetUrl,
) {
  return (
    classifyPermittedLoginTarget(
      requestedTargetUrl,
      observedTargetUrl,
    ) !== null
  );
}

function classifyPermittedLoginTarget(
  requestedTargetUrl,
  observedTargetUrl,
) {
  let requested;
  let observed;
  try {
    requested = new URL(requestedTargetUrl);
    observed = new URL(observedTargetUrl);
  } catch {
    return null;
  }
  if (
    requested.protocol !== "https:" ||
    requested.hostname !== "chatgpt.com" ||
    requested.port ||
    requested.username ||
    requested.password ||
    requested.search ||
    requested.hash ||
    requested.href !== requestedTargetUrl ||
    requestedTargetUrl !==
      `${requested.origin}${requested.pathname}` ||
    (requested.pathname !== "/" &&
      !/^\/g\/g-p-[A-Za-z0-9_-]{8,128}\/project$/.test(
        requested.pathname,
      )) ||
    observed.protocol !== "https:" ||
    observed.hostname !== "chatgpt.com" ||
    observed.port ||
    observed.username ||
    observed.password ||
    observed.hash ||
    observed.href !== observedTargetUrl ||
    observedTargetUrl !==
      `${observed.origin}${observed.pathname}${observed.search}`
  ) {
    return null;
  }
  if (
    observed.pathname === "/auth" ||
    observed.pathname.startsWith("/auth/")
  ) {
    return "auth";
  }
  if (
    requested.pathname !== "/" &&
    observed.pathname === "/" &&
    !observed.search
  ) {
    return "root";
  }
  return null;
}

function normalizeBrowserReceipt(value) {
  if (!isPlainObject(value)) gateError("browser_receipt_invalid");
  const required = [
    "schema",
    "state",
    "evidence_mode",
    "production_evidence",
    "attestation_simulated",
    "gatekeeper_assessed",
    "dynamic_code_verified",
    "chrome_signature_verified",
    "cdp_browser_pid_verified",
    "pid",
    "port",
    "bind",
    "profile_root",
    "profile_directory",
    "target_id",
    "target_url",
    "target_observed",
    "visibility",
    "visibility_verified",
    "process_visible",
    "process_frontmost",
    "submit_performed",
    "observed_at",
  ];
  if (required.some((key) => !Object.hasOwn(value, key))) {
    gateError("browser_receipt_invalid");
  }
  if (
    value.schema !== "oracle-subagent.browser.v1" ||
    value.state !== "ready" ||
    value.evidence_mode !== "production" ||
    value.production_evidence !== true ||
    value.attestation_simulated !== false ||
    value.gatekeeper_assessed !== true ||
    value.dynamic_code_verified !== true ||
    value.chrome_signature_verified !== true ||
    value.cdp_browser_pid_verified !== true ||
    value.bind !== "127.0.0.1" ||
    value.target_observed !== true ||
    value.visibility !== "hidden-headful" ||
    value.visibility_verified !== true ||
    value.process_visible !== false ||
    value.process_frontmost !== false ||
    value.submit_performed !== false
  ) {
    gateError("browser_receipt_invalid");
  }
  if (!Number.isSafeInteger(value.pid) || value.pid <= 1) {
    gateError("browser_receipt_invalid");
  }
  if (
    !Number.isSafeInteger(value.port) ||
    value.port < 1 ||
    value.port > 65535
  ) {
    gateError("browser_receipt_invalid");
  }
  if (
    typeof value.profile_root !== "string" ||
    !isAbsolute(value.profile_root) ||
    resolve(value.profile_root) !== value.profile_root ||
    typeof value.profile_directory !== "string" ||
    !/^[^/.\0][^/\0]{0,127}$/.test(value.profile_directory) ||
    value.profile_directory === ".."
  ) {
    gateError("browser_receipt_invalid");
  }
  if (
    typeof value.target_id !== "string" ||
    !TARGET_ID_PATTERN.test(value.target_id)
  ) {
    gateError("browser_receipt_invalid");
  }
  return {
    ...value,
    target_url: normalizeChatGptUrl(value.target_url),
    observed_at_ms: parseTimestamp(value.observed_at, "browser_receipt_invalid"),
  };
}

function normalizeObservation(value) {
  exactObject(
    value,
    [
      "schema",
      "observed_at",
      "profile_fingerprint",
      "account_fingerprint",
      "session_state",
      "challenge",
      "project_access",
      "pro_plan",
      "pro_model_available",
      "deep_research_available",
      "composer_available",
    ],
    "auth_observation",
  );
  if (value.schema !== AUTH_OBSERVATION_SCHEMA) {
    gateError("auth_observation_invalid");
  }
  const observedAtMs = parseTimestamp(
    value.observed_at,
    "auth_observation_invalid",
  );
  requireSha256(value.profile_fingerprint, "auth_observation_invalid");
  if (
    value.account_fingerprint !== null &&
    !SHA256_PATTERN.test(value.account_fingerprint)
  ) {
    gateError("auth_observation_invalid");
  }
  if (!SESSION_STATES.has(value.session_state)) {
    gateError("auth_observation_invalid");
  }
  exactObject(
    value.challenge,
    ["present", "observed_at"],
    "auth_observation",
  );
  if (typeof value.challenge.present !== "boolean") {
    gateError("auth_observation_invalid");
  }
  let challengeObservedAtMs = null;
  if (value.challenge.present) {
    challengeObservedAtMs = parseTimestamp(
      value.challenge.observed_at,
      "auth_observation_invalid",
    );
  } else if (value.challenge.observed_at !== null) {
    gateError("auth_observation_invalid");
  }
  if (!PROJECT_STATES.has(value.project_access)) {
    gateError("auth_observation_invalid");
  }
  for (const field of [
    "pro_plan",
    "pro_model_available",
    "deep_research_available",
    "composer_available",
  ]) {
    if (typeof value[field] !== "boolean") {
      gateError("auth_observation_invalid");
    }
  }
  return {
    ...structuredClone(value),
    observed_at_ms: observedAtMs,
    challenge_observed_at_ms: challengeObservedAtMs,
  };
}

function normalizePolicy(value) {
  exactObject(
    value,
    [
      "schema",
      "profile_fingerprint",
      "account_fingerprint",
      "enrolled_at",
    ],
    "auth_policy",
  );
  if (value.schema !== AUTH_POLICY_SCHEMA) gateError("auth_policy_invalid");
  requireSha256(value.profile_fingerprint, "auth_policy_invalid");
  requireSha256(value.account_fingerprint, "auth_policy_invalid");
  parseTimestamp(value.enrolled_at, "auth_policy_invalid");
  return structuredClone(value);
}

function normalizeSecurity(value) {
  exactObject(
    value,
    [
      "runtime_private",
      "receipt_private",
      "profile_private",
      "policy_private",
    ],
    "auth_security",
  );
  for (const field of Object.keys(value)) {
    if (typeof value[field] !== "boolean") gateError("auth_security_invalid");
  }
  return structuredClone(value);
}

function normalizeTransport(value) {
  exactObject(
    value,
    [
      "single_listener",
      "loopback_only",
      "pid_matches",
      "target_matches",
      "hidden",
    ],
    "auth_transport",
  );
  for (const field of Object.keys(value)) {
    if (typeof value[field] !== "boolean") gateError("auth_transport_invalid");
  }
  return structuredClone(value);
}

function addReason(reasons, condition, code) {
  if (!condition) reasons.push(code);
}

export function evaluateAuthDoctor({
  receipt_observed_at,
  observation: rawObservation,
  policy: rawPolicy,
  security: rawSecurity,
  transport: rawTransport,
  now = new Date().toISOString(),
  receipt_max_age_ms = RECEIPT_MAX_AGE_MS,
  observation_max_age_ms = OBSERVATION_MAX_AGE_MS,
  challenge_max_age_ms = CHALLENGE_MAX_AGE_MS,
}) {
  const nowMs = parseTimestamp(now, "doctor_input_invalid");
  const receiptObservedAtMs = parseTimestamp(
    receipt_observed_at,
    "doctor_input_invalid",
  );
  const observation = normalizeObservation(rawObservation);
  const policy = rawPolicy === null ? null : normalizePolicy(rawPolicy);
  const security = normalizeSecurity(rawSecurity);
  const transport = normalizeTransport(rawTransport);
  for (const value of [
    receipt_max_age_ms,
    observation_max_age_ms,
    challenge_max_age_ms,
  ]) {
    if (!Number.isSafeInteger(value) || value < 1) {
      gateError("doctor_input_invalid");
    }
  }

  const checks = {
    private_permissions: Object.values(security).every(Boolean),
    receipt_fresh: ageIsFresh(
      receiptObservedAtMs,
      nowMs,
      receipt_max_age_ms,
    ),
    single_listener: transport.single_listener,
    loopback_only: transport.loopback_only,
    browser_pid: transport.pid_matches,
    exact_target: transport.target_matches,
    browser_hidden: transport.hidden,
    observation_fresh: ageIsFresh(
      observation.observed_at_ms,
      nowMs,
      observation_max_age_ms,
    ),
    challenge_clear: !observation.challenge.present,
    authenticated: observation.session_state === "authenticated",
    policy_enrolled: policy !== null,
    profile_matches:
      policy !== null &&
      policy.profile_fingerprint === observation.profile_fingerprint,
    account_matches:
      policy !== null &&
      observation.account_fingerprint !== null &&
      policy.account_fingerprint === observation.account_fingerprint,
    project_access:
      observation.project_access === "not_requested" ||
      observation.project_access === "granted",
    pro_plan: observation.pro_plan,
    pro_model: observation.pro_model_available,
    composer_available: observation.composer_available,
  };

  const reasons = [];
  addReason(reasons, checks.private_permissions, "wrong_permissions");
  addReason(reasons, checks.receipt_fresh, "browser_receipt_stale");
  addReason(reasons, checks.single_listener, "listener_ambiguous");
  addReason(reasons, checks.loopback_only, "wildcard_cdp");
  addReason(reasons, checks.browser_pid, "browser_pid_mismatch");
  addReason(reasons, checks.exact_target, "exact_target_mismatch");
  addReason(reasons, checks.browser_hidden, "browser_visible");
  addReason(reasons, checks.observation_fresh, "auth_observation_stale");
  if (observation.challenge.present) {
    const challengeFresh = ageIsFresh(
      observation.challenge_observed_at_ms,
      nowMs,
      challenge_max_age_ms,
    );
    reasons.push(challengeFresh ? "challenge_present" : "stale_challenge");
  }
  if (!checks.authenticated) {
    reasons.push(
      observation.session_state === "guest" ? "logged_out" : "auth_ambiguous",
    );
  }
  if (!checks.policy_enrolled) {
    reasons.push("auth_policy_missing");
  } else {
    addReason(reasons, checks.profile_matches, "profile_mismatch");
    addReason(reasons, checks.account_matches, "wrong_account");
  }
  if (!checks.project_access) {
    reasons.push(
      observation.project_access === "denied"
        ? "project_denied"
        : "project_access_ambiguous",
    );
  }
  addReason(reasons, checks.pro_plan, "pro_plan_missing");
  addReason(reasons, checks.pro_model, "pro_model_missing");
  addReason(reasons, checks.composer_available, "composer_missing");

  return {
    schema: AUTH_REPORT_SCHEMA,
    ok: reasons.length === 0,
    state: reasons.length === 0 ? "ready" : "blocked",
    reasons,
    checks,
  };
}

export function loginCandidateReady(report, hasPolicy) {
  if (
    !isPlainObject(report) ||
    report.schema !== AUTH_REPORT_SCHEMA ||
    typeof hasPolicy !== "boolean"
  ) {
    gateError("doctor_input_invalid");
  }
  const ignored = new Set(["browser_visible"]);
  if (!hasPolicy) {
    ignored.add("auth_policy_missing");
    ignored.add("profile_mismatch");
    ignored.add("wrong_account");
  }
  return report.reasons.every((reason) => ignored.has(reason));
}

function profileFingerprint(profileRoot, profileDirectory) {
  return sha256(`${profileRoot}\0${profileDirectory}`);
}

async function inspectPrivateDirectory(pathname, code) {
  let metadata;
  try {
    metadata = await lstat(pathname);
  } catch {
    gateError(code);
  }
  if (
    !metadata.isDirectory() ||
    metadata.isSymbolicLink() ||
    metadata.uid !== process.getuid() ||
    (metadata.mode & 0o077) !== 0
  ) {
    gateError(code);
  }
  let canonical;
  try {
    canonical = await realpath(pathname);
  } catch {
    gateError(code);
  }
  if (canonical !== resolve(pathname)) gateError(code);
  return canonical;
}

function sameFileSnapshot(left, right) {
  return (
    left.dev === right.dev &&
    left.ino === right.ino &&
    left.uid === right.uid &&
    left.nlink === right.nlink &&
    left.mode === right.mode &&
    left.size === right.size &&
    left.mtimeMs === right.mtimeMs &&
    left.ctimeMs === right.ctimeMs
  );
}

async function readPrivateJson(pathname, code, { optional = false } = {}) {
  let before;
  try {
    before = await lstat(pathname);
  } catch (error) {
    if (optional && error?.code === "ENOENT") return null;
    gateError(code);
  }
  if (
    !before.isFile() ||
    before.isSymbolicLink() ||
    before.uid !== process.getuid() ||
    before.nlink !== 1 ||
    (before.mode & 0o077) !== 0
  ) {
    gateError("wrong_permissions");
  }
  let handle;
  try {
    handle = await open(
      pathname,
      fsConstants.O_RDONLY |
        (fsConstants.O_NOFOLLOW ?? 0) |
        (fsConstants.O_CLOEXEC ?? 0),
    );
    const opened = await handle.stat();
    if (
      !opened.isFile() ||
      opened.uid !== process.getuid() ||
      opened.nlink !== 1 ||
      !sameFileSnapshot(opened, before) ||
      (opened.mode & 0o077) !== 0
    ) {
      gateError("wrong_permissions");
    }
    const encoded = await handle.readFile("utf8");
    const after = await handle.stat();
    let pathAfter;
    try {
      pathAfter = await lstat(pathname);
    } catch {
      gateError(code);
    }
    if (
      !pathAfter.isFile() ||
      pathAfter.isSymbolicLink() ||
      pathAfter.uid !== process.getuid() ||
      pathAfter.nlink !== 1 ||
      (pathAfter.mode & 0o077) !== 0 ||
      !sameFileSnapshot(after, opened) ||
      !sameFileSnapshot(pathAfter, opened)
    ) {
      gateError(code);
    }
    try {
      return JSON.parse(encoded);
    } catch {
      gateError(code);
    }
  } catch (error) {
    if (error instanceof AuthGateError) throw error;
    gateError(code);
  } finally {
    await handle?.close().catch(() => {});
  }
}

export function parseListenerRecords(encoded) {
  if (typeof encoded !== "string") gateError("listener_unverifiable");
  const records = [];
  let current = null;
  for (const line of encoded.split(/\r?\n/)) {
    if (!line) continue;
    const prefix = line[0];
    const value = line.slice(1);
    if (prefix === "p") {
      if (!/^[0-9]+$/.test(value)) gateError("listener_unverifiable");
      current = {
        pid: Number(value),
        uid: null,
        command: null,
        names: [],
      };
      records.push(current);
      continue;
    }
    if (!current) gateError("listener_unverifiable");
    if (prefix === "u") {
      if (!/^[0-9]+$/.test(value)) gateError("listener_unverifiable");
      current.uid = Number(value);
    } else if (prefix === "c") {
      current.command = value;
    } else if (prefix === "n") {
      current.names.push(value);
    }
  }
  return records;
}

function inspectListenerFromLsof(receipt, lsofPath) {
  const result = spawnSync(
    lsofPath,
    [
      "-nP",
      `-iTCP:${receipt.port}`,
      "-sTCP:LISTEN",
      "-Fpcun",
    ],
    {
      encoding: "utf8",
      env: {
        LANG: "C",
        LC_ALL: "C",
        PATH: "/usr/bin:/bin:/usr/sbin:/sbin",
      },
      timeout: 3_000,
    },
  );
  if (result.error || result.status !== 0) gateError("listener_unverifiable");
  const records = parseListenerRecords(result.stdout);
  const expectedNames = new Set([
    `127.0.0.1:${receipt.port}`,
    `[::1]:${receipt.port}`,
  ]);
  return {
    single_listener:
      records.length === 1 &&
      records[0].pid === receipt.pid &&
      records[0].uid === process.getuid(),
    loopback_only:
      records.length === 1 &&
      records[0].names.length > 0 &&
      records[0].names.every((name) => expectedNames.has(name)),
  };
}

function inspectListenerLinux(receipt) {
  // Prefer lsof when present (same -F records as Darwin). Fall back to /proc
  // so the VPS host still works if lsof is missing from PATH.
  for (const lsofPath of ["/usr/bin/lsof", "/usr/sbin/lsof"]) {
    try {
      return inspectListenerFromLsof(receipt, lsofPath);
    } catch (error) {
      if (!(error instanceof AuthGateError)) throw error;
    }
  }
  let exe;
  try {
    exe = realpathSync(`/proc/${receipt.pid}/exe`);
  } catch {
    gateError("listener_unverifiable");
  }
  if (!exe || typeof exe !== "string") gateError("listener_unverifiable");
  let cmdline = "";
  try {
    cmdline = readFileSync(`/proc/${receipt.pid}/cmdline`, "utf8");
  } catch {
    gateError("listener_unverifiable");
  }
  const argv = cmdline.includes("\0")
    ? cmdline.split("\0").filter(Boolean)
    : cmdline.trim().split(/\s+/).filter(Boolean);
  const joined = argv.join(" ");
  const hasPort =
    argv.some((part) => part === `--remote-debugging-port=${receipt.port}`) ||
    joined.includes(`--remote-debugging-port=${receipt.port}`);
  const hasLoopback =
    argv.some((part) => part === "--remote-debugging-address=127.0.0.1") ||
    joined.includes("--remote-debugging-address=127.0.0.1");
  if (!hasPort || !hasLoopback) gateError("listener_unverifiable");
  // Confirm the TCP listen slot is loopback-only via /proc/net/tcp.
  let loopbackOnly = false;
  let singleMatch = false;
  let pidOwnsListener = false;
  try {
    const table = readFileSync("/proc/net/tcp", "utf8");
    const portHex = Number(receipt.port).toString(16).toUpperCase().padStart(4, "0");
    const matches = [];
    for (const line of table.split("\n").slice(1)) {
      const parts = line.trim().split(/\s+/);
      if (parts.length < 10) continue;
      const local = parts[1];
      const state = parts[3];
      if (state !== "0A") continue; // TCP_LISTEN
      const [addrHex, port] = local.split(":");
      if (port !== portHex) continue;
      matches.push({ addrHex, inode: parts[9] });
    }
    singleMatch = matches.length === 1;
    // 0100007F = 127.0.0.1 little-endian
    loopbackOnly = singleMatch && matches[0].addrHex === "0100007F";
    const ownedSocketInodes = new Set();
    for (const fd of readdirSync(`/proc/${receipt.pid}/fd`)) {
      let target;
      try {
        target = readlinkSync(`/proc/${receipt.pid}/fd/${fd}`);
      } catch {
        continue;
      }
      const match = /^socket:\[([0-9]+)\]$/.exec(target);
      if (match) ownedSocketInodes.add(match[1]);
    }
    pidOwnsListener =
      singleMatch &&
      ownedSocketInodes.has(matches[0].inode) &&
      statSync(`/proc/${receipt.pid}`).uid === process.getuid();
  } catch {
    gateError("listener_unverifiable");
  }
  return {
    single_listener: singleMatch && pidOwnsListener,
    loopback_only: loopbackOnly,
  };
}

function PathExistsProc(pid) {
  try {
    accessSync(`/proc/${pid}`, fsConstants.F_OK);
    return true;
  } catch {
    return false;
  }
}

function inspectListener(receipt) {
  if (process.platform === "linux") {
    return inspectListenerLinux(receipt);
  }
  if (process.platform !== "darwin") gateError("listener_unverifiable");
  return inspectListenerFromLsof(receipt, "/usr/sbin/lsof");
}

function inspectVisibility(pid) {
  if (process.platform === "linux") {
    // Hidden-headful under Xvfb: no operator-visible display. Contract is
    // "process still alive" — true headless is forbidden at launch time.
    if (!PathExistsProc(pid)) gateError("visibility_unverifiable");
    return true;
  }
  if (process.platform !== "darwin") gateError("visibility_unverifiable");
  const script = [
    "on run argv",
    "set browserPid to (item 1 of argv) as integer",
    'tell application "System Events"',
    "set browserProcess to first application process whose unix id is browserPid",
    "set offscreenWindows to true",
    "repeat with browserWindow in windows of browserProcess",
    "set windowPosition to position of browserWindow",
    "if (item 1 of windowPosition) > -10000 then set offscreenWindows to false",
    "end repeat",
    'return (visible of browserProcess as text) & \":\" & (frontmost of browserProcess as text) & \":\" & (offscreenWindows as text)',
    "end tell",
    "end run",
  ].join("\n");
  const result = spawnSync("/usr/bin/osascript", ["-", String(pid)], {
    input: script,
    encoding: "utf8",
    env: {
      LANG: "C",
      LC_ALL: "C",
      PATH: "/usr/bin:/bin",
    },
    timeout: 5_000,
  });
  if (result.error || result.status !== 0) gateError("visibility_unverifiable");
  const [visible, frontmost, offscreen] = result.stdout.trim().split(":");
  return (
    visible === "false" &&
    frontmost === "false" &&
    new Set(["true", "false"]).has(offscreen)
  );
}

function requireLoopbackWebSocket(value, port, code) {
  if (typeof value !== "string") gateError(code);
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    gateError(code);
  }
  if (
    parsed.protocol !== "ws:" ||
    !new Set(["127.0.0.1", "localhost", "[::1]"]).has(parsed.hostname) ||
    Number(parsed.port) !== port ||
    parsed.username ||
    parsed.password
  ) {
    gateError(code);
  }
  parsed.hostname = "127.0.0.1";
  return parsed.href;
}

async function fetchLoopbackJson(port, path, code) {
  try {
    const response = await fetch(`http://127.0.0.1:${port}${path}`, {
      signal: AbortSignal.timeout(3_000),
      cache: "no-store",
    });
    if (!response.ok) gateError(code);
    return await response.json();
  } catch (error) {
    if (error instanceof AuthGateError) throw error;
    gateError(code);
  }
}

async function cdpCall(webSocketUrl, method, params = {}, timeoutMs = 5_000) {
  let socket;
  try {
    socket = new WebSocket(webSocketUrl);
  } catch {
    gateError("cdp_unreachable");
  }
  return new Promise((resolvePromise, rejectPromise) => {
    let settled = false;
    const settle = (callback, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try {
        socket.close();
      } catch {}
      callback(value);
    };
    const timer = setTimeout(
      () => settle(rejectPromise, new AuthGateError("cdp_unreachable")),
      timeoutMs,
    );
    socket.addEventListener(
      "open",
      () => {
        socket.send(JSON.stringify({ id: 1, method, params }));
      },
      { once: true },
    );
    socket.addEventListener("message", (event) => {
      let message;
      try {
        message = JSON.parse(String(event.data));
      } catch {
        settle(rejectPromise, new AuthGateError("cdp_unreachable"));
        return;
      }
      if (message.id !== 1) return;
      if (message.error) {
        settle(rejectPromise, new AuthGateError("cdp_unreachable"));
        return;
      }
      settle(resolvePromise, message.result);
    });
    socket.addEventListener(
      "error",
      () => settle(rejectPromise, new AuthGateError("cdp_unreachable")),
      { once: true },
    );
  });
}

export function canonicalProCapability(
  modelsBody,
  proEffortSelected = false,
) {
  const models = Array.isArray(modelsBody?.models)
    ? modelsBody.models
    : modelsBody?.models &&
        typeof modelsBody.models === "object" &&
        !Array.isArray(modelsBody.models)
      ? Object.values(modelsBody.models)
      : [];
  const identifiers = models
    .filter(
      (model) =>
        model &&
        typeof model === "object" &&
        model.enabled !== false &&
        model.available !== false &&
        !model.unavailable_reason &&
        typeof model.slug === "string" &&
        /^gpt-[a-z0-9]+(?:[.-][a-z0-9]+)*-pro$/.test(model.slug),
    )
    .map((model) => model.slug);
  if (proEffortSelected === true && models.length > 0) {
    identifiers.push("ui-selected-pro-effort");
  }
  return {
    available: identifiers.length > 0,
    identifiers,
  };
}

export function deriveAccountCapability(
  meResponse,
  accountsResponse,
  loginControl,
  proModelAvailable,
  proPlanUiAvailable = false,
) {
  const me =
    meResponse?.ok === true &&
    meResponse.body &&
    typeof meResponse.body === "object"
      ? meResponse.body
      : null;
  const accountMap =
    accountsResponse?.ok === true &&
    accountsResponse.body?.accounts &&
    typeof accountsResponse.body.accounts === "object" &&
    !Array.isArray(accountsResponse.body.accounts)
      ? accountsResponse.body.accounts
      : null;
  const accountEntries = accountMap ? Object.values(accountMap) : [];
  const accessible = accountEntries.filter(
    (entry) =>
      entry &&
      typeof entry === "object" &&
      entry.can_access_with_session === true &&
      entry.account?.is_deactivated !== true,
  );
  const proAccounts = accessible.filter((entry) => {
    const accountPlan = String(entry?.account?.plan_type ?? "").toLowerCase();
    const subscriptionPlan = String(
      entry?.entitlement?.subscription_plan ?? "",
    ).toLowerCase();
    return (
      new Set(["pro", "chatgptproplan", "chatgpt-pro"]).has(accountPlan) ||
      new Set(["pro", "chatgptproplan", "chatgpt-pro"]).has(subscriptionPlan)
    ) &&
      entry?.entitlement?.has_active_subscription === true &&
      entry?.entitlement?.is_delinquent !== true;
  });
  const identity =
    typeof me?.id === "string" && me.id.length > 0 ? me.id : null;
  let sessionState = "ambiguous";
  if (
    identity &&
    accessible.length > 0 &&
    (loginControl !== true || proPlanUiAvailable === true)
  ) {
    sessionState = "authenticated";
  } else if (loginControl === true || (accountMap && accessible.length === 0)) {
    sessionState = "guest";
  }
  // ChatGPT exposes one account twice: once under its UUID and once under the
  // "default" alias, with an identical account_id. Collapse aliases before the
  // uniqueness test, or a single-account Pro user reads as ambiguous and the
  // Pro plan is never proven. Prefer the concrete key so the workspace identity
  // does not become the literal string "default".
  const aliasKey = (entry) =>
    [
      entry?.account?.account_id,
      entry?.account?.organization_id,
      entry?.account?.account_user_id,
    ].find((value) => typeof value === "string" && value.length > 0) ?? null;
  const collapseAliases = (entries) => {
    const distinct = [];
    for (const entry of entries) {
      const key = aliasKey(entry);
      if (key === null) {
        distinct.push(entry);
        continue;
      }
      const seenAt = distinct.findIndex((seen) => aliasKey(seen) === key);
      if (seenAt === -1) {
        distinct.push(entry);
        continue;
      }
      const seenMapKey = accountMap
        ? Object.entries(accountMap).find(
            ([, value]) => value === distinct[seenAt],
          )?.[0]
        : null;
      if (seenMapKey === "default") distinct[seenAt] = entry;
    }
    return distinct;
  };
  const distinctPro = collapseAliases(proAccounts);
  const distinctAccessible = collapseAliases(accessible);
  const uniquePro = distinctPro.length === 1 ? distinctPro[0] : null;
  const selectedAccount =
    uniquePro ??
    (proPlanUiAvailable === true && distinctAccessible.length === 1
      ? distinctAccessible[0]
      : null);
  const selectedAccountMapKey =
    selectedAccount !== null && accountMap
      ? Object.entries(accountMap).find(
          ([, entry]) => entry === selectedAccount,
        )?.[0]
      : null;
  const workspaceIdentity =
    selectedAccount?.account &&
    [
      selectedAccount.account.account_id,
      selectedAccount.account.account_user_id,
      selectedAccount.account.organization_id,
      selectedAccountMapKey,
    ].find((value) => typeof value === "string" && value.length > 0);
  const proPlan =
    sessionState === "authenticated" &&
    proModelAvailable === true &&
    selectedAccount !== null &&
    (uniquePro !== null || proPlanUiAvailable === true) &&
    typeof workspaceIdentity === "string";
  return {
    session_state: sessionState,
    pro_plan: proPlan,
    account_identity:
      proPlan && identity
        ? `${identity}\0${workspaceIdentity}`
        : null,
    features:
      selectedAccount && Array.isArray(selectedAccount.features)
        ? selectedAccount.features.filter((value) => typeof value === "string")
        : [],
  };
}

async function authPageProbe(
  requestedUrl,
  canonicalProCapabilityFunction,
  deriveAccountCapabilityFunction,
) {
  const normalizedText = (value) =>
    String(value || "")
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();
  const isVisible = (element) => {
    const rectangle = element.getBoundingClientRect();
    return rectangle.width > 1 && rectangle.height > 1;
  };
  const sha = async (value) => {
    const bytes = await crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(String(value)),
    );
    return Array.from(new Uint8Array(bytes))
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("");
  };
  // backend-api authenticates by bearer, not by cookie. Without this header it
  // answers 200 describing a guest: plan_type "guest" and 5 free model slugs
  // instead of "pro" and 19 including gpt-5-6-pro and research. That failed
  // open, leaving the DOM as the only real evidence of the Pro plan.
  const bearer = await (async () => {
    try {
      const session = await fetch("/api/auth/session", {
        credentials: "include",
        cache: "no-store",
      });
      const body = await session.json().catch(() => null);
      return typeof body?.accessToken === "string" ? body.accessToken : "";
    } catch {
      return "";
    }
  })();
  const readJson = async (path) => {
    try {
      const response = await fetch(path, {
        credentials: "include",
        cache: "no-store",
        headers: bearer ? { Authorization: `Bearer ${bearer}` } : {},
      });
      const body = await response.json().catch(() => null);
      return { ok: response.ok, status: response.status, body };
    } catch {
      return { ok: false, status: 0, body: null };
    }
  };
  const bodyText = normalizedText(document.body?.innerText);
  const controls = Array.from(
    document.querySelectorAll("button,a,[role='button']"),
  )
    .filter(isVisible)
    .map((element) =>
      normalizedText(
        `${element.innerText || element.textContent || ""} ${
          element.getAttribute("aria-label") || ""
        }`,
      ),
    );
  const composer = document.querySelector(
    "#prompt-textarea[contenteditable='true'],[contenteditable='true'][role='textbox']",
  );
  const composerAvailable = Boolean(composer);
  const composerForm = composer?.closest("form") ?? null;
  const profileProAvailable = Array.from(
    document.querySelectorAll("[data-testid='accounts-profile-button']"),
  )
    .filter(isVisible)
    .some((element) =>
      Array.from(element.querySelectorAll("*")).some(
        (child) => normalizedText(child.textContent) === "pro",
      ),
    );
  const proEffortSelected =
    composerForm !== null &&
    Array.from(composerForm.querySelectorAll("button,[role='button']"))
      .filter(isVisible)
      .some(
        (element) =>
          normalizedText(element.innerText || element.textContent) === "pro",
      );
  const challengePresent =
    /just a moment|attention required|checking your browser/i.test(
      document.title,
    ) ||
    Boolean(
      document.querySelector(
        "iframe[src*='challenge'],#challenge-form,.cf-challenge",
      ),
    );
  const loginControl = controls.some((label) =>
    /^(log in|sign up)( |$)/.test(label),
  );
  const projectDenied =
    /you do not have access|project not found|unable to load project|you don.t have access|access denied/.test(
      bodyText,
    );

  const [meResponse, accountsResponse, modelsResponse] = await Promise.all([
    readJson("/backend-api/me"),
    readJson("/backend-api/accounts/check/v4-2023-04-27"),
    readJson("/backend-api/models?history_and_training_disabled=false"),
  ]);
  const modelCapability = canonicalProCapabilityFunction(
    modelsResponse.ok ? modelsResponse.body : null,
    proEffortSelected,
  );
  const accountCapability = deriveAccountCapabilityFunction(
    meResponse,
    accountsResponse,
    loginControl,
    modelCapability.available,
    profileProAvailable,
  );
  const deepResearchAvailable =
    accountCapability.features.some((value) => /deep.?research/i.test(value)) ||
    controls.some((value) => /deep research/.test(value));

  const requested = new URL(requestedUrl);
  let projectAccess = "not_requested";
  if (requested.pathname !== "/") {
    if (
      !/^\/g\/g-p-[A-Za-z0-9_-]{8,128}\/project$/.test(
        requested.pathname,
      )
    ) {
      projectAccess = "ambiguous";
    } else if (projectDenied) {
      projectAccess = "denied";
    } else if (
      location.href === requested.href &&
      composerAvailable
    ) {
      projectAccess = "granted";
    } else {
      projectAccess = "ambiguous";
    }
  }

  const observedAt = new Date().toISOString();
  return {
    schema: "oracle-subagent.auth-observation.v1",
    observed_at: observedAt,
    profile_fingerprint: "",
    account_fingerprint: accountCapability.account_identity
      ? await sha(accountCapability.account_identity)
      : null,
    session_state: accountCapability.session_state,
    challenge: {
      present: challengePresent,
      observed_at: challengePresent ? observedAt : null,
    },
    project_access: projectAccess,
    pro_plan: accountCapability.pro_plan,
    pro_model_available: modelCapability.available,
    deep_research_available: deepResearchAvailable,
    composer_available: composerAvailable,
  };

}

export function authPageProbeSource() {
  return [
    canonicalProCapability.toString(),
    deriveAccountCapability.toString(),
    authPageProbe.toString(),
  ].join("\n");
}

async function collectObservation(
  receipt,
  { allowAuthNavigation = false } = {},
) {
  const version = await fetchLoopbackJson(
    receipt.port,
    "/json/version",
    "cdp_unreachable",
  );
  const browserWebSocket = requireLoopbackWebSocket(
    version.webSocketDebuggerUrl,
    receipt.port,
    "cdp_unreachable",
  );
  const processInfo = await cdpCall(
    browserWebSocket,
    "SystemInfo.getProcessInfo",
  );
  const browsers = processInfo?.processInfo?.filter(
    (entry) => entry.type === "browser",
  );
  const pidMatches =
    Array.isArray(browsers) &&
    browsers.length === 1 &&
    browsers[0].id === receipt.pid;

  const targets = await fetchLoopbackJson(
    receipt.port,
    "/json",
    "exact_target_mismatch",
  );
  const matches = Array.isArray(targets)
    ? targets.filter((target) => target.id === receipt.target_id)
    : [];
  const target = matches.length === 1 ? matches[0] : null;
  let targetMatches = false;
  let observation = null;
  let targetWebSocket = null;
  let loginNavigationState = null;
  if (target?.type === "page") {
    let parsedTarget;
    try {
      parsedTarget = new URL(target.url);
    } catch {}
    const exactTargetUrl = parsedTarget?.href === receipt.target_url;
    const permittedLoginNavigation =
      allowAuthNavigation &&
      classifyPermittedLoginTarget(receipt.target_url, target.url);
    loginNavigationState = exactTargetUrl
      ? "exact"
      : permittedLoginNavigation;
    if (exactTargetUrl || permittedLoginNavigation) {
      targetWebSocket = requireLoopbackWebSocket(
        target.webSocketDebuggerUrl,
        receipt.port,
        "exact_target_mismatch",
      );
      const targetWebSocketPath = new URL(targetWebSocket).pathname;
      const exactTargetSocket =
        targetWebSocketPath === `/devtools/page/${receipt.target_id}` &&
        target.id === receipt.target_id;
      targetMatches =
        exactTargetSocket &&
        Boolean(loginNavigationState);
      if (exactTargetSocket) {
        const expression = `(${authPageProbe})(${JSON.stringify(
          receipt.target_url,
        )}, ${canonicalProCapability}, ${deriveAccountCapability})`;
        const evaluated = await cdpCall(targetWebSocket, "Runtime.evaluate", {
          expression,
          awaitPromise: true,
          returnByValue: true,
        });
        if (
          evaluated?.exceptionDetails ||
          !Object.hasOwn(evaluated?.result ?? {}, "value")
        ) {
          gateError("auth_observation_invalid");
        }
        observation = evaluated.result.value;
      }
    }
  }
  if (!observation) gateError("exact_target_mismatch");
  observation.profile_fingerprint = profileFingerprint(
    receipt.profile_root,
    receipt.profile_directory,
  );
  normalizeObservation(observation);
  return {
    pidMatches,
    targetMatches,
    observation,
    browserWebSocket,
    targetWebSocket,
    loginNavigationState,
  };
}

function runtimePaths() {
  const runtimeRoot =
    process.env.ORACLE_SUBAGENT_RUNTIME_DIR ||
    join(homedir(), ".oracle", "oracle-subagent");
  if (
    !isAbsolute(runtimeRoot) ||
    resolve(runtimeRoot) !== runtimeRoot ||
    runtimeRoot === "/" ||
    runtimeRoot === homedir()
  ) {
    gateError("runtime_path_invalid");
  }
  return {
    runtimeRoot,
    receiptPath: join(runtimeRoot, "browser.json"),
    policyPath: join(runtimeRoot, "auth-policy.json"),
  };
}

export async function readAuthPolicy(pathname) {
  const value = await readPrivateJson(pathname, "auth_policy_invalid", {
    optional: true,
  });
  return value === null ? null : normalizePolicy(value);
}

export async function writeAuthPolicy(pathname, rawPolicy) {
  const policy = normalizePolicy(rawPolicy);
  const parent = dirname(pathname);
  await inspectPrivateDirectory(parent, "wrong_permissions");
  const existing = await readPrivateJson(pathname, "auth_policy_invalid", {
    optional: true,
  });
  if (existing !== null) gateError("auth_policy_exists");
  const temporary = join(parent, `.auth-policy.${randomUUID()}.tmp`);
  let handle;
  try {
    handle = await open(
      temporary,
      fsConstants.O_WRONLY |
        fsConstants.O_CREAT |
        fsConstants.O_EXCL |
        (fsConstants.O_CLOEXEC ?? 0),
      0o600,
    );
    await handle.writeFile(`${JSON.stringify(policy)}\n`, "utf8");
    await handle.sync();
    await handle.close();
    handle = null;
    await link(temporary, pathname);
    await unlink(temporary);
    const directory = await open(parent, fsConstants.O_RDONLY);
    try {
      await directory.sync();
    } finally {
      await directory.close();
    }
    return policy;
  } catch (error) {
    if (error instanceof AuthGateError) throw error;
    if (error?.code === "EEXIST") gateError("auth_policy_exists");
    gateError("auth_policy_write_failed");
  } finally {
    await handle?.close().catch(() => {});
    await unlink(temporary).catch(() => {});
  }
}

function policyFromObservation(observation) {
  if (
    observation.session_state !== "authenticated" ||
    observation.account_fingerprint === null ||
    !observation.pro_plan ||
    !observation.pro_model_available
  ) {
    gateError("login_not_ready");
  }
  return {
    schema: AUTH_POLICY_SCHEMA,
    profile_fingerprint: observation.profile_fingerprint,
    account_fingerprint: observation.account_fingerprint,
    enrolled_at: new Date().toISOString(),
  };
}

async function collectLiveContext({ allowAuthNavigation = false } = {}) {
  const paths = runtimePaths();
  await inspectPrivateDirectory(paths.runtimeRoot, "wrong_permissions");
  const rawReceipt = await readPrivateJson(
    paths.receiptPath,
    "browser_receipt_invalid",
  );
  const receipt = normalizeBrowserReceipt(rawReceipt);
  const canonicalProfileRoot = await inspectPrivateDirectory(
    receipt.profile_root,
    "wrong_permissions",
  );
  const canonicalProfile = await inspectPrivateDirectory(
    join(canonicalProfileRoot, receipt.profile_directory),
    "wrong_permissions",
  );
  if (canonicalProfile !== join(canonicalProfileRoot, receipt.profile_directory)) {
    gateError("wrong_permissions");
  }
  const listenerBefore = inspectListener(receipt);
  const collected = await collectObservation(receipt, {
    allowAuthNavigation,
  });
  const hidden = inspectVisibility(receipt.pid);
  const policy = await readAuthPolicy(paths.policyPath);
  const finalRawReceipt = await readPrivateJson(
    paths.receiptPath,
    "browser_receipt_invalid",
  );
  normalizeBrowserReceipt(finalRawReceipt);
  if (sha256(JSON.stringify(finalRawReceipt)) !== sha256(JSON.stringify(rawReceipt))) {
    gateError("browser_receipt_changed");
  }
  const finalPolicy = await readAuthPolicy(paths.policyPath);
  if (sha256(JSON.stringify(finalPolicy)) !== sha256(JSON.stringify(policy))) {
    gateError("auth_policy_changed");
  }
  await inspectPrivateDirectory(paths.runtimeRoot, "wrong_permissions");
  await inspectPrivateDirectory(receipt.profile_root, "wrong_permissions");
  await inspectPrivateDirectory(
    join(receipt.profile_root, receipt.profile_directory),
    "wrong_permissions",
  );
  const listenerAfter = inspectListener(receipt);
  return {
    paths,
    receipt,
    observation: collected.observation,
    policy,
    browserWebSocket: collected.browserWebSocket,
    targetWebSocket: collected.targetWebSocket,
    loginNavigationState: collected.loginNavigationState,
    security: {
      runtime_private: true,
      receipt_private: true,
      profile_private: true,
      policy_private: true,
    },
    transport: {
      single_listener:
        listenerBefore.single_listener && listenerAfter.single_listener,
      loopback_only:
        listenerBefore.loopback_only && listenerAfter.loopback_only,
      pid_matches: collected.pidMatches,
      target_matches: collected.targetMatches,
      hidden,
    },
  };
}

function reportForContext(context, now = new Date().toISOString()) {
  return evaluateAuthDoctor({
    receipt_observed_at: context.receipt.observed_at,
    observation: context.observation,
    policy: context.policy,
    security: context.security,
    transport: context.transport,
    now,
  });
}

export function loginPreflightReady(report) {
  if (!isPlainObject(report) || report.schema !== AUTH_REPORT_SCHEMA) {
    gateError("doctor_input_invalid");
  }
  return [
    "private_permissions",
    "receipt_fresh",
    "single_listener",
    "loopback_only",
    "browser_pid",
    "exact_target",
    "browser_hidden",
    "observation_fresh",
  ].every((check) => report.checks?.[check] === true);
}

export function sameBrowserContext(left, right) {
  if (!isPlainObject(left?.receipt) || !isPlainObject(right?.receipt)) {
    gateError("doctor_input_invalid");
  }
  const fields = [
    "schema",
    "pid",
    "port",
    "profile_root",
    "profile_directory",
    "target_id",
    "target_url",
    "observed_at",
  ];
  return (
    fields.every((field) => left.receipt[field] === right.receipt[field]) &&
    left.paths?.runtimeRoot === right.paths?.runtimeRoot &&
    left.browserWebSocket === right.browserWebSocket &&
    left.targetWebSocket === right.targetWebSocket
  );
}

function loginRestoreReady(context) {
  return (
    context?.loginNavigationState === "root" &&
    context?.observation?.session_state === "authenticated" &&
    context.observation.pro_plan === true &&
    context.observation.pro_model_available === true &&
    context.observation.composer_available === true
  );
}

async function restorePinnedLoginTarget(context) {
  if (
    context?.loginNavigationState !== "root" ||
    typeof context?.targetWebSocket !== "string"
  ) {
    gateError("exact_target_mismatch");
  }
  await cdpCall(context.targetWebSocket, "Page.navigate", {
    url: context.receipt.target_url,
  });
}

function samePolicySnapshot(left, right) {
  return sha256(JSON.stringify(left)) === sha256(JSON.stringify(right));
}

async function setInteractiveVisibility(context, visible) {
  const { receipt, browserWebSocket } = context;
  if (visible) {
    await cdpCall(browserWebSocket, "Target.activateTarget", {
      targetId: receipt.target_id,
    });
    const window = await cdpCall(
      browserWebSocket,
      "Browser.getWindowForTarget",
      { targetId: receipt.target_id },
    );
    if (!Number.isSafeInteger(window?.windowId)) {
      gateError("visibility_unverifiable");
    }
    await cdpCall(browserWebSocket, "Browser.setWindowBounds", {
      windowId: window.windowId,
      bounds: {
        windowState: "normal",
        left: 80,
        top: 80,
        width: 1280,
        height: 900,
      },
    });
  } else if (process.platform === "linux") {
    // Re-hide under Xvfb by parking the window offscreen; no operator display.
    try {
      const window = await cdpCall(
        browserWebSocket,
        "Browser.getWindowForTarget",
        { targetId: receipt.target_id },
      );
      if (Number.isSafeInteger(window?.windowId)) {
        await cdpCall(browserWebSocket, "Browser.setWindowBounds", {
          windowId: window.windowId,
          bounds: {
            windowState: "normal",
            left: -32000,
            top: -32000,
            width: 1280,
            height: 900,
          },
        });
      }
    } catch {
      // Best-effort; hidden-headful under Xvfb is already non-operator-visible.
    }
  }
  // Linux Xvfb has no AppKit/System Events process visibility. Doctor already
  // treats "process alive under Xvfb" as hidden; login/enroll must not require
  // osascript or the VPS host can never enroll from a restored session.
  if (process.platform === "linux") {
    return;
  }
  if (process.platform !== "darwin") {
    gateError("visibility_unverifiable");
  }
  const script = visible
    ? [
        "on run argv",
        "set browserPid to (item 1 of argv) as integer",
        'tell application "System Events"',
        "set browserProcess to first application process whose unix id is browserPid",
        "set visible of browserProcess to true",
        "set frontmost of browserProcess to true",
        "end tell",
        "end run",
      ].join("\n")
    : [
        "on run argv",
        "set browserPid to (item 1 of argv) as integer",
        'tell application "System Events"',
        "set browserProcess to first application process whose unix id is browserPid",
        "repeat with browserWindow in windows of browserProcess",
        "set position of browserWindow to {-32000, -32000}",
        "end repeat",
        "set visible of browserProcess to false",
        "end tell",
        "end run",
      ].join("\n");
  const result = spawnSync("/usr/bin/osascript", ["-", String(receipt.pid)], {
    input: script,
    encoding: "utf8",
    env: {
      LANG: "C",
      LC_ALL: "C",
      PATH: "/usr/bin:/bin",
    },
    timeout: 5_000,
  });
  if (result.error || result.status !== 0) gateError("visibility_unverifiable");
}

function safeFailure(command, code) {
  return {
    schema: AUTH_REPORT_SCHEMA,
    command,
    ok: false,
    state: "blocked",
    reasons: [code],
    checks: {},
  };
}

function commandReport(command, report) {
  return {
    schema: report.schema,
    command,
    ok: report.ok,
    state: report.state,
    reasons: report.reasons,
    checks: report.checks,
  };
}

function emit(report, json) {
  if (json) {
    process.stdout.write(`${JSON.stringify(report)}\n`);
    return;
  }
  process.stdout.write(
    report.ok
      ? `oracle-subagent auth: ${report.command} ready\n`
      : `oracle-subagent auth: ${report.command} blocked (${report.reasons.join(
          ", ",
        )})\n`,
  );
}

function parseCli(rawArguments) {
  const [command = "", ...flags] = rawArguments;
  if (!new Set(["status", "doctor", "login"]).has(command)) {
    gateError("usage");
  }
  let json = false;
  let enrollCurrentAccount = false;
  let timeoutSeconds = 600;
  for (let index = 0; index < flags.length; index += 1) {
    const flag = flags[index];
    if (flag === "--json") {
      json = true;
    } else if (flag === "--enroll-current-account") {
      enrollCurrentAccount = true;
    } else if (flag === "--timeout-seconds") {
      const raw = flags[index + 1];
      if (!/^[0-9]+$/.test(raw || "")) gateError("usage");
      timeoutSeconds = Number(raw);
      index += 1;
    } else {
      gateError("usage");
    }
  }
  if (
    !Number.isSafeInteger(timeoutSeconds) ||
    timeoutSeconds < 30 ||
    timeoutSeconds > 900
  ) {
    gateError("usage");
  }
  if (command !== "login" && (enrollCurrentAccount || timeoutSeconds !== 600)) {
    gateError("usage");
  }
  return { command, json, enrollCurrentAccount, timeoutSeconds };
}

async function runLogin(options) {
  const anchor = await collectLiveContext({
    allowAuthNavigation: true,
  });
  const preflight = reportForContext(anchor);
  if (!loginPreflightReady(preflight)) {
    gateError("login_preflight_failed");
  }
  if (anchor.policy === null && !options.enrollCurrentAccount) {
    gateError("enrollment_confirmation_required");
  }
  if (anchor.policy !== null && options.enrollCurrentAccount) {
    gateError("auth_policy_exists");
  }
  let context = anchor;
  let interrupted = false;
  const interrupt = () => {
    interrupted = true;
  };
  process.once("SIGINT", interrupt);
  process.once("SIGTERM", interrupt);
  let madeVisible = false;
  try {
    if (anchor.loginNavigationState === "root") {
      await restorePinnedLoginTarget(anchor);
    }
    madeVisible = true;
    await setInteractiveVisibility(anchor, true);
    const deadline = Date.now() + options.timeoutSeconds * 1_000;
    while (Date.now() < deadline) {
      if (interrupted) gateError("login_cancelled");
      await new Promise((resolvePromise) => setTimeout(resolvePromise, 2_000));
      context = await collectLiveContext({ allowAuthNavigation: true });
      if (!sameBrowserContext(anchor, context)) {
        gateError("browser_rollover");
      }
      if (!samePolicySnapshot(anchor.policy, context.policy)) {
        gateError("auth_policy_changed");
      }
      if (loginRestoreReady(context)) {
        await restorePinnedLoginTarget(context);
        continue;
      }
      const report = reportForContext(context);
      if (loginCandidateReady(report, context.policy !== null)) {
        let expectedPolicy = context.policy;
        if (context.policy === null) {
          expectedPolicy = await writeAuthPolicy(
            context.paths.policyPath,
            policyFromObservation(context.observation),
          );
        }
        await setInteractiveVisibility(anchor, false);
        madeVisible = false;
        const finalContext = await collectLiveContext();
        if (!sameBrowserContext(anchor, finalContext)) {
          gateError("browser_rollover");
        }
        if (!samePolicySnapshot(expectedPolicy, finalContext.policy)) {
          gateError("auth_policy_changed");
        }
        const finalReport = reportForContext(finalContext);
        if (!finalReport.ok) gateError("login_verification_failed");
        return commandReport("login", finalReport);
      }
    }
    gateError("login_timeout");
  } finally {
    process.removeListener("SIGINT", interrupt);
    process.removeListener("SIGTERM", interrupt);
    if (madeVisible) {
      await setInteractiveVisibility(anchor, false).catch(() => {});
    }
  }
}

export async function main(rawArguments = process.argv.slice(2)) {
  let options;
  try {
    options = parseCli(rawArguments);
  } catch (error) {
    const report = safeFailure(
      new Set(["status", "doctor", "login"]).has(rawArguments[0])
        ? rawArguments[0]
        : "unknown",
      error instanceof AuthGateError ? error.code : "internal_error",
    );
    emit(report, rawArguments.includes("--json"));
    return 2;
  }
  try {
    if (options.command === "login") {
      const report = await runLogin(options);
      emit(report, options.json);
      return 0;
    }
    const context = await collectLiveContext();
    const report = commandReport(options.command, reportForContext(context));
    emit(report, options.json);
    if (options.command === "status") return 0;
    return report.ok ? 0 : 1;
  } catch (error) {
    const code =
      error instanceof AuthGateError ? error.code : "internal_error";
    const report = safeFailure(options.command, code);
    emit(report, options.json);
    return options.command === "status" ? 0 : 1;
  }
}

let invokedAsMain = false;
try {
  invokedAsMain =
    Boolean(process.argv[1]) &&
    import.meta.url === pathToFileURL(realpathSync(resolve(process.argv[1]))).href;
} catch {
  invokedAsMain = false;
}
if (invokedAsMain) {
  process.exitCode = await main();
}
