// Chrome/ChatGPT compatibility canary for the Oracle subagent.
//
// The Oracle lane depends on things nobody in this repo controls: the Chrome
// build on the host, the CDP protocol it speaks, ChatGPT's composer DOM, its
// auth surface, and whatever Cloudflare decides to interpose. Any of those can
// change under a working install, and the first symptom is normally a real
// research run failing halfway through.
//
// This canary moves that discovery earlier. It compares a pinned compatibility
// manifest against what the host actually presents, and classifies the
// difference as typed drift before production work starts.
//
// It never submits. That is structural, not a promise:
//
//   * the only CDP method it can issue is `Runtime.evaluate`, enforced by an
//     allowlist inside the one call helper — there is no code path to `Input.*`,
//     `Page.navigate`, `Target.createTarget`, `Target.activateTarget`, or
//     `Browser.setWindowBounds`;
//   * the page probe is a pure reader: it queries the DOM and returns counts and
//     classifications, it never clicks, types, focuses, or dispatches an event;
//   * the browser is never raised or focused, so a steady-state hidden window
//     stays hidden;
//   * the endpoint must be literal loopback. A hostname is refused outright,
//     because what a name resolves to can change under a running listener.
//
// It also never reports page text. A ChatGPT tab's title *is* the conversation
// title, and a conversation URL carries its id, so this module classifies both
// and emits the classification. `document.title` never reaches a report.
//
// Touching a browser is opt-in: with no `--endpoint` (or `ORACLE_CDP_ENDPOINT`)
// the canary runs its static checks, reports the live checks as skipped, and
// says `live_proved: false` rather than implying compatibility it did not
// observe.

import { realpathSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import {
  SELECTOR_OBSERVATION_SCHEMA,
  SELECTOR_PROOF_SCHEMA,
  proveSelectorObservation,
  selectorPageProbeExpression,
} from "./chatgpt-selector-contract.mjs";
import { AUTH_OBSERVATION_SCHEMA } from "./oracle-subagent-auth.mjs";

export const COMPATIBILITY_MANIFEST_SCHEMA =
  "oracle-subagent.compatibility-manifest.v1";
export const CANARY_OBSERVATION_SCHEMA =
  "oracle-subagent.canary-observation.v1";
export const CANARY_REPORT_SCHEMA = "oracle-subagent.canary-report.v1";

/**
 * The only CDP method this module can issue, and it is a read.
 *
 * Kept to exactly what is used. An allowlist with a spare entry is a hole
 * waiting for a future edit, so nothing sits here "in case".
 */
export const CDP_METHOD_ALLOWLIST = Object.freeze(["Runtime.evaluate"]);

const BROWSER_VERSION_PATTERN =
  /^([A-Za-z][A-Za-z0-9 ._-]{0,63})\/(\d+(?:\.\d+){0,3})$/;
const PROTOCOL_VERSION_PATTERN = /^\d+\.\d+$/;
const TARGET_ID_PATTERN = /^[A-Fa-f0-9]{16,128}$/;
const PRO_MODEL_PATTERN = /^gpt-[a-z0-9]+(?:[.-][a-z0-9]+)*-pro$/;
const MODES = new Set(["pro", "deep-research"]);
const VERSION_POLICIES = new Set(["exact_major", "at_least_major"]);
const CHATGPT_ORIGIN = "https://chatgpt.com";

const HTTP_TIMEOUT_MS = 3_000;
const CDP_TIMEOUT_MS = 5_000;
const MAX_TARGETS = 64;

export const EXIT_PASS = 0;
export const EXIT_DRIFT = 1;
export const EXIT_USAGE = 2;
export const EXIT_UNAVAILABLE = 3;

/**
 * The pinned baseline. Re-pin deliberately (see
 * references/oracle-subagent-compatibility.md); a manifest that drifts by
 * accident is a manifest that proves nothing.
 */
export const DEFAULT_COMPATIBILITY_MANIFEST = Object.freeze({
  schema: COMPATIBILITY_MANIFEST_SCHEMA,
  browser: Object.freeze({
    // Floor, not a ceiling. 150 is where `oracle-credential.mjs` already pins
    // the user-agent this lane presents, so the two statements about "which
    // Chrome generation we target" cannot drift apart silently. Raise it
    // deliberately when the host is rebuilt; see the reference doc.
    product: "Chrome",
    major: 150,
    policy: "at_least_major",
  }),
  cdp_protocol_version: "1.3",
  selector_observation_schema: SELECTOR_OBSERVATION_SCHEMA,
  selector_proof_schema: SELECTOR_PROOF_SCHEMA,
  auth_observation_schema: AUTH_OBSERVATION_SCHEMA,
  mode: "pro",
  pro_model: "gpt-5-5-pro",
});

export class OracleCanaryError extends Error {
  constructor(code) {
    super("oracle canary: rejected");
    this.name = "OracleCanaryError";
    this.code = code;
  }
}

function reject(code) {
  throw new OracleCanaryError(code);
}

function isPlainObject(value) {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.getPrototypeOf(value) === Object.prototype
  );
}

