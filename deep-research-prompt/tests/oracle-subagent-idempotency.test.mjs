import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import {
  chmod,
  mkdtemp,
  mkdir,
  readFile,
  readdir,
  realpath,
  rename,
  rm,
  stat,
  symlink,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  IDEMPOTENCY_CLAIM_SCHEMA,
  OracleSubagentIdempotencyError,
  claimIdempotentRequest,
  idempotencyLayout,
} from "../assets/scripts/oracle-subagent-idempotency.mjs";
import {
  createReceiptFile,
  transitionReceiptFile,
  writeResultAtomic,
} from "../assets/scripts/oracle-subagent-state.mjs";

const FINGERPRINT = "a".repeat(64);
const SECOND_FINGERPRINT = "b".repeat(64);
const THIRD_FINGERPRINT = "c".repeat(64);
const BASE_TIME = Date.parse("2026-07-28T00:00:00.000Z");
const TARGET_ID = "target-idempotency-123";
const TARGET_URL = "https://chatgpt.com/";
const CONVERSATION_URL = "https://chatgpt.com/c/idempotency-123";

function at(offset) {
  return new Date(BASE_TIME + offset * 1_000).toISOString();
}

async function temporaryRoot(t) {
  const root = await realpath(
    await mkdtemp(path.join(os.tmpdir(), "oracle-idempotency-test-")),
  );
  t.after(async () => {
    await rm(root, { recursive: true, force: true });
  });
  return root;
}

async function holdAdvisoryLock(pathname) {
  const child = spawn(
    "/usr/bin/python3",
    [
      "-I",
      "-c",
      `
import fcntl
import os
import sys

descriptor = os.open(sys.argv[1], os.O_RDWR)
fcntl.flock(descriptor, fcntl.LOCK_EX)
print("locked", flush=True)
sys.stdin.buffer.read()
os.close(descriptor)
`,
      pathname,
    ],
    {
      env: { PATH: "/usr/bin:/bin", LANG: "C", LC_ALL: "C" },
      stdio: ["pipe", "pipe", "pipe"],
    },
  );
  child.stdout.setEncoding("utf8");
  await new Promise((resolvePromise, rejectPromise) => {
    child.once("error", rejectPromise);
    child.stdout.once("data", (chunk) => {
      if (chunk === "locked\n") resolvePromise();
      else rejectPromise(new Error("unexpected lock-holder output"));
    });
    child.once("exit", (code) => {
      if (code !== null) {
        rejectPromise(new Error(`lock holder exited ${code}`));
      }
    });
  });
  return child;
}

async function stopLockHolder(child) {
  const exited = new Promise((resolvePromise) =>
    child.once("exit", resolvePromise),
  );
  child.stdin.end();
  await exited;
}

async function fileExists(pathname) {
  try {
    await stat(pathname);
    return true;
  } catch (error) {
    if (error.code === "ENOENT") return false;
    throw error;
  }
}

