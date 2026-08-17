// Contract tests for the Oracle benchmark harness.
//
//   node --test deep-research-prompt/tests/oracle-subagent-benchmark.test.mjs
//
// Three claims carry the weight, and each is tested against something outside
// the module's own opinion of itself:
//
//   1. **It reproduces the recorded measurement.** The 2026-08-06 run in
//      `references/oracle-slo.md` is encoded as a fixture, and the harness must
//      return that document's numbers — including its failing warm gate. A
//      summarizer that cannot re-derive the measurement it is meant to be
//      compared against is not a baseline.
//   2. **It is deterministic.** Same samples, same `generated_at`, byte-identical
//      receipt and digest. That is the only thing that makes a later run
//      comparable rather than merely adjacent.
//   3. **It cannot reach the Oracle and cannot leak.** The import allowlist is
//      checked against the module's own source text, not against a mock; the
//      redaction test injects real credential and prompt shapes and asserts they
//      have nowhere to land.

import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import {
  BENCHMARK_RECEIPT_SCHEMA,
  BENCHMARK_SAMPLES_SCHEMA,
  BENCHMARK_SLO_SCHEMA,
  DEFAULT_SLO,
  EXIT_FAIL,
  EXIT_INCOMPLETE,
  EXIT_PASS,
  EXIT_USAGE,
  MODULE_IMPORT_ALLOWLIST,
  OracleBenchmarkError,
  assertReceiptSafe,
  buildReceipt,
  canonicalJson,
  collectSamples,
  evaluateGates,
  main,
  nearestRankPercentile,
  normalizeSampleSet,
  parseArguments,
  parseSlo,
  receiptDigest,
  summarizeLatency,
  summarizeRss,
  verifyReceiptDigest,
} from "../assets/scripts/oracle-subagent-benchmark.mjs";

const MODULE_PATH = fileURLToPath(
  new URL("../assets/scripts/oracle-subagent-benchmark.mjs", import.meta.url),
);

const NOW = "2026-08-06T19:40:00.000Z";
const STARTED_AT = "2026-08-06T19:32:42.383Z";
const ENDED_AT = "2026-08-06T19:36:56.426Z";
const RUN_ID = "oracle-bench-2026-08-06";

// ---------------------------------------------------------------------------
// The 2026-08-06 live run, transcribed from references/oracle-slo.md
// ---------------------------------------------------------------------------

const COLD_2026_08_06 = [7273.8893, 6313.497611, 6755.460291];

// The document publishes min, p95, and max for the twenty warm samples. The
// seventeen interior values are filler chosen to sit strictly between the
// published min and p95, so the three order statistics the document does state
// are exactly the three this fixture reproduces. Nothing here claims to know
// the interior of that run.
const WARM_2026_08_06 = [
  4206.743224, 9614.340436, 10027.255714,
  ...Array.from({ length: 17 }, (_, index) => 4500 + index * 250),
];

// Twenty-one readings: baseline plus one after each warm call. Baseline, peak,
// and final are the document's; the rest interpolate between them without
// exceeding the peak.
const RSS_BASELINE = 958_316_544;
const RSS_PEAK = RSS_BASELINE + 14_237_696; // max growth 14,237,696
const RSS_FINAL = 971_665_408; // final growth 13,348,864

const RSS_2026_08_06 = [
  RSS_BASELINE,
  ...Array.from({ length: 18 }, (_, index) =>
    Math.round(RSS_BASELINE + ((RSS_PEAK - RSS_BASELINE) * (index + 1)) / 19),
  ),
  RSS_PEAK,
  RSS_FINAL,
];

function latencySamples(durations, outcome = "ok") {
  return durations.map((duration_ms, index) => ({
    index,
    duration_ms,
    outcome: typeof outcome === "function" ? outcome(index) : outcome,
  }));
}

function rssObservations(values, rootPid = 4242) {
  return values.map((rss_bytes, index) => ({
    index,
    root_pid: typeof rootPid === "function" ? rootPid(index) : rootPid,
    rss_bytes,
  }));
}

function historicalSamples(overrides = {}) {
  return {
    schema: BENCHMARK_SAMPLES_SCHEMA,
    run_id: RUN_ID,
    model: "gpt-5-5-instant",
    started_at: STARTED_AT,
    ended_at: ENDED_AT,
    cold: latencySamples(COLD_2026_08_06),
    warm: latencySamples(WARM_2026_08_06),
    rss: rssObservations(RSS_2026_08_06),
    ...overrides,
  };
}

