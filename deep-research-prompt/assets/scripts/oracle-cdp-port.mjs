#!/usr/bin/env node
/**
 * oracle-cdp-port.mjs — THE canonical loopback CDP port resolution contract.
 *
 * Every maintained Oracle entrypoint resolves the ChatGPT CDP port through
 * this matrix. The three .mjs entrypoints import this module directly; the two
 * shell entrypoints (launch-chatgpt-cdp.sh, oracle-xvfb-host.sh) cannot import
 * an ES module, so they carry a native-shell PARITY implementation of the same
 * matrix with a comment pointing back here. Any change to this table must be
 * mirrored in both scripts.
 *
 * PRECEDENCE MATRIX (first level that yields a valid port wins; a level is
 * only examined when every higher level was unset):
 *
 *   # | source                                        | valid      | invalid       | unset/blank
 *  ---+-----------------------------------------------+------------+---------------+------------
 *   1 | explicit argument (--port / function arg)     | wins       | FAIL          | next level
 *   2 | config cdp_port / cdpPort                     | wins       | fall through  | next level
 *     |   (ORACLE_CONFIG_PATH, default                |            |               |
 *     |    ~/.oracle/config.json)                     |            |               |
 *   3 | ORACLE_CDP_PORT environment variable          | wins       | FAIL          | next level
 *   4 | validated browser receipt `port`              | wins       | fall through  | next level
 *     |   (HEAL-ONLY: examined only when the caller   |            |               |
 *     |    opts in via `receiptPath`;                 |            |               |
 *     |    oracle-session-heal is the only caller)    |            |               |
 *   5 | default                                       | 9222       | —             | —
 *
 * VALIDITY: an integer in 1..65535. Strings must be decimal digits after
 * trimming surrounding whitespace ("19222", " 9222 "); numbers must be
 * integral. Anything else — non-numeric text, out-of-range values, negatives,
 * fractions, booleans, objects — is invalid. A blank/whitespace-only string
 * (and undefined/null) counts as UNSET, not invalid.
 *
 * FAIL vs FALL THROUGH: explicit and env values are operator-asserted for
 * THIS invocation, so an invalid one fails closed (CdpPortError) instead of
 * silently talking to a different browser on 9222. Config and receipt are
 * ambient state files that may be absent, stale, or malformed, so an invalid
 * one falls through to the next level. Unreadable/unparseable config or
 * receipt files also fall through.
 *
 * Rationale for config-over-env: host config is the pin (e.g. cdp_port 19222
 * on skillbox-portfolio-devbox, where 9222 is owned by tailscaled) and must
 * beat ambient overlay env that still ships ORACLE_CDP_PORT=9222.
 */

import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import process from "node:process";

export const DEFAULT_CDP_PORT = 9222;
export const CDP_PORT_MIN = 1;
export const CDP_PORT_MAX = 65535;
export const DEFAULT_CONFIG_PATH = join(homedir(), ".oracle", "config.json");

export class CdpPortError extends Error {
  constructor(source, value) {
    super(
      `invalid CDP port from ${source}: ${JSON.stringify(value)} ` +
        `(need an integer between ${CDP_PORT_MIN} and ${CDP_PORT_MAX})`,
    );
    this.name = "CdpPortError";
    this.code = "invalid_cdp_port";
    this.source = source;
    this.value = value;
  }
}

/**
 * Classify one candidate value against the validity contract above.
 * Pure. Returns { state: "unset" } | { state: "valid", port } |
 * { state: "invalid" }.
 */
export function parseCdpPort(value) {
  if (value === undefined || value === null) return { state: "unset" };
  if (typeof value === "number") {
    if (
      Number.isInteger(value) &&
      value >= CDP_PORT_MIN &&
      value <= CDP_PORT_MAX
    ) {
      return { state: "valid", port: value };
    }
    return { state: "invalid" };
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed === "") return { state: "unset" };
    if (!/^[0-9]+$/.test(trimmed)) return { state: "invalid" };
    const port = Number(trimmed);
    if (port >= CDP_PORT_MIN && port <= CDP_PORT_MAX) {
      return { state: "valid", port };
    }
    return { state: "invalid" };
  }
  return { state: "invalid" };
}

/**
 * Resolve the loopback CDP port per the precedence matrix in the header.
 *
 * @param {object} [options]
 * @param {number|string} [options.explicit]  level 1 — CLI --port / caller arg
 * @param {object} [options.env]              environment (default process.env)
 * @param {boolean} [options.useConfig]       level 2 gate; defaults to true
 *   only when `env` IS `process.env`, so pure unit tests that pass `{}` never
 *   read host config
 * @param {string} [options.configPath]       config override (else
 *   env.ORACLE_CONFIG_PATH, else ~/.oracle/config.json)
 * @param {Function} [options.readFileSyncImpl] injected reader for tests
 * @param {string} [options.receiptPath]      level 4 opt-in — path to a
 *   browser receipt (browser.json). HEAL-ONLY: pass it only where healing
 *   must reach the browser the last launch actually bound.
 * @returns {number} the resolved port
 * @throws {CdpPortError} on an invalid explicit or env value (fail-closed)
 */
export function resolveCdpPort({
  explicit,
  env = process.env,
  useConfig,
  configPath,
  readFileSyncImpl = readFileSync,
  receiptPath,
} = {}) {
  // 1. explicit argument — invalid fails, never falls through.
  const fromExplicit = parseCdpPort(explicit);
  if (fromExplicit.state === "valid") return fromExplicit.port;
  if (fromExplicit.state === "invalid") {
    throw new CdpPortError("explicit argument", explicit);
  }

  // 2. config cdp_port / cdpPort — missing/unreadable/invalid falls through.
  const readConfig = useConfig ?? Object.is(env, process.env);
  if (readConfig) {
    const path = configPath || env?.ORACLE_CONFIG_PATH || DEFAULT_CONFIG_PATH;
    try {
      const data = JSON.parse(readFileSyncImpl(path, "utf8"));
      if (data && typeof data === "object" && !Array.isArray(data)) {
        const fromConfig = parseCdpPort(data.cdp_port ?? data.cdpPort);
        if (fromConfig.state === "valid") return fromConfig.port;
      }
    } catch {
      // fall through
    }
  }

  // 3. ORACLE_CDP_PORT env — blank counts as unset; set-but-invalid fails.
  const rawEnv = env?.ORACLE_CDP_PORT;
  const fromEnv = parseCdpPort(rawEnv);
  if (fromEnv.state === "valid") return fromEnv.port;
  if (fromEnv.state === "invalid") {
    throw new CdpPortError("ORACLE_CDP_PORT", rawEnv);
  }

  // 4. browser receipt — heal-only opt-in; invalid/unreadable falls through.
  if (receiptPath) {
    try {
      const receipt = JSON.parse(readFileSyncImpl(receiptPath, "utf8"));
      if (receipt && typeof receipt === "object" && !Array.isArray(receipt)) {
        const fromReceipt = parseCdpPort(receipt.port);
        if (fromReceipt.state === "valid") return fromReceipt.port;
      }
    } catch {
      // fall through
    }
  }

  // 5. default.
  return DEFAULT_CDP_PORT;
}
