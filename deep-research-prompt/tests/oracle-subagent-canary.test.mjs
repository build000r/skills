// Contract tests for the Chrome/ChatGPT compatibility canary.
//
//   node --test deep-research-prompt/tests/oracle-subagent-canary.test.mjs
//
// The load-bearing claims are (1) drift is detected before production work and
// (2) the canary cannot send. Both are tested against the real fake CDP server
// rather than a mock of the canary's own internals: the live path runs end to
// end over loopback HTTP + WebSocket, and the fake server's call log is what
// proves no window was raised and nothing was submitted.

import assert from "node:assert/strict";
import { test } from "node:test";
import { runInNewContext } from "node:vm";

import {
  CANARY_OBSERVATION_SCHEMA,
  CANARY_REPORT_SCHEMA,
  CDP_METHOD_ALLOWLIST,
  COMPATIBILITY_MANIFEST_SCHEMA,
  DEFAULT_COMPATIBILITY_MANIFEST,
  EXIT_DRIFT,
  EXIT_PASS,
  EXIT_UNAVAILABLE,
  EXIT_USAGE,
  OracleCanaryError,
  browserChecks,
  canaryPageProbeExpression,
  classifyPageObservation,
  main,
  parseArguments,
  parseBrowserVersion,
  parseCompatibilityManifest,
  parseLoopbackEndpoint,
  runCanary,
  selectExactChatGptTarget,
  staticChecks,
} from "../assets/scripts/oracle-subagent-canary.mjs";
import { SELECTOR_OBSERVATION_SCHEMA } from "../assets/scripts/chatgpt-selector-contract.mjs";
import { startFakeCdp } from "./fake-cdp.mjs";

const TARGET_ID = "ABCDEF0123456789";
const OBSERVED_AT = "2026-07-28T07:20:00.000Z";
const NOW = "2026-07-28T07:20:05.000Z";
const PRO_MODEL = "gpt-5-5-pro";

// The fake CDP server reports FakeChrome/1.0 and protocol 1.3 and is outside
// this node's write scope, so the live-path manifest pins to what it serves.
// The manifest is an input for exactly this reason.
function fakeManifest(overrides = {}) {
  return {
    ...DEFAULT_COMPATIBILITY_MANIFEST,
    browser: { product: "FakeChrome", major: 1, policy: "at_least_major" },
    pro_model: PRO_MODEL,
    ...overrides,
  };
}

function selectorObservation(overrides = {}) {
  return {
    schema: SELECTOR_OBSERVATION_SCHEMA,
    observed_at: OBSERVED_AT,
    target_id: TARGET_ID,
    target_url: "https://chatgpt.com/",
    composer_count: 1,
    composer_visible: true,
    prompt_field_count: 1,
    model_control_count: 1,
    model_control_enabled: true,
    model_machine_id: null,
    model_selection: "pro",
    catalog_pro_model_ids: [PRO_MODEL],
    active_tool_count: 0,
    active_tools_enabled: true,
    tool_selection: "none",
    ...overrides,
  };
}

function canaryObservation(overrides = {}) {
  return {
    schema: CANARY_OBSERVATION_SCHEMA,
    observed_at: OBSERVED_AT,
    target_id: TARGET_ID,
    same_origin: true,
    path_class: "root",
    title_class: "normal",
    challenge_node_count: 0,
    login_control_count: 0,
    composer_visible_count: 1,
    prompt_field_visible_count: 1,
    ...overrides,
  };
}

function findCheck(report, name) {
  return report.checks.find((entry) => entry.check === name);
}

async function withFakeCdp(scenario, body) {
  const fake = await startFakeCdp(scenario);
  try {
    return await body(fake);
  } finally {
    await fake.close();
  }
}

function liveScenario({ selector = selectorObservation(), canary = canaryObservation() } = {}) {
  return {
    targets: [
      {
        id: TARGET_ID,
        type: "page",
        url: "https://chatgpt.com/",
        title: "ChatGPT fixture",
      },
    ],
    // The canary evaluates the selector probe first, then its own DOM probe.
    runtime_results: { [TARGET_ID]: [selector, canary] },
  };
}

// ---------------------------------------------------------------------------
// Compatibility manifest
// ---------------------------------------------------------------------------

