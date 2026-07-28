import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import {
  mkdtemp,
  readFile,
  realpath,
  rm,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  createRunArtifacts,
  writeRunResult,
} from "../assets/scripts/oracle-subagent-artifacts.mjs";
import {
  cancelOracleRun,
  OracleSubagentResumeError,
  resumeOracleRun,
} from "../assets/scripts/oracle-subagent-resume.mjs";
import {
  readReceiptFile,
  transitionReceiptFile,
} from "../assets/scripts/oracle-subagent-state.mjs";

const THIS_FILE = fileURLToPath(import.meta.url);
const BASE_TIME = Date.parse("2026-07-28T12:00:00.000Z");
const QUEUE_CONFIG = Object.freeze({
  target_ids: ["target-resume-alpha"],
  max_active: 1,
  max_depth: 8,
  lease_duration_ms: 10_000,
});
const PRIVATE_PROMPT =
  "Private analysis with cookie=session-private and an internal URL.";

function at(offset) {
  return new Date(BASE_TIME + offset * 1_000).toISOString();
}

function fingerprint(character) {
  return character.repeat(64);
}

async function workspace(t) {
  const parent = await realpath(
    await mkdtemp(path.join(os.tmpdir(), "oracle-resume-test-")),
  );
  t.after(() => rm(parent, { recursive: true, force: true }));
  return path.join(parent, "runs");
}

async function createRun(
  root,
  {
    runId = "run-resume-0001",
    character = "a",
    createdAt = at(0),
  } = {},
) {
  const requestFingerprint = fingerprint(character);
  const created = await createRunArtifacts(root, {
    run_id: runId,
    slug: `resume-${character}`,
    mode: "deep-research",
    request_fingerprint: requestFingerprint,
    prompt: PRIVATE_PROMPT,
    attachments: [],
    created_at: createdAt,
    event_id: `event-created-${runId}`,
  });
  return {
    ...created,
    runId,
    requestFingerprint,
    createdAt,
  };
}

function resumeRequest(
  run,
  {
    candidateRunId = run.runId,
    ownerId = "owner-resume-0001",
    nowMs = 100,
  } = {},
) {
  return {
    request_fingerprint: run.requestFingerprint,
    candidate_run_id: candidateRunId,
    owner_id: ownerId,
    now_ms: nowMs,
  };
}

function transition(to, revision, observedAt, runId, evidence) {
  return {
    to,
    expectedRevision: revision,
    eventId: `event-${to}-${revision}-${runId}`,
    observedAt,
    evidence: { run_id: runId, ...evidence },
  };
}

async function advanceToModelVerified(run) {
  const targetId = QUEUE_CONFIG.target_ids[0];
  await transitionReceiptFile(
    run.layout.receipt,
    transition("auth_ready", 0, at(1), run.runId, {
      source: "browser",
      profile_fingerprint: "b".repeat(64),
      challenge_observed: false,
    }),
  );
  await transitionReceiptFile(
    run.layout.receipt,
    transition("target_bound", 1, at(2), run.runId, {
      source: "browser",
      target_id: targetId,
      target_url: "https://chatgpt.com/",
      browser_pid: 4242,
    }),
  );
  await transitionReceiptFile(
    run.layout.receipt,
    transition("model_tool_verified", 2, at(3), run.runId, {
      source: "browser",
      target_id: targetId,
      model_requested: "gpt-5.4-pro",
      model_observed: "gpt-5.4-pro",
      model_proven: true,
      tool_requested: "deep-research",
      tool_observed: "deep-research",
      tool_proven: true,
    }),
  );
  return { targetId };
}

