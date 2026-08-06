import { spawn } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { constants as fsConstants } from "node:fs";
import {
  lstat,
  mkdir,
  open,
  readdir,
  realpath,
} from "node:fs/promises";
import { dirname, isAbsolute, join, resolve } from "node:path";

export const QUEUE_GENERATION_SCHEMA =
  "oracle-subagent.queue-generation.v1";
export const QUEUE_SNAPSHOT_SCHEMA = "oracle-subagent.queue-snapshot.v1";
export const QUEUE_HEAD_SCHEMA = "oracle-subagent.queue-head.v1";
export const QUEUE_WITNESS_SCHEMA = "oracle-subagent.queue-witness.v1";
export const QUEUE_ANCHOR_SCHEMA = "oracle-subagent.queue-anchor.v1";
export const QUEUE_RESULT_SCHEMA = "oracle-subagent.queue-result.v1";

const RUN_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$/;
const WORKER_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/;
const TARGET_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,255}$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const DECIMAL_PATTERN = /^(?:0|[1-9][0-9]{0,39})$/;
const SENSITIVE_PATTERN =
  /(?:authorization|bearer|cookie|password|prompt|secret|session[_-]?token|token|https?:\/\/)/i;
const CREDENTIAL_PATTERN =
  /(?:sk-(?:proj-)?[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{12,}|xapp-[A-Za-z0-9-]{12,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})/i;
const EMPTY_HASH = "0".repeat(64);
const MAX_LEDGER_BYTES = 64 * 1024 * 1024;
const MAX_HEAD_BYTES = 32 * 1024 * 1024;
const MAX_ANCHOR_BYTES = 32 * 1024 * 1024;
const MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024;
const MAX_HEAD_ENTRY_BYTES = 2_048;
const MAX_HEAD_RECORD_BYTES = MAX_HEAD_ENTRY_BYTES + 1;
const MAX_ANCHOR_ENTRY_BYTES = 1_024;
const MAX_ANCHOR_RECORD_BYTES = MAX_ANCHOR_ENTRY_BYTES + 1;
const MAX_ENTRIES = 100_000;
const MAX_RECORDS = 100_000;
const MAX_LOCK_TIMEOUT_MS = 60_000;
const MAX_LOCK_POLL_MS = 1_000;
const DEFAULT_LOCK_TIMEOUT_MS = 5_000;
const DEFAULT_LOCK_POLL_MS = 20;

export class OracleSubagentQueueError extends Error {
  constructor(code) {
    super("oracle-subagent queue: rejected");
    this.name = "OracleSubagentQueueError";
    this.code = code;
  }
}

function reject(code) {
  throw new OracleSubagentQueueError(code);
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

function safeInteger(value, minimum, maximum, code) {
  if (
    !Number.isSafeInteger(value) ||
    value < minimum ||
    value > maximum
  ) {
    reject(code);
  }
  return value;
}

function nullableInteger(value, minimum, maximum, code) {
  if (value === null) return null;
  return safeInteger(value, minimum, maximum, code);
}

function nullableIdentifier(value, pattern, code) {
  if (value === null) return null;
  return safeIdentifier(value, pattern, code);
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

function hashRecord(record, hashKey) {
  const copy = structuredClone(record);
  delete copy[hashKey];
  return sha256(canonicalJson(copy));
}

function deepFreeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value)) deepFreeze(child);
  }
  return value;
}

function absolutePath(value, code) {
  if (
    typeof value !== "string" ||
    !isAbsolute(value) ||
    value.includes("\0") ||
    value.includes("\n") ||
    resolve(value) !== value
  ) {
    reject(code);
  }
  return value;
}

function currentUid() {
  if (typeof process.getuid !== "function") reject("platform_unsupported");
  return process.getuid();
}

function validatePrivateDirectoryMetadata(metadata, code) {
  if (
    !metadata.isDirectory() ||
    metadata.isSymbolicLink() ||
    (metadata.mode & 0o777) !== 0o700 ||
    metadata.uid !== currentUid()
  ) {
    reject(code);
  }
}

function validatePrivateFileMetadata(metadata, code) {
  if (
    !metadata.isFile() ||
    metadata.isSymbolicLink() ||
    metadata.nlink !== 1 ||
    (metadata.mode & 0o777) !== 0o600 ||
    metadata.uid !== currentUid()
  ) {
    reject(code);
  }
}

async function privateDirectoryIdentity(path, code) {
  try {
    const [metadata, precise] = await Promise.all([
      lstat(path),
      lstat(path, { bigint: true }),
    ]);
    validatePrivateDirectoryMetadata(metadata, code);
    if ((await realpath(path)) !== path) reject(code);
    return Object.freeze({
      dev: precise.dev.toString(),
      ino: precise.ino.toString(),
    });
  } catch (error) {
    if (error instanceof OracleSubagentQueueError) throw error;
    reject(code);
  }
}

async function privateFileIdentity(path, code, { ctime = false } = {}) {
  try {
    const [metadata, precise] = await Promise.all([
      lstat(path),
      lstat(path, { bigint: true }),
    ]);
    validatePrivateFileMetadata(metadata, code);
    if ((await realpath(path)) !== path) reject(code);
    return Object.freeze({
      dev: precise.dev.toString(),
      ino: precise.ino.toString(),
      ...(ctime ? { ctime_ns: precise.ctimeNs.toString() } : {}),
    });
  } catch (error) {
    if (error instanceof OracleSubagentQueueError) throw error;
    reject(code);
  }
}

function sameIdentity(left, right, { ctime = false } = {}) {
  return (
    left.dev === right.dev &&
    left.ino === right.ino &&
    (!ctime || left.ctime_ns === right.ctime_ns)
  );
}

async function fsyncDirectory(path, code = "queue_durability_failed") {
  let handle;
  try {
    handle = await open(
      path,
      fsConstants.O_RDONLY |
        (fsConstants.O_DIRECTORY ?? 0) |
        (fsConstants.O_NOFOLLOW ?? 0) |
        (fsConstants.O_CLOEXEC ?? 0),
    );
    await handle.sync();
  } catch {
    reject(code);
  } finally {
    await handle?.close().catch(() => {});
  }
}

async function createPrivateFile(path, code) {
  let handle;
  try {
    handle = await open(
      path,
      fsConstants.O_CREAT |
        fsConstants.O_EXCL |
        fsConstants.O_RDWR |
        (fsConstants.O_NOFOLLOW ?? 0) |
        (fsConstants.O_CLOEXEC ?? 0),
      0o600,
    );
    validatePrivateFileMetadata(await handle.stat(), code);
    await handle.sync();
    await fsyncDirectory(dirname(path), code);
    return handle;
  } catch (error) {
    await handle?.close().catch(() => {});
    if (error instanceof OracleSubagentQueueError) throw error;
    if (error.code === "EEXIST") reject(code);
    reject(code);
  }
}

async function openedNamedIdentity(path, handle, code, { ctime = false } = {}) {
  try {
    const [opened, openedPrecise, named, namedPrecise] = await Promise.all([
      handle.stat(),
      handle.stat({ bigint: true }),
      lstat(path),
      lstat(path, { bigint: true }),
    ]);
    validatePrivateFileMetadata(opened, code);
    validatePrivateFileMetadata(named, code);
    if ((await realpath(path)) !== path) reject(code);
    const openedIdentity = {
      dev: openedPrecise.dev.toString(),
      ino: openedPrecise.ino.toString(),
      ...(ctime ? { ctime_ns: openedPrecise.ctimeNs.toString() } : {}),
    };
    const namedIdentity = {
      dev: namedPrecise.dev.toString(),
      ino: namedPrecise.ino.toString(),
      ...(ctime ? { ctime_ns: namedPrecise.ctimeNs.toString() } : {}),
    };
    if (!sameIdentity(openedIdentity, namedIdentity, { ctime })) reject(code);
    return Object.freeze(openedIdentity);
  } catch (error) {
    if (error instanceof OracleSubagentQueueError) throw error;
    reject(code);
  }
}

function normalizeConfig(rawConfig) {
  const config = exactObject(
    rawConfig,
    ["target_ids", "max_active", "max_depth", "lease_duration_ms"],
    [],
    "queue_config_invalid",
  );
  if (
    !Array.isArray(config.target_ids) ||
    config.target_ids.length < 1 ||
    config.target_ids.length > 64
  ) {
    reject("queue_config_invalid");
  }
  const targetIds = config.target_ids
    .map((value) =>
      safeIdentifier(value, TARGET_ID_PATTERN, "queue_config_invalid"),
    )
    .sort();
  if (new Set(targetIds).size !== targetIds.length) {
    reject("queue_config_invalid");
  }
  const maxActive = safeInteger(
    config.max_active,
    1,
    targetIds.length,
    "queue_config_invalid",
  );
  return deepFreeze({
    target_ids: targetIds,
    max_active: maxActive,
    max_depth: safeInteger(
      config.max_depth,
      1,
      10_000,
      "queue_config_invalid",
    ),
    lease_duration_ms: safeInteger(
      config.lease_duration_ms,
      1_000,
      86_400_000,
      "queue_config_invalid",
    ),
  });
}

function configHash(config) {
  return sha256(canonicalJson(config));
}

export function queueLayout(artifactRoot) {
  const root = absolutePath(artifactRoot, "artifact_root_invalid");
  const witnessDirectory = join(
    root,
    ".oracle-subagent-queue-witnesses",
  );
  return Object.freeze({
    artifact_root: root,
    generation_path: join(
      root,
      ".oracle-subagent-queue-generation.json",
    ),
    lock_path: join(root, ".oracle-subagent-queue.lock"),
    ledger_path: join(root, ".oracle-subagent-queue-ledger.ndjson"),
    head_path: join(root, ".oracle-subagent-queue-head.ndjson"),
    anchor_path: join(root, ".oracle-subagent-queue-anchor.ndjson"),
    witness_directory: witnessDirectory,
  });
}