// A run that meets every applicable gate, used wherever the failing historical
// fixture would mask the behaviour under test.
function passingSamples(overrides = {}) {
  return historicalSamples({
    run_id: "oracle-bench-passing-01",
    cold: latencySamples([8000.5, 7500.25, 9000.125]),
    warm: latencySamples(
      Array.from({ length: 20 }, (_, index) => 3000 + index * 10),
    ),
    rss: rssObservations(
      Array.from({ length: 21 }, (_, index) => RSS_BASELINE + index * 1000),
    ),
    ...overrides,
  });
}

function rejectsWith(code, body) {
  assert.throws(body, (error) => {
    assert.ok(error instanceof OracleBenchmarkError, `not a harness error: ${error}`);
    assert.equal(error.code, code);
    return true;
  });
}

// ---------------------------------------------------------------------------
// Structural: it cannot reach the Oracle
// ---------------------------------------------------------------------------

// The claim under test is about code, not documentation — the module's own
// header names `node:child_process` in order to say it does not use it — so the
// scan runs against the source with comments removed.
function moduleCode() {
  return readFileSync(MODULE_PATH, "utf8")
    .replaceAll(/\/\*[\s\S]*?\*\//g, "")
    .replaceAll(/^\s*\/\/.*$/gm, "");
}

test("the module imports nothing outside its pinned allowlist", () => {
  const source = moduleCode();
  const specifiers = new Set();
  for (const match of source.matchAll(/(?:^|\s)from\s+"([^"]+)";/gm)) {
    specifiers.add(match[1]);
  }
  for (const match of source.matchAll(/\bimport\(\s*"([^"]+)"\s*\)/g)) {
    specifiers.add(match[1]);
  }
  assert.deepEqual(
    [...specifiers].sort(),
    [...MODULE_IMPORT_ALLOWLIST].sort(),
    "an import appeared that the allowlist does not name",
  );
});

test("the module has no path to a process, a socket, or an Oracle module", () => {
  const source = moduleCode();
  for (const forbidden of [
    "node:child_process",
    "node:net",
    "node:http",
    "node:https",
    "node:tls",
    "node:dgram",
    "node:worker_threads",
    "./oracle-",
  ]) {
    assert.ok(
      !source.includes(forbidden),
      `benchmark harness must not reference ${forbidden}`,
    );
  }
});

test("the CLI refuses a live mode instead of improvising one", () => {
  rejectsWith("live_collection_unavailable", () =>
    parseArguments(["--samples", "s.json", "--live"]),
  );
});

// ---------------------------------------------------------------------------
// Percentile arithmetic
// ---------------------------------------------------------------------------

test("p95 is nearest-rank: three samples use the maximum", () => {
  // references/oracle-slo.md states exactly this, and the host-side summarizer
  // uses the same rule. Two summaries of one run must not disagree about which
  // observation p95 names.
  assert.equal(nearestRankPercentile([3, 1, 2], 0.95), 3);
});

test("p95 is nearest-rank: twenty samples use the nineteenth sorted value", () => {
  const values = Array.from({ length: 20 }, (_, index) => index + 1);
  assert.equal(nearestRankPercentile(values, 0.95), 19);
  assert.equal(nearestRankPercentile(values, 0.5), 10);
  assert.equal(nearestRankPercentile(values, 1), 20);
});

test("p95 never interpolates, so it always names a real observation", () => {
  const values = [10, 20, 30, 40];
  assert.ok(values.includes(nearestRankPercentile(values, 0.95)));
  assert.ok(values.includes(nearestRankPercentile(values, 0.75)));
});

test("percentiles fail closed on an empty series or a bad percentile", () => {
  rejectsWith("percentile_empty", () => nearestRankPercentile([], 0.95));
  rejectsWith("percentile_invalid", () => nearestRankPercentile([1], 0));
  rejectsWith("percentile_invalid", () => nearestRankPercentile([1], 1.5));
  rejectsWith("percentile_invalid", () => nearestRankPercentile([1], Number.NaN));
});

// ---------------------------------------------------------------------------
// SLO contract
// ---------------------------------------------------------------------------

test("the shipped SLO matches the published release targets", () => {
  const slo = parseSlo(DEFAULT_SLO);
  assert.equal(slo.schema, BENCHMARK_SLO_SCHEMA);
  assert.equal(slo.cold_p95_ms_max, 12_000);
  assert.equal(slo.warm_p95_ms_max, 4_000);
  assert.equal(slo.warm_successful_runs_min, 20);
  assert.equal(slo.browser_pids_exact, 1);
  assert.equal(slo.max_rss_growth_bytes_max, 104_857_600);
  assert.equal(slo.final_dom_to_output_p95_ms.max, 5_000);
  assert.equal(slo.final_dom_to_output_p95_ms.applicable, false);
  assert.ok(Object.isFrozen(DEFAULT_SLO));
});

