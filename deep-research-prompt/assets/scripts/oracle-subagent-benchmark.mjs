// Reusable benchmark harness for the Oracle latency and resource SLO.
//
// `references/oracle-slo.md` records one live measurement, by hand. That is
// enough to state a verdict once and not enough to state whether anything
// improved: the next measurement has to be taken the same way, summarized with
// the same arithmetic, and compared field for field, or the two numbers are not
// comparable and "we made it faster" is an opinion.
//
// This module is that fixed procedure. It turns recorded samples into a
// versioned, redacted receipt whose digest covers every field, so two runs are
// either byte-identical or provably different.
//
// It cannot invoke the Oracle. That is structural, not a promise:
//
//   * the module imports only `node:crypto`, `node:fs`, `node:path`, and
//     `node:url` — pinned in `MODULE_IMPORT_ALLOWLIST` and asserted against this
//     file's own source by the test suite. There is no `node:child_process`, no
//     `node:net`, no `node:http`, and no import of any `oracle-*` module, so
//     there is no code path that starts a service, opens a socket, reads a
//     credential, or submits a prompt;
//   * measurement enters through injected probes (`collectSamples`) or a
//     recorded sample file (`main`). The harness times what it is handed;
//   * the CLI has no live mode at all. `--live` is refused with
//     `live_collection_unavailable` rather than quietly wiring one up.
//
// It also never carries measurement context out. A benchmark run knows the
// prompt it sent, the profile it used, and the PID it watched; none of those are
// receipt fields. `assertReceiptSafe` inverts the usual test the way
// `oracle-subagent-canary.mjs` does — nothing may appear in a receipt that is
// not in this module's closed vocabulary, so a leaked prompt, path, cookie, or
// token matches nothing and cannot be emitted.