test("the shipped default manifest is valid and frozen", () => {
  const manifest = parseCompatibilityManifest(DEFAULT_COMPATIBILITY_MANIFEST);
  assert.equal(manifest.schema, COMPATIBILITY_MANIFEST_SCHEMA);
  assert.ok(Object.isFrozen(DEFAULT_COMPATIBILITY_MANIFEST));
  assert.ok(Object.isFrozen(manifest.browser));
});

test("the manifest key set is exact", () => {
  assert.deepEqual(Object.keys(DEFAULT_COMPATIBILITY_MANIFEST).sort(), [
    "auth_observation_schema",
    "browser",
    "cdp_protocol_version",
    "mode",
    "pro_model",
    "schema",
    "selector_observation_schema",
    "selector_proof_schema",
  ]);
  assert.throws(
    () =>
      parseCompatibilityManifest({ ...DEFAULT_COMPATIBILITY_MANIFEST, extra: 1 }),
    (error) => error instanceof OracleCanaryError && error.code === "manifest_invalid",
  );
  const short = { ...DEFAULT_COMPATIBILITY_MANIFEST };
  delete short.mode;
  assert.throws(() => parseCompatibilityManifest(short), OracleCanaryError);
});

test("every manifest field fails closed on a bad value", () => {
  const cases = [
    { schema: "other.v1" },
    { browser: { product: "Chrome", major: 141 } },
    { browser: { product: "Chrome", major: 0, policy: "exact_major" } },
    { browser: { product: "Chrome", major: 141, policy: "whatever" } },
    { browser: { product: "", major: 141, policy: "exact_major" } },
    { cdp_protocol_version: "1" },
    { cdp_protocol_version: 1.3 },
    { selector_observation_schema: "" },
    { auth_observation_schema: null },
    { mode: "turbo" },
    { pro_model: "gpt-5-5" },
    { pro_model: "GPT-5-5-PRO" },
  ];
  for (const overrides of cases) {
    assert.throws(
      () =>
        parseCompatibilityManifest({
          ...DEFAULT_COMPATIBILITY_MANIFEST,
          ...overrides,
        }),
      OracleCanaryError,
      JSON.stringify(overrides),
    );
  }
});

// ---------------------------------------------------------------------------
// Version parsing and browser drift
// ---------------------------------------------------------------------------

test("browser version strings parse into comparable parts", () => {
  assert.deepEqual(parseBrowserVersion("Chrome/150.0.7390.55"), {
    product: "Chrome",
    version: "150.0.7390.55",
    major: 150,
    minor: 0,
    build: 7390,
    patch: 55,
  });
  assert.equal(parseBrowserVersion("FakeChrome/1.0").major, 1);
  assert.equal(parseBrowserVersion("HeadlessChrome/151.0.0.0").product, "HeadlessChrome");
});

test("malformed version strings fail closed", () => {
  for (const value of ["", "Chrome", "141.0", "Chrome/", "/141", "Chrome/x.y", null, 141]) {
    assert.throws(
      () => parseBrowserVersion(value),
      (error) =>
        error instanceof OracleCanaryError && error.code === "browser_version_invalid",
      String(value),
    );
  }
});

test("a matching browser and protocol produce no drift", () => {
  const checks = browserChecks(parseCompatibilityManifest(DEFAULT_COMPATIBILITY_MANIFEST), {
    Browser: "Chrome/150.0.7390.55",
    "Protocol-Version": "1.3",
  });
  assert.deepEqual(
    checks.map((entry) => entry.status),
    ["pass", "pass", "pass"],
  );
});

test("product, version, and protocol drift are each detected and named", () => {
  const manifest = parseCompatibilityManifest(DEFAULT_COMPATIBILITY_MANIFEST);
  const product = browserChecks(manifest, {
    Browser: "Chromium/150.0.7390.55",
    "Protocol-Version": "1.3",
  });
  assert.equal(product[0].code, "browser_product_drift");

  const older = browserChecks(manifest, {
    Browser: "Chrome/149.0.0.0",
    "Protocol-Version": "1.3",
  });
  assert.equal(older[1].code, "browser_version_drift");

  const protocol = browserChecks(manifest, {
    Browser: "Chrome/150.0.7390.55",
    "Protocol-Version": "1.4",
  });
  assert.equal(protocol[2].code, "cdp_protocol_drift");
});

