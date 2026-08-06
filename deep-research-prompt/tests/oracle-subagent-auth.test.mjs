import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  chmod,
  lstat,
  mkdtemp,
  readFile,
  realpath,
  rm,
  stat,
  symlink,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  AUTH_OBSERVATION_SCHEMA,
  AUTH_POLICY_SCHEMA,
  AUTH_REPORT_SCHEMA,
  authPageProbeSource,
  canonicalProCapability,
  deriveAccountCapability,
  evaluateAuthDoctor,
  isPermittedLoginTarget,
  loginCandidateReady,
  loginPreflightReady,
  normalizeChatGptUrl,
  parseListenerRecords,
  readAuthPolicy,
  sameBrowserContext,
  writeAuthPolicy,
} from "../assets/scripts/oracle-subagent-auth.mjs";

const NOW = "2026-07-28T07:00:00.000Z";
const OBSERVED_AT = "2026-07-28T06:59:55.000Z";
const PROFILE_FINGERPRINT = "a".repeat(64);
const ACCOUNT_FINGERPRINT = "b".repeat(64);

function observation(overrides = {}) {
  return {
    schema: AUTH_OBSERVATION_SCHEMA,
    observed_at: OBSERVED_AT,
    profile_fingerprint: PROFILE_FINGERPRINT,
    account_fingerprint: ACCOUNT_FINGERPRINT,
    session_state: "authenticated",
    challenge: {
      present: false,
      observed_at: null,
    },
    project_access: "granted",
    pro_plan: true,
    pro_model_available: true,
    deep_research_available: true,
    composer_available: true,
    ...overrides,
  };
}

function policy(overrides = {}) {
  return {
    schema: AUTH_POLICY_SCHEMA,
    profile_fingerprint: PROFILE_FINGERPRINT,
    account_fingerprint: ACCOUNT_FINGERPRINT,
    enrolled_at: "2026-07-28T06:00:00.000Z",
    ...overrides,
  };
}

function healthyInput(overrides = {}) {
  return {
    receipt_observed_at: OBSERVED_AT,
    observation: observation(),
    policy: policy(),
    security: {
      runtime_private: true,
      receipt_private: true,
      profile_private: true,
      policy_private: true,
    },
    transport: {
      single_listener: true,
      loopback_only: true,
      pid_matches: true,
      target_matches: true,
      hidden: true,
    },
    now: NOW,
    ...overrides,
  };
}

async function workspace(t) {
  const directory = await mkdtemp(path.join(os.tmpdir(), "oracle-auth-test-"));
  await chmod(directory, 0o700);
  t.after(async () => {
    await rm(directory, { recursive: true, force: true });
  });
  return realpath(directory);
}

test("healthy enrolled Pro session is the only ready state", () => {
  const report = evaluateAuthDoctor(healthyInput());
  assert.equal(report.schema, AUTH_REPORT_SCHEMA);
  assert.equal(report.ok, true);
  assert.equal(report.state, "ready");
  assert.deepEqual(report.reasons, []);
  assert.equal(Object.values(report.checks).every(Boolean), true);
});

test("launcher whole-second RFC3339 receipts are accepted", () => {
  const report = evaluateAuthDoctor(
    healthyInput({
      receipt_observed_at: "2026-07-28T06:59:55Z",
    }),
  );
  assert.equal(report.ok, true);
});

test("logged-out and ambiguous sessions fail even when account endpoints answered", () => {
  const loggedOut = evaluateAuthDoctor(
    healthyInput({
      observation: observation({
        account_fingerprint: null,
        session_state: "guest",
        pro_plan: false,
        pro_model_available: false,
      }),
    }),
  );
  assert.equal(loggedOut.ok, false);
  assert.ok(loggedOut.reasons.includes("logged_out"));
  assert.ok(loggedOut.reasons.includes("wrong_account"));
  assert.ok(loggedOut.reasons.includes("pro_plan_missing"));
  assert.ok(loggedOut.reasons.includes("pro_model_missing"));

  const ambiguous = evaluateAuthDoctor(
    healthyInput({
      observation: observation({ session_state: "ambiguous" }),
    }),
  );
  assert.ok(ambiguous.reasons.includes("auth_ambiguous"));
});