function normalizeLockOptions(rawOptions = {}) {
  const options = exactObject(
    rawOptions,
    [],
    ["timeout_ms", "poll_ms", "hooks"],
    "queue_options_invalid",
  );
  const hooks = options.hooks ?? {};
  if (!isPlainObject(hooks)) reject("queue_options_invalid");
  for (const [key, value] of Object.entries(hooks)) {
    if (
      ![
        "after_ledger_fsync",
        "after_witness_fsync",
        "after_head_fsync",
        "after_anchor_fsync",
      ].includes(key) ||
      typeof value !== "function"
    ) {
      reject("queue_options_invalid");
    }
  }
  return {
    timeout_ms: safeInteger(
      options.timeout_ms ?? DEFAULT_LOCK_TIMEOUT_MS,
      0,
      MAX_LOCK_TIMEOUT_MS,
      "queue_options_invalid",
    ),
    poll_ms: safeInteger(
      options.poll_ms ?? DEFAULT_LOCK_POLL_MS,
      1,
      MAX_LOCK_POLL_MS,
      "queue_options_invalid",
    ),
    hooks,
  };
}

async function acquireQueueLock(layout, options, { create = false } = {}) {
  let handle;
  const flags =
    fsConstants.O_RDWR |
    (create ? fsConstants.O_CREAT | fsConstants.O_EXCL : 0) |
    (fsConstants.O_NOFOLLOW ?? 0) |
    (fsConstants.O_CLOEXEC ?? 0);
  try {
    handle = await open(layout.lock_path, flags, 0o600);
    const identity = await openedNamedIdentity(
      layout.lock_path,
      handle,
      "queue_lock_invalid",
      { ctime: true },
    );
    const helper = spawn(
      "/usr/bin/python3",
      [
        "-I",
        "-c",
        `
import fcntl
import sys
import time

deadline = time.monotonic() + int(sys.argv[1]) / 1000
poll = int(sys.argv[2]) / 1000
while True:
    try:
        fcntl.flock(3, fcntl.LOCK_EX | fcntl.LOCK_NB)
        raise SystemExit(0)
    except BlockingIOError:
        if time.monotonic() >= deadline:
            raise SystemExit(75)
        time.sleep(poll)
`,
        String(options.timeout_ms),
        String(options.poll_ms),
      ],
      {
        env: { PATH: "/usr/bin:/bin", LANG: "C", LC_ALL: "C" },
        stdio: ["ignore", "ignore", "pipe", handle.fd],
      },
    );
    let standardError = "";
    helper.stderr.setEncoding("utf8");
    helper.stderr.on("data", (chunk) => {
      if (standardError.length < 1024) standardError += chunk;
    });
    const code = await new Promise((resolvePromise, rejectPromise) => {
      helper.once("error", rejectPromise);
      helper.once("exit", resolvePromise);
    });
    if (code === 75) reject("queue_lock_timeout");
    if (code !== 0 || standardError) reject("queue_lock_failed");
    await openedNamedIdentity(
      layout.lock_path,
      handle,
      "queue_lock_replaced",
      { ctime: true },
    );
    return { handle, identity };
  } catch (error) {
    await handle?.close().catch(() => {});
    if (error instanceof OracleSubagentQueueError) throw error;
    reject(create ? "queue_lock_invalid" : "queue_lock_failed");
  }
}

async function assertQueueLock(layout, lock) {
  const identity = await openedNamedIdentity(
    layout.lock_path,
    lock.handle,
    "queue_lock_replaced",
    { ctime: true },
  );
  if (!sameIdentity(identity, lock.identity, { ctime: true })) {
    reject("queue_lock_replaced");
  }
}

async function releaseQueueLock(lock) {
  await lock.handle.close().catch(() => {});
}

function normalizeGeneration(raw) {
  const generation = exactObject(
    raw,
    [
      "schema",
      "generation_id",
      "artifact_root_dev",
      "artifact_root_ino",
      "generation_dev",
      "generation_ino",
      "lock_dev",
      "lock_ino",
      "lock_ctime_ns",
      "ledger_dev",
      "ledger_ino",
      "head_dev",
      "head_ino",
      "anchor_dev",
      "anchor_ino",
      "witness_directory_dev",
      "witness_directory_ino",
      "config",
      "config_hash",
      "generation_hash",
    ],
    [],
    "queue_generation_invalid",
  );
  if (generation.schema !== QUEUE_GENERATION_SCHEMA) {
    reject("queue_generation_invalid");
  }
  const normalized = {
    schema: QUEUE_GENERATION_SCHEMA,
    generation_id: safeIdentifier(
      generation.generation_id,
      UUID_PATTERN,
      "queue_generation_invalid",
    ),
    artifact_root_dev: safeIdentifier(
      generation.artifact_root_dev,
      DECIMAL_PATTERN,
      "queue_generation_invalid",
    ),
    artifact_root_ino: safeIdentifier(
      generation.artifact_root_ino,
      DECIMAL_PATTERN,
      "queue_generation_invalid",
    ),
    generation_dev: safeIdentifier(
      generation.generation_dev,
      DECIMAL_PATTERN,
      "queue_generation_invalid",
    ),
    generation_ino: safeIdentifier(
      generation.generation_ino,
      DECIMAL_PATTERN,
      "queue_generation_invalid",
    ),
    lock_dev: safeIdentifier(
      generation.lock_dev,
      DECIMAL_PATTERN,
      "queue_generation_invalid",
    ),
    lock_ino: safeIdentifier(
      generation.lock_ino,
      DECIMAL_PATTERN,
      "queue_generation_invalid",
    ),
    lock_ctime_ns: safeIdentifier(
      generation.lock_ctime_ns,
      DECIMAL_PATTERN,
      "queue_generation_invalid",
    ),
    ledger_dev: safeIdentifier(
      generation.ledger_dev,
      DECIMAL_PATTERN,
      "queue_generation_invalid",
    ),
    ledger_ino: safeIdentifier(
      generation.ledger_ino,
      DECIMAL_PATTERN,
      "queue_generation_invalid",
    ),
    head_dev: safeIdentifier(
      generation.head_dev,
      DECIMAL_PATTERN,
      "queue_generation_invalid",
    ),
    head_ino: safeIdentifier(
      generation.head_ino,
      DECIMAL_PATTERN,
      "queue_generation_invalid",
    ),
    anchor_dev: safeIdentifier(
      generation.anchor_dev,
      DECIMAL_PATTERN,
      "queue_generation_invalid",
    ),
    anchor_ino: safeIdentifier(
      generation.anchor_ino,
      DECIMAL_PATTERN,
      "queue_generation_invalid",
    ),
    witness_directory_dev: safeIdentifier(
      generation.witness_directory_dev,
      DECIMAL_PATTERN,
      "queue_generation_invalid",
    ),
    witness_directory_ino: safeIdentifier(
      generation.witness_directory_ino,
      DECIMAL_PATTERN,
      "queue_generation_invalid",
    ),
    config: normalizeConfig(generation.config),
    config_hash: safeIdentifier(
      generation.config_hash,
      SHA256_PATTERN,
      "queue_generation_invalid",
    ),
  };
  if (normalized.config_hash !== configHash(normalized.config)) {
    reject("queue_generation_invalid");
  }
  const expectedHash = hashRecord(normalized, "generation_hash");
  if (generation.generation_hash !== expectedHash) {
    reject("queue_generation_invalid");
  }
  return deepFreeze({ ...normalized, generation_hash: expectedHash });
}

async function readCanonicalFile(
  path,
  normalize,
  code,
  { missing = false, maximumBytes = 64 * 1024 } = {},
) {
  let handle;
  try {
    handle = await open(
      path,
      fsConstants.O_RDONLY |
        (fsConstants.O_NOFOLLOW ?? 0) |
        (fsConstants.O_CLOEXEC ?? 0),
    );
    await openedNamedIdentity(path, handle, code);
    const metadata = await handle.stat();
    if (metadata.size < 2 || metadata.size > maximumBytes) reject(code);
    const bytes = await handle.readFile();
    const text = bytes.toString("utf8");
    if (!text.endsWith("\n")) reject(code);
    const parsed = normalize(JSON.parse(text));
    if (`${canonicalJson(parsed)}\n` !== text) reject(code);
    await openedNamedIdentity(path, handle, code);
    return parsed;
  } catch (error) {
    if (missing && error.code === "ENOENT") return null;
    if (error instanceof OracleSubagentQueueError) throw error;
    reject(code);
  } finally {
    await handle?.close().catch(() => {});
  }
}

async function readGeneration(layout, { missing = false } = {}) {
  return readCanonicalFile(
    layout.generation_path,
    normalizeGeneration,
    "queue_generation_invalid",
    { missing, maximumBytes: 64 * 1024 },
  );
}