test("at_least_major accepts an upgrade while exact_major rejects it", () => {
  const version = { Browser: "Chrome/151.0.1.0", "Protocol-Version": "1.3" };
  const lenient = parseCompatibilityManifest(DEFAULT_COMPATIBILITY_MANIFEST);
  assert.equal(browserChecks(lenient, version)[1].status, "pass");
  const strict = parseCompatibilityManifest({
    ...DEFAULT_COMPATIBILITY_MANIFEST,
    browser: { product: "Chrome", major: 150, policy: "exact_major" },
  });
  assert.equal(browserChecks(strict, version)[1].status, "fail");
});

test("a missing or non-string Browser field fails closed", () => {
  const manifest = parseCompatibilityManifest(DEFAULT_COMPATIBILITY_MANIFEST);
  assert.throws(() => browserChecks(manifest, {}), OracleCanaryError);
  assert.throws(() => browserChecks(manifest, null), OracleCanaryError);
});

// ---------------------------------------------------------------------------
// Static checks — drift with no browser at all
// ---------------------------------------------------------------------------

test("static checks pass against the live contract schemas", () => {
  const checks = staticChecks(parseCompatibilityManifest(DEFAULT_COMPATIBILITY_MANIFEST));
  assert.equal(checks.length, 3);
  assert.ok(checks.every((entry) => entry.status === "pass"));
  assert.ok(checks.every((entry) => entry.scope === "static"));
});

test("an upstream schema bump is caught with no browser involved", () => {
  const stale = parseCompatibilityManifest({
    ...DEFAULT_COMPATIBILITY_MANIFEST,
    selector_proof_schema: "oracle-subagent.selector-proof.v0",
  });
  const checks = staticChecks(stale);
  const failed = checks.filter((entry) => entry.status === "fail");
  assert.equal(failed.length, 1);
  assert.equal(failed[0].check, "selector_proof_schema");
  assert.equal(failed[0].code, "contract_schema_drift");
});

// ---------------------------------------------------------------------------
// Loopback-only endpoint
// ---------------------------------------------------------------------------

test("literal loopback endpoints are accepted", () => {
  assert.deepEqual(parseLoopbackEndpoint("http://127.0.0.1:9222"), {
    origin: "http://127.0.0.1:9222",
    hostname: "127.0.0.1",
    port: 9222,
  });
  assert.equal(parseLoopbackEndpoint("http://[::1]:9222/").hostname, "[::1]");
});

test("anything that is not literal loopback is refused", () => {
  const cases = [
    ["http://localhost:9222", "endpoint_not_loopback"],
    ["http://oracle.example:9222", "endpoint_not_loopback"],
    ["http://0.0.0.0:9222", "endpoint_not_loopback"],
    ["http://192.0.2.1:9222", "endpoint_not_loopback"],
    ["https://127.0.0.1:9222", "endpoint_not_loopback"],
    ["ws://127.0.0.1:9222", "endpoint_not_loopback"],
    ["http://user:pass@127.0.0.1:9222", "endpoint_invalid"],
    ["http://127.0.0.1:80", "endpoint_invalid"],
    ["http://127.0.0.1", "endpoint_invalid"],
    ["http://127.0.0.1:9222/json", "endpoint_invalid"],
    ["", "endpoint_invalid"],
  ];
  for (const [value, code] of cases) {
    assert.throws(
      () => parseLoopbackEndpoint(value),
      (error) => error instanceof OracleCanaryError && error.code === code,
      value,
    );
  }
});

// ---------------------------------------------------------------------------
// Exact target binding
// ---------------------------------------------------------------------------

test("exactly one ChatGPT page target binds", () => {
  const target = selectExactChatGptTarget([
    { id: TARGET_ID, type: "page", url: "https://chatgpt.com/" },
    { id: "AAAAAAAAAAAAAAAA", type: "service_worker", url: "https://chatgpt.com/sw" },
    { id: "BBBBBBBBBBBBBBBB", type: "page", url: "https://example.com/" },
  ]);
  assert.equal(target.id, TARGET_ID);
});

test("zero and several ChatGPT targets are both refusals", () => {
  assert.throws(
    () => selectExactChatGptTarget([{ id: "AAAAAAAAAAAAAAAA", type: "page", url: "https://example.com/" }]),
    (error) => error.code === "target_absent",
  );
  assert.throws(
    () =>
      selectExactChatGptTarget([
        { id: TARGET_ID, type: "page", url: "https://chatgpt.com/" },
        { id: "AAAAAAAAAAAAAAAA", type: "page", url: "https://chatgpt.com/c/abcdefgh" },
      ]),
    (error) => error.code === "target_ambiguous",
    "picking the first would report on a tab nobody meant",
  );
});