async function advanceToStarted(run) {
  const { targetId } = await advanceToModelVerified(run);
  const conversationUrl = `https://chatgpt.com/c/${run.runId}`;
  const userTurnId = `user-${run.runId}`;
  await transitionReceiptFile(
    run.layout.receipt,
    transition("submitted", 3, at(4), run.runId, {
      source: "browser",
      target_id: targetId,
      conversation_url: conversationUrl,
      baseline_assistant_turn_id: `baseline-${run.runId}`,
      baseline_assistant_turn_position: 10,
      user_turn_id: userTurnId,
      user_turn_position: 11,
      request_fingerprint: run.requestFingerprint,
      deadline_at: at(100),
    }),
  );
  await transitionReceiptFile(
    run.layout.receipt,
    transition("started", 4, at(5), run.runId, {
      source: "browser",
      target_id: targetId,
      conversation_url: conversationUrl,
      user_turn_id: userTurnId,
      assistant_signal_id: `progress-${run.runId}`,
      assistant_signal_position: 12,
    }),
  );
  return { targetId, conversationUrl, userTurnId };
}

async function completeRun(run, content = "# Durable result\n") {
  const { targetId, conversationUrl, userTurnId } =
    await advanceToStarted(run);
  const result = await writeRunResult(run.layout, content);
  return transitionReceiptFile(
    run.layout.receipt,
    transition("completed", 5, at(6), run.runId, {
      source: "browser",
      target_id: targetId,
      conversation_url: conversationUrl,
      user_turn_id: userTurnId,
      final_assistant_turn_id: `final-${run.runId}`,
      final_assistant_turn_position: 13,
      result,
    }),
  );
}

function assertResumeError(error, code) {
  assert.ok(error instanceof OracleSubagentResumeError);
  assert.equal(error.code, code);
  assert.equal(error.message, "oracle-subagent resume: rejected");
  return true;
}

async function childResume(root, run, ownerId) {
  const childScript = path.join(path.dirname(root), "resume-child.mjs");
  const moduleUrl = new URL(
    "../assets/scripts/oracle-subagent-resume.mjs",
    import.meta.url,
  ).href;
  await writeFile(
    childScript,
    `
import { resumeOracleRun } from ${JSON.stringify(moduleUrl)};
const result = await resumeOracleRun(
  process.argv[2],
  {
    request_fingerprint: process.argv[3],
    candidate_run_id: process.argv[4],
    owner_id: process.argv[5],
    now_ms: 100,
  },
  ${JSON.stringify(QUEUE_CONFIG)},
);
process.stdout.write(JSON.stringify(result));
`,
    { mode: 0o600 },
  );
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(
      process.execPath,
      [
        childScript,
        root,
        run.requestFingerprint,
        run.runId,
        ownerId,
      ],
      {
        env: { PATH: process.env.PATH, LANG: "C", LC_ALL: "C" },
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.once("error", rejectPromise);
    child.once("exit", (code) => {
      if (code !== 0 || stderr !== "") {
        rejectPromise(new Error(`resume child failed ${code}: ${stderr}`));
        return;
      }
      resolvePromise(JSON.parse(stdout));
    });
  });
}

test("one owner receives execution capability while reconnects reattach without duplicate send", async (t) => {
  const root = await workspace(t);
  const run = await createRun(root);
  const initial = await resumeOracleRun(
    root,
    resumeRequest(run),
    QUEUE_CONFIG,
  );
  assert.equal(initial.disposition, "owner");
  assert.equal(initial.directive, "execute");
  assert.equal(initial.send_authorized, true);
  assert.equal(initial.queue.status, "leased");
  assert.ok(initial.lease.lease_id);

  const reconnect = await resumeOracleRun(
    root,
    resumeRequest(run, {
      candidateRunId: "run-unused-candidate",
      ownerId: "owner-reconnect-01",
      nowMs: 101,
    }),
    QUEUE_CONFIG,
  );
  assert.equal(reconnect.run_id, run.runId);
  assert.equal(reconnect.disposition, "reattached");
  assert.equal(reconnect.directive, "reattached");
  assert.equal(reconnect.send_authorized, false);
  assert.equal(reconnect.lease, null);
  assert.equal(reconnect.queue.status, "leased");
  assert.doesNotMatch(JSON.stringify(reconnect), /session-private|Private analysis/);
});