function normalizeEntry(raw) {
  const entry = exactObject(
    raw,
    [
      "run_id",
      "request_fingerprint",
      "worker_id",
      "enqueue_sequence",
      "enqueued_at_ms",
      "updated_at_ms",
      "status",
      "target_id",
      "lease_id",
      "fencing_token",
      "leased_at_ms",
      "lease_expires_at_ms",
      "terminal_at_ms",
    ],
    [],
    "queue_snapshot_invalid",
  );
  const normalized = {
    run_id: safeIdentifier(
      entry.run_id,
      RUN_ID_PATTERN,
      "queue_snapshot_invalid",
    ),
    request_fingerprint: safeIdentifier(
      entry.request_fingerprint,
      SHA256_PATTERN,
      "queue_snapshot_invalid",
    ),
    worker_id: safeIdentifier(
      entry.worker_id,
      WORKER_ID_PATTERN,
      "queue_snapshot_invalid",
    ),
    enqueue_sequence: safeInteger(
      entry.enqueue_sequence,
      1,
      Number.MAX_SAFE_INTEGER,
      "queue_snapshot_invalid",
    ),
    enqueued_at_ms: safeInteger(
      entry.enqueued_at_ms,
      0,
      Number.MAX_SAFE_INTEGER,
      "queue_snapshot_invalid",
    ),
    updated_at_ms: safeInteger(
      entry.updated_at_ms,
      entry.enqueued_at_ms,
      Number.MAX_SAFE_INTEGER,
      "queue_snapshot_invalid",
    ),
    status: entry.status,
    target_id: nullableIdentifier(
      entry.target_id,
      TARGET_ID_PATTERN,
      "queue_snapshot_invalid",
    ),
    lease_id: nullableIdentifier(
      entry.lease_id,
      UUID_PATTERN,
      "queue_snapshot_invalid",
    ),
    fencing_token: nullableInteger(
      entry.fencing_token,
      1,
      Number.MAX_SAFE_INTEGER,
      "queue_snapshot_invalid",
    ),
    leased_at_ms: nullableInteger(
      entry.leased_at_ms,
      0,
      Number.MAX_SAFE_INTEGER,
      "queue_snapshot_invalid",
    ),
    lease_expires_at_ms: nullableInteger(
      entry.lease_expires_at_ms,
      1,
      Number.MAX_SAFE_INTEGER,
      "queue_snapshot_invalid",
    ),
    terminal_at_ms: nullableInteger(
      entry.terminal_at_ms,
      0,
      Number.MAX_SAFE_INTEGER,
      "queue_snapshot_invalid",
    ),
  };
  if (!["queued", "leased", "released", "cancelled"].includes(entry.status)) {
    reject("queue_snapshot_invalid");
  }
  const leaseFields = [
    normalized.target_id,
    normalized.lease_id,
    normalized.fencing_token,
    normalized.leased_at_ms,
    normalized.lease_expires_at_ms,
  ];
  if (entry.status === "queued" && leaseFields.some((value) => value !== null)) {
    reject("queue_snapshot_invalid");
  }
  if (
    entry.status === "leased" &&
    (leaseFields.some((value) => value === null) ||
      normalized.terminal_at_ms !== null ||
      normalized.lease_expires_at_ms <= normalized.leased_at_ms)
  ) {
    reject("queue_snapshot_invalid");
  }
  if (
    ["released", "cancelled"].includes(entry.status) &&
    (normalized.terminal_at_ms === null ||
      normalized.terminal_at_ms !== normalized.updated_at_ms)
  ) {
    reject("queue_snapshot_invalid");
  }
  const hasNoLease = leaseFields.every((value) => value === null);
  const hasFullLease = leaseFields.every((value) => value !== null);
  if (
    entry.status === "released" &&
    (!hasFullLease ||
      normalized.lease_expires_at_ms <= normalized.leased_at_ms)
  ) {
    reject("queue_snapshot_invalid");
  }
  if (
    entry.status === "cancelled" &&
    (!hasNoLease && !hasFullLease)
  ) {
    reject("queue_snapshot_invalid");
  }
  if (
    entry.status === "cancelled" &&
    hasFullLease &&
    normalized.lease_expires_at_ms <= normalized.leased_at_ms
  ) {
    reject("queue_snapshot_invalid");
  }
  return normalized;
}

function validateStateInvariants(state, config) {
  if (state.entries.length > MAX_ENTRIES) reject("queue_snapshot_invalid");
  const runIds = new Set();
  const fingerprints = new Set();
  const enqueueSequences = new Set();
  const activeTargets = new Set();
  const leaseIds = new Set();
  const fencingTokens = new Set();
  let activeCount = 0;
  for (const entry of state.entries) {
    if (
      runIds.has(entry.run_id) ||
      fingerprints.has(entry.request_fingerprint) ||
      enqueueSequences.has(entry.enqueue_sequence)
    ) {
      reject("queue_snapshot_invalid");
    }
    runIds.add(entry.run_id);
    fingerprints.add(entry.request_fingerprint);
    enqueueSequences.add(entry.enqueue_sequence);
    if (entry.enqueue_sequence >= state.next_enqueue_sequence) {
      reject("queue_snapshot_invalid");
    }
    if (entry.lease_id !== null) {
      if (
        !config.target_ids.includes(entry.target_id) ||
        leaseIds.has(entry.lease_id) ||
        fencingTokens.has(entry.fencing_token) ||
        entry.fencing_token >= state.next_fencing_token
      ) {
        reject("queue_snapshot_invalid");
      }
      leaseIds.add(entry.lease_id);
      fencingTokens.add(entry.fencing_token);
    }
    if (entry.status === "leased") {
      activeCount += 1;
      if (
        activeTargets.has(entry.target_id)
      ) {
        reject("queue_snapshot_invalid");
      }
      activeTargets.add(entry.target_id);
    }
  }
  if (activeCount > config.max_active) reject("queue_snapshot_invalid");
}

function normalizeSnapshot(raw, generation) {
  const snapshot = exactObject(
    raw,
    [
      "schema",
      "generation_hash",
      "revision",
      "previous_snapshot_hash",
      "committed_at_ms",
      "next_enqueue_sequence",
      "next_fencing_token",
      "entries",
      "snapshot_hash",
    ],
    [],
    "queue_snapshot_invalid",
  );
  if (
    snapshot.schema !== QUEUE_SNAPSHOT_SCHEMA ||
    snapshot.generation_hash !== generation.generation_hash ||
    !Array.isArray(snapshot.entries)
  ) {
    reject("queue_snapshot_invalid");
  }
  const normalized = {
    schema: QUEUE_SNAPSHOT_SCHEMA,
    generation_hash: generation.generation_hash,
    revision: safeInteger(
      snapshot.revision,
      0,
      Number.MAX_SAFE_INTEGER,
      "queue_snapshot_invalid",
    ),
    previous_snapshot_hash:
      snapshot.previous_snapshot_hash === null
        ? null
        : safeIdentifier(
            snapshot.previous_snapshot_hash,
            SHA256_PATTERN,
            "queue_snapshot_invalid",
          ),
    committed_at_ms: safeInteger(
      snapshot.committed_at_ms,
      0,
      Number.MAX_SAFE_INTEGER,
      "queue_snapshot_invalid",
    ),
    next_enqueue_sequence: safeInteger(
      snapshot.next_enqueue_sequence,
      1,
      Number.MAX_SAFE_INTEGER,
      "queue_snapshot_invalid",
    ),
    next_fencing_token: safeInteger(
      snapshot.next_fencing_token,
      1,
      Number.MAX_SAFE_INTEGER,
      "queue_snapshot_invalid",
    ),
    entries: snapshot.entries.map(normalizeEntry).sort((left, right) =>
      left.run_id.localeCompare(right.run_id),
    ),
  };
  validateStateInvariants(normalized, generation.config);
  const expectedHash = hashRecord(normalized, "snapshot_hash");
  if (snapshot.snapshot_hash !== expectedHash) {
    reject("queue_snapshot_invalid");
  }
  return { ...normalized, snapshot_hash: expectedHash };
}

function normalizeWitness(raw, generation) {
  const witness = exactObject(
    raw,
    [
      "schema",
      "generation_hash",
      "revision",
      "snapshot_hash",
      "previous_witness_hash",
      "witness_hash",
    ],
    [],
    "queue_witness_invalid",
  );
  if (
    witness.schema !== QUEUE_WITNESS_SCHEMA ||
    witness.generation_hash !== generation.generation_hash
  ) {
    reject("queue_witness_invalid");
  }
  const normalized = {
    schema: QUEUE_WITNESS_SCHEMA,
    generation_hash: generation.generation_hash,
    revision: safeInteger(
      witness.revision,
      0,
      Number.MAX_SAFE_INTEGER,
      "queue_witness_invalid",
    ),
    snapshot_hash: safeIdentifier(
      witness.snapshot_hash,
      SHA256_PATTERN,
      "queue_witness_invalid",
    ),
    previous_witness_hash:
      witness.previous_witness_hash === null
        ? null
        : safeIdentifier(
            witness.previous_witness_hash,
            SHA256_PATTERN,
            "queue_witness_invalid",
          ),
  };
  const expectedHash = hashRecord(normalized, "witness_hash");
  if (witness.witness_hash !== expectedHash) {
    reject("queue_witness_invalid");
  }
  return { ...normalized, witness_hash: expectedHash };
}

