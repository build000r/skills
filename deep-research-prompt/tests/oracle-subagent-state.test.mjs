import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { watch } from "node:fs";
import {
  link,
  mkdtemp,
  mkdir,
  readFile,
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
  createReceipt,
  createReceiptFile,
  readReceiptFile,
  RECEIPT_SCHEMA,
  transitionReceiptFile,
  validateReceipt,
  writeResultAtomic,
} from "../assets/scripts/oracle-subagent-state.mjs";

const RUN_ID = "run-oracle-12345678";
const SLUG = "state-proof";
const REQUEST_FINGERPRINT = "a".repeat(64);
const PROFILE_FINGERPRINT = "b".repeat(64);
const TARGET_ID = "target-123";
const TARGET_URL = "https://chatgpt.com/";
const CONVERSATION_URL = "https://chatgpt.com/c/conversation-123";
const BASELINE_TURN = "assistant-baseline";
const USER_TURN = "user-turn-123";
const START_SIGNAL = "assistant-progress-123";
const BASELINE_POSITION = 10;
const USER_POSITION = 11;
const START_POSITION = 12;
const FINAL_POSITION = 13;
const BASE_TIME = Date.parse("2026-07-28T00:00:00.000Z");
const RECEIPT_LOCK = Object.freeze({ dev: "1", ino: "2", ctime_ns: "3" });
const DENIED_IDENTIFIERS = Object.freeze([
  "authorization-material",
  "Bearer-credential-value",
  "cookie-material",
  "password-material",
  "prompt-material",
  "secret-material",
  "session_token_material",
  "token-material",
  "sk-proj-abcdefghijklmnop",
  "ghp_abcdefghijklmnopqrstuvwxyz",
  "github_pat_abcdefghijklmnopqrstuvwxyz",
  "xoxb-abcdefghijklmnop",
  "xapp-abcdefghijklmnop",
  "eyJabcdefgh.ijklmnop.qrstuvwx",
]);

function stableValue(value) {
  if (Array.isArray(value)) return value.map(stableValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, stableValue(value[key])]),
    );
  }
  return value;
}

function hash(value) {
  return createHash("sha256")
    .update(JSON.stringify(stableValue(value)))
    .digest("hex");
}

function rehashTamperedReceipt(receipt) {
  let previous = null;
  for (const event of receipt.history) {
    event.previous_event_hash = previous;
    const eventCopy = structuredClone(event);
    delete eventCopy.event_hash;
    event.event_hash = hash(eventCopy);
    previous = event.event_hash;
  }
  receipt.head_event_hash = previous;
  const receiptCopy = structuredClone(receipt);
  delete receiptCopy.receipt_hash;
  receipt.receipt_hash = hash(receiptCopy);
  return receipt;
}

function at(offset) {
  return new Date(BASE_TIME + offset * 1_000).toISOString();
}

function receiptInput(overrides = {}) {
  return {
    runId: RUN_ID,
    slug: SLUG,
    mode: "deep-research",
    requestFingerprint: REQUEST_FINGERPRINT,
    receiptLock: RECEIPT_LOCK,
    createdAt: at(0),
    eventId: "event-created-memory",
    ...overrides,
  };
}

function assertThrowsWithoutEcho(operation, rejectedValue) {
  let observed;
  try {
    operation();
  } catch (error) {
    observed = error;
  }
  assert.ok(observed instanceof Error, "operation must throw an Error");
  assert.equal(
    observed.message.includes(rejectedValue),
    false,
    "error message must not echo the rejected value",
  );
  return observed;
}

async function assertRejectsWithoutEcho(operation, rejectedValue) {
  let observed;
  try {
    await operation();
  } catch (error) {
    observed = error;
  }
  assert.ok(observed instanceof Error, "operation must reject with an Error");
  assert.equal(
    observed.message.includes(rejectedValue),
    false,
    "error message must not echo the rejected value",
  );
  return observed;
}

async function temporaryWorkspace(t) {
  const directory = await mkdtemp(path.join(os.tmpdir(), "oracle-state-test-"));
  t.after(async () => {
    await rm(directory, { recursive: true, force: true });
  });
  return realpath(directory);
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

descriptor = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)
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
      else rejectPromise(new Error(`unexpected lock helper output: ${chunk}`));
    });
    child.once("exit", (code) => {
      if (code !== null) rejectPromise(new Error(`lock helper exited ${code}`));
    });
  });
  return child;
}

async function stopLockHolder(child, signal = null) {
  const exited = new Promise((resolvePromise) => child.once("exit", resolvePromise));
  if (signal) child.kill(signal);
  else child.stdin.end();
  await exited;
}

function spawnTransitionChild(
  receiptPath,
  transitionValue,
  lockOptions = {},
) {
  const moduleUrl = new URL(
    "../assets/scripts/oracle-subagent-state.mjs",
    import.meta.url,
  ).href;
  const source = `
import { transitionReceiptFile } from ${JSON.stringify(moduleUrl)};
try {
  const receipt = await transitionReceiptFile(
    ${JSON.stringify(receiptPath)},
    ${JSON.stringify(transitionValue)},
    ${JSON.stringify(lockOptions)},
  );
  process.stdout.write(JSON.stringify({
    ok: true,
    state: receipt.state,
    revision: receipt.revision,
    receipt_hash: receipt.receipt_hash,
  }) + "\\n");
} catch (error) {
  process.stdout.write(JSON.stringify({
    ok: false,
    code: error.code ?? null,
    message: error.message,
  }) + "\\n");
}
`;
  const child = spawn(
    process.execPath,
    ["--input-type=module", "-e", source],
    {
      env: { PATH: process.env.PATH ?? "/usr/bin:/bin" },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  let standardOutput = "";
  let standardError = "";
  child.stdout.on("data", (chunk) => {
    standardOutput += chunk;
  });
  child.stderr.on("data", (chunk) => {
    standardError += chunk;
  });
  const outcome = new Promise((resolvePromise, rejectPromise) => {
    child.once("error", rejectPromise);
    child.once("exit", (code, signal) => {
      if (code !== 0 || signal !== null || standardError !== "") {
        rejectPromise(
          new Error(
            `transition child failed: code=${code} signal=${signal} stderr=${standardError}`,
          ),
        );
        return;
      }
      resolvePromise(JSON.parse(standardOutput.trim()));
    });
  });
  return { child, outcome };
}

function stopChildOnPathEvent(directory, predicate) {
  let child;
  let pendingStop = false;
  let attachChild;
  let watcher;
  const stopped = new Promise((resolvePromise, rejectPromise) => {
    const stop = () => {
      if (!child) {
        pendingStop = true;
        return;
      }
      watcher.close();
      if (!child.kill("SIGSTOP")) {
        rejectPromise(new Error("could not stop transition child"));
        return;
      }
      resolvePromise();
    };
    watcher = watch(directory, (eventType, filename) => {
      if (!predicate(eventType, filename, child)) return;
      stop();
    });
    watcher.once("error", rejectPromise);
    attachChild = (transitionChild) => {
      child = transitionChild;
      child.once("exit", () => {
        rejectPromise(new Error("transition child exited before boundary stop"));
      });
      if (pendingStop) stop();
    };
  });
  return {
    stopped,
    attach: (child) => attachChild(child),
    close: () => watcher?.close(),
  };
}

function transition(to, expectedRevision, observedAt, evidence, suffix = to) {
  return {
    to,
    expectedRevision,
    eventId: `event-${suffix}-${expectedRevision}`,
    observedAt,
    evidence: { run_id: RUN_ID, ...evidence },
  };
}

async function createRun(receiptPath) {
  return createReceiptFile(receiptPath, {
    runId: RUN_ID,
    slug: SLUG,
    mode: "deep-research",
    requestFingerprint: REQUEST_FINGERPRINT,
    createdAt: at(0),
    eventId: "event-created-0",
  });
}

async function rejectTransitionWithoutEcho(
  receiptPath,
  transitionValue,
  rejectedValue,
) {
  const before = await readFile(receiptPath);
  const error = await assertRejectsWithoutEcho(
    () => transitionReceiptFile(receiptPath, transitionValue),
    rejectedValue,
  );
  assert.deepEqual(await readFile(receiptPath), before);
  return error;
}

async function advanceToStarted(receiptPath, { deadlineAt = at(10) } = {}) {
  await createRun(receiptPath);
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
      baseline_assistant_turn_position: BASELINE_POSITION,
      user_turn_id: USER_TURN,
      user_turn_position: USER_POSITION,
      request_fingerprint: REQUEST_FINGERPRINT,
      deadline_at: deadlineAt,
    }),
  );
  return transitionReceiptFile(
    receiptPath,
    transition("started", 4, at(5), {
      source: "browser",
      target_id: TARGET_ID,
      conversation_url: CONVERSATION_URL,
      user_turn_id: USER_TURN,
      assistant_signal_id: START_SIGNAL,
      assistant_signal_position: START_POSITION,
    }),
  );
}

