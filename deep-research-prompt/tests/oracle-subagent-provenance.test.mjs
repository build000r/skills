import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFile, mkdtemp, realpath, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  OracleSubagentProvenanceError,
  PROVENANCE_RECEIPT_SCHEMA,
  PROVENANCE_SCHEMA,
  PROVENANCE_WRITER_CONTRACT,
  SELECTOR_OBSERVATION_SCHEMA,
  SELECTOR_PROOF_SCHEMA,
  createProvenanceReceipt,
  verifyProvenance,
  verifyProvenanceReceipt,
} from "../assets/scripts/oracle-subagent-provenance.mjs";
import {
  RECEIPT_SCHEMA,
  createReceiptFile,
  transitionReceiptFile,
  withReceiptFileLock,
  writeResultAtomic,
} from "../assets/scripts/oracle-subagent-state.mjs";

const RUN_ID = "run-provenance-12345678";
const REQUEST_FINGERPRINT = "a".repeat(64);
const PROFILE_FINGERPRINT = "b".repeat(64);
const TARGET_ID = "target-provenance-123";
const TARGET_URL = "https://chatgpt.com/";
const CONVERSATION_URL = "https://chatgpt.com/c/provenance-123";
const BASELINE_TURN = "assistant-baseline";
const USER_TURN = "user-turn-provenance";
const START_SIGNAL = "assistant-progress";
const BASE_TIME = Date.parse("2026-07-28T00:00:00.000Z");

const EXPECTED = Object.freeze({
  wrapper: Object.freeze({
    version: "1.4.0",
    sha256: "1".repeat(64),
  }),
  oracle: Object.freeze({
    version: "2.3.1",
    sha256: "2".repeat(64),
  }),
  chrome: Object.freeze({
    version: "138.0.7204.94",
    executable_sha256: "3".repeat(64),
  }),
  policy: Object.freeze({
    version: "1.2.0",
    sha256: "4".repeat(64),
  }),
  selector_contract: Object.freeze({
    version: "1.1.0",
    sha256: "5".repeat(64),
    observation_schema: SELECTOR_OBSERVATION_SCHEMA,
    proof_schema: SELECTOR_PROOF_SCHEMA,
  }),
});

function provenance(overrides = {}) {
  return {
    schema: PROVENANCE_SCHEMA,
    run_id: RUN_ID,
    ...structuredClone(EXPECTED),
    ...overrides,
  };
}

function at(offset) {
  return new Date(BASE_TIME + offset * 1_000).toISOString();
}

async function temporaryWorkspace(t) {
  const directory = await realpath(
    await mkdtemp(path.join(os.tmpdir(), "oracle-provenance-test-")),
  );
  t.after(async () => {
    await rm(directory, { recursive: true, force: true });
  });
  return directory;
}

function transition(to, expectedRevision, observedAt, evidence) {
  return {
    to,
    expectedRevision,
    eventId: `event-${to}-${expectedRevision}`,
    observedAt,
    evidence: { run_id: RUN_ID, ...evidence },
  };
}

async function createLifecycle(receiptPath) {
  return createReceiptFile(receiptPath, {
    runId: RUN_ID,
    slug: "provenance-proof",
    mode: "deep-research",
    requestFingerprint: REQUEST_FINGERPRINT,
    createdAt: at(0),
    eventId: "event-created-0",
  });
}