function normalizeHead(raw, generation) {
  const head = exactObject(
    raw,
    [
      "schema",
      "generation_hash",
      "revision",
      "snapshot_hash",
      "ledger_bytes",
      "witness_hash",
      "witness_dev",
      "witness_ino",
      "witness_ctime_ns",
      "previous_head_hash",
      "head_hash",
    ],
    [],
    "queue_head_invalid",
  );
  if (
    head.schema !== QUEUE_HEAD_SCHEMA ||
    head.generation_hash !== generation.generation_hash
  ) {
    reject("queue_head_invalid");
  }
  const normalized = {
    schema: QUEUE_HEAD_SCHEMA,
    generation_hash: generation.generation_hash,
    revision: safeInteger(
      head.revision,
      0,
      Number.MAX_SAFE_INTEGER,
      "queue_head_invalid",
    ),
    snapshot_hash: safeIdentifier(
      head.snapshot_hash,
      SHA256_PATTERN,
      "queue_head_invalid",
    ),
    ledger_bytes: safeInteger(
      head.ledger_bytes,
      1,
      MAX_LEDGER_BYTES,
      "queue_head_invalid",
    ),
    witness_hash: safeIdentifier(
      head.witness_hash,
      SHA256_PATTERN,
      "queue_head_invalid",
    ),
    witness_dev: safeIdentifier(
      head.witness_dev,
      DECIMAL_PATTERN,
      "queue_head_invalid",
    ),
    witness_ino: safeIdentifier(
      head.witness_ino,
      DECIMAL_PATTERN,
      "queue_head_invalid",
    ),
    witness_ctime_ns: safeIdentifier(
      head.witness_ctime_ns,
      DECIMAL_PATTERN,
      "queue_head_invalid",
    ),
    previous_head_hash:
      head.previous_head_hash === null
        ? null
        : safeIdentifier(
            head.previous_head_hash,
            SHA256_PATTERN,
            "queue_head_invalid",
          ),
  };
  const expectedHash = hashRecord(normalized, "head_hash");
  if (head.head_hash !== expectedHash) reject("queue_head_invalid");
  return { ...normalized, head_hash: expectedHash };
}

function normalizeAnchor(raw, generation) {
  const anchor = exactObject(
    raw,
    [
      "schema",
      "generation_hash",
      "revision",
      "snapshot_hash",
      "head_hash",
      "ledger_bytes",
      "previous_anchor_hash",
      "anchor_hash",
    ],
    [],
    "queue_anchor_invalid",
  );
  if (
    anchor.schema !== QUEUE_ANCHOR_SCHEMA ||
    anchor.generation_hash !== generation.generation_hash
  ) {
    reject("queue_anchor_invalid");
  }
  const normalized = {
    schema: QUEUE_ANCHOR_SCHEMA,
    generation_hash: generation.generation_hash,
    revision: safeInteger(
      anchor.revision,
      0,
      Number.MAX_SAFE_INTEGER,
      "queue_anchor_invalid",
    ),
    snapshot_hash: safeIdentifier(
      anchor.snapshot_hash,
      SHA256_PATTERN,
      "queue_anchor_invalid",
    ),
    head_hash: safeIdentifier(
      anchor.head_hash,
      SHA256_PATTERN,
      "queue_anchor_invalid",
    ),
    ledger_bytes: safeInteger(
      anchor.ledger_bytes,
      1,
      MAX_LEDGER_BYTES,
      "queue_anchor_invalid",
    ),
    previous_anchor_hash:
      anchor.previous_anchor_hash === null
        ? null
        : safeIdentifier(
            anchor.previous_anchor_hash,
            SHA256_PATTERN,
            "queue_anchor_invalid",
          ),
  };
  const expectedHash = hashRecord(normalized, "anchor_hash");
  if (anchor.anchor_hash !== expectedHash) {
    reject("queue_anchor_invalid");
  }
  return { ...normalized, anchor_hash: expectedHash };
}

async function readNdjson(path, generation, kind) {
  const code =
    kind === "ledger"
      ? "queue_ledger_invalid"
      : kind === "head"
        ? "queue_head_invalid"
        : "queue_anchor_invalid";
  const maximumBytes =
    kind === "ledger"
      ? MAX_LEDGER_BYTES
      : kind === "head"
        ? MAX_HEAD_BYTES
        : MAX_ANCHOR_BYTES;
  let handle;
  try {
    handle = await open(
      path,
      fsConstants.O_RDONLY |
        (fsConstants.O_NOFOLLOW ?? 0) |
        (fsConstants.O_CLOEXEC ?? 0),
    );
    await openedNamedIdentity(path, handle, code);
    const metadata = await handle.stat();
    if (metadata.size < 2 || metadata.size > maximumBytes) reject(code);
    const bytes = await handle.readFile();
    if (bytes.at(-1) !== 0x0a) reject(code);
    const text = bytes.toString("utf8");
    const lines = text.slice(0, -1).split("\n");
    if (lines.length < 1 || lines.length > MAX_RECORDS) reject(code);
    const records = [];
    let byteEnd = 0;
    for (const line of lines) {
      if (
        line.length < 2 ||
        Buffer.byteLength(line) >
          (kind === "ledger"
            ? MAX_SNAPSHOT_BYTES
            : kind === "head"
              ? MAX_HEAD_ENTRY_BYTES
              : MAX_ANCHOR_ENTRY_BYTES)
      ) {
        reject(code);
      }
      let parsed;
      try {
        parsed = JSON.parse(line);
      } catch {
        reject(code);
      }
      const normalized =
        kind === "ledger"
          ? normalizeSnapshot(parsed, generation)
          : kind === "head"
            ? normalizeHead(parsed, generation)
            : normalizeAnchor(parsed, generation);
      if (canonicalJson(normalized) !== line) reject(code);
      byteEnd += Buffer.byteLength(`${line}\n`);
      records.push({ record: normalized, byte_end: byteEnd });
    }
    await openedNamedIdentity(path, handle, code);
    return records;
  } catch (error) {
    if (error instanceof OracleSubagentQueueError) throw error;
    reject(code);
  } finally {
    await handle?.close().catch(() => {});
  }
}

function witnessName(revision) {
  return `${String(revision).padStart(16, "0")}.json`;
}

async function readWitness(layout, generation, revision, { missing = false } = {}) {
  const path = join(layout.witness_directory, witnessName(revision));
  const witness = await readCanonicalFile(
    path,
    (raw) => normalizeWitness(raw, generation),
    "queue_witness_invalid",
    { missing, maximumBytes: 4_096 },
  );
  if (witness && witness.revision !== revision) {
    reject("queue_witness_invalid");
  }
  return witness;
}

async function witnessIdentity(layout, revision) {
  return privateFileIdentity(
    join(layout.witness_directory, witnessName(revision)),
    "queue_witness_invalid",
    { ctime: true },
  );
}

async function appendCanonicalRecord(path, record, expectedIdentity, code) {
  let handle;
  try {
    handle = await open(
      path,
      fsConstants.O_WRONLY |
        fsConstants.O_APPEND |
        (fsConstants.O_NOFOLLOW ?? 0) |
        (fsConstants.O_CLOEXEC ?? 0),
    );
    const before = await openedNamedIdentity(path, handle, code);
    if (!sameIdentity(before, expectedIdentity)) reject(code);
    await handle.writeFile(`${canonicalJson(record)}\n`);
    await handle.sync();
    const after = await openedNamedIdentity(path, handle, code);
    if (!sameIdentity(after, expectedIdentity)) reject(code);
  } catch (error) {
    if (error instanceof OracleSubagentQueueError) throw error;
    reject(code);
  } finally {
    await handle?.close().catch(() => {});
  }
}

async function createWitness(layout, generation, snapshot, previousWitnessHash) {
  const witnessBase = {
    schema: QUEUE_WITNESS_SCHEMA,
    generation_hash: generation.generation_hash,
    revision: snapshot.revision,
    snapshot_hash: snapshot.snapshot_hash,
    previous_witness_hash: previousWitnessHash,
  };
  const witness = {
    ...witnessBase,
    witness_hash: hashRecord(witnessBase, "witness_hash"),
  };
  const path = join(layout.witness_directory, witnessName(snapshot.revision));
  let handle;
  try {
    handle = await open(
      path,
      fsConstants.O_CREAT |
        fsConstants.O_EXCL |
        fsConstants.O_WRONLY |
        (fsConstants.O_NOFOLLOW ?? 0) |
        (fsConstants.O_CLOEXEC ?? 0),
      0o600,
    );
    await handle.writeFile(`${canonicalJson(witness)}\n`);
    await handle.sync();
    await handle.close();
    handle = undefined;
    await fsyncDirectory(layout.witness_directory);
    const reread = await readWitness(
      layout,
      generation,
      snapshot.revision,
    );
    if (canonicalJson(reread) !== canonicalJson(witness)) {
      reject("queue_witness_invalid");
    }
    return {
      witness,
      identity: await witnessIdentity(layout, snapshot.revision),
    };
  } catch (error) {
    await handle?.close().catch(() => {});
    if (error instanceof OracleSubagentQueueError) throw error;
    if (error.code === "EEXIST") reject("queue_witness_conflict");
    reject("queue_witness_invalid");
  }
}

function headFrom(snapshot, ledgerBytes, witness, identity, previousHeadHash) {
  const base = {
    schema: QUEUE_HEAD_SCHEMA,
    generation_hash: snapshot.generation_hash,
    revision: snapshot.revision,
    snapshot_hash: snapshot.snapshot_hash,
    ledger_bytes: ledgerBytes,
    witness_hash: witness.witness_hash,
    witness_dev: identity.dev,
    witness_ino: identity.ino,
    witness_ctime_ns: identity.ctime_ns,
    previous_head_hash: previousHeadHash,
  };
  return { ...base, head_hash: hashRecord(base, "head_hash") };
}

function anchorFrom(snapshot, head, previousAnchorHash) {
  const base = {
    schema: QUEUE_ANCHOR_SCHEMA,
    generation_hash: snapshot.generation_hash,
    revision: snapshot.revision,
    snapshot_hash: snapshot.snapshot_hash,
    head_hash: head.head_hash,
    ledger_bytes: head.ledger_bytes,
    previous_anchor_hash: previousAnchorHash,
  };
  return { ...base, anchor_hash: hashRecord(base, "anchor_hash") };
}