function completionEvidence(result) {
  return {
    source: "browser",
    target_id: TARGET_ID,
    conversation_url: CONVERSATION_URL,
    user_turn_id: USER_TURN,
    final_assistant_turn_id: "assistant-final-123",
    final_assistant_turn_position: FINAL_POSITION,
    result,
  };
}

test("creation rejects the full identifier denylist without echo", () => {
  for (const denied of [
    ...DENIED_IDENTIFIERS,
    "https://example.invalid/credential",
  ]) {
    const error = assertThrowsWithoutEcho(
      () => createReceipt(receiptInput({ eventId: denied })),
      denied,
    );
    assert.match(error.message, /event_id/);
  }

  for (const [field, denied] of [
    ["runId", "run-secret-material"],
    ["slug", "prompt-material"],
    ["eventId", "event-cookie-material"],
  ]) {
    const error = assertThrowsWithoutEcho(
      () => createReceipt(receiptInput({ [field]: denied })),
      denied,
    );
    assert.match(error.message, /sensitive/);
  }

  const opaque = createReceipt(
    receiptInput({
      runId: "run-ghp_short-123",
      eventId: "opaque-browser:ghp_short",
    }),
  );
  assert.equal(opaque.run_id, "run-ghp_short-123");
  assert.equal(opaque.history[0].event_id, "opaque-browser:ghp_short");
});

test("every transition identifier class rejects sensitive values without mutation or echo", async (t) => {
  const directory = await temporaryWorkspace(t);
  const receiptPath = path.join(directory, "receipt.json");
  const authEvidence = {
    source: "browser",
    profile_fingerprint: PROFILE_FINGERPRINT,
    challenge_observed: false,
  };
  await createRun(receiptPath);

  const deniedTargetState = transition(
    "secret-state",
    0,
    at(1),
    authEvidence,
  );
  await rejectTransitionWithoutEcho(
    receiptPath,
    deniedTargetState,
    deniedTargetState.to,
  );
  const deniedEvent = transition("auth_ready", 0, at(1), authEvidence);
  deniedEvent.eventId = "event-secret-material";
  await rejectTransitionWithoutEcho(
    receiptPath,
    deniedEvent,
    deniedEvent.eventId,
  );
  const deniedRevision = transition("auth_ready", 0, at(1), authEvidence);
  deniedRevision.expectedRevision = "sk-proj-abcdefghijklmnop";
  await rejectTransitionWithoutEcho(
    receiptPath,
    deniedRevision,
    deniedRevision.expectedRevision,
  );
  for (const [field, denied] of [
    ["run_id", "run-secret-material"],
    ["source", "secret-source"],
  ]) {
    await rejectTransitionWithoutEcho(
      receiptPath,
      transition("auth_ready", 0, at(1), {
        ...authEvidence,
        [field]: denied,
      }),
      denied,
    );
  }
  await transitionReceiptFile(
    receiptPath,
    transition("auth_ready", 0, at(1), authEvidence),
  );

  const targetEvidence = {
    source: "browser",
    target_id: TARGET_ID,
    target_url: TARGET_URL,
    browser_pid: 4242,
  };
  await rejectTransitionWithoutEcho(
    receiptPath,
    transition("target_bound", 1, at(2), {
      ...targetEvidence,
      target_id: "target-secret-material",
    }),
    "target-secret-material",
  );
  await transitionReceiptFile(
    receiptPath,
    transition("target_bound", 1, at(2), targetEvidence),
  );

  const modelEvidence = {
    source: "browser",
    target_id: TARGET_ID,
    model_requested: "gpt-5.4-pro",
    model_observed: "gpt-5.4-pro",
    model_proven: true,
    tool_requested: "deep-research",
    tool_observed: "deep-research",
    tool_proven: true,
  };
  for (const [field, denied] of [
    ["model_requested", "gpt-secret-pro"],
    ["model_observed", "sk-proj-abcdefghijklmnop"],
    ["tool_requested", "token-tool"],
    ["tool_observed", "cookie-tool"],
  ]) {
    await rejectTransitionWithoutEcho(
      receiptPath,
      transition("model_tool_verified", 2, at(3), {
        ...modelEvidence,
        [field]: denied,
      }),
      denied,
    );
  }
  await transitionReceiptFile(
    receiptPath,
    transition("model_tool_verified", 2, at(3), modelEvidence),
  );

  const submissionEvidence = {
    source: "browser",
    target_id: TARGET_ID,
    conversation_url: CONVERSATION_URL,
    baseline_assistant_turn_id: BASELINE_TURN,
    baseline_assistant_turn_position: BASELINE_POSITION,
    user_turn_id: USER_TURN,
    user_turn_position: USER_POSITION,
    request_fingerprint: REQUEST_FINGERPRINT,
    deadline_at: at(10),
  };
  for (const [field, denied] of [
    ["baseline_assistant_turn_id", "assistant-secret-baseline"],
    ["user_turn_id", "xoxb-abcdefghijklmnop"],
  ]) {
    await rejectTransitionWithoutEcho(
      receiptPath,
      transition("submitted", 3, at(4), {
        ...submissionEvidence,
        [field]: denied,
      }),
      denied,
    );
  }
  await transitionReceiptFile(
    receiptPath,
    transition("submitted", 3, at(4), submissionEvidence),
  );

  const startedEvidence = {
    source: "browser",
    target_id: TARGET_ID,
    conversation_url: CONVERSATION_URL,
    user_turn_id: USER_TURN,
    assistant_signal_id: START_SIGNAL,
    assistant_signal_position: START_POSITION,
  };
  await rejectTransitionWithoutEcho(
    receiptPath,
    transition("started", 4, at(5), {
      ...startedEvidence,
      assistant_signal_id: "assistant-secret-signal",
    }),
    "assistant-secret-signal",
  );
  await transitionReceiptFile(
    receiptPath,
    transition("started", 4, at(5), startedEvidence),
  );

  for (const [field, denied] of [
    ["code", "secret_error"],
    ["stage", "secret-stage"],
  ]) {
    await rejectTransitionWithoutEcho(
      receiptPath,
      transition("failed", 5, at(6), {
        source: "controller",
        code: "execution_failed",
        stage: "started",
        target_id: TARGET_ID,
        [field]: denied,
      }),
      denied,
    );
  }
  await rejectTransitionWithoutEcho(
    receiptPath,
    transition("timed_out", 5, at(10), {
      source: "controller",
      target_id: TARGET_ID,
      conversation_url: CONVERSATION_URL,
      user_turn_id: USER_TURN,
      deadline_at: at(10),
      last_state: "secret-state",
    }),
    "secret-state",
  );
  for (const [field, denied] of [
    ["actor", "secret-actor"],
    ["reason_code", "secret_reason"],
    ["last_state", "secret-state"],
  ]) {
    await rejectTransitionWithoutEcho(
      receiptPath,
      transition("cancelled", 5, at(6), {
        source: "user",
        actor: "user",
        reason_code: "user_request",
        last_state: "started",
        target_id: TARGET_ID,
        [field]: denied,
      }),
      denied,
    );
  }

  const result = await writeResultAtomic(
    path.join(directory, "result.md"),
    "verified result",
    { runId: RUN_ID },
  );
  await rejectTransitionWithoutEcho(
    receiptPath,
    transition("completed", 5, at(6), {
      ...completionEvidence(result),
      final_assistant_turn_id: "assistant-secret-final",
    }),
    "assistant-secret-final",
  );
  for (const [field, denied] of [
    ["run_id", "run-secret-material"],
    ["atomic_write_id", "ghp_abcdefghijklmnopqrstuvwxyz"],
    ["path", path.join(directory, "secret-result.md")],
    ["proof_path", path.join(directory, "secret-proof.json")],
  ]) {
    await rejectTransitionWithoutEcho(
      receiptPath,
      transition(
        "completed",
        5,
        at(6),
        completionEvidence({ ...result, [field]: denied }),
      ),
      denied,
    );
  }
  for (const [field, denied] of [
    ["destination_id", "Bearer-destination"],
    ["delivery_code", "secret_delivery"],
  ]) {
    await rejectTransitionWithoutEcho(
      receiptPath,
      transition("delivery_failed", 5, at(6), {
        source: "delivery",
        target_id: TARGET_ID,
        conversation_url: CONVERSATION_URL,
        user_turn_id: USER_TURN,
        final_assistant_turn_id: "assistant-final-123",
        final_assistant_turn_position: FINAL_POSITION,
        result,
        destination_id: "caller-d3",
        delivery_code: "transport_closed",
        [field]: denied,
      }),
      denied,
    );
  }

  const completed = await transitionReceiptFile(
    receiptPath,
    transition("completed", 5, at(6), completionEvidence(result)),
  );
  assert.equal(completed.state, "completed");
});

