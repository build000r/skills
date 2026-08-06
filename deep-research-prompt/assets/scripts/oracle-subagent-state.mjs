import { spawn } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { constants as fsConstants } from "node:fs";
import {
  link,
  lstat,
  open,
  realpath,
  rename,
  unlink,
} from "node:fs/promises";
import { basename, dirname, isAbsolute, resolve } from "node:path";

export const RECEIPT_SCHEMA = "oracle-subagent.receipt.v1";

export const STATES = Object.freeze([
  "created",
  "auth_ready",
  "target_bound",
  "model_tool_verified",
  "submitted",
  "started",
  "completed",
  "failed",
  "timed_out",
  "cancelled",
  "delivery_failed",
]);

export const TERMINAL_STATES = Object.freeze([
  "completed",
  "failed",
  "timed_out",
  "cancelled",
  "delivery_failed",
]);

const LEGAL_TRANSITIONS = Object.freeze({
  created: new Set(["auth_ready", "failed", "cancelled"]),
  auth_ready: new Set(["target_bound", "failed", "cancelled"]),
  target_bound: new Set(["model_tool_verified", "failed", "cancelled"]),
  model_tool_verified: new Set(["submitted", "failed", "cancelled"]),
  submitted: new Set(["started", "failed", "timed_out", "cancelled"]),
  started: new Set([
    "completed",
    "failed",
    "timed_out",
    "cancelled",
    "delivery_failed",
  ]),
  completed: new Set(),
  failed: new Set(),
  timed_out: new Set(),
  cancelled: new Set(),
  delivery_failed: new Set(),
});

const RUN_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$/;
const SLUG_PATTERN = /^[a-z0-9][a-z0-9-]{0,79}$/;
const IDENTIFIER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/;
const CODE_PATTERN = /^[a-z][a-z0-9_]{1,63}$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const DECIMAL_PATTERN = /^(?:0|[1-9][0-9]{0,39})$/;
const SENSITIVE_PATTERN =
  /(?:authorization|bearer|cookie|password|prompt|secret|session[_-]?token|token|https?:\/\/)/i;
const CREDENTIAL_PATTERN =
  /(?:sk-(?:proj-)?[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{12,}|xapp-[A-Za-z0-9-]{12,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})/i;
const MAX_BOUNDARY_DELAY_MS = 10_000;
const TERMINAL_SET = new Set(TERMINAL_STATES);
const EVIDENCE_SOURCES = new Set([
  "browser",
  "controller",
  "delivery",
  "operator",
  "user",
]);

function fail(message) {
  throw new Error(`oracle-subagent state: ${message}`);
}

function isPlainObject(value) {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.getPrototypeOf(value) === Object.prototype
  );
}

function requirePlainObject(value, label) {
  if (!isPlainObject(value)) fail(`${label} must be a plain object`);
  return value;
}

function requireExactKeys(value, required, optional = []) {
  const object = requirePlainObject(value, "evidence");
  const allowed = new Set([...required, ...optional]);
  const keys = Object.keys(object);
  for (const key of required) {
    if (!Object.hasOwn(object, key)) fail(`evidence is missing ${key}`);
  }
  for (const key of keys) {
    if (!allowed.has(key)) fail("evidence contains a forbidden field");
  }
  return object;
}

function requireString(value, label, pattern = IDENTIFIER_PATTERN) {
  if (typeof value !== "string" || !pattern.test(value)) {
    fail(`${label} is invalid`);
  }
  return value;
}

function requireSafeIdentifier(value, label, pattern = IDENTIFIER_PATTERN) {
  const identifier = requireString(value, label, pattern);
  if (
    SENSITIVE_PATTERN.test(identifier) ||
    CREDENTIAL_PATTERN.test(identifier)
  ) {
    fail(`${label} contains sensitive text`);
  }
  return identifier;
}

function rejectSensitiveText(value, label) {
  if (SENSITIVE_PATTERN.test(value) || CREDENTIAL_PATTERN.test(value)) {
    fail(`${label} contains sensitive text`);
  }
  return value;
}

function parseJsonNonEcho(bytes, label) {
  try {
    return JSON.parse(bytes.toString("utf8"));
  } catch {
    fail(`${label} is invalid JSON`);
  }
}

function requireBoolean(value, label) {
  if (typeof value !== "boolean") fail(`${label} must be boolean`);
  return value;
}

function requireInteger(value, label, minimum = 0) {
  if (!Number.isSafeInteger(value) || value < minimum) {
    fail(`${label} must be an integer >= ${minimum}`);
  }
  return value;
}

function requireTimestamp(value, label) {
  if (typeof value !== "string") fail(`${label} must be an RFC3339 timestamp`);
  const milliseconds = Date.parse(value);
  if (!Number.isFinite(milliseconds)) {
    fail(`${label} must be an RFC3339 timestamp`);
  }
  return new Date(milliseconds).toISOString();
}

function requireSha256(value, label) {
  return requireString(value, label, SHA256_PATTERN);
}

function requireAbsolutePath(value, label) {
  if (
    typeof value !== "string" ||
    !isAbsolute(value) ||
    value.includes("\0") ||
    value.includes("\n") ||
    resolve(value) !== value
  ) {
    fail(`${label} must be a normalized absolute path`);
  }
  return value;
}

function requireSafePersistedPath(value, label) {
  return rejectSensitiveText(requireAbsolutePath(value, label), label);
}

function requireChatGptUrl(value, label, { conversation = false } = {}) {
  if (typeof value !== "string") fail(`${label} must be a URL`);
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    fail(`${label} must be a URL`);
  }
  if (
    parsed.protocol !== "https:" ||
    parsed.hostname !== "chatgpt.com" ||
    parsed.port ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash ||
    (conversation && !parsed.pathname.startsWith("/c/"))
  ) {
    fail(`${label} must be an exact chatgpt.com URL`);
  }
  return parsed.toString();
}

function stableValue(value) {
  if (Array.isArray(value)) return value.map(stableValue);
  if (isPlainObject(value)) {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, stableValue(value[key])]),
    );
  }
  return value;
}