test("a malformed target list fails closed", () => {
  assert.throws(() => selectExactChatGptTarget("nope"), OracleCanaryError);
  assert.throws(
    () => selectExactChatGptTarget(new Array(65).fill({ id: TARGET_ID, type: "page", url: "https://chatgpt.com/" })),
    OracleCanaryError,
  );
});

// ---------------------------------------------------------------------------
// Auth / Cloudflare / selector classification
// ---------------------------------------------------------------------------

test("a healthy page passes origin, cloudflare, auth, and composer", () => {
  const findings = classifyPageObservation(canaryObservation());
  assert.deepEqual(
    findings.map((entry) => [entry.check, entry.status]),
    [
      ["target_origin", "pass"],
      ["cloudflare", "pass"],
      ["auth", "pass"],
      ["composer_selectors", "pass"],
    ],
  );
});

test("a Cloudflare challenge is reported once and masks the readings it breaks", () => {
  // A challenge interstitial hides the composer and shows no login control, so
  // reporting auth and composer here would manufacture two more failures from
  // one cause — and send someone to re-authenticate a live session.
  const findings = classifyPageObservation(
    canaryObservation({
      title_class: "challenge",
      challenge_node_count: 1,
      composer_visible_count: 0,
      prompt_field_visible_count: 0,
    }),
  );
  const byCheck = Object.fromEntries(findings.map((entry) => [entry.check, entry]));
  assert.equal(byCheck.cloudflare.code, "cloudflare_challenge");
  assert.equal(byCheck.auth.status, "skipped");
  assert.equal(byCheck.auth.code, "masked_by_challenge");
  assert.equal(byCheck.composer_selectors.status, "skipped");
  assert.equal(findings.filter((entry) => entry.status === "fail").length, 1);
});

test("a challenge is detected from markup even when the title looks normal", () => {
  const findings = classifyPageObservation(canaryObservation({ challenge_node_count: 2 }));
  assert.equal(findings.find((entry) => entry.check === "cloudflare").status, "fail");
});

test("a lost session is reported as auth_lost", () => {
  const findings = classifyPageObservation(
    canaryObservation({ login_control_count: 1, composer_visible_count: 0, prompt_field_visible_count: 0 }),
  );
  const byCheck = Object.fromEntries(findings.map((entry) => [entry.check, entry]));
  assert.equal(byCheck.auth.code, "auth_lost");
  assert.equal(byCheck.composer_selectors.code, "composer_absent");
});

test("composer selector drift is distinguished from absence", () => {
  const absent = classifyPageObservation(
    canaryObservation({ composer_visible_count: 0, prompt_field_visible_count: 0 }),
  );
  assert.equal(
    absent.find((entry) => entry.check === "composer_selectors").code,
    "composer_absent",
  );
  const ambiguous = classifyPageObservation(canaryObservation({ composer_visible_count: 2 }));
  assert.equal(
    ambiguous.find((entry) => entry.check === "composer_selectors").code,
    "composer_ambiguous",
  );
});

test("an off-origin page is drift, not a silent pass", () => {
  const findings = classifyPageObservation(canaryObservation({ same_origin: false }));
  assert.equal(findings.find((entry) => entry.check === "target_origin").code, "origin_drift");
});

test("a malformed observation fails closed", () => {
  const cases = [
    { schema: "other.v1" },
    { observed_at: "not-a-date" },
    { target_id: "short" },
    { same_origin: "yes" },
    { path_class: "elsewhere" },
    { title_class: "weird" },
    { challenge_node_count: -1 },
    { login_control_count: 1.5 },
  ];
  for (const overrides of cases) {
    assert.throws(
      () => classifyPageObservation(canaryObservation(overrides)),
      (error) =>
        error instanceof OracleCanaryError &&
        error.code === "canary_observation_invalid",
      JSON.stringify(overrides),
    );
  }
  assert.throws(
    () => classifyPageObservation({ ...canaryObservation(), extra: 1 }),
    OracleCanaryError,
  );
});

// ---------------------------------------------------------------------------
// The page probe never carries page text out
// ---------------------------------------------------------------------------