import { createHash } from "node:crypto";
import { realpathSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

export const BENCHMARK_SAMPLES_SCHEMA = "oracle-subagent.benchmark-samples.v1";
export const BENCHMARK_RECEIPT_SCHEMA = "oracle-subagent.benchmark-receipt.v1";
export const BENCHMARK_SLO_SCHEMA = "oracle-subagent.benchmark-slo.v1";

/**
 * Every module this file may import, pinned so the "cannot invoke the Oracle"
 * claim is auditable rather than asserted. The test suite parses this file's
 * source — static and dynamic forms both, since a dynamic `import()` is exactly
 * where an unwanted reach would hide — and fails on anything not listed here.
 */
export const MODULE_IMPORT_ALLOWLIST = Object.freeze([
  "node:crypto",
  "node:fs",
  "node:fs/promises",
  "node:path",
  "node:url",
]);

export const PHASES = Object.freeze(["cold", "warm"]);
export const OUTCOMES = Object.freeze(["ok", "error", "aborted"]);
export const COMPARATORS = Object.freeze(["lt", "lte", "gte", "eq"]);
export const VERDICTS = Object.freeze([
  "pass",
  "fail",
  "not_exercised",
  "no_samples",
]);

export const EXIT_PASS = 0;
export const EXIT_FAIL = 1;
export const EXIT_USAGE = 2;
export const EXIT_INCOMPLETE = 3;

const RUN_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$/;
const MODEL_PATTERN = /^[a-z0-9]+(?:[.-][a-z0-9]+)*$/;
const GATE_PATTERN = /^[a-z][a-z0-9_]{2,63}$/;
const CODE_PATTERN = /^[a-z][a-z0-9_]{2,63}$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;

// Mirrors `oracle-subagent-artifacts.mjs`. Duplicated rather than imported:
// importing it would drag the whole artifact/state stack — and its filesystem
// reach — into a module whose entire safety argument is its tiny import list.
const SENSITIVE_LOG_PATTERN =
  /(?:authorization|bearer|cookie|password|prompt|secret|session[_-]?token|token|https?:\/\/)/i;
const CREDENTIAL_SHAPE_PATTERN =
  /(?:sk-(?:proj-)?[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{12,}|xapp-[A-Za-z0-9-]{12,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})/i;

const MAX_SAMPLES = 1_000;
const MAX_DURATION_MS = 3_600_000;
const MAX_RSS_BYTES = 1_099_511_627_776; // 1 TiB; a larger reading is a unit bug
const MAX_PID = 4_194_304; // Linux pid_max ceiling
const MIB = 1_048_576;

/**
 * The shipped release contract, transcribed from `references/oracle-slo.md`.
 *
 * `final_dom_to_output_p95_ms` is declared and `applicable: false`: the
 * production ask lane returns over HTTPS and has no final DOM, so the gate is
 * reported `not_exercised`. Deleting it would quietly shrink the contract to
 * whatever this lane happens to measure.
 */
export const DEFAULT_SLO = Object.freeze({
  schema: BENCHMARK_SLO_SCHEMA,
  version: 1,
  cold_p95_ms_max: 12_000,
  warm_p95_ms_max: 4_000,
  final_dom_to_output_p95_ms: Object.freeze({ max: 5_000, applicable: false }),
  warm_successful_runs_min: 20,
  browser_pids_exact: 1,
  max_rss_growth_bytes_max: 100 * MIB,
});

export class OracleBenchmarkError extends Error {
  constructor(code) {
    super("oracle benchmark: rejected");
    this.name = "OracleBenchmarkError";
    this.code = code;
  }
}

function reject(code) {
  throw new OracleBenchmarkError(code);
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

function requireString(value, pattern, code) {
  if (typeof value !== "string" || !pattern.test(value)) reject(code);
  if (SENSITIVE_LOG_PATTERN.test(value) || CREDENTIAL_SHAPE_PATTERN.test(value)) {
    reject(code);
  }
  return value;
}

function requireInteger(value, minimum, maximum, code) {
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    reject(code);
  }
  return value;
}

/**
 * Canonical RFC3339, not merely parseable. `Date.parse` accepts a startling
 * range of inputs, and a receipt whose timestamps round-trip differently on two
 * machines is a receipt whose digest is not reproducible.
 */
function requireTimestamp(value, code) {
  if (typeof value !== "string") reject(code);
  const milliseconds = Date.parse(value);
  if (!Number.isFinite(milliseconds)) reject(code);
  if (new Date(milliseconds).toISOString() !== value) reject(code);
  return value;
}

function requireDuration(value, code) {
  if (
    typeof value !== "number" ||
    !Number.isFinite(value) ||
    value <= 0 ||
    value > MAX_DURATION_MS
  ) {
    reject(code);
  }
  return value;
}

// ---------------------------------------------------------------------------
// Deterministic arithmetic
// ---------------------------------------------------------------------------

/**
 * Nearest-rank percentile: `ceil(p * n)` into the sorted values, no
 * interpolation, so the result is always an observation that actually happened.
 *
 * This is the arithmetic `references/oracle-slo.md` already states and the same
 * rule `oracle_latency.nearest_rank` uses on the host. Two summaries of one run
 * must not disagree about which sample p95 names, so the rule is pinned here
 * rather than re-chosen.
 */
export function nearestRankPercentile(values, percentile) {
  if (!Array.isArray(values) || values.length === 0) reject("percentile_empty");
  if (
    typeof percentile !== "number" ||
    !Number.isFinite(percentile) ||
    percentile <= 0 ||
    percentile > 1
  ) {
    reject("percentile_invalid");
  }
  const sorted = [...values].sort((left, right) => left - right);
  const rank = Math.ceil(percentile * sorted.length);
  return sorted[Math.min(rank, sorted.length) - 1];
}

/**
 * Six decimal places, matching the precision the SLO receipt already reports.
 * Derived values are rounded; selected order statistics are not, because they
 * are samples and rounding one would make it stop matching its own run.
 */
function round6(value) {
  return Math.round(value * 1e6) / 1e6;
}

function leastSquaresSlope(points) {
  if (points.length < 2) return null;
  const n = points.length;
  const meanX = points.reduce((total, point) => total + point.x, 0) / n;
  const meanY = points.reduce((total, point) => total + point.y, 0) / n;
  let covariance = 0;
  let variance = 0;
  for (const point of points) {
    covariance += (point.x - meanX) * (point.y - meanY);
    variance += (point.x - meanX) ** 2;
  }
  if (variance === 0) return null;
  return round6(covariance / variance);
}

function stableValue(value) {
  if (Array.isArray(value)) return value.map(stableValue);
  if (isPlainObject(value)) {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, stableValue(value[key])]),
    );
  }
  return value;
}