test("persists the complete legal lifecycle with hash-chained evidence", async (t) => {
  const directory = await temporaryWorkspace(t);
  const receiptPath = path.join(directory, "receipt.json");
  const resultPath = path.join(directory, "result.md");
  await advanceToStarted(receiptPath);
  const result = await writeResultAtomic(resultPath, "# Verified result\n", {
    runId: RUN_ID,
  });
  const completed = await transitionReceiptFile(
    receiptPath,
    transition("completed", 5, at(6), completionEvidence(result)),
  );

  assert.equal(completed.schema, RECEIPT_SCHEMA);
  assert.equal(completed.state, "completed");
  assert.equal(completed.revision, 6);
  assert.equal(completed.history.length, 7);
  assert.equal(completed.result.sha256, result.sha256);
  assert.equal(completed.result.bytes, Buffer.byteLength("# Verified result\n"));
  assert.equal(completed.error, null);
  assert.equal(completed.target.id, TARGET_ID);
  assert.equal(completed.submission.user_turn_id, USER_TURN);
  assert.equal((await stat(receiptPath)).mode & 0o777, 0o600);
  assert.equal((await stat(resultPath)).mode & 0o777, 0o600);
  assert.equal((await stat(result.proof_path)).mode & 0o777, 0o600);
  assert.deepEqual(await readReceiptFile(receiptPath), completed);

  const encoded = await readFile(receiptPath, "utf8");
  assert.doesNotMatch(encoded, /prompt|cookie|token|authorization/i);
  await assert.rejects(
    transitionReceiptFile(
      receiptPath,
      transition("failed", 6, at(7), {
        source: "controller",
        code: "late_failure",
        stage: "completed",
        target_id: TARGET_ID,
      }),
    ),
    /illegal transition completed -> failed/,
  );
});

test("completion fails closed for missing, empty, or hash-mismatched results", async (t) => {
  const directory = await temporaryWorkspace(t);
  const receiptPath = path.join(directory, "receipt.json");
  await advanceToStarted(receiptPath);
  const before = await readFile(receiptPath, "utf8");

  await assert.rejects(
    writeResultAtomic(path.join(directory, "empty.md"), "", { runId: RUN_ID }),
    /result content must be nonempty/,
  );

  const missing = {
    path: path.join(directory, "missing.md"),
    bytes: 1,
    sha256: "c".repeat(64),
    run_id: RUN_ID,
    atomic_write_id: "write-missing-123456",
    proof_path: `${path.join(directory, "missing.md")}.oracle-write-proof.json`,
  };
  await assert.rejects(
    transitionReceiptFile(
      receiptPath,
      transition("completed", 5, at(6), completionEvidence(missing)),
    ),
    /ENOENT/,
  );
  assert.equal(await readFile(receiptPath, "utf8"), before);

  const overlapping = {
    path: receiptPath,
    bytes: 1,
    sha256: "c".repeat(64),
    run_id: RUN_ID,
    atomic_write_id: "write-overlap-123456",
    proof_path: `${receiptPath}.oracle-write-proof.json`,
  };
  await assert.rejects(
    transitionReceiptFile(
      receiptPath,
      transition("completed", 5, at(6), completionEvidence(overlapping)),
    ),
    /overlap receipt control files/,
  );
  assert.equal(await readFile(receiptPath, "utf8"), before);

  const result = await writeResultAtomic(
    path.join(directory, "result.md"),
    "real result",
    { runId: RUN_ID },
  );
  const forged = { ...result, sha256: "d".repeat(64) };
  await assert.rejects(
    transitionReceiptFile(
      receiptPath,
      transition("completed", 5, at(6), completionEvidence(forged)),
    ),
    /result sha256 does not match/,
  );
  assert.equal(await readFile(receiptPath, "utf8"), before);

  const foreign = await writeResultAtomic(
    path.join(directory, "foreign.md"),
    "foreign result",
    { runId: "run-foreign-123456" },
  );
  await assert.rejects(
    transitionReceiptFile(
      receiptPath,
      transition("completed", 5, at(6), completionEvidence(foreign)),
    ),
    /not bound to this run/,
  );

  const missingProof = await writeResultAtomic(
    path.join(directory, "missing-proof.md"),
    "missing proof",
    { runId: RUN_ID },
  );
  await rm(missingProof.proof_path);
  await assert.rejects(
    transitionReceiptFile(
      receiptPath,
      transition("completed", 5, at(6), completionEvidence(missingProof)),
    ),
    /ENOENT/,
  );

  const forgedProof = await writeResultAtomic(
    path.join(directory, "forged-proof.md"),
    "forged proof",
    { runId: RUN_ID },
  );
  const proof = JSON.parse(await readFile(forgedProof.proof_path, "utf8"));
  proof.atomic_write_id = "write-forged-123456";
  await writeFile(forgedProof.proof_path, `${JSON.stringify(proof)}\n`, {
    mode: 0o600,
  });
  await assert.rejects(
    transitionReceiptFile(
      receiptPath,
      transition("completed", 5, at(6), completionEvidence(forgedProof)),
    ),
    /atomic-write proof does not match/,
  );
  assert.equal(await readFile(receiptPath, "utf8"), before);

  const receiptBytes = await readFile(receiptPath);
  const aliasedResultPath = path.join(directory, "aliased-result.md");
  await link(receiptPath, aliasedResultPath);
  const aliasedResult = {
    path: aliasedResultPath,
    bytes: receiptBytes.length,
    sha256: createHash("sha256").update(receiptBytes).digest("hex"),
    run_id: RUN_ID,
    atomic_write_id: "write-aliased-123456",
    proof_path: `${aliasedResultPath}.oracle-write-proof.json`,
  };
  await writeFile(
    aliasedResult.proof_path,
    `${JSON.stringify({
      schema: "oracle-subagent.result-write-proof.v1",
      run_id: RUN_ID,
      path: aliasedResult.path,
      bytes: aliasedResult.bytes,
      sha256: aliasedResult.sha256,
      atomic_write_id: aliasedResult.atomic_write_id,
    })}\n`,
    { mode: 0o600 },
  );
  await assert.rejects(
    transitionReceiptFile(
      receiptPath,
      transition("completed", 5, at(6), completionEvidence(aliasedResult)),
    ),
    /hard-link alias/,
  );
  await rm(aliasedResultPath);
  await rm(aliasedResult.proof_path);

  const actualParent = path.join(directory, "actual-result-parent");
  await mkdir(actualParent, { mode: 0o700 });
  const linkedParent = path.join(directory, "linked-result-parent");
  await symlink(actualParent, linkedParent, "dir");
  await assert.rejects(
    writeResultAtomic(path.join(linkedParent, "result.md"), "result", {
      runId: RUN_ID,
    }),
    /artifact parent traverses a symlink/,
  );
});