test("concurrent reconnect storm has exactly one send-authorized owner", async (t) => {
  const root = await workspace(t);
  const run = await createRun(root, {
    runId: "run-resume-race1",
    character: "b",
  });
  const outcomes = await Promise.all(
    Array.from({ length: 12 }, (_, index) =>
      resumeOracleRun(
        root,
        resumeRequest(run, {
          ownerId: `owner-race-${String(index).padStart(4, "0")}`,
        }),
        QUEUE_CONFIG,
      ),
    ),
  );
  assert.equal(
    outcomes.filter((outcome) => outcome.send_authorized).length,
    1,
  );
  assert.equal(
    outcomes.filter((outcome) => outcome.disposition === "owner").length,
    1,
  );
  assert.equal(new Set(outcomes.map((outcome) => outcome.run_id)).size, 1);
  assert.equal(
    new Set(
      outcomes
        .filter((outcome) => outcome.lease)
        .map((outcome) => outcome.lease.lease_id),
    ).size,
    1,
  );
});

test("client process disconnect leaves a durable stale-owner reattachment, never a second send", async (t) => {
  const root = await workspace(t);
  const run = await createRun(root, {
    runId: "run-resume-child1",
    character: "c",
  });
  const child = await childResume(root, run, "owner-child-0001");
  assert.equal(child.send_authorized, true);

  const resumed = await resumeOracleRun(
    root,
    resumeRequest(run, {
      candidateRunId: "run-child-retry1",
      ownerId: "owner-parent-0001",
      nowMs: 101,
    }),
    QUEUE_CONFIG,
  );
  assert.equal(resumed.run_id, run.runId);
  assert.equal(resumed.owner_status, "stale");
  assert.equal(resumed.directive, "restart_worker");
  assert.equal(resumed.send_authorized, false);
  assert.equal(resumed.lease, null);
});

test("disconnect after durable queue lease retries into the sole execution grant", async (t) => {
  const root = await workspace(t);
  const run = await createRun(root, {
    runId: "run-resume-qcrash",
    character: "d",
  });
  await assert.rejects(
    resumeOracleRun(
      root,
      resumeRequest(run, { ownerId: "owner-qcrash-001" }),
      QUEUE_CONFIG,
      {
        hooks: {
          after_queue_claim: async () => {
            throw new Error("synthetic disconnect");
          },
        },
      },
    ),
    (error) =>
      assertResumeError(error, "resume_after_queue_interrupted"),
  );

  const recovered = await resumeOracleRun(
    root,
    resumeRequest(run, {
      candidateRunId: "run-qcrash-retry",
      ownerId: "owner-qcrash-002",
      nowMs: 101,
    }),
    QUEUE_CONFIG,
  );
  assert.equal(recovered.run_id, run.runId);
  assert.equal(recovered.disposition, "owner");
  assert.equal(recovered.directive, "execute");
  assert.equal(recovered.send_authorized, true);
  assert.ok(recovered.lease);

  const reconnect = await resumeOracleRun(
    root,
    resumeRequest(run, {
      candidateRunId: "run-qcrash-later",
      ownerId: "owner-qcrash-003",
      nowMs: 102,
    }),
    QUEUE_CONFIG,
  );
  assert.equal(reconnect.disposition, "reattached");
  assert.equal(reconnect.send_authorized, false);
  assert.equal(reconnect.lease, null);
});

test("disconnect after durable identity grant fails closed against duplicate send", async (t) => {
  const root = await workspace(t);
  const run = await createRun(root, {
    runId: "run-resume-icrash",
    character: "e",
  });
  await assert.rejects(
    resumeOracleRun(
      root,
      resumeRequest(run, { ownerId: "owner-icrash-001" }),
      QUEUE_CONFIG,
      {
        hooks: {
          after_identity_claim: async () => {
            throw new Error("synthetic disconnect");
          },
        },
      },
    ),
    (error) =>
      assertResumeError(error, "resume_after_identity_interrupted"),
  );

  const recovered = await resumeOracleRun(
    root,
    resumeRequest(run, {
      candidateRunId: "run-icrash-retry",
      ownerId: "owner-icrash-002",
      nowMs: 101,
    }),
    QUEUE_CONFIG,
  );
  assert.equal(recovered.run_id, run.runId);
  assert.equal(recovered.disposition, "reattached");
  assert.equal(recovered.directive, "reattached");
  assert.equal(recovered.send_authorized, false);
  assert.equal(recovered.lease, null);
});