export function canonicalJson(value) {
  return JSON.stringify(stableValue(value));
}

// ---------------------------------------------------------------------------
// SLO contract
// ---------------------------------------------------------------------------

export function parseSlo(value) {
  const code = "slo_invalid";
  exactObject(
    value,
    [
      "schema",
      "version",
      "cold_p95_ms_max",
      "warm_p95_ms_max",
      "final_dom_to_output_p95_ms",
      "warm_successful_runs_min",
      "browser_pids_exact",
      "max_rss_growth_bytes_max",
    ],
    code,
  );
  if (value.schema !== BENCHMARK_SLO_SCHEMA) reject(code);
  requireInteger(value.version, 1, 1_000, code);
  requireInteger(value.cold_p95_ms_max, 1, MAX_DURATION_MS, code);
  requireInteger(value.warm_p95_ms_max, 1, MAX_DURATION_MS, code);
  exactObject(value.final_dom_to_output_p95_ms, ["max", "applicable"], code);
  requireInteger(value.final_dom_to_output_p95_ms.max, 1, MAX_DURATION_MS, code);
  if (typeof value.final_dom_to_output_p95_ms.applicable !== "boolean") {
    reject(code);
  }
  requireInteger(value.warm_successful_runs_min, 1, MAX_SAMPLES, code);
  requireInteger(value.browser_pids_exact, 1, 64, code);
  requireInteger(value.max_rss_growth_bytes_max, 1, MAX_RSS_BYTES, code);
  return Object.freeze({
    ...structuredClone(value),
    final_dom_to_output_p95_ms: Object.freeze({
      ...value.final_dom_to_output_p95_ms,
    }),
  });
}

// ---------------------------------------------------------------------------
// Samples
// ---------------------------------------------------------------------------

function normalizeLatencySamples(rawSamples) {
  const code = "sample_invalid";
  if (
    !Array.isArray(rawSamples) ||
    rawSamples.length === 0 ||
    rawSamples.length > MAX_SAMPLES
  ) {
    reject(code);
  }
  return rawSamples.map((rawSample, index) => {
    exactObject(rawSample, ["index", "duration_ms", "outcome"], code);
    // Contiguous from zero. A gap means samples were dropped somewhere between
    // the run and this file, and a percentile over an unknown subset of a run
    // is not the percentile anyone thinks it is.
    if (rawSample.index !== index) reject(code);
    if (!OUTCOMES.includes(rawSample.outcome)) reject(code);
    requireDuration(rawSample.duration_ms, code);
    // Deliberately the same key set that came in: normalization is idempotent,
    // so a sample set that has been through it once — as `collectSamples`
    // returns — is still accepted by `buildReceipt`.
    return Object.freeze({
      index,
      duration_ms: rawSample.duration_ms,
      outcome: rawSample.outcome,
    });
  });
}