function exactObject(value, keys, code) {
  if (
    !isPlainObject(value) ||
    Object.keys(value).length !== keys.length ||
    !keys.every((key) => Object.hasOwn(value, key))
  ) {
    reject(code);
  }
  return value;
}

// --------------------------------------------------------------------------
// Compatibility manifest
// --------------------------------------------------------------------------

export function parseCompatibilityManifest(value) {
  const code = "manifest_invalid";
  exactObject(
    value,
    [
      "schema",
      "browser",
      "cdp_protocol_version",
      "selector_observation_schema",
      "selector_proof_schema",
      "auth_observation_schema",
      "mode",
      "pro_model",
    ],
    code,
  );
  if (value.schema !== COMPATIBILITY_MANIFEST_SCHEMA) reject(code);
  exactObject(value.browser, ["product", "major", "policy"], code);
  const { product, major, policy } = value.browser;
  if (
    typeof product !== "string" ||
    !/^[A-Za-z][A-Za-z0-9 ._-]{0,63}$/.test(product) ||
    !Number.isSafeInteger(major) ||
    major < 1 ||
    major > 10_000 ||
    !VERSION_POLICIES.has(policy)
  ) {
    reject(code);
  }
  if (
    typeof value.cdp_protocol_version !== "string" ||
    !PROTOCOL_VERSION_PATTERN.test(value.cdp_protocol_version)
  ) {
    reject(code);
  }
  for (const key of [
    "selector_observation_schema",
    "selector_proof_schema",
    "auth_observation_schema",
  ]) {
    if (typeof value[key] !== "string" || !value[key]) reject(code);
  }
  if (!MODES.has(value.mode)) reject(code);
  if (
    typeof value.pro_model !== "string" ||
    !PRO_MODEL_PATTERN.test(value.pro_model)
  ) {
    reject(code);
  }
  return Object.freeze({
    ...structuredClone(value),
    browser: Object.freeze({ ...value.browser }),
  });
}

export function parseBrowserVersion(text) {
  if (typeof text !== "string") reject("browser_version_invalid");
  const match = BROWSER_VERSION_PATTERN.exec(text.trim());
  if (!match) reject("browser_version_invalid");
  const parts = match[2].split(".").map((part) => Number.parseInt(part, 10));
  if (parts.some((part) => !Number.isSafeInteger(part) || part < 0)) {
    reject("browser_version_invalid");
  }
  return Object.freeze({
    product: match[1],
    version: match[2],
    major: parts[0],
    minor: parts[1] ?? 0,
    build: parts[2] ?? 0,
    patch: parts[3] ?? 0,
  });
}

function versionSatisfies(policy, pinnedMajor, observedMajor) {
  return policy === "exact_major"
    ? observedMajor === pinnedMajor
    : observedMajor >= pinnedMajor;
}

// --------------------------------------------------------------------------
// Loopback CDP, read-only
// --------------------------------------------------------------------------

