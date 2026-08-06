/**
 * Regression fixture for the launcher→doctor hydration settle race.
 *
 * launch-chatgpt-cdp.sh mints a brand-new blank target; the auth doctor at
 * t+0s reports composer_missing / wrong_account / pro_*_missing on an
 * unhydrated tab. Bounded readiness poll (waitForBrowserAuthReady) must keep
 * retrying until ready, not fail on the first blocked observation.
 *
 * Run:
 *   node --test ./oracle-subagent-preflight.test.mjs
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  BROWSER_SETTLE_DEADLINE_MS,
  BROWSER_SETTLE_POLL_MS,
  isAuthDoctorReady,
  waitForBrowserAuthReady,
} from "./oracle-subagent.mjs";

function blockedReport(reasons = ["composer_missing", "wrong_account"]) {
  return {
    schema: "oracle-subagent.auth-report.v1",
    command: "doctor",
    ok: false,
    state: "blocked",
    reasons,
    checks: {},
  };
}

function readyReport() {
  return {
    schema: "oracle-subagent.auth-report.v1",
    command: "doctor",
    ok: true,
    state: "ready",
    reasons: [],
    checks: { composer: true },
  };
}

test("isAuthDoctorReady requires ok and state=ready", () => {
  assert.equal(isAuthDoctorReady(readyReport()), true);
  assert.equal(isAuthDoctorReady(blockedReport()), false);
  assert.equal(isAuthDoctorReady(null), false);
  assert.equal(isAuthDoctorReady({ ok: true, state: "blocked" }), false);
  assert.equal(isAuthDoctorReady({ ok: false, state: "ready" }), false);
});

test("settle constants are bounded, not a fixed one-shot sleep", () => {
  assert.equal(BROWSER_SETTLE_DEADLINE_MS, 15_000);
  assert.equal(BROWSER_SETTLE_POLL_MS, 500);
  assert.ok(BROWSER_SETTLE_DEADLINE_MS > BROWSER_SETTLE_POLL_MS);
  // Measured settle window was ~1s; deadline must cover it with margin.
  assert.ok(BROWSER_SETTLE_DEADLINE_MS >= 1_000);
});

test("hydration race: first blocked doctor observations do not fail preflight", async () => {
  // Reproduces the verified 2026-07-28 baseline: t+0s blocked, t+1s ok.
  const sequence = [
    blockedReport([
      "wrong_account",
      "project_access_ambiguous",
      "pro_plan_missing",
      "pro_model_missing",
      "composer_missing",
    ]),
    blockedReport(["composer_missing"]),
    readyReport(),
  ];
  let calls = 0;
  let now = 0;
  let sleepCount = 0;

  const result = await waitForBrowserAuthReady({
    runDoctor: async () => {
      const report = sequence[Math.min(calls, sequence.length - 1)];
      calls += 1;
      return report;
    },
    sleep: async (milliseconds) => {
      sleepCount += 1;
      now += milliseconds;
    },
    nowMs: () => now,
    deadlineMs: 5_000,
    pollMs: 500,
  });

  assert.equal(result.ready, true);
  assert.equal(result.attempts, 3);
  assert.equal(sleepCount, 2);
  assert.equal(result.authReport.state, "ready");
  assert.equal(result.authReport.ok, true);
  // Elapsed settle time equals poll intervals between the three observations.
  assert.equal(now, 1_000);
});

test("hydration race: doctor process failures are retried until ready", async () => {
  let calls = 0;
  let now = 0;

  const result = await waitForBrowserAuthReady({
    runDoctor: async () => {
      calls += 1;
      if (calls === 1) throw new Error("child_failed");
      if (calls === 2) return blockedReport(["composer_missing"]);
      return readyReport();
    },
    sleep: async (milliseconds) => {
      now += milliseconds;
    },
    nowMs: () => now,
    deadlineMs: 5_000,
    pollMs: 250,
  });

  assert.equal(result.ready, true);
  assert.equal(result.attempts, 3);
  assert.equal(result.authReport.ok, true);
});

test("hydration race: immediate ready does not sleep", async () => {
  let sleptMs = 0;
  const result = await waitForBrowserAuthReady({
    runDoctor: async () => readyReport(),
    sleep: async (milliseconds) => {
      sleptMs += milliseconds;
    },
    nowMs: () => 0,
    deadlineMs: BROWSER_SETTLE_DEADLINE_MS,
    pollMs: BROWSER_SETTLE_POLL_MS,
  });

  assert.equal(result.ready, true);
  assert.equal(result.attempts, 1);
  assert.equal(sleptMs, 0);
});

test("hydration race: never-ready fails closed at deadline with last report", async () => {
  let now = 0;
  const last = blockedReport(["pro_plan_missing"]);

  const result = await waitForBrowserAuthReady({
    runDoctor: async () => last,
    sleep: async (milliseconds) => {
      now += milliseconds;
    },
    nowMs: () => now,
    deadlineMs: 1_500,
    pollMs: 500,
  });

  assert.equal(result.ready, false);
  assert.ok(result.attempts >= 2, `expected >=2 attempts, got ${result.attempts}`);
  assert.equal(result.authReport, last);
  assert.ok(now >= 1_500);
});

test("hydration race: total doctor throw leaves null report at deadline", async () => {
  let now = 0;
  const result = await waitForBrowserAuthReady({
    runDoctor: async () => {
      throw new Error("child_failed");
    },
    sleep: async (milliseconds) => {
      now += milliseconds;
    },
    nowMs: () => now,
    deadlineMs: 1_000,
    pollMs: 400,
  });

  assert.equal(result.ready, false);
  assert.equal(result.authReport, null);
  assert.ok(result.attempts >= 2);
});
