import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  chmod,
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
  appendRunEvent,
  createRunArtifacts,
  EVENT_SCHEMA,
  publicRequestMetadata,
  readRunEvents,
  readRunRequest,
  REQUEST_SCHEMA,
  runArtifactLayout,
  verifyRunArtifactPermissions,
  writeRunResult,
} from "../assets/scripts/oracle-subagent-artifacts.mjs";
import {
  transitionReceiptFile,
} from "../assets/scripts/oracle-subagent-state.mjs";

const RUN_ID = "run-artifacts-123456";
const REQUEST_FINGERPRINT = "a".repeat(64);
const CREATED_AT = "2026-07-28T06:00:00.000Z";
const PRIVATE_PROMPT =
  "Use https://internal.example.test/?token=private and cookie=session-secret";

async function workspace(t) {
  const directory = await mkdtemp(path.join(os.tmpdir(), "oracle-artifacts-test-"));
  t.after(async () => {
    await rm(directory, { recursive: true, force: true });
  });
  return realpath(directory);
}

function request(overrides = {}) {
  return {
    run_id: RUN_ID,
    slug: "artifact-proof",
    mode: "deep-research",
    request_fingerprint: REQUEST_FINGERPRINT,
    prompt: PRIVATE_PROMPT,
    attachments: [],
    created_at: CREATED_AT,
    event_id: "event-created-123456",
    ...overrides,
  };
}

async function mode(pathname) {
  return (await stat(pathname)).mode & 0o777;
}

function eventFromReceipt(receipt) {
  const head = receipt.history.at(-1);
  const event = {
    event_id: head.event_id,
    run_id: receipt.run_id,
    state: receipt.state,
    revision: receipt.revision,
    observed_at: head.observed_at,
    source: head.evidence.source,
    receipt_hash: receipt.receipt_hash,
  };
  if (receipt.error) event.code = receipt.error.code;
  if (receipt.target) {
    event.target_fingerprint = createHash("sha256")
      .update(receipt.target.id)
      .digest("hex");
  }
  if (receipt.result) event.result_sha256 = receipt.result.sha256;
  return event;
}

test("creates a private run envelope and keeps prompt data out of logs", async (t) => {
  const parent = await workspace(t);
  const root = path.join(parent, "runs");
  const created = await createRunArtifacts(root, request());
  const { layout, receipt, public_request: publicRequest } = created;

  assert.equal(receipt.state, "created");
  assert.equal(publicRequest.schema, REQUEST_SCHEMA);
  assert.equal(publicRequest.run_id, RUN_ID);
  assert.equal(publicRequest.attachment_count, 0);
  assert.equal(Object.hasOwn(publicRequest, "prompt"), false);
  assert.equal(await mode(root), 0o700);
  assert.equal(await mode(layout.directory), 0o700);
  for (const pathname of [layout.request, layout.events, layout.receipt]) {
    assert.equal(await mode(pathname), 0o600);
  }

  const storedRequest = await readRunRequest(layout);
  assert.equal(storedRequest.prompt, PRIVATE_PROMPT);
  const events = await readRunEvents(layout);
  assert.equal(events.length, 1);
  assert.equal(events[0].schema, EVENT_SCHEMA);
  assert.equal(events[0].state, "created");

  const eventLog = await readFile(layout.events, "utf8");
  const receiptFile = await readFile(layout.receipt, "utf8");
  for (const publicArtifact of [
    eventLog,
    receiptFile,
    JSON.stringify(publicRequest),
  ]) {
    assert.doesNotMatch(publicArtifact, /internal\.example|session-secret|prompt/i);
  }
  assert.match(await readFile(layout.request, "utf8"), /session-secret/);
  assert.equal(await verifyRunArtifactPermissions(layout), true);
});