async function validateStoreIdentities(layout, generation) {
  const [
    rootIdentity,
    generationIdentity,
    lockIdentity,
    ledgerIdentity,
    headIdentity,
    anchorIdentity,
    witnessDirectoryIdentity,
  ] = await Promise.all([
    privateDirectoryIdentity(layout.artifact_root, "artifact_root_invalid"),
    privateFileIdentity(
      layout.generation_path,
      "queue_generation_invalid",
    ),
    privateFileIdentity(layout.lock_path, "queue_lock_invalid", {
      ctime: true,
    }),
    privateFileIdentity(layout.ledger_path, "queue_ledger_invalid"),
    privateFileIdentity(layout.head_path, "queue_head_invalid"),
    privateFileIdentity(layout.anchor_path, "queue_anchor_invalid"),
    privateDirectoryIdentity(
      layout.witness_directory,
      "queue_witness_directory_invalid",
    ),
  ]);
  if (
    rootIdentity.dev !== generation.artifact_root_dev ||
    rootIdentity.ino !== generation.artifact_root_ino ||
    generationIdentity.dev !== generation.generation_dev ||
    generationIdentity.ino !== generation.generation_ino ||
    lockIdentity.dev !== generation.lock_dev ||
    lockIdentity.ino !== generation.lock_ino ||
    lockIdentity.ctime_ns !== generation.lock_ctime_ns ||
    ledgerIdentity.dev !== generation.ledger_dev ||
    ledgerIdentity.ino !== generation.ledger_ino ||
    headIdentity.dev !== generation.head_dev ||
    headIdentity.ino !== generation.head_ino ||
    anchorIdentity.dev !== generation.anchor_dev ||
    anchorIdentity.ino !== generation.anchor_ino ||
    witnessDirectoryIdentity.dev !== generation.witness_directory_dev ||
    witnessDirectoryIdentity.ino !== generation.witness_directory_ino
  ) {
    reject("queue_store_replaced");
  }
  return { ledgerIdentity, headIdentity, anchorIdentity };
}

async function validateWitnessSet(
  layout,
  generation,
  snapshots,
  heads,
  { allowMissingTerminal = false } = {},
) {
  let names;
  try {
    names = (await readdir(layout.witness_directory)).sort();
  } catch {
    reject("queue_witness_directory_invalid");
  }
  const expectedFull = snapshots.map(({ record }) =>
    witnessName(record.revision),
  );
  const expectedWithoutTerminal = expectedFull.slice(0, -1);
  const terminalMayBeMissing =
    allowMissingTerminal &&
    names.length === expectedWithoutTerminal.length &&
    names.every((name, index) => name === expectedWithoutTerminal[index]);
  if (
    !terminalMayBeMissing &&
    (names.length !== expectedFull.length ||
      names.some((name, index) => name !== expectedFull[index]))
  ) {
    reject("queue_witness_set_invalid");
  }
  const witnesses = [];
  for (let index = 0; index < names.length; index += 1) {
    const snapshot = snapshots[index].record;
    const witness = await readWitness(layout, generation, snapshot.revision);
    if (
      witness.snapshot_hash !== snapshot.snapshot_hash ||
      witness.previous_witness_hash !==
        (index === 0 ? null : witnesses[index - 1].witness_hash)
    ) {
      reject("queue_witness_invalid");
    }
    const identity = await witnessIdentity(layout, snapshot.revision);
    if (index < heads.length) {
      const head = heads[index].record;
      if (
        head.witness_hash !== witness.witness_hash ||
        head.witness_dev !== identity.dev ||
        head.witness_ino !== identity.ino ||
        head.witness_ctime_ns !== identity.ctime_ns
      ) {
        reject("queue_witness_invalid");
      }
    }
    witnesses.push(witness);
  }
  return { witnesses, terminalMayBeMissing };
}

function validateChains(snapshots, heads) {
  if (heads.length > snapshots.length) {
    reject("queue_commit_incomplete");
  }
  for (let index = 0; index < snapshots.length; index += 1) {
    const snapshot = snapshots[index];
    if (
      snapshot.record.revision !== index ||
      snapshot.record.previous_snapshot_hash !==
        (index === 0 ? null : snapshots[index - 1].record.snapshot_hash)
    ) {
      reject("queue_ledger_invalid");
    }
  }
  for (let index = 0; index < heads.length; index += 1) {
    const head = heads[index];
    const snapshot = snapshots[index];
    if (
      head.record.revision !== index ||
      head.record.snapshot_hash !== snapshot.record.snapshot_hash ||
      head.record.ledger_bytes !== snapshot.byte_end ||
      head.record.previous_head_hash !==
        (index === 0 ? null : heads[index - 1].record.head_hash)
    ) {
      reject("queue_head_invalid");
    }
  }
}

function validateAnchorPrefix(snapshots, heads, anchors, { exact = false } = {}) {
  if (
    anchors.length > heads.length ||
    (exact && anchors.length !== heads.length)
  ) {
    reject("queue_anchor_invalid");
  }
  for (let index = 0; index < anchors.length; index += 1) {
    const anchor = anchors[index].record;
    const snapshot = snapshots[index].record;
    const head = heads[index].record;
    if (
      anchor.revision !== index ||
      anchor.snapshot_hash !== snapshot.snapshot_hash ||
      anchor.head_hash !== head.head_hash ||
      anchor.ledger_bytes !== head.ledger_bytes ||
      anchor.previous_anchor_hash !==
        (index === 0 ? null : anchors[index - 1].record.anchor_hash)
    ) {
      reject("queue_anchor_invalid");
    }
  }
}

async function repairTerminalCommit(
  layout,
  generation,
  snapshots,
  heads,
  identities,
  options,
) {
  const snapshot = snapshots.at(-1);
  const previousWitness =
    snapshot.record.revision === 0
      ? null
      : await readWitness(
          layout,
          generation,
          snapshot.record.revision - 1,
        );
  let witness = await readWitness(
    layout,
    generation,
    snapshot.record.revision,
    { missing: true },
  );
  let identity;
  if (!witness) {
    const created = await createWitness(
      layout,
      generation,
      snapshot.record,
      previousWitness?.witness_hash ?? null,
    );
    witness = created.witness;
    identity = created.identity;
    await options.hooks.after_witness_fsync?.();
  } else {
    if (
      witness.snapshot_hash !== snapshot.record.snapshot_hash ||
      witness.previous_witness_hash !==
        (previousWitness?.witness_hash ?? null)
    ) {
      reject("queue_witness_invalid");
    }
    identity = await witnessIdentity(layout, snapshot.record.revision);
  }
  const head = headFrom(
    snapshot.record,
    snapshot.byte_end,
    witness,
    identity,
    heads.at(-1)?.record.head_hash ?? null,
  );
  await appendCanonicalRecord(
    layout.head_path,
    head,
    identities.headIdentity,
    "queue_head_write_failed",
  );
  await options.hooks.after_head_fsync?.();
  await fsyncDirectory(layout.artifact_root);
}

async function repairTerminalAnchor(
  layout,
  snapshots,
  heads,
  anchors,
  identities,
  options,
) {
  const snapshot = snapshots.at(-1).record;
  const head = heads.at(-1).record;
  const anchor = anchorFrom(
    snapshot,
    head,
    anchors.at(-1)?.record.anchor_hash ?? null,
  );
  await appendCanonicalRecord(
    layout.anchor_path,
    anchor,
    identities.anchorIdentity,
    "queue_anchor_write_failed",
  );
  await options.hooks.after_anchor_fsync?.();
  await fsyncDirectory(layout.artifact_root);
}

async function loadStore(layout, generation, options, { repair = true } = {}) {
  const identities = await validateStoreIdentities(layout, generation);
  let snapshots = await readNdjson(
    layout.ledger_path,
    generation,
    "ledger",
  );
  let heads = await readNdjson(layout.head_path, generation, "head");
  let anchors = await readNdjson(
    layout.anchor_path,
    generation,
    "anchor",
  );
  validateChains(snapshots, heads);
  validateAnchorPrefix(snapshots, heads, anchors);
  const ledgerLag = snapshots.length - heads.length;
  const anchorLag = heads.length - anchors.length;
  if (
    ledgerLag < 0 ||
    ledgerLag > 1 ||
    anchorLag < 0 ||
    anchorLag > 1 ||
    (ledgerLag === 1 && anchorLag === 1)
  ) {
    reject("queue_commit_incomplete");
  }
  if (ledgerLag === 1) {
    await validateWitnessSet(layout, generation, snapshots, heads, {
      allowMissingTerminal: true,
    });
  } else {
    await validateWitnessSet(layout, generation, snapshots, heads);
  }
  if (!repair && (ledgerLag === 1 || anchorLag === 1)) {
    const committedIndex = anchors.length - 1;
    if (committedIndex < 0) reject("queue_commit_incomplete");
    await validateStoreIdentities(layout, generation);
    return {
      generation,
      state: snapshots[committedIndex].record,
      identities,
      ledger_bytes: snapshots[committedIndex].byte_end,
      head_bytes: heads[committedIndex].byte_end,
      anchor_bytes: anchors[committedIndex].byte_end,
      last_head: heads[committedIndex].record,
      last_anchor: anchors[committedIndex].record,
    };
  }
  if (ledgerLag === 1) {
    await repairTerminalCommit(
      layout,
      generation,
      snapshots,
      heads,
      identities,
      options,
    );
    heads = await readNdjson(layout.head_path, generation, "head");
    validateChains(snapshots, heads);
    validateAnchorPrefix(snapshots, heads, anchors);
  }
  if (snapshots.length !== heads.length) {
    reject("queue_commit_incomplete");
  }
  await validateWitnessSet(layout, generation, snapshots, heads);
  if (heads.length === anchors.length + 1) {
    await repairTerminalAnchor(
      layout,
      snapshots,
      heads,
      anchors,
      identities,
      options,
    );
    anchors = await readNdjson(
      layout.anchor_path,
      generation,
      "anchor",
    );
  }
  validateAnchorPrefix(snapshots, heads, anchors, { exact: true });
  await validateStoreIdentities(layout, generation);
  return {
    generation,
    state: snapshots.at(-1).record,
    identities,
    ledger_bytes: snapshots.at(-1).byte_end,
    head_bytes: heads.at(-1).byte_end,
    anchor_bytes: anchors.at(-1).byte_end,
    last_head: heads.at(-1).record,
    last_anchor: anchors.at(-1).record,
  };
}

