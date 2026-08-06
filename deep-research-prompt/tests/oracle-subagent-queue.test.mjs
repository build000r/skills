import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import {
  chmod,
  lstat,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  realpath,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  OracleSubagentQueueError,
  cancelQueueRun,
  claimQueueRun,
  getQueueRunStatus,
  queueLayout,
  releaseQueueLease,
  renewQueueLease,
} from "../assets/scripts/oracle-subagent-queue.mjs";

const THIS_FILE = fileURLToPath(import.meta.url);
const CONFIG_ONE = Object.freeze({
  target_ids: ["target-alpha"],
  max_active: 1,
  max_depth: 4,
  lease_duration_ms: 1_000,
});
const CONFIG_TWO = Object.freeze({
  target_ids: ["target-alpha", "target-beta"],
  max_active: 2,
  max_depth: 8,
  lease_duration_ms: 1_000,
});

function fingerprint(character) {
  if (/^[0-9a-f]{64}$/.test(character)) return character;
  return character.repeat(64);
}

function claim(runId, character, workerId, nowMs) {
  return {
    run_id: runId,
    request_fingerprint: fingerprint(character),
    worker_id: workerId,
    now_ms: nowMs,
  };
}

async function makeRoot(t) {
  const root = await realpath(
    await mkdtemp(path.join(os.tmpdir(), "oracle-queue-test-")),
  );
  t.after(() => rm(root, { recursive: true, force: true }));
  return root;
}

async function replaceFileWithSameBytes(filePath) {
  const bytes = await readFile(filePath);
  const replacedPath = `${filePath}.replaced`;
  await rename(filePath, replacedPath);
  await writeFile(filePath, bytes, { mode: 0o600 });
  await rm(replacedPath);
}

function assertGenericQueueError(error, code) {
  assert.ok(error instanceof OracleSubagentQueueError);
  assert.equal(error.code, code);
  assert.equal(error.message, "oracle-subagent queue: rejected");
  return true;
}

async function childClaim(root, runId, character, workerId, nowMs, config) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(
      process.execPath,
      [
        THIS_FILE,
        "--queue-child",
        root,
        runId,
        character,
        workerId,
        String(nowMs),
        JSON.stringify(config),
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
      if (code !== 0) {
        rejectPromise(new Error(`queue child failed ${code}: ${stderr}`));
        return;
      }
      resolvePromise(JSON.parse(stdout));
    });
  });
}

if (process.argv[2] === "--queue-child") {
  const [, , , root, runId, character, workerId, nowMs, rawConfig] =
    process.argv;
  try {
    const result = await claimQueueRun(
      root,
      claim(runId, character, workerId, Number(nowMs)),
      JSON.parse(rawConfig),
    );
    process.stdout.write(JSON.stringify({ ok: true, result }));
  } catch (error) {
    process.stdout.write(
      JSON.stringify({
        ok: false,
        code: error?.code ?? "unknown",
        message: error?.message ?? "unknown",
      }),
    );
  }
  process.exit(0);
}

test("FIFO claims expose truthful positions, duplicate reattach, and read-only status", async (t) => {
  const root = await makeRoot(t);
  const first = await claimQueueRun(
    root,
    claim("run-queue-0001", "a", "worker-alpha", 100),
    CONFIG_ONE,
  );
  assert.equal(first.outcome, "accepted");
  assert.equal(first.status, "leased");
  assert.equal(first.target_id, "target-alpha");
  assert.equal(first.fencing_token, 1);

  const second = await claimQueueRun(
    root,
    claim("run-queue-0002", "b", "worker-bravo", 101),
    CONFIG_ONE,
  );
  const third = await claimQueueRun(
    root,
    claim("run-queue-0003", "c", "worker-charlie", 102),
    CONFIG_ONE,
  );
  assert.equal(second.status, "queued");
  assert.equal(second.queue_position, 1);
  assert.equal(third.queue_position, 2);

  const layout = queueLayout(root);
  const sizesBefore = [
    (await lstat(layout.ledger_path)).size,
    (await lstat(layout.head_path)).size,
    (await lstat(layout.anchor_path)).size,
    (await readdir(layout.witness_directory)).length,
  ];
  const status = await getQueueRunStatus(root, "run-queue-0002", {
    now_ms: 103,
  });
  const sizesAfter = [
    (await lstat(layout.ledger_path)).size,
    (await lstat(layout.head_path)).size,
    (await lstat(layout.anchor_path)).size,
    (await readdir(layout.witness_directory)).length,
  ];
  assert.equal(status.outcome, "status");
  assert.equal(status.queue_position, 1);
  assert.deepEqual(sizesAfter, sizesBefore);

  const duplicate = await claimQueueRun(
    root,
    claim("run-queue-0002", "b", "worker-bravo", 104),
    CONFIG_ONE,
  );
  assert.equal(duplicate.outcome, "reattached");
  assert.equal(duplicate.run_id, "run-queue-0002");
  assert.equal(duplicate.queue_position, 1);

  const fingerprintDuplicate = await claimQueueRun(
    root,
    claim("run-queue-other", "b", "worker-bravo", 105),
    CONFIG_ONE,
  );
  assert.equal(fingerprintDuplicate.outcome, "reattached");
  assert.equal(fingerprintDuplicate.run_id, "run-queue-0002");
});