test("queue wait and bounded backpressure stay explicit across reconnects", async (t) => {
  const root = await workspace(t);
  const config = { ...QUEUE_CONFIG, max_depth: 1 };
  const firstRun = await createRun(root, {
    runId: "run-resume-full01",
    character: "a",
  });
  const secondRun = await createRun(root, {
    runId: "run-resume-full02",
    character: "b",
  });
  const thirdRun = await createRun(root, {
    runId: "run-resume-full03",
    character: "c",
  });
  const first = await resumeOracleRun(
    root,
    resumeRequest(firstRun, { ownerId: "owner-full-0001" }),
    config,
  );
  const second = await resumeOracleRun(
    root,
    resumeRequest(secondRun, {
      ownerId: "owner-full-0002",
      nowMs: 101,
    }),
    config,
  );
  const third = await resumeOracleRun(
    root,
    resumeRequest(thirdRun, {
      ownerId: "owner-full-0003",
      nowMs: 102,
    }),
    config,
  );
  assert.equal(first.directive, "execute");
  assert.equal(second.directive, "wait");
  assert.equal(second.queue.queue_position, 1);
  assert.equal(second.send_authorized, false);
  assert.equal(third.directive, "backpressure");
  assert.equal(third.queue.status, "missing");
  assert.equal(third.send_authorized, false);

  const secondRetry = await resumeOracleRun(
    root,
    resumeRequest(secondRun, {
      ownerId: "owner-full-retry",
      nowMs: 103,
    }),
    config,
  );
  assert.equal(secondRetry.directive, "wait");
  assert.equal(secondRetry.queue.queue_position, 1);

  await cancelOracleRun(
    root,
    {
      ...resumeRequest(firstRun, {
        ownerId: "owner-full-cancel",
        nowMs: 104,
      }),
      actor: "operator",
      reason_code: "operator_request",
      observed_at: at(1),
    },
    config,
  );
  const promoted = await resumeOracleRun(
    root,
    resumeRequest(secondRun, {
      ownerId: "owner-full-0002",
      nowMs: 105,
    }),
    config,
  );
  assert.equal(promoted.disposition, "owner");
  assert.equal(promoted.directive, "execute");
  assert.equal(promoted.send_authorized, true);
  assert.equal(promoted.queue.status, "leased");
});

test("model/send ambiguity reconciles while submitted and started runs only monitor", async (t) => {
  const root = await workspace(t);
  const run = await createRun(root, {
    runId: "run-resume-bound1",
    character: "d",
  });
  await resumeOracleRun(
    root,
    resumeRequest(run, { ownerId: "owner-bound-0001" }),
    QUEUE_CONFIG,
  );
  const { targetId } = await advanceToModelVerified(run);
  const boundary = await resumeOracleRun(
    root,
    resumeRequest(run, {
      ownerId: "owner-bound-0002",
      nowMs: 101,
    }),
    QUEUE_CONFIG,
  );
  assert.equal(boundary.receipt_state, "model_tool_verified");
  assert.equal(boundary.directive, "reconcile_submission");
  assert.equal(boundary.send_authorized, false);

  const conversationUrl = `https://chatgpt.com/c/${run.runId}`;
  const userTurnId = `user-${run.runId}`;
  await transitionReceiptFile(
    run.layout.receipt,
    transition("submitted", 3, at(4), run.runId, {
      source: "browser",
      target_id: targetId,
      conversation_url: conversationUrl,
      baseline_assistant_turn_id: `baseline-${run.runId}`,
      baseline_assistant_turn_position: 10,
      user_turn_id: userTurnId,
      user_turn_position: 11,
      request_fingerprint: run.requestFingerprint,
      deadline_at: at(100),
    }),
  );
  const submitted = await resumeOracleRun(
    root,
    resumeRequest(run, {
      ownerId: "owner-bound-0003",
      nowMs: 102,
    }),
    QUEUE_CONFIG,
  );
  assert.equal(submitted.directive, "monitor");
  assert.equal(submitted.send_authorized, false);

  await transitionReceiptFile(
    run.layout.receipt,
    transition("started", 4, at(5), run.runId, {
      source: "browser",
      target_id: targetId,
      conversation_url: conversationUrl,
      user_turn_id: userTurnId,
      assistant_signal_id: `progress-${run.runId}`,
      assistant_signal_position: 12,
    }),
  );
  const started = await resumeOracleRun(
    root,
    resumeRequest(run, {
      ownerId: "owner-bound-0004",
      nowMs: 103,
    }),
    QUEUE_CONFIG,
  );
  assert.equal(started.directive, "monitor");
  assert.equal(started.receipt_state, "started");
});