test("terminal reads reverify result bytes and write proof", async (t) => {
  const directory = await temporaryWorkspace(t);
  const receiptPath = path.join(directory, "receipt.json");
  const resultPath = path.join(directory, "result.md");
  await advanceToStarted(receiptPath);
  const result = await writeResultAtomic(resultPath, "verified", {
    runId: RUN_ID,
  });
  await transitionReceiptFile(
    receiptPath,
    transition("completed", 5, at(6), completionEvidence(result)),
  );
  await writeFile(resultPath, "tampered", { mode: 0o600 });
  await assert.rejects(
    readReceiptFile(receiptPath),
    /byte count|sha256 does not match/,
  );
});

test("rehashed replay rejects sensitive top-level, history, result, and error identifiers without echo", async (t) => {
  const directory = await temporaryWorkspace(t);
  const receiptPath = path.join(directory, "started.json");
  const started = await advanceToStarted(receiptPath);
  const startedCases = [
    {
      denied: "run-secret-material",
      mutate: (receipt) => {
        receipt.run_id = "run-secret-material";
      },
    },
    {
      denied: "prompt-material",
      mutate: (receipt) => {
        receipt.slug = "prompt-material";
      },
    },
    {
      denied: "secret-state",
      mutate: (receipt) => {
        receipt.state = "secret-state";
      },
    },
    {
      denied: "target-secret-material",
      mutate: (receipt) => {
        receipt.target.id = "target-secret-material";
      },
    },
    {
      denied: "model-secret-material",
      mutate: (receipt) => {
        receipt.model.requested = "model-secret-material";
      },
    },
    {
      denied: "token-tool",
      mutate: (receipt) => {
        receipt.tool.observed = "token-tool";
      },
    },
    {
      denied: "assistant-secret-baseline",
      mutate: (receipt) => {
        receipt.submission.baseline_assistant_turn_id =
          "assistant-secret-baseline";
      },
    },
    {
      denied: "user-cookie-material",
      mutate: (receipt) => {
        receipt.submission.user_turn_id = "user-cookie-material";
      },
    },
    {
      denied: "assistant-secret-signal",
      mutate: (receipt) => {
        receipt.started.assistant_signal_id = "assistant-secret-signal";
      },
    },
    {
      denied: "event-secret-material",
      mutate: (receipt) => {
        receipt.history[1].event_id = "event-secret-material";
      },
    },
    {
      denied: "run-secret-history",
      mutate: (receipt) => {
        receipt.history[1].run_id = "run-secret-history";
      },
    },
    {
      denied: "run-token-evidence",
      mutate: (receipt) => {
        receipt.history[1].evidence.run_id = "run-token-evidence";
      },
    },
    {
      denied: "secret-state",
      mutate: (receipt) => {
        receipt.history[1].from = "secret-state";
      },
    },
    {
      denied: "secret-transition",
      mutate: (receipt) => {
        receipt.history[1].to = "secret-transition";
      },
    },
    {
      denied: "secret-source",
      mutate: (receipt) => {
        receipt.history[1].evidence.source = "secret-source";
      },
    },
    {
      denied: "target-secret-history",
      mutate: (receipt) => {
        receipt.history[2].evidence.target_id = "target-secret-history";
      },
    },
    {
      denied: "gpt-secret-pro",
      mutate: (receipt) => {
        receipt.history[3].evidence.model_observed = "gpt-secret-pro";
      },
    },
    {
      denied: "cookie-tool",
      mutate: (receipt) => {
        receipt.history[3].evidence.tool_requested = "cookie-tool";
      },
    },
    {
      denied: "assistant-secret-history",
      mutate: (receipt) => {
        receipt.history[4].evidence.baseline_assistant_turn_id =
          "assistant-secret-history";
      },
    },
    {
      denied: "xapp-abcdefghijklmnop",
      mutate: (receipt) => {
        receipt.history[4].evidence.user_turn_id =
          "xapp-abcdefghijklmnop";
      },
    },
    {
      denied: "assistant-token-signal",
      mutate: (receipt) => {
        receipt.history[5].evidence.assistant_signal_id =
          "assistant-token-signal";
      },
    },
  ];
  for (const { denied, mutate } of startedCases) {
    const tampered = structuredClone(started);
    mutate(tampered);
    rehashTamperedReceipt(tampered);
    const error = assertThrowsWithoutEcho(
      () => validateReceipt(tampered),
      denied,
    );
    assert.match(error.message, /sensitive/);
  }

  const result = await writeResultAtomic(
    path.join(directory, "result.md"),
    "verified result",
    { runId: RUN_ID },
  );
  const completed = await transitionReceiptFile(
    receiptPath,
    transition("completed", 5, at(6), completionEvidence(result)),
  );
  const resultCases = [
    {
      denied: path.join(directory, "secret-result.md"),
      mutate: (receipt, denied) => {
        receipt.result.path = denied;
      },
    },
    {
      denied: "run-secret-result",
      mutate: (receipt, denied) => {
        receipt.result.run_id = denied;
      },
    },
    {
      denied: "ghp_abcdefghijklmnopqrstuvwxyz",
      mutate: (receipt, denied) => {
        receipt.result.atomic_write_id = denied;
      },
    },
    {
      denied: path.join(directory, "secret-proof.json"),
      mutate: (receipt, denied) => {
        receipt.result.proof_path = denied;
      },
    },
    {
      denied: "assistant-secret-final",
      mutate: (receipt, denied) => {
        receipt.history[6].evidence.final_assistant_turn_id = denied;
      },
    },
    {
      denied: "run-token-result",
      mutate: (receipt, denied) => {
        receipt.history[6].evidence.result.run_id = denied;
      },
    },
    {
      denied: "xoxb-abcdefghijklmnop",
      mutate: (receipt, denied) => {
        receipt.history[6].evidence.result.atomic_write_id = denied;
      },
    },
  ];
  for (const { denied, mutate } of resultCases) {
    const tampered = structuredClone(completed);
    mutate(tampered, denied);
    rehashTamperedReceipt(tampered);
    const error = assertThrowsWithoutEcho(
      () => validateReceipt(tampered),
      denied,
    );
    assert.match(error.message, /sensitive/);
  }

  const failedPath = path.join(directory, "failed.json");
  await createRun(failedPath);
  const failed = await transitionReceiptFile(
    failedPath,
    transition("failed", 0, at(1), {
      source: "controller",
      code: "execution_failed",
      stage: "created",
    }),
  );
  for (const [field, denied] of [
    ["code", "secret_error"],
    ["stage", "secret-stage"],
  ]) {
    const topLevelTamper = structuredClone(failed);
    topLevelTamper.error[field] = denied;
    rehashTamperedReceipt(topLevelTamper);
    assertThrowsWithoutEcho(
      () => validateReceipt(topLevelTamper),
      denied,
    );

    const historyTamper = structuredClone(failed);
    historyTamper.history[1].evidence[field] = denied;
    rehashTamperedReceipt(historyTamper);
    assertThrowsWithoutEcho(
      () => validateReceipt(historyTamper),
      denied,
    );
  }

  const cancelledPath = path.join(directory, "cancelled.json");
  await createRun(cancelledPath);
  const cancelled = await transitionReceiptFile(
    cancelledPath,
    transition("cancelled", 0, at(1), {
      source: "user",
      actor: "user",
      reason_code: "user_request",
      last_state: "created",
    }),
  );
  for (const [field, denied] of [
    ["actor", "secret-actor"],
    ["reason_code", "secret_reason"],
    ["last_state", "secret-state"],
  ]) {
    const tampered = structuredClone(cancelled);
    tampered.history[1].evidence[field] = denied;
    rehashTamperedReceipt(tampered);
    assertThrowsWithoutEcho(() => validateReceipt(tampered), denied);
  }

  const deliveryPath = path.join(directory, "delivery.json");
  await advanceToStarted(deliveryPath);
  const deliveryResult = await writeResultAtomic(
    path.join(directory, "delivery-result.md"),
    "verified delivery result",
    { runId: RUN_ID },
  );
  const deliveryFailed = await transitionReceiptFile(
    deliveryPath,
    transition("delivery_failed", 5, at(6), {
      source: "delivery",
      target_id: TARGET_ID,
      conversation_url: CONVERSATION_URL,
      user_turn_id: USER_TURN,
      final_assistant_turn_id: "assistant-final-123",
      final_assistant_turn_position: FINAL_POSITION,
      result: deliveryResult,
      destination_id: "caller-d3",
      delivery_code: "transport_closed",
    }),
  );
  for (const [field, denied] of [
    ["destination_id", "Bearer-destination"],
    ["delivery_code", "secret_delivery"],
  ]) {
    const topLevelTamper = structuredClone(deliveryFailed);
    topLevelTamper.error[
      field === "delivery_code" ? "code" : "destination_id"
    ] = denied;
    rehashTamperedReceipt(topLevelTamper);
    assertThrowsWithoutEcho(
      () => validateReceipt(topLevelTamper),
      denied,
    );

    const historyTamper = structuredClone(deliveryFailed);
    historyTamper.history[6].evidence[field] = denied;
    rehashTamperedReceipt(historyTamper);
    assertThrowsWithoutEcho(
      () => validateReceipt(historyTamper),
      denied,
    );
  }
});

