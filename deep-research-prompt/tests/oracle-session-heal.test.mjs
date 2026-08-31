import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  HEALABLE_REASONS,
  remediationForAuthReport,
} from "../assets/scripts/oracle-session-heal.mjs";

const HEAL_URL = new URL(
  "../assets/scripts/oracle-session-heal.mjs",
  import.meta.url,
);

test("healable reasons cover the session restore + enroll path", () => {
  for (const reason of [
    "logged_out",
    "auth_policy_missing",
    "browser_receipt_stale",
    "exact_target_mismatch",
  ]) {
    assert.ok(HEALABLE_REASONS.includes(reason), reason);
  }
});

test("remediation for logged_out points at doctor auto-heal and portable credential", () => {
  const text = remediationForAuthReport(
    {
      reasons: ["logged_out", "auth_policy_missing"],
      checks: { authenticated: false },
    },
    { invokedAs: "sbp oracle" },
  );
  assert.match(text, /Blocked by: logged_out, auth_policy_missing/);
  assert.match(text, /sbp oracle --doctor/);
  assert.match(text, /portable credential/);
  assert.match(text, /oracle-credential\.mjs/);
});

test("remediation for auth_policy_missing alone names enroll when already signed in", () => {
  const text = remediationForAuthReport(
    {
      reasons: ["auth_policy_missing"],
      checks: { authenticated: true },
    },
    { invokedAs: "sbp oracle" },
  );
  assert.match(text, /login --enroll-current-account/);
});

test("remediation for stale receipt points at launcher refresh", () => {
  const text = remediationForAuthReport(
    {
      reasons: ["browser_receipt_stale"],
      checks: { receipt_fresh: false },
    },
    { invokedAs: "sbp oracle" },
  );
  assert.match(text, /launch-chatgpt-cdp\.sh/);
});

/* ------------------------------------------------------------------ *
 * CDP port — heal resolves through the canonical matrix, and is the ONLY
 * entrypoint that opts into the browser-receipt level (a heal must reach
 * the browser the last launch actually bound).
 * ------------------------------------------------------------------ */

test("heal delegates port resolution to oracle-cdp-port.mjs with the receipt opt-in", async () => {
  const src = await readFile(HEAL_URL, "utf8");
  assert.match(src, /from "\.\/oracle-cdp-port\.mjs"/);
  assert.match(src, /receiptPath:\s*join\(runtimeRoot\(\), "browser\.json"\)/);
  assert.equal(
    src.includes("Number(process.env.ORACLE_CDP_PORT)"),
    false,
    "no local re-implementation of the env level",
  );
});

test("an invalid explicit --port fails closed before any heal step runs", () => {
  const result = spawnSync(
    process.execPath,
    [fileURLToPath(HEAL_URL), "--port", "not-a-port", "--json"],
    {
      encoding: "utf8",
      env: {
        ...process.env,
        // Hermetic: no host config, env, or receipt may rescue the bad value.
        ORACLE_CONFIG_PATH: "/nonexistent/oracle-config.json",
        ORACLE_CDP_PORT: "",
        ORACLE_SUBAGENT_RUNTIME_DIR: "/nonexistent/oracle-runtime",
      },
      timeout: 30_000,
    },
  );
  assert.equal(result.status, 2, result.stderr);
  assert.match(result.stderr, /invalid CDP port/);
  assert.match(result.stderr, /explicit argument/);
  assert.equal(result.stdout, "", "no heal output may follow a port failure");
});

test("an out-of-range explicit --port fails the same way", () => {
  const result = spawnSync(
    process.execPath,
    [fileURLToPath(HEAL_URL), "--port", "70000"],
    {
      encoding: "utf8",
      env: {
        ...process.env,
        ORACLE_CONFIG_PATH: "/nonexistent/oracle-config.json",
        ORACLE_CDP_PORT: "",
        ORACLE_SUBAGENT_RUNTIME_DIR: "/nonexistent/oracle-runtime",
      },
      timeout: 30_000,
    },
  );
  assert.equal(result.status, 2, result.stderr);
  assert.match(result.stderr, /invalid CDP port/);
});