async function completeLifecycle(receiptPath, resultPath) {
  await createLifecycle(receiptPath);
  await transitionReceiptFile(
    receiptPath,
    transition("auth_ready", 0, at(1), {
      source: "browser",
      profile_fingerprint: PROFILE_FINGERPRINT,
      challenge_observed: false,
    }),
  );
  await transitionReceiptFile(
    receiptPath,
    transition("target_bound", 1, at(2), {
      source: "browser",
      target_id: TARGET_ID,
      target_url: TARGET_URL,
      browser_pid: 4242,
    }),
  );
  await transitionReceiptFile(
    receiptPath,
    transition("model_tool_verified", 2, at(3), {
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
    transition("submitted", 3, at(4), {
      source: "browser",
      target_id: TARGET_ID,
      conversation_url: CONVERSATION_URL,
      baseline_assistant_turn_id: BASELINE_TURN,
      baseline_assistant_turn_position: 10,
      user_turn_id: USER_TURN,
      user_turn_position: 11,
      request_fingerprint: REQUEST_FINGERPRINT,
      deadline_at: at(10),
    }),
  );
  await transitionReceiptFile(
    receiptPath,
    transition("started", 4, at(5), {
      source: "browser",
      target_id: TARGET_ID,
      conversation_url: CONVERSATION_URL,
      user_turn_id: USER_TURN,
      assistant_signal_id: START_SIGNAL,
      assistant_signal_position: 12,
    }),
  );
  const result = await writeResultAtomic(resultPath, "# Verified result\n", {
    runId: RUN_ID,
  });
  await transitionReceiptFile(
    receiptPath,
    transition("completed", 5, at(6), {
      source: "browser",
      target_id: TARGET_ID,
      conversation_url: CONVERSATION_URL,
      user_turn_id: USER_TURN,
      final_assistant_turn_id: "assistant-final",
      final_assistant_turn_position: 13,
      result,
    }),
  );
  return result;
}

function assertRejected(action, code) {
  assert.throws(action, (error) => {
    assert(error instanceof OracleSubagentProvenanceError);
    assert.equal(error.code, code);
    assert.equal(error.message, "oracle-subagent provenance: rejected");
    return true;
  });
}

test("creates a strict, immutable, run-bound receipt with sanitized versions", async (t) => {
  const directory = await temporaryWorkspace(t);
  const receiptPath = path.join(directory, "receipt.json");
  const lifecycle = await createLifecycle(receiptPath);

  const receipt = await createProvenanceReceipt(
    receiptPath,
    provenance(),
    EXPECTED,
  );

  assert.deepEqual(receipt, {
    schema: PROVENANCE_RECEIPT_SCHEMA,
    run_id: RUN_ID,
    state: "created",
    lifecycle_receipt_schema: RECEIPT_SCHEMA,
    lifecycle_receipt_hash: lifecycle.receipt_hash,
    provenance: provenance(),
  });
  assert(Object.isFrozen(receipt));
  assert(Object.isFrozen(receipt.provenance.selector_contract));
  assert.doesNotMatch(
    JSON.stringify(receipt),
    /authorization|bearer|cookie|environment|password|prompt|secret|session|token/i,
  );
  assert.deepEqual(
    await verifyProvenanceReceipt(receiptPath, receipt, EXPECTED),
    receipt,
  );
});

test("rejects extra fields, malformed versions, selector drift, and dependency drift", () => {
  assertRejected(
    () =>
      verifyProvenance(
        provenance({
          wrapper: {
            ...EXPECTED.wrapper,
            prompt: "sensitive-input-must-not-escape",
          },
        }),
        EXPECTED,
      ),
    "provenance_invalid",
  );
  assertRejected(
    () =>
      verifyProvenance(
        provenance({
          chrome: {
            ...EXPECTED.chrome,
            version: "138.0",
          },
        }),
        EXPECTED,
      ),
    "provenance_invalid",
  );
  assertRejected(
    () =>
      verifyProvenance(
        provenance({
          policy: {
            ...EXPECTED.policy,
            version: "1.2.0+arbitrary-secret-carrier",
          },
        }),
        EXPECTED,
      ),
    "provenance_invalid",
  );
  assertRejected(
    () =>
      verifyProvenance(
        provenance({
          selector_contract: {
            ...EXPECTED.selector_contract,
            proof_schema: "oracle-subagent.selector-proof.v2",
          },
        }),
        EXPECTED,
      ),
    "provenance_invalid",
  );
  assertRejected(
    () =>
      verifyProvenance(
        provenance({
          policy: {
            ...EXPECTED.policy,
            sha256: "6".repeat(64),
          },
        }),
        EXPECTED,
      ),
    "provenance_mismatch",
  );
  assertRejected(
    () =>
      verifyProvenance(provenance(), {
        ...structuredClone(EXPECTED),
        environment: "forbidden",
      }),
    "expected_provenance_invalid",
  );
});

test("completed provenance requires the nonempty atomic result proof on disk", async (t) => {
  const directory = await temporaryWorkspace(t);
  const receiptPath = path.join(directory, "receipt.json");
  const resultPath = path.join(directory, "result.md");
  const result = await completeLifecycle(receiptPath, resultPath);

  const completed = await createProvenanceReceipt(
    receiptPath,
    provenance(),
    EXPECTED,
  );
  assert.equal(completed.state, "completed");
  assert.equal(completed.run_id, result.run_id);
  assert.deepEqual(
    await verifyProvenanceReceipt(receiptPath, completed, EXPECTED),
    completed,
  );

  await writeFile(resultPath, "# Corrupted result\n", { mode: 0o600 });
  await assert.rejects(
    createProvenanceReceipt(receiptPath, provenance(), EXPECTED),
    (error) => {
      assert(error instanceof OracleSubagentProvenanceError);
      assert.equal(error.code, "lifecycle_receipt_invalid");
      assert.equal(error.message, "oracle-subagent provenance: rejected");
      return true;
    },
  );
});

test("double snapshot rejects deterministic replacement during completed verification", async (t) => {
  const directory = await temporaryWorkspace(t);
  const receiptPath = path.join(directory, "receipt.json");
  const resultPath = path.join(directory, "result.md");
  await completeLifecycle(receiptPath, resultPath);

  const stabilityDelayMs = 7_777;
  const originalSetTimeout = globalThis.setTimeout;
  let releaseGap;
  let signalGap;
  const gapStarted = new Promise((resolvePromise) => {
    signalGap = resolvePromise;
  });
  globalThis.setTimeout = (callback, delay, ...arguments_) => {
    if (delay === stabilityDelayMs) {
      releaseGap = () => callback(...arguments_);
      signalGap();
      return undefined;
    }
    return originalSetTimeout(callback, delay, ...arguments_);
  };

  let pending;
  try {
    pending = createProvenanceReceipt(
      receiptPath,
      provenance(),
      EXPECTED,
      { stabilityDelayMs },
    );
    await gapStarted;
    await writeFile(resultPath, "# Replaced between snapshots\n", {
      mode: 0o600,
    });
    releaseGap();
    await assert.rejects(pending, (error) => {
      assert(error instanceof OracleSubagentProvenanceError);
      assert.equal(error.code, "lifecycle_receipt_unstable");
      assert.equal(error.message, "oracle-subagent provenance: rejected");
      return true;
    });
  } finally {
    globalThis.setTimeout = originalSetTimeout;
    releaseGap?.();
    await pending?.catch(() => {});
  }
});

test("holds the lifecycle writer lock across both snapshots and construction", async (t) => {
  const directory = await temporaryWorkspace(t);
  const receiptPath = path.join(directory, "receipt.json");
  await createLifecycle(receiptPath);

  const stabilityDelayMs = 8_888;
  const originalSetTimeout = globalThis.setTimeout;
  let releaseGap;
  let signalGap;
  const gapStarted = new Promise((resolvePromise) => {
    signalGap = resolvePromise;
  });
  globalThis.setTimeout = (callback, delay, ...arguments_) => {
    if (delay === stabilityDelayMs) {
      releaseGap = () => callback(...arguments_);
      signalGap();
      return undefined;
    }
    return originalSetTimeout(callback, delay, ...arguments_);
  };

  let creation;
  let writer;
  try {
    creation = createProvenanceReceipt(
      receiptPath,
      provenance(),
      EXPECTED,
      { stabilityDelayMs },
    );
    await gapStarted;
    let writerEntered = false;
    writer = withReceiptFileLock(receiptPath, async () => {
      writerEntered = true;
    });
    await new Promise((resolvePromise) =>
      originalSetTimeout(resolvePromise, 100),
    );
    assert.equal(writerEntered, false);
    releaseGap();
    await creation;
    await writer;
    assert.equal(writerEntered, true);
    assert.deepEqual(PROVENANCE_WRITER_CONTRACT, {
      schema: "oracle-subagent.provenance-writer-contract.v1",
      receipt_lock: "oracle-subagent-state.withReceiptFileLock",
      result_and_proof_writes: "receipt-lock-required",
      terminal_result_and_proof: "immutable",
    });
  } finally {
    globalThis.setTimeout = originalSetTimeout;
    releaseGap?.();
    await creation?.catch(() => {});
    await writer?.catch(() => {});
  }
});

test("receipt verification fails closed on run, state, hash, or shape drift", async (t) => {
  const directory = await temporaryWorkspace(t);
  const receiptPath = path.join(directory, "receipt.json");
  await createLifecycle(receiptPath);
  const receipt = await createProvenanceReceipt(
    receiptPath,
    provenance(),
    EXPECTED,
  );

  for (const tampered of [
    { ...structuredClone(receipt), run_id: "run-other-12345678" },
    { ...structuredClone(receipt), state: "completed" },
    {
      ...structuredClone(receipt),
      lifecycle_receipt_hash: "f".repeat(64),
    },
    { ...structuredClone(receipt), environment: "forbidden" },
  ]) {
    await assert.rejects(
      verifyProvenanceReceipt(receiptPath, tampered, EXPECTED),
      (error) => {
        assert(error instanceof OracleSubagentProvenanceError);
        assert.equal(error.code, "provenance_receipt_invalid");
        return true;
      },
    );
  }

  await assert.rejects(
    createProvenanceReceipt(
      receiptPath,
      provenance({ run_id: "run-other-12345678" }),
      EXPECTED,
    ),
    (error) => {
      assert(error instanceof OracleSubagentProvenanceError);
      assert.equal(error.code, "run_binding_invalid");
      return true;
    },
  );
});

test("implementation has no secret-bearing input, logging, process, or send surface", async () => {
  const provenanceUrl = new URL(
    "../assets/scripts/oracle-subagent-provenance.mjs",
    import.meta.url,
  );
  const selectorUrl = new URL(
    "../assets/scripts/chatgpt-selector-contract.mjs",
    import.meta.url,
  );
  const [source, selectorSource] = await Promise.all([
    readFile(provenanceUrl, "utf8"),
    readFile(selectorUrl, "utf8"),
  ]);
  assert.doesNotMatch(source, /process\.(?:argv|env)/);
  assert.doesNotMatch(source, /\bconsole\s*\./);
  assert.doesNotMatch(source, /node:child_process|\bspawn\s*\(|\bexec(?:File)?\s*\(/);
  assert.doesNotMatch(source, /\bfetch\s*\(|WebSocket|http(?:s)?:\/\//);
  assert.doesNotMatch(source, /chatgpt-selector-contract/);

  const observationSchema = selectorSource.match(
    /export const SELECTOR_OBSERVATION_SCHEMA\s*=\s*"([^"]+)"/,
  )?.[1];
  const proofSchema = selectorSource.match(
    /export const SELECTOR_PROOF_SCHEMA\s*=\s*"([^"]+)"/,
  )?.[1];
  assert.equal(observationSchema, SELECTOR_OBSERVATION_SCHEMA);
  assert.equal(proofSchema, SELECTOR_PROOF_SCHEMA);

  const importProbe = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "--eval",
      `Object.defineProperty(process.argv, "1", { configurable: true, get() { throw new Error("argv-read"); } }); await import(${JSON.stringify(provenanceUrl.href)});`,
    ],
    {
      encoding: "utf8",
      env: { PATH: process.env.PATH ?? "/usr/bin:/bin" },
    },
  );
  assert.equal(importProbe.status, 0, importProbe.stderr);
  assert.equal(importProbe.stdout, "");
});