function normalizeRssObservations(rawObservations) {
  const code = "rss_observation_invalid";
  if (
    !Array.isArray(rawObservations) ||
    rawObservations.length === 0 ||
    rawObservations.length > MAX_SAMPLES + 1
  ) {
    reject(code);
  }
  return rawObservations.map((rawObservation, index) => {
    exactObject(rawObservation, ["index", "root_pid", "rss_bytes"], code);
    if (rawObservation.index !== index) reject(code);
    requireInteger(rawObservation.root_pid, 1, MAX_PID, code);
    requireInteger(rawObservation.rss_bytes, 0, MAX_RSS_BYTES, code);
    return Object.freeze({
      index,
      root_pid: rawObservation.root_pid,
      rss_bytes: rawObservation.rss_bytes,
    });
  });
}

/**
 * Fail closed on a malformed sample set; do not fail closed on a bad result.
 *
 * The distinction is the whole point of this function. A sample file with a
 * negative duration, a torn index, or an unknown key is *unreadable* and throws
 * — summarizing it would invent a number. A run where every warm call errored
 * is perfectly readable and means the lane is broken; that becomes a receipt
 * with `no_samples` and an overall `fail`, because a thrown error there would
 * destroy the very measurement someone needs to see.
 */
export function normalizeSampleSet(value) {
  const code = "samples_invalid";
  exactObject(
    value,
    [
      "schema",
      "run_id",
      "model",
      "started_at",
      "ended_at",
      "cold",
      "warm",
      "rss",
    ],
    code,
  );
  if (value.schema !== BENCHMARK_SAMPLES_SCHEMA) reject(code);
  const runId = requireString(value.run_id, RUN_ID_PATTERN, code);
  const model = (() => {
    if (typeof value.model !== "string" || value.model.length > 64) reject(code);
    return requireString(value.model, MODEL_PATTERN, code);
  })();
  const startedAt = requireTimestamp(value.started_at, code);
  const endedAt = requireTimestamp(value.ended_at, code);
  if (Date.parse(endedAt) < Date.parse(startedAt)) reject(code);
  return Object.freeze({
    schema: BENCHMARK_SAMPLES_SCHEMA,
    run_id: runId,
    model,
    started_at: startedAt,
    ended_at: endedAt,
    cold: Object.freeze(normalizeLatencySamples(value.cold)),
    warm: Object.freeze(normalizeLatencySamples(value.warm)),
    rss: Object.freeze(normalizeRssObservations(value.rss)),
  });
}

/**
 * Latency summary over the *successful* samples only.
 *
 * The SLO is stated for runs that produced an answer. Including an abort would
 * let a lane improve its p95 by failing faster, which is the opposite of the
 * thing being measured — so failures are counted separately and named, never
 * folded into the percentile.
 */
export function summarizeLatency(samples) {
  const successful = samples
    .filter((sample) => sample.outcome === "ok")
    .map((sample) => sample.duration_ms);
  if (successful.length === 0) {
    return Object.freeze({
      count: samples.length,
      successful: 0,
      failed: samples.length,
      min_ms: null,
      p50_ms: null,
      p95_ms: null,
      max_ms: null,
      code: "no_successful_samples",
    });
  }
  return Object.freeze({
    count: samples.length,
    successful: successful.length,
    failed: samples.length - successful.length,
    min_ms: Math.min(...successful),
    p50_ms: nearestRankPercentile(successful, 0.5),
    p95_ms: nearestRankPercentile(successful, 0.95),
    max_ms: Math.max(...successful),
    code: null,
  });
}

/**
 * Growth against the first observation, plus how many distinct root PIDs were
 * ever seen.
 *
 * The PID count is the leak detector that matters most: an RSS series that
 * looks flat because the browser was restarted underneath it is not a flat RSS
 * series, and only the distinct-PID count can tell the difference. Raw PIDs are
 * read and discarded — the receipt carries the count.
 */