export function parseLoopbackEndpoint(value) {
  if (typeof value !== "string" || !value.trim()) reject("endpoint_invalid");
  let parsed;
  try {
    parsed = new URL(value.trim());
  } catch {
    reject("endpoint_invalid");
  }
  if (parsed.protocol !== "http:") reject("endpoint_not_loopback");
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    reject("endpoint_invalid");
  }
  if (parsed.pathname !== "/" && parsed.pathname !== "") {
    reject("endpoint_invalid");
  }
  // A hostname is refused outright: what a name resolves to can change under a
  // running listener, so a name can never prove the endpoint is local.
  if (parsed.hostname !== "127.0.0.1" && parsed.hostname !== "[::1]") {
    reject("endpoint_not_loopback");
  }
  const port = Number.parseInt(parsed.port, 10);
  if (!Number.isSafeInteger(port) || port < 1024 || port > 65535) {
    reject("endpoint_invalid");
  }
  return Object.freeze({
    origin: `http://${parsed.hostname}:${port}`,
    hostname: parsed.hostname,
    port,
  });
}

function assertLoopbackWebSocketUrl(value, endpoint, targetId) {
  let parsed;
  try {
    parsed = new URL(String(value));
  } catch {
    reject("cdp_websocket_invalid");
  }
  if (
    parsed.protocol !== "ws:" ||
    parsed.hostname !== endpoint.hostname ||
    Number.parseInt(parsed.port, 10) !== endpoint.port ||
    parsed.username ||
    parsed.password ||
    parsed.pathname !== `/devtools/page/${targetId}`
  ) {
    reject("cdp_websocket_invalid");
  }
  return parsed.href;
}

async function fetchLoopbackJson(endpoint, pathname, { fetchImpl }) {
  let response;
  try {
    response = await fetchImpl(`${endpoint.origin}${pathname}`, {
      signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
      cache: "no-store",
    });
  } catch {
    reject("cdp_unreachable");
  }
  if (!response || response.ok !== true) reject("cdp_unreachable");
  try {
    return await response.json();
  } catch {
    reject("cdp_response_invalid");
  }
}

/**
 * The single CDP call helper. Every method goes through the allowlist here, so
 * there is exactly one place to audit for "can this thing send anything".
 */
async function cdpCall(
  webSocketUrl,
  method,
  params,
  { WebSocketImpl, timeoutMs = CDP_TIMEOUT_MS },
) {
  if (!CDP_METHOD_ALLOWLIST.includes(method)) reject("cdp_method_forbidden");
  const WebSocketConstructor = WebSocketImpl ?? globalThis.WebSocket;
  if (typeof WebSocketConstructor !== "function") reject("cdp_unavailable");
  let socket;
  try {
    socket = new WebSocketConstructor(webSocketUrl);
  } catch {
    reject("cdp_unreachable");
  }
  return new Promise((resolvePromise, rejectPromise) => {
    let settled = false;
    const settle = (callback, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try {
        socket.close();
      } catch {
        /* the socket is already gone; nothing to recover */
      }
      callback(value);
    };
    const timer = setTimeout(
      () => settle(rejectPromise, new OracleCanaryError("cdp_timeout")),
      timeoutMs,
    );
    socket.addEventListener(
      "open",
      () => socket.send(JSON.stringify({ id: 1, method, params })),
      { once: true },
    );
    socket.addEventListener("message", (event) => {
      let message;
      try {
        message = JSON.parse(String(event.data));
      } catch {
        settle(rejectPromise, new OracleCanaryError("cdp_response_invalid"));
        return;
      }
      if (message.id !== 1) return;
      if (message.error) {
        settle(rejectPromise, new OracleCanaryError("cdp_method_failed"));
        return;
      }
      settle(resolvePromise, message.result);
    });
    for (const name of ["error", "close"]) {
      socket.addEventListener(
        name,
        () => settle(rejectPromise, new OracleCanaryError("cdp_unreachable")),
        { once: true },
      );
    }
  });
}

/**
 * Exactly one visible ChatGPT page target, or fail closed.
 *
 * Zero and several are both refusals. "Several" matters most: picking the
 * first would make the canary report on a tab nobody meant, and a green canary
 * bound to the wrong tab is worse than a red one.
 */