async function pathExists(path) {
  try {
    await lstat(path);
    return true;
  } catch (error) {
    if (error.code === "ENOENT") return false;
    reject("queue_bootstrap_invalid");
  }
}

async function secureUuid(code) {
  try {
    const value = randomUUID();
    if (!UUID_PATTERN.test(value)) reject(code);
    return value;
  } catch (error) {
    if (error instanceof OracleSubagentQueueError) throw error;
    reject(code);
  }
}

async function initializeStore(layout, config, lock, options) {
  const existing = await Promise.all([
    pathExists(layout.generation_path),
    pathExists(layout.ledger_path),
    pathExists(layout.head_path),
    pathExists(layout.anchor_path),
    pathExists(layout.witness_directory),
  ]);
  if (existing.some(Boolean)) reject("queue_bootstrap_incomplete");
  const rootIdentity = await privateDirectoryIdentity(
    layout.artifact_root,
    "artifact_root_invalid",
  );
  let generationHandle;
  let ledgerHandle;
  let headHandle;
  let anchorHandle;
  try {
    generationHandle = await createPrivateFile(
      layout.generation_path,
      "queue_generation_invalid",
    );
    ledgerHandle = await createPrivateFile(
      layout.ledger_path,
      "queue_ledger_invalid",
    );
    headHandle = await createPrivateFile(
      layout.head_path,
      "queue_head_invalid",
    );
    anchorHandle = await createPrivateFile(
      layout.anchor_path,
      "queue_anchor_invalid",
    );
    try {
      await mkdir(layout.witness_directory, { mode: 0o700 });
    } catch {
      reject("queue_witness_directory_invalid");
    }
    await fsyncDirectory(layout.artifact_root);
    const [
      generationIdentity,
      ledgerIdentity,
      headIdentity,
      anchorIdentity,
      witnessDirectoryIdentity,
    ] = await Promise.all([
      openedNamedIdentity(
        layout.generation_path,
        generationHandle,
        "queue_generation_invalid",
      ),
      openedNamedIdentity(
        layout.ledger_path,
        ledgerHandle,
        "queue_ledger_invalid",
      ),
      openedNamedIdentity(
        layout.head_path,
        headHandle,
        "queue_head_invalid",
      ),
      openedNamedIdentity(
        layout.anchor_path,
        anchorHandle,
        "queue_anchor_invalid",
      ),
      privateDirectoryIdentity(
        layout.witness_directory,
        "queue_witness_directory_invalid",
      ),
    ]);
    const generationBase = {
      schema: QUEUE_GENERATION_SCHEMA,
      generation_id: await secureUuid("queue_generation_invalid"),
      artifact_root_dev: rootIdentity.dev,
      artifact_root_ino: rootIdentity.ino,
      generation_dev: generationIdentity.dev,
      generation_ino: generationIdentity.ino,
      lock_dev: lock.identity.dev,
      lock_ino: lock.identity.ino,
      lock_ctime_ns: lock.identity.ctime_ns,
      ledger_dev: ledgerIdentity.dev,
      ledger_ino: ledgerIdentity.ino,
      head_dev: headIdentity.dev,
      head_ino: headIdentity.ino,
      anchor_dev: anchorIdentity.dev,
      anchor_ino: anchorIdentity.ino,
      witness_directory_dev: witnessDirectoryIdentity.dev,
      witness_directory_ino: witnessDirectoryIdentity.ino,
      config,
      config_hash: configHash(config),
    };
    const generation = {
      ...generationBase,
      generation_hash: hashRecord(generationBase, "generation_hash"),
    };
    const initialBase = {
      schema: QUEUE_SNAPSHOT_SCHEMA,
      generation_hash: generation.generation_hash,
      revision: 0,
      previous_snapshot_hash: null,
      committed_at_ms: 0,
      next_enqueue_sequence: 1,
      next_fencing_token: 1,
      entries: [],
    };
    const initial = {
      ...initialBase,
      snapshot_hash: hashRecord(initialBase, "snapshot_hash"),
    };
    await ledgerHandle.writeFile(`${canonicalJson(initial)}\n`);
    await ledgerHandle.sync();
    await options.hooks.after_ledger_fsync?.();
    const created = await createWitness(
      layout,
      generation,
      initial,
      null,
    );
    await options.hooks.after_witness_fsync?.();
    const initialBytes = Buffer.byteLength(`${canonicalJson(initial)}\n`);
    const head = headFrom(
      initial,
      initialBytes,
      created.witness,
      created.identity,
      null,
    );
    await headHandle.writeFile(`${canonicalJson(head)}\n`);
    await headHandle.sync();
    await options.hooks.after_head_fsync?.();
    const anchor = anchorFrom(initial, head, null);
    await anchorHandle.writeFile(`${canonicalJson(anchor)}\n`);
    await anchorHandle.sync();
    await options.hooks.after_anchor_fsync?.();
    await generationHandle.writeFile(`${canonicalJson(generation)}\n`);
    await generationHandle.sync();
    await fsyncDirectory(layout.artifact_root);
    return generation;
  } catch (error) {
    if (error instanceof OracleSubagentQueueError) throw error;
    reject("queue_bootstrap_invalid");
  } finally {
    await generationHandle?.close().catch(() => {});
    await ledgerHandle?.close().catch(() => {});
    await headHandle?.close().catch(() => {});
    await anchorHandle?.close().catch(() => {});
  }
}

async function withStore(
  artifactRoot,
  config,
  rawOptions,
  callback,
  { repair = true } = {},
) {
  const layout = queueLayout(artifactRoot);
  const options = normalizeLockOptions(rawOptions);
  const normalizedConfig = config ? normalizeConfig(config) : null;
  await privateDirectoryIdentity(layout.artifact_root, "artifact_root_invalid");
  let lock;
  if (normalizedConfig) {
    let createdLock = false;
    try {
      lock = await acquireQueueLock(layout, options, { create: true });
      createdLock = true;
    } catch (error) {
      if (error.code !== "queue_lock_invalid") throw error;
      lock = await acquireQueueLock(layout, options);
    }
    if (createdLock) {
      try {
        await fsyncDirectory(layout.artifact_root);
      } catch (error) {
        await releaseQueueLock(lock);
        throw error;
      }
    }
  } else {
    lock = await acquireQueueLock(layout, options);
  }
  try {
    await assertQueueLock(layout, lock);
    let generation = await readGeneration(layout, {
      missing: normalizedConfig !== null,
    });
    if (!generation) {
      generation = await initializeStore(
        layout,
        normalizedConfig,
        lock,
        options,
      );
    }
    if (
      normalizedConfig &&
      canonicalJson(generation.config) !== canonicalJson(normalizedConfig)
    ) {
      reject("queue_config_mismatch");
    }
    const store = await loadStore(layout, generation, options, {
      repair,
    });
    await assertQueueLock(layout, lock);
    const result = await callback({
      layout,
      options,
      generation,
      store,
      assertStable: () => assertQueueLock(layout, lock),
    });
    await assertQueueLock(layout, lock);
    await validateStoreIdentities(layout, generation);
    return result;
  } finally {
    await releaseQueueLock(lock);
  }
}

function snapshotFromState(state, previous, nowMs) {
  const base = {
    schema: QUEUE_SNAPSHOT_SCHEMA,
    generation_hash: previous.generation_hash,
    revision: previous.revision + 1,
    previous_snapshot_hash: previous.snapshot_hash,
    committed_at_ms: nowMs,
    next_enqueue_sequence: state.next_enqueue_sequence,
    next_fencing_token: state.next_fencing_token,
    entries: state.entries
      .map((entry) => structuredClone(entry))
      .sort((left, right) => left.run_id.localeCompare(right.run_id)),
  };
  return { ...base, snapshot_hash: hashRecord(base, "snapshot_hash") };
}

