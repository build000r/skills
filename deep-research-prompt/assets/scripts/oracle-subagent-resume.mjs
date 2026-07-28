import { createHash } from "node:crypto";

import {
  runArtifactLayout,
} from "./oracle-subagent-artifacts.mjs";
import {
  claimIdempotentRequest,
} from "./oracle-subagent-idempotency.mjs";
import {
  cancelQueueRun,
  claimQueueRun,
  OracleSubagentQueueError,
  releaseQueueLease,
} from "./oracle-subagent-queue.mjs";
import {
  readReceiptFile,
  TERMINAL_STATES,
  transitionReceiptFile,
} from "./oracle-subagent-state.mjs";

export const RESUME_RESULT_SCHEMA = "oracle-subagent.resume-result.v1";

const RUN_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$/;
const OWNER_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const CODE_PATTERN = /^[a-z][a-z0-9_]{1,63}$/;
const SAFE_CAUSE_PATTERN = /^[a-z][a-z0-9_]{1,95}$/;
const SENSITIVE_PATTERN =
  /(?:authorization|bearer|cookie|password|prompt|secret|session[_-]?token|token|https?:\/\/)/i;
const CREDENTIAL_PATTERN =
  /(?:sk-(?:proj-)?[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{12,}|xapp-[A-Za-z0-9-]{12,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})/i;
const TERMINAL_SET = new Set(TERMINAL_STATES);
const PRE_SUBMISSION_STATES = new Set([
  "created",
  "auth_ready",
  "target_bound",
  "model_tool_verified",
]);
const EXECUTION_GRANT_STATES = new Set([
  "created",
  "auth_ready",
  "target_bound",
]);
const FAILURE_TERMINALS = new Set([
  "failed",
  "timed_out",
  "cancelled",
]);

export class OracleSubagentResumeError extends Error {
  constructor(code, causeCode = null) {
    super("oracle-subagent resume: rejected");
    this.name = "OracleSubagentResumeError";
    this.code = code;
    this.cause_code = causeCode;
  }
}

function reject(code, causeCode = null) {
  throw new OracleSubagentResumeError(code, causeCode);
}

function isPlainObject(value) {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.getPrototypeOf(value) === Object.prototype
  );
}

function exactObject(value, required, optional, code) {
  if (!isPlainObject(value)) reject(code);
  const allowed = new Set([...required, ...optional]);
  if (
    required.some((key) => !Object.hasOwn(value, key)) ||
    Object.keys(value).some((key) => !allowed.has(key))
  ) {
    reject(code);
  }
  return value;
}

function safeIdentifier(value, pattern, code) {
  if (
    typeof value !== "string" ||
    !pattern.test(value) ||
    SENSITIVE_PATTERN.test(value) ||
    CREDENTIAL_PATTERN.test(value)
  ) {
    reject(code);
  }
  return value;
}

function safeInteger(value, code) {
  if (
    !Number.isSafeInteger(value) ||
    value < 0 ||
    value > Number.MAX_SAFE_INTEGER
  ) {
    reject(code);
  }
  return value;
}

function canonicalTimestamp(value, code) {
  if (typeof value !== "string") reject(code);
  const milliseconds = Date.parse(value);
  if (
    !Number.isFinite(milliseconds) ||
    new Date(milliseconds).toISOString() !== value
  ) {
    reject(code);
  }
  return value;
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function deepFreeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value)) deepFreeze(child);
  }
  return value;
}

function safeCauseCode(error) {
  const value = error?.code;
  return typeof value === "string" &&
    SAFE_CAUSE_PATTERN.test(value) &&
    !SENSITIVE_PATTERN.test(value)
    ? value
    : null;
}

async function mappedCall(code, callback) {
  try {
    return await callback();
  } catch (error) {
    if (error instanceof OracleSubagentResumeError) throw error;
    reject(code, safeCauseCode(error));
  }
}