test("wrong account and wrong profile are rejected only by fingerprints", () => {
  const report = evaluateAuthDoctor(
    healthyInput({
      observation: observation({
        profile_fingerprint: "c".repeat(64),
        account_fingerprint: "d".repeat(64),
      }),
    }),
  );
  assert.equal(report.ok, false);
  assert.ok(report.reasons.includes("profile_mismatch"));
  assert.ok(report.reasons.includes("wrong_account"));
  const encoded = JSON.stringify(report);
  assert.doesNotMatch(encoded, /a{16}|b{16}|c{16}|d{16}/);
});

test("denied and ambiguous project routes fail closed", () => {
  const denied = evaluateAuthDoctor(
    healthyInput({
      observation: observation({ project_access: "denied" }),
    }),
  );
  assert.ok(denied.reasons.includes("project_denied"));

  const ambiguous = evaluateAuthDoctor(
    healthyInput({
      observation: observation({ project_access: "ambiguous" }),
    }),
  );
  assert.ok(ambiguous.reasons.includes("project_access_ambiguous"));

  const root = evaluateAuthDoctor(
    healthyInput({
      observation: observation({ project_access: "not_requested" }),
    }),
  );
  assert.equal(root.ok, true);
});

test("fresh and stale browser challenges have distinct hard failures", () => {
  const fresh = evaluateAuthDoctor(
    healthyInput({
      observation: observation({
        challenge: {
          present: true,
          observed_at: OBSERVED_AT,
        },
      }),
    }),
  );
  assert.ok(fresh.reasons.includes("challenge_present"));
  assert.equal(fresh.reasons.includes("stale_challenge"), false);

  const stale = evaluateAuthDoctor(
    healthyInput({
      observation: observation({
        challenge: {
          present: true,
          observed_at: "2026-07-28T06:30:00.000Z",
        },
      }),
    }),
  );
  assert.ok(stale.reasons.includes("stale_challenge"));
  assert.equal(stale.reasons.includes("challenge_present"), false);
});

test("wrong permissions, wildcard CDP, wrong PID, and wrong target all fail", () => {
  const report = evaluateAuthDoctor(
    healthyInput({
      security: {
        runtime_private: true,
        receipt_private: false,
        profile_private: true,
        policy_private: true,
      },
      transport: {
        single_listener: false,
        loopback_only: false,
        pid_matches: false,
        target_matches: false,
        hidden: false,
      },
    }),
  );
  for (const reason of [
    "wrong_permissions",
    "listener_ambiguous",
    "wildcard_cdp",
    "browser_pid_mismatch",
    "exact_target_mismatch",
    "browser_visible",
  ]) {
    assert.ok(report.reasons.includes(reason), reason);
  }
});

test("missing Pro plan or actual Pro model capability is never accepted", () => {
  const planMissing = evaluateAuthDoctor(
    healthyInput({
      observation: observation({ pro_plan: false }),
    }),
  );
  assert.ok(planMissing.reasons.includes("pro_plan_missing"));

  const modelMissing = evaluateAuthDoctor(
    healthyInput({
      observation: observation({ pro_model_available: false }),
    }),
  );
  assert.ok(modelMissing.reasons.includes("pro_model_missing"));
});