test("result writes and atomic proofs reject sensitive IDs, paths, and malformed JSON without echo", async (t) => {
  const directory = await temporaryWorkspace(t);
  for (const denied of DENIED_IDENTIFIERS) {
    const resultPath = path.join(
      directory,
      `denied-result-${DENIED_IDENTIFIERS.indexOf(denied)}.md`,
    );
    const error = await assertRejectsWithoutEcho(
      () => writeResultAtomic(resultPath, "result", { runId: denied }),
      denied,
    );
    assert.match(error.message, /result run_id/);
  }

  const deniedPath = path.join(directory, "secret-result.md");
  const pathError = await assertRejectsWithoutEcho(
    () => writeResultAtomic(deniedPath, "result", { runId: RUN_ID }),
    deniedPath,
  );
  assert.match(pathError.message, /result path/);
  await assert.rejects(stat(deniedPath), { code: "ENOENT" });

  const receiptPath = path.join(directory, "receipt.json");
  await advanceToStarted(receiptPath);
  const result = await writeResultAtomic(
    path.join(directory, "result.md"),
    "verified result",
    { runId: RUN_ID },
  );
  const proof = JSON.parse(await readFile(result.proof_path, "utf8"));
  for (const [field, denied] of [
    ["run_id", "run-secret-proof"],
    ["path", path.join(directory, "secret-proof-result.md")],
    ["atomic_write_id", "github_pat_abcdefghijklmnopqrstuvwxyz"],
  ]) {
    await writeFile(
      result.proof_path,
      `${JSON.stringify({ ...proof, [field]: denied })}\n`,
      { mode: 0o600 },
    );
    const error = await rejectTransitionWithoutEcho(
      receiptPath,
      transition("completed", 5, at(6), completionEvidence(result)),
      denied,
    );
    assert.match(error.message, /result proof.*sensitive/);
  }

  const malformedCredential = "sk-proj-malformedcredential";
  await writeFile(
    result.proof_path,
    `{"credential":"${malformedCredential}"`,
    { mode: 0o600 },
  );
  const malformedError = await rejectTransitionWithoutEcho(
    receiptPath,
    transition("completed", 5, at(6), completionEvidence(result)),
    malformedCredential,
  );
  assert.match(malformedError.message, /result proof is invalid JSON/);

  const forbiddenCredential = "ghp_abcdefghijklmnopqrstuvwxyz";
  await writeFile(
    result.proof_path,
    `${JSON.stringify({
      ...proof,
      prompt: forbiddenCredential,
    })}\n`,
    { mode: 0o600 },
  );
  const forbiddenError = await rejectTransitionWithoutEcho(
    receiptPath,
    transition("completed", 5, at(6), completionEvidence(result)),
    forbiddenCredential,
  );
  assert.match(forbiddenError.message, /invalid shape/);
  assert.doesNotMatch(forbiddenError.message, /prompt/i);

  const malformedReceiptPath = path.join(directory, "malformed-receipt.json");
  await createRun(malformedReceiptPath);
  const receiptCredential = "xoxb-malformedcredential";
  await writeFile(
    malformedReceiptPath,
    `{"credential":"${receiptCredential}"`,
    { mode: 0o600 },
  );
  const receiptError = await assertRejectsWithoutEcho(
    () => readReceiptFile(malformedReceiptPath),
    receiptCredential,
  );
  assert.match(receiptError.message, /receipt file is invalid JSON/);
});