export function selectExactChatGptTarget(targets) {
  if (!Array.isArray(targets) || targets.length > MAX_TARGETS) {
    reject("cdp_response_invalid");
  }
  const pages = [];
  for (const target of targets) {
    if (!isPlainObject(target)) continue;
    if (target.type !== "page") continue;
    if (typeof target.id !== "string" || !TARGET_ID_PATTERN.test(target.id)) {
      continue;
    }
    let parsed;
    try {
      parsed = new URL(String(target.url));
    } catch {
      continue;
    }
    if (parsed.origin !== CHATGPT_ORIGIN) continue;
    pages.push(Object.freeze({ id: target.id, url: parsed.href }));
  }
  if (pages.length === 0) reject("target_absent");
  if (pages.length > 1) reject("target_ambiguous");
  return pages[0];
}

// --------------------------------------------------------------------------
// The page probe: reads, classifies, never quotes
// --------------------------------------------------------------------------

/* c8 ignore start -- executed inside the page, not in this process */
function canaryPageProbe(targetId, originExpected) {
  const isVisible = (element) => {
    if (!element || typeof element.getBoundingClientRect !== "function") {
      return false;
    }
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const all = (selector) => Array.from(document.querySelectorAll(selector));
  const title = String(document.title || "");
  const challengeTitle =
    /just a moment|attention required|checking your browser|verify you are human/i.test(
      title,
    );
  const challengeNodes = all(
    "iframe[src*='challenge'],#challenge-form,.cf-challenge,#cf-challenge-running,[data-testid='cf-challenge']",
  ).length;
  const loginControls = all("a,button,[role='button']").filter((element) => {
    if (!isVisible(element)) return false;
    const label = String(element.innerText || element.textContent || "")
      .trim()
      .toLowerCase();
    return /^(log in|sign up|continue with)/.test(label);
  }).length;
  const composers = all("[data-testid='composer'],form [contenteditable='true']")
    .filter(isVisible).length;
  const promptFields = all(
    "#prompt-textarea,[data-testid='prompt-textarea'],textarea[name='prompt-textarea']",
  ).filter(isVisible).length;
  const sameOrigin = location.origin === originExpected;
  const conversation = /^\/c\/[A-Za-z0-9-]{8,128}$/.test(location.pathname);
  return {
    // Deliberately no title and no URL: a ChatGPT tab title IS the conversation
    // title and a /c/ path carries its id. Only classifications leave the page.
    schema: "oracle-subagent.canary-observation.v1",
    observed_at: new Date().toISOString(),
    target_id: targetId,
    same_origin: sameOrigin,
    path_class: conversation
      ? "conversation"
      : location.pathname === "/"
        ? "root"
        : "other",
    title_class: challengeTitle ? "challenge" : "normal",
    challenge_node_count: challengeNodes,
    login_control_count: loginControls,
    composer_visible_count: composers,
    prompt_field_visible_count: promptFields,
  };
}
/* c8 ignore stop */

export function canaryPageProbeSource() {
  return canaryPageProbe.toString();
}

export function canaryPageProbeExpression(targetId) {
  if (typeof targetId !== "string" || !TARGET_ID_PATTERN.test(targetId)) {
    reject("request_invalid");
  }
  return `(${canaryPageProbe})(${JSON.stringify(targetId)}, ${JSON.stringify(
    CHATGPT_ORIGIN,
  )})`;
}

export function normalizeCanaryObservation(value) {
  const code = "canary_observation_invalid";
  exactObject(
    value,
    [
      "schema",
      "observed_at",
      "target_id",
      "same_origin",
      "path_class",
      "title_class",
      "challenge_node_count",
      "login_control_count",
      "composer_visible_count",
      "prompt_field_visible_count",
    ],
    code,
  );
  if (value.schema !== CANARY_OBSERVATION_SCHEMA) reject(code);
  if (
    typeof value.observed_at !== "string" ||
    Number.isNaN(Date.parse(value.observed_at))
  ) {
    reject(code);
  }
  if (
    typeof value.target_id !== "string" ||
    !TARGET_ID_PATTERN.test(value.target_id)
  ) {
    reject(code);
  }
  if (typeof value.same_origin !== "boolean") reject(code);
  if (!["conversation", "root", "other"].includes(value.path_class)) {
    reject(code);
  }
  if (!["challenge", "normal"].includes(value.title_class)) reject(code);
  for (const key of [
    "challenge_node_count",
    "login_control_count",
    "composer_visible_count",
    "prompt_field_visible_count",
  ]) {
    if (!Number.isSafeInteger(value[key]) || value[key] < 0) reject(code);
  }
  return Object.freeze(structuredClone(value));
}

/**
 * Auth and Cloudflare compatibility, from the classified observation.
 *
 * Order matters: a Cloudflare interstitial hides the composer and shows no
 * login control, so checking auth first would report "logged out" for what is
 * really a challenge — and someone would go re-authenticate a session that was
 * never lost.
 */
export function classifyPageObservation(observation) {
  const value = normalizeCanaryObservation(observation);
  const findings = [];
  if (!value.same_origin) {
    findings.push({ check: "target_origin", status: "fail", code: "origin_drift" });
  } else {
    findings.push({ check: "target_origin", status: "pass", code: null });
  }
  const challenged =
    value.title_class === "challenge" || value.challenge_node_count > 0;
  findings.push({
    check: "cloudflare",
    status: challenged ? "fail" : "pass",
    code: challenged ? "cloudflare_challenge" : null,
  });
  if (challenged) {
    // Auth and composer readings are not meaningful behind an interstitial;
    // reporting them would manufacture two more failures from one cause.
    findings.push({ check: "auth", status: "skipped", code: "masked_by_challenge" });
    findings.push({
      check: "composer_selectors",
      status: "skipped",
      code: "masked_by_challenge",
    });
    return Object.freeze(findings.map((entry) => Object.freeze(entry)));
  }
  const loggedOut = value.login_control_count > 0;
  findings.push({
    check: "auth",
    status: loggedOut ? "fail" : "pass",
    code: loggedOut ? "auth_lost" : null,
  });
  const composerOk =
    value.composer_visible_count === 1 && value.prompt_field_visible_count === 1;
  findings.push({
    check: "composer_selectors",
    status: composerOk ? "pass" : "fail",
    code: composerOk
      ? null
      : value.composer_visible_count === 0
        ? "composer_absent"
        : "composer_ambiguous",
  });
  return Object.freeze(findings.map((entry) => Object.freeze(entry)));
}

// --------------------------------------------------------------------------
// Checks
// --------------------------------------------------------------------------

function check(name, scope, status, code, detail) {
  return Object.freeze({
    check: name,
    scope,
    status,
    code: code ?? null,
    detail: detail ?? null,
  });
}

/**
 * Static checks need no browser: they catch an upstream module bumping a
 * schema out from under the pinned manifest, which is drift a live probe would
 * only surface later as a confusing parse failure.
 */
export function staticChecks(manifest) {
  const pairs = [
    ["selector_observation_schema", SELECTOR_OBSERVATION_SCHEMA],
    ["selector_proof_schema", SELECTOR_PROOF_SCHEMA],
    ["auth_observation_schema", AUTH_OBSERVATION_SCHEMA],
  ];
  return pairs.map(([key, live]) =>
    manifest[key] === live
      ? check(key, "static", "pass", null, live)
      : check(key, "static", "fail", "contract_schema_drift", live),
  );
}

export function browserChecks(manifest, versionDocument) {
  if (!isPlainObject(versionDocument)) reject("cdp_response_invalid");
  const observed = parseBrowserVersion(versionDocument.Browser);
  const protocol = versionDocument["Protocol-Version"];
  const productOk = observed.product === manifest.browser.product;
  const majorOk =
    productOk &&
    versionSatisfies(manifest.browser.policy, manifest.browser.major, observed.major);
  const protocolOk =
    typeof protocol === "string" &&
    PROTOCOL_VERSION_PATTERN.test(protocol) &&
    protocol === manifest.cdp_protocol_version;
  return [
    check(
      "browser_product",
      "live",
      productOk ? "pass" : "fail",
      productOk ? null : "browser_product_drift",
      observed.product,
    ),
    check(
      "browser_version",
      "live",
      majorOk ? "pass" : "fail",
      majorOk ? null : "browser_version_drift",
      observed.version,
    ),
    check(
      "cdp_protocol_version",
      "live",
      protocolOk ? "pass" : "fail",
      protocolOk ? null : "cdp_protocol_drift",
      typeof protocol === "string" ? protocol : null,
    ),
  ];
}

function selectorCheck(manifest, rawObservation, target, now) {
  try {
    proveSelectorObservation(rawObservation, {
      target_id: target.id,
      target_url: target.url,
      mode: manifest.mode,
      model: manifest.pro_model,
      now,
    });
  } catch (error) {
    const code = error?.code ? String(error.code) : "selector_contract_failed";
    return check("selector_contract", "live", "fail", code, null);
  }
  return check("selector_contract", "live", "pass", null, manifest.pro_model);
}

// --------------------------------------------------------------------------
// Run
// --------------------------------------------------------------------------

const SKIPPABLE_LIVE_CHECKS = Object.freeze([
  "browser_product",
  "browser_version",
  "cdp_protocol_version",
  "target_binding",
  "selector_contract",
  "target_origin",
  "cloudflare",
  "auth",
  "composer_selectors",
]);

function skippedLiveChecks(code) {
  return SKIPPABLE_LIVE_CHECKS.map((name) =>
    check(name, "live", "skipped", code, null),
  );
}

export async function runCanary({
  manifest: rawManifest = DEFAULT_COMPATIBILITY_MANIFEST,
  endpoint: rawEndpoint = null,
  submit = false,
  now = new Date().toISOString(),
  fetchImpl = globalThis.fetch,
  WebSocketImpl = null,
} = {}) {
  // There is no supported submitting mode. The flag exists so that a caller
  // asking for one gets a refusal instead of a canary that quietly complies.
  if (submit !== false) reject("submit_forbidden");
  const manifest = parseCompatibilityManifest(rawManifest);
  const checks = [...staticChecks(manifest)];
  const blockers = [];
  let endpoint = null;
  let liveProved = false;

  if (rawEndpoint === null || rawEndpoint === undefined || rawEndpoint === "") {
    checks.push(...skippedLiveChecks("endpoint_unset"));
    blockers.push({
      blocker: "endpoint_unset",
      detail:
        "no --endpoint and no ORACLE_CDP_ENDPOINT; touching a browser is opt-in, "
        + "so selectors, auth, and Cloudflare compatibility were not observed",
    });
  } else {
    endpoint = parseLoopbackEndpoint(rawEndpoint);
    let version = null;
    let targets = null;
    try {
      version = await fetchLoopbackJson(endpoint, "/json/version", { fetchImpl });
      targets = await fetchLoopbackJson(endpoint, "/json/list", { fetchImpl });
    } catch (error) {
      const code = error?.code ? String(error.code) : "cdp_unreachable";
      checks.push(...skippedLiveChecks(code));
      blockers.push({
        blocker: code,
        detail: `loopback CDP endpoint ${endpoint.origin} did not answer`,
      });
      version = null;
    }
    if (version !== null) {
      checks.push(...browserChecks(manifest, version));
      let target = null;
      try {
        target = selectExactChatGptTarget(targets);
        checks.push(check("target_binding", "live", "pass", null, target.id));
      } catch (error) {
        const code = error?.code ? String(error.code) : "target_absent";
        checks.push(check("target_binding", "live", "fail", code, null));
        for (const name of [
          "selector_contract",
          "target_origin",
          "cloudflare",
          "auth",
          "composer_selectors",
        ]) {
          checks.push(check(name, "live", "skipped", "target_unbound", null));
        }
      }
      if (target !== null) {
        const socketUrl = assertLoopbackWebSocketUrl(
          (targets.find((entry) => entry?.id === target.id) || {})
            .webSocketDebuggerUrl,
          endpoint,
          target.id,
        );
        const selectorResult = await cdpCall(
          socketUrl,
          "Runtime.evaluate",
          {
            expression: selectorPageProbeExpression(target.id),
            returnByValue: true,
            awaitPromise: true,
          },
          { WebSocketImpl },
        );
        checks.push(
          selectorCheck(manifest, selectorResult?.result?.value, target, now),
        );
        const canaryResult = await cdpCall(
          socketUrl,
          "Runtime.evaluate",
          {
            expression: canaryPageProbeExpression(target.id),
            returnByValue: true,
            awaitPromise: true,
          },
          { WebSocketImpl },
        );
        for (const finding of classifyPageObservation(
          canaryResult?.result?.value,
        )) {
          checks.push(
            check(finding.check, "live", finding.status, finding.code, null),
          );
        }
        liveProved = true;
      }
    }
  }

  const failed = checks.filter((entry) => entry.status === "fail");
  const skippedLive = checks.filter(
    (entry) => entry.scope === "live" && entry.status === "skipped",
  );
  const status =
    failed.length > 0 ? "drift" : skippedLive.length > 0 ? "degraded" : "pass";
  return Object.freeze({
    schema: CANARY_REPORT_SCHEMA,
    generated_at: now,
    submit: false,
    manifest,
    endpoint: endpoint === null ? null : endpoint.origin,
    cdp_methods_allowed: CDP_METHOD_ALLOWLIST,
    checks: Object.freeze(checks),
    drift: Object.freeze(
      Array.from(new Set(failed.map((entry) => entry.code))).sort(),
    ),
    blockers: Object.freeze(blockers.map((entry) => Object.freeze(entry))),
    live_proved: liveProved,
    status,
  });
}

// --------------------------------------------------------------------------
// CLI
// --------------------------------------------------------------------------

export function parseArguments(argv) {
  const options = {
    json: false,
    endpoint: null,
    requireLive: false,
    manifestPath: null,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--json") {
      options.json = true;
    } else if (argument === "--no-submit") {
      // Accepted as an explicit affirmation of intent. There is no --submit:
      // the module has no code path that could send anything.
      continue;
    } else if (argument === "--require-live") {
      options.requireLive = true;
    } else if (argument === "--endpoint") {
      options.endpoint = argv[index + 1] ?? null;
      index += 1;
    } else if (argument.startsWith("--endpoint=")) {
      options.endpoint = argument.slice("--endpoint=".length);
    } else if (argument === "--manifest") {
      options.manifestPath = argv[index + 1] ?? null;
      index += 1;
    } else if (argument.startsWith("--manifest=")) {
      options.manifestPath = argument.slice("--manifest=".length);
    } else {
      reject("usage_invalid");
    }
  }
  if (options.endpoint === null) {
    const fromEnvironment = process.env.ORACLE_CDP_ENDPOINT;
    if (typeof fromEnvironment === "string" && fromEnvironment.trim()) {
      options.endpoint = fromEnvironment.trim();
    }
  }
  return options;
}