async function commitState(context, state, nowMs) {
  if (nowMs < context.store.state.committed_at_ms) {
    reject("queue_clock_regressed");
  }
  validateStateInvariants(state, context.generation.config);
  const next = snapshotFromState(state, context.store.state, nowMs);
  const line = `${canonicalJson(next)}\n`;
  const lineBytes = Buffer.byteLength(line);
  if (lineBytes > MAX_SNAPSHOT_BYTES) {
    reject("queue_state_too_large");
  }
  if (
    next.revision >= MAX_RECORDS ||
    context.store.ledger_bytes + lineBytes > MAX_LEDGER_BYTES ||
    context.store.head_bytes + MAX_HEAD_RECORD_BYTES > MAX_HEAD_BYTES ||
    context.store.anchor_bytes + MAX_ANCHOR_RECORD_BYTES >
      MAX_ANCHOR_BYTES
  ) {
    reject("queue_history_full");
  }
  await context.assertStable();
  await appendCanonicalRecord(
    context.layout.ledger_path,
    next,
    context.store.identities.ledgerIdentity,
    "queue_ledger_write_failed",
  );
  await context.options.hooks.after_ledger_fsync?.();
  const previousWitness = await readWitness(
    context.layout,
    context.generation,
    context.store.state.revision,
  );
  const created = await createWitness(
    context.layout,
    context.generation,
    next,
    previousWitness.witness_hash,
  );
  await context.options.hooks.after_witness_fsync?.();
  const head = headFrom(
    next,
    context.store.ledger_bytes + lineBytes,
    created.witness,
    created.identity,
    context.store.last_head.head_hash,
  );
  await appendCanonicalRecord(
    context.layout.head_path,
    head,
    context.store.identities.headIdentity,
    "queue_head_write_failed",
  );
  await context.options.hooks.after_head_fsync?.();
  const anchor = anchorFrom(
    next,
    head,
    context.store.last_anchor.anchor_hash,
  );
  await appendCanonicalRecord(
    context.layout.anchor_path,
    anchor,
    context.store.identities.anchorIdentity,
    "queue_anchor_write_failed",
  );
  await context.options.hooks.after_anchor_fsync?.();
  await fsyncDirectory(context.layout.artifact_root);
  await context.assertStable();
  const reread = await loadStore(
    context.layout,
    context.generation,
    context.options,
  );
  if (reread.state.snapshot_hash !== next.snapshot_hash) {
    reject("queue_commit_unstable");
  }
  context.store = reread;
  return reread.state;
}

function normalizeNow(value, code = "queue_request_invalid") {
  return safeInteger(value, 0, Number.MAX_SAFE_INTEGER, code);
}

function normalizeClaim(raw) {
  const claim = exactObject(
    raw,
    ["run_id", "request_fingerprint", "worker_id", "now_ms"],
    [],
    "queue_request_invalid",
  );
  return {
    run_id: safeIdentifier(
      claim.run_id,
      RUN_ID_PATTERN,
      "queue_request_invalid",
    ),
    request_fingerprint: safeIdentifier(
      claim.request_fingerprint,
      SHA256_PATTERN,
      "queue_request_invalid",
    ),
    worker_id: safeIdentifier(
      claim.worker_id,
      WORKER_ID_PATTERN,
      "queue_request_invalid",
    ),
    now_ms: normalizeNow(claim.now_ms),
  };
}

function normalizeLeaseOperation(raw, { outcome = false } = {}) {
  const required = [
    "run_id",
    "worker_id",
    "lease_id",
    "fencing_token",
    "now_ms",
  ];
  if (outcome) required.push("outcome");
  const operation = exactObject(
    raw,
    required,
    [],
    "queue_lease_request_invalid",
  );
  if (outcome && operation.outcome !== "released") {
    reject("queue_lease_request_invalid");
  }
  return {
    run_id: safeIdentifier(
      operation.run_id,
      RUN_ID_PATTERN,
      "queue_lease_request_invalid",
    ),
    worker_id: safeIdentifier(
      operation.worker_id,
      WORKER_ID_PATTERN,
      "queue_lease_request_invalid",
    ),
    lease_id: safeIdentifier(
      operation.lease_id,
      UUID_PATTERN,
      "queue_lease_request_invalid",
    ),
    fencing_token: safeInteger(
      operation.fencing_token,
      1,
      Number.MAX_SAFE_INTEGER,
      "queue_lease_request_invalid",
    ),
    now_ms: normalizeNow(operation.now_ms, "queue_lease_request_invalid"),
    ...(outcome ? { outcome: "released" } : {}),
  };
}

function normalizeCancel(raw) {
  const cancel = exactObject(
    raw,
    ["run_id", "worker_id", "now_ms"],
    ["lease_id", "fencing_token"],
    "queue_cancel_request_invalid",
  );
  const leaseId =
    cancel.lease_id === undefined
      ? null
      : safeIdentifier(
          cancel.lease_id,
          UUID_PATTERN,
          "queue_cancel_request_invalid",
        );
  const fencingToken =
    cancel.fencing_token === undefined
      ? null
      : safeInteger(
          cancel.fencing_token,
          1,
          Number.MAX_SAFE_INTEGER,
          "queue_cancel_request_invalid",
        );
  if ((leaseId === null) !== (fencingToken === null)) {
    reject("queue_cancel_request_invalid");
  }
  return {
    run_id: safeIdentifier(
      cancel.run_id,
      RUN_ID_PATTERN,
      "queue_cancel_request_invalid",
    ),
    worker_id: safeIdentifier(
      cancel.worker_id,
      WORKER_ID_PATTERN,
      "queue_cancel_request_invalid",
    ),
    now_ms: normalizeNow(cancel.now_ms, "queue_cancel_request_invalid"),
    lease_id: leaseId,
    fencing_token: fencingToken,
  };
}

function mutableState(snapshot) {
  return {
    next_enqueue_sequence: snapshot.next_enqueue_sequence,
    next_fencing_token: snapshot.next_fencing_token,
    entries: snapshot.entries.map((entry) => structuredClone(entry)),
  };
}

function takeEnqueueSequence(state) {
  const sequence = state.next_enqueue_sequence;
  const next = sequence + 1;
  if (!Number.isSafeInteger(next)) {
    reject("queue_sequence_exhausted");
  }
  state.next_enqueue_sequence = next;
  return sequence;
}

function fifoEntries(entries) {
  return entries
    .filter((entry) => entry.status === "queued")
    .sort(
      (left, right) =>
        left.enqueue_sequence - right.enqueue_sequence ||
        left.run_id.localeCompare(right.run_id),
    );
}

function projectExpired(state, nowMs) {
  const expired = state.entries
    .filter(
      (entry) =>
        entry.status === "leased" &&
        entry.lease_expires_at_ms <= nowMs,
    )
    .sort(
      (left, right) =>
        left.enqueue_sequence - right.enqueue_sequence ||
        left.run_id.localeCompare(right.run_id),
    );
  for (const entry of expired) {
    entry.status = "queued";
    entry.enqueue_sequence = takeEnqueueSequence(state);
    entry.target_id = null;
    entry.lease_id = null;
    entry.fencing_token = null;
    entry.leased_at_ms = null;
    entry.lease_expires_at_ms = null;
    entry.terminal_at_ms = null;
    entry.updated_at_ms = nowMs;
  }
  return expired.length > 0;
}

function leaseExpiry(nowMs, durationMs) {
  const expiresAt = nowMs + durationMs;
  if (!Number.isSafeInteger(expiresAt) || expiresAt <= nowMs) {
    reject("queue_clock_exhausted");
  }
  return expiresAt;
}

async function scheduleQueued(state, config, nowMs) {
  const active = state.entries.filter((entry) => entry.status === "leased");
  const activeTargets = new Set(active.map((entry) => entry.target_id));
  const freeTargets = config.target_ids.filter(
    (targetId) => !activeTargets.has(targetId),
  );
  let capacity = Math.min(
    config.max_active - active.length,
    freeTargets.length,
  );
  let changed = false;
  for (const entry of fifoEntries(state.entries)) {
    if (capacity <= 0) break;
    const targetId = freeTargets.shift();
    let leaseId;
    try {
      leaseId = randomUUID();
    } catch {
      reject("queue_lease_id_failed");
    }
    if (!UUID_PATTERN.test(leaseId)) reject("queue_lease_id_failed");
    const fencingToken = state.next_fencing_token;
    state.next_fencing_token += 1;
    if (!Number.isSafeInteger(state.next_fencing_token)) {
      reject("queue_fencing_exhausted");
    }
    entry.status = "leased";
    entry.target_id = targetId;
    entry.lease_id = leaseId;
    entry.fencing_token = fencingToken;
    entry.leased_at_ms = nowMs;
    entry.lease_expires_at_ms = leaseExpiry(
      nowMs,
      config.lease_duration_ms,
    );
    entry.terminal_at_ms = null;
    entry.updated_at_ms = nowMs;
    capacity -= 1;
    changed = true;
  }
  return changed;
}

function queuePosition(entries, runId) {
  const queued = fifoEntries(entries);
  const index = queued.findIndex((entry) => entry.run_id === runId);
  return index === -1 ? null : index + 1;
}

function publicResult(entry, entries, outcome, revision) {
  const queueDepth = entries.filter(
    (candidate) => candidate.status === "queued",
  ).length;
  const activeCount = entries.filter(
    (candidate) => candidate.status === "leased",
  ).length;
  if (!entry) {
    return deepFreeze({
      schema: QUEUE_RESULT_SCHEMA,
      outcome,
      status: "missing",
      run_id: null,
      request_fingerprint: null,
      queue_position: null,
      target_id: null,
      lease_id: null,
      fencing_token: null,
      lease_expires_at_ms: null,
      queue_depth: queueDepth,
      active_count: activeCount,
      revision,
    });
  }
  const exposeTarget = outcome !== "fenced";
  const exposeLease = exposeTarget && outcome !== "status";
  return deepFreeze({
    schema: QUEUE_RESULT_SCHEMA,
    outcome,
    status: entry.status,
    run_id: entry.run_id,
    request_fingerprint: entry.request_fingerprint,
    queue_position:
      entry.status === "queued"
        ? queuePosition(entries, entry.run_id)
        : null,
    target_id: exposeTarget ? entry.target_id : null,
    lease_id: exposeLease ? entry.lease_id : null,
    fencing_token: exposeLease ? entry.fencing_token : null,
    lease_expires_at_ms: exposeLease
      ? entry.lease_expires_at_ms
      : null,
    queue_depth: queueDepth,
    active_count: activeCount,
    revision,
  });
}