async function spawnClaimChild(
  root,
  fingerprint,
  runId,
  ownerId,
  lockOptions = {},
) {
  const boundaryDelayMs = Math.max(
    lockOptions.postLedgerFsyncDelayMs ?? 0,
    lockOptions.postWitnessFsyncDelayMs ?? 0,
    lockOptions.postPublicationFsyncDelayMs ?? 0,
  );
  const moduleUrl = new URL(
    "../assets/scripts/oracle-subagent-idempotency.mjs",
    import.meta.url,
  ).href;
  const childScript = path.join(root, `${ownerId}.mjs`);
  await writeFile(
    childScript,
    `
import { claimIdempotentRequest } from ${JSON.stringify(moduleUrl)};
const boundaryDelayMs = ${boundaryDelayMs};
if (boundaryDelayMs > 0) {
  const originalSetTimeout = globalThis.setTimeout;
  globalThis.setTimeout = (callback, delay, ...arguments_) => {
    if (delay === boundaryDelayMs) process.stdout.write("boundary\\n");
    return originalSetTimeout(callback, delay, ...arguments_);
  };
}
const claim = await claimIdempotentRequest(process.argv[2], {
  request_fingerprint: process.argv[3],
  candidate_run_id: process.argv[4],
  owner_id: process.argv[5],
}, ${JSON.stringify(lockOptions)});
process.stdout.write(JSON.stringify({
  disposition: claim.disposition,
  send_authorized: claim.send_authorized,
}));
`,
    { mode: 0o600 },
  );
  const child = spawn(
    process.execPath,
    [childScript, root, fingerprint, runId, ownerId],
    {
      env: { PATH: process.env.PATH ?? "/usr/bin:/bin" },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  child.stderr.resume();
  return child;
}

async function waitForChildLine(child, expectedLine) {
  child.stdout.setEncoding("utf8");
  await new Promise((resolvePromise, rejectPromise) => {
    let output = "";
    child.stdout.on("data", (chunk) => {
      output += chunk;
      if (output.includes(expectedLine)) resolvePromise();
    });
    child.once("error", rejectPromise);
    child.once("exit", (code, signal) => {
      rejectPromise(
        new Error(
          `claim child exited before ${expectedLine.trim()}: ${code ?? signal}`,
        ),
      );
    });
  });
}

async function killChild(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const exited = new Promise((resolvePromise) =>
    child.once("exit", resolvePromise),
  );
  child.kill("SIGKILL");
  await exited;
}

async function runGatedClaimProcesses(root, claims) {
  const moduleUrl = new URL(
    "../assets/scripts/oracle-subagent-idempotency.mjs",
    import.meta.url,
  ).href;
  const childScript = path.join(root, "gated-claim-process.mjs");
  await writeFile(
    childScript,
    `
import { claimIdempotentRequest } from ${JSON.stringify(moduleUrl)};
await new Promise((resolvePromise) => process.stdin.once("data", resolvePromise));
try {
  const claim = await claimIdempotentRequest(process.argv[2], {
    request_fingerprint: process.argv[3],
    candidate_run_id: process.argv[4],
    owner_id: process.argv[5],
  }, { timeoutMs: 60000, pollMs: 5 });
  process.stdout.write(JSON.stringify({
    ok: true,
    disposition: claim.disposition,
    send_authorized: claim.send_authorized,
    run_id: claim.run_id,
    request_fingerprint: claim.request_fingerprint,
  }));
} catch (error) {
  process.stdout.write(JSON.stringify({
    ok: false,
    name: error?.name,
    code: error?.code,
    message: error?.message,
  }));
}
`,
    { mode: 0o600 },
  );
  const children = claims.map((claim) =>
    spawn(
      process.execPath,
      [
        childScript,
        root,
        claim.fingerprint,
        claim.runId,
        claim.ownerId,
      ],
      {
        env: { PATH: process.env.PATH ?? "/usr/bin:/bin" },
        stdio: ["pipe", "pipe", "pipe"],
      },
    ),
  );
  const outcomes = children.map(
    (child) =>
      new Promise((resolvePromise, rejectPromise) => {
        let standardOutput = "";
        let standardError = "";
        child.stdout.setEncoding("utf8");
        child.stderr.setEncoding("utf8");
        child.stdout.on("data", (chunk) => {
          standardOutput += chunk;
        });
        child.stderr.on("data", (chunk) => {
          standardError += chunk;
        });
        child.once("error", rejectPromise);
        child.once("exit", (code, signal) => {
          if (code !== 0 || signal !== null || standardError !== "") {
            rejectPromise(
              new Error(
                `claim process failed: code=${code} signal=${signal} stderr=${standardError}`,
              ),
            );
            return;
          }
          resolvePromise(JSON.parse(standardOutput));
        });
      }),
  );
  for (const child of children) child.stdin.end("start\n");
  return Promise.all(outcomes);
}

async function createCandidate(root, runId, fingerprint = FINGERPRINT) {
  const directory = path.join(root, runId);
  await mkdir(directory, { mode: 0o700 });
  const receiptPath = path.join(directory, "receipt.json");
  const receipt = await createReceiptFile(receiptPath, {
    runId,
    slug: "idempotency-proof",
    mode: "deep-research",
    requestFingerprint: fingerprint,
    createdAt: at(0),
    eventId: `event-created-${runId}`,
  });
  return { receiptPath, receipt };
}

function claimInput(runId, ownerId, fingerprint = FINGERPRINT) {
  return {
    request_fingerprint: fingerprint,
    candidate_run_id: runId,
    owner_id: ownerId,
  };
}

function transition(runId, to, expectedRevision, observedAt, evidence) {
  return {
    to,
    expectedRevision,
    eventId: `event-${to}-${expectedRevision}`,
    observedAt,
    evidence: { run_id: runId, ...evidence },
  };
}

async function completeLifecycle(receiptPath, resultPath, runId) {
  await transitionReceiptFile(
    receiptPath,
    transition(runId, "auth_ready", 0, at(1), {
      source: "browser",
      profile_fingerprint: "b".repeat(64),
      challenge_observed: false,
    }),
  );
  await transitionReceiptFile(
    receiptPath,
    transition(runId, "target_bound", 1, at(2), {
      source: "browser",
      target_id: TARGET_ID,
      target_url: TARGET_URL,
      browser_pid: 4242,
    }),
  );
  await transitionReceiptFile(
    receiptPath,
    transition(runId, "model_tool_verified", 2, at(3), {
      source: "browser",
      target_id: TARGET_ID,
      model_requested: "gpt-5.4-pro",
      model_observed: "gpt-5.4-pro",
      model_proven: true,
      tool_requested: "deep-research",
      tool_observed: "deep-research",
      tool_proven: true,
    }),
  );
  await transitionReceiptFile(
    receiptPath,
    transition(runId, "submitted", 3, at(4), {
      source: "browser",
      target_id: TARGET_ID,
      conversation_url: CONVERSATION_URL,
      baseline_assistant_turn_id: "assistant-baseline",
      baseline_assistant_turn_position: 10,
      user_turn_id: "user-turn-idempotency",
      user_turn_position: 11,
      request_fingerprint: FINGERPRINT,
      deadline_at: at(10),
    }),
  );
  await transitionReceiptFile(
    receiptPath,
    transition(runId, "started", 4, at(5), {
      source: "browser",
      target_id: TARGET_ID,
      conversation_url: CONVERSATION_URL,
      user_turn_id: "user-turn-idempotency",
      assistant_signal_id: "assistant-progress",
      assistant_signal_position: 12,
    }),
  );
  const result = await writeResultAtomic(resultPath, "# Durable result\n", {
    runId,
  });
  await transitionReceiptFile(
    receiptPath,
    transition(runId, "completed", 5, at(6), {
      source: "browser",
      target_id: TARGET_ID,
      conversation_url: CONVERSATION_URL,
      user_turn_id: "user-turn-idempotency",
      final_assistant_turn_id: "assistant-final",
      final_assistant_turn_position: 13,
      result,
    }),
  );
  return result;
}

function assertIdempotencyError(error, code) {
  assert(error instanceof OracleSubagentIdempotencyError);
  assert.equal(error.code, code);
  assert.equal(error.message, "oracle-subagent idempotency: rejected");
  return true;
}

test("concurrent identical requests yield one authorization and one reattach target", async (t) => {
  const root = await temporaryRoot(t);
  const candidates = Array.from(
    { length: 12 },
    (_, index) => `run-idempotency-${String(index).padStart(2, "0")}`,
  );
  await Promise.all(candidates.map((runId) => createCandidate(root, runId)));

  const stabilityDelayMs = 7_777;
  const originalSetTimeout = globalThis.setTimeout;
  let releaseOwner;
  let signalOwner;
  const ownerLocked = new Promise((resolvePromise) => {
    signalOwner = resolvePromise;
  });
  globalThis.setTimeout = (callback, delay, ...arguments_) => {
    if (delay === stabilityDelayMs) {
      releaseOwner = () => callback(...arguments_);
      signalOwner();
      return undefined;
    }
    return originalSetTimeout(callback, delay, ...arguments_);
  };

  let first;
  try {
    first = claimIdempotentRequest(
      root,
      claimInput(candidates[0], "owner-concurrent-00"),
      { postAcquireDelayMs: stabilityDelayMs },
    );
    await ownerLocked;
    const duplicates = candidates.slice(1).map((runId, index) =>
      claimIdempotentRequest(
        root,
        claimInput(runId, `owner-concurrent-${String(index + 1).padStart(2, "0")}`),
      ),
    );
    releaseOwner();
    const claims = await Promise.all([first, ...duplicates]);

    assert.equal(
      claims.filter((claim) => claim.send_authorized).length,
      1,
    );
    assert.equal(
      claims.filter((claim) => claim.disposition === "owner").length,
      1,
    );
    assert.deepEqual(
      new Set(claims.map((claim) => claim.run_id)),
      new Set([candidates[0]]),
    );
    assert.deepEqual(
      new Set(claims.map((claim) => claim.receipt_path)),
      new Set([path.join(root, candidates[0], "receipt.json")]),
    );
    assert(claims.every((claim) => claim.schema === IDEMPOTENCY_CLAIM_SCHEMA));
    assert(claims.every((claim) => claim.receipt.run_id === candidates[0]));

    const retry = await claimIdempotentRequest(
      root,
      claimInput(candidates[0], "owner-concurrent-00"),
    );
    assert.equal(retry.disposition, "reattached");
    assert.equal(retry.send_authorized, false);

    const layout = idempotencyLayout(root, FINGERPRINT);
    const encoded = await readFile(layout.index_path, "utf8");
    const publicationEncoded = await readFile(
      layout.publication_path,
      "utf8",
    );
    const intentEncoded = await readFile(layout.intent_path, "utf8");
    const markerEncoded = await readFile(layout.claim_marker_path, "utf8");
    const generationEncoded = await readFile(layout.generation_path, "utf8");
    const ledgerEncoded = await readFile(
      layout.claim_ledger_path,
      "utf8",
    );
    const ledgerHeadEncoded = await readFile(
      layout.claim_ledger_head_path,
      "utf8",
    );
    const [witnessName] = await readdir(
      layout.claim_ledger_witness_directory,
    );
    const witnessEncoded = await readFile(
      path.join(layout.claim_ledger_witness_directory, witnessName),
      "utf8",
    );
    assert.doesNotMatch(
      `${encoded}${publicationEncoded}${intentEncoded}${markerEncoded}${generationEncoded}${ledgerEncoded}${ledgerHeadEncoded}${witnessEncoded}`,
      /authorization|bearer|cookie|password|prompt|secret|session|token|https?:\/\//i,
    );
    assert.equal((await stat(layout.index_directory)).mode & 0o777, 0o700);
    assert.equal((await stat(layout.index_path)).mode & 0o777, 0o600);
    assert.equal(
      (await stat(layout.publication_path)).mode & 0o777,
      0o600,
    );
    assert.equal((await stat(layout.intent_path)).mode & 0o777, 0o600);
    assert.equal((await stat(layout.claim_marker_path)).mode & 0o777, 0o600);
    assert.equal((await stat(layout.generation_path)).mode & 0o777, 0o600);
    assert.equal(
      (await stat(layout.bootstrap_lock_path)).mode & 0o777,
      0o600,
    );
    assert.equal((await stat(layout.lock_path)).mode & 0o777, 0o600);
    assert.equal(
      (await stat(layout.claim_ledger_path)).mode & 0o777,
      0o600,
    );
    assert.equal(
      (await stat(layout.claim_ledger_head_path)).mode & 0o777,
      0o600,
    );
    assert.equal(
      (await stat(layout.claim_ledger_lock_path)).mode & 0o777,
      0o600,
    );
    assert.equal(
      (await stat(layout.claim_ledger_witness_directory)).mode &
        0o777,
      0o700,
    );
    assert.equal(
      (
        await stat(
          path.join(
            layout.claim_ledger_witness_directory,
            witnessName,
          ),
        )
      ).mode & 0o777,
      0o600,
    );
  } finally {
    globalThis.setTimeout = originalSetTimeout;
    releaseOwner?.();
    await first?.catch(() => {});
  }
});

test("fresh-root multiprocess identical requests bootstrap once and converge without rejection", async (t) => {
  for (let repetition = 0; repetition < 2; repetition += 1) {
    await t.test(`repetition ${repetition + 1}`, async (subtest) => {
      const root = await temporaryRoot(subtest);
      const claims = Array.from({ length: 20 }, (_, index) => ({
        fingerprint: FINGERPRINT,
        runId: `run-multiprocess-same-${repetition}-${String(index).padStart(2, "0")}`,
        ownerId: `owner-multiprocess-same-${repetition}-${String(index).padStart(2, "0")}`,
      }));
      await Promise.all(
        claims.map((claim) =>
          createCandidate(root, claim.runId, claim.fingerprint),
        ),
      );
      const outcomes = await runGatedClaimProcesses(root, claims);
      assert(outcomes.every((outcome) => outcome.ok));
      assert.equal(
        outcomes.filter((outcome) => outcome.send_authorized).length,
        1,
      );
      assert.equal(
        outcomes.filter(
          (outcome) => outcome.disposition === "reattached",
        ).length,
        19,
      );
      assert.equal(
        new Set(outcomes.map((outcome) => outcome.run_id)).size,
        1,
      );
      assert.equal(
        outcomes.find((outcome) => outcome.send_authorized).run_id,
        outcomes[0].run_id,
      );
    });
  }
});

test("fresh-root multiprocess distinct requests all allocate after one bootstrap", async (t) => {
  for (let repetition = 0; repetition < 2; repetition += 1) {
    await t.test(`repetition ${repetition + 1}`, async (subtest) => {
      const root = await temporaryRoot(subtest);
      const claims = Array.from({ length: 12 }, (_, index) => ({
        fingerprint: String(index + 1).padStart(64, "0"),
        runId: `run-multiprocess-distinct-${repetition}-${String(index).padStart(2, "0")}`,
        ownerId: `owner-multiprocess-distinct-${repetition}-${String(index).padStart(2, "0")}`,
      }));
      await Promise.all(
        claims.map((claim) =>
          createCandidate(root, claim.runId, claim.fingerprint),
        ),
      );
      const outcomes = await runGatedClaimProcesses(root, claims);
      assert(outcomes.every((outcome) => outcome.ok));
      assert(outcomes.every((outcome) => outcome.send_authorized));
      assert(
        outcomes.every((outcome) => outcome.disposition === "owner"),
      );
      assert.equal(
        new Set(outcomes.map((outcome) => outcome.run_id)).size,
        12,
      );
      const layout = idempotencyLayout(
        root,
        claims[0].fingerprint,
      );
      assert.equal(
        (await readFile(layout.claim_ledger_path, "utf8"))
          .trimEnd()
          .split("\n").length,
        12,
      );
    });
  }
});

test("concurrent distinct fingerprints allocate independently under one global ledger order", async (t) => {
  const root = await temporaryRoot(t);
  const firstRun = "run-idempotency-distinct-first";
  const secondRun = "run-idempotency-distinct-second";
  await Promise.all([
    createCandidate(root, firstRun, SECOND_FINGERPRINT),
    createCandidate(root, secondRun, THIRD_FINGERPRINT),
  ]);

  const claims = await Promise.all([
    claimIdempotentRequest(
      root,
      claimInput(
        firstRun,
        "owner-distinct-first",
        SECOND_FINGERPRINT,
      ),
    ),
    claimIdempotentRequest(
      root,
      claimInput(
        secondRun,
        "owner-distinct-second",
        THIRD_FINGERPRINT,
      ),
    ),
  ]);
  assert.equal(
    claims.filter((claim) => claim.send_authorized).length,
    2,
  );
  assert(claims.every((claim) => claim.disposition === "owner"));

  const layout = idempotencyLayout(root, SECOND_FINGERPRINT);
  const ledgerEntries = (await readFile(layout.claim_ledger_path, "utf8"))
    .trimEnd()
    .split("\n")
    .map((line) => JSON.parse(line));
  const headEntries = (
    await readFile(layout.claim_ledger_head_path, "utf8")
  )
    .trimEnd()
    .split("\n")
    .map((line) => JSON.parse(line));
  assert.deepEqual(
    new Set(
      ledgerEntries.map((entry) => entry.request_fingerprint),
    ),
    new Set([SECOND_FINGERPRINT, THIRD_FINGERPRINT]),
  );
  assert.deepEqual(
    ledgerEntries.map((entry) => entry.sequence),
    [1, 2],
  );
  assert.deepEqual(
    headEntries.map((entry) => entry.claim_count),
    [1, 2],
  );
  assert.equal(
    (await readdir(layout.claim_ledger_witness_directory)).length,
    2,
  );

  const retries = await Promise.all([
    claimIdempotentRequest(
      root,
      claimInput(
        firstRun,
        "owner-distinct-first-retry",
        SECOND_FINGERPRINT,
      ),
    ),
    claimIdempotentRequest(
      root,
      claimInput(
        secondRun,
        "owner-distinct-second-retry",
        THIRD_FINGERPRINT,
      ),
    ),
  ]);
  assert(retries.every((claim) => !claim.send_authorized));
  assert(retries.every((claim) => claim.disposition === "reattached"));
});

test("durable intent recovers simultaneous record loss without reauthorizing send", async (t) => {
  const root = await temporaryRoot(t);
  const firstRun = "run-idempotency-intent-first";
  const secondRun = "run-idempotency-intent-second";
  await Promise.all([
    createCandidate(root, firstRun),
    createCandidate(root, secondRun),
  ]);
  const first = await claimIdempotentRequest(
    root,
    claimInput(firstRun, "owner-intent-first"),
  );
  assert.equal(first.send_authorized, true);
  const layout = idempotencyLayout(root, FINGERPRINT);
  await Promise.all([
    rename(layout.index_path, `${layout.index_path}.removed`),
    rename(
      layout.publication_path,
      `${layout.publication_path}.removed`,
    ),
  ]);

  const recovered = await claimIdempotentRequest(
    root,
    claimInput(secondRun, "owner-intent-second"),
  );
  assert.equal(recovered.disposition, "reattached");
  assert.equal(recovered.send_authorized, false);
  assert.equal(recovered.run_id, firstRun);
  assert.equal((await stat(layout.intent_path)).mode & 0o777, 0o600);

  const retry = await claimIdempotentRequest(
    root,
    claimInput(secondRun, "owner-intent-retry"),
  );
  assert.equal(retry.send_authorized, false);
  assert.equal(retry.run_id, firstRun);
});

test("wholesale four-record loss reattaches from the allocation ledger without authorizing send", async (t) => {
  const root = await temporaryRoot(t);
  const firstRun = "run-idempotency-all-state-first";
  const secondRun = "run-idempotency-all-state-second";
  await Promise.all([
    createCandidate(root, firstRun),
    createCandidate(root, secondRun),
  ]);
  const first = await claimIdempotentRequest(
    root,
    claimInput(firstRun, "owner-all-state-first"),
  );
  assert.equal(first.send_authorized, true);
  const layout = idempotencyLayout(root, FINGERPRINT);
  await Promise.all(
    [
      layout.intent_path,
      layout.claim_marker_path,
      layout.index_path,
      layout.publication_path,
    ].map((recordPath) => rename(recordPath, `${recordPath}.removed`)),
  );
  const recovered = await claimIdempotentRequest(
    root,
    claimInput(secondRun, "owner-all-state-second"),
  );
  assert.equal(recovered.disposition, "reattached");
  assert.equal(recovered.send_authorized, false);
  assert.equal(recovered.run_id, firstRun);
  for (const recordPath of [
    layout.intent_path,
    layout.claim_marker_path,
    layout.index_path,
    layout.publication_path,
  ]) {
    assert.equal((await stat(recordPath)).mode & 0o777, 0o600);
  }
});

for (const crashPoint of [
  {
    name: "ledger fsync",
    lockOptions: { postLedgerFsyncDelayMs: 9_000 },
    reached: async (layout) =>
      (await readFile(layout.claim_ledger_path)).length > 0 &&
      (await readFile(layout.claim_ledger_head_path)).length === 0 &&
      (await readdir(layout.claim_ledger_witness_directory)).length ===
        0 &&
      !(await fileExists(layout.intent_path)),
  },
  {
    name: "witness fsync",
    lockOptions: { postWitnessFsyncDelayMs: 9_000 },
    reached: async (layout) => {
      const witnessNames = await readdir(
        layout.claim_ledger_witness_directory,
      );
      return (
        (await readFile(layout.claim_ledger_path)).length > 0 &&
        (await readFile(layout.claim_ledger_head_path)).length === 0 &&
        witnessNames.length === 1 &&
        witnessNames[0] ===
          `000000000001-${FINGERPRINT}.json` &&
        !(await fileExists(layout.intent_path))
      );
    },
  },
  {
    name: "publication fsync",
    lockOptions: { postPublicationFsyncDelayMs: 9_000 },
    reached: async (layout) =>
      (await readFile(layout.claim_ledger_head_path)).length > 0 &&
      (await fileExists(layout.intent_path)) &&
      (await fileExists(layout.claim_marker_path)) &&
      (await fileExists(layout.publication_path)) &&
      !(await fileExists(layout.index_path)),
  },
]) {
  test(`SIGKILL at the ${crashPoint.name} crash durability point repairs to reattach-only`, async (t) => {
    const root = await temporaryRoot(t);
    const suffix = crashPoint.name.replace(" ", "-");
    const firstRun = `run-idempotency-crash-${suffix}`;
    const secondRun = `run-idempotency-crash-${suffix}-unused`;
    await Promise.all([
      createCandidate(root, firstRun),
      createCandidate(root, secondRun),
    ]);
    const layout = idempotencyLayout(root, FINGERPRINT);
    const child = await spawnClaimChild(
      root,
      FINGERPRINT,
      firstRun,
      `owner-crash-${suffix}`,
      crashPoint.lockOptions,
    );
    t.after(() => killChild(child));
    await waitForChildLine(child, "boundary\n");
    assert.equal(
      await crashPoint.reached(layout),
      true,
      `${crashPoint.name} durable prefix shape`,
    );
    await killChild(child);

    const recovered = await claimIdempotentRequest(
      root,
      claimInput(
        secondRun,
        `owner-recover-${suffix}`,
      ),
    );
    assert.equal(recovered.disposition, "reattached");
    assert.equal(recovered.send_authorized, false);
    assert.equal(recovered.run_id, firstRun);

    const retry = await claimIdempotentRequest(
      root,
      claimInput(secondRun, `owner-retry-${suffix}`),
    );
    assert.equal(retry.send_authorized, false);
    assert.equal(retry.run_id, firstRun);
  });
}

test("generation anchor rejects wholesale index-directory replacement", async (t) => {
  const root = await temporaryRoot(t);
  const firstRun = "run-idempotency-generation-first";
  const secondRun = "run-idempotency-generation-second";
  await Promise.all([
    createCandidate(root, firstRun),
    createCandidate(root, secondRun),
  ]);
  const first = await claimIdempotentRequest(
    root,
    claimInput(firstRun, "owner-generation-first"),
  );
  assert.equal(first.send_authorized, true);
  const layout = idempotencyLayout(root, FINGERPRINT);
  await rename(
    layout.index_directory,
    `${layout.index_directory}.displaced`,
  );
  await mkdir(layout.index_directory, { mode: 0o700 });
  await assert.rejects(
    claimIdempotentRequest(
      root,
      claimInput(secondRun, "owner-generation-second"),
    ),
    (error) =>
      assertIdempotencyError(error, "generation_directory_mismatch"),
  );
});

test("ledger, monotonic head, witness, and store-anchor damage fail globally", async (t) => {
  const cases = [
    {
      name: "ledger loss",
      code: "claim_ledger_invalid",
      mutate: async (layout) =>
        rename(
          layout.claim_ledger_path,
          `${layout.claim_ledger_path}.displaced`,
        ),
    },
    {
      name: "ledger corruption",
      code: "claim_ledger_invalid",
      mutate: async (layout) =>
        writeFile(layout.claim_ledger_path, "corrupt\n"),
    },
    {
      name: "ledger truncation",
      code: "claim_ledger_invalid",
      mutate: async (layout) => {
        const bytes = await readFile(layout.claim_ledger_path);
        await writeFile(
          layout.claim_ledger_path,
          bytes.subarray(0, bytes.length - 1),
        );
      },
    },
    {
      name: "ledger replacement",
      code: "generation_directory_mismatch",
      mutate: async (layout) => {
        const bytes = await readFile(layout.claim_ledger_path);
        await rename(
          layout.claim_ledger_path,
          `${layout.claim_ledger_path}.displaced`,
        );
        await writeFile(layout.claim_ledger_path, bytes, { mode: 0o600 });
      },
    },
    {
      name: "monotonic head loss",
      code: "claim_ledger_head_invalid",
      mutate: async (layout) =>
        rename(
          layout.claim_ledger_head_path,
          `${layout.claim_ledger_head_path}.displaced`,
        ),
    },
    {
      name: "monotonic head corruption",
      code: "claim_ledger_head_invalid",
      mutate: async (layout) =>
        writeFile(layout.claim_ledger_head_path, "corrupt\n"),
    },
    {
      name: "monotonic head truncation",
      code: "claim_ledger_head_invalid",
      mutate: async (layout) => {
        const bytes = await readFile(layout.claim_ledger_head_path);
        await writeFile(
          layout.claim_ledger_head_path,
          bytes.subarray(0, bytes.length - 1),
        );
      },
    },
    {
      name: "monotonic head replacement",
      code: "generation_directory_mismatch",
      mutate: async (layout) => {
        const bytes = await readFile(layout.claim_ledger_head_path);
        await rename(
          layout.claim_ledger_head_path,
          `${layout.claim_ledger_head_path}.displaced`,
        );
        await writeFile(layout.claim_ledger_head_path, bytes, {
          mode: 0o600,
        });
      },
    },
    {
      name: "witness loss",
      code: "claim_ledger_witness_mismatch",
      mutate: async (layout) => {
        const [name] = await readdir(
          layout.claim_ledger_witness_directory,
        );
        await rename(
          path.join(layout.claim_ledger_witness_directory, name),
          path.join(layout.artifact_root, "displaced-witness.json"),
        );
      },
    },
    {
      name: "witness corruption",
      code: "claim_ledger_witness_invalid",
      mutate: async (layout) => {
        const [name] = await readdir(
          layout.claim_ledger_witness_directory,
        );
        await writeFile(
          path.join(layout.claim_ledger_witness_directory, name),
          "corrupt\n",
        );
      },
    },
    {
      name: "witness truncation",
      code: "claim_ledger_witness_invalid",
      mutate: async (layout) => {
        const [name] = await readdir(
          layout.claim_ledger_witness_directory,
        );
        const witnessPath = path.join(
          layout.claim_ledger_witness_directory,
          name,
        );
        const bytes = await readFile(witnessPath);
        await writeFile(
          witnessPath,
          bytes.subarray(0, bytes.length - 1),
        );
      },
    },
    {
      name: "same-content witness replacement",
      code: "claim_ledger_witness_mismatch",
      mutate: async (layout) => {
        const [name] = await readdir(
          layout.claim_ledger_witness_directory,
        );
        const witnessPath = path.join(
          layout.claim_ledger_witness_directory,
          name,
        );
        const bytes = await readFile(witnessPath);
        await rename(
          witnessPath,
          path.join(layout.artifact_root, "displaced-witness.json"),
        );
        await writeFile(witnessPath, bytes, { mode: 0o600 });
      },
    },
    {
      name: "global ledger-lock identity replacement",
      code: "generation_directory_mismatch",
      mutate: async (layout) => {
        await rename(
          layout.claim_ledger_lock_path,
          `${layout.claim_ledger_lock_path}.displaced`,
        );
        await writeFile(layout.claim_ledger_lock_path, "", {
          mode: 0o600,
        });
      },
    },
    {
      name: "witness-directory identity replacement",
      code: "generation_directory_mismatch",
      mutate: async (layout) => {
        await rename(
          layout.claim_ledger_witness_directory,
          `${layout.claim_ledger_witness_directory}.displaced`,
        );
        await mkdir(layout.claim_ledger_witness_directory, {
          mode: 0o700,
        });
      },
    },
  ];

  for (const [index, scenario] of cases.entries()) {
    await t.test(scenario.name, async (subtest) => {
      const root = await temporaryRoot(subtest);
      const firstRun = `run-integrity-first-${String(index).padStart(2, "0")}`;
      const secondRun = `run-integrity-second-${String(index).padStart(2, "0")}`;
      await Promise.all([
        createCandidate(root, firstRun),
        createCandidate(root, secondRun, SECOND_FINGERPRINT),
      ]);
      const owner = await claimIdempotentRequest(
        root,
        claimInput(firstRun, `owner-integrity-first-${index}`),
      );
      assert.equal(owner.send_authorized, true);
      const layout = idempotencyLayout(root, FINGERPRINT);
      await scenario.mutate(layout);
      await assert.rejects(
        claimIdempotentRequest(
          root,
          claimInput(
            secondRun,
            `owner-integrity-second-${index}`,
            SECOND_FINGERPRINT,
          ),
        ),
        (error) => assertIdempotencyError(error, scenario.code),
      );
    });
  }
});

test("valid-prefix ledger rollback plus removal of every rolled-back witness and local record is detected by the independent head", async (t) => {
  const root = await temporaryRoot(t);
  const firstRun = "run-prefix-rollback-first";
  const secondRun = "run-prefix-rollback-second";
  const thirdRun = "run-prefix-rollback-third";
  await Promise.all([
    createCandidate(root, firstRun),
    createCandidate(root, secondRun, SECOND_FINGERPRINT),
    createCandidate(root, thirdRun, THIRD_FINGERPRINT),
  ]);
  await claimIdempotentRequest(
    root,
    claimInput(firstRun, "owner-prefix-rollback-first"),
  );
  const firstLayout = idempotencyLayout(root, FINGERPRINT);
  const ledgerPrefix = await readFile(firstLayout.claim_ledger_path);
  await claimIdempotentRequest(
    root,
    claimInput(
      secondRun,
      "owner-prefix-rollback-second",
      SECOND_FINGERPRINT,
    ),
  );
  const secondLayout = idempotencyLayout(root, SECOND_FINGERPRINT);
  const identitiesBefore = {
    generation: await stat(firstLayout.generation_path),
    ledger: await stat(firstLayout.claim_ledger_path),
    ledgerLock: await stat(firstLayout.claim_ledger_lock_path),
    witnessDirectory: await stat(
      firstLayout.claim_ledger_witness_directory,
    ),
  };

  await writeFile(firstLayout.claim_ledger_path, ledgerPrefix);
  const witnessNames = await readdir(
    firstLayout.claim_ledger_witness_directory,
  );
  const rolledBackWitness = witnessNames.find((name) =>
    name.includes(SECOND_FINGERPRINT),
  );
  assert(rolledBackWitness);
  await rm(
    path.join(
      firstLayout.claim_ledger_witness_directory,
      rolledBackWitness,
    ),
  );
  await Promise.all(
    [
      secondLayout.intent_path,
      secondLayout.claim_marker_path,
      secondLayout.index_path,
      secondLayout.publication_path,
    ].map((recordPath) => rm(recordPath)),
  );

  const identitiesAfter = {
    generation: await stat(firstLayout.generation_path),
    ledger: await stat(firstLayout.claim_ledger_path),
    ledgerLock: await stat(firstLayout.claim_ledger_lock_path),
    witnessDirectory: await stat(
      firstLayout.claim_ledger_witness_directory,
    ),
  };
  for (const key of Object.keys(identitiesBefore)) {
    assert.equal(identitiesAfter[key].dev, identitiesBefore[key].dev);
    assert.equal(identitiesAfter[key].ino, identitiesBefore[key].ino);
  }

  await assert.rejects(
    claimIdempotentRequest(
      root,
      claimInput(
        thirdRun,
        "owner-prefix-rollback-third",
        THIRD_FINGERPRINT,
      ),
    ),
    (error) =>
      assertIdempotencyError(error, "claim_ledger_head_mismatch"),
  );
});

test("terminal-prefix repair rejects torn ledger and hash-invalid witness or publication evidence", async (t) => {
  await t.test("torn ledger append", async (subtest) => {
    const root = await temporaryRoot(subtest);
    const firstRun = "run-terminal-invalid-ledger-first";
    const secondRun = "run-terminal-invalid-ledger-second";
    await Promise.all([
      createCandidate(root, firstRun),
      createCandidate(root, secondRun, SECOND_FINGERPRINT),
    ]);
    await claimIdempotentRequest(
      root,
      claimInput(firstRun, "owner-terminal-invalid-ledger"),
    );
    const layout = idempotencyLayout(root, FINGERPRINT);
    const ledger = await readFile(layout.claim_ledger_path);
    await writeFile(
      layout.claim_ledger_path,
      Buffer.concat([ledger, Buffer.from("{")]),
    );
    await assert.rejects(
      claimIdempotentRequest(
        root,
        claimInput(
          secondRun,
          "owner-terminal-invalid-ledger-reader",
          SECOND_FINGERPRINT,
        ),
      ),
      (error) => assertIdempotencyError(error, "claim_ledger_invalid"),
    );
  });

  await t.test("hash-invalid terminal witness", async (subtest) => {
    const root = await temporaryRoot(subtest);
    const firstRun = "run-terminal-invalid-witness-first";
    const secondRun = "run-terminal-invalid-witness-second";
    await Promise.all([
      createCandidate(root, firstRun),
      createCandidate(root, secondRun, SECOND_FINGERPRINT),
    ]);
    await claimIdempotentRequest(
      root,
      claimInput(firstRun, "owner-terminal-invalid-witness"),
    );
    const layout = idempotencyLayout(root, FINGERPRINT);
    await writeFile(layout.claim_ledger_head_path, "");
    const [witnessName] = await readdir(
      layout.claim_ledger_witness_directory,
    );
    const witnessPath = path.join(
      layout.claim_ledger_witness_directory,
      witnessName,
    );
    const witness = JSON.parse(await readFile(witnessPath, "utf8"));
    witness.witness_hash = "0".repeat(64);
    await writeFile(witnessPath, `${JSON.stringify(witness)}\n`);
    await assert.rejects(
      claimIdempotentRequest(
        root,
        claimInput(
          secondRun,
          "owner-terminal-invalid-witness-reader",
          SECOND_FINGERPRINT,
        ),
      ),
      (error) =>
        assertIdempotencyError(
          error,
          "claim_ledger_witness_invalid",
        ),
    );
  });

  await t.test("hash-invalid publication prefix", async (subtest) => {
    const root = await temporaryRoot(subtest);
    const firstRun = "run-terminal-invalid-publication-first";
    const secondRun = "run-terminal-invalid-publication-second";
    await Promise.all([
      createCandidate(root, firstRun),
      createCandidate(root, secondRun),
    ]);
    await claimIdempotentRequest(
      root,
      claimInput(firstRun, "owner-terminal-invalid-publication"),
    );
    const layout = idempotencyLayout(root, FINGERPRINT);
    await rename(layout.index_path, `${layout.index_path}.removed`);
    const publication = JSON.parse(
      await readFile(layout.publication_path, "utf8"),
    );
    publication.publication_hash = "0".repeat(64);
    await writeFile(
      layout.publication_path,
      `${JSON.stringify(publication)}\n`,
    );
    await assert.rejects(
      claimIdempotentRequest(
        root,
        claimInput(
          secondRun,
          "owner-terminal-invalid-publication-reader",
        ),
      ),
      (error) => assertIdempotencyError(error, "publication_invalid"),
    );
  });
});

test("incomplete namespace bootstrap cannot be retried as virgin", async (t) => {
  const partials = [
    {
      name: "index directory",
      create: (layout) =>
        mkdir(layout.index_directory, { mode: 0o700 }),
    },
    {
      name: "claim ledger",
      create: (layout) =>
        writeFile(layout.claim_ledger_path, "", { mode: 0o600 }),
    },
    {
      name: "monotonic head",
      create: (layout) =>
        writeFile(layout.claim_ledger_head_path, "", { mode: 0o600 }),
    },
    {
      name: "global ledger lock",
      create: (layout) =>
        writeFile(layout.claim_ledger_lock_path, "", { mode: 0o600 }),
    },
    {
      name: "witness directory",
      create: (layout) =>
        mkdir(layout.claim_ledger_witness_directory, { mode: 0o700 }),
    },
  ];
  for (const [index, partial] of partials.entries()) {
    await t.test(partial.name, async (subtest) => {
      const root = await temporaryRoot(subtest);
      const runId = `run-bootstrap-incomplete-${index}`;
      await createCandidate(root, runId);
      const layout = idempotencyLayout(root, FINGERPRINT);
      await partial.create(layout);
      for (let attempt = 0; attempt < 2; attempt += 1) {
        await assert.rejects(
          claimIdempotentRequest(
            root,
            claimInput(
              runId,
              `owner-bootstrap-incomplete-${index}-${attempt}`,
            ),
          ),
          (error) =>
            assertIdempotencyError(error, "generation_missing"),
        );
      }
      await assert.rejects(stat(layout.generation_path), {
        code: "ENOENT",
      });
      await assert.rejects(stat(layout.intent_path), { code: "ENOENT" });
    });
  }
  await t.test(
    "bootstrap lock pathname alone remains virgin",
    async (subtest) => {
      const root = await temporaryRoot(subtest);
      const runId = "run-bootstrap-lock-only";
      await createCandidate(root, runId);
      const layout = idempotencyLayout(root, FINGERPRINT);
      await writeFile(layout.bootstrap_lock_path, "", { mode: 0o600 });
      const owner = await claimIdempotentRequest(
        root,
        claimInput(runId, "owner-bootstrap-lock-only"),
      );
      assert.equal(owner.disposition, "owner");
      assert.equal(owner.send_authorized, true);
      const retry = await claimIdempotentRequest(
        root,
        claimInput(runId, "owner-bootstrap-lock-only-retry"),
      );
      assert.equal(retry.send_authorized, false);
      assert.equal(retry.run_id, runId);
    },
  );
});

test("valid publication terminal prefix reconstructs a missing index reattach-only", async (t) => {
  const root = await temporaryRoot(t);
  const firstRun = "run-idempotency-published";
  const secondRun = "run-idempotency-after-remove";
  await Promise.all([
    createCandidate(root, firstRun),
    createCandidate(root, secondRun),
  ]);
  const owner = await claimIdempotentRequest(
    root,
    claimInput(firstRun, "owner-before-index-remove"),
  );
  assert.equal(owner.send_authorized, true);

  const layout = idempotencyLayout(root, FINGERPRINT);
  const movedIndex = `${layout.index_path}.removed`;
  await rename(layout.index_path, movedIndex);
  assert.equal((await stat(layout.publication_path)).mode & 0o777, 0o600);
  const repaired = await claimIdempotentRequest(
    root,
    claimInput(secondRun, "owner-after-index-remove"),
  );
  assert.equal(repaired.disposition, "reattached");
  assert.equal(repaired.send_authorized, false);
  assert.equal(repaired.run_id, firstRun);
  assert.equal((await stat(layout.index_path)).mode & 0o777, 0o600);
  assert.equal((await stat(movedIndex)).mode & 0o777, 0o600);
});

test("reattach rejects a displaced receipt lock while its old holder is live", async (t) => {
  const root = await temporaryRoot(t);
  const runId = "run-idempotency-receipt-lock";
  const { receiptPath } = await createCandidate(root, runId);
  const owner = await claimIdempotentRequest(
    root,
    claimInput(runId, "owner-receipt-lock"),
  );
  assert.equal(owner.send_authorized, true);
  await completeLifecycle(
    receiptPath,
    path.join(root, runId, "result.md"),
    runId,
  );

  const lockPath = `${receiptPath}.lock`;
  const holder = await holdAdvisoryLock(lockPath);
  try {
    await rename(lockPath, `${lockPath}.displaced`);
    await writeFile(lockPath, "", { mode: 0o600 });
    await assert.rejects(
      claimIdempotentRequest(
        root,
        claimInput(
          "run-idempotency-receipt-lock-unused",
          "owner-receipt-lock-reattach",
        ),
      ),
      (error) =>
        assertIdempotencyError(error, "receipt_lock_replaced"),
    );
    assert.equal(holder.exitCode, null);
  } finally {
    await stopLockHolder(holder);
  }
});

test("lock pathname replacement cannot create split-brain ownership", async (t) => {
  const root = await temporaryRoot(t);
  const firstRun = "run-idempotency-lock-old";
  const secondRun = "run-idempotency-lock-new";
  await Promise.all([
    createCandidate(root, firstRun),
    createCandidate(root, secondRun),
  ]);

  const stabilityDelayMs = 6_666;
  const originalSetTimeout = globalThis.setTimeout;
  let releaseFirst;
  let signalFirst;
  const firstLocked = new Promise((resolvePromise) => {
    signalFirst = resolvePromise;
  });
  globalThis.setTimeout = (callback, delay, ...arguments_) => {
    if (delay === stabilityDelayMs) {
      releaseFirst = () => callback(...arguments_);
      signalFirst();
      return undefined;
    }
    return originalSetTimeout(callback, delay, ...arguments_);
  };

  let first;
  let second;
  try {
    first = claimIdempotentRequest(
      root,
      claimInput(firstRun, "owner-replaced-lock-old"),
      { postAcquireDelayMs: stabilityDelayMs },
    );
    await firstLocked;
    const layout = idempotencyLayout(root, FINGERPRINT);
    await rename(layout.lock_path, `${layout.lock_path}.displaced`);
    await writeFile(layout.lock_path, "", { mode: 0o600 });
    second = claimIdempotentRequest(
      root,
      claimInput(secondRun, "owner-replaced-lock-new"),
    );
    releaseFirst();

    const outcomes = await Promise.allSettled([first, second]);
    const fulfilled = outcomes
      .filter((outcome) => outcome.status === "fulfilled")
      .map((outcome) => outcome.value);
    const rejected = outcomes
      .filter((outcome) => outcome.status === "rejected")
      .map((outcome) => outcome.reason);
    assert.equal(fulfilled.length, 1);
    assert.equal(fulfilled[0].send_authorized, true);
    assert.equal(fulfilled[0].run_id, secondRun);
    assert.equal(rejected.length, 1);
    assertIdempotencyError(rejected[0], "lock_replaced");

    const reattached = await claimIdempotentRequest(
      root,
      claimInput(firstRun, "owner-replaced-lock-followup"),
    );
    assert.equal(reattached.send_authorized, false);
    assert.equal(reattached.run_id, secondRun);
  } finally {
    globalThis.setTimeout = originalSetTimeout;
    releaseFirst?.();
    await first?.catch(() => {});
    await second?.catch(() => {});
  }
});

test("dead owner remains reattach-only and can never regain send authorization", async (t) => {
  const root = await temporaryRoot(t);
  const runId = "run-idempotency-death";
  await createCandidate(root, runId);
  const moduleUrl = new URL(
    "../assets/scripts/oracle-subagent-idempotency.mjs",
    import.meta.url,
  ).href;
  const childScript = path.join(root, "death-owner.mjs");
  await writeFile(
    childScript,
    `
import { claimIdempotentRequest } from ${JSON.stringify(moduleUrl)};
const claim = await claimIdempotentRequest(process.argv[2], {
  request_fingerprint: process.argv[3],
  candidate_run_id: process.argv[4],
  owner_id: "owner-child-death",
});
if (!claim.send_authorized) process.exit(31);
process.stdout.write("owned\\n");
setInterval(() => {}, 1000);
`,
    { mode: 0o600 },
  );
  const child = spawn(
    process.execPath,
    [childScript, root, FINGERPRINT, runId],
    {
      env: { PATH: process.env.PATH ?? "/usr/bin:/bin" },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  t.after(() => child.kill("SIGKILL"));
  child.stdout.setEncoding("utf8");
  await new Promise((resolvePromise, rejectPromise) => {
    child.once("error", rejectPromise);
    child.stdout.once("data", (chunk) => {
      if (chunk === "owned\n") resolvePromise();
      else rejectPromise(new Error("unexpected child output"));
    });
    child.once("exit", (code) => {
      if (code !== null) rejectPromise(new Error(`owner exited ${code}`));
    });
  });
  const exited = new Promise((resolvePromise) =>
    child.once("exit", resolvePromise),
  );
  child.kill("SIGKILL");
  await exited;

  const reattached = await claimIdempotentRequest(
    root,
    claimInput("run-unused-after-death", "owner-parent-after-death"),
  );
  assert.equal(reattached.run_id, runId);
  assert.equal(reattached.owner_status, "stale");
  assert.equal(reattached.disposition, "reattached");
  assert.equal(reattached.send_authorized, false);
});

test("death while holding flock before publication releases safely", async (t) => {
  const root = await temporaryRoot(t);
  const runId = "run-idempotency-lock-death";
  await createCandidate(root, runId);
  const moduleUrl = new URL(
    "../assets/scripts/oracle-subagent-idempotency.mjs",
    import.meta.url,
  ).href;
  const childScript = path.join(root, "lock-death-owner.mjs");
  await writeFile(
    childScript,
    `
import { claimIdempotentRequest } from ${JSON.stringify(moduleUrl)};
const originalSetTimeout = globalThis.setTimeout;
globalThis.setTimeout = (callback, delay, ...rest) => {
  if (delay === 10000) {
    process.stdout.write("locked\\n");
    setInterval(() => {}, 1000);
    return undefined;
  }
  return originalSetTimeout(callback, delay, ...rest);
};
await claimIdempotentRequest(process.argv[2], {
  request_fingerprint: process.argv[3],
  candidate_run_id: process.argv[4],
  owner_id: "owner-lock-death",
}, { postAcquireDelayMs: 10000 });
`,
    { mode: 0o600 },
  );
  const child = spawn(
    process.execPath,
    [childScript, root, FINGERPRINT, runId],
    {
      env: { PATH: process.env.PATH ?? "/usr/bin:/bin" },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  t.after(() => child.kill("SIGKILL"));
  child.stdout.setEncoding("utf8");
  await new Promise((resolvePromise, rejectPromise) => {
    child.once("error", rejectPromise);
    child.stdout.once("data", (chunk) => {
      if (chunk === "locked\n") resolvePromise();
      else rejectPromise(new Error("unexpected lock-owner output"));
    });
    child.once("exit", (code) => {
      if (code !== null) rejectPromise(new Error(`lock owner exited ${code}`));
    });
  });

  await assert.rejects(
    claimIdempotentRequest(
      root,
      claimInput(runId, "owner-blocked-by-lock"),
      { timeoutMs: 50, pollMs: 5 },
    ),
    (error) => assertIdempotencyError(error, "lock_timeout"),
  );
  const exited = new Promise((resolvePromise) =>
    child.once("exit", resolvePromise),
  );
  child.kill("SIGKILL");
  await exited;

  const recovered = await claimIdempotentRequest(
    root,
    claimInput(runId, "owner-after-lock-death"),
  );
  assert.equal(recovered.disposition, "owner");
  assert.equal(recovered.send_authorized, true);
});

test("reattach validates completed lifecycle result and atomic-write proof", async (t) => {
  const root = await temporaryRoot(t);
  const runId = "run-idempotency-complete";
  const { receiptPath } = await createCandidate(root, runId);
  const owner = await claimIdempotentRequest(
    root,
    claimInput(runId, "owner-completed-proof"),
  );
  assert.equal(owner.send_authorized, true);

  const resultPath = path.join(root, runId, "result.md");
  await completeLifecycle(receiptPath, resultPath, runId);
  const completed = await claimIdempotentRequest(
    root,
    claimInput("run-ignored-completed", "owner-completed-reattach"),
  );
  assert.equal(completed.run_id, runId);
  assert.equal(completed.receipt.state, "completed");
  assert.equal(completed.send_authorized, false);

  await writeFile(resultPath, "# Tampered result\n", { mode: 0o600 });
  await assert.rejects(
    claimIdempotentRequest(
      root,
      claimInput("run-ignored-tampered", "owner-tampered-reattach"),
    ),
    (error) => assertIdempotencyError(error, "receipt_invalid"),
  );
});

test("index, path, and input tampering fail closed without replacement", async (t) => {
  const root = await temporaryRoot(t);
  const runId = "run-idempotency-tamper";
  await createCandidate(root, runId);
  await claimIdempotentRequest(
    root,
    claimInput(runId, "owner-index-tamper"),
  );
  const layout = idempotencyLayout(root, FINGERPRINT);
  const tampered = JSON.parse(await readFile(layout.index_path, "utf8"));
  tampered.owner_id = "owner-index-forged";
  await writeFile(layout.index_path, `${JSON.stringify(tampered)}\n`, {
    mode: 0o600,
  });
  await assert.rejects(
    claimIdempotentRequest(
      root,
      claimInput("run-ignored-index", "owner-index-reader"),
    ),
    (error) => assertIdempotencyError(error, "index_invalid"),
  );

  const publicRoot = await temporaryRoot(t);
  await createCandidate(publicRoot, "run-idempotency-public");
  await chmod(publicRoot, 0o755);
  await assert.rejects(
    claimIdempotentRequest(
      publicRoot,
      claimInput("run-idempotency-public", "owner-public-root"),
    ),
    (error) => assertIdempotencyError(error, "artifact_root_invalid"),
  );

  const symlinkRoot = await temporaryRoot(t);
  const symlinkRun = "run-idempotency-symlink";
  await createCandidate(symlinkRoot, symlinkRun);
  const bootstrapFingerprint = "b".repeat(64);
  const bootstrapRun = "run-idempotency-bootstrap";
  await createCandidate(symlinkRoot, bootstrapRun, bootstrapFingerprint);
  await claimIdempotentRequest(
    symlinkRoot,
    claimInput(
      bootstrapRun,
      "owner-bootstrap-symlink-test",
      bootstrapFingerprint,
    ),
  );
  const symlinkLayout = idempotencyLayout(symlinkRoot, FINGERPRINT);
  const target = path.join(symlinkRoot, "index-target.json");
  await writeFile(target, "{}\n", { mode: 0o600 });
  await symlink(target, symlinkLayout.index_path);
  await assert.rejects(
    claimIdempotentRequest(
      symlinkRoot,
      claimInput(symlinkRun, "owner-symlink-index"),
    ),
    (error) => assertIdempotencyError(error, "index_invalid"),
  );

  await assert.rejects(
    claimIdempotentRequest(root, {
      ...claimInput(runId, "owner-extra-field"),
      prompt: "must-never-enter-the-index",
    }),
    (error) => assertIdempotencyError(error, "claim_invalid"),
  );
});

test("implementation has no prompt, file, argv, logging, or ambient-env surface", async () => {
  const source = await readFile(
    new URL(
      "../assets/scripts/oracle-subagent-idempotency.mjs",
      import.meta.url,
    ),
    "utf8",
  );
  assert.doesNotMatch(source, /process\.(?:argv|env)/);
  assert.doesNotMatch(source, /\bconsole\s*\./);
  assert.doesNotMatch(source, /chatgpt-selector-contract|oracle-subagent-auth/);
  assert.doesNotMatch(source, /attachment|raw[_-]?prompt/i);
  assert.match(source, /fcntl\.flock/);
});