export async function main(
  rawArguments = process.argv.slice(2),
  // Injectable so a test can capture output without replacing
  // ``process.stdout.write``, which would also swallow the test runner's own
  // reporting and quietly corrupt its results.
  { write = (text) => process.stdout.write(text) } = {},
) {
  let options;
  try {
    options = parseArguments(rawArguments);
  } catch (error) {
    write(
      `${JSON.stringify({
        schema: CANARY_REPORT_SCHEMA,
        status: "error",
        code: error?.code ?? "usage_invalid",
      })}\n`,
    );
    return EXIT_USAGE;
  }
  let manifest = DEFAULT_COMPATIBILITY_MANIFEST;
  if (options.manifestPath !== null) {
    try {
      const { readFile } = await import("node:fs/promises");
      manifest = JSON.parse(await readFile(options.manifestPath, "utf8"));
    } catch {
      write(
        `${JSON.stringify({
          schema: CANARY_REPORT_SCHEMA,
          status: "error",
          code: "manifest_unreadable",
        })}\n`,
      );
      return EXIT_USAGE;
    }
  }
  let report;
  try {
    report = await runCanary({ manifest, endpoint: options.endpoint });
  } catch (error) {
    write(
      `${JSON.stringify({
        schema: CANARY_REPORT_SCHEMA,
        status: "error",
        code: error?.code ?? "internal_error",
      })}\n`,
    );
    return EXIT_USAGE;
  }
  write(
    options.json
      ? `${JSON.stringify(report)}\n`
      : `${report.status} live_proved=${report.live_proved} drift=${
          report.drift.join(",") || "none"
        }\n`,
  );
  if (report.status === "drift") return EXIT_DRIFT;
  if (report.status === "degraded") {
    return options.requireLive ? EXIT_UNAVAILABLE : EXIT_PASS;
  }
  return EXIT_PASS;
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