test("live capability classifiers require canonical available Pro model and unique Pro account", () => {
  assert.deepEqual(
    canonicalProCapability({
      models: [
        { slug: "gpt-5-5", title: "GPT Pro" },
        { slug: "gpt-5-5-pro", unavailable_reason: "upgrade" },
        { slug: "gpt-5-4-pro", enabled: false },
      ],
    }),
    { available: false, identifiers: [] },
  );
  assert.deepEqual(
    canonicalProCapability({
      models: [{ slug: "gpt-5-5-pro", title: "Irrelevant display text" }],
    }),
    { available: true, identifiers: ["gpt-5-5-pro"] },
  );
  assert.deepEqual(
    canonicalProCapability(
      {
        models: [{ slug: "gpt-5-6-sol", title: "GPT-5.6 Sol" }],
      },
      true,
    ),
    { available: true, identifiers: ["ui-selected-pro-effort"] },
  );
  assert.deepEqual(
    canonicalProCapability({ models: [] }, true),
    { available: false, identifiers: [] },
  );

  const meResponse = { ok: true, body: { id: "user-synthetic" } };
  const proEntry = {
    can_access_with_session: true,
    account: {
      account_id: "workspace-pro",
      plan_type: "pro",
      is_deactivated: false,
    },
    entitlement: {
      has_active_subscription: true,
      is_delinquent: false,
      subscription_plan: "chatgptproplan",
    },
    features: ["deep_research"],
  };
  const accountsResponse = {
    ok: true,
    body: {
      // Ordering is intentionally misleading and must not choose the plan.
      account_ordering: ["free", "paid"],
      accounts: {
        free: {
          can_access_with_session: true,
          account: { account_id: "workspace-free", plan_type: "free" },
          entitlement: { has_active_subscription: false },
          features: [],
        },
        paid: proEntry,
      },
    },
  };
  const capability = deriveAccountCapability(
    meResponse,
    accountsResponse,
    false,
    true,
  );
  assert.equal(capability.session_state, "authenticated");
  assert.equal(capability.pro_plan, true);
  assert.equal(
    capability.account_identity,
    "user-synthetic\0workspace-pro",
  );
  assert.deepEqual(capability.features, ["deep_research"]);

  const ambiguousPro = deriveAccountCapability(
    meResponse,
    {
      ok: true,
      body: {
        accounts: {
          one: proEntry,
          two: {
            ...structuredClone(proEntry),
            account: {
              ...structuredClone(proEntry.account),
              account_id: "workspace-pro-two",
            },
          },
        },
      },
    },
    false,
    true,
  );
  assert.equal(ambiguousPro.pro_plan, false);
  assert.equal(ambiguousPro.account_identity, null);
});

test("current Pro UI contract overrides stale free-plan metadata without weakening identity proof", () => {
  const meResponse = { ok: true, body: { id: "user-synthetic" } };
  const freeMetadataEntry = {
    can_access_with_session: true,
    account: {
      plan_type: "guest",
      is_deactivated: false,
    },
    entitlement: {
      has_active_subscription: false,
      is_delinquent: false,
      subscription_plan: "free",
    },
    features: [],
  };
  const accountsResponse = {
    ok: true,
    body: { accounts: { current: freeMetadataEntry } },
  };

  const capability = deriveAccountCapability(
    meResponse,
    accountsResponse,
    true,
    true,
    true,
  );
  assert.equal(capability.session_state, "authenticated");
  assert.equal(capability.pro_plan, true);
  assert.equal(
    capability.account_identity,
    "user-synthetic\0current",
  );

  const noUiProof = deriveAccountCapability(
    meResponse,
    accountsResponse,
    false,
    true,
    false,
  );
  assert.equal(noUiProof.session_state, "authenticated");
  assert.equal(noUiProof.pro_plan, false);
  assert.equal(noUiProof.account_identity, null);

  const ambiguousWorkspace = deriveAccountCapability(
    meResponse,
    {
      ok: true,
      body: {
        accounts: {
          one: freeMetadataEntry,
          two: {
            ...structuredClone(freeMetadataEntry),
            account: {
              ...structuredClone(freeMetadataEntry.account),
              account_id: "workspace-other",
            },
          },
        },
      },
    },
    false,
    true,
    true,
  );
  assert.equal(ambiguousWorkspace.pro_plan, false);
  assert.equal(ambiguousWorkspace.account_identity, null);
});

test("stale receipts and observations are independent failures", () => {
  const report = evaluateAuthDoctor(
    healthyInput({
      receipt_observed_at: "2026-07-28T06:00:00.000Z",
      observation: observation({
        observed_at: "2026-07-28T06:58:00.000Z",
      }),
    }),
  );
  assert.ok(report.reasons.includes("browser_receipt_stale"));
  assert.ok(report.reasons.includes("auth_observation_stale"));
});

test("policy enrollment is explicit and login ignores visibility only", () => {
  const missingPolicy = evaluateAuthDoctor(
    healthyInput({
      policy: null,
      transport: {
        single_listener: true,
        loopback_only: true,
        pid_matches: true,
        target_matches: true,
        hidden: false,
      },
    }),
  );
  assert.deepEqual(missingPolicy.reasons, [
    "browser_visible",
    "auth_policy_missing",
  ]);
  assert.equal(loginCandidateReady(missingPolicy, false), true);

  const wrongAccount = evaluateAuthDoctor(
    healthyInput({
      observation: observation({
        account_fingerprint: "e".repeat(64),
      }),
      transport: {
        single_listener: true,
        loopback_only: true,
        pid_matches: true,
        target_matches: true,
        hidden: false,
      },
    }),
  );
  assert.equal(loginCandidateReady(wrongAccount, true), false);
});