test("appends only strict secret-free run-bound events", async (t) => {
  const parent = await workspace(t);
  const root = path.join(parent, "runs");
  const { layout } = await createRunArtifacts(root, request());
  const authReady = await transitionReceiptFile(layout.receipt, {
    to: "auth_ready",
    expectedRevision: 0,
    eventId: "event-auth-ready-123456",
    observedAt: "2026-07-28T06:00:01.000Z",
    evidence: {
      run_id: RUN_ID,
      source: "browser",
      profile_fingerprint: "b".repeat(64),
      challenge_observed: false,
    },
  });
  const event = await appendRunEvent(layout, eventFromReceipt(authReady));
  assert.equal(event.state, "auth_ready");
  assert.equal((await readRunEvents(layout)).length, 2);

  for (const [field, value] of [
    ["prompt", "do not log"],
    ["cookie", "session-secret"],
    ["authorization", "Bearer abc"],
    ["url", "https://chatgpt.com/c/private"],
  ]) {
    await assert.rejects(
      appendRunEvent(layout, {
        event_id: `event-forbidden-${field}-123456`,
        run_id: RUN_ID,
        state: "target_bound",
        revision: 2,
        observed_at: "2026-07-28T06:00:02.000Z",
        source: "browser",
        receipt_hash: authReady.receipt_hash,
        [field]: value,
      }),
      /contains a forbidden field/,
    );
  }
  for (const eventId of [
    "event-sk-proj-abcdefghijklmnop",
    "github_pat_abcdefghijklmnopqrstuvwxyz123456",
    "xapp-1-abcdefghijklmnopqrstuvwxyz123456",
  ]) {
    await assert.rejects(
      appendRunEvent(layout, {
        event_id: eventId,
        run_id: RUN_ID,
        state: "target_bound",
        revision: 2,
        observed_at: "2026-07-28T06:00:02.000Z",
        source: "browser",
        receipt_hash: authReady.receipt_hash,
      }),
      /sensitive log text/,
    );
  }
  await assert.rejects(
    appendRunEvent(layout, {
      event_id: "event-wrong-run-123456",
      run_id: "run-foreign-123456",
      state: "target_bound",
      revision: 2,
      observed_at: "2026-07-28T06:00:02.000Z",
      source: "browser",
      receipt_hash: authReady.receipt_hash,
    }),
    /not bound to this run/,
  );
  assert.equal((await readRunEvents(layout)).length, 2);
});

test("concurrent event appends serialize and only the receipt head wins", async (t) => {
  const parent = await workspace(t);
  const root = path.join(parent, "runs");
  const { layout } = await createRunArtifacts(root, request());
  const authReady = await transitionReceiptFile(layout.receipt, {
    to: "auth_ready",
    expectedRevision: 0,
    eventId: "event-auth-race-123456",
    observedAt: "2026-07-28T06:00:01.000Z",
    evidence: {
      run_id: RUN_ID,
      source: "browser",
      profile_fingerprint: "b".repeat(64),
      challenge_observed: false,
    },
  });
  const attempts = await Promise.allSettled([
    appendRunEvent(layout, eventFromReceipt(authReady)),
    appendRunEvent(layout, eventFromReceipt(authReady)),
  ]);
  assert.equal(
    attempts.filter((attempt) => attempt.status === "fulfilled").length,
    1,
  );
  assert.match(
    attempts.find((attempt) => attempt.status === "rejected").reason.message,
    /revision does not append|event_id already exists/,
  );
  assert.equal((await readRunEvents(layout)).length, 2);

  await assert.rejects(
    readRunEvents({ ...layout, events: layout.receipt }),
    /layout does not match/,
  );
});

test("receipt transition and event projection share one serialization lock", async (t) => {
  const parent = await workspace(t);
  const root = path.join(parent, "runs");
  const { layout } = await createRunArtifacts(root, request());
  const authReady = await transitionReceiptFile(layout.receipt, {
    to: "auth_ready",
    expectedRevision: 0,
    eventId: "event-auth-projection-race-123456",
    observedAt: "2026-07-28T06:00:01.000Z",
    evidence: {
      run_id: RUN_ID,
      source: "browser",
      profile_fingerprint: "b".repeat(64),
      challenge_observed: false,
    },
  });
  const targetTransition = transitionReceiptFile(
    layout.receipt,
    {
      to: "target_bound",
      expectedRevision: 1,
      eventId: "event-target-projection-race-123456",
      observedAt: "2026-07-28T06:00:02.000Z",
      evidence: {
        run_id: RUN_ID,
        source: "browser",
        target_id: "A".repeat(32),
        target_url: "https://chatgpt.com/",
        browser_pid: 4242,
      },
    },
    { postAcquireDelayMs: 100 },
  );
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 20));
  const staleProjection = appendRunEvent(layout, eventFromReceipt(authReady));
  await targetTransition;
  await assert.rejects(staleProjection, /does not exactly project/);
  assert.equal((await readRunEvents(layout)).length, 1);
});

test("writes nonempty private result and run-bound atomic proof", async (t) => {
  const parent = await workspace(t);
  const root = path.join(parent, "runs");
  const { layout } = await createRunArtifacts(root, request());
  const result = await writeRunResult(layout, "# Final report\n");

  assert.equal(result.run_id, RUN_ID);
  assert.equal(result.path, layout.result);
  assert.equal(await mode(layout.result), 0o600);
  assert.equal(await mode(result.proof_path), 0o600);
  assert.equal(await verifyRunArtifactPermissions(layout, { requireResult: true }), true);
  await assert.rejects(writeRunResult(layout, ""), /must be nonempty/);

  const terminal = await createRunArtifacts(
    root,
    request({
      run_id: "run-terminal-123456",
      event_id: "event-terminal-created-123456",
    }),
  );
  await transitionReceiptFile(terminal.layout.receipt, {
    to: "cancelled",
    expectedRevision: 0,
    eventId: "event-terminal-cancelled-123456",
    observedAt: "2026-07-28T06:00:01.000Z",
    evidence: {
      run_id: terminal.layout.run_id,
      source: "user",
      actor: "user",
      reason_code: "user_request",
      last_state: "created",
    },
  });
  await assert.rejects(
    writeRunResult(terminal.layout, "late overwrite"),
    /receipt is terminal/,
  );
});