test("the SLO fails closed on an unknown key or a bad target", () => {
  rejectsWith("slo_invalid", () => parseSlo({ ...DEFAULT_SLO, extra: 1 }));
  rejectsWith("slo_invalid", () => parseSlo({ ...DEFAULT_SLO, warm_p95_ms_max: 0 }));
  rejectsWith("slo_invalid", () =>
    parseSlo({ ...DEFAULT_SLO, warm_p95_ms_max: 4000.5 }),
  );
  rejectsWith("slo_invalid", () => parseSlo({ ...DEFAULT_SLO, schema: "other" }));
  rejectsWith("slo_invalid", () =>
    parseSlo({ ...DEFAULT_SLO, browser_pids_exact: 0 }),
  );
});

// ---------------------------------------------------------------------------
// Samples: fail closed on malformed input
// ---------------------------------------------------------------------------

test("the historical sample set is accepted and frozen", () => {
  const samples = normalizeSampleSet(historicalSamples());
  assert.equal(samples.cold.length, 3);
  assert.equal(samples.warm.length, 20);
  assert.equal(samples.rss.length, 21);
  assert.ok(Object.isFrozen(samples));
  assert.ok(Object.isFrozen(samples.warm));
});

test("normalization is idempotent, so collected samples stay summarizable", () => {
  // `collectSamples` returns a normalized set and `buildReceipt` normalizes
  // again. If the two disagreed on the key set, the harness would refuse its
  // own output and the live path would break only on the host.
  const once = normalizeSampleSet(historicalSamples());
  const twice = normalizeSampleSet(once);
  assert.deepEqual(twice, once);
  assert.equal(canonicalJson(twice), canonicalJson(once));
});

test("a non-positive, non-finite, or non-numeric duration is rejected", () => {
  for (const duration of [0, -1, Number.NaN, Number.POSITIVE_INFINITY, "12", null]) {
    rejectsWith("sample_invalid", () =>
      normalizeSampleSet(
        historicalSamples({
          warm: latencySamples(WARM_2026_08_06).map((sample, index) =>
            index === 3 ? { ...sample, duration_ms: duration } : sample,
          ),
        }),
      ),
    );
  }
});

test("a torn sample index is rejected rather than silently renumbered", () => {
  // A gap means samples were dropped between the run and this file, and a
  // percentile over an unknown subset of a run is not that run's percentile.
  const warm = latencySamples(WARM_2026_08_06);
  warm.splice(5, 1);
  rejectsWith("sample_invalid", () => normalizeSampleSet(historicalSamples({ warm })));
});

test("an empty phase, an unknown key, and an unknown outcome are rejected", () => {
  rejectsWith("sample_invalid", () => normalizeSampleSet(historicalSamples({ warm: [] })));
  rejectsWith("sample_invalid", () =>
    normalizeSampleSet(
      historicalSamples({
        cold: latencySamples(COLD_2026_08_06).map((sample) => ({
          ...sample,
          note: "slow",
        })),
      }),
    ),
  );
  rejectsWith("sample_invalid", () =>
    normalizeSampleSet(historicalSamples({ warm: latencySamples(WARM_2026_08_06, "maybe") })),
  );
});

test("a bad schema, run id, model, or window is rejected", () => {
  rejectsWith("samples_invalid", () =>
    normalizeSampleSet(historicalSamples({ schema: "other.v1" })),
  );
  rejectsWith("samples_invalid", () => normalizeSampleSet(historicalSamples({ run_id: "short" })));
  rejectsWith("samples_invalid", () =>
    normalizeSampleSet(historicalSamples({ model: "GPT_5_5" })),
  );
  // Parseable but not canonical: a timestamp that round-trips differently on
  // two machines makes the digest irreproducible.
  rejectsWith("samples_invalid", () =>
    normalizeSampleSet(historicalSamples({ started_at: "2026-08-06T19:32:42Z" })),
  );
  rejectsWith("samples_invalid", () =>
    normalizeSampleSet(historicalSamples({ ended_at: "2026-08-06T19:00:00.000Z" })),
  );
  rejectsWith("samples_invalid", () =>
    normalizeSampleSet({ ...historicalSamples(), extra: true }),
  );
});

test("an implausible RSS observation is rejected", () => {
  rejectsWith("rss_observation_invalid", () =>
    normalizeSampleSet(historicalSamples({ rss: rssObservations(RSS_2026_08_06, 0) })),
  );
  rejectsWith("rss_observation_invalid", () =>
    normalizeSampleSet(historicalSamples({ rss: rssObservations([-1, 2, 3]) })),
  );
  rejectsWith("rss_observation_invalid", () =>
    normalizeSampleSet(
      historicalSamples({
        rss: rssObservations(RSS_2026_08_06).map((observation, index) =>
          index === 2 ? { ...observation, index: 99 } : observation,
        ),
      }),
    ),
  );
  rejectsWith("rss_observation_invalid", () => normalizeSampleSet(historicalSamples({ rss: [] })));
});