function normalizeBaseRequest(raw, { cancel = false } = {}) {
  const required = [
    "request_fingerprint",
    "candidate_run_id",
    "owner_id",
    "now_ms",
  ];
  if (cancel) {
    required.push("actor", "reason_code", "observed_at");
  }
  const value = exactObject(raw, required, [], "resume_request_invalid");
  const normalized = {
    request_fingerprint: safeIdentifier(
      value.request_fingerprint,
      SHA256_PATTERN,
      "resume_request_invalid",
    ),
    candidate_run_id: safeIdentifier(
      value.candidate_run_id,
      RUN_ID_PATTERN,
      "resume_request_invalid",
    ),
    owner_id: safeIdentifier(
      value.owner_id,
      OWNER_ID_PATTERN,
      "resume_request_invalid",
    ),
    now_ms: safeInteger(value.now_ms, "resume_request_invalid"),
  };
  if (!cancel) return normalized;
  if (!["user", "operator"].includes(value.actor)) {
    reject("resume_request_invalid");
  }
  return {
    ...normalized,
    actor: value.actor,
    reason_code: safeIdentifier(
      value.reason_code,
      CODE_PATTERN,
      "resume_request_invalid",
    ),
    observed_at: canonicalTimestamp(
      value.observed_at,
      "resume_request_invalid",
    ),
  };
}

function normalizeOptions(raw = {}) {
  const value = exactObject(
    raw,
    [],
    ["idempotency_options", "queue_options", "hooks"],
    "resume_options_invalid",
  );
  const idempotencyOptions = value.idempotency_options ?? {};
  const queueOptions = value.queue_options ?? {};
  const hooks = value.hooks ?? {};
  if (
    !isPlainObject(idempotencyOptions) ||
    !isPlainObject(queueOptions) ||
    !isPlainObject(hooks)
  ) {
    reject("resume_options_invalid");
  }
  const allowedHooks = new Set([
    "after_queue_claim",
    "after_identity_claim",
    "after_terminal_queue_reconcile",
    "after_receipt_cancel",
  ]);
  for (const [key, hook] of Object.entries(hooks)) {
    if (!allowedHooks.has(key) || typeof hook !== "function") {
      reject("resume_options_invalid");
    }
  }
  return { idempotencyOptions, queueOptions, hooks };
}

async function invokeHook(options, name, code) {
  try {
    await options.hooks[name]?.();
  } catch {
    reject(code);
  }
}

export function resumeWorkerId(requestFingerprint) {
  const normalizedFingerprint = safeIdentifier(
    requestFingerprint,
    SHA256_PATTERN,
    "resume_fingerprint_invalid",
  );
  return `resume:${sha256(normalizedFingerprint).slice(0, 40)}`;
}

async function claimIdentity(
  artifactRoot,
  request,
  options,
  candidateRunId = request.candidate_run_id,
) {
  return mappedCall("resume_idempotency_failed", () =>
    claimIdempotentRequest(
      artifactRoot,
      {
        request_fingerprint: request.request_fingerprint,
        candidate_run_id: candidateRunId,
        owner_id: request.owner_id,
      },
      options.idempotencyOptions,
    ),
  );
}

async function readBoundReceipt(claim) {
  const receipt = await mappedCall("resume_receipt_invalid", () =>
    readReceiptFile(claim.receipt_path),
  );
  if (
    receipt.run_id !== claim.run_id ||
    receipt.request_fingerprint !== claim.request_fingerprint
  ) {
    reject("resume_receipt_binding_invalid");
  }
  return receipt;
}

function pendingIdentity(artifactRoot, runId, requestFingerprint) {
  const layout = runArtifactLayout(artifactRoot, runId);
  return {
    run_id: runId,
    request_fingerprint: requestFingerprint,
    receipt_path: layout.receipt,
    disposition: "pending",
    owner_status: "unknown",
    send_authorized: false,
  };
}

async function claimQueue(
  artifactRoot,
  runId,
  requestFingerprint,
  request,
  queueConfig,
  options,
) {
  return mappedCall("resume_queue_failed", () =>
    claimQueueRun(
      artifactRoot,
      {
        run_id: runId,
        request_fingerprint: requestFingerprint,
        worker_id: resumeWorkerId(requestFingerprint),
        now_ms: request.now_ms,
      },
      queueConfig,
      options.queueOptions,
    ),
  );
}

function queueSummary(queue) {
  return {
    outcome: queue.outcome,
    status: queue.status,
    queue_position: queue.queue_position,
    target_id: queue.target_id,
    queue_depth: queue.queue_depth,
    active_count: queue.active_count,
    revision: queue.revision,
  };
}