test("login preflight rejects unsafe reveal and browser rollover", () => {
  const healthy = evaluateAuthDoctor(healthyInput());
  assert.equal(loginPreflightReady(healthy), true);

  const unsafe = evaluateAuthDoctor(
    healthyInput({
      transport: {
        single_listener: true,
        loopback_only: false,
        pid_matches: true,
        target_matches: true,
        hidden: true,
      },
    }),
  );
  assert.equal(loginPreflightReady(unsafe), false);

  const context = {
    receipt: {
      schema: "oracle-subagent.browser.v1",
      pid: 1234,
      port: 9222,
      profile_root: "/private/profile",
      profile_directory: "Default",
      target_id: "ABCDEF0123456789",
      target_url: "https://chatgpt.com/",
      observed_at: OBSERVED_AT,
    },
    paths: { runtimeRoot: "/private/runtime" },
    browserWebSocket: "ws://127.0.0.1:9222/devtools/browser/one",
  };
  assert.equal(sameBrowserContext(context, structuredClone(context)), true);
  const rollover = structuredClone(context);
  rollover.receipt.target_id = "ABCDEF0123456790";
  assert.equal(sameBrowserContext(context, rollover), false);
});

test("explicit login permits only the pinned target's ChatGPT auth route", () => {
  const requested =
    "https://chatgpt.com/g/g-p-local-proof/project";
  assert.equal(
    isPermittedLoginTarget(
      requested,
      "https://chatgpt.com/auth/login?next=%2Fg%2Fg-p-local-proof%2Fproject",
    ),
    true,
  );
  assert.equal(
    isPermittedLoginTarget(requested, "https://chatgpt.com/auth"),
    true,
  );
  assert.equal(
    isPermittedLoginTarget(requested, "https://chatgpt.com/"),
    true,
  );
  assert.equal(
    isPermittedLoginTarget(
      "https://chatgpt.com/c/not-a-project",
      "https://chatgpt.com/auth/login",
    ),
    false,
  );
  for (const observed of [
    "http://chatgpt.com/auth/login",
    "https://chatgpt.com:443/auth/login",
    "https://user@chatgpt.com/auth/login",
    "https://chatgpt.com/auth/login#fragment",
    "https://chatgpt.com/auth#",
    "https://chatgpt.com/auth?",
    "https://chatgpt.com/auth?#",
    "https://chatgpt.com/authentic",
    "https://chatgpt.com/?next=project",
    "https://chatgpt.com/?",
    "https://chatgpt.com/#",
    "https://chatgpt.com/?#",
    "https://chatgpt.com/c/conversation",
    "https://evil.example/auth/login",
  ]) {
    assert.equal(
      isPermittedLoginTarget(requested, observed),
      false,
      observed,
    );
  }
});

test("receipt target accepts only exact canonical root or Project URLs", () => {
  const project =
    "https://chatgpt.com/g/g-p-local-proof/project";
  assert.equal(normalizeChatGptUrl("https://chatgpt.com/"), "https://chatgpt.com/");
  assert.equal(normalizeChatGptUrl(project), project);
  for (const candidate of [
    "https://chatgpt.com:443/",
    "https://chatgpt.com/?",
    "https://chatgpt.com/#",
    "https://chatgpt.com/?#",
    `${project}?`,
    `${project}#`,
    "https://chatgpt.com/c/not-a-project",
  ]) {
    assert.throws(
      () => normalizeChatGptUrl(candidate),
      /auth gate failed/,
    );
  }
});

test("listener parser preserves exact bind evidence for wildcard rejection", () => {
  const loopback = parseListenerRecords(
    "p58193\ncGoogle Chrome\nu501\nf64\nn127.0.0.1:9222\n",
  );
  assert.deepEqual(loopback, [
    {
      pid: 58193,
      uid: 501,
      command: "Google Chrome",
      names: ["127.0.0.1:9222"],
    },
  ]);
  const wildcard = parseListenerRecords(
    "p58193\ncGoogle Chrome\nu501\nf64\nn*:9222\n",
  );
  assert.equal(wildcard[0].names[0], "*:9222");
  assert.notEqual(wildcard[0].names[0], "127.0.0.1:9222");
});