test("run identity and generation configuration are exact and immutable", async (t) => {
  const root = await makeRoot(t);
  const accepted = await claimQueueRun(
    root,
    claim("run-identity-001", "a", "worker-identity1", 100),
    CONFIG_TWO,
  );
  assert.equal(accepted.status, "leased");

  await assert.rejects(
    claimQueueRun(
      root,
      claim("run-identity-001", "b", "worker-identity1", 101),
      CONFIG_TWO,
    ),
    (error) =>
      assertGenericQueueError(error, "queue_run_fingerprint_mismatch"),
  );
  await assert.rejects(
    claimQueueRun(
      root,
      claim("run-identity-002", "b", "worker-identity2", 102),
      { ...CONFIG_TWO, max_depth: CONFIG_TWO.max_depth + 1 },
    ),
    (error) => assertGenericQueueError(error, "queue_config_mismatch"),
  );
  await assert.rejects(
    claimQueueRun(
      root,
      claim("run-identity-001", "a", "worker-identity2", 103),
      CONFIG_TWO,
    ),
    (error) => assertGenericQueueError(error, "queue_worker_mismatch"),
  );

  const reordered = await claimQueueRun(
    root,
    claim("run-identity-002", "b", "worker-identity2", 104),
    {
      ...CONFIG_TWO,
      target_ids: [...CONFIG_TWO.target_ids].reverse(),
    },
  );
  assert.equal(reordered.status, "leased");
});

test("mutations reject a regressed caller clock without changing queue truth", async (t) => {
  const root = await makeRoot(t);
  const active = await claimQueueRun(
    root,
    claim("run-clock-0001", "a", "worker-clock-001", 100),
    CONFIG_ONE,
  );
  await assert.rejects(
    claimQueueRun(
      root,
      claim("run-clock-0002", "b", "worker-clock-002", 99),
      CONFIG_ONE,
    ),
    (error) => assertGenericQueueError(error, "queue_clock_regressed"),
  );
  await assert.rejects(
    renewQueueLease(root, {
      run_id: active.run_id,
      worker_id: "worker-clock-001",
      lease_id: active.lease_id,
      fencing_token: active.fencing_token,
      now_ms: 99,
    }),
    (error) => assertGenericQueueError(error, "queue_clock_regressed"),
  );
  const unchanged = await getQueueRunStatus(root, active.run_id, {
    now_ms: 100,
  });
  assert.equal(unchanged.revision, active.revision);
  assert.equal(unchanged.lease_expires_at_ms, null);
  const reattached = await claimQueueRun(
    root,
    claim("run-clock-0001", "a", "worker-clock-001", 100),
    CONFIG_ONE,
  );
  assert.equal(
    reattached.lease_expires_at_ms,
    active.lease_expires_at_ms,
  );
  assert.equal(
    (
      await getQueueRunStatus(root, "run-clock-0002", {
        now_ms: 100,
      })
    ).status,
    "missing",
  );
});

test("lease deadline overflow fails before publishing an invalid snapshot", async (t) => {
  const overflowRoot = await makeRoot(t);
  await assert.rejects(
    claimQueueRun(
      overflowRoot,
      claim(
        "run-clock-overflow",
        "a",
        "worker-clock-max",
        Number.MAX_SAFE_INTEGER,
      ),
      CONFIG_ONE,
    ),
    (error) => assertGenericQueueError(error, "queue_clock_exhausted"),
  );
  const absent = await getQueueRunStatus(
    overflowRoot,
    "run-clock-overflow",
    { now_ms: Number.MAX_SAFE_INTEGER },
  );
  assert.equal(absent.status, "missing");
  assert.equal(absent.revision, 0);

  const renewRoot = await makeRoot(t);
  const lastSafeStart =
    Number.MAX_SAFE_INTEGER - CONFIG_ONE.lease_duration_ms;
  const active = await claimQueueRun(
    renewRoot,
    claim(
      "run-clock-renewmax",
      "b",
      "worker-clock-renew",
      lastSafeStart,
    ),
    CONFIG_ONE,
  );
  await assert.rejects(
    renewQueueLease(renewRoot, {
      run_id: active.run_id,
      worker_id: "worker-clock-renew",
      lease_id: active.lease_id,
      fencing_token: active.fencing_token,
      now_ms: lastSafeStart + 1,
    }),
    (error) => assertGenericQueueError(error, "queue_clock_exhausted"),
  );
  const unchanged = await getQueueRunStatus(renewRoot, active.run_id, {
    now_ms: lastSafeStart + 1,
  });
  assert.equal(unchanged.revision, active.revision);
  assert.equal(unchanged.status, "leased");
  assert.equal(unchanged.lease_id, null);
  assert.equal(unchanged.fencing_token, null);
});