export function summarizeRss(observations) {
  const baseline = observations[0].rss_bytes;
  const final = observations.at(-1).rss_bytes;
  let maxGrowth = 0;
  for (const observation of observations) {
    maxGrowth = Math.max(maxGrowth, observation.rss_bytes - baseline);
  }
  const pids = new Set(observations.map((observation) => observation.root_pid));
  return Object.freeze({
    browser_pids: pids.size,
    browser_pid_samples: observations.length,
    max_rss_growth_bytes: maxGrowth,
    rss: Object.freeze({
      baseline_bytes: baseline,
      final_bytes: final,
      final_growth_bytes: final - baseline,
      slope_bytes_per_run: leastSquaresSlope(
        observations.map((observation) => ({
          x: observation.index,
          y: observation.rss_bytes,
        })),
      ),
      observations: observations.length,
    }),
  });
}

// ---------------------------------------------------------------------------
// Gates
// ---------------------------------------------------------------------------

function compare(comparator, observed, target) {
  if (comparator === "lt") return observed < target;
  if (comparator === "lte") return observed <= target;
  if (comparator === "gte") return observed >= target;
  return observed === target;
}

function gate(name, comparator, target, observed, { applicable = true } = {}) {
  const verdict = !applicable
    ? "not_exercised"
    : observed === null
      ? "no_samples"
      : compare(comparator, observed, target)
        ? "pass"
        : "fail";
  return Object.freeze({
    gate: name,
    comparator,
    target,
    observed,
    verdict,
    code:
      verdict === "pass"
        ? null
        : verdict === "not_exercised"
          ? "lane_has_no_final_dom"
          : verdict === "no_samples"
            ? "no_successful_samples"
            : `${name}_missed`,
  });
}

export function evaluateGates(summary, slo) {
  return Object.freeze([
    gate(
      "cold_cli_to_submit_p95",
      "lte",
      slo.cold_p95_ms_max,
      summary.cold.p95_ms,
    ),
    gate(
      "warm_browser_to_submit_p95",
      "lte",
      slo.warm_p95_ms_max,
      summary.warm.p95_ms,
    ),
    gate(
      "final_dom_to_output_p95",
      "lte",
      slo.final_dom_to_output_p95_ms.max,
      null,
      { applicable: slo.final_dom_to_output_p95_ms.applicable },
    ),
    gate(
      "warm_successful_runs",
      "gte",
      slo.warm_successful_runs_min,
      summary.warm.successful,
    ),
    gate("browser_pids", "eq", slo.browser_pids_exact, summary.browser_pids),
    gate(
      "max_rss_growth_bytes",
      "lt",
      slo.max_rss_growth_bytes_max,
      summary.max_rss_growth_bytes,
    ),
  ]);
}

// ---------------------------------------------------------------------------
// Receipt safety: a closed vocabulary
// ---------------------------------------------------------------------------

const RECEIPT_KEYS = new Set([
  "schema",
  "generated_at",
  "run_id",
  "model",
  "window",
  "started_at",
  "ended_at",
  "slo",
  "version",
  "cold_p95_ms_max",
  "warm_p95_ms_max",
  "final_dom_to_output_p95_ms",
  "max",
  "applicable",
  "warm_successful_runs_min",
  "browser_pids_exact",
  "max_rss_growth_bytes_max",
  "cold",
  "warm",
  "count",
  "successful",
  "failed",
  "min_ms",
  "p50_ms",
  "p95_ms",
  "max_ms",
  "code",
  "browser_pids",
  "browser_pid_samples",
  "max_rss_growth_bytes",
  "rss",
  "baseline_bytes",
  "final_bytes",
  "final_growth_bytes",
  "slope_bytes_per_run",
  "observations",
  "gates",
  "gate",
  "comparator",
  "target",
  "observed",
  "verdict",
  "status",
  "receipt_sha256",
]);

const isCanonicalTimestamp = (value) => {
  const milliseconds = Date.parse(value);
  return (
    Number.isFinite(milliseconds) &&
    new Date(milliseconds).toISOString() === value
  );
};

/**
 * Which keys are allowed to hold a string at all, and what that string may be.
 *
 * Keyed rather than value-shaped on purpose. A validator that accepts "any
 * lowercase token up to 64 characters" anywhere in the tree would happily pass
 * a conversation slug or a profile directory name; binding each string to the
 * one key that may carry it means an extra string has nowhere legal to land.
 */