function projectedState(snapshot, nowMs) {
  const state = mutableState(snapshot);
  projectExpired(state, nowMs);
  return state;
}

async function persistIfChanged(context, state, changed, nowMs) {
  if (!changed) return context.store.state;
  return commitState(context, state, nowMs);
}

export async function claimQueueRun(
  artifactRoot,
  rawClaim,
  rawConfig,
  options = {},
) {
  const claim = normalizeClaim(rawClaim);
  const config = normalizeConfig(rawConfig);
  return withStore(
    artifactRoot,
    config,
    options,
    async (context) => {
      const state = mutableState(context.store.state);
      let changed = projectExpired(state, claim.now_ms);
      changed =
        (await scheduleQueued(state, config, claim.now_ms)) || changed;

      const byRun = state.entries.find(
        (entry) => entry.run_id === claim.run_id,
      );
      const byFingerprint = state.entries.find(
        (entry) =>
          entry.request_fingerprint === claim.request_fingerprint,
      );
      if (
        byRun &&
        byRun.request_fingerprint !== claim.request_fingerprint
      ) {
        reject("queue_run_fingerprint_mismatch");
      }
      const existing = byRun ?? byFingerprint;
      if (existing) {
        if (existing.worker_id !== claim.worker_id) {
          reject("queue_worker_mismatch");
        }
        const persisted = await persistIfChanged(
          context,
          state,
          changed,
          claim.now_ms,
        );
        const entry = persisted.entries.find(
          (candidate) => candidate.run_id === existing.run_id,
        );
        return publicResult(
          entry,
          persisted.entries,
          "reattached",
          persisted.revision,
        );
      }

      if (
        state.entries.filter((entry) => entry.status === "queued").length >=
        config.max_depth
      ) {
        const persisted = await persistIfChanged(
          context,
          state,
          changed,
          claim.now_ms,
        );
        return publicResult(
          null,
          persisted.entries,
          "queue_full",
          persisted.revision,
        );
      }
      if (state.entries.length >= MAX_ENTRIES) reject("queue_history_full");
      const enqueueSequence = takeEnqueueSequence(state);
      state.entries.push({
        run_id: claim.run_id,
        request_fingerprint: claim.request_fingerprint,
        worker_id: claim.worker_id,
        enqueue_sequence: enqueueSequence,
        enqueued_at_ms: claim.now_ms,
        updated_at_ms: claim.now_ms,
        status: "queued",
        target_id: null,
        lease_id: null,
        fencing_token: null,
        leased_at_ms: null,
        lease_expires_at_ms: null,
        terminal_at_ms: null,
      });
      await scheduleQueued(state, config, claim.now_ms);
      const persisted = await commitState(context, state, claim.now_ms);
      const entry = persisted.entries.find(
        (candidate) => candidate.run_id === claim.run_id,
      );
      return publicResult(
        entry,
        persisted.entries,
        "accepted",
        persisted.revision,
      );
    },
  );
}

export async function getQueueRunStatus(
  artifactRoot,
  runId,
  { now_ms: nowMs, ...rawOptions } = {},
) {
  const normalizedRunId = safeIdentifier(
    runId,
    RUN_ID_PATTERN,
    "queue_status_request_invalid",
  );
  const normalizedNow = normalizeNow(
    nowMs,
    "queue_status_request_invalid",
  );
  return withStore(
    artifactRoot,
    null,
    rawOptions,
    async (context) => {
      const state = projectedState(context.store.state, normalizedNow);
      const entry = state.entries.find(
        (candidate) => candidate.run_id === normalizedRunId,
      );
      return publicResult(
        entry,
        state.entries,
        "status",
        context.store.state.revision,
      );
    },
    { repair: false },
  );
}

function exactLeaseMatches(entry, operation) {
  return (
    entry.worker_id === operation.worker_id &&
    entry.lease_id === operation.lease_id &&
    entry.fencing_token === operation.fencing_token
  );
}

export async function renewQueueLease(
  artifactRoot,
  rawOperation,
  options = {},
) {
  const operation = normalizeLeaseOperation(rawOperation);
  return withStore(
    artifactRoot,
    null,
    options,
    async (context) => {
      const config = context.generation.config;
      const state = mutableState(context.store.state);
      const before = state.entries.find(
        (entry) => entry.run_id === operation.run_id,
      );
      if (!before) reject("queue_run_missing");
      if (
        before.status === "leased" &&
        exactLeaseMatches(before, operation) &&
        before.lease_expires_at_ms > operation.now_ms
      ) {
        before.lease_expires_at_ms =
          leaseExpiry(operation.now_ms, config.lease_duration_ms);
        before.updated_at_ms = operation.now_ms;
        const persisted = await commitState(
          context,
          state,
          operation.now_ms,
        );
        const entry = persisted.entries.find(
          (candidate) => candidate.run_id === operation.run_id,
        );
        return publicResult(
          entry,
          persisted.entries,
          "renewed",
          persisted.revision,
        );
      }
      if (
        before.status === "leased" &&
        before.lease_expires_at_ms > operation.now_ms
      ) {
        reject("queue_lease_fenced");
      }
      let changed = projectExpired(state, operation.now_ms);
      changed =
        (await scheduleQueued(state, config, operation.now_ms)) || changed;
      const persisted = await persistIfChanged(
        context,
        state,
        changed,
        operation.now_ms,
      );
      const entry = persisted.entries.find(
        (candidate) => candidate.run_id === operation.run_id,
      );
      return publicResult(
        entry,
        persisted.entries,
        "fenced",
        persisted.revision,
      );
    },
  );
}

export async function releaseQueueLease(
  artifactRoot,
  rawOperation,
  options = {},
) {
  const operation = normalizeLeaseOperation(rawOperation, { outcome: true });
  return withStore(
    artifactRoot,
    null,
    options,
    async (context) => {
      const config = context.generation.config;
      const state = mutableState(context.store.state);
      const entry = state.entries.find(
        (candidate) => candidate.run_id === operation.run_id,
      );
      if (!entry) reject("queue_run_missing");
      if (
        entry.status === "released" &&
        exactLeaseMatches(entry, operation)
      ) {
        return publicResult(
          entry,
          state.entries,
          "released",
          context.store.state.revision,
        );
      }
      if (
        entry.status !== "leased" ||
        !exactLeaseMatches(entry, operation)
      ) {
        reject("queue_lease_fenced");
      }
      if (entry.lease_expires_at_ms <= operation.now_ms) {
        projectExpired(state, operation.now_ms);
        await scheduleQueued(state, config, operation.now_ms);
        const persisted = await commitState(
          context,
          state,
          operation.now_ms,
        );
        const current = persisted.entries.find(
          (candidate) => candidate.run_id === operation.run_id,
        );
        return publicResult(
          current,
          persisted.entries,
          "fenced",
          persisted.revision,
        );
      }
      entry.status = "released";
      entry.terminal_at_ms = operation.now_ms;
      entry.updated_at_ms = operation.now_ms;
      await scheduleQueued(state, config, operation.now_ms);
      const persisted = await commitState(
        context,
        state,
        operation.now_ms,
      );
      const current = persisted.entries.find(
        (candidate) => candidate.run_id === operation.run_id,
      );
      return publicResult(
        current,
        persisted.entries,
        "released",
        persisted.revision,
      );
    },
  );
}

export async function cancelQueueRun(
  artifactRoot,
  rawCancel,
  options = {},
) {
  const cancel = normalizeCancel(rawCancel);
  return withStore(
    artifactRoot,
    null,
    options,
    async (context) => {
      const config = context.generation.config;
      const state = mutableState(context.store.state);
      const entry = state.entries.find(
        (candidate) => candidate.run_id === cancel.run_id,
      );
      if (!entry) reject("queue_run_missing");
      if (entry.worker_id !== cancel.worker_id) {
        reject("queue_cancel_denied");
      }
      if (entry.status === "cancelled") {
        return publicResult(
          entry,
          state.entries,
          "cancelled",
          context.store.state.revision,
        );
      }
      if (entry.status === "released") reject("queue_cancel_denied");
      if (entry.status === "leased") {
        if (
          cancel.lease_id === null ||
          cancel.fencing_token === null ||
          !exactLeaseMatches(entry, cancel)
        ) {
          reject("queue_lease_fenced");
        }
        if (entry.lease_expires_at_ms <= cancel.now_ms) {
          projectExpired(state, cancel.now_ms);
          await scheduleQueued(state, config, cancel.now_ms);
          const persisted = await commitState(
            context,
            state,
            cancel.now_ms,
          );
          const current = persisted.entries.find(
            (candidate) => candidate.run_id === cancel.run_id,
          );
          return publicResult(
            current,
            persisted.entries,
            "fenced",
            persisted.revision,
          );
        }
      } else if (
        cancel.lease_id !== null ||
        cancel.fencing_token !== null
      ) {
        reject("queue_cancel_request_invalid");
      }
      entry.status = "cancelled";
      entry.terminal_at_ms = cancel.now_ms;
      entry.updated_at_ms = cancel.now_ms;
      await scheduleQueued(state, config, cancel.now_ms);
      const persisted = await commitState(context, state, cancel.now_ms);
      const current = persisted.entries.find(
        (candidate) => candidate.run_id === cancel.run_id,
      );
      return publicResult(
        current,
        persisted.entries,
        "cancelled",
        persisted.revision,
      );
    },
  );
}