test("multiple exact targets obey max_active and never cross-lease", async (t) => {
  const root = await makeRoot(t);
  const results = [];
  for (let index = 0; index < 4; index += 1) {
    results.push(
      await claimQueueRun(
        root,
        claim(
          `run-multi-000${index}`,
          String.fromCharCode(97 + index),
          `worker-multi-00${index}`,
          100 + index,
        ),
        CONFIG_TWO,
      ),
    );
  }
  const leased = results.filter((result) => result.status === "leased");
  const queued = results.filter((result) => result.status === "queued");
  assert.equal(leased.length, 2);
  assert.deepEqual(
    leased.map((result) => result.target_id).sort(),
    ["target-alpha", "target-beta"],
  );
  assert.equal(new Set(leased.map((result) => result.lease_id)).size, 2);
  assert.deepEqual(
    queued.map((result) => result.queue_position),
    [1, 2],
  );
});

test("bounded backpressure is explicit and never creates an ambiguous record", async (t) => {
  const root = await makeRoot(t);
  const config = {
    target_ids: ["target-alpha"],
    max_active: 1,
    max_depth: 1,
    lease_duration_ms: 1_000,
  };
  await claimQueueRun(
    root,
    claim("run-full-0001", "a", "worker-full-001", 1),
    config,
  );
  await claimQueueRun(
    root,
    claim("run-full-0002", "b", "worker-full-002", 2),
    config,
  );
  const rejected = await claimQueueRun(
    root,
    claim("run-full-0003", "c", "worker-full-003", 3),
    config,
  );
  assert.deepEqual(
    {
      outcome: rejected.outcome,
      status: rejected.status,
      run_id: rejected.run_id,
      queue_depth: rejected.queue_depth,
      active_count: rejected.active_count,
    },
    {
      outcome: "queue_full",
      status: "missing",
      run_id: null,
      queue_depth: 1,
      active_count: 1,
    },
  );
  assert.equal(
    (await getQueueRunStatus(root, "run-full-0003", { now_ms: 3 }))
      .status,
    "missing",
  );
});

test("renew, release, cancel, expiry, and fencing are idempotent and generation-bound", async (t) => {
  const root = await makeRoot(t);
  const first = await claimQueueRun(
    root,
    claim("run-lease-001", "a", "worker-lease-01", 100),
    CONFIG_ONE,
  );
  await claimQueueRun(
    root,
    claim("run-lease-002", "b", "worker-lease-02", 101),
    CONFIG_ONE,
  );
  const renewed = await renewQueueLease(root, {
    run_id: first.run_id,
    worker_id: "worker-lease-01",
    lease_id: first.lease_id,
    fencing_token: first.fencing_token,
    now_ms: 500,
  });
  assert.equal(renewed.outcome, "renewed");
  assert.equal(renewed.lease_expires_at_ms, 1_500);

  const released = await releaseQueueLease(root, {
    run_id: first.run_id,
    worker_id: "worker-lease-01",
    lease_id: first.lease_id,
    fencing_token: first.fencing_token,
    now_ms: 600,
    outcome: "released",
  });
  assert.equal(released.status, "released");
  const releasedAgain = await releaseQueueLease(root, {
    run_id: first.run_id,
    worker_id: "worker-lease-01",
    lease_id: first.lease_id,
    fencing_token: first.fencing_token,
    now_ms: 601,
    outcome: "released",
  });
  assert.equal(releasedAgain.revision, released.revision);

  const secondStatus = await getQueueRunStatus(root, "run-lease-002", {
    now_ms: 602,
  });
  assert.equal(secondStatus.status, "leased");
  assert.equal(secondStatus.lease_id, null);
  const second = await claimQueueRun(
    root,
    claim("run-lease-002", "b", "worker-lease-02", 602),
    CONFIG_ONE,
  );
  assert.equal(second.status, "leased");
  assert.equal(second.fencing_token, 2);
  const cancelled = await cancelQueueRun(root, {
    run_id: second.run_id,
    worker_id: "worker-lease-02",
    lease_id: second.lease_id,
    fencing_token: second.fencing_token,
    now_ms: 700,
  });
  assert.equal(cancelled.status, "cancelled");
  assert.equal(
    (
      await cancelQueueRun(root, {
        run_id: second.run_id,
        worker_id: "worker-lease-02",
        now_ms: 701,
      })
    ).revision,
    cancelled.revision,
  );

  const expiring = await claimQueueRun(
    root,
    claim("run-expire-001", "c", "worker-expire1", 800),
    CONFIG_ONE,
  );
  assert.equal(expiring.status, "leased");
  await claimQueueRun(
    root,
    claim("run-expire-002", "d", "worker-expire2", 1_801),
    CONFIG_ONE,
  );
  const currentStatus = await getQueueRunStatus(root, expiring.run_id, {
    now_ms: 1_802,
  });
  assert.equal(currentStatus.status, "leased");
  assert.equal(currentStatus.fencing_token, null);
  const current = await claimQueueRun(
    root,
    claim("run-expire-001", "c", "worker-expire1", 1_802),
    CONFIG_ONE,
  );
  assert.equal(current.status, "leased");
  assert.ok(current.fencing_token > expiring.fencing_token);
  await assert.rejects(
    releaseQueueLease(root, {
      run_id: expiring.run_id,
      worker_id: "worker-expire1",
      lease_id: expiring.lease_id,
      fencing_token: expiring.fencing_token,
      now_ms: 1_803,
      outcome: "released",
    }),
    (error) => assertGenericQueueError(error, "queue_lease_fenced"),
  );
});