function resultSummary(receipt) {
  if (!receipt.result) return null;
  return {
    bytes: receipt.result.bytes,
    sha256: receipt.result.sha256,
    atomic_write_id: receipt.result.atomic_write_id,
  };
}

function requireTargetBinding(receipt, queue) {
  if (
    queue.status === "leased" &&
    receipt.target !== null &&
    queue.target_id !== receipt.target.id
  ) {
    reject("resume_target_binding_invalid");
  }
}

function directiveFor(claim, receipt, queue, sendAuthorized) {
  if (TERMINAL_SET.has(receipt.state)) return "terminal";
  if (queue.outcome === "queue_full" || queue.status === "missing") {
    return "backpressure";
  }
  if (queue.status === "queued") return "wait";
  if (queue.status !== "leased") return "repair_required";
  if (sendAuthorized) return "execute";
  if (receipt.state === "model_tool_verified") {
    return "reconcile_submission";
  }
  if (["submitted", "started"].includes(receipt.state)) return "monitor";
  if (
    claim.owner_status === "stale" &&
    PRE_SUBMISSION_STATES.has(receipt.state)
  ) {
    return "restart_worker";
  }
  return "reattached";
}

function buildResult(command, claim, receipt, queue) {
  const sendAuthorized =
    command === "resume" &&
    claim.send_authorized === true &&
    queue.status === "leased" &&
    EXECUTION_GRANT_STATES.has(receipt.state);
  const lease = sendAuthorized
    ? {
        target_id: queue.target_id,
        lease_id: queue.lease_id,
        fencing_token: queue.fencing_token,
        lease_expires_at_ms: queue.lease_expires_at_ms,
      }
    : null;
  return deepFreeze({
    schema: RESUME_RESULT_SCHEMA,
    command,
    disposition: claim.disposition,
    owner_status: claim.owner_status,
    run_id: claim.run_id,
    request_fingerprint: claim.request_fingerprint,
    receipt_state: receipt.state,
    receipt_revision: receipt.revision,
    receipt_hash: receipt.receipt_hash,
    terminal: TERMINAL_SET.has(receipt.state),
    send_authorized: sendAuthorized,
    directive: directiveFor(claim, receipt, queue, sendAuthorized),
    queue: queueSummary(queue),
    lease,
    result: resultSummary(receipt),
  });
}

async function reconcileTerminalQueue(
  artifactRoot,
  claim,
  request,
  receipt,
  queueConfig,
  options,
  initialQueue,
) {
  let queue = initialQueue;
  const workerId = resumeWorkerId(claim.request_fingerprint);
  for (let attempt = 0; attempt < 2; attempt += 1) {
    if (
      queue.status === "missing" ||
      queue.status === "released" ||
      queue.status === "cancelled"
    ) {
      return queue;
    }
    let reconciled;
    if (
      queue.status === "leased" &&
      !FAILURE_TERMINALS.has(receipt.state)
    ) {
      reconciled = await mappedCall("resume_queue_reconcile_failed", () =>
        releaseQueueLease(
          artifactRoot,
          {
            run_id: claim.run_id,
            worker_id: workerId,
            lease_id: queue.lease_id,
            fencing_token: queue.fencing_token,
            now_ms: request.now_ms,
            outcome: "released",
          },
          options.queueOptions,
        ),
      );
    } else {
      const cancellation = {
        run_id: claim.run_id,
        worker_id: workerId,
        now_ms: request.now_ms,
        ...(queue.status === "leased"
          ? {
              lease_id: queue.lease_id,
              fencing_token: queue.fencing_token,
            }
          : {}),
      };
      reconciled = await mappedCall("resume_queue_reconcile_failed", () =>
        cancelQueueRun(
          artifactRoot,
          cancellation,
          options.queueOptions,
        ),
      );
    }
    if (reconciled.outcome !== "fenced") return reconciled;
    queue = await claimQueue(
      artifactRoot,
      claim.run_id,
      claim.request_fingerprint,
      request,
      queueConfig,
      options,
    );
  }
  reject("resume_queue_reconcile_failed", "queue_lease_fenced");
}