test("historical, wrong-run, wrong-target, and secret-shaped evidence is rejected", async (t) => {
  const directory = await temporaryWorkspace(t);
  const receiptPath = path.join(directory, "receipt.json");
  await createRun(receiptPath);

  await assert.rejects(
    transitionReceiptFile(
      receiptPath,
      transition("auth_ready", 0, at(1), {
        run_id: "run-foreign-123456",
        source: "browser",
        profile_fingerprint: PROFILE_FINGERPRINT,
        challenge_observed: false,
      }),
    ),
    /run_id does not match/,
  );
  const forbiddenError = await rejectTransitionWithoutEcho(
    receiptPath,
    transition("auth_ready", 0, at(1), {
      source: "browser",
      profile_fingerprint: PROFILE_FINGERPRINT,
      challenge_observed: false,
      prompt: "must never persist",
    }),
    "must never persist",
  );
  assert.match(forbiddenError.message, /forbidden field/);
  assert.doesNotMatch(forbiddenError.message, /prompt/i);

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
  await assert.rejects(
    transitionReceiptFile(
      receiptPath,
      transition("model_tool_verified", 2, at(3), {
        source: "browser",
        target_id: "wrong-target",
        model_requested: "gpt-5.4-pro",
        model_observed: "gpt-5.4-pro",
        model_proven: true,
        tool_requested: "deep-research",
        tool_observed: "deep-research",
        tool_proven: true,
      }),
    ),
    /target_id does not match/,
  );
  await assert.rejects(
    transitionReceiptFile(
      receiptPath,
      transition("model_tool_verified", 2, at(3), {
        source: "browser",
        target_id: TARGET_ID,
        model_requested: "gpt-5.4-pro",
        model_observed: "gpt-5.4-instant",
        model_proven: true,
        tool_requested: "deep-research",
        tool_observed: "deep-research",
        tool_proven: true,
      }),
    ),
    /exact Pro model/,
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
      baseline_assistant_turn_position: BASELINE_POSITION,
      user_turn_id: USER_TURN,
      user_turn_position: USER_POSITION,
      request_fingerprint: REQUEST_FINGERPRINT,
      deadline_at: at(10),
    }),
  );
  await assert.rejects(
    transitionReceiptFile(
      receiptPath,
      transition("started", 4, at(5), {
        source: "browser",
        target_id: TARGET_ID,
        conversation_url: CONVERSATION_URL,
        user_turn_id: USER_TURN,
        assistant_signal_id: BASELINE_TURN,
        assistant_signal_position: START_POSITION,
      }),
    ),
    /ordered after the submitted user turn/,
  );
  await assert.rejects(
    transitionReceiptFile(
      receiptPath,
      transition("started", 4, at(5), {
        source: "browser",
        target_id: TARGET_ID,
        conversation_url: CONVERSATION_URL,
        user_turn_id: USER_TURN,
        assistant_signal_id: "older-distinct-assistant",
        assistant_signal_position: BASELINE_POSITION,
      }),
    ),
    /ordered after the submitted user turn/,
  );
});

test("failed and cancelled are terminal and require exact stage-bound evidence", async (t) => {
  const directory = await temporaryWorkspace(t);
  const failedPath = path.join(directory, "failed.json");
  await createRun(failedPath);
  await assert.rejects(
    transitionReceiptFile(
      failedPath,
      transition("failed", 0, at(1), {
        source: "controller",
        code: "auth_missing",
        stage: "auth_ready",
      }),
    ),
    /failure stage does not match/,
  );
  const failed = await transitionReceiptFile(
    failedPath,
    transition("failed", 0, at(1), {
      source: "controller",
      code: "auth_missing",
      stage: "created",
    }),
  );
  assert.equal(failed.state, "failed");
  assert.deepEqual(failed.error, { code: "auth_missing", stage: "created" });

  const cancelledPath = path.join(directory, "cancelled.json");
  await createRun(cancelledPath);
  await assert.rejects(
    transitionReceiptFile(
      cancelledPath,
      transition("cancelled", 0, at(1), {
        source: "controller",
        actor: "user",
        reason_code: "user_request",
        last_state: "created",
      }),
    ),
    /source must match/,
  );
  const cancelled = await transitionReceiptFile(
    cancelledPath,
    transition("cancelled", 0, at(1), {
      source: "user",
      actor: "user",
      reason_code: "user_request",
      last_state: "created",
    }),
  );
  assert.equal(cancelled.state, "cancelled");
});

test("timed_out requires a submitted run and an elapsed deadline", async (t) => {
  const directory = await temporaryWorkspace(t);
  const receiptPath = path.join(directory, "receipt.json");
  await advanceToStarted(receiptPath);
  const evidence = {
    source: "controller",
    target_id: TARGET_ID,
    conversation_url: CONVERSATION_URL,
    user_turn_id: USER_TURN,
    deadline_at: at(10),
    last_state: "started",
  };
  await assert.rejects(
    transitionReceiptFile(
      receiptPath,
      transition("timed_out", 5, at(9), evidence),
    ),
    /cannot precede its anchored deadline/,
  );
  const timedOut = await transitionReceiptFile(
    receiptPath,
    transition("timed_out", 5, at(10), evidence),
  );
  assert.equal(timedOut.state, "timed_out");
  assert.equal(timedOut.error.code, "deadline_exceeded");

  const futurePath = path.join(directory, "future.json");
  const futureDeadline = "2100-01-01T00:00:00.000Z";
  await advanceToStarted(futurePath, { deadlineAt: futureDeadline });
  await assert.rejects(
    transitionReceiptFile(
      futurePath,
      transition("timed_out", 5, futureDeadline, {
        source: "controller",
        target_id: TARGET_ID,
        conversation_url: CONVERSATION_URL,
        user_turn_id: USER_TURN,
        deadline_at: futureDeadline,
        last_state: "started",
      }),
    ),
    /cannot precede its anchored deadline/,
  );
});

test("delivery_failed preserves a verified local result without claiming completed", async (t) => {
  const directory = await temporaryWorkspace(t);
  const receiptPath = path.join(directory, "receipt.json");
  await advanceToStarted(receiptPath);
  const result = await writeResultAtomic(
    path.join(directory, "result.md"),
    "locally complete but not delivered",
    { runId: RUN_ID },
  );
  const staleFinal = {
    source: "delivery",
    target_id: TARGET_ID,
    conversation_url: CONVERSATION_URL,
    user_turn_id: USER_TURN,
    final_assistant_turn_id: START_SIGNAL,
    final_assistant_turn_position: START_POSITION,
    result,
    destination_id: "caller-d3",
    delivery_code: "transport_closed",
  };
  await assert.rejects(
    transitionReceiptFile(
      receiptPath,
      transition("delivery_failed", 5, at(6), staleFinal),
    ),
    /requires a new final assistant turn/,
  );
  const deliveryFailed = await transitionReceiptFile(
    receiptPath,
    transition("delivery_failed", 5, at(6), {
      source: "delivery",
      target_id: TARGET_ID,
      conversation_url: CONVERSATION_URL,
      user_turn_id: USER_TURN,
      final_assistant_turn_id: "assistant-final-123",
      final_assistant_turn_position: FINAL_POSITION,
      result,
      destination_id: "caller-d3",
      delivery_code: "transport_closed",
    }),
  );
  assert.equal(deliveryFailed.state, "delivery_failed");
  assert.equal(deliveryFailed.result.sha256, result.sha256);
  assert.deepEqual(deliveryFailed.error, {
    code: "transport_closed",
    stage: "delivery",
    destination_id: "caller-d3",
  });
});