test("expired status is read-only and stale renewals persist a newer fenced lease", async (t) => {
  const statusRoot = await makeRoot(t);
  const expiring = await claimQueueRun(
    statusRoot,
    claim("run-status-expired", "a", "worker-status-01", 100),
    CONFIG_ONE,
  );
  const statusLayout = queueLayout(statusRoot);
  const beforeStatus = [
    (await lstat(statusLayout.ledger_path)).size,
    (await lstat(statusLayout.head_path)).size,
    (await lstat(statusLayout.anchor_path)).size,
    (await readdir(statusLayout.witness_directory)).length,
  ];
  const projected = await getQueueRunStatus(
    statusRoot,
    expiring.run_id,
    { now_ms: expiring.lease_expires_at_ms },
  );
  const afterStatus = [
    (await lstat(statusLayout.ledger_path)).size,
    (await lstat(statusLayout.head_path)).size,
    (await lstat(statusLayout.anchor_path)).size,
    (await readdir(statusLayout.witness_directory)).length,
  ];
  assert.equal(projected.status, "queued");
  assert.equal(projected.queue_position, 1);
  assert.equal(projected.lease_id, null);
  assert.equal(projected.revision, expiring.revision);
  assert.deepEqual(afterStatus, beforeStatus);

  const fenced = await renewQueueLease(statusRoot, {
    run_id: expiring.run_id,
    worker_id: "worker-status-01",
    lease_id: expiring.lease_id,
    fencing_token: expiring.fencing_token,
    now_ms: expiring.lease_expires_at_ms,
  });
  assert.equal(fenced.outcome, "fenced");
  assert.equal(fenced.status, "leased");
  assert.equal(fenced.fencing_token, null);
  assert.equal(fenced.lease_id, null);
  assert.equal(fenced.target_id, null);
  assert.equal(fenced.lease_expires_at_ms, null);

  for (const operation of [
    () =>
      renewQueueLease(statusRoot, {
        run_id: expiring.run_id,
        worker_id: "worker-status-01",
        lease_id: expiring.lease_id,
        fencing_token: expiring.fencing_token,
        now_ms: expiring.lease_expires_at_ms + 1,
      }),
    () =>
      releaseQueueLease(statusRoot, {
        run_id: expiring.run_id,
        worker_id: "worker-status-01",
        lease_id: expiring.lease_id,
        fencing_token: expiring.fencing_token,
        now_ms: expiring.lease_expires_at_ms + 1,
        outcome: "released",
      }),
    () =>
      cancelQueueRun(statusRoot, {
        run_id: expiring.run_id,
        worker_id: "worker-status-01",
        lease_id: expiring.lease_id,
        fencing_token: expiring.fencing_token,
        now_ms: expiring.lease_expires_at_ms + 1,
      }),
  ]) {
    await assert.rejects(
      operation(),
      (error) => assertGenericQueueError(error, "queue_lease_fenced"),
    );
  }
  const unchanged = await getQueueRunStatus(
    statusRoot,
    expiring.run_id,
    { now_ms: expiring.lease_expires_at_ms + 1 },
  );
  assert.equal(unchanged.fencing_token, null);
  assert.equal(unchanged.lease_id, null);
  assert.equal(unchanged.revision, fenced.revision);
  const reattached = await claimQueueRun(
    statusRoot,
    claim(
      expiring.run_id,
      "a",
      "worker-status-01",
      expiring.lease_expires_at_ms + 1,
    ),
    CONFIG_ONE,
  );
  assert.equal(reattached.outcome, "reattached");
  assert.ok(reattached.fencing_token > expiring.fencing_token);
  assert.notEqual(reattached.lease_id, expiring.lease_id);
});