test("policy file is private, single-link, immutable, and non-echoing", async (t) => {
  const directory = await workspace(t);
  const pathname = path.join(directory, "auth-policy.json");
  await writeAuthPolicy(pathname, policy());
  const metadata = await stat(pathname);
  assert.equal(metadata.mode & 0o777, 0o600);
  assert.equal(metadata.nlink, 1);
  assert.deepEqual(await readAuthPolicy(pathname), policy());

  await assert.rejects(writeAuthPolicy(pathname, policy()), /auth gate failed/);
  assert.deepEqual(JSON.parse(await readFile(pathname, "utf8")), policy());

  const malformed = path.join(directory, "malformed.json");
  await writeFile(malformed, '{"account_fingerprint":"never-echo', {
    mode: 0o600,
  });
  await assert.rejects(
    readAuthPolicy(malformed),
    (error) => {
      assert.doesNotMatch(error.message, /account|never-echo|fingerprint/);
      return true;
    },
  );

  const permissive = path.join(directory, "permissive.json");
  await writeFile(permissive, JSON.stringify(policy()), { mode: 0o644 });
  await chmod(permissive, 0o644);
  await assert.rejects(readAuthPolicy(permissive), /auth gate failed/);

  const linked = path.join(directory, "linked.json");
  await symlink(pathname, linked);
  assert.equal((await lstat(linked)).isSymbolicLink(), true);
  await assert.rejects(readAuthPolicy(linked), /auth gate failed/);
});

test("strict inputs and reports cannot echo identity or attacker fields", () => {
  const privateIdentity = "owner@example.test";
  assert.throws(
    () =>
      evaluateAuthDoctor(
        healthyInput({
          observation: {
            ...observation(),
            email: privateIdentity,
          },
        }),
      ),
    (error) => {
      assert.doesNotMatch(error.message, /owner|example|email/);
      return true;
    },
  );
  const report = evaluateAuthDoctor(healthyInput());
  assert.doesNotMatch(JSON.stringify(report), /account_fingerprint|profile_fingerprint/);

  const script = path.resolve(
    "deep-research-prompt/assets/scripts/oracle-subagent-auth.mjs",
  );
  const attackerCommand =
    "https://chatgpt.com/auth?target=TARGET-ABCDEF0123456789";
  for (const flags of [[], ["--json"]]) {
    const attempted = spawnSync(
      process.execPath,
      [script, attackerCommand, ...flags],
      {
        cwd: path.resolve("."),
        encoding: "utf8",
      },
    );
    assert.equal(attempted.status, 2);
    assert.doesNotMatch(attempted.stdout, /TARGET-ABCDEF0123456789/);
    assert.doesNotMatch(attempted.stdout, /chatgpt\.com/);
    if (flags.length > 0) {
      const parsed = JSON.parse(attempted.stdout);
      assert.equal(parsed.command, "unknown");
      assert.deepEqual(parsed.reasons, ["usage"]);
    }
  }
});

test("page probe is observation-only and contains no credential extraction or send path", () => {
  const source = authPageProbeSource();
  assert.match(source, /backend-api\/me/);
  assert.match(source, /backend-api\/models/);
  assert.doesNotMatch(source, /document\.cookie/);
  assert.doesNotMatch(source, /localStorage|sessionStorage/);
  assert.doesNotMatch(source, /Network\.get|Storage\.get/);
  assert.doesNotMatch(source, /Input\.|dispatchEvent|\.click\(/);
  assert.doesNotMatch(source, /send-button|composer-submit|Send prompt/);
  assert.match(source, /\^gpt-/);
  assert.match(source, /ui-selected-pro-effort/);
  assert.match(source, /accounts-profile-button/);
  assert.match(source, /composerForm/);
  assert.doesNotMatch(source, /modelLabels|account_ordering\[0\]/);
  assert.match(source, /location\.href === requested\.href/);
  assert.match(source, /g-p-\[A-Za-z0-9_-\]\{8,128\}/);
  assert.doesNotMatch(source, /normalizedPath|endsWith\(["']\\\/["']\)/);
});