test("concurrent transitions serialize and only one revision wins", async (t) => {
  const directory = await temporaryWorkspace(t);
  const receiptPath = path.join(directory, "receipt.json");
  await createRun(receiptPath);
  const evidence = {
    source: "browser",
    profile_fingerprint: PROFILE_FINGERPRINT,
    challenge_observed: false,
  };
  const attempts = await Promise.allSettled([
    transitionReceiptFile(
      receiptPath,
      transition("auth_ready", 0, at(1), evidence, "race-a"),
    ),
    transitionReceiptFile(
      receiptPath,
      transition("auth_ready", 0, at(1), evidence, "race-b"),
    ),
  ]);
  assert.equal(
    attempts.filter((attempt) => attempt.status === "fulfilled").length,
    1,
  );
  const rejection = attempts.find((attempt) => attempt.status === "rejected");
  assert.match(rejection.reason.message, /revision mismatch/);
  const receipt = await readReceiptFile(receiptPath);
  assert.equal(receipt.state, "auth_ready");
  assert.equal(receipt.revision, 1);
});

test("concurrent use of the immutable receipt lock remains serialized", async (t) => {
  const directory = await temporaryWorkspace(t);
  const receiptPath = path.join(directory, "receipt.json");
  await createRun(receiptPath);
  const evidence = {
    source: "browser",
    profile_fingerprint: PROFILE_FINGERPRINT,
    challenge_observed: false,
  };
  const attempts = await Promise.allSettled([
    transitionReceiptFile(
      receiptPath,
      transition("auth_ready", 0, at(1), evidence, "stale-race-a"),
      { postAcquireDelayMs: 50 },
    ),
    transitionReceiptFile(
      receiptPath,
      transition("auth_ready", 0, at(1), evidence, "stale-race-b"),
    ),
  ]);
  assert.equal(
    attempts.filter((attempt) => attempt.status === "fulfilled").length,
    1,
  );
  assert.match(
    attempts.find((attempt) => attempt.status === "rejected").reason.message,
    /revision mismatch/,
  );
  assert.equal((await readReceiptFile(receiptPath)).revision, 1);
});

test("receipt publication requires an exclusive lock and transitions never recreate it", async (t) => {
  const directory = await temporaryWorkspace(t);
  const blockedReceiptPath = path.join(directory, "blocked.json");
  await writeFile(`${blockedReceiptPath}.lock`, "", { mode: 0o600 });
  await assert.rejects(
    createRun(blockedReceiptPath),
    (error) => error.code === "EEXIST",
  );
  await assert.rejects(stat(blockedReceiptPath), { code: "ENOENT" });

  const receiptPath = path.join(directory, "missing-lock.json");
  await createRun(receiptPath);
  const before = await readFile(receiptPath);
  await rm(`${receiptPath}.lock`);
  await assert.rejects(
    transitionReceiptFile(
      receiptPath,
      transition("auth_ready", 0, at(1), {
        source: "browser",
        profile_fingerprint: PROFILE_FINGERPRINT,
        challenge_observed: false,
      }),
    ),
    (error) => error.code === "ENOENT",
  );
  await assert.rejects(stat(`${receiptPath}.lock`), { code: "ENOENT" });
  assert.deepEqual(await readFile(receiptPath), before);
});

test("receipt lock replacement and replace-restore ABA fail before mutation", async (t) => {
  const directory = await temporaryWorkspace(t);
  const originalSetTimeout = globalThis.setTimeout;

  for (const scenario of ["replacement", "aba"]) {
    const receiptPath = path.join(directory, `${scenario}.json`);
    const lockPath = `${receiptPath}.lock`;
    const movedLock = `${lockPath}.moved`;
    await createRun(receiptPath);
    const delay = scenario === "replacement" ? 8_881 : 8_882;
    let releaseDelay;
    let signalLocked;
    const locked = new Promise((resolvePromise) => {
      signalLocked = resolvePromise;
    });
    globalThis.setTimeout = (callback, milliseconds, ...arguments_) => {
      if (milliseconds === delay) {
        releaseDelay = () => callback(...arguments_);
        signalLocked();
        return undefined;
      }
      return originalSetTimeout(callback, milliseconds, ...arguments_);
    };

    let operation;
    try {
      operation = transitionReceiptFile(
        receiptPath,
        transition("auth_ready", 0, at(1), {
          source: "browser",
          profile_fingerprint: PROFILE_FINGERPRINT,
          challenge_observed: false,
        }),
        { postAcquireDelayMs: delay },
      );
      await locked;
      await rename(lockPath, movedLock);
      await writeFile(lockPath, "", { mode: 0o600 });
      if (scenario === "aba") {
        await rm(lockPath);
        await rename(movedLock, lockPath);
      }
      releaseDelay();
      await assert.rejects(operation, /receipt lock was replaced/);
      const receipt = await readReceiptFile(receiptPath);
      assert.equal(receipt.state, "created");
      assert.equal(receipt.revision, 0);
    } finally {
      releaseDelay?.();
      await operation?.catch(() => {});
      globalThis.setTimeout = originalSetTimeout;
    }
  }
});

test("split receipt lock rejects the replacement domain and reconciles the winning commit", async (t) => {
  const directory = await temporaryWorkspace(t);
  const receiptPath = path.join(directory, "receipt.json");
  const lockPath = `${receiptPath}.lock`;
  const displacedLockPath = `${lockPath}.displaced`;
  const initial = await createRun(receiptPath);
  const lockMetadata = await stat(lockPath, { bigint: true });
  assert.deepEqual(initial.receipt_lock, {
    dev: lockMetadata.dev.toString(),
    ino: lockMetadata.ino.toString(),
    ctime_ns: lockMetadata.ctimeNs.toString(),
  });

  const childTransition = transition(
    "auth_ready",
    0,
    at(1),
    {
      source: "browser",
      profile_fingerprint: PROFILE_FINGERPRINT,
      challenge_observed: false,
    },
    "split-owner-a",
  );
  const temporaryStop = stopChildOnPathEvent(
    directory,
    (eventType, filename, transitionChild) =>
      eventType === "rename" &&
      filename?.startsWith(
        `.receipt.json.${transitionChild?.pid}.`,
      ) &&
      filename.endsWith(".tmp"),
  );
  t.after(temporaryStop.close);
  const { child, outcome } = spawnTransitionChild(
    receiptPath,
    childTransition,
    { preCommitDelayMs: 500, postCommitDelayMs: 100 },
  );
  temporaryStop.attach(child);
  t.after(() => {
    child.kill("SIGCONT");
    child.kill("SIGKILL");
  });
  await temporaryStop.stopped;
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 10));
  assert.equal((await readReceiptFile(receiptPath)).revision, 0);

  await rename(lockPath, displacedLockPath);
  await writeFile(lockPath, "", { mode: 0o600 });
  await assert.rejects(
    transitionReceiptFile(
      receiptPath,
      transition(
        "failed",
        0,
        at(1),
        {
          source: "controller",
          code: "split_domain",
          stage: "created",
        },
        "split-owner-b",
      ),
    ),
    /immutable receipt binding/,
  );
  assert.equal((await readReceiptFile(receiptPath)).revision, 0);

  child.kill("SIGCONT");
  const ownerOutcome = await outcome;
  assert.equal(ownerOutcome.ok, true, JSON.stringify(ownerOutcome));
  assert.deepEqual(
    {
      ok: ownerOutcome.ok,
      state: ownerOutcome.state,
      revision: ownerOutcome.revision,
    },
    { ok: true, state: "auth_ready", revision: 1 },
  );
  const final = await readReceiptFile(receiptPath);
  assert.equal(final.receipt_hash, ownerOutcome.receipt_hash);
  assert.equal(final.state, "auth_ready");
  assert.deepEqual(final.receipt_lock, initial.receipt_lock);
});