export async function resumeOracleRun(
  artifactRoot,
  rawRequest,
  queueConfig,
  rawOptions = {},
) {
  const request = normalizeBaseRequest(rawRequest);
  const options = normalizeOptions(rawOptions);
  let queue = await claimQueue(
    artifactRoot,
    request.candidate_run_id,
    request.request_fingerprint,
    request,
    queueConfig,
    options,
  );
  await invokeHook(
    options,
    "after_queue_claim",
    "resume_after_queue_interrupted",
  );
  const canonicalRunId = queue.run_id ?? request.candidate_run_id;
  let claim = pendingIdentity(
    artifactRoot,
    canonicalRunId,
    request.request_fingerprint,
  );
  let receipt = await readBoundReceipt(claim);
  if (
    queue.status === "leased" &&
    EXECUTION_GRANT_STATES.has(receipt.state)
  ) {
    claim = await claimIdentity(
      artifactRoot,
      request,
      options,
      canonicalRunId,
    );
    await invokeHook(
      options,
      "after_identity_claim",
      "resume_after_identity_interrupted",
    );
    if (claim.run_id !== canonicalRunId) {
      reject("resume_queue_identity_mismatch");
    }
    receipt = await readBoundReceipt(claim);
  } else if (
    queue.status === "leased" ||
    TERMINAL_SET.has(receipt.state)
  ) {
    claim = { ...claim, disposition: "reattached" };
  }
  requireTargetBinding(receipt, queue);
  if (TERMINAL_SET.has(receipt.state)) {
    queue = await reconcileTerminalQueue(
      artifactRoot,
      claim,
      request,
      receipt,
      queueConfig,
      options,
      queue,
    );
    await invokeHook(
      options,
      "after_terminal_queue_reconcile",
      "resume_after_terminal_reconcile_interrupted",
    );
    receipt = await readBoundReceipt(claim);
  }
  return buildResult("resume", claim, receipt, queue);
}

function cancellationEvidence(receipt, request) {
  return {
    run_id: receipt.run_id,
    source: request.actor,
    actor: request.actor,
    reason_code: request.reason_code,
    last_state: receipt.state,
    ...(receipt.target ? { target_id: receipt.target.id } : {}),
  };
}

async function transitionCancellation(claim, receipt, request, options) {
  if (TERMINAL_SET.has(receipt.state)) return receipt;
  const eventId = `cancel-${sha256(
    [
      receipt.run_id,
      receipt.revision,
      request.actor,
      request.reason_code,
      request.observed_at,
    ].join("\n"),
  )}`;
  let cancelled;
  try {
    cancelled = await transitionReceiptFile(claim.receipt_path, {
      to: "cancelled",
      expectedRevision: receipt.revision,
      eventId,
      observedAt: request.observed_at,
      evidence: cancellationEvidence(receipt, request),
    });
  } catch (error) {
    if (error instanceof OracleSubagentResumeError) throw error;
    const latest = await readBoundReceipt(claim);
    if (TERMINAL_SET.has(latest.state)) return latest;
    reject("resume_cancel_transition_failed", safeCauseCode(error));
  }
  await invokeHook(
    options,
    "after_receipt_cancel",
    "resume_cancel_interrupted",
  );
  return cancelled;
}

export async function cancelOracleRun(
  artifactRoot,
  rawRequest,
  queueConfig,
  rawOptions = {},
) {
  const request = normalizeBaseRequest(rawRequest, { cancel: true });
  const options = normalizeOptions(rawOptions);
  let queue = await claimQueue(
    artifactRoot,
    request.candidate_run_id,
    request.request_fingerprint,
    request,
    queueConfig,
    options,
  );
  const canonicalRunId = queue.run_id ?? request.candidate_run_id;
  const claim = await claimIdentity(
    artifactRoot,
    request,
    options,
    canonicalRunId,
  );
  if (claim.run_id !== canonicalRunId) {
    reject("resume_queue_identity_mismatch");
  }
  const before = await readBoundReceipt(claim);
  requireTargetBinding(before, queue);
  const receipt = await transitionCancellation(
    claim,
    before,
    request,
    options,
  );
  queue = await reconcileTerminalQueue(
    artifactRoot,
    claim,
    request,
    receipt,
    queueConfig,
    options,
    queue,
  );
  const persisted = await readBoundReceipt(claim);
  return buildResult("cancel", claim, persisted, queue);
}