test("a first claim at the model boundary never receives execution authority", async (t) => {
  const root = await workspace(t);
  const run = await createRun(root, {
    runId: "run-resume-bound2",
    character: "f",
  });
  await advanceToModelVerified(run);

  const boundary = await resumeOracleRun(
    root,
    resumeRequest(run, { ownerId: "owner-bound2-001" }),
    QUEUE_CONFIG,
  );
  assert.equal(boundary.disposition, "reattached");
  assert.equal(boundary.receipt_state, "model_tool_verified");
  assert.equal(boundary.directive, "reconcile_submission");
  assert.equal(boundary.send_authorized, false);
  assert.equal(boundary.lease, null);
});

test("a receipt bound to another browser target fails before resume or cancellation", async (t) => {
  const root = await workspace(t);
  const run = await createRun(root, {
    runId: "run-resume-target",
    character: "c",
  });
  await resumeOracleRun(
    root,
    resumeRequest(run, { ownerId: "owner-target-001" }),
    QUEUE_CONFIG,
  );
  await transitionReceiptFile(
    run.layout.receipt,
    transition("auth_ready", 0, at(1), run.runId, {
      source: "browser",
      profile_fingerprint: "b".repeat(64),
      challenge_observed: false,
    }),
  );
  await transitionReceiptFile(
    run.layout.receipt,
    transition("target_bound", 1, at(2), run.runId, {
      source: "browser",
      target_id: "target-wrong-browser",
      target_url: "https://chatgpt.com/",
      browser_pid: 4242,
    }),
  );

  await assert.rejects(
    resumeOracleRun(
      root,
      resumeRequest(run, {
        ownerId: "owner-target-002",
        nowMs: 101,
      }),
      QUEUE_CONFIG,
    ),
    (error) =>
      assertResumeError(error, "resume_target_binding_invalid"),
  );
  await assert.rejects(
    cancelOracleRun(
      root,
      {
        ...resumeRequest(run, {
          ownerId: "owner-target-003",
          nowMs: 102,
        }),
        actor: "operator",
        reason_code: "operator_request",
        observed_at: at(3),
      },
      QUEUE_CONFIG,
    ),
    (error) =>
      assertResumeError(error, "resume_target_binding_invalid"),
  );
});

test("completed is returned only with a verified nonempty atomic result and frees its lease", async (t) => {
  const root = await workspace(t);
  const run = await createRun(root, {
    runId: "run-resume-done01",
    character: "e",
  });
  await resumeOracleRun(
    root,
    resumeRequest(run, { ownerId: "owner-done-0001" }),
    QUEUE_CONFIG,
  );
  const completedReceipt = await completeRun(run, "# Verified result\n");
  const completed = await resumeOracleRun(
    root,
    resumeRequest(run, {
      ownerId: "owner-done-0002",
      nowMs: 106,
    }),
    QUEUE_CONFIG,
  );
  assert.equal(completed.receipt_state, "completed");
  assert.equal(completed.terminal, true);
  assert.equal(completed.directive, "terminal");
  assert.equal(completed.send_authorized, false);
  assert.equal(completed.queue.status, "released");
  assert.equal(completed.result.sha256, completedReceipt.result.sha256);
  assert.ok(completed.result.bytes > 0);
  assert.equal(Object.hasOwn(completed.result, "path"), false);

  await writeFile(run.layout.result, "tampered", { mode: 0o600 });
  await assert.rejects(
    resumeOracleRun(
      root,
      resumeRequest(run, {
        ownerId: "owner-done-0003",
        nowMs: 107,
      }),
      QUEUE_CONFIG,
    ),
    (error) => assertResumeError(error, "resume_receipt_invalid"),
  );
});