function fakeElement({ text = "", visible = true } = {}) {
  return {
    innerText: text,
    textContent: text,
    getBoundingClientRect() {
      return visible ? { width: 120, height: 40 } : { width: 0, height: 0 };
    },
  };
}

function runProbe({ title, pathname = "/", origin = "https://chatgpt.com", nodes = {} }) {
  const context = {
    document: {
      title,
      querySelectorAll(selector) {
        for (const [key, value] of Object.entries(nodes)) {
          if (selector.includes(key)) return value;
        }
        return [];
      },
    },
    location: { origin, pathname },
    Date,
    Array,
    String,
    RegExp,
  };
  return runInNewContext(canaryPageProbeExpression(TARGET_ID), context);
}

test("the probe returns classifications only — never the page title or URL", () => {
  const secret = "Acquisition memo for Q3 — do not share";
  const observation = runProbe({
    title: secret,
    pathname: "/c/6f2a1b90aaaa",
    nodes: {
      "data-testid='composer'": [fakeElement()],
      "#prompt-textarea": [fakeElement()],
    },
  });
  const encoded = JSON.stringify(observation);
  assert.ok(!encoded.includes(secret), "conversation title must never leave the page");
  assert.ok(!encoded.includes("6f2a1b90aaaa"), "conversation id must never leave the page");
  assert.deepEqual(Object.keys(observation).sort(), [
    "challenge_node_count",
    "composer_visible_count",
    "login_control_count",
    "observed_at",
    "path_class",
    "prompt_field_visible_count",
    "same_origin",
    "schema",
    "target_id",
    "title_class",
  ]);
  assert.equal(observation.path_class, "conversation");
  assert.equal(observation.title_class, "normal");
});

test("the probe classifies a Cloudflare interstitial title", () => {
  const observation = runProbe({ title: "Just a moment..." });
  assert.equal(observation.title_class, "challenge");
  assert.equal(observation.composer_visible_count, 0);
  // The classification round-trips through the public classifier.
  const findings = classifyPageObservation({
    ...observation,
    observed_at: OBSERVED_AT,
  });
  assert.equal(findings.find((entry) => entry.check === "cloudflare").status, "fail");
});

test("the probe counts only visible login controls", () => {
  const observation = runProbe({
    title: "ChatGPT",
    nodes: {
      "a,button,[role='button']": [
        fakeElement({ text: "Log in" }),
        fakeElement({ text: "Log in", visible: false }),
        fakeElement({ text: "New chat" }),
      ],
    },
  });
  assert.equal(observation.login_control_count, 1);
});

// ---------------------------------------------------------------------------
// The canary cannot send
// ---------------------------------------------------------------------------

test("the CDP allowlist is exactly one read method", () => {
  assert.deepEqual(CDP_METHOD_ALLOWLIST, ["Runtime.evaluate"]);
  assert.ok(Object.isFrozen(CDP_METHOD_ALLOWLIST));
});

test("asking the canary to submit is a refusal, not a mode", async () => {
  await assert.rejects(
    () => runCanary({ submit: true }),
    (error) => error instanceof OracleCanaryError && error.code === "submit_forbidden",
  );
});

test("a live run issues only Runtime.evaluate and never raises the window", async () => {
  await withFakeCdp(liveScenario(), async (fake) => {
    const report = await runCanary({
      manifest: fakeManifest(),
      endpoint: fake.base_url,
      now: NOW,
    });
    assert.equal(report.status, "pass");
    assert.equal(report.live_proved, true);
    const methods = new Set(fake.calls.map((call) => call.method));
    assert.deepEqual([...methods], ["Runtime.evaluate"]);
    for (const forbidden of [
      "Target.activateTarget",
      "Target.createTarget",
      "Browser.setWindowBounds",
      "Browser.getWindowForTarget",
    ]) {
      assert.ok(!methods.has(forbidden), forbidden);
    }
  });
});

// ---------------------------------------------------------------------------
// Live path over the fake CDP server
// ---------------------------------------------------------------------------