const RECEIPT_STRING_KEYS = new Map([
  [
    "schema",
    (value) => value === BENCHMARK_RECEIPT_SCHEMA || value === BENCHMARK_SLO_SCHEMA,
  ],
  ["generated_at", isCanonicalTimestamp],
  ["started_at", isCanonicalTimestamp],
  ["ended_at", isCanonicalTimestamp],
  ["run_id", (value) => RUN_ID_PATTERN.test(value)],
  ["model", (value) => value.length <= 64 && MODEL_PATTERN.test(value)],
  ["code", (value) => CODE_PATTERN.test(value)],
  ["gate", (value) => GATE_PATTERN.test(value)],
  ["comparator", (value) => COMPARATORS.includes(value)],
  ["verdict", (value) => VERDICTS.includes(value)],
  ["status", (value) => ["pass", "fail", "degraded"].includes(value)],
  ["receipt_sha256", (value) => SHA256_PATTERN.test(value)],
]);

/**
 * Nothing may appear in a receipt that this module cannot name.
 *
 * The check is inverted on purpose. An outbound denylist has to anticipate the
 * shape of the next leak; a closed vocabulary does not, because a prompt
 * fragment, a profile path, a cookie, a bearer token, and a Tailnet IP all fail
 * the same way — they have no key that will hold them.
 */
export function assertReceiptSafe(receipt) {
  const code = "receipt_unsafe";
  const walk = (value, key) => {
    if (value === null || typeof value === "boolean") return;
    if (typeof value === "number") {
      if (!Number.isFinite(value)) reject(code);
      return;
    }
    if (typeof value === "string") {
      const accepts = RECEIPT_STRING_KEYS.get(key);
      if (!accepts || !accepts(value)) reject(code);
      if (
        SENSITIVE_LOG_PATTERN.test(value) ||
        CREDENTIAL_SHAPE_PATTERN.test(value)
      ) {
        reject(code);
      }
      return;
    }
    // An array inherits its parent's key: `gates` holds gate objects, and no
    // receipt array holds a bare string.
    if (Array.isArray(value)) {
      for (const item of value) walk(item, key);
      return;
    }
    if (!isPlainObject(value)) reject(code);
    for (const [nestedKey, nested] of Object.entries(value)) {
      if (!RECEIPT_KEYS.has(nestedKey)) reject(code);
      walk(nested, nestedKey);
    }
  };
  walk(receipt, null);
  const encoded = canonicalJson(receipt);
  if (
    SENSITIVE_LOG_PATTERN.test(encoded) ||
    CREDENTIAL_SHAPE_PATTERN.test(encoded)
  ) {
    reject(code);
  }
  return receipt;
}

// ---------------------------------------------------------------------------
// Receipt
// ---------------------------------------------------------------------------

/**
 * The digest covers the whole receipt except itself, over canonical JSON with
 * sorted keys — so it is stable against key-order churn and cannot be satisfied
 * by editing a field the hash "happened not to cover".
 */
export function receiptDigest(receipt) {
  if (!isPlainObject(receipt)) reject("receipt_invalid");
  const { receipt_sha256: _digest, ...body } = receipt;
  return createHash("sha256").update(canonicalJson(body), "utf8").digest("hex");
}

export function verifyReceiptDigest(receipt) {
  if (!isPlainObject(receipt)) reject("receipt_invalid");
  if (typeof receipt.receipt_sha256 !== "string") reject("receipt_invalid");
  return receiptDigest(receipt) === receipt.receipt_sha256;
}

/**
 * Build the receipt. Pure: the same samples and the same `generatedAt` produce
 * the same bytes and the same digest, which is what makes two measurements
 * comparable at all.
 */