test("a credential-shaped run id cannot enter through the sample file", () => {
  for (const runId of [
    "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
    "sk-proj-ABCDEFGHIJKLMNOP",
    "session_token_abcdefgh",
  ]) {
    rejectsWith("samples_invalid", () =>
      normalizeSampleSet(historicalSamples({ run_id: runId })),
    );
  }
});

// ---------------------------------------------------------------------------
// Summaries
// ---------------------------------------------------------------------------

test("failed runs are counted but kept out of the percentile", () => {
  // Otherwise a lane could improve its p95 by failing faster, which is the
  // opposite of the property being measured.
  const samples = normalizeSampleSet(
    historicalSamples({
      warm: latencySamples([100, 200, 5000], (index) => (index === 2 ? "error" : "ok")),
    }),
  );
  const summary = summarizeLatency(samples.warm);
  assert.equal(summary.count, 3);
  assert.equal(summary.successful, 2);
  assert.equal(summary.failed, 1);
  assert.equal(summary.max_ms, 200);
  assert.equal(summary.p95_ms, 200);
  assert.equal(summary.code, null);
});

test("a phase with no successful run reports no_samples instead of throwing", () => {
  // A readable file describing a broken lane is a measurement. Throwing here
  // would destroy the very result someone needs to see.
  const samples = normalizeSampleSet(
    historicalSamples({ warm: latencySamples([100, 200], "aborted") }),
  );
  const summary = summarizeLatency(samples.warm);
  assert.equal(summary.successful, 0);
  assert.equal(summary.failed, 2);
  assert.equal(summary.p95_ms, null);
  assert.equal(summary.min_ms, null);
  assert.equal(summary.code, "no_successful_samples");
});

test("RSS growth is measured against the baseline, and the peak is kept", () => {
  const samples = normalizeSampleSet(historicalSamples());
  const resources = summarizeRss(samples.rss);
  assert.equal(resources.rss.baseline_bytes, RSS_BASELINE);
  assert.equal(resources.rss.final_bytes, RSS_FINAL);
  assert.equal(resources.rss.final_growth_bytes, 13_348_864);
  // The peak, not the endpoint: a run that grows and then releases still grew.
  assert.equal(resources.max_rss_growth_bytes, 14_237_696);
  assert.equal(resources.browser_pid_samples, 21);
});

test("a restarted browser is caught by the distinct PID count", () => {
  // An RSS series that looks flat because the browser was replaced underneath
  // it is not a flat RSS series, and only the PID count can tell the difference.
  const samples = normalizeSampleSet(
    historicalSamples({
      rss: rssObservations(RSS_2026_08_06, (index) => (index > 10 ? 5555 : 4242)),
    }),
  );
  assert.equal(summarizeRss(samples.rss).browser_pids, 2);
});

test("the RSS slope is a least-squares fit over the run index", () => {
  const samples = normalizeSampleSet(
    historicalSamples({ rss: rssObservations([1000, 2000, 3000, 4000]) }),
  );
  assert.equal(summarizeRss(samples.rss).rss.slope_bytes_per_run, 1000);
  const flat = normalizeSampleSet(
    historicalSamples({ rss: rssObservations([1000, 1000, 1000]) }),
  );
  assert.equal(summarizeRss(flat.rss).rss.slope_bytes_per_run, 0);
});

test("a single RSS observation yields a null slope rather than a fake zero", () => {
  const samples = normalizeSampleSet(historicalSamples({ rss: rssObservations([1000]) }));
  assert.equal(summarizeRss(samples.rss).rss.slope_bytes_per_run, null);
});

// ---------------------------------------------------------------------------
// The receipt reproduces the recorded measurement
// ---------------------------------------------------------------------------

test("the harness re-derives the 2026-08-06 measurement exactly", () => {
  const receipt = buildReceipt({ samples: historicalSamples(), generatedAt: NOW });
  assert.equal(receipt.cold.p95_ms, 7273.8893);
  assert.equal(receipt.cold.successful, 3);
  assert.equal(receipt.warm.min_ms, 4206.743224);
  assert.equal(receipt.warm.p95_ms, 9614.340436);
  assert.equal(receipt.warm.max_ms, 10027.255714);
  assert.equal(receipt.warm.successful, 20);
  assert.equal(receipt.browser_pids, 1);
  assert.equal(receipt.max_rss_growth_bytes, 14_237_696);
  assert.equal(receipt.rss.final_growth_bytes, 13_348_864);
  assert.equal(receipt.model, "gpt-5-5-instant");
});