test("expired abandoned work moves behind existing FIFO waiters and cannot ghost-starve them", async (t) => {
  const root = await makeRoot(t);
  const abandoned = await claimQueueRun(
    root,
    claim("run-starve-oldest", "a", "worker-starve-old", 100),
    CONFIG_ONE,
  );
  const waiting = await claimQueueRun(
    root,
    claim("run-starve-waiter", "b", "worker-starve-new", 101),
    CONFIG_ONE,
  );
  assert.equal(abandoned.status, "leased");
  assert.equal(waiting.status, "queued");
  assert.equal(waiting.queue_position, 1);

  const promoted = await claimQueueRun(
    root,
    claim("run-starve-waiter", "b", "worker-starve-new", 1_100),
    CONFIG_ONE,
  );
  assert.equal(promoted.outcome, "reattached");
  assert.equal(promoted.status, "leased");
  assert.equal(promoted.fencing_token, 2);
  const oldAtTail = await getQueueRunStatus(
    root,
    "run-starve-oldest",
    { now_ms: 1_100 },
  );
  assert.equal(oldAtTail.status, "queued");
  assert.equal(oldAtTail.queue_position, 1);

  const oldPromotedNext = await claimQueueRun(
    root,
    claim("run-starve-oldest", "a", "worker-starve-old", 2_100),
    CONFIG_ONE,
  );
  assert.equal(oldPromotedNext.status, "leased");
  assert.equal(oldPromotedNext.fencing_token, 3);
  const waiterAtTail = await getQueueRunStatus(
    root,
    "run-starve-waiter",
    { now_ms: 2_100 },
  );
  assert.equal(waiterAtTail.status, "queued");
  assert.equal(waiterAtTail.queue_position, 1);
});

test("queued and leased cancellation require exact ownership and leave terminal tombstones", async (t) => {
  const root = await makeRoot(t);
  const active = await claimQueueRun(
    root,
    claim("run-cancel-active", "a", "worker-cancel-01", 100),
    CONFIG_ONE,
  );
  const queued = await claimQueueRun(
    root,
    claim("run-cancel-queued", "b", "worker-cancel-02", 101),
    CONFIG_ONE,
  );
  assert.equal(queued.status, "queued");

  await assert.rejects(
    cancelQueueRun(root, {
      run_id: queued.run_id,
      worker_id: "worker-cancel-wrong",
      now_ms: 102,
    }),
    (error) => assertGenericQueueError(error, "queue_cancel_denied"),
  );
  const cancelledQueued = await cancelQueueRun(root, {
    run_id: queued.run_id,
    worker_id: "worker-cancel-02",
    now_ms: 103,
  });
  assert.equal(cancelledQueued.status, "cancelled");
  assert.equal(cancelledQueued.lease_id, null);

  await assert.rejects(
    cancelQueueRun(root, {
      run_id: active.run_id,
      worker_id: "worker-cancel-01",
      now_ms: 104,
    }),
    (error) => assertGenericQueueError(error, "queue_lease_fenced"),
  );
  const cancelledActive = await cancelQueueRun(root, {
    run_id: active.run_id,
    worker_id: "worker-cancel-01",
    lease_id: active.lease_id,
    fencing_token: active.fencing_token,
    now_ms: 105,
  });
  assert.equal(cancelledActive.status, "cancelled");
  assert.equal(cancelledActive.lease_id, active.lease_id);

  const tombstone = await claimQueueRun(
    root,
    claim("run-cancel-active", "a", "worker-cancel-01", 106),
    CONFIG_ONE,
  );
  assert.equal(tombstone.outcome, "reattached");
  assert.equal(tombstone.status, "cancelled");
  assert.equal(tombstone.revision, cancelledActive.revision);
});

test("concurrent in-process claims serialize with unique targets, leases, and positions", async (t) => {
  const root = await makeRoot(t);
  const config = {
    target_ids: ["target-alpha", "target-beta", "target-gamma"],
    max_active: 3,
    max_depth: 24,
    lease_duration_ms: 2_000,
  };
  const results = await Promise.all(
    Array.from({ length: 20 }, (_, index) =>
      claimQueueRun(
        root,
        claim(
          `run-race-${String(index).padStart(4, "0")}`,
          index.toString(16).padStart(64, "0"),
          `worker-race-${String(index).padStart(4, "0")}`,
          100,
        ),
        config,
      ),
    ),
  );
  assert.equal(results.filter((result) => result.status === "leased").length, 3);
  assert.equal(
    new Set(
      results
        .filter((result) => result.status === "leased")
        .map((result) => result.target_id),
    ).size,
    3,
  );
  assert.deepEqual(
    results
      .filter((result) => result.status === "queued")
      .map((result) => result.queue_position)
      .sort((left, right) => left - right),
    Array.from({ length: 17 }, (_, index) => index + 1),
  );
});