test("terminal reconciliation reverifies result bytes before reporting completion", async (t) => {
  const root = await workspace(t);
  const run = await createRun(root, {
    runId: "run-resume-reread",
    character: "d",
  });
  await resumeOracleRun(
    root,
    resumeRequest(run, { ownerId: "owner-reread-001" }),
    QUEUE_CONFIG,
  );
  await completeRun(run);

  await assert.rejects(
    resumeOracleRun(
      root,
      resumeRequest(run, {
        ownerId: "owner-reread-002",
        nowMs: 106,
      }),
      QUEUE_CONFIG,
      {
        hooks: {
          after_terminal_queue_reconcile: async () => {
            await writeFile(run.layout.result, "tampered", {
              mode: 0o600,
            });
          },
        },
      },
    ),
    (error) => assertResumeError(error, "resume_receipt_invalid"),
  );
});

test("explicit cancellation is receipt-first, queue-terminal, and idempotent", async (t) => {
  const root = await workspace(t);
  const run = await createRun(root, {
    runId: "run-resume-cancel",
    character: "f",
  });
  await resumeOracleRun(
    root,
    resumeRequest(run, { ownerId: "owner-cancel-001" }),
    QUEUE_CONFIG,
  );
  const cancellation = {
    ...resumeRequest(run, {
      ownerId: "owner-cancel-002",
      nowMs: 101,
    }),
    actor: "user",
    reason_code: "user_request",
    observed_at: at(1),
  };
  const cancelled = await cancelOracleRun(
    root,
    cancellation,
    QUEUE_CONFIG,
  );
  assert.equal(cancelled.command, "cancel");
  assert.equal(cancelled.receipt_state, "cancelled");
  assert.equal(cancelled.queue.status, "cancelled");
  assert.equal(cancelled.send_authorized, false);
  const revision = cancelled.receipt_revision;

  const repeated = await cancelOracleRun(
    root,
    { ...cancellation, owner_id: "owner-cancel-003", now_ms: 102 },
    QUEUE_CONFIG,
  );
  assert.equal(repeated.receipt_state, "cancelled");
  assert.equal(repeated.receipt_revision, revision);
  assert.equal(repeated.queue.status, "cancelled");
});

test("explicit cancellation removes queued work without ever authorizing a send", async (t) => {
  const root = await workspace(t);
  const activeRun = await createRun(root, {
    runId: "run-resume-active",
    character: "a",
  });
  const queuedRun = await createRun(root, {
    runId: "run-resume-queued",
    character: "b",
  });
  const active = await resumeOracleRun(
    root,
    resumeRequest(activeRun, { ownerId: "owner-active-001" }),
    QUEUE_CONFIG,
  );
  const queued = await resumeOracleRun(
    root,
    resumeRequest(queuedRun, {
      ownerId: "owner-queued-001",
      nowMs: 101,
    }),
    QUEUE_CONFIG,
  );
  assert.equal(active.send_authorized, true);
  assert.equal(queued.directive, "wait");
  assert.equal(queued.send_authorized, false);

  const cancelled = await cancelOracleRun(
    root,
    {
      ...resumeRequest(queuedRun, {
        ownerId: "owner-queued-002",
        nowMs: 102,
      }),
      actor: "operator",
      reason_code: "operator_request",
      observed_at: at(1),
    },
    QUEUE_CONFIG,
  );
  assert.equal(cancelled.receipt_state, "cancelled");
  assert.equal(cancelled.queue.status, "cancelled");
  assert.equal(cancelled.send_authorized, false);
  assert.equal(cancelled.lease, null);

  const resumed = await resumeOracleRun(
    root,
    resumeRequest(queuedRun, {
      candidateRunId: "run-queued-retry",
      ownerId: "owner-queued-003",
      nowMs: 103,
    }),
    QUEUE_CONFIG,
  );
  assert.equal(resumed.receipt_state, "cancelled");
  assert.equal(resumed.queue.status, "cancelled");
  assert.equal(resumed.send_authorized, false);
});