test("the failing warm gate is reported, not averaged away", () => {
  const receipt = buildReceipt({ samples: historicalSamples(), generatedAt: NOW });
  const byGate = Object.fromEntries(receipt.gates.map((entry) => [entry.gate, entry]));
  assert.equal(byGate.warm_browser_to_submit_p95.verdict, "fail");
  assert.equal(byGate.warm_browser_to_submit_p95.code, "warm_browser_to_submit_p95_missed");
  assert.equal(byGate.warm_browser_to_submit_p95.target, 4000);
  assert.equal(byGate.warm_browser_to_submit_p95.observed, 9614.340436);
  assert.equal(byGate.cold_cli_to_submit_p95.verdict, "pass");
  assert.equal(byGate.warm_successful_runs.verdict, "pass");
  assert.equal(byGate.browser_pids.verdict, "pass");
  assert.equal(byGate.max_rss_growth_bytes.verdict, "pass");
  // One failing gate makes the run fail. Four passes do not buy it off.
  assert.equal(receipt.status, "fail");
});

test("the untested final-DOM gate stays visible as not_exercised", () => {
  const receipt = buildReceipt({ samples: passingSamples(), generatedAt: NOW });
  const dom = receipt.gates.find((entry) => entry.gate === "final_dom_to_output_p95");
  assert.equal(dom.verdict, "not_exercised");
  assert.equal(dom.code, "lane_has_no_final_dom");
  assert.equal(dom.observed, null);
  // Everything applicable passed, and the receipt still refuses to say "pass".
  assert.equal(receipt.status, "degraded");
});

test("a declared-applicable final-DOM gate with no measurement fails", () => {
  const receipt = buildReceipt({
    samples: passingSamples(),
    slo: {
      ...DEFAULT_SLO,
      final_dom_to_output_p95_ms: { max: 5_000, applicable: true },
    },
    generatedAt: NOW,
  });
  const dom = receipt.gates.find((entry) => entry.gate === "final_dom_to_output_p95");
  assert.equal(dom.verdict, "no_samples");
  assert.equal(receipt.status, "fail");
});

test("a phase with no successful run fails the gate rather than passing vacuously", () => {
  const receipt = buildReceipt({
    samples: passingSamples({ warm: latencySamples([100, 200], "error") }),
    generatedAt: NOW,
  });
  assert.equal(receipt.warm.p95_ms, null);
  const warm = receipt.gates.find(
    (entry) => entry.gate === "warm_browser_to_submit_p95",
  );
  assert.equal(warm.verdict, "no_samples");
  assert.equal(receipt.status, "fail");
});

// ---------------------------------------------------------------------------
// Stable shape and a digest that covers it
// ---------------------------------------------------------------------------

test("the receipt shape is stable and versioned", () => {
  const receipt = buildReceipt({ samples: historicalSamples(), generatedAt: NOW });
  assert.equal(receipt.schema, BENCHMARK_RECEIPT_SCHEMA);
  assert.deepEqual(Object.keys(receipt).sort(), [
    "browser_pid_samples",
    "browser_pids",
    "cold",
    "gates",
    "generated_at",
    "max_rss_growth_bytes",
    "model",
    "receipt_sha256",
    "rss",
    "run_id",
    "schema",
    "slo",
    "status",
    "warm",
    "window",
  ]);
  assert.deepEqual(Object.keys(receipt.warm).sort(), [
    "code",
    "count",
    "failed",
    "max_ms",
    "min_ms",
    "p50_ms",
    "p95_ms",
    "successful",
  ]);
  assert.deepEqual(Object.keys(receipt.gates[0]).sort(), [
    "code",
    "comparator",
    "gate",
    "observed",
    "target",
    "verdict",
  ]);
  assert.deepEqual(
    receipt.gates.map((entry) => entry.gate),
    [
      "cold_cli_to_submit_p95",
      "warm_browser_to_submit_p95",
      "final_dom_to_output_p95",
      "warm_successful_runs",
      "browser_pids",
      "max_rss_growth_bytes",
    ],
  );
});

test("the receipt carries every field .6.16 needs to compare two runs", () => {
  const receipt = buildReceipt({ samples: historicalSamples(), generatedAt: NOW });
  for (const value of [
    receipt.cold.p95_ms,
    receipt.warm.p95_ms,
    receipt.browser_pids,
    receipt.max_rss_growth_bytes,
    receipt.receipt_sha256,
  ]) {
    assert.notEqual(value, undefined);
  }
  assert.match(receipt.receipt_sha256, /^[0-9a-f]{64}$/);
});