test("fresh-root cross-process duplicates converge and distinct work all enters", async (t) => {
  const duplicateRoot = await makeRoot(t);
  const duplicateResults = await Promise.all(
    Array.from({ length: 12 }, () =>
      childClaim(
        duplicateRoot,
        "run-process-same",
        "a",
        "worker-proc-shared",
        100,
        CONFIG_ONE,
      ),
    ),
  );
  assert.equal(duplicateResults.filter((item) => item.ok).length, 12);
  assert.equal(
    duplicateResults.filter(
      (item) => item.result.outcome === "accepted",
    ).length,
    1,
  );
  assert.equal(
    duplicateResults.filter(
      (item) => item.result.outcome === "reattached",
    ).length,
    11,
  );
  assert.equal(
    new Set(duplicateResults.map((item) => item.result.run_id)).size,
    1,
  );

  const distinctRoot = await makeRoot(t);
  const distinctConfig = {
    target_ids: ["target-alpha", "target-beta"],
    max_active: 2,
    max_depth: 16,
    lease_duration_ms: 2_000,
  };
  const distinctResults = await Promise.all(
    Array.from({ length: 8 }, (_, index) =>
      childClaim(
        distinctRoot,
        `run-proc-${String(index).padStart(4, "0")}`,
        index.toString(16),
        `worker-proc-${String(index).padStart(3, "0")}`,
        100,
        distinctConfig,
      ),
    ),
  );
  assert.equal(distinctResults.filter((item) => item.ok).length, 8);
  assert.equal(
    distinctResults.filter(
      (item) => item.result.outcome === "accepted",
    ).length,
    8,
  );
  assert.equal(
    distinctResults.filter(
      (item) => item.result.status === "leased",
    ).length,
    2,
  );
  const finalStatuses = await Promise.all(
    Array.from({ length: 8 }, (_, index) =>
      getQueueRunStatus(
        distinctRoot,
        `run-proc-${String(index).padStart(4, "0")}`,
        { now_ms: 101 },
      ),
    ),
  );
  assert.equal(
    new Set(
      finalStatuses
        .filter((item) => item.status === "leased")
        .map((item) => item.target_id),
    ).size,
    2,
  );
  assert.deepEqual(
    finalStatuses
      .filter((item) => item.status === "queued")
      .map((item) => item.queue_position)
      .sort((left, right) => left - right),
    [1, 2, 3, 4, 5, 6],
  );
});

for (const boundary of [
  "after_ledger_fsync",
  "after_witness_fsync",
  "after_head_fsync",
  "after_anchor_fsync",
]) {
  test(`a crash after ${boundary} repairs or observes one durable queue transaction`, async (t) => {
    const root = await makeRoot(t);
    await claimQueueRun(
      root,
      claim("run-crash-base", "a", "worker-crash-01", 1),
      CONFIG_ONE,
    );
    let triggered = false;
    await assert.rejects(
      claimQueueRun(
        root,
        claim("run-crash-next", "b", "worker-crash-02", 2),
        CONFIG_ONE,
        {
          hooks: {
            [boundary]: async () => {
              triggered = true;
              throw new Error("synthetic stop");
            },
          },
        },
      ),
      /synthetic stop/,
    );
    assert.equal(triggered, true);
    const layout = queueLayout(root);
    const beforeStatus = [
      (await lstat(layout.ledger_path)).size,
      (await lstat(layout.head_path)).size,
      (await lstat(layout.anchor_path)).size,
      (await readdir(layout.witness_directory)).length,
    ];
    const readOnly = await getQueueRunStatus(root, "run-crash-next", {
      now_ms: 2,
    });
    const afterStatus = [
      (await lstat(layout.ledger_path)).size,
      (await lstat(layout.head_path)).size,
      (await lstat(layout.anchor_path)).size,
      (await readdir(layout.witness_directory)).length,
    ];
    assert.deepEqual(afterStatus, beforeStatus);
    assert.equal(
      readOnly.status,
      boundary === "after_anchor_fsync" ? "queued" : "missing",
    );
    const recovered = await claimQueueRun(
      root,
      claim("run-crash-next", "b", "worker-crash-02", 3),
      CONFIG_ONE,
    );
    assert.equal(recovered.outcome, "reattached");
    assert.equal(recovered.run_id, "run-crash-next");
    assert.equal(recovered.status, "queued");
  });
}

test("a release interrupted after ledger fsync recovers without double release or cross-capture", async (t) => {
  const root = await makeRoot(t);
  const active = await claimQueueRun(
    root,
    claim("run-release-crash1", "a", "worker-release1", 100),
    CONFIG_ONE,
  );
  await claimQueueRun(
    root,
    claim("run-release-crash2", "b", "worker-release2", 101),
    CONFIG_ONE,
  );
  await assert.rejects(
    releaseQueueLease(
      root,
      {
        run_id: active.run_id,
        worker_id: "worker-release1",
        lease_id: active.lease_id,
        fencing_token: active.fencing_token,
        now_ms: 200,
        outcome: "released",
      },
      {
        hooks: {
          after_ledger_fsync: async () => {
            throw new Error("synthetic release stop");
          },
        },
      },
    ),
    /synthetic release stop/,
  );
  const recovered = await releaseQueueLease(root, {
    run_id: active.run_id,
    worker_id: "worker-release1",
    lease_id: active.lease_id,
    fencing_token: active.fencing_token,
    now_ms: 201,
    outcome: "released",
  });
  assert.equal(recovered.outcome, "released");
  assert.equal(recovered.status, "released");
  const promoted = await getQueueRunStatus(root, "run-release-crash2", {
    now_ms: 202,
  });
  assert.equal(promoted.status, "leased");
  assert.equal(promoted.target_id, "target-alpha");
  assert.notEqual(promoted.lease_id, active.lease_id);
});