export function buildReceipt({
  samples: rawSamples,
  slo: rawSlo = DEFAULT_SLO,
  generatedAt,
} = {}) {
  const samples = normalizeSampleSet(rawSamples);
  const slo = parseSlo(rawSlo);
  const generated = requireTimestamp(generatedAt, "generated_at_invalid");
  const resources = summarizeRss(samples.rss);
  const summary = {
    cold: summarizeLatency(samples.cold),
    warm: summarizeLatency(samples.warm),
    browser_pids: resources.browser_pids,
    max_rss_growth_bytes: resources.max_rss_growth_bytes,
  };
  const gates = evaluateGates(summary, slo);
  // `degraded` is not a softer `fail`; it is the only honest verdict for a run
  // that could not exercise a declared gate. Collapsing it into `pass` would
  // let the untested final-DOM path report green forever.
  const status = gates.some((entry) =>
    ["fail", "no_samples"].includes(entry.verdict),
  )
    ? "fail"
    : gates.some((entry) => entry.verdict === "not_exercised")
      ? "degraded"
      : "pass";
  const body = {
    schema: BENCHMARK_RECEIPT_SCHEMA,
    generated_at: generated,
    run_id: samples.run_id,
    model: samples.model,
    window: { started_at: samples.started_at, ended_at: samples.ended_at },
    slo,
    cold: summary.cold,
    warm: summary.warm,
    browser_pids: resources.browser_pids,
    browser_pid_samples: resources.browser_pid_samples,
    max_rss_growth_bytes: resources.max_rss_growth_bytes,
    rss: resources.rss,
    gates,
    status,
  };
  assertReceiptSafe(body);
  return Object.freeze({ ...body, receipt_sha256: receiptDigest(body) });
}

// ---------------------------------------------------------------------------
// Live collection, through injected probes
// ---------------------------------------------------------------------------

function parsePlan(value) {
  const code = "plan_invalid";
  exactObject(value, ["run_id", "model", "cold_runs", "warm_runs"], code);
  if (typeof value.model !== "string" || value.model.length > 64) reject(code);
  return Object.freeze({
    run_id: requireString(value.run_id, RUN_ID_PATTERN, code),
    model: requireString(value.model, MODEL_PATTERN, code),
    cold_runs: requireInteger(value.cold_runs, 1, MAX_SAMPLES, code),
    warm_runs: requireInteger(value.warm_runs, 1, MAX_SAMPLES, code),
  });
}

async function callLatencyProbe(probe, phase, index) {
  const code = "probe_result_invalid";
  const result = await probe({ phase, index });
  exactObject(result, ["duration_ms", "outcome"], code);
  requireDuration(result.duration_ms, code);
  if (!OUTCOMES.includes(result.outcome)) reject(code);
  return { index, duration_ms: result.duration_ms, outcome: result.outcome };
}

async function callRssProbe(rssProbe, index) {
  const code = "rss_probe_result_invalid";
  const result = await rssProbe({ index });
  exactObject(result, ["root_pid", "rss_bytes"], code);
  requireInteger(result.root_pid, 1, MAX_PID, code);
  requireInteger(result.rss_bytes, 0, MAX_RSS_BYTES, code);
  return { index, root_pid: result.root_pid, rss_bytes: result.rss_bytes };
}

/**
 * Drive the measurement in the order the SLO defines, and hand back a sample
 * set the pure path can summarize.
 *
 * The probes are the seam. On the host they wrap a fresh Node process
 * (`cold`), a sequential `askOracle` against the running browser (`warm`), and
 * a read of the Chrome tree's `VmRSS`. Here they are function arguments and
 * nothing more, which is why this file can hold the procedure without holding
 * the ability to run the Oracle.
 *
 * RSS is sampled once at baseline and again after every warm call, so the
 * series has `warm_runs + 1` points and `index` is the run number.
 */