function canonicalJson(value) {
  return JSON.stringify(stableValue(value));
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function eventHash(event) {
  const copy = structuredClone(event);
  delete copy.event_hash;
  return sha256(canonicalJson(copy));
}

function receiptHash(receipt) {
  const copy = structuredClone(receipt);
  delete copy.receipt_hash;
  return sha256(canonicalJson(copy));
}

function finalizeReceipt(receipt) {
  const next = structuredClone(receipt);
  next.receipt_hash = receiptHash(next);
  return next;
}

function requireRunBinding(receipt, evidence) {
  requireSafeIdentifier(evidence.run_id, "evidence run_id", RUN_ID_PATTERN);
  requireSafeIdentifier(evidence.source, "evidence source");
  if (evidence.run_id !== receipt.run_id) {
    fail("evidence run_id does not match the receipt");
  }
  if (!EVIDENCE_SOURCES.has(evidence.source)) {
    fail("evidence source is not allowed");
  }
}

function requireTargetBinding(receipt, evidence) {
  requireSafeIdentifier(evidence.target_id, "evidence target_id");
  if (!receipt.target || evidence.target_id !== receipt.target.id) {
    fail("evidence target_id does not match the bound target");
  }
}

function requireConversationBinding(receipt, evidence) {
  requireTargetBinding(receipt, evidence);
  requireChatGptUrl(evidence.conversation_url, "evidence conversation_url", {
    conversation: true,
  });
  requireSafeIdentifier(evidence.user_turn_id, "evidence user_turn_id");
  if (
    !receipt.submission ||
    evidence.conversation_url !== receipt.submission.conversation_url ||
    evidence.user_turn_id !== receipt.submission.user_turn_id
  ) {
    fail("evidence does not match the submitted conversation turn");
  }
}

function validateResultShape(result) {
  const value = requirePlainObject(result, "result evidence");
  const required = [
    "path",
    "bytes",
    "sha256",
    "run_id",
    "atomic_write_id",
    "proof_path",
  ];
  if (
    Object.keys(value).length !== required.length ||
    required.some((key) => !Object.hasOwn(value, key))
  ) {
    fail("result evidence has an invalid shape");
  }
  requireSafePersistedPath(value.path, "result path");
  requireInteger(value.bytes, "result bytes", 1);
  requireSha256(value.sha256, "result sha256");
  requireSafeIdentifier(value.run_id, "result run_id", RUN_ID_PATTERN);
  requireSafeIdentifier(
    value.atomic_write_id,
    "atomic_write_id",
    RUN_ID_PATTERN,
  );
  requireSafePersistedPath(value.proof_path, "result proof path");
  if (value.proof_path !== `${value.path}.oracle-write-proof.json`) {
    fail("result proof path does not match the result");
  }
  return structuredClone(value);
}

function validatePersistedDerivedIdentifiers(receipt) {
  if (receipt.target !== null) {
    const target = requirePlainObject(receipt.target, "receipt target");
    requireSafeIdentifier(target.id, "receipt target id");
    requireChatGptUrl(target.url, "receipt target url");
  }
  if (receipt.model !== null) {
    const model = requirePlainObject(receipt.model, "receipt model");
    requireSafeIdentifier(model.requested, "receipt model requested");
    requireSafeIdentifier(model.observed, "receipt model observed");
  }
  if (receipt.tool !== null) {
    const tool = requirePlainObject(receipt.tool, "receipt tool");
    requireSafeIdentifier(tool.requested, "receipt tool requested");
    requireSafeIdentifier(tool.observed, "receipt tool observed");
  }
  if (receipt.submission !== null) {
    const submission = requirePlainObject(
      receipt.submission,
      "receipt submission",
    );
    requireChatGptUrl(
      submission.conversation_url,
      "receipt submission conversation_url",
      { conversation: true },
    );
    requireSafeIdentifier(
      submission.baseline_assistant_turn_id,
      "receipt submission baseline_assistant_turn_id",
    );
    requireSafeIdentifier(
      submission.user_turn_id,
      "receipt submission user_turn_id",
    );
  }
  if (receipt.started !== null) {
    const started = requirePlainObject(receipt.started, "receipt started");
    requireSafeIdentifier(
      started.assistant_signal_id,
      "receipt started assistant_signal_id",
    );
  }
  if (receipt.result !== null) validateResultShape(receipt.result);
  if (receipt.error !== null) {
    const error = requirePlainObject(receipt.error, "receipt error");
    requireSafeIdentifier(error.code, "receipt error code", CODE_PATTERN);
    requireSafeIdentifier(error.stage, "receipt error stage");
    if (Object.hasOwn(error, "destination_id")) {
      requireSafeIdentifier(
        error.destination_id,
        "receipt error destination_id",
      );
    }
  }
}

function validateReceiptLockBinding(rawBinding) {
  const binding = requirePlainObject(rawBinding, "receipt lock binding");
  const required = ["dev", "ino", "ctime_ns"];
  if (
    Object.keys(binding).length !== required.length ||
    required.some((key) => !Object.hasOwn(binding, key))
  ) {
    fail("receipt lock binding has an invalid shape");
  }
  return Object.freeze({
    dev: requireString(
      binding.dev,
      "receipt lock binding dev",
      DECIMAL_PATTERN,
    ),
    ino: requireString(
      binding.ino,
      "receipt lock binding ino",
      DECIMAL_PATTERN,
    ),
    ctime_ns: requireString(
      binding.ctime_ns,
      "receipt lock binding ctime_ns",
      DECIMAL_PATTERN,
    ),
  });
}

function validateTransitionEvidence(receipt, to, rawEvidence) {
  let evidence;
  switch (to) {
    case "auth_ready":
      evidence = requireExactKeys(rawEvidence, [
        "run_id",
        "source",
        "profile_fingerprint",
        "challenge_observed",
      ]);
      requireRunBinding(receipt, evidence);
      if (evidence.source !== "browser") fail("auth evidence must come from browser");
      requireSha256(evidence.profile_fingerprint, "profile fingerprint");
      if (requireBoolean(evidence.challenge_observed, "challenge_observed")) {
        fail("auth_ready cannot be proven while a challenge is observed");
      }
      break;

    case "target_bound":
      evidence = requireExactKeys(rawEvidence, [
        "run_id",
        "source",
        "target_id",
        "target_url",
        "browser_pid",
      ]);
      requireRunBinding(receipt, evidence);
      if (evidence.source !== "browser") fail("target evidence must come from browser");
      requireSafeIdentifier(evidence.target_id, "target_id");
      evidence.target_url = requireChatGptUrl(evidence.target_url, "target_url");
      requireInteger(evidence.browser_pid, "browser_pid", 2);
      break;

    case "model_tool_verified":
      evidence = requireExactKeys(rawEvidence, [
        "run_id",
        "source",
        "target_id",
        "model_requested",
        "model_observed",
        "model_proven",
        "tool_requested",
        "tool_observed",
        "tool_proven",
      ]);
      requireRunBinding(receipt, evidence);
      if (evidence.source !== "browser") fail("model evidence must come from browser");
      requireTargetBinding(receipt, evidence);
      requireSafeIdentifier(evidence.model_requested, "model_requested");
      requireSafeIdentifier(evidence.model_observed, "model_observed");
      requireSafeIdentifier(evidence.tool_requested, "tool_requested");
      requireSafeIdentifier(evidence.tool_observed, "tool_observed");
      if (
        evidence.model_requested !== evidence.model_observed ||
        !/^gpt-[a-z0-9.]+-pro$/.test(evidence.model_requested) ||
        evidence.tool_requested !== evidence.tool_observed ||
        evidence.tool_requested !==
          (receipt.mode === "deep-research" ? "deep-research" : "none") ||
        evidence.model_proven !== true ||
        evidence.tool_proven !== true
      ) {
        fail("exact Pro model and mode tool must both be proven before submission");
      }
      break;

    case "submitted":
      evidence = requireExactKeys(rawEvidence, [
        "run_id",
        "source",
        "target_id",
        "conversation_url",
        "baseline_assistant_turn_id",
        "baseline_assistant_turn_position",
        "user_turn_id",
        "user_turn_position",
        "request_fingerprint",
        "deadline_at",
      ]);
      requireRunBinding(receipt, evidence);
      if (evidence.source !== "browser") fail("submission evidence must come from browser");
      requireTargetBinding(receipt, evidence);
      evidence.conversation_url = requireChatGptUrl(
        evidence.conversation_url,
        "conversation_url",
        { conversation: true },
      );
      requireSafeIdentifier(
        evidence.baseline_assistant_turn_id,
        "baseline_assistant_turn_id",
      );
      requireInteger(
        evidence.baseline_assistant_turn_position,
        "baseline_assistant_turn_position",
      );
      requireSafeIdentifier(evidence.user_turn_id, "user_turn_id");
      requireInteger(evidence.user_turn_position, "user_turn_position");
      requireSha256(evidence.request_fingerprint, "request_fingerprint");
      evidence.deadline_at = requireTimestamp(
        evidence.deadline_at,
        "deadline_at",
      );
      if (evidence.request_fingerprint !== receipt.request_fingerprint) {
        fail("submitted request fingerprint does not match this run");
      }
      if (
        evidence.user_turn_id === evidence.baseline_assistant_turn_id ||
        evidence.user_turn_position <=
          evidence.baseline_assistant_turn_position
      ) {
        fail("submitted user turn must be ordered after the baseline");
      }
      break;

    case "started":
      evidence = requireExactKeys(rawEvidence, [
        "run_id",
        "source",
        "target_id",
        "conversation_url",
        "user_turn_id",
        "assistant_signal_id",
        "assistant_signal_position",
      ]);
      requireRunBinding(receipt, evidence);
      if (evidence.source !== "browser") fail("start evidence must come from browser");
      requireConversationBinding(receipt, evidence);
      requireSafeIdentifier(
        evidence.assistant_signal_id,
        "assistant_signal_id",
      );
      requireInteger(
        evidence.assistant_signal_position,
        "assistant_signal_position",
      );
      if (
        evidence.assistant_signal_id ===
          receipt.submission.baseline_assistant_turn_id ||
        evidence.assistant_signal_id === receipt.submission.user_turn_id ||
        evidence.assistant_signal_position <=
          receipt.submission.user_turn_position
      ) {
        fail("started requires an assistant signal ordered after the submitted user turn");
      }
      break;

    case "completed":
      evidence = requireExactKeys(rawEvidence, [
        "run_id",
        "source",
        "target_id",
        "conversation_url",
        "user_turn_id",
        "final_assistant_turn_id",
        "final_assistant_turn_position",
        "result",
      ]);
      requireRunBinding(receipt, evidence);
      if (evidence.source !== "browser") fail("completion evidence must come from browser");
      requireConversationBinding(receipt, evidence);
      requireSafeIdentifier(
        evidence.final_assistant_turn_id,
        "final_assistant_turn_id",
      );
      requireInteger(
        evidence.final_assistant_turn_position,
        "final_assistant_turn_position",
      );
      if (
        evidence.final_assistant_turn_id ===
          receipt.submission.baseline_assistant_turn_id ||
        evidence.final_assistant_turn_id === receipt.submission.user_turn_id ||
        evidence.final_assistant_turn_id ===
          receipt.started.assistant_signal_id ||
        evidence.final_assistant_turn_position <=
          receipt.started.assistant_signal_position
      ) {
        fail("completed requires a new final assistant turn ordered after started");
      }
      evidence.result = validateResultShape(evidence.result);
      break;

    case "failed": {
      const optional = receipt.target ? ["target_id"] : [];
      evidence = requireExactKeys(
        rawEvidence,
        ["run_id", "source", "code", "stage"],
        optional,
      );
      requireRunBinding(receipt, evidence);
      if (!["browser", "controller"].includes(evidence.source)) {
        fail("failure evidence source is invalid");
      }
      requireSafeIdentifier(
        evidence.code,
        "failure code",
        CODE_PATTERN,
      );
      requireSafeIdentifier(evidence.stage, "failure stage");
      if (evidence.stage !== receipt.state) {
        fail("failure stage does not match current state");
      }
      if (receipt.target) requireTargetBinding(receipt, evidence);
      break;
    }

    case "timed_out":
      evidence = requireExactKeys(rawEvidence, [
        "run_id",
        "source",
        "target_id",
        "conversation_url",
        "user_turn_id",
        "deadline_at",
        "last_state",
      ]);
      requireRunBinding(receipt, evidence);
      if (evidence.source !== "controller") {
        fail("timeout evidence must come from controller");
      }
      requireConversationBinding(receipt, evidence);
      requireSafeIdentifier(evidence.last_state, "timeout last_state");
      if (evidence.last_state !== receipt.state) {
        fail("timeout last_state does not match current state");
      }
      evidence.deadline_at = requireTimestamp(
        evidence.deadline_at,
        "deadline_at",
      );
      if (evidence.deadline_at !== receipt.submission.deadline_at) {
        fail("timeout deadline does not match the submitted deadline");
      }
      break;

    case "cancelled": {
      const optional = receipt.target ? ["target_id"] : [];
      evidence = requireExactKeys(
        rawEvidence,
        ["run_id", "source", "actor", "reason_code", "last_state"],
        optional,
      );
      requireRunBinding(receipt, evidence);
      requireSafeIdentifier(evidence.actor, "cancellation actor");
      if (evidence.source !== evidence.actor) {
        fail("cancellation source must match its actor");
      }
      if (!["user", "operator"].includes(evidence.actor)) {
        fail("cancellation actor must be user or operator");
      }
      requireSafeIdentifier(
        evidence.reason_code,
        "reason_code",
        CODE_PATTERN,
      );
      requireSafeIdentifier(evidence.last_state, "cancellation last_state");
      if (evidence.last_state !== receipt.state) {
        fail("cancellation last_state does not match current state");
      }
      if (receipt.target) requireTargetBinding(receipt, evidence);
      break;
    }

    case "delivery_failed":
      evidence = requireExactKeys(rawEvidence, [
        "run_id",
        "source",
        "target_id",
        "conversation_url",
        "user_turn_id",
        "final_assistant_turn_id",
        "final_assistant_turn_position",
        "result",
        "destination_id",
        "delivery_code",
      ]);
      requireRunBinding(receipt, evidence);
      if (evidence.source !== "delivery") {
        fail("delivery failure evidence must come from delivery");
      }
      requireConversationBinding(receipt, evidence);
      requireSafeIdentifier(
        evidence.final_assistant_turn_id,
        "final_assistant_turn_id",
      );
      requireInteger(
        evidence.final_assistant_turn_position,
        "final_assistant_turn_position",
      );
      if (
        evidence.final_assistant_turn_id ===
          receipt.submission.baseline_assistant_turn_id ||
        evidence.final_assistant_turn_id === receipt.submission.user_turn_id ||
        evidence.final_assistant_turn_id ===
          receipt.started.assistant_signal_id ||
        evidence.final_assistant_turn_position <=
          receipt.started.assistant_signal_position
      ) {
        fail("delivery failure requires a new final assistant turn ordered after started");
      }
      requireSafeIdentifier(evidence.destination_id, "destination_id");
      requireSafeIdentifier(
        evidence.delivery_code,
        "delivery_code",
        CODE_PATTERN,
      );
      evidence.result = validateResultShape(evidence.result);
      break;

    default:
      fail("unsupported transition target");
  }
  return structuredClone(evidence);
}

function appendEvent(receipt, { to, eventId, observedAt, evidence }) {
  const previous = receipt.history.at(-1);
  const event = {
    event_id: requireSafeIdentifier(eventId, "event_id"),
    run_id: receipt.run_id,
    from: receipt.state,
    to,
    observed_at: requireTimestamp(observedAt, "observed_at"),
    previous_event_hash: previous.event_hash,
    evidence,
  };
  if (Date.parse(event.observed_at) < Date.parse(previous.observed_at)) {
    fail("transition timestamp precedes the previous event");
  }
  event.event_hash = eventHash(event);
  receipt.history.push(event);
  receipt.head_event_hash = event.event_hash;
  receipt.revision += 1;
  receipt.state = to;
  receipt.timestamps[to] = event.observed_at;
}

function applyDerivedState(receipt, to, evidence, fromState) {
  if (to === "target_bound") {
    receipt.target = {
      id: evidence.target_id,
      url: evidence.target_url,
      browser_pid: evidence.browser_pid,
    };
  } else if (to === "model_tool_verified") {
    receipt.model = {
      requested: evidence.model_requested,
      observed: evidence.model_observed,
      proven: true,
    };
    receipt.tool = {
      requested: evidence.tool_requested,
      observed: evidence.tool_observed,
      proven: true,
    };
  } else if (to === "submitted") {
    receipt.submission = {
      conversation_url: evidence.conversation_url,
      baseline_assistant_turn_id: evidence.baseline_assistant_turn_id,
      baseline_assistant_turn_position:
        evidence.baseline_assistant_turn_position,
      user_turn_id: evidence.user_turn_id,
      user_turn_position: evidence.user_turn_position,
      deadline_at: evidence.deadline_at,
    };
  } else if (to === "started") {
    receipt.started = {
      assistant_signal_id: evidence.assistant_signal_id,
      assistant_signal_position: evidence.assistant_signal_position,
    };
  } else if (to === "completed") {
    receipt.result = structuredClone(evidence.result);
  } else if (to === "delivery_failed") {
    receipt.result = structuredClone(evidence.result);
    receipt.error = {
      code: evidence.delivery_code,
      stage: "delivery",
      destination_id: evidence.destination_id,
    };
  } else if (TERMINAL_SET.has(to)) {
    receipt.error = {
      code:
        evidence.code ??
        evidence.reason_code ??
        (to === "timed_out" ? "deadline_exceeded" : to),
      stage: fromState,
    };
  }
}

function reduceReceipt(receipt, transition) {
  validateReceipt(receipt);
  const next = structuredClone(receipt);
  const to = transition?.to;
  requireSafeIdentifier(to, "transition target state");
  if (!STATES.includes(to)) fail("transition target state is invalid");
  requireInteger(transition.expectedRevision, "expected revision");
  if (transition.expectedRevision !== next.revision) {
    fail(
      `revision mismatch: expected ${transition.expectedRevision}, current ${next.revision}`,
    );
  }
  if (!LEGAL_TRANSITIONS[next.state].has(to)) {
    fail(`illegal transition ${next.state} -> ${to}`);
  }
  const evidence = validateTransitionEvidence(next, to, transition.evidence);
  if (
    to === "submitted" &&
    Date.parse(requireTimestamp(transition.observedAt, "observed_at")) >=
      Date.parse(evidence.deadline_at)
  ) {
    fail("submitted deadline must be later than submission");
  }
  if (
    to === "timed_out" &&
    (Date.parse(requireTimestamp(transition.observedAt, "observed_at")) <
      Date.parse(evidence.deadline_at) ||
      Date.now() < Date.parse(evidence.deadline_at))
  ) {
    fail("timed_out cannot precede its anchored deadline");
  }
  appendEvent(next, {
    to,
    eventId: transition.eventId,
    observedAt: transition.observedAt,
    evidence,
  });
  applyDerivedState(next, to, evidence, receipt.state);
  return finalizeReceipt(next);
}

export function createReceipt({
  runId = randomUUID(),
  slug,
  mode,
  requestFingerprint,
  receiptLock,
  createdAt = new Date().toISOString(),
  eventId = randomUUID(),
} = {}) {
  requireSafeIdentifier(runId, "run_id", RUN_ID_PATTERN);
  requireSafeIdentifier(slug, "slug", SLUG_PATTERN);
  if (!["pro", "deep-research"].includes(mode)) {
    fail("mode must be pro or deep-research");
  }
  requireSha256(requestFingerprint, "request_fingerprint");
  const receiptLockBinding = validateReceiptLockBinding(receiptLock);
  const observedAt = requireTimestamp(createdAt, "created_at");
  const evidence = {
    run_id: runId,
    source: "controller",
    request_fingerprint: requestFingerprint,
  };
  const event = {
    event_id: requireSafeIdentifier(eventId, "event_id"),
    run_id: runId,
    from: null,
    to: "created",
    observed_at: observedAt,
    previous_event_hash: null,
    evidence,
  };
  event.event_hash = eventHash(event);
  return finalizeReceipt({
    schema: RECEIPT_SCHEMA,
    run_id: runId,
    slug,
    mode,
    request_fingerprint: requestFingerprint,
    receipt_lock: receiptLockBinding,
    state: "created",
    revision: 0,
    target: null,
    model: null,
    tool: null,
    submission: null,
    started: null,
    result: null,
    error: null,
    timestamps: { created: observedAt },
    history: [event],
    head_event_hash: event.event_hash,
  });
}

export function validateReceipt(rawReceipt) {
  const receipt = requirePlainObject(rawReceipt, "receipt");
  const requiredKeys = [
    "schema",
    "run_id",
    "slug",
    "mode",
    "request_fingerprint",
    "receipt_lock",
    "state",
    "revision",
    "target",
    "model",
    "tool",
    "submission",
    "started",
    "result",
    "error",
    "timestamps",
    "history",
    "head_event_hash",
    "receipt_hash",
  ];
  if (
    Object.keys(receipt).length !== requiredKeys.length ||
    requiredKeys.some((key) => !Object.hasOwn(receipt, key))
  ) {
    fail("receipt has an invalid top-level shape");
  }
  if (receipt.schema !== RECEIPT_SCHEMA) fail("receipt schema is invalid");
  requireSafeIdentifier(receipt.run_id, "run_id", RUN_ID_PATTERN);
  requireSafeIdentifier(receipt.slug, "slug", SLUG_PATTERN);
  if (!["pro", "deep-research"].includes(receipt.mode)) {
    fail("receipt mode is invalid");
  }
  requireSha256(receipt.request_fingerprint, "request_fingerprint");
  validateReceiptLockBinding(receipt.receipt_lock);
  requireSafeIdentifier(receipt.state, "receipt state");
  if (!STATES.includes(receipt.state)) fail("receipt state is invalid");
  validatePersistedDerivedIdentifiers(receipt);
  requireInteger(receipt.revision, "revision");
  if (!Array.isArray(receipt.history) || receipt.history.length === 0) {
    fail("receipt history is empty");
  }
  if (receipt.revision !== receipt.history.length - 1) {
    fail("receipt revision does not match history");
  }
  let previousHash = null;
  let previousAt = 0;
  let previousState = null;
  const timestampKeys = [];
  const eventIds = new Set();
  const derived = {
    run_id: receipt.run_id,
    request_fingerprint: receipt.request_fingerprint,
    mode: receipt.mode,
    state: "created",
    target: null,
    model: null,
    tool: null,
    submission: null,
    started: null,
    result: null,
    error: null,
  };
  for (const [index, event] of receipt.history.entries()) {
    requirePlainObject(event, `history event ${index}`);
    const eventKeys = [
      "event_id",
      "run_id",
      "from",
      "to",
      "observed_at",
      "previous_event_hash",
      "evidence",
      "event_hash",
    ];
    if (
      Object.keys(event).length !== eventKeys.length ||
      eventKeys.some((key) => !Object.hasOwn(event, key))
    ) {
      fail(`history event ${index} has an invalid shape`);
    }
    const eventId = requireSafeIdentifier(
      event.event_id,
      `history event ${index} event_id`,
    );
    requireSafeIdentifier(
      event.run_id,
      `history event ${index} run_id`,
      RUN_ID_PATTERN,
    );
    requireSafeIdentifier(
      event.evidence?.run_id,
      `history event ${index} evidence run_id`,
      RUN_ID_PATTERN,
    );
    if (event.from !== null) {
      requireSafeIdentifier(
        event.from,
        `history event ${index} from state`,
      );
    }
    requireSafeIdentifier(event.to, `history event ${index} to state`);
    if (eventIds.has(eventId)) fail("receipt history contains a duplicate event_id");
    eventIds.add(eventId);
    if (
      (index === 0 &&
        (event.from !== null || event.to !== "created")) ||
      (index > 0 &&
        (event.from !== previousState ||
          !LEGAL_TRANSITIONS[previousState]?.has(event.to)))
    ) {
      fail(`history event ${index} is an illegal transition`);
    }
    if (
      event.run_id !== receipt.run_id ||
      event.evidence?.run_id !== receipt.run_id ||
      event.previous_event_hash !== previousHash ||
      event.event_hash !== eventHash(event)
    ) {
      fail(`history event ${index} is not run-bound or hash-valid`);
    }
    const normalizedObservedAt = requireTimestamp(
      event.observed_at,
      "event timestamp",
    );
    if (event.observed_at !== normalizedObservedAt) {
      fail(`history event ${index} timestamp is not canonical`);
    }
    const timestamp = Date.parse(normalizedObservedAt);
    if (timestamp < previousAt) fail("receipt history timestamps regress");
    if (index === 0) {
      const evidence = requireExactKeys(event.evidence, [
        "run_id",
        "source",
        "request_fingerprint",
      ]);
      requireRunBinding(derived, evidence);
      if (
        evidence.source !== "controller" ||
        evidence.request_fingerprint !== receipt.request_fingerprint
      ) {
        fail("created evidence does not match the receipt");
      }
    } else {
      const fromState = derived.state;
      const evidence = validateTransitionEvidence(
        derived,
        event.to,
        event.evidence,
      );
      if (canonicalJson(evidence) !== canonicalJson(event.evidence)) {
        fail(`history event ${index} evidence is not canonical`);
      }
      if (
        event.to === "submitted" &&
        timestamp >= Date.parse(evidence.deadline_at)
      ) {
        fail("submitted history deadline is not later than submission");
      }
      if (
        event.to === "timed_out" &&
        timestamp < Date.parse(evidence.deadline_at)
      ) {
        fail("timed_out history event precedes its deadline");
      }
      applyDerivedState(derived, event.to, evidence, fromState);
      derived.state = event.to;
    }
    previousAt = timestamp;
    previousHash = event.event_hash;
    previousState = event.to;
    timestampKeys.push(event.to);
  }
  const lastEvent = receipt.history.at(-1);
  if (
    receipt.state !== lastEvent.to ||
    receipt.head_event_hash !== lastEvent.event_hash
  ) {
    fail("receipt head does not match its history");
  }
  for (const key of [
    "state",
    "target",
    "model",
    "tool",
    "submission",
    "started",
    "result",
    "error",
  ]) {
    if (canonicalJson(receipt[key]) !== canonicalJson(derived[key])) {
      fail(`receipt ${key} does not match replayed history`);
    }
  }
  const timestamps = requirePlainObject(receipt.timestamps, "timestamps");
  if (
    Object.keys(timestamps).length !== timestampKeys.length ||
    timestampKeys.some(
      (state, index) =>
        timestamps[state] !== receipt.history[index].observed_at,
    )
  ) {
    fail("receipt timestamps do not match history");
  }
  if (receipt.receipt_hash !== receiptHash(receipt)) {
    fail("receipt hash is invalid");
  }
  return structuredClone(receipt);
}

/**
 * Allow only root-owned intermediate symlinks (macOS /tmp -> /private/tmp).
 * Leaf/user-owned redirects and unresolved case-hostile aliases still fail.
 */
async function assertNoHostileSymlinkTraversal(absolutePath, label) {
  const resolved = await realpath(absolutePath);
  if (resolved === absolutePath) return;

  if (typeof process.getuid !== "function") {
    fail(`${label} traverses a symlink or case alias`);
  }

  const prefixes = [];
  let current = absolutePath;
  while (current !== dirname(current)) {
    prefixes.unshift(current);
    current = dirname(current);
  }

  let sawSystemSymlink = false;
  for (const prefix of prefixes) {
    let metadata;
    try {
      metadata = await lstat(prefix);
    } catch (error) {
      if (error?.code === "ENOENT") continue;
      throw error;
    }
    if (!metadata.isSymbolicLink()) continue;
    if (prefix === absolutePath || metadata.uid !== 0) {
      fail(`${label} traverses a symlink or case alias`);
    }
    sawSystemSymlink = true;
  }

  // realpath differed with no intermediate system symlink: case alias / other
  // non-canonical form. Keep fail-closed except the macOS /tmp allowance.
  if (!sawSystemSymlink) {
    fail(`${label} traverses a symlink or case alias`);
  }
}

async function assertCanonicalExistingPath(path, label) {
  await assertNoHostileSymlinkTraversal(path, label);
}

function validatePrivateRegularMetadata(
  metadata,
  label,
  { singleLink = false } = {},
) {
  if (!metadata.isFile()) fail(`${label} is not a regular file`);
  if ((metadata.mode & 0o077) !== 0) {
    fail(`${label} grants group/world access`);
  }
  if (
    typeof process.getuid === "function" &&
    metadata.uid !== process.getuid()
  ) {
    fail(`${label} is not owned by the current user`);
  }
  if (singleLink && metadata.nlink !== 1) {
    fail(`${label} has an unexpected hard-link alias`);
  }
}

async function assertPrivateRegularFile(
  path,
  label,
  { singleLink = false } = {},
) {
  const metadata = await lstat(path);
  if (!metadata.isFile() || metadata.isSymbolicLink()) {
    fail(`${label} is not a regular file`);
  }
  validatePrivateRegularMetadata(metadata, label, { singleLink });
  return metadata;
}

async function readPrivateRegularFile(
  path,
  label,
  { singleLink = false } = {},
) {
  await assertCanonicalExistingPath(path, label);
  const flags =
    fsConstants.O_RDONLY |
    (fsConstants.O_NOFOLLOW ?? 0) |
    (fsConstants.O_CLOEXEC ?? 0);
  const handle = await open(path, flags);
  try {
    const metadata = await handle.stat();
    validatePrivateRegularMetadata(metadata, label, { singleLink });
    const namedBefore = await assertPrivateRegularFile(path, label, {
      singleLink,
    });
    if (!sameFile(metadata, namedBefore)) {
      fail(`${label} pathname was replaced`);
    }
    const bytes = await handle.readFile();
    const [openedAfter, namedAfter] = await Promise.all([
      handle.stat(),
      assertPrivateRegularFile(path, label, { singleLink }),
    ]);
    if (
      !sameFile(metadata, openedAfter) ||
      !sameFile(metadata, namedAfter)
    ) {
      fail(`${label} pathname was replaced`);
    }
    await assertCanonicalExistingPath(path, label);
    return { bytes, metadata };
  } finally {
    await handle.close();
  }
}

async function fsyncDirectory(path) {
  let handle;
  try {
    handle = await open(path, fsConstants.O_RDONLY);
    await handle.sync();
  } finally {
    await handle?.close();
  }
}

async function atomicWrite(
  path,
  bytes,
  {
    replaceExisting,
    commitState = null,
    preCommitDelayMs = 0,
  },
) {
  requireAbsolutePath(path, "artifact path");
  const parent = dirname(path);
  await assertCanonicalExistingPath(parent, "artifact parent");
  const temporaryPath = `${parent}/.${basename(path)}.${process.pid}.${randomUUID()}.tmp`;
  let handle;
  try {
    handle = await open(
      temporaryPath,
      fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_WRONLY,
      0o600,
    );
    await handle.writeFile(bytes);
    await handle.sync();
    await handle.close();
    handle = undefined;
    if (preCommitDelayMs > 0) {
      await new Promise((resolvePromise) =>
        setTimeout(resolvePromise, preCommitDelayMs),
      );
    }
    if (replaceExisting) {
      try {
        const existing = await lstat(path);
        if (existing.isSymbolicLink() || !existing.isFile()) {
          fail("refusing to replace a non-regular artifact path");
        }
      } catch (error) {
        if (error.code !== "ENOENT") throw error;
      }
      if (commitState) commitState.rename_may_have_happened = true;
      await rename(temporaryPath, path);
      if (commitState) commitState.renamed = true;
    } else {
      await link(temporaryPath, path);
      await unlink(temporaryPath);
    }
    await fsyncDirectory(parent);
    if (commitState) commitState.durable = true;
  } catch (error) {
    await handle?.close().catch(() => {});
    await unlink(temporaryPath).catch(() => {});
    throw error;
  }
}

function sameFile(left, right) {
  return left.dev === right.dev && left.ino === right.ino;
}

async function validateResultIsolation(
  receiptPath,
  result,
  { lockPath = null } = {},
) {
  const paths = [
    [receiptPath, "receipt file"],
    [result.path, "result file"],
    [result.proof_path, "result proof file"],
  ];
  if (lockPath) paths.push([lockPath, "receipt lock"]);
  if (new Set(paths.map(([path]) => path)).size !== paths.length) {
    fail("result artifacts overlap receipt control files");
  }
  const files = [];
  for (const [path, label] of paths) {
    await assertCanonicalExistingPath(path, label);
    const metadata = await assertPrivateRegularFile(path, label, {
      singleLink: true,
    });
    files.push({ path, label, metadata });
  }
  for (let left = 0; left < files.length; left += 1) {
    for (let right = left + 1; right < files.length; right += 1) {
      if (sameFile(files[left].metadata, files[right].metadata)) {
        fail(`${files[left].label} aliases ${files[right].label}`);
      }
    }
  }
}

async function verifyResultFile(result, expectedRunId) {
  validateResultShape(result);
  if (result.run_id !== expectedRunId) {
    fail("result proof is not bound to this run");
  }
  const resultFile = await readPrivateRegularFile(result.path, "result file", {
    singleLink: true,
  });
  const { metadata } = resultFile;
  if (metadata.size < 1 || metadata.size !== result.bytes) {
    fail("result byte count does not match the nonempty file");
  }
  const observedHash = sha256(resultFile.bytes);
  if (observedHash !== result.sha256) {
    fail("result sha256 does not match the file");
  }
  const proofFile = await readPrivateRegularFile(
    result.proof_path,
    "result proof file",
    { singleLink: true },
  );
  const proof = parseJsonNonEcho(proofFile.bytes, "result proof");
  const proofKeys = [
    "schema",
    "run_id",
    "path",
    "bytes",
    "sha256",
    "atomic_write_id",
  ];
  if (
    !isPlainObject(proof) ||
    Object.keys(proof).length !== proofKeys.length ||
    proofKeys.some((key) => !Object.hasOwn(proof, key))
  ) {
    fail("result atomic-write proof has an invalid shape");
  }
  if (proof.schema !== "oracle-subagent.result-write-proof.v1") {
    fail("result atomic-write proof schema is invalid");
  }
  requireSafeIdentifier(proof.run_id, "result proof run_id", RUN_ID_PATTERN);
  requireSafePersistedPath(proof.path, "result proof path");
  requireInteger(proof.bytes, "result proof bytes", 1);
  requireSha256(proof.sha256, "result proof sha256");
  requireSafeIdentifier(
    proof.atomic_write_id,
    "result proof atomic_write_id",
    RUN_ID_PATTERN,
  );
  const expectedProof = {
    schema: "oracle-subagent.result-write-proof.v1",
    run_id: result.run_id,
    path: result.path,
    bytes: result.bytes,
    sha256: result.sha256,
    atomic_write_id: result.atomic_write_id,
  };
  if (canonicalJson(proof) !== canonicalJson(expectedProof)) {
    fail("result atomic-write proof does not match the file");
  }
}

export async function writeResultAtomic(path, content, { runId } = {}) {
  requireSafeIdentifier(runId, "result run_id", RUN_ID_PATTERN);
  requireSafePersistedPath(path, "result path");
  const bytes = Buffer.isBuffer(content)
    ? content
    : Buffer.from(String(content), "utf8");
  if (bytes.length === 0) fail("result content must be nonempty");
  await atomicWrite(path, bytes, { replaceExisting: true });
  await assertCanonicalExistingPath(path, "result file");
  await assertPrivateRegularFile(path, "result file", { singleLink: true });
  const result = {
    path,
    bytes: bytes.length,
    sha256: sha256(bytes),
    run_id: runId,
    atomic_write_id: randomUUID(),
    proof_path: `${path}.oracle-write-proof.json`,
  };
  await atomicWrite(
    result.proof_path,
    `${canonicalJson({
      schema: "oracle-subagent.result-write-proof.v1",
      run_id: result.run_id,
      path: result.path,
      bytes: result.bytes,
      sha256: result.sha256,
      atomic_write_id: result.atomic_write_id,
    })}\n`,
    { replaceExisting: true },
  );
  return result;
}

export async function readReceiptFile(path) {
  requireAbsolutePath(path, "receipt path");
  const receiptFile = await readPrivateRegularFile(path, "receipt file", {
    singleLink: true,
  });
  const receipt = validateReceipt(
    parseJsonNonEcho(receiptFile.bytes, "receipt file"),
  );
  if (["completed", "delivery_failed"].includes(receipt.state)) {
    await validateResultIsolation(path, receipt.result);
    await verifyResultFile(receipt.result, receipt.run_id);
  }
  return receipt;
}

export async function createReceiptFile(path, initial) {
  requireAbsolutePath(path, "receipt path");
  const lock = await acquireLock(path, {}, { createExclusive: true });
  try {
    const receipt = createReceipt({
      ...initial,
      receiptLock: lock.identity,
    });
    await atomicWrite(path, `${canonicalJson(receipt)}\n`, {
      replaceExisting: false,
    });
    await receiptLockIdentity(lock.lockPath, lock.handle, lock.identity);
    const persisted = await readReceiptFile(path);
    if (canonicalJson(persisted) !== canonicalJson(receipt)) {
      fail("created receipt does not match its durable publication");
    }
    return persisted;
  } finally {
    await releaseLock(lock);
  }
}

async function acquireLock(
  receiptPath,
  {
    timeoutMs = 5_000,
    pollMs = 20,
    postAcquireDelayMs = 0,
  } = {},
  { createExclusive = false } = {},
) {
  requireInteger(timeoutMs, "lock timeoutMs");
  requireInteger(pollMs, "lock pollMs", 1);
  requireInteger(postAcquireDelayMs, "lock postAcquireDelayMs");
  const lockPath = `${receiptPath}.lock`;
  await assertCanonicalExistingPath(dirname(lockPath), "receipt lock parent");
  const flags =
    fsConstants.O_RDWR |
    (createExclusive ? fsConstants.O_CREAT | fsConstants.O_EXCL : 0) |
    (fsConstants.O_NOFOLLOW ?? 0) |
    (fsConstants.O_CLOEXEC ?? 0);
  const handle = await open(lockPath, flags, 0o600);
  try {
    validatePrivateRegularMetadata(await handle.stat(), "receipt lock", {
      singleLink: true,
    });
    await assertCanonicalExistingPath(lockPath, "receipt lock");
    const identity = await receiptLockIdentity(lockPath, handle);
    await handle.sync();
    await fsyncDirectory(dirname(lockPath));
    const helper = spawn(
      "/usr/bin/python3",
      [
        "-I",
        "-c",
        `
import fcntl
import sys
import time

descriptor = 3
deadline = time.monotonic() + (int(sys.argv[1]) / 1000)
poll = int(sys.argv[2]) / 1000
while True:
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        raise SystemExit(0)
    except BlockingIOError:
        if time.monotonic() >= deadline:
            raise SystemExit(75)
        time.sleep(poll)
`,
        String(timeoutMs),
        String(pollMs),
      ],
      {
        env: { PATH: "/usr/bin:/bin", LANG: "C", LC_ALL: "C" },
        stdio: ["ignore", "ignore", "pipe", handle.fd],
      },
    );
    let standardError = "";
    helper.stderr.setEncoding("utf8");
    helper.stderr.on("data", (chunk) => {
      if (standardError.length < 4096) standardError += chunk;
    });
    const code = await new Promise((resolvePromise, rejectPromise) => {
      helper.once("error", rejectPromise);
      helper.once("exit", resolvePromise);
    });
    if (code === 75) fail("timed out waiting for receipt lock");
    if (code !== 0) fail("receipt lock helper failed closed");
    if (standardError) fail("receipt lock helper emitted diagnostics");
    if (postAcquireDelayMs > 0) {
      await new Promise((resolvePromise) =>
        setTimeout(resolvePromise, postAcquireDelayMs),
      );
    }
    await receiptLockIdentity(lockPath, handle, identity);
    return { handle, lockPath, identity };
  } catch (error) {
    await handle.close().catch(() => {});
    throw error;
  }
}

async function releaseLock({ handle }) {
  await handle.close();
}

async function receiptLockIdentity(lockPath, handle, expected = null) {
  const [opened, named, openedPrecise, namedPrecise] = await Promise.all([
    handle.stat(),
    lstat(lockPath),
    handle.stat({ bigint: true }),
    lstat(lockPath, { bigint: true }),
  ]);
  validatePrivateRegularMetadata(opened, "receipt lock", {
    singleLink: true,
  });
  validatePrivateRegularMetadata(named, "receipt lock", {
    singleLink: true,
  });
  await assertCanonicalExistingPath(lockPath, "receipt lock");
  const identity = Object.freeze({
    dev: openedPrecise.dev.toString(),
    ino: openedPrecise.ino.toString(),
    ctime_ns: openedPrecise.ctimeNs.toString(),
  });
  if (
    openedPrecise.dev !== namedPrecise.dev ||
    openedPrecise.ino !== namedPrecise.ino ||
    openedPrecise.ctimeNs !== namedPrecise.ctimeNs ||
    (expected &&
      (identity.dev !== expected.dev ||
        identity.ino !== expected.ino ||
        identity.ctime_ns !== expected.ctime_ns))
  ) {
    fail("receipt lock was replaced");
  }
  return identity;
}

function requireReceiptLockBinding(receipt, observedIdentity) {
  const binding = validateReceiptLockBinding(receipt.receipt_lock);
  if (
    binding.dev !== observedIdentity.dev ||
    binding.ino !== observedIdentity.ino ||
    binding.ctime_ns !== observedIdentity.ctime_ns
  ) {
    fail("receipt lock does not match its immutable receipt binding");
  }
}

async function readReceiptUnderLock(path, assertLockStable) {
  const receipt = await readReceiptFile(path);
  const identity = await assertLockStable();
  requireReceiptLockBinding(receipt, identity);
  return receipt;
}

function unprovableCommit(cause = undefined) {
  const error = new Error(
    "oracle-subagent state: transition commit outcome is unprovable",
    cause ? { cause } : undefined,
  );
  error.code = "ORACLE_SUBAGENT_COMMIT_UNPROVABLE";
  return error;
}

async function reconcileReceiptCommit(path, next, cause) {
  try {
    const observed = await readReceiptFile(path);
    if (
      observed.receipt_hash !== next.receipt_hash ||
      canonicalJson(observed) !== canonicalJson(next)
    ) {
      throw unprovableCommit(cause);
    }
    await fsyncDirectory(dirname(path));
    const durable = await readReceiptFile(path);
    if (
      durable.receipt_hash !== next.receipt_hash ||
      canonicalJson(durable) !== canonicalJson(next)
    ) {
      throw unprovableCommit(cause);
    }
    return durable;
  } catch (error) {
    if (error?.code === "ORACLE_SUBAGENT_COMMIT_UNPROVABLE") throw error;
    throw unprovableCommit(cause ?? error);
  }
}

export async function withReceiptFileLock(
  path,
  callback,
  lockOptions = {},
) {
  requireAbsolutePath(path, "receipt path");
  if (typeof callback !== "function") fail("receipt lock callback is invalid");
  const lock = await acquireLock(path, lockOptions);
  const assertLockStable = () =>
    receiptLockIdentity(lock.lockPath, lock.handle, lock.identity);
  try {
    await readReceiptUnderLock(path, assertLockStable);
    const result = await callback(assertLockStable);
    await readReceiptUnderLock(path, assertLockStable);
    return result;
  } finally {
    await releaseLock(lock);
  }
}

export async function transitionReceiptFile(
  path,
  transition,
  lockOptions = {},
) {
  requireAbsolutePath(path, "receipt path");
  const preCommitDelayMs = lockOptions.preCommitDelayMs ?? 0;
  const postCommitDelayMs = lockOptions.postCommitDelayMs ?? 0;
  requireInteger(preCommitDelayMs, "lock preCommitDelayMs");
  requireInteger(postCommitDelayMs, "lock postCommitDelayMs");
  if (
    preCommitDelayMs > MAX_BOUNDARY_DELAY_MS ||
    postCommitDelayMs > MAX_BOUNDARY_DELAY_MS
  ) {
    fail(`lock boundary delays must be <= ${MAX_BOUNDARY_DELAY_MS}`);
  }
  const lock = await acquireLock(path, lockOptions);
  const assertLockStable = () =>
    receiptLockIdentity(lock.lockPath, lock.handle, lock.identity);
  try {
    const receipt = await readReceiptUnderLock(path, assertLockStable);
    if (["completed", "delivery_failed"].includes(transition?.to)) {
      const result = transition?.evidence?.result;
      validateResultShape(result);
      await validateResultIsolation(path, result, {
        lockPath: `${path}.lock`,
      });
      await verifyResultFile(result, receipt.run_id);
      requireReceiptLockBinding(receipt, await assertLockStable());
    }
    const next = reduceReceipt(receipt, transition);
    requireReceiptLockBinding(receipt, await assertLockStable());
    const commitState = {
      rename_may_have_happened: false,
      renamed: false,
      durable: false,
    };
    try {
      await atomicWrite(path, `${canonicalJson(next)}\n`, {
        replaceExisting: true,
        commitState,
        preCommitDelayMs,
      });
    } catch (error) {
      if (!commitState.rename_may_have_happened) throw error;
      return reconcileReceiptCommit(path, next, error);
    }
    if (postCommitDelayMs > 0) {
      await new Promise((resolvePromise) =>
        setTimeout(resolvePromise, postCommitDelayMs),
      );
    }
    try {
      const persisted = await readReceiptUnderLock(path, assertLockStable);
      if (
        persisted.receipt_hash !== next.receipt_hash ||
        canonicalJson(persisted) !== canonicalJson(next)
      ) {
        throw unprovableCommit();
      }
      requireReceiptLockBinding(persisted, await assertLockStable());
      return persisted;
    } catch (error) {
      return reconcileReceiptCommit(path, next, error);
    }
  } finally {
    await releaseLock(lock);
  }
}