test("the same samples and clock produce byte-identical receipts", () => {
  const first = buildReceipt({ samples: historicalSamples(), generatedAt: NOW });
  const second = buildReceipt({ samples: historicalSamples(), generatedAt: NOW });
  assert.equal(JSON.stringify(first), JSON.stringify(second));
  assert.equal(first.receipt_sha256, second.receipt_sha256);
});

test("the digest verifies and is recomputable from the receipt alone", () => {
  const receipt = buildReceipt({ samples: historicalSamples(), generatedAt: NOW });
  assert.ok(verifyReceiptDigest(receipt));
  assert.equal(receiptDigest(receipt), receipt.receipt_sha256);
});

test("the digest covers every field, including nested ones", () => {
  const receipt = buildReceipt({ samples: historicalSamples(), generatedAt: NOW });
  const tampered = [
    { ...receipt, status: "pass" },
    { ...receipt, warm: { ...receipt.warm, p95_ms: 100 } },
    { ...receipt, max_rss_growth_bytes: 0 },
    { ...receipt, browser_pids: 1_000 },
    { ...receipt, rss: { ...receipt.rss, baseline_bytes: 1 } },
    { ...receipt, slo: { ...receipt.slo, warm_p95_ms_max: 20_000 } },
    {
      ...receipt,
      gates: receipt.gates.map((entry) => ({ ...entry, verdict: "pass" })),
    },
  ];
  for (const candidate of tampered) {
    assert.equal(verifyReceiptDigest(candidate), false);
  }
});

test("the digest is stable under key reordering", () => {
  const receipt = buildReceipt({ samples: historicalSamples(), generatedAt: NOW });
  const reordered = Object.fromEntries(Object.entries(receipt).reverse());
  assert.ok(verifyReceiptDigest(reordered));
  assert.equal(canonicalJson(receipt), canonicalJson(reordered));
});

test("a different clock is a different receipt", () => {
  const first = buildReceipt({ samples: historicalSamples(), generatedAt: NOW });
  const second = buildReceipt({
    samples: historicalSamples(),
    generatedAt: "2026-08-06T19:41:00.000Z",
  });
  assert.notEqual(first.receipt_sha256, second.receipt_sha256);
});

test("a non-canonical generated_at is refused", () => {
  rejectsWith("generated_at_invalid", () =>
    buildReceipt({ samples: historicalSamples(), generatedAt: "2026-08-06" }),
  );
  rejectsWith("generated_at_invalid", () =>
    buildReceipt({ samples: historicalSamples() }),
  );
});

// ---------------------------------------------------------------------------
// Redaction: a closed vocabulary
// ---------------------------------------------------------------------------

test("nothing outside the vocabulary can appear in a receipt", () => {
  const receipt = buildReceipt({ samples: historicalSamples(), generatedAt: NOW });
  for (const injected of [
    { ...receipt, prompt: "what is the capital of France" },
    { ...receipt, profile_path: "/home/oracle/.config/chrome" },
    { ...receipt, endpoint: "http://192.0.2.1:9222" },
    { ...receipt, cookie: "__Secure-next-auth.session-token=abc" },
  ]) {
    rejectsWith("receipt_unsafe", () => assertReceiptSafe(injected));
  }
});

test("a known key cannot be used to smuggle a string", () => {
  const receipt = buildReceipt({ samples: historicalSamples(), generatedAt: NOW });
  // `code` is a real receipt key, but only this module's own codes fit it.
  rejectsWith("receipt_unsafe", () =>
    assertReceiptSafe({ ...receipt, cold: { ...receipt.cold, code: "GET /c/abc123" } }),
  );
  // `count` holds a number and must never hold text.
  rejectsWith("receipt_unsafe", () =>
    assertReceiptSafe({ ...receipt, cold: { ...receipt.cold, count: "three" } }),
  );
  rejectsWith("receipt_unsafe", () =>
    assertReceiptSafe({ ...receipt, model: "eyJhbGciOi.eyJzdWIiOi.SflKxwRJSM" }),
  );
  rejectsWith("receipt_unsafe", () =>
    assertReceiptSafe({ ...receipt, status: "probably fine" }),
  );
});

test("a non-finite number cannot reach a receipt", () => {
  const receipt = buildReceipt({ samples: historicalSamples(), generatedAt: NOW });
  rejectsWith("receipt_unsafe", () =>
    assertReceiptSafe({
      ...receipt,
      warm: { ...receipt.warm, p95_ms: Number.POSITIVE_INFINITY },
    }),
  );
});