test("disconnect after durable receipt cancellation resumes queue cleanup without reopening work", async (t) => {
  const root = await workspace(t);
  const run = await createRun(root, {
    runId: "run-resume-crash1",
    character: "a",
  });
  await resumeOracleRun(
    root,
    resumeRequest(run, { ownerId: "owner-crash-0001" }),
    QUEUE_CONFIG,
  );
  await assert.rejects(
    cancelOracleRun(
      root,
      {
        ...resumeRequest(run, {
          ownerId: "owner-crash-0002",
          nowMs: 101,
        }),
        actor: "operator",
        reason_code: "operator_request",
        observed_at: at(1),
      },
      QUEUE_CONFIG,
      {
        hooks: {
          after_receipt_cancel: async () => {
            throw new Error("synthetic disconnect");
          },
        },
      },
    ),
    (error) => assertResumeError(error, "resume_cancel_interrupted"),
  );
  assert.equal((await readReceiptFile(run.layout.receipt)).state, "cancelled");

  const recovered = await resumeOracleRun(
    root,
    resumeRequest(run, {
      ownerId: "owner-crash-0003",
      nowMs: 102,
    }),
    QUEUE_CONFIG,
  );
  assert.equal(recovered.receipt_state, "cancelled");
  assert.equal(recovered.queue.status, "cancelled");
  assert.equal(recovered.send_authorized, false);
});

test("completion wins a late cancellation and remains verified terminal truth", async (t) => {
  const root = await workspace(t);
  const run = await createRun(root, {
    runId: "run-resume-racewin",
    character: "b",
  });
  await resumeOracleRun(
    root,
    resumeRequest(run, { ownerId: "owner-win-0001" }),
    QUEUE_CONFIG,
  );
  await completeRun(run);
  const lateCancel = await cancelOracleRun(
    root,
    {
      ...resumeRequest(run, {
        ownerId: "owner-win-0002",
        nowMs: 106,
      }),
      actor: "user",
      reason_code: "user_request",
      observed_at: at(7),
    },
    QUEUE_CONFIG,
  );
  assert.equal(lateCancel.receipt_state, "completed");
  assert.equal(lateCancel.queue.status, "released");
  assert.ok(lateCancel.result.bytes > 0);
});

test("secret-shaped requests fail generically and the runtime exposes no logging or ambient-input surface", async (t) => {
  const root = await workspace(t);
  const run = await createRun(root, {
    runId: "run-resume-safe01",
    character: "c",
  });
  for (const request of [
    { ...resumeRequest(run), candidate_run_id: "run-token-material" },
    { ...resumeRequest(run), owner_id: "owner-cookie-material" },
  ]) {
    await assert.rejects(
      resumeOracleRun(root, request, QUEUE_CONFIG),
      (error) => {
        assert.ok(error instanceof OracleSubagentResumeError);
        assert.equal(error.message, "oracle-subagent resume: rejected");
        assert.equal(error.message.includes("token-material"), false);
        assert.equal(error.message.includes("cookie-material"), false);
        return true;
      },
    );
  }
  const source = await readFile(
    path.join(
      path.dirname(THIS_FILE),
      "../assets/scripts/oracle-subagent-resume.mjs",
    ),
    "utf8",
  );
  assert.doesNotMatch(source, /console\.(?:log|error)|process\.env|process\.argv/);
  assert.doesNotMatch(source, /prompt_bytes|cookie_value|authorization_value/);
});