test("a compatible host reports pass with every live check green", async () => {
  await withFakeCdp(liveScenario(), async (fake) => {
    const report = await runCanary({
      manifest: fakeManifest(),
      endpoint: fake.base_url,
      now: NOW,
    });
    assert.equal(report.schema, CANARY_REPORT_SCHEMA);
    assert.equal(report.submit, false);
    assert.equal(report.endpoint, fake.base_url);
    assert.deepEqual(report.drift, []);
    assert.deepEqual(report.blockers, []);
    assert.ok(report.checks.every((entry) => entry.status === "pass"));
    assert.equal(findCheck(report, "target_binding").detail, TARGET_ID);
  });
});

test("a Chrome upgrade past the pin is reported as version drift", async () => {
  await withFakeCdp(liveScenario(), async (fake) => {
    const report = await runCanary({
      manifest: fakeManifest({
        browser: { product: "FakeChrome", major: 2, policy: "at_least_major" },
      }),
      endpoint: fake.base_url,
      now: NOW,
    });
    assert.equal(report.status, "drift");
    assert.ok(report.drift.includes("browser_version_drift"));
    // Everything downstream still ran: drift in one axis must not hide another.
    assert.equal(findCheck(report, "selector_contract").status, "pass");
    assert.equal(findCheck(report, "cloudflare").status, "pass");
  });
});

test("model ambiguity fails the selector contract with its own code", async () => {
  await withFakeCdp(
    liveScenario({ selector: selectorObservation({ model_selection: "ambiguous" }) }),
    async (fake) => {
      const report = await runCanary({
        manifest: fakeManifest(),
        endpoint: fake.base_url,
        now: NOW,
      });
      assert.equal(report.status, "drift");
      assert.equal(findCheck(report, "selector_contract").code, "model_not_pro");
    },
  );
});

test("tool ambiguity fails closed rather than passing a Pro run", async () => {
  await withFakeCdp(
    liveScenario({ selector: selectorObservation({ tool_selection: "ambiguous", active_tool_count: 1 }) }),
    async (fake) => {
      const report = await runCanary({
        manifest: fakeManifest(),
        endpoint: fake.base_url,
        now: NOW,
      });
      assert.equal(findCheck(report, "selector_contract").code, "tool_not_exact");
    },
  );
});

test("a stale selector observation is drift, not a pass", async () => {
  await withFakeCdp(
    liveScenario({ selector: selectorObservation({ observed_at: "2026-07-28T07:00:00.000Z" }) }),
    async (fake) => {
      const report = await runCanary({
        manifest: fakeManifest(),
        endpoint: fake.base_url,
        now: NOW,
      });
      assert.equal(findCheck(report, "selector_contract").code, "observation_stale");
    },
  );
});

test("a Cloudflare challenge on the live page surfaces as drift", async () => {
  await withFakeCdp(
    liveScenario({
      canary: canaryObservation({
        title_class: "challenge",
        challenge_node_count: 1,
        composer_visible_count: 0,
        prompt_field_visible_count: 0,
      }),
    }),
    async (fake) => {
      const report = await runCanary({
        manifest: fakeManifest(),
        endpoint: fake.base_url,
        now: NOW,
      });
      assert.equal(report.status, "drift");
      assert.deepEqual(report.drift, ["cloudflare_challenge"]);
      assert.equal(findCheck(report, "auth").status, "skipped");
    },
  );
});

test("two ChatGPT tabs bind to neither and skip the page checks", async () => {
  await withFakeCdp(
    {
      targets: [
        { id: TARGET_ID, type: "page", url: "https://chatgpt.com/", title: "a" },
        { id: "ABCDEF0123456780", type: "page", url: "https://chatgpt.com/", title: "b" },
      ],
    },
    async (fake) => {
      const report = await runCanary({
        manifest: fakeManifest(),
        endpoint: fake.base_url,
        now: NOW,
      });
      assert.equal(report.status, "drift");
      assert.equal(findCheck(report, "target_binding").code, "target_ambiguous");
      assert.equal(findCheck(report, "selector_contract").status, "skipped");
      assert.equal(report.live_proved, false);
      assert.equal(fake.calls.length, 0, "no page was evaluated");
    },
  );
});

test("an unreachable endpoint is degraded with a named blocker, never a pass", async () => {
  const fake = await startFakeCdp(liveScenario());
  const url = fake.base_url;
  await fake.close();
  const report = await runCanary({
    manifest: fakeManifest(),
    endpoint: url,
    now: NOW,
  });
  assert.equal(report.status, "degraded");
  assert.equal(report.live_proved, false);
  assert.equal(report.blockers[0].blocker, "cdp_unreachable");
  assert.ok(report.checks.some((entry) => entry.code === "cdp_unreachable"));
});