test("a lock-only virgin root bootstraps once while partial bootstrap fails closed", async (t) => {
  const lockOnlyRoot = await makeRoot(t);
  const lockOnlyLayout = queueLayout(lockOnlyRoot);
  await writeFile(lockOnlyLayout.lock_path, "", { mode: 0o600 });
  const accepted = await claimQueueRun(
    lockOnlyRoot,
    claim("run-lock-only-001", "a", "worker-lock-only", 1),
    CONFIG_ONE,
  );
  assert.equal(accepted.outcome, "accepted");
  assert.equal(accepted.status, "leased");

  const partialRoot = await makeRoot(t);
  const partialLayout = queueLayout(partialRoot);
  await writeFile(partialLayout.ledger_path, "{}\n", { mode: 0o600 });
  await assert.rejects(
    claimQueueRun(
      partialRoot,
      claim("run-partial-0001", "b", "worker-partial01", 1),
      CONFIG_ONE,
    ),
    (error) =>
      assertGenericQueueError(error, "queue_bootstrap_incomplete"),
  );
});

test("same-content generation, ledger, head, anchor, witness, and witness-directory replacement fail closed", async (t) => {
  for (const [index, component] of [
    "generation",
    "ledger",
    "head",
    "anchor",
    "witness",
  ].entries()) {
    const root = await makeRoot(t);
    await claimQueueRun(
      root,
      claim(
        `run-replace-${component}`,
        ["a", "b", "c", "d", "e"][index],
        `worker-replace-${component}`,
        1,
      ),
      CONFIG_ONE,
    );
    const layout = queueLayout(root);
    let targetPath;
    if (component === "generation") targetPath = layout.generation_path;
    if (component === "ledger") targetPath = layout.ledger_path;
    if (component === "head") targetPath = layout.head_path;
    if (component === "anchor") targetPath = layout.anchor_path;
    if (component === "witness") {
      const names = await readdir(layout.witness_directory);
      targetPath = path.join(layout.witness_directory, names.at(-1));
    }
    await replaceFileWithSameBytes(targetPath);
    await assert.rejects(
      getQueueRunStatus(root, `run-replace-${component}`, { now_ms: 2 }),
      (error) => {
        assert.ok(error instanceof OracleSubagentQueueError);
        assert.ok(
          ["queue_store_replaced", "queue_witness_invalid"].includes(
            error.code,
          ),
          `${component}: ${error.code}`,
        );
        return true;
      },
    );
  }

  const directoryRoot = await makeRoot(t);
  await claimQueueRun(
    directoryRoot,
    claim("run-replace-directory", "f", "worker-replace-dir", 1),
    CONFIG_ONE,
  );
  const directoryLayout = queueLayout(directoryRoot);
  const originalDirectory = `${directoryLayout.witness_directory}.replaced`;
  const witnessCopies = await Promise.all(
    (await readdir(directoryLayout.witness_directory)).map(async (name) => ({
      name,
      bytes: await readFile(
        path.join(directoryLayout.witness_directory, name),
      ),
    })),
  );
  await rename(directoryLayout.witness_directory, originalDirectory);
  await mkdir(directoryLayout.witness_directory, { mode: 0o700 });
  for (const witness of witnessCopies) {
    await writeFile(
      path.join(directoryLayout.witness_directory, witness.name),
      witness.bytes,
      { mode: 0o600 },
    );
  }
  await assert.rejects(
    getQueueRunStatus(directoryRoot, "run-replace-directory", {
      now_ms: 2,
    }),
    (error) => assertGenericQueueError(error, "queue_store_replaced"),
  );
});

