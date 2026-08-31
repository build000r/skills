import assert from "node:assert/strict";
import test from "node:test";

import {
  CDP_PORT_MAX,
  CDP_PORT_MIN,
  CdpPortError,
  DEFAULT_CDP_PORT,
  parseCdpPort,
  resolveCdpPort,
} from "../assets/scripts/oracle-cdp-port.mjs";

/* ------------------------------------------------------------------ *
 * Helpers: injected readers keyed by path so one resolver call can see
 * distinct config and receipt files without touching the filesystem.
 * ------------------------------------------------------------------ */

function readerFor(files) {
  const reads = [];
  const impl = (path) => {
    reads.push(path);
    if (!(path in files)) {
      const error = new Error(`ENOENT: ${path}`);
      error.code = "ENOENT";
      throw error;
    }
    return files[path];
  };
  return { impl, reads };
}

const CONFIG = "/fake/config.json";
const RECEIPT = "/fake/browser.json";

function resolveWith({ files = {}, ...options } = {}) {
  const { impl, reads } = readerFor(files);
  const port = resolveCdpPort({
    env: {},
    readFileSyncImpl: impl,
    ...options,
  });
  return { port, reads };
}

/* ------------------------------------------------------------------ *
 * parseCdpPort — the validity contract
 * ------------------------------------------------------------------ */

test("bounds are 1..65535 with 9222 as the default", () => {
  assert.equal(CDP_PORT_MIN, 1);
  assert.equal(CDP_PORT_MAX, 65535);
  assert.equal(DEFAULT_CDP_PORT, 9222);
});

test("valid ports: integral numbers and trimmed decimal strings in range", () => {
  assert.deepEqual(parseCdpPort(9222), { state: "valid", port: 9222 });
  assert.deepEqual(parseCdpPort(1), { state: "valid", port: 1 });
  assert.deepEqual(parseCdpPort(65535), { state: "valid", port: 65535 });
  assert.deepEqual(parseCdpPort("19222"), { state: "valid", port: 19222 });
  assert.deepEqual(parseCdpPort(" 9222 \n"), { state: "valid", port: 9222 });
});

test("unset: undefined, null, empty and whitespace-only strings", () => {
  for (const value of [undefined, null, "", "   ", "\t\n"]) {
    assert.deepEqual(parseCdpPort(value), { state: "unset" }, String(value));
  }
});

test("invalid: non-numeric, out of range, fractional, signed, wrong type", () => {
  for (const value of [
    "abc",
    "9222x",
    "-1",
    "+9222",
    "12.5",
    "1e3",
    "0x20",
    "0",
    "65536",
    "70000",
    0,
    -1,
    65536,
    3.5,
    Number.NaN,
    Number.POSITIVE_INFINITY,
    true,
    false,
    {},
    [9222],
  ]) {
    assert.deepEqual(parseCdpPort(value), { state: "invalid" }, String(value));
  }
});

/* ------------------------------------------------------------------ *
 * Level 1 — explicit argument
 * ------------------------------------------------------------------ */

test("explicit argument wins over config, env, and receipt", () => {
  const { port } = resolveWith({
    explicit: "18000",
    useConfig: true,
    configPath: CONFIG,
    env: { ORACLE_CDP_PORT: "9333" },
    receiptPath: RECEIPT,
    files: {
      [CONFIG]: '{"cdp_port": 19222}',
      [RECEIPT]: '{"port": 17000}',
    },
  });
  assert.equal(port, 18000);
});

test("explicit accepts a number as well as a string", () => {
  assert.equal(resolveCdpPort({ explicit: 18001, env: {} }), 18001);
});

test("invalid explicit fails (never falls through)", () => {
  for (const explicit of ["abc", "0", "70000", "-5", "12.5", 0, 65536, 3.5]) {
    assert.throws(
      () => resolveCdpPort({ explicit, env: { ORACLE_CDP_PORT: "9333" } }),
      (error) =>
        error instanceof CdpPortError &&
        error.code === "invalid_cdp_port" &&
        /explicit argument/.test(error.message),
      String(explicit),
    );
  }
});

test("blank explicit counts as unset and falls through", () => {
  assert.equal(
    resolveCdpPort({ explicit: "", env: { ORACLE_CDP_PORT: "9333" } }),
    9333,
  );
  assert.equal(resolveCdpPort({ explicit: "  ", env: {} }), DEFAULT_CDP_PORT);
});

/* ------------------------------------------------------------------ *
 * Level 2 — config cdp_port / cdpPort
 * ------------------------------------------------------------------ */

test("config beats env: host config is the pin", () => {
  const { port } = resolveWith({
    useConfig: true,
    configPath: CONFIG,
    env: { ORACLE_CDP_PORT: "9222" },
    files: { [CONFIG]: '{"cdp_port": 19222}' },
  });
  assert.equal(port, 19222);
});

test("config accepts the cdpPort spelling and digit strings", () => {
  assert.equal(
    resolveWith({
      useConfig: true,
      configPath: CONFIG,
      files: { [CONFIG]: '{"cdpPort": 19223}' },
    }).port,
    19223,
  );
  assert.equal(
    resolveWith({
      useConfig: true,
      configPath: CONFIG,
      files: { [CONFIG]: '{"cdp_port": "19224"}' },
    }).port,
    19224,
  );
});