test("with no endpoint the run is degraded and says so", async () => {
  const report = await runCanary({ now: NOW });
  assert.equal(report.status, "degraded");
  assert.equal(report.live_proved, false);
  assert.equal(report.endpoint, null);
  assert.equal(report.blockers[0].blocker, "endpoint_unset");
  assert.ok(
    report.checks
      .filter((entry) => entry.scope === "static")
      .every((entry) => entry.status === "pass"),
  );
});

test("static drift is caught even with no browser reachable", async () => {
  const report = await runCanary({
    manifest: { ...DEFAULT_COMPATIBILITY_MANIFEST, auth_observation_schema: "stale.v0" },
    now: NOW,
  });
  assert.equal(report.status, "drift");
  assert.deepEqual(report.drift, ["contract_schema_drift"]);
});

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

test("--no-submit is accepted and there is no --submit", () => {
  const options = parseArguments(["--no-submit", "--json"]);
  assert.equal(options.json, true);
  assert.throws(
    () => parseArguments(["--submit"]),
    (error) => error instanceof OracleCanaryError && error.code === "usage_invalid",
  );
  assert.throws(() => parseArguments(["--wat"]), OracleCanaryError);
});

test("endpoint and manifest flags parse in both forms", () => {
  assert.equal(
    parseArguments(["--endpoint", "http://127.0.0.1:9222"]).endpoint,
    "http://127.0.0.1:9222",
  );
  assert.equal(
    parseArguments(["--endpoint=http://127.0.0.1:9222"]).endpoint,
    "http://127.0.0.1:9222",
  );
  assert.equal(parseArguments(["--manifest=/tmp/m.json"]).manifestPath, "/tmp/m.json");
  assert.equal(parseArguments(["--require-live"]).requireLive, true);
});

function capture() {
  const written = [];
  // Never replace process.stdout.write: doing so also swallows the test
  // runner's own TAP output and silently corrupts its pass/fail counts.
  return { written, write: (text) => void written.push(String(text)) };
}

test("the documented invocation exits 0 and emits one JSON report", async () => {
  const sink = capture();
  const code = await main(["--no-submit", "--json"], { write: sink.write });
  assert.equal(code, EXIT_PASS);
  assert.equal(sink.written.length, 1);
  const report = JSON.parse(sink.written[0]);
  assert.equal(report.schema, CANARY_REPORT_SCHEMA);
  assert.equal(report.submit, false);
  assert.equal(report.live_proved, false);
});

test("--require-live refuses to call an unobserved host green", async () => {
  const sink = capture();
  const code = await main(["--no-submit", "--json", "--require-live"], {
    write: sink.write,
  });
  assert.equal(code, EXIT_UNAVAILABLE);
});

test("a non-loopback endpoint is a usage refusal, not a silent skip", async () => {
  const sink = capture();
  const code = await main(["--no-submit", "--endpoint", "http://localhost:9222"], {
    write: sink.write,
  });
  assert.equal(code, EXIT_USAGE);
  assert.equal(JSON.parse(sink.written[0]).code, "endpoint_not_loopback");
});

test("an unreadable manifest path is a usage error", async () => {
  const sink = capture();
  const code = await main(["--manifest", "/nonexistent/manifest.json"], {
    write: sink.write,
  });
  assert.equal(code, EXIT_USAGE);
  assert.equal(JSON.parse(sink.written[0]).code, "manifest_unreadable");
});

test("a drifting live host exits EXIT_DRIFT through the CLI", async () => {
  await withFakeCdp(liveScenario(), async (fake) => {
    const sink = capture();
    // The default manifest pins Chrome; the fake server serves FakeChrome.
    const code = await main(
      ["--no-submit", "--json", "--endpoint", fake.base_url],
      { write: sink.write },
    );
    assert.equal(code, EXIT_DRIFT);
    assert.ok(
      JSON.parse(sink.written[0]).drift.includes("browser_product_drift"),
    );
  });
});

test("the human-readable form is one compact line", async () => {
  const sink = capture();
  await main(["--no-submit"], { write: sink.write });
  assert.equal(sink.written.length, 1);
  assert.match(sink.written[0], /^degraded live_proved=false drift=none\n$/);
});
