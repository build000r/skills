import assert from "node:assert/strict";
import test from "node:test";

import {
  HEALABLE_REASONS,
  remediationForAuthReport,
} from "../assets/scripts/oracle-session-heal.mjs";

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