test("post-rename receipt conflict reports an explicitly unprovable commit", async (t) => {
  const directory = await temporaryWorkspace(t);
  const receiptPath = path.join(directory, "receipt.json");
  const lockPath = `${receiptPath}.lock`;
  const initial = await createRun(receiptPath);
  const initialBytes = await readFile(receiptPath);
  const childTransition = transition(
    "auth_ready",
    0,
    at(1),
    {
      source: "browser",
      profile_fingerprint: PROFILE_FINGERPRINT,
      challenge_observed: false,
    },
    "unprovable-owner",
  );
  const temporaryStop = stopChildOnPathEvent(
    directory,
    (eventType, filename, transitionChild) =>
      eventType === "rename" &&
      filename?.startsWith(
        `.receipt.json.${transitionChild?.pid}.`,
      ) &&
      filename.endsWith(".tmp"),
  );
  t.after(temporaryStop.close);
  const { child, outcome } = spawnTransitionChild(
    receiptPath,
    childTransition,
    { preCommitDelayMs: 500, postCommitDelayMs: 500 },
  );
  temporaryStop.attach(child);
  t.after(() => {
    child.kill("SIGCONT");
    child.kill("SIGKILL");
  });
  await temporaryStop.stopped;
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 10));
  assert.equal((await readReceiptFile(receiptPath)).revision, 0);

  await rename(lockPath, `${lockPath}.displaced`);
  await writeFile(lockPath, "", { mode: 0o600 });
  const commitStop = stopChildOnPathEvent(
    directory,
    (eventType, filename) => filename === "receipt.json",
  );
  commitStop.attach(child);
  t.after(commitStop.close);
  child.kill("SIGCONT");
  await commitStop.stopped;
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 10));
  assert.equal((await readReceiptFile(receiptPath)).state, "auth_ready");

  await writeFile(receiptPath, initialBytes, { mode: 0o600 });
  child.kill("SIGCONT");
  const conflicted = await outcome;
  assert.deepEqual(
    {
      ok: conflicted.ok,
      code: conflicted.code,
      message: conflicted.message,
    },
    {
      ok: false,
      code: "ORACLE_SUBAGENT_COMMIT_UNPROVABLE",
      message:
        "oracle-subagent state: transition commit outcome is unprovable",
    },
  );
  assert.deepEqual(await readReceiptFile(receiptPath), initial);
});

test("precreated advisory locks recover from holder death and symlinks fail closed", async (t) => {
  const directory = await temporaryWorkspace(t);
  const receiptPath = path.join(directory, "receipt.json");
  await createRun(receiptPath);
  const lockPath = `${receiptPath}.lock`;
  const recovered = await transitionReceiptFile(
    receiptPath,
    transition("auth_ready", 0, at(1), {
      source: "browser",
      profile_fingerprint: PROFILE_FINGERPRINT,
      challenge_observed: false,
    }),
  );
  assert.equal(recovered.state, "auth_ready");

  const holder = await holdAdvisoryLock(lockPath);
  try {
    await assert.rejects(
      transitionReceiptFile(
        receiptPath,
        transition("target_bound", 1, at(2), {
          source: "browser",
          target_id: TARGET_ID,
          target_url: TARGET_URL,
          browser_pid: 4242,
        }),
        { timeoutMs: 50, pollMs: 5 },
      ),
      /timed out waiting for receipt lock/,
    );
  } finally {
    await stopLockHolder(holder);
  }

  const crashHolder = await holdAdvisoryLock(lockPath);
  await stopLockHolder(crashHolder, "SIGKILL");
  const afterCrash = await transitionReceiptFile(
    receiptPath,
    transition("target_bound", 1, at(2), {
      source: "browser",
      target_id: TARGET_ID,
      target_url: TARGET_URL,
      browser_pid: 4242,
    }),
  );
  assert.equal(afterCrash.state, "target_bound");

  const target = path.join(directory, "symlink-target");
  await writeFile(target, "preserve", { mode: 0o600 });
  const resultLink = path.join(directory, "result-link.md");
  await symlink(target, resultLink);
  await assert.rejects(
    writeResultAtomic(resultLink, "replacement", { runId: RUN_ID }),
    /refusing to replace a non-regular artifact path/,
  );
  assert.equal(await readFile(target, "utf8"), "preserve");

  const symlinkReceiptPath = path.join(directory, "symlink-lock-receipt.json");
  await createRun(symlinkReceiptPath);
  const lockTarget = path.join(directory, "lock-target");
  await writeFile(lockTarget, "preserve", { mode: 0o600 });
  await rename(
    `${symlinkReceiptPath}.lock`,
    `${symlinkReceiptPath}.lock.displaced`,
  );
  await symlink(lockTarget, `${symlinkReceiptPath}.lock`);
  await assert.rejects(
    transitionReceiptFile(
      symlinkReceiptPath,
      transition("auth_ready", 0, at(1), {
        source: "browser",
        profile_fingerprint: PROFILE_FINGERPRINT,
        challenge_observed: false,
      }),
    ),
    /ELOOP|symbolic link/,
  );
  assert.equal(await readFile(lockTarget, "utf8"), "preserve");
});

test("receipt tampering and duplicate creation fail without replacement", async (t) => {
  const directory = await temporaryWorkspace(t);
  const receiptPath = path.join(directory, "receipt.json");
  const original = await createRun(receiptPath);
  await assert.rejects(
    createRun(receiptPath),
    (error) => error.code === "EEXIST",
  );
  assert.deepEqual(await readReceiptFile(receiptPath), original);

  const tampered = JSON.parse(await readFile(receiptPath, "utf8"));
  tampered.state = "completed";
  await writeFile(receiptPath, `${JSON.stringify(tampered)}\n`, { mode: 0o600 });
  await assert.rejects(readReceiptFile(receiptPath), /receipt head|receipt hash/);

  const inMemory = createReceipt({
    runId: RUN_ID,
    slug: SLUG,
    mode: "pro",
    requestFingerprint: REQUEST_FINGERPRINT,
    receiptLock: { dev: "1", ino: "2", ctime_ns: "3" },
    createdAt: at(0),
    eventId: "event-created-memory",
  });
  inMemory.history[0].evidence.request_fingerprint = "f".repeat(64);
  assert.throws(() => validateReceipt(inMemory), /hash-valid|receipt hash/);
});

test("semantic replay rejects rehashed derived-state, evidence, and event-id tampering", async (t) => {
  const directory = await temporaryWorkspace(t);
  const receiptPath = path.join(directory, "receipt.json");
  const started = await advanceToStarted(receiptPath);

  const derivedTamper = structuredClone(started);
  derivedTamper.target.id = "attacker-target";
  rehashTamperedReceipt(derivedTamper);
  assert.throws(
    () => validateReceipt(derivedTamper),
    /target does not match replayed history/,
  );

  const evidenceTamper = structuredClone(started);
  evidenceTamper.history[3].evidence.target_id = "attacker-target";
  rehashTamperedReceipt(evidenceTamper);
  assert.throws(
    () => validateReceipt(evidenceTamper),
    /target_id does not match/,
  );

  const duplicateEvent = structuredClone(started);
  duplicateEvent.history.at(-1).event_id = duplicateEvent.history[0].event_id;
  rehashTamperedReceipt(duplicateEvent);
  assert.throws(
    () => validateReceipt(duplicateEvent),
    /duplicate event_id/,
  );
});