test("the serialized receipt contains no sensitive marker at all", () => {
  const receipt = buildReceipt({ samples: historicalSamples(), generatedAt: NOW });
  const encoded = JSON.stringify(receipt);
  for (const marker of ["cookie", "bearer", "token", "prompt", "http://", "https://"]) {
    assert.ok(!encoded.toLowerCase().includes(marker), `receipt leaked ${marker}`);
  }
  // Raw PIDs are read from the samples and discarded; only the count survives.
  assert.ok(!encoded.includes("4242"));
});

// ---------------------------------------------------------------------------
// Live collection through injected probes
// ---------------------------------------------------------------------------

function recordingProbes({ warmDuration = 3000 } = {}) {
  const calls = [];
  let pid = 4242;
  let rss = RSS_BASELINE;
  let tick = 0;
  return {
    calls,
    probe: async ({ phase, index }) => {
      calls.push(`${phase}:${index}`);
      return {
        duration_ms: phase === "cold" ? 8000 + index : warmDuration + index,
        outcome: "ok",
      };
    },
    rssProbe: async ({ index }) => {
      calls.push(`rss:${index}`);
      rss += 1000;
      return { root_pid: pid, rss_bytes: rss };
    },
    clock: () => {
      tick += 1;
      return new Date(Date.parse(STARTED_AT) + tick * 1000).toISOString();
    },
  };
}

test("collection runs cold, then baseline RSS, then warm-with-RSS", () => {
  return (async () => {
    const probes = recordingProbes();
    const samples = await collectSamples({
      plan: { run_id: RUN_ID, model: "gpt-5-5-instant", cold_runs: 2, warm_runs: 3 },
      probe: probes.probe,
      rssProbe: probes.rssProbe,
      clock: probes.clock,
    });
    assert.deepEqual(probes.calls, [
      "cold:0",
      "cold:1",
      "rss:0",
      "warm:0",
      "rss:1",
      "warm:1",
      "rss:2",
      "warm:2",
      "rss:3",
    ]);
    // One baseline plus one reading after every warm call.
    assert.equal(samples.rss.length, samples.warm.length + 1);
    assert.equal(samples.cold.length, 2);
    // The collected set is directly summarizable; the two halves share a schema.
    const receipt = buildReceipt({ samples, generatedAt: NOW });
    assert.equal(receipt.run_id, RUN_ID);
    assert.equal(receipt.browser_pids, 1);
  })();
});

test("collection fails closed on a probe that returns the wrong shape", async () => {
  const probes = recordingProbes();
  const plan = { run_id: RUN_ID, model: "gpt-5-5-instant", cold_runs: 1, warm_runs: 1 };
  await assert.rejects(
    collectSamples({
      ...probes,
      plan,
      probe: async () => ({ duration_ms: 10, outcome: "ok", prompt: "hello" }),
    }),
    (error) => error.code === "probe_result_invalid",
  );
  await assert.rejects(
    collectSamples({ ...probes, plan, probe: async () => ({ duration_ms: -1, outcome: "ok" }) }),
    (error) => error.code === "probe_result_invalid",
  );
  await assert.rejects(
    collectSamples({ ...probes, plan, rssProbe: async () => ({ rss_bytes: 1 }) }),
    (error) => error.code === "rss_probe_result_invalid",
  );
});

test("collection refuses a missing probe or an invalid plan", async () => {
  const probes = recordingProbes();
  await assert.rejects(
    collectSamples({
      plan: { run_id: RUN_ID, model: "gpt-5-5-instant", cold_runs: 1, warm_runs: 1 },
      probe: probes.probe,
      rssProbe: probes.rssProbe,
    }),
    (error) => error.code === "probe_missing",
  );
  await assert.rejects(
    collectSamples({ ...probes, plan: { run_id: RUN_ID, cold_runs: 1, warm_runs: 1 } }),
    (error) => error.code === "plan_invalid",
  );
  await assert.rejects(
    collectSamples({
      ...probes,
      plan: { run_id: RUN_ID, model: "gpt-5-5-instant", cold_runs: 0, warm_runs: 1 },
    }),
    (error) => error.code === "plan_invalid",
  );
});

// ---------------------------------------------------------------------------
// Gates, directly
// ---------------------------------------------------------------------------

test("gate comparators are the ones the SLO table states", () => {
  const slo = parseSlo(DEFAULT_SLO);
  const gates = evaluateGates(
    { cold: { p95_ms: 12_000 }, warm: { p95_ms: 4_000, successful: 20 }, browser_pids: 1, max_rss_growth_bytes: 104_857_600 },
    slo,
  );
  const byGate = Object.fromEntries(gates.map((entry) => [entry.gate, entry]));
  // Latency targets are inclusive; the RSS budget is not.
  assert.equal(byGate.cold_cli_to_submit_p95.verdict, "pass");
  assert.equal(byGate.warm_browser_to_submit_p95.verdict, "pass");
  assert.equal(byGate.warm_successful_runs.verdict, "pass");
  assert.equal(byGate.max_rss_growth_bytes.verdict, "fail");
});