test("invalid config values fall through to env, then default", () => {
  for (const body of [
    '{"cdp_port": "abc"}',
    '{"cdp_port": 70000}',
    '{"cdp_port": 0}',
    '{"cdp_port": 19222.5}',
    '{"cdp_port": true}',
    '{"cdp_port": ""}',
    '{"other": 1}',
    "[19222]",
    "not json",
  ]) {
    assert.equal(
      resolveWith({
        useConfig: true,
        configPath: CONFIG,
        env: { ORACLE_CDP_PORT: "9333" },
        files: { [CONFIG]: body },
      }).port,
      9333,
      body,
    );
    assert.equal(
      resolveWith({
        useConfig: true,
        configPath: CONFIG,
        files: { [CONFIG]: body },
      }).port,
      DEFAULT_CDP_PORT,
      body,
    );
  }
});

test("a missing/unreadable config file falls through silently", () => {
  const { port } = resolveWith({
    useConfig: true,
    configPath: CONFIG,
    env: { ORACLE_CDP_PORT: "9333" },
    files: {},
  });
  assert.equal(port, 9333);
});

test("config is not consulted for a plain env object unless opted in", () => {
  const { impl, reads } = readerFor({ [CONFIG]: '{"cdp_port": 19222}' });
  const port = resolveCdpPort({
    env: { ORACLE_CDP_PORT: "9333" },
    configPath: CONFIG,
    readFileSyncImpl: impl,
  });
  assert.equal(port, 9333);
  assert.deepEqual(reads, [], "hermetic env must never read host config");
});

/* ------------------------------------------------------------------ *
 * Level 3 — ORACLE_CDP_PORT env
 * ------------------------------------------------------------------ */

test("env supplies the port when explicit and config are absent", () => {
  assert.equal(resolveCdpPort({ env: { ORACLE_CDP_PORT: "9333" } }), 9333);
  assert.equal(resolveCdpPort({ env: { ORACLE_CDP_PORT: " 9333 " } }), 9333);
});

test("invalid env fails (never a silent downgrade to 9222)", () => {
  for (const value of ["abc", "0", "-1", "70000", "12.5", "9222x"]) {
    assert.throws(
      () => resolveCdpPort({ env: { ORACLE_CDP_PORT: value } }),
      (error) =>
        error instanceof CdpPortError &&
        error.source === "ORACLE_CDP_PORT" &&
        /ORACLE_CDP_PORT/.test(error.message),
      value,
    );
  }
});

test("blank env counts as unset and falls through to the default", () => {
  assert.equal(resolveCdpPort({ env: { ORACLE_CDP_PORT: "" } }), DEFAULT_CDP_PORT);
  assert.equal(resolveCdpPort({ env: { ORACLE_CDP_PORT: "  " } }), DEFAULT_CDP_PORT);
  assert.equal(resolveCdpPort({ env: {} }), DEFAULT_CDP_PORT);
});

/* ------------------------------------------------------------------ *
 * Level 4 — browser receipt (heal-only opt-in)
 * ------------------------------------------------------------------ */

test("a validated receipt supplies the port when higher levels are unset", () => {
  const { port } = resolveWith({
    receiptPath: RECEIPT,
    files: { [RECEIPT]: '{"port": 17000, "target_url": "https://chatgpt.com/"}' },
  });
  assert.equal(port, 17000);
});

test("the receipt level does not exist unless receiptPath opts in", () => {
  const { impl, reads } = readerFor({ [RECEIPT]: '{"port": 17000}' });
  const port = resolveCdpPort({ env: {}, readFileSyncImpl: impl });
  assert.equal(port, DEFAULT_CDP_PORT);
  assert.deepEqual(reads, [], "no receiptPath means no receipt read");
});

test("env beats the receipt; config beats both", () => {
  assert.equal(
    resolveWith({
      env: { ORACLE_CDP_PORT: "9333" },
      receiptPath: RECEIPT,
      files: { [RECEIPT]: '{"port": 17000}' },
    }).port,
    9333,
  );
  assert.equal(
    resolveWith({
      useConfig: true,
      configPath: CONFIG,
      receiptPath: RECEIPT,
      files: { [CONFIG]: '{"cdp_port": 19222}', [RECEIPT]: '{"port": 17000}' },
    }).port,
    19222,
  );
});

test("invalid or unreadable receipts fall through to the default", () => {
  for (const body of [
    '{"port": "abc"}',
    '{"port": 0}',
    '{"port": 70000}',
    '{"port": 17000.5}',
    '{"port": ""}',
    "{}",
    "not json",
  ]) {
    assert.equal(
      resolveWith({ receiptPath: RECEIPT, files: { [RECEIPT]: body } }).port,
      DEFAULT_CDP_PORT,
      body,
    );
  }
  assert.equal(
    resolveWith({ receiptPath: RECEIPT, files: {} }).port,
    DEFAULT_CDP_PORT,
  );
});

/* ------------------------------------------------------------------ *
 * Full-chain precedence
 * ------------------------------------------------------------------ */

test("each level falls through in order when the one above is unset or (config/receipt) invalid", () => {
  const files = {
    [CONFIG]: '{"cdp_port": "not-a-port"}',
    [RECEIPT]: '{"port": 17000}',
  };
  // explicit unset, config invalid, env unset -> receipt
  assert.equal(
    resolveWith({ useConfig: true, configPath: CONFIG, receiptPath: RECEIPT, files }).port,
    17000,
  );
  // ... and with the receipt also invalid -> default
  assert.equal(
    resolveWith({
      useConfig: true,
      configPath: CONFIG,
      receiptPath: RECEIPT,
      files: { ...files, [RECEIPT]: "{}" },
    }).port,
    DEFAULT_CDP_PORT,
  );
});