export async function collectSamples({
  plan: rawPlan,
  probe,
  rssProbe,
  clock,
} = {}) {
  const planned = parsePlan(rawPlan);
  for (const dependency of [probe, rssProbe, clock]) {
    if (typeof dependency !== "function") reject("probe_missing");
  }
  const startedAt = requireTimestamp(clock(), "clock_invalid");
  const cold = [];
  for (let index = 0; index < planned.cold_runs; index += 1) {
    cold.push(await callLatencyProbe(probe, "cold", index));
  }
  const rss = [await callRssProbe(rssProbe, 0)];
  const warm = [];
  for (let index = 0; index < planned.warm_runs; index += 1) {
    warm.push(await callLatencyProbe(probe, "warm", index));
    rss.push(await callRssProbe(rssProbe, index + 1));
  }
  const endedAt = requireTimestamp(clock(), "clock_invalid");
  return normalizeSampleSet({
    schema: BENCHMARK_SAMPLES_SCHEMA,
    run_id: planned.run_id,
    model: planned.model,
    started_at: startedAt,
    ended_at: endedAt,
    cold,
    warm,
    rss,
  });
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

export function parseArguments(argv) {
  const options = {
    json: false,
    samplesPath: null,
    sloPath: null,
    now: null,
    requireComplete: false,
  };
  const takeValue = (argument, index) => {
    const value = argv[index + 1];
    if (typeof value !== "string" || value.startsWith("--")) {
      reject("usage_invalid");
    }
    return value;
  };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--json") {
      options.json = true;
    } else if (argument === "--require-complete") {
      options.requireComplete = true;
    } else if (argument === "--live") {
      // There is no live mode. The flag exists so an operator who expects one
      // is told, rather than getting a receipt built from nothing.
      reject("live_collection_unavailable");
    } else if (argument === "--samples") {
      options.samplesPath = takeValue(argument, index);
      index += 1;
    } else if (argument.startsWith("--samples=")) {
      options.samplesPath = argument.slice("--samples=".length);
    } else if (argument === "--slo") {
      options.sloPath = takeValue(argument, index);
      index += 1;
    } else if (argument.startsWith("--slo=")) {
      options.sloPath = argument.slice("--slo=".length);
    } else if (argument === "--now") {
      options.now = takeValue(argument, index);
      index += 1;
    } else if (argument.startsWith("--now=")) {
      options.now = argument.slice("--now=".length);
    } else {
      reject("usage_invalid");
    }
  }
  if (options.samplesPath === null) reject("samples_required");
  return options;
}

function errorLine(code) {
  return `${JSON.stringify({
    schema: BENCHMARK_RECEIPT_SCHEMA,
    status: "error",
    code,
  })}\n`;
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
    write(errorLine(error?.code ?? "usage_invalid"));
    return EXIT_USAGE;
  }
  const { readFile } = await import("node:fs/promises");
  const load = async (path, code) => {
    try {
      return JSON.parse(await readFile(path, "utf8"));
    } catch {
      reject(code);
    }
  };
  let receipt;
  try {
    const samples = await load(options.samplesPath, "samples_unreadable");
    const slo =
      options.sloPath === null
        ? DEFAULT_SLO
        : await load(options.sloPath, "slo_unreadable");
    receipt = buildReceipt({
      samples,
      slo,
      generatedAt: options.now ?? new Date().toISOString(),
    });
  } catch (error) {
    write(errorLine(error?.code ?? "internal_error"));
    return EXIT_USAGE;
  }
  write(
    options.json
      ? `${JSON.stringify(receipt)}\n`
      : `${receipt.status} cold_p95=${receipt.cold.p95_ms} warm_p95=${
          receipt.warm.p95_ms
        } browser_pids=${receipt.browser_pids} max_rss_growth_bytes=${
          receipt.max_rss_growth_bytes
        } sha256=${receipt.receipt_sha256}\n`,
  );
  if (receipt.status === "fail") return EXIT_FAIL;
  if (receipt.status === "degraded") {
    return options.requireComplete ? EXIT_INCOMPLETE : EXIT_PASS;
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