test("terminal transition wins atomically over a queued result write", async (t) => {
  const parent = await workspace(t);
  const root = path.join(parent, "runs");
  const { layout } = await createRunArtifacts(root, request());
  const cancellation = transitionReceiptFile(
    layout.receipt,
    {
      to: "cancelled",
      expectedRevision: 0,
      eventId: "event-cancel-race-123456",
      observedAt: "2026-07-28T06:00:01.000Z",
      evidence: {
        run_id: RUN_ID,
        source: "user",
        actor: "user",
        reason_code: "user_request",
        last_state: "created",
      },
    },
    { postAcquireDelayMs: 100 },
  );
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 20));
  const lateWrite = writeRunResult(layout, "must not land");
  await cancellation;
  await assert.rejects(lateWrite, /receipt is terminal/);
  await assert.rejects(stat(layout.result), (error) => error.code === "ENOENT");
});

test("rejects duplicates, unsafe roots, symlinks, torn logs, and bad revisions", async (t) => {
  const parent = await workspace(t);
  const root = path.join(parent, "runs");
  const { layout } = await createRunArtifacts(root, request());
  await assert.rejects(createRunArtifacts(root, request()), (error) =>
    ["EEXIST", "ENOTEMPTY"].includes(error.code),
  );

  const insecureRoot = path.join(parent, "insecure");
  await createRunArtifacts(insecureRoot, request({ run_id: "run-insecure-123456" }));
  await chmod(insecureRoot, 0o755);
  await assert.rejects(
    createRunArtifacts(
      insecureRoot,
      request({ run_id: "run-insecure-next-123456" }),
    ),
    /grants group\/world access/,
  );

  const symlinkRoot = path.join(parent, "runs-link");
  await symlink(root, symlinkRoot, "dir");
  await assert.rejects(
    createRunArtifacts(
      symlinkRoot,
      request({ run_id: "run-symlink-123456" }),
    ),
    /not a real directory|traverses a symlink/,
  );

  await writeFile(layout.events, '{"torn":true}', { mode: 0o600 });
  await assert.rejects(readRunEvents(layout), /torn final record/);

  const cleanLayout = runArtifactLayout(root, "run-clean-events-123456");
  const clean = await createRunArtifacts(
    root,
    request({ run_id: cleanLayout.run_id, event_id: "event-clean-123456" }),
  );
  await assert.rejects(
    appendRunEvent(clean.layout, {
      event_id: "event-gap-123456",
      run_id: cleanLayout.run_id,
      state: "auth_ready",
      revision: 2,
      observed_at: "2026-07-28T06:00:01.000Z",
      source: "browser",
      receipt_hash: "b".repeat(64),
    }),
    /does not exactly project|revision does not append/,
  );
});

test("public metadata cannot be expanded with prompt or credential fields", () => {
  const metadata = publicRequestMetadata(request());
  assert.deepEqual(Object.keys(metadata).sort(), [
    "attachment_count",
    "created_at",
    "mode",
    "request_fingerprint",
    "run_id",
    "schema",
    "slug",
  ]);
  assert.throws(
    () =>
      publicRequestMetadata({
        ...request(),
        slug: "sk-proj-abcdefghijklmnop",
      }),
    /sensitive log text/,
  );
  for (const runId of [
    "github_pat_abcdefghijklmnopqrstuvwxyz123456",
    "xapp-1-abcdefghijklmnopqrstuvwxyz123456",
  ]) {
    assert.throws(
      () =>
        publicRequestMetadata({
          ...request(),
          run_id: runId,
        }),
      /sensitive log text/,
    );
  }
  const secretKey = "https://private.example/?token=never-log\n";
  assert.throws(
    () =>
      publicRequestMetadata({
        ...request(),
        [secretKey]: "value",
      }),
    (error) => {
      assert.match(error.message, /contains a forbidden field/);
      assert.doesNotMatch(error.message, /private\.example|never-log|token/);
      return true;
    },
  );
});

test("malformed private request errors never echo request bytes", async (t) => {
  const parent = await workspace(t);
  const root = path.join(parent, "runs");
  const { layout } = await createRunArtifacts(root, request());
  const privateFragment =
    '{"schema":"oracle-subagent.request.v1","prompt":"sk-proj-never-echo';
  await writeFile(layout.request, privateFragment, { mode: 0o600 });

  await assert.rejects(
    readRunRequest(layout),
    (error) => {
      assert.match(error.message, /request file is not valid JSON/);
      assert.doesNotMatch(error.message, /sk-proj|never-echo|prompt/);
      return true;
    },
  );
});