test("coherent prefix rollback and multi-record terminal lag fail closed", async (t) => {
  const prefixRoot = await makeRoot(t);
  await claimQueueRun(
    prefixRoot,
    claim("run-prefix-0001", "a", "worker-prefix-01", 1),
    CONFIG_ONE,
  );
  await claimQueueRun(
    prefixRoot,
    claim("run-prefix-0002", "b", "worker-prefix-02", 2),
    CONFIG_ONE,
  );
  const prefixLayout = queueLayout(prefixRoot);
  for (const filePath of [
    prefixLayout.ledger_path,
    prefixLayout.head_path,
  ]) {
    const lines = (await readFile(filePath, "utf8"))
      .trimEnd()
      .split("\n");
    await writeFile(filePath, `${lines.slice(0, -1).join("\n")}\n`, {
      mode: 0o600,
    });
  }
  const prefixWitnesses = (
    await readdir(prefixLayout.witness_directory)
  ).sort();
  await rm(
    path.join(
      prefixLayout.witness_directory,
      prefixWitnesses.at(-1),
    ),
  );
  await assert.rejects(
    getQueueRunStatus(prefixRoot, "run-prefix-0001", { now_ms: 3 }),
    (error) => assertGenericQueueError(error, "queue_anchor_invalid"),
  );

  const lagRoot = await makeRoot(t);
  await claimQueueRun(
    lagRoot,
    claim("run-lag-0001", "c", "worker-lag-0001", 1),
    CONFIG_ONE,
  );
  await claimQueueRun(
    lagRoot,
    claim("run-lag-0002", "d", "worker-lag-0002", 2),
    CONFIG_ONE,
  );
  const lagLayout = queueLayout(lagRoot);
  for (const filePath of [lagLayout.head_path, lagLayout.anchor_path]) {
    const lines = (await readFile(filePath, "utf8"))
      .trimEnd()
      .split("\n");
    await writeFile(filePath, `${lines.slice(0, -2).join("\n")}\n`, {
      mode: 0o600,
    });
  }
  await assert.rejects(
    getQueueRunStatus(lagRoot, "run-lag-0001", { now_ms: 3 }),
    (error) => assertGenericQueueError(error, "queue_commit_incomplete"),
  );

  const reverseLagRoot = await makeRoot(t);
  await claimQueueRun(
    reverseLagRoot,
    claim("run-reverse-lag1", "e", "worker-reverse-1", 1),
    CONFIG_ONE,
  );
  await claimQueueRun(
    reverseLagRoot,
    claim("run-reverse-lag2", "f", "worker-reverse-2", 2),
    CONFIG_ONE,
  );
  const reverseLagLayout = queueLayout(reverseLagRoot);
  const ledgerLines = (
    await readFile(reverseLagLayout.ledger_path, "utf8")
  )
    .trimEnd()
    .split("\n");
  await writeFile(
    reverseLagLayout.ledger_path,
    `${ledgerLines.slice(0, -1).join("\n")}\n`,
    { mode: 0o600 },
  );
  await assert.rejects(
    getQueueRunStatus(reverseLagRoot, "run-reverse-lag1", {
      now_ms: 3,
    }),
    (error) => assertGenericQueueError(error, "queue_commit_incomplete"),
  );
});

test("store corruption, lock replacement, and witness rollback fail closed", async (t) => {
  const ledgerRoot = await makeRoot(t);
  await claimQueueRun(
    ledgerRoot,
    claim("run-damage-001", "a", "worker-damage1", 1),
    CONFIG_ONE,
  );
  const ledgerLayout = queueLayout(ledgerRoot);
  await writeFile(ledgerLayout.ledger_path, "not-json\n", { mode: 0o600 });
  await assert.rejects(
    getQueueRunStatus(ledgerRoot, "run-damage-001", { now_ms: 2 }),
    (error) => assertGenericQueueError(error, "queue_ledger_invalid"),
  );

  const lockRoot = await makeRoot(t);
  await claimQueueRun(
    lockRoot,
    claim("run-damage-002", "b", "worker-damage2", 1),
    CONFIG_ONE,
  );
  const lockLayout = queueLayout(lockRoot);
  await rename(lockLayout.lock_path, `${lockLayout.lock_path}.old`);
  await writeFile(lockLayout.lock_path, "", { mode: 0o600 });
  await chmod(lockLayout.lock_path, 0o600);
  await assert.rejects(
    getQueueRunStatus(lockRoot, "run-damage-002", { now_ms: 2 }),
    (error) => assertGenericQueueError(error, "queue_store_replaced"),
  );

  const witnessRoot = await makeRoot(t);
  await claimQueueRun(
    witnessRoot,
    claim("run-damage-003", "c", "worker-damage3", 1),
    CONFIG_ONE,
  );
  const witnessLayout = queueLayout(witnessRoot);
  const witnessNames = await readdir(witnessLayout.witness_directory);
  await rm(
    path.join(witnessLayout.witness_directory, witnessNames.at(-1)),
  );
  await assert.rejects(
    getQueueRunStatus(witnessRoot, "run-damage-003", { now_ms: 2 }),
    (error) => {
      assert.ok(
        ["queue_witness_set_invalid", "queue_witness_invalid"].includes(
          error.code,
        ),
      );
      return true;
    },
  );
});

test("secret-shaped identifiers and config fail generically without a logging or ambient surface", async (t) => {
  const root = await makeRoot(t);
  for (const [rawClaim, config] of [
    [
      claim("token-marker-001", "a", "worker-secret1", 1),
      CONFIG_ONE,
    ],
    [
      claim("run-secret-001", "a", "worker-secret2", 1),
      { ...CONFIG_ONE, target_ids: ["sk-proj-AAAAAAAAAAAAAAAAAAAA"] },
    ],
  ]) {
    await assert.rejects(
      claimQueueRun(root, rawClaim, config),
      (error) => {
        assert.ok(error instanceof OracleSubagentQueueError);
        assert.equal(error.message, "oracle-subagent queue: rejected");
        assert.equal(error.message.includes("token-marker"), false);
        assert.equal(error.message.includes("sk-proj"), false);
        return true;
      },
    );
  }
  const source = await readFile(
    path.join(
      path.dirname(THIS_FILE),
      "../assets/scripts/oracle-subagent-queue.mjs",
    ),
    "utf8",
  );
  assert.doesNotMatch(source, /console\.(?:log|error)|process\.env|process\.argv/);
  assert.doesNotMatch(source, /prompt_bytes|attachment_bytes|cookie_value/);
});