test("a second browser PID fails the gate", () => {
  const gates = evaluateGates(
    { cold: { p95_ms: 1 }, warm: { p95_ms: 1, successful: 20 }, browser_pids: 2, max_rss_growth_bytes: 0 },
    parseSlo(DEFAULT_SLO),
  );
  const pids = gates.find((entry) => entry.gate === "browser_pids");
  assert.equal(pids.verdict, "fail");
  assert.equal(pids.code, "browser_pids_missed");
});

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

async function withSamplesFile(samples, body) {
  const directory = await mkdtemp(join(tmpdir(), "oracle-benchmark-"));
  try {
    const path = join(directory, "samples.json");
    await writeFile(path, JSON.stringify(samples), "utf8");
    return await body(path, directory);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

function capture() {
  const chunks = [];
  return { chunks, write: (text) => chunks.push(text) };
}

test("the CLI summarizes a recorded run and exits non-zero on a failure", async () => {
  await withSamplesFile(historicalSamples(), async (path) => {
    const output = capture();
    const code = await main(["--samples", path, "--json", "--now", NOW], output);
    assert.equal(code, EXIT_FAIL);
    const receipt = JSON.parse(output.chunks.join(""));
    assert.equal(receipt.status, "fail");
    assert.equal(receipt.warm.p95_ms, 9614.340436);
    assert.equal(
      receipt.receipt_sha256,
      buildReceipt({ samples: historicalSamples(), generatedAt: NOW }).receipt_sha256,
    );
  });
});

test("the human line carries the four numbers the bead asks for", async () => {
  await withSamplesFile(historicalSamples(), async (path) => {
    const output = capture();
    await main(["--samples", path, "--now", NOW], output);
    const line = output.chunks.join("");
    assert.match(line, /^fail /);
    assert.match(line, /cold_p95=7273\.8893/);
    assert.match(line, /warm_p95=9614\.340436/);
    assert.match(line, /browser_pids=1/);
    assert.match(line, /max_rss_growth_bytes=14237696/);
    assert.match(line, /sha256=[0-9a-f]{64}/);
  });
});

test("a degraded run exits zero, or three under --require-complete", async () => {
  await withSamplesFile(passingSamples(), async (path) => {
    const first = capture();
    assert.equal(
      await main(["--samples", path, "--now", NOW], first),
      EXIT_PASS,
    );
    assert.match(first.chunks.join(""), /^degraded /);
    const second = capture();
    assert.equal(
      await main(["--samples", path, "--now", NOW, "--require-complete"], second),
      EXIT_INCOMPLETE,
    );
  });
});

test("the CLI refuses missing, unreadable, or malformed input", async () => {
  for (const argv of [
    [],
    ["--json"],
    ["--samples", "/nonexistent/samples.json"],
    ["--samples"],
    ["--samples", "x.json", "--unknown"],
    ["--samples", "x.json", "--live"],
  ]) {
    const output = capture();
    assert.equal(await main(argv, output), EXIT_USAGE);
    const parsed = JSON.parse(output.chunks.join(""));
    assert.equal(parsed.status, "error");
    assert.match(parsed.code, /^[a-z][a-z0-9_]+$/);
  }
});

test("a malformed sample file is refused rather than summarized", async () => {
  await withSamplesFile(
    historicalSamples({ warm: latencySamples([-5]) }),
    async (path) => {
      const output = capture();
      assert.equal(await main(["--samples", path, "--now", NOW], output), EXIT_USAGE);
      assert.equal(JSON.parse(output.chunks.join("")).code, "sample_invalid");
    },
  );
});

test("an override SLO is honoured and recorded in the receipt", async () => {
  await withSamplesFile(historicalSamples(), async (path, directory) => {
    const sloPath = join(directory, "slo.json");
    await writeFile(
      sloPath,
      JSON.stringify({ ...DEFAULT_SLO, warm_p95_ms_max: 10_000 }),
      "utf8",
    );
    const output = capture();
    const code = await main(
      ["--samples", path, "--slo", sloPath, "--json", "--now", NOW],
      output,
    );
    // The measurement is unchanged; only the declared target moved, and the
    // receipt carries the target it was judged against.
    assert.equal(code, EXIT_PASS);
    const receipt = JSON.parse(output.chunks.join(""));
    assert.equal(receipt.status, "degraded");
    assert.equal(receipt.slo.warm_p95_ms_max, 10_000);
    assert.equal(receipt.warm.p95_ms, 9614.340436);
  });
});
