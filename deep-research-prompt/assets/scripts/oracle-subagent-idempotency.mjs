import { spawn } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { constants as fsConstants } from "node:fs";
import {
  link,
  lstat,
  mkdir,
  open,
  readdir,
  realpath,
  unlink,
} from "node:fs/promises";
import { dirname, isAbsolute, join, resolve } from "node:path";

import {
  RECEIPT_SCHEMA,
  readReceiptFile,
  withReceiptFileLock,
} from "./oracle-subagent-state.mjs";

export const IDEMPOTENCY_INDEX_SCHEMA =
  "oracle-subagent.idempotency-index.v1";
export const IDEMPOTENCY_PUBLICATION_SCHEMA =
  "oracle-subagent.idempotency-publication.v1";
export const IDEMPOTENCY_GENERATION_SCHEMA =
  "oracle-subagent.idempotency-generation.v3";
export const IDEMPOTENCY_INTENT_SCHEMA =
  "oracle-subagent.idempotency-intent.v1";
export const IDEMPOTENCY_CLAIM_MARKER_SCHEMA =
  "oracle-subagent.idempotency-claim-marker.v1";
export const IDEMPOTENCY_CLAIM_LEDGER_ENTRY_SCHEMA =
  "oracle-subagent.idempotency-claim-ledger-entry.v1";
export const IDEMPOTENCY_CLAIM_LEDGER_HEAD_SCHEMA =
  "oracle-subagent.idempotency-claim-ledger-head.v1";
export const IDEMPOTENCY_CLAIM_LEDGER_WITNESS_SCHEMA =
  "oracle-subagent.idempotency-claim-ledger-witness.v1";
export const IDEMPOTENCY_CLAIM_SCHEMA =
  "oracle-subagent.idempotency-claim.v1";

const RUN_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$/;
const OWNER_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const DECIMAL_PATTERN = /^(?:0|[1-9][0-9]{0,39})$/;
const SENSITIVE_PATTERN =
  /(?:authorization|bearer|cookie|password|prompt|secret|session[_-]?token|token|https?:\/\/)/i;
const CREDENTIAL_PATTERN =
  /(?:sk-(?:proj-)?[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{12,}|xapp-[A-Za-z0-9-]{12,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})/i;
const INDEX_LIMIT = 4_096;
const CLAIM_LEDGER_LIMIT = 64 * 1024 * 1024;
const CLAIM_LEDGER_HEAD_LIMIT = 32 * 1024 * 1024;
const CLAIM_LEDGER_ENTRY_LIMIT = 4_096;
const CLAIM_LEDGER_HEAD_ENTRY_LIMIT = 1_024;
const CLAIM_LEDGER_MAX_ENTRIES = 100_000;
const EMPTY_LEDGER_ENTRY_HASH = "0".repeat(64);
const EMPTY_LEDGER_HEAD_HASH = "0".repeat(64);
const MAX_LOCK_TIMEOUT_MS = 60_000;
const MAX_LOCK_POLL_MS = 1_000;
const MAX_POST_ACQUIRE_DELAY_MS = 10_000;
const MAX_BOUNDARY_DELAY_MS = 10_000;

export class OracleSubagentIdempotencyError extends Error {
  constructor(code) {
    super("oracle-subagent idempotency: rejected");
    this.name = "OracleSubagentIdempotencyError";
    this.code = code;
  }
}

function reject(code) {
  throw new OracleSubagentIdempotencyError(code);
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

function patternedString(value, pattern, code) {
  if (typeof value !== "string" || !pattern.test(value)) reject(code);
  return value;
}

function safeIdentifier(value, pattern, code) {
  const identifier = patternedString(value, pattern, code);
  if (
    SENSITIVE_PATTERN.test(identifier) ||
    CREDENTIAL_PATTERN.test(identifier)
  ) {
    reject(code);
  }
  return identifier;
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

function indexHash(index) {
  const copy = structuredClone(index);
  delete copy.index_hash;
  return sha256(canonicalJson(copy));
}

function publicationHash(publication) {
  const copy = structuredClone(publication);
  delete copy.publication_hash;
  return sha256(canonicalJson(copy));
}

function generationHash(generation) {
  const copy = structuredClone(generation);
  delete copy.generation_hash;
  return sha256(canonicalJson(copy));
}

function intentHash(intent) {
  const copy = structuredClone(intent);
  delete copy.intent_hash;
  return sha256(canonicalJson(copy));
}

function claimMarkerHash(marker) {
  const copy = structuredClone(marker);
  delete copy.marker_hash;
  return sha256(canonicalJson(copy));
}

function claimLedgerEntryHash(entry) {
  const copy = structuredClone(entry);
  delete copy.entry_hash;
  return sha256(canonicalJson(copy));
}

function claimLedgerHeadHash(head) {
  const copy = structuredClone(head);
  delete copy.head_hash;
  return sha256(canonicalJson(copy));
}

function claimLedgerWitnessHash(witness) {
  const copy = structuredClone(witness);
  delete copy.witness_hash;
  return sha256(canonicalJson(copy));
}

function deepFreeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value)) deepFreeze(child);
  }
  return value;
}

function validatePrivateMetadata(
  metadata,
  code,
  { directory = false, singleLink = false } = {},
) {
  if (
    (directory && !metadata.isDirectory()) ||
    (!directory && !metadata.isFile()) ||
    metadata.isSymbolicLink() ||
    (metadata.mode & 0o077) !== 0 ||
    (typeof process.getuid === "function" &&
      metadata.uid !== process.getuid()) ||
    (singleLink && metadata.nlink !== 1)
  ) {
    reject(code);
  }
  return metadata;
}

async function privateDirectory(path, code) {
  try {
    const metadata = validatePrivateMetadata(await lstat(path), code, {
      directory: true,
    });
    if ((await realpath(path)) !== path) reject(code);
    return metadata;
  } catch (error) {
    if (error instanceof OracleSubagentIdempotencyError) throw error;
    reject(code);
  }
}

function metadataIdentity(metadata) {
  return Object.freeze({
    dev: String(metadata.dev),
    ino: String(metadata.ino),
  });
}

function sameIdentity(left, right) {
  return left.dev === right.dev && left.ino === right.ino;
}

async function privateDirectoryIdentity(path, code) {
  return metadataIdentity(await privateDirectory(path, code));
}

async function assertOpenedNamedIdentity(path, handle, code) {
  try {
    const opened = validatePrivateMetadata(await handle.stat(), code, {
      singleLink: true,
    });
    const named = validatePrivateMetadata(await lstat(path), code, {
      singleLink: true,
    });
    if (
      opened.dev !== named.dev ||
      opened.ino !== named.ino ||
      (await realpath(path)) !== path
    ) {
      reject(code);
    }
  } catch (error) {
    if (error instanceof OracleSubagentIdempotencyError) throw error;
    reject(code);
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

export function idempotencyLayout(artifactRoot, requestFingerprint) {
  artifactRoot = absolutePath(artifactRoot, "artifact_root_invalid");
  requestFingerprint = patternedString(
    requestFingerprint,
    SHA256_PATTERN,
    "fingerprint_invalid",
  );
  const index_directory = join(artifactRoot, ".idempotency");
  return Object.freeze({
    artifact_root: artifactRoot,
    request_fingerprint: requestFingerprint,
    index_directory,
    bootstrap_lock_path: join(
      artifactRoot,
      ".oracle-subagent-idempotency-bootstrap.lock",
    ),
    generation_path: join(
      artifactRoot,
      ".oracle-subagent-idempotency-generation.json",
    ),
    claim_ledger_path: join(
      artifactRoot,
      ".oracle-subagent-idempotency-claim-ledger.ndjson",
    ),
    claim_ledger_head_path: join(
      artifactRoot,
      ".oracle-subagent-idempotency-claim-ledger-head.ndjson",
    ),
    claim_ledger_lock_path: join(
      artifactRoot,
      ".oracle-subagent-idempotency-claim-ledger.lock",
    ),
    claim_ledger_witness_directory: join(
      artifactRoot,
      ".oracle-subagent-idempotency-claim-ledger-witnesses",
    ),
    intent_path: join(
      artifactRoot,
      `.oracle-subagent-idempotency-intent-${requestFingerprint}.json`,
    ),
    claim_marker_path: join(
      artifactRoot,
      `.oracle-subagent-idempotency-claimed-${requestFingerprint}.json`,
    ),
    index_path: join(index_directory, `${requestFingerprint}.json`),
    publication_path: join(
      index_directory,
      `${requestFingerprint}.published.json`,
    ),
    lock_path: join(
      artifactRoot,
      `.oracle-subagent-idempotency-fingerprint-${requestFingerprint}.lock`,
    ),
  });
}

function normalizeGeneration(rawGeneration) {
  const generation = exactObject(
    rawGeneration,
    [
      "schema",
      "generation_id",
      "artifact_root_dev",
      "artifact_root_ino",
      "index_directory_dev",
      "index_directory_ino",
      "claim_ledger_dev",
      "claim_ledger_ino",
      "claim_ledger_head_dev",
      "claim_ledger_head_ino",
      "claim_ledger_lock_dev",
      "claim_ledger_lock_ino",
      "claim_ledger_lock_ctime_ns",
      "claim_ledger_witness_directory_dev",
      "claim_ledger_witness_directory_ino",
      "created_at",
      "generation_hash",
    ],
    [],
    "generation_invalid",
  );
  if (generation.schema !== IDEMPOTENCY_GENERATION_SCHEMA) {
    reject("generation_invalid");
  }
  const normalized = {
    schema: IDEMPOTENCY_GENERATION_SCHEMA,
    generation_id: patternedString(
      generation.generation_id,
      UUID_PATTERN,
      "generation_invalid",
    ),
    artifact_root_dev: patternedString(
      generation.artifact_root_dev,
      DECIMAL_PATTERN,
      "generation_invalid",
    ),
    artifact_root_ino: patternedString(
      generation.artifact_root_ino,
      DECIMAL_PATTERN,
      "generation_invalid",
    ),
    index_directory_dev: patternedString(
      generation.index_directory_dev,
      DECIMAL_PATTERN,
      "generation_invalid",
    ),
    index_directory_ino: patternedString(
      generation.index_directory_ino,
      DECIMAL_PATTERN,
      "generation_invalid",
    ),
    claim_ledger_dev: patternedString(
      generation.claim_ledger_dev,
      DECIMAL_PATTERN,
      "generation_invalid",
    ),
    claim_ledger_ino: patternedString(
      generation.claim_ledger_ino,
      DECIMAL_PATTERN,
      "generation_invalid",
    ),
    claim_ledger_head_dev: patternedString(
      generation.claim_ledger_head_dev,
      DECIMAL_PATTERN,
      "generation_invalid",
    ),
    claim_ledger_head_ino: patternedString(
      generation.claim_ledger_head_ino,
      DECIMAL_PATTERN,
      "generation_invalid",
    ),
    claim_ledger_lock_dev: patternedString(
      generation.claim_ledger_lock_dev,
      DECIMAL_PATTERN,
      "generation_invalid",
    ),
    claim_ledger_lock_ino: patternedString(
      generation.claim_ledger_lock_ino,
      DECIMAL_PATTERN,
      "generation_invalid",
    ),
    claim_ledger_lock_ctime_ns: patternedString(
      generation.claim_ledger_lock_ctime_ns,
      DECIMAL_PATTERN,
      "generation_invalid",
    ),
    claim_ledger_witness_directory_dev: patternedString(
      generation.claim_ledger_witness_directory_dev,
      DECIMAL_PATTERN,
      "generation_invalid",
    ),
    claim_ledger_witness_directory_ino: patternedString(
      generation.claim_ledger_witness_directory_ino,
      DECIMAL_PATTERN,
      "generation_invalid",
    ),
    created_at: canonicalTimestamp(
      generation.created_at,
      "generation_invalid",
    ),
  };
  const expectedHash = generationHash(normalized);
  if (generation.generation_hash !== expectedHash) {
    reject("generation_invalid");
  }
  return { ...normalized, generation_hash: expectedHash };
}

function normalizeIntent(rawIntent, expectedFingerprint) {
  const intent = exactObject(
    rawIntent,
    [
      "schema",
      "generation_hash",
      "request_fingerprint",
      "run_id",
      "receipt_schema",
      "initial_receipt_hash",
      "receipt_lock_dev",
      "receipt_lock_ino",
      "receipt_lock_ctime_ns",
      "run_directory_dev",
      "run_directory_ino",
      "owner_id",
      "owner_pid",
      "claimed_at",
      "intent_hash",
    ],
    [],
    "intent_invalid",
  );
  if (
    intent.schema !== IDEMPOTENCY_INTENT_SCHEMA ||
    intent.receipt_schema !== RECEIPT_SCHEMA ||
    intent.request_fingerprint !== expectedFingerprint ||
    !Number.isSafeInteger(intent.owner_pid) ||
    intent.owner_pid < 1
  ) {
    reject("intent_invalid");
  }
  const normalized = {
    schema: IDEMPOTENCY_INTENT_SCHEMA,
    generation_hash: patternedString(
      intent.generation_hash,
      SHA256_PATTERN,
      "intent_invalid",
    ),
    request_fingerprint: patternedString(
      intent.request_fingerprint,
      SHA256_PATTERN,
      "intent_invalid",
    ),
    run_id: safeIdentifier(intent.run_id, RUN_ID_PATTERN, "intent_invalid"),
    receipt_schema: RECEIPT_SCHEMA,
    initial_receipt_hash: patternedString(
      intent.initial_receipt_hash,
      SHA256_PATTERN,
      "intent_invalid",
    ),
    receipt_lock_dev: patternedString(
      intent.receipt_lock_dev,
      DECIMAL_PATTERN,
      "intent_invalid",
    ),
    receipt_lock_ino: patternedString(
      intent.receipt_lock_ino,
      DECIMAL_PATTERN,
      "intent_invalid",
    ),
    receipt_lock_ctime_ns: patternedString(
      intent.receipt_lock_ctime_ns,
      DECIMAL_PATTERN,
      "intent_invalid",
    ),
    run_directory_dev: patternedString(
      intent.run_directory_dev,
      DECIMAL_PATTERN,
      "intent_invalid",
    ),
    run_directory_ino: patternedString(
      intent.run_directory_ino,
      DECIMAL_PATTERN,
      "intent_invalid",
    ),
    owner_id: safeIdentifier(
      intent.owner_id,
      OWNER_ID_PATTERN,
      "intent_invalid",
    ),
    owner_pid: intent.owner_pid,
    claimed_at: canonicalTimestamp(intent.claimed_at, "intent_invalid"),
  };
  const expectedHash = intentHash(normalized);
  if (intent.intent_hash !== expectedHash) reject("intent_invalid");
  return { ...normalized, intent_hash: expectedHash };
}

function normalizeClaimMarker(rawMarker, expectedFingerprint) {
  const marker = exactObject(
    rawMarker,
    [
      "schema",
      "generation_hash",
      "request_fingerprint",
      "intent_hash",
      "marker_hash",
    ],
    [],
    "claim_marker_invalid",
  );
  if (
    marker.schema !== IDEMPOTENCY_CLAIM_MARKER_SCHEMA ||
    marker.request_fingerprint !== expectedFingerprint
  ) {
    reject("claim_marker_invalid");
  }
  const normalized = {
    schema: IDEMPOTENCY_CLAIM_MARKER_SCHEMA,
    generation_hash: patternedString(
      marker.generation_hash,
      SHA256_PATTERN,
      "claim_marker_invalid",
    ),
    request_fingerprint: patternedString(
      marker.request_fingerprint,
      SHA256_PATTERN,
      "claim_marker_invalid",
    ),
    intent_hash: patternedString(
      marker.intent_hash,
      SHA256_PATTERN,
      "claim_marker_invalid",
    ),
  };
  const expectedHash = claimMarkerHash(normalized);
  if (marker.marker_hash !== expectedHash) reject("claim_marker_invalid");
  return { ...normalized, marker_hash: expectedHash };
}

function intentFromClaimLedgerEntry(entry) {
  return normalizeIntent(
    {
      schema: IDEMPOTENCY_INTENT_SCHEMA,
      generation_hash: entry.generation_hash,
      request_fingerprint: entry.request_fingerprint,
      run_id: entry.run_id,
      receipt_schema: entry.receipt_schema,
      initial_receipt_hash: entry.initial_receipt_hash,
      receipt_lock_dev: entry.receipt_lock_dev,
      receipt_lock_ino: entry.receipt_lock_ino,
      receipt_lock_ctime_ns: entry.receipt_lock_ctime_ns,
      run_directory_dev: entry.run_directory_dev,
      run_directory_ino: entry.run_directory_ino,
      owner_id: entry.owner_id,
      owner_pid: entry.owner_pid,
      claimed_at: entry.claimed_at,
      intent_hash: entry.intent_hash,
    },
    entry.request_fingerprint,
  );
}

function normalizeClaimLedgerEntry(rawEntry) {
  const entry = exactObject(
    rawEntry,
    [
      "schema",
      "sequence",
      "previous_entry_hash",
      "generation_hash",
      "request_fingerprint",
      "run_id",
      "receipt_schema",
      "initial_receipt_hash",
      "receipt_lock_dev",
      "receipt_lock_ino",
      "receipt_lock_ctime_ns",
      "run_directory_dev",
      "run_directory_ino",
      "owner_id",
      "owner_pid",
      "claimed_at",
      "intent_hash",
      "entry_hash",
    ],
    [],
    "claim_ledger_invalid",
  );
  if (
    entry.schema !== IDEMPOTENCY_CLAIM_LEDGER_ENTRY_SCHEMA ||
    !Number.isSafeInteger(entry.sequence) ||
    entry.sequence < 1 ||
    entry.sequence > CLAIM_LEDGER_MAX_ENTRIES
  ) {
    reject("claim_ledger_invalid");
  }
  const intent = intentFromClaimLedgerEntry(entry);
  const normalized = {
    schema: IDEMPOTENCY_CLAIM_LEDGER_ENTRY_SCHEMA,
    sequence: entry.sequence,
    previous_entry_hash: patternedString(
      entry.previous_entry_hash,
      SHA256_PATTERN,
      "claim_ledger_invalid",
    ),
    generation_hash: intent.generation_hash,
    request_fingerprint: intent.request_fingerprint,
    run_id: intent.run_id,
    receipt_schema: intent.receipt_schema,
    initial_receipt_hash: intent.initial_receipt_hash,
    receipt_lock_dev: intent.receipt_lock_dev,
    receipt_lock_ino: intent.receipt_lock_ino,
    receipt_lock_ctime_ns: intent.receipt_lock_ctime_ns,
    run_directory_dev: intent.run_directory_dev,
    run_directory_ino: intent.run_directory_ino,
    owner_id: intent.owner_id,
    owner_pid: intent.owner_pid,
    claimed_at: intent.claimed_at,
    intent_hash: intent.intent_hash,
  };
  const expectedHash = claimLedgerEntryHash(normalized);
  if (entry.entry_hash !== expectedHash) {
    reject("claim_ledger_invalid");
  }
  return { ...normalized, entry_hash: expectedHash };
}

function normalizeClaimLedgerHead(rawHead) {
  const head = exactObject(
    rawHead,
    [
      "schema",
      "generation_hash",
      "sequence",
      "claim_count",
      "ledger_byte_length",
      "ledger_entry_hash",
      "witness_hash",
      "witness_dev",
      "witness_ino",
      "witness_ctime_ns",
      "previous_head_hash",
      "head_hash",
    ],
    [],
    "claim_ledger_head_invalid",
  );
  if (
    head.schema !== IDEMPOTENCY_CLAIM_LEDGER_HEAD_SCHEMA ||
    !Number.isSafeInteger(head.sequence) ||
    head.sequence < 1 ||
    head.sequence > CLAIM_LEDGER_MAX_ENTRIES ||
    head.claim_count !== head.sequence ||
    !Number.isSafeInteger(head.ledger_byte_length) ||
    head.ledger_byte_length < 1 ||
    head.ledger_byte_length > CLAIM_LEDGER_LIMIT
  ) {
    reject("claim_ledger_head_invalid");
  }
  const normalized = {
    schema: IDEMPOTENCY_CLAIM_LEDGER_HEAD_SCHEMA,
    generation_hash: patternedString(
      head.generation_hash,
      SHA256_PATTERN,
      "claim_ledger_head_invalid",
    ),
    sequence: head.sequence,
    claim_count: head.claim_count,
    ledger_byte_length: head.ledger_byte_length,
    ledger_entry_hash: patternedString(
      head.ledger_entry_hash,
      SHA256_PATTERN,
      "claim_ledger_head_invalid",
    ),
    witness_hash: patternedString(
      head.witness_hash,
      SHA256_PATTERN,
      "claim_ledger_head_invalid",
    ),
    witness_dev: patternedString(
      head.witness_dev,
      DECIMAL_PATTERN,
      "claim_ledger_head_invalid",
    ),
    witness_ino: patternedString(
      head.witness_ino,
      DECIMAL_PATTERN,
      "claim_ledger_head_invalid",
    ),
    witness_ctime_ns: patternedString(
      head.witness_ctime_ns,
      DECIMAL_PATTERN,
      "claim_ledger_head_invalid",
    ),
    previous_head_hash: patternedString(
      head.previous_head_hash,
      SHA256_PATTERN,
      "claim_ledger_head_invalid",
    ),
  };
  const expectedHash = claimLedgerHeadHash(normalized);
  if (head.head_hash !== expectedHash) {
    reject("claim_ledger_head_invalid");
  }
  return { ...normalized, head_hash: expectedHash };
}

function normalizeClaimLedgerWitness(rawWitness) {
  const witness = exactObject(
    rawWitness,
    [
      "schema",
      "generation_hash",
      "sequence",
      "request_fingerprint",
      "run_id",
      "intent_hash",
      "entry_hash",
      "witness_hash",
    ],
    [],
    "claim_ledger_witness_invalid",
  );
  if (
    witness.schema !== IDEMPOTENCY_CLAIM_LEDGER_WITNESS_SCHEMA ||
    !Number.isSafeInteger(witness.sequence) ||
    witness.sequence < 1 ||
    witness.sequence > CLAIM_LEDGER_MAX_ENTRIES
  ) {
    reject("claim_ledger_witness_invalid");
  }
  const normalized = {
    schema: IDEMPOTENCY_CLAIM_LEDGER_WITNESS_SCHEMA,
    generation_hash: patternedString(
      witness.generation_hash,
      SHA256_PATTERN,
      "claim_ledger_witness_invalid",
    ),
    sequence: witness.sequence,
    request_fingerprint: patternedString(
      witness.request_fingerprint,
      SHA256_PATTERN,
      "claim_ledger_witness_invalid",
    ),
    run_id: safeIdentifier(
      witness.run_id,
      RUN_ID_PATTERN,
      "claim_ledger_witness_invalid",
    ),
    intent_hash: patternedString(
      witness.intent_hash,
      SHA256_PATTERN,
      "claim_ledger_witness_invalid",
    ),
    entry_hash: patternedString(
      witness.entry_hash,
      SHA256_PATTERN,
      "claim_ledger_witness_invalid",
    ),
  };
  const expectedHash = claimLedgerWitnessHash(normalized);
  if (witness.witness_hash !== expectedHash) {
    reject("claim_ledger_witness_invalid");
  }
  return { ...normalized, witness_hash: expectedHash };
}

function normalizeIndex(rawIndex, expectedFingerprint) {
  const index = exactObject(
    rawIndex,
    [
      "schema",
      "generation_hash",
      "intent_hash",
      "request_fingerprint",
      "run_id",
      "receipt_schema",
      "initial_receipt_hash",
      "receipt_lock_dev",
      "receipt_lock_ino",
      "receipt_lock_ctime_ns",
      "run_directory_dev",
      "run_directory_ino",
      "owner_id",
      "owner_pid",
      "claimed_at",
      "index_hash",
    ],
    [],
    "index_invalid",
  );
  if (
    index.schema !== IDEMPOTENCY_INDEX_SCHEMA ||
    index.receipt_schema !== RECEIPT_SCHEMA ||
    index.request_fingerprint !== expectedFingerprint ||
    !Number.isSafeInteger(index.owner_pid) ||
    index.owner_pid < 1
  ) {
    reject("index_invalid");
  }
  const normalized = {
    schema: IDEMPOTENCY_INDEX_SCHEMA,
    generation_hash: patternedString(
      index.generation_hash,
      SHA256_PATTERN,
      "index_invalid",
    ),
    intent_hash: patternedString(
      index.intent_hash,
      SHA256_PATTERN,
      "index_invalid",
    ),
    request_fingerprint: patternedString(
      index.request_fingerprint,
      SHA256_PATTERN,
      "index_invalid",
    ),
    run_id: safeIdentifier(index.run_id, RUN_ID_PATTERN, "index_invalid"),
    receipt_schema: RECEIPT_SCHEMA,
    initial_receipt_hash: patternedString(
      index.initial_receipt_hash,
      SHA256_PATTERN,
      "index_invalid",
    ),
    receipt_lock_dev: patternedString(
      index.receipt_lock_dev,
      DECIMAL_PATTERN,
      "index_invalid",
    ),
    receipt_lock_ino: patternedString(
      index.receipt_lock_ino,
      DECIMAL_PATTERN,
      "index_invalid",
    ),
    receipt_lock_ctime_ns: patternedString(
      index.receipt_lock_ctime_ns,
      DECIMAL_PATTERN,
      "index_invalid",
    ),
    run_directory_dev: patternedString(
      index.run_directory_dev,
      DECIMAL_PATTERN,
      "index_invalid",
    ),
    run_directory_ino: patternedString(
      index.run_directory_ino,
      DECIMAL_PATTERN,
      "index_invalid",
    ),
    owner_id: safeIdentifier(
      index.owner_id,
      OWNER_ID_PATTERN,
      "index_invalid",
    ),
    owner_pid: index.owner_pid,
    claimed_at: canonicalTimestamp(index.claimed_at, "index_invalid"),
  };
  const expectedHash = indexHash(normalized);
  if (index.index_hash !== expectedHash) reject("index_invalid");
  return { ...normalized, index_hash: expectedHash };
}

function normalizePublication(rawPublication, expectedFingerprint) {
  const publication = exactObject(
    rawPublication,
    [
      "schema",
      "generation_hash",
      "intent_hash",
      "request_fingerprint",
      "run_id",
      "index_hash",
      "published_at",
      "publication_hash",
    ],
    [],
    "publication_invalid",
  );
  if (
    publication.schema !== IDEMPOTENCY_PUBLICATION_SCHEMA ||
    publication.request_fingerprint !== expectedFingerprint
  ) {
    reject("publication_invalid");
  }
  const normalized = {
    schema: IDEMPOTENCY_PUBLICATION_SCHEMA,
    generation_hash: patternedString(
      publication.generation_hash,
      SHA256_PATTERN,
      "publication_invalid",
    ),
    intent_hash: patternedString(
      publication.intent_hash,
      SHA256_PATTERN,
      "publication_invalid",
    ),
    request_fingerprint: patternedString(
      publication.request_fingerprint,
      SHA256_PATTERN,
      "publication_invalid",
    ),
    run_id: safeIdentifier(
      publication.run_id,
      RUN_ID_PATTERN,
      "publication_invalid",
    ),
    index_hash: patternedString(
      publication.index_hash,
      SHA256_PATTERN,
      "publication_invalid",
    ),
    published_at: canonicalTimestamp(
      publication.published_at,
      "publication_invalid",
    ),
  };
  const expectedHash = publicationHash(normalized);
  if (publication.publication_hash !== expectedHash) {
    reject("publication_invalid");
  }
  return { ...normalized, publication_hash: expectedHash };
}

async function readCanonicalRecord(
  path,
  normalize,
  code,
  { missing = false } = {},
) {
  const flags =
    fsConstants.O_RDONLY |
    (fsConstants.O_NOFOLLOW ?? 0) |
    (fsConstants.O_CLOEXEC ?? 0);
  let handle;
  try {
    handle = await open(path, flags);
    await assertOpenedNamedIdentity(path, handle, code);
    const bytes = await handle.readFile();
    if (
      bytes.length === 0 ||
      bytes.length > INDEX_LIMIT ||
      bytes.at(-1) !== 0x0a
    ) {
      reject(code);
    }
    const record = normalize(JSON.parse(bytes.toString("utf8")));
    if (`${canonicalJson(record)}\n` !== bytes.toString("utf8")) {
      reject(code);
    }
    await assertOpenedNamedIdentity(path, handle, code);
    return record;
  } catch (error) {
    if (missing && error.code === "ENOENT") return null;
    if (error instanceof OracleSubagentIdempotencyError) throw error;
    reject(code);
  } finally {
    await handle?.close().catch(() => {});
  }
}

async function readGeneration(path, options) {
  return readCanonicalRecord(
    path,
    normalizeGeneration,
    "generation_invalid",
    options,
  );
}

async function readIntent(path, fingerprint, options) {
  return readCanonicalRecord(
    path,
    (value) => normalizeIntent(value, fingerprint),
    "intent_invalid",
    options,
  );
}

async function readClaimMarker(path, fingerprint, options) {
  return readCanonicalRecord(
    path,
    (value) => normalizeClaimMarker(value, fingerprint),
    "claim_marker_invalid",
    options,
  );
}

async function readIndex(path, fingerprint, options) {
  return readCanonicalRecord(
    path,
    (value) => normalizeIndex(value, fingerprint),
    "index_invalid",
    options,
  );
}

async function readPublication(
  path,
  fingerprint,
  options,
) {
  return readCanonicalRecord(
    path,
    (value) => normalizePublication(value, fingerprint),
    "publication_invalid",
    options,
  );
}

async function readClaimLedgerWitness(path, options) {
  return readCanonicalRecord(
    path,
    normalizeClaimLedgerWitness,
    "claim_ledger_witness_invalid",
    options,
  );
}

async function writeRecordAtomic(path, record, conflictCode) {
  const temporaryPath = `${dirname(path)}/.idempotency.${process.pid}.${randomUUID()}.tmp`;
  let handle;
  try {
    handle = await open(
      temporaryPath,
      fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_WRONLY,
      0o600,
    );
    await handle.writeFile(`${canonicalJson(record)}\n`);
    await handle.sync();
    await handle.close();
    handle = undefined;
    await link(temporaryPath, path);
    await unlink(temporaryPath);
    await fsyncDirectory(dirname(path));
  } catch (error) {
    await handle?.close().catch(() => {});
    await unlink(temporaryPath).catch(() => {});
    if (error.code === "EEXIST") reject(conflictCode);
    if (error instanceof OracleSubagentIdempotencyError) throw error;
    reject("record_write_failed");
  }
}

async function ensureEmptyPrivateFile(path, code) {
  const flags =
    fsConstants.O_CREAT |
    fsConstants.O_EXCL |
    fsConstants.O_WRONLY |
    (fsConstants.O_NOFOLLOW ?? 0) |
    (fsConstants.O_CLOEXEC ?? 0);
  let handle;
  let created = false;
  try {
    try {
      handle = await open(path, flags, 0o600);
      created = true;
      await handle.sync();
      await assertOpenedNamedIdentity(path, handle, code);
    } catch (error) {
      if (error.code !== "EEXIST") throw error;
    } finally {
      await handle?.close();
      handle = undefined;
    }
    const metadata = validatePrivateMetadata(await lstat(path), code, {
      singleLink: true,
    });
    if (metadata.size !== 0 || (await realpath(path)) !== path) {
      reject(code);
    }
    await fsyncDirectory(dirname(path));
    return created;
  } catch (error) {
    await handle?.close().catch(() => {});
    if (error instanceof OracleSubagentIdempotencyError) throw error;
    reject(code);
  }
}

function normalizeLockOptions(rawOptions = {}) {
  const options = exactObject(
    rawOptions,
    [],
    [
      "timeoutMs",
      "pollMs",
      "postAcquireDelayMs",
      "postLedgerFsyncDelayMs",
      "postWitnessFsyncDelayMs",
      "postPublicationFsyncDelayMs",
    ],
    "lock_options_invalid",
  );
  const normalized = {
    timeoutMs: options.timeoutMs ?? 5_000,
    pollMs: options.pollMs ?? 20,
    postAcquireDelayMs: options.postAcquireDelayMs ?? 0,
    postLedgerFsyncDelayMs: options.postLedgerFsyncDelayMs ?? 0,
    postWitnessFsyncDelayMs: options.postWitnessFsyncDelayMs ?? 0,
    postPublicationFsyncDelayMs:
      options.postPublicationFsyncDelayMs ?? 0,
  };
  if (
    !Number.isSafeInteger(normalized.timeoutMs) ||
    normalized.timeoutMs < 0 ||
    normalized.timeoutMs > MAX_LOCK_TIMEOUT_MS ||
    !Number.isSafeInteger(normalized.pollMs) ||
    normalized.pollMs < 1 ||
    normalized.pollMs > MAX_LOCK_POLL_MS ||
    !Number.isSafeInteger(normalized.postAcquireDelayMs) ||
    normalized.postAcquireDelayMs < 0 ||
    normalized.postAcquireDelayMs > MAX_POST_ACQUIRE_DELAY_MS ||
    !Number.isSafeInteger(normalized.postLedgerFsyncDelayMs) ||
    normalized.postLedgerFsyncDelayMs < 0 ||
    normalized.postLedgerFsyncDelayMs > MAX_BOUNDARY_DELAY_MS ||
    !Number.isSafeInteger(normalized.postWitnessFsyncDelayMs) ||
    normalized.postWitnessFsyncDelayMs < 0 ||
    normalized.postWitnessFsyncDelayMs > MAX_BOUNDARY_DELAY_MS ||
    !Number.isSafeInteger(normalized.postPublicationFsyncDelayMs) ||
    normalized.postPublicationFsyncDelayMs < 0 ||
    normalized.postPublicationFsyncDelayMs > MAX_BOUNDARY_DELAY_MS
  ) {
    reject("lock_options_invalid");
  }
  return normalized;
}

async function boundaryDelay(milliseconds) {
  if (milliseconds > 0) {
    await new Promise((resolvePromise) =>
      setTimeout(resolvePromise, milliseconds),
    );
  }
}

async function assertLockIdentity(lockPath, handle) {
  try {
    const opened = validatePrivateMetadata(
      await handle.stat(),
      "lock_replaced",
      { singleLink: true },
    );
    const named = validatePrivateMetadata(
      await lstat(lockPath),
      "lock_replaced",
      { singleLink: true },
    );
    if (
      opened.dev !== named.dev ||
      opened.ino !== named.ino ||
      (await realpath(lockPath)) !== lockPath
    ) {
      reject("lock_replaced");
    }
  } catch (error) {
    if (error instanceof OracleSubagentIdempotencyError) throw error;
    reject("lock_replaced");
  }
}

async function withFingerprintLock(lockPath, callback, rawOptions) {
  const { timeoutMs, pollMs, postAcquireDelayMs } =
    normalizeLockOptions(rawOptions);
  const flags =
    fsConstants.O_RDWR |
    fsConstants.O_CREAT |
    (fsConstants.O_NOFOLLOW ?? 0) |
    (fsConstants.O_CLOEXEC ?? 0);
  let handle;
  try {
    handle = await open(lockPath, flags, 0o600);
    await assertLockIdentity(lockPath, handle);
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
    if (code === 75) reject("lock_timeout");
    if (code !== 0 || standardError) reject("lock_failed");
    if (postAcquireDelayMs > 0) {
      await new Promise((resolvePromise) =>
        setTimeout(resolvePromise, postAcquireDelayMs),
      );
    }
    await assertLockIdentity(lockPath, handle);
    const result = await callback(() => assertLockIdentity(lockPath, handle));
    await assertLockIdentity(lockPath, handle);
    return result;
  } catch (error) {
    if (error instanceof OracleSubagentIdempotencyError) throw error;
    reject("lock_failed");
  } finally {
    await handle?.close().catch(() => {});
  }
}

async function assertDirectoryIdentity(path, expected, code) {
  const observed = await privateDirectoryIdentity(path, code);
  if (!sameIdentity(observed, expected)) reject(code);
}

async function pathPresent(path, code) {
  try {
    await lstat(path);
    return true;
  } catch (error) {
    if (error.code === "ENOENT") return false;
    reject(code);
  }
}

function requireGenerationBinding(
  generation,
  artifactRootIdentity,
  indexDirectoryIdentity,
  claimLedgerIdentity,
  claimLedgerHeadIdentity,
  claimLedgerLockIdentity,
  claimLedgerWitnessDirectoryIdentity,
) {
  if (
    generation.artifact_root_dev !== artifactRootIdentity.dev ||
    generation.artifact_root_ino !== artifactRootIdentity.ino ||
    generation.index_directory_dev !== indexDirectoryIdentity.dev ||
    generation.index_directory_ino !== indexDirectoryIdentity.ino ||
    generation.claim_ledger_dev !== claimLedgerIdentity.dev ||
    generation.claim_ledger_ino !== claimLedgerIdentity.ino ||
    generation.claim_ledger_head_dev !== claimLedgerHeadIdentity.dev ||
    generation.claim_ledger_head_ino !== claimLedgerHeadIdentity.ino ||
    generation.claim_ledger_lock_dev !== claimLedgerLockIdentity.dev ||
    generation.claim_ledger_lock_ino !== claimLedgerLockIdentity.ino ||
    generation.claim_ledger_lock_ctime_ns !==
      claimLedgerLockIdentity.ctime_ns ||
    generation.claim_ledger_witness_directory_dev !==
      claimLedgerWitnessDirectoryIdentity.dev ||
    generation.claim_ledger_witness_directory_ino !==
      claimLedgerWitnessDirectoryIdentity.ino
  ) {
    reject("generation_directory_mismatch");
  }
}

async function ensureIdempotencyStore(layout) {
  const artifactRootIdentity = await privateDirectoryIdentity(
    layout.artifact_root,
    "artifact_root_invalid",
  );
  const inspectStoreComponents = async () => ({
    indexDirectoryIdentity: await privateDirectoryIdentity(
      layout.index_directory,
      "index_directory_invalid",
    ),
    claimLedgerIdentity: await namedPrivateFileIdentity(
      layout.claim_ledger_path,
      "claim_ledger_invalid",
    ),
    claimLedgerHeadIdentity: await namedPrivateFileIdentity(
      layout.claim_ledger_head_path,
      "claim_ledger_head_invalid",
    ),
    claimLedgerLockIdentity: await namedPrivateFileIdentity(
      layout.claim_ledger_lock_path,
      "claim_ledger_lock_invalid",
    ),
    claimLedgerWitnessDirectoryIdentity:
      await privateDirectoryIdentity(
        layout.claim_ledger_witness_directory,
        "claim_ledger_witness_directory_invalid",
      ),
  });
  let generation = await readGeneration(layout.generation_path, {
    missing: true,
  });
  let store;
  if (generation) {
    const components = await inspectStoreComponents();
    requireGenerationBinding(
      generation,
      artifactRootIdentity,
      components.indexDirectoryIdentity,
      components.claimLedgerIdentity,
      components.claimLedgerHeadIdentity,
      components.claimLedgerLockIdentity,
      components.claimLedgerWitnessDirectoryIdentity,
    );
    try {
      await fsyncDirectory(layout.artifact_root);
    } catch {
      reject("bootstrap_durability_failed");
    }
    store = {
      artifactRootIdentity,
      ...components,
      generation,
    };
  } else {
    store = await withFingerprintLock(
      layout.bootstrap_lock_path,
      async (assertBootstrapLockStable) => {
        await assertBootstrapLockStable();
        await assertDirectoryIdentity(
          layout.artifact_root,
          artifactRootIdentity,
          "artifact_root_invalid",
        );
        generation = await readGeneration(layout.generation_path, {
          missing: true,
        });
        if (generation) {
          const components = await inspectStoreComponents();
          requireGenerationBinding(
            generation,
            artifactRootIdentity,
            components.indexDirectoryIdentity,
            components.claimLedgerIdentity,
            components.claimLedgerHeadIdentity,
            components.claimLedgerLockIdentity,
            components.claimLedgerWitnessDirectoryIdentity,
          );
          await assertBootstrapLockStable();
          return {
            artifactRootIdentity,
            ...components,
            generation,
          };
        }
        const componentPresence = await Promise.all([
          pathPresent(
            layout.index_directory,
            "index_directory_invalid",
          ),
          pathPresent(layout.claim_ledger_path, "claim_ledger_invalid"),
          pathPresent(
            layout.claim_ledger_head_path,
            "claim_ledger_head_invalid",
          ),
          pathPresent(
            layout.claim_ledger_lock_path,
            "claim_ledger_lock_invalid",
          ),
          pathPresent(
            layout.claim_ledger_witness_directory,
            "claim_ledger_witness_directory_invalid",
          ),
        ]);
        if (componentPresence.some(Boolean)) {
          reject("generation_missing");
        }
        let directoryCreated = false;
        try {
          await mkdir(layout.index_directory, { mode: 0o700 });
          directoryCreated = true;
        } catch (error) {
          if (error.code !== "EEXIST") reject("index_directory_invalid");
        }
        let witnessDirectoryCreated = false;
        try {
          await mkdir(layout.claim_ledger_witness_directory, {
            mode: 0o700,
          });
          witnessDirectoryCreated = true;
        } catch (error) {
          if (error.code !== "EEXIST") {
            reject("claim_ledger_witness_directory_invalid");
          }
        }
        const claimLedgerCreated = await ensureEmptyPrivateFile(
          layout.claim_ledger_path,
          "claim_ledger_invalid",
        );
        const claimLedgerHeadCreated = await ensureEmptyPrivateFile(
          layout.claim_ledger_head_path,
          "claim_ledger_head_invalid",
        );
        const claimLedgerLockCreated = await ensureEmptyPrivateFile(
          layout.claim_ledger_lock_path,
          "claim_ledger_lock_invalid",
        );
        try {
          await fsyncDirectory(layout.index_directory);
          await fsyncDirectory(
            layout.claim_ledger_witness_directory,
          );
          await fsyncDirectory(layout.artifact_root);
        } catch {
          reject("bootstrap_durability_failed");
        }
        const components = await inspectStoreComponents();
        await assertBootstrapLockStable();
        generation = await readGeneration(layout.generation_path, {
          missing: true,
        });
        if (!generation) {
          if (
            !directoryCreated ||
            !witnessDirectoryCreated ||
            !claimLedgerCreated ||
            !claimLedgerHeadCreated ||
            !claimLedgerLockCreated
          ) {
            reject("generation_missing");
          }
          const generationBase = {
            schema: IDEMPOTENCY_GENERATION_SCHEMA,
            generation_id: randomUUID(),
            artifact_root_dev: artifactRootIdentity.dev,
            artifact_root_ino: artifactRootIdentity.ino,
            index_directory_dev:
              components.indexDirectoryIdentity.dev,
            index_directory_ino:
              components.indexDirectoryIdentity.ino,
            claim_ledger_dev: components.claimLedgerIdentity.dev,
            claim_ledger_ino: components.claimLedgerIdentity.ino,
            claim_ledger_head_dev:
              components.claimLedgerHeadIdentity.dev,
            claim_ledger_head_ino:
              components.claimLedgerHeadIdentity.ino,
            claim_ledger_lock_dev:
              components.claimLedgerLockIdentity.dev,
            claim_ledger_lock_ino:
              components.claimLedgerLockIdentity.ino,
            claim_ledger_lock_ctime_ns:
              components.claimLedgerLockIdentity.ctime_ns,
            claim_ledger_witness_directory_dev:
              components.claimLedgerWitnessDirectoryIdentity.dev,
            claim_ledger_witness_directory_ino:
              components.claimLedgerWitnessDirectoryIdentity.ino,
            created_at: new Date().toISOString(),
          };
          generation = {
            ...generationBase,
            generation_hash: generationHash(generationBase),
          };
          await writeRecordAtomic(
            layout.generation_path,
            generation,
            "generation_conflict",
          );
        }
        requireGenerationBinding(
          generation,
          artifactRootIdentity,
          components.indexDirectoryIdentity,
          components.claimLedgerIdentity,
          components.claimLedgerHeadIdentity,
          components.claimLedgerLockIdentity,
          components.claimLedgerWitnessDirectoryIdentity,
        );
        await assertBootstrapLockStable();
        try {
          await fsyncDirectory(layout.artifact_root);
        } catch {
          reject("bootstrap_durability_failed");
        }
        return {
          artifactRootIdentity,
          ...components,
          generation,
        };
      },
    );
  }

  const assertStoreStable = async () => {
    await assertDirectoryIdentity(
      layout.artifact_root,
      store.artifactRootIdentity,
      "artifact_root_invalid",
    );
    await assertDirectoryIdentity(
      layout.index_directory,
      store.indexDirectoryIdentity,
      "index_directory_invalid",
    );
    await assertDirectoryIdentity(
      layout.claim_ledger_witness_directory,
      store.claimLedgerWitnessDirectoryIdentity,
      "claim_ledger_witness_directory_invalid",
    );
    const claimLedgerIdentity = await namedPrivateFileIdentity(
      layout.claim_ledger_path,
      "claim_ledger_invalid",
    );
    const claimLedgerHeadIdentity = await namedPrivateFileIdentity(
      layout.claim_ledger_head_path,
      "claim_ledger_head_invalid",
    );
    const claimLedgerLockIdentity = await namedPrivateFileIdentity(
      layout.claim_ledger_lock_path,
      "claim_ledger_lock_invalid",
    );
    const generation = await readGeneration(layout.generation_path, {
      missing: true,
    });
    if (!generation) reject("generation_missing");
    if (canonicalJson(generation) !== canonicalJson(store.generation)) {
      reject("generation_changed");
    }
    requireGenerationBinding(
      generation,
      store.artifactRootIdentity,
      store.indexDirectoryIdentity,
      claimLedgerIdentity,
      claimLedgerHeadIdentity,
      claimLedgerLockIdentity,
      store.claimLedgerWitnessDirectoryIdentity,
    );
  };
  await assertStoreStable();
  return Object.freeze({ ...store, assertStoreStable });
}

async function namedPrivateFileIdentity(path, code) {
  try {
    const [metadata, precise] = await Promise.all([
      lstat(path),
      lstat(path, { bigint: true }),
    ]);
    validatePrivateMetadata(metadata, code, { singleLink: true });
    if ((await realpath(path)) !== path) reject(code);
    return Object.freeze({
      dev: precise.dev.toString(),
      ino: precise.ino.toString(),
      ctime_ns: precise.ctimeNs.toString(),
    });
  } catch (error) {
    if (error instanceof OracleSubagentIdempotencyError) throw error;
    reject(code);
  }
}

function claimLedgerWitnessName(entry) {
  return `${String(entry.sequence).padStart(12, "0")}-${entry.request_fingerprint}.json`;
}

function claimLedgerWitnessFromEntry(entry) {
  const base = {
    schema: IDEMPOTENCY_CLAIM_LEDGER_WITNESS_SCHEMA,
    generation_hash: entry.generation_hash,
    sequence: entry.sequence,
    request_fingerprint: entry.request_fingerprint,
    run_id: entry.run_id,
    intent_hash: entry.intent_hash,
    entry_hash: entry.entry_hash,
  };
  return { ...base, witness_hash: claimLedgerWitnessHash(base) };
}

function claimLedgerHeadFromEntry(
  entry,
  previousHeadHash,
  ledgerByteLength,
  witness,
  witnessIdentity,
) {
  const base = {
    schema: IDEMPOTENCY_CLAIM_LEDGER_HEAD_SCHEMA,
    generation_hash: entry.generation_hash,
    sequence: entry.sequence,
    claim_count: entry.sequence,
    ledger_byte_length: ledgerByteLength,
    ledger_entry_hash: entry.entry_hash,
    witness_hash: witness.witness_hash,
    witness_dev: witnessIdentity.dev,
    witness_ino: witnessIdentity.ino,
    witness_ctime_ns: witnessIdentity.ctime_ns,
    previous_head_hash: previousHeadHash,
  };
  return { ...base, head_hash: claimLedgerHeadHash(base) };
}

function claimLedgerEntryFromIntent(intent, previousEntryHash, sequence) {
  const base = {
    schema: IDEMPOTENCY_CLAIM_LEDGER_ENTRY_SCHEMA,
    sequence,
    previous_entry_hash: previousEntryHash,
    generation_hash: intent.generation_hash,
    request_fingerprint: intent.request_fingerprint,
    run_id: intent.run_id,
    receipt_schema: intent.receipt_schema,
    initial_receipt_hash: intent.initial_receipt_hash,
    receipt_lock_dev: intent.receipt_lock_dev,
    receipt_lock_ino: intent.receipt_lock_ino,
    receipt_lock_ctime_ns: intent.receipt_lock_ctime_ns,
    run_directory_dev: intent.run_directory_dev,
    run_directory_ino: intent.run_directory_ino,
    owner_id: intent.owner_id,
    owner_pid: intent.owner_pid,
    claimed_at: intent.claimed_at,
    intent_hash: intent.intent_hash,
  };
  return { ...base, entry_hash: claimLedgerEntryHash(base) };
}

function requireClaimLedgerIntentBinding(entry, intent) {
  if (
    canonicalJson(intentFromClaimLedgerEntry(entry)) !==
    canonicalJson(intent)
  ) {
    reject("claim_ledger_intent_mismatch");
  }
}

function requireClaimLedgerWitnessBinding(witness, entry) {
  if (
    canonicalJson(claimLedgerWitnessFromEntry(entry)) !==
    canonicalJson(witness)
  ) {
    reject("claim_ledger_witness_mismatch");
  }
}

async function readClaimLedgerHead(layout, store) {
  const flags =
    fsConstants.O_RDONLY |
    (fsConstants.O_NOFOLLOW ?? 0) |
    (fsConstants.O_CLOEXEC ?? 0);
  let handle;
  try {
    handle = await open(layout.claim_ledger_head_path, flags);
    await assertOpenedNamedIdentity(
      layout.claim_ledger_head_path,
      handle,
      "claim_ledger_head_invalid",
    );
    const openedIdentity = metadataIdentity(await handle.stat());
    if (!sameIdentity(openedIdentity, store.claimLedgerHeadIdentity)) {
      reject("claim_ledger_head_replaced");
    }
    const bytes = await handle.readFile();
    if (
      bytes.length > CLAIM_LEDGER_HEAD_LIMIT ||
      (bytes.length > 0 && bytes.at(-1) !== 0x0a)
    ) {
      reject("claim_ledger_head_invalid");
    }
    const encodedLines =
      bytes.length === 0
        ? []
        : bytes
            .toString("utf8")
            .slice(0, -1)
            .split("\n");
    if (encodedLines.length > CLAIM_LEDGER_MAX_ENTRIES) {
      reject("claim_ledger_head_invalid");
    }
    const heads = [];
    let previousHeadHash = EMPTY_LEDGER_HEAD_HASH;
    for (const [index, encoded] of encodedLines.entries()) {
      if (
        Buffer.byteLength(encoded, "utf8") === 0 ||
        Buffer.byteLength(encoded, "utf8") >
          CLAIM_LEDGER_HEAD_ENTRY_LIMIT
      ) {
        reject("claim_ledger_head_invalid");
      }
      let parsed;
      try {
        parsed = JSON.parse(encoded);
      } catch {
        reject("claim_ledger_head_invalid");
      }
      const head = normalizeClaimLedgerHead(parsed);
      if (
        canonicalJson(head) !== encoded ||
        head.sequence !== index + 1 ||
        head.previous_head_hash !== previousHeadHash ||
        head.generation_hash !== store.generation.generation_hash
      ) {
        reject("claim_ledger_head_invalid");
      }
      heads.push(head);
      previousHeadHash = head.head_hash;
    }
    await assertOpenedNamedIdentity(
      layout.claim_ledger_head_path,
      handle,
      "claim_ledger_head_invalid",
    );
    return Object.freeze({
      byteLength: bytes.length,
      heads: Object.freeze(heads),
      lastHeadHash: previousHeadHash,
    });
  } catch (error) {
    if (error instanceof OracleSubagentIdempotencyError) throw error;
    reject("claim_ledger_head_invalid");
  } finally {
    await handle?.close().catch(() => {});
  }
}

async function readClaimLedgerEntries(layout, store) {
  const flags =
    fsConstants.O_RDONLY |
    (fsConstants.O_NOFOLLOW ?? 0) |
    (fsConstants.O_CLOEXEC ?? 0);
  let handle;
  try {
    handle = await open(layout.claim_ledger_path, flags);
    await assertOpenedNamedIdentity(
      layout.claim_ledger_path,
      handle,
      "claim_ledger_invalid",
    );
    const openedIdentity = metadataIdentity(await handle.stat());
    if (!sameIdentity(openedIdentity, store.claimLedgerIdentity)) {
      reject("claim_ledger_replaced");
    }
    const bytes = await handle.readFile();
    if (
      bytes.length > CLAIM_LEDGER_LIMIT ||
      (bytes.length > 0 && bytes.at(-1) !== 0x0a)
    ) {
      reject("claim_ledger_invalid");
    }
    const encodedLines =
      bytes.length === 0
        ? []
        : bytes
            .toString("utf8")
            .slice(0, -1)
            .split("\n");
    if (encodedLines.length > CLAIM_LEDGER_MAX_ENTRIES) {
      reject("claim_ledger_invalid");
    }
    const entries = [];
    const ledgerByteLengths = [];
    const fingerprints = new Set();
    let previousEntryHash = EMPTY_LEDGER_ENTRY_HASH;
    let ledgerByteLength = 0;
    for (const [index, encoded] of encodedLines.entries()) {
      if (
        Buffer.byteLength(encoded, "utf8") === 0 ||
        Buffer.byteLength(encoded, "utf8") >
          CLAIM_LEDGER_ENTRY_LIMIT
      ) {
        reject("claim_ledger_invalid");
      }
      let parsed;
      try {
        parsed = JSON.parse(encoded);
      } catch {
        reject("claim_ledger_invalid");
      }
      const entry = normalizeClaimLedgerEntry(parsed);
      if (
        `${canonicalJson(entry)}` !== encoded ||
        entry.sequence !== index + 1 ||
        entry.previous_entry_hash !== previousEntryHash ||
        entry.generation_hash !==
          store.generation.generation_hash ||
        fingerprints.has(entry.request_fingerprint)
      ) {
        reject("claim_ledger_invalid");
      }
      entries.push(entry);
      ledgerByteLength += Buffer.byteLength(`${encoded}\n`, "utf8");
      ledgerByteLengths.push(ledgerByteLength);
      fingerprints.add(entry.request_fingerprint);
      previousEntryHash = entry.entry_hash;
    }
    await assertOpenedNamedIdentity(
      layout.claim_ledger_path,
      handle,
      "claim_ledger_invalid",
    );
    return Object.freeze({
      byteLength: bytes.length,
      entries: Object.freeze(entries),
      entriesByFingerprint: new Map(
        entries.map((entry) => [
          entry.request_fingerprint,
          entry,
        ]),
      ),
      ledgerByteLengths: Object.freeze(ledgerByteLengths),
      lastEntryHash: previousEntryHash,
    });
  } catch (error) {
    if (error instanceof OracleSubagentIdempotencyError) throw error;
    reject("claim_ledger_invalid");
  } finally {
    await handle?.close().catch(() => {});
  }
}

function requireClaimLedgerHeadPrefix(ledger, head, { exact = false } = {}) {
  if (
    head.heads.length > ledger.entries.length ||
    (exact && head.heads.length !== ledger.entries.length) ||
    head.heads.some(
      (record, index) =>
        record.sequence !== ledger.entries[index].sequence ||
        record.claim_count !== ledger.entries[index].sequence ||
        record.ledger_byte_length !==
          ledger.ledgerByteLengths[index] ||
        record.ledger_entry_hash !== ledger.entries[index].entry_hash,
    )
  ) {
    reject("claim_ledger_head_mismatch");
  }
}

async function readClaimLedgerWitnessDirectory(layout, store) {
  const witnessDirectoryBefore = await privateDirectoryIdentity(
    layout.claim_ledger_witness_directory,
    "claim_ledger_witness_directory_invalid",
  );
  if (
    !sameIdentity(
      witnessDirectoryBefore,
      store.claimLedgerWitnessDirectoryIdentity,
    )
  ) {
    reject("claim_ledger_witness_directory_replaced");
  }
  try {
    return await readdir(layout.claim_ledger_witness_directory, {
      withFileTypes: true,
    });
  } catch {
    reject("claim_ledger_witness_invalid");
  }
}

async function verifyClaimLedgerWitness(layout, entry, headRecord) {
  const witnessPath = join(
    layout.claim_ledger_witness_directory,
    claimLedgerWitnessName(entry),
  );
  const witnessIdentityBefore = await namedPrivateFileIdentity(
    witnessPath,
    "claim_ledger_witness_invalid",
  );
  const witness = await readClaimLedgerWitness(witnessPath);
  requireClaimLedgerWitnessBinding(witness, entry);
  const witnessIdentityAfter = await namedPrivateFileIdentity(
    witnessPath,
    "claim_ledger_witness_invalid",
  );
  if (
    witnessIdentityBefore.dev !== witnessIdentityAfter.dev ||
    witnessIdentityBefore.ino !== witnessIdentityAfter.ino ||
    witnessIdentityBefore.ctime_ns !== witnessIdentityAfter.ctime_ns ||
    (headRecord &&
      (headRecord.witness_hash !== witness.witness_hash ||
        headRecord.witness_dev !== witnessIdentityAfter.dev ||
        headRecord.witness_ino !== witnessIdentityAfter.ino ||
        headRecord.witness_ctime_ns !==
          witnessIdentityAfter.ctime_ns))
  ) {
    reject("claim_ledger_witness_mismatch");
  }
  return Object.freeze({
    witness,
    identity: witnessIdentityAfter,
  });
}

async function readClaimLedger(layout, store) {
  const ledger = await readClaimLedgerEntries(layout, store);
  const head = await readClaimLedgerHead(layout, store);
  requireClaimLedgerHeadPrefix(ledger, head, { exact: true });
  const witnessEntries = await readClaimLedgerWitnessDirectory(
    layout,
    store,
  );
  const expectedNames = new Set(
    ledger.entries.map(claimLedgerWitnessName),
  );
  if (
    witnessEntries.length !== expectedNames.size ||
    witnessEntries.some(
      (entry) => !entry.isFile() || !expectedNames.has(entry.name),
    )
  ) {
    reject("claim_ledger_witness_mismatch");
  }
  for (const [index, entry] of ledger.entries.entries()) {
    await verifyClaimLedgerWitness(layout, entry, head.heads[index]);
  }
  await assertDirectoryIdentity(
    layout.claim_ledger_witness_directory,
    store.claimLedgerWitnessDirectoryIdentity,
    "claim_ledger_witness_directory_replaced",
  );
  return Object.freeze({
    ...ledger,
    headByteLength: head.byteLength,
    heads: head.heads,
    lastHeadHash: head.lastHeadHash,
  });
}

async function appendClaimLedgerHeadRecord(
  layout,
  store,
  head,
  expectedByteLength,
  assertStable,
) {
  const encodedHead = `${canonicalJson(head)}\n`;
  if (
    Buffer.byteLength(encodedHead, "utf8") >
    CLAIM_LEDGER_HEAD_ENTRY_LIMIT
  ) {
    reject("claim_ledger_head_invalid");
  }
  let handle;
  try {
    handle = await open(
      layout.claim_ledger_head_path,
      fsConstants.O_WRONLY |
        fsConstants.O_APPEND |
        (fsConstants.O_NOFOLLOW ?? 0) |
        (fsConstants.O_CLOEXEC ?? 0),
    );
    await assertOpenedNamedIdentity(
      layout.claim_ledger_head_path,
      handle,
      "claim_ledger_head_invalid",
    );
    const metadata = await handle.stat();
    if (
      !sameIdentity(
        metadataIdentity(metadata),
        store.claimLedgerHeadIdentity,
      ) ||
      metadata.size !== expectedByteLength
    ) {
      reject("claim_ledger_head_changed");
    }
    await handle.writeFile(encodedHead);
    await handle.sync();
    await assertOpenedNamedIdentity(
      layout.claim_ledger_head_path,
      handle,
      "claim_ledger_head_invalid",
    );
    await handle.close();
    handle = undefined;
    await fsyncDirectory(layout.artifact_root);
    await assertStable();
  } catch (error) {
    if (error instanceof OracleSubagentIdempotencyError) throw error;
    reject("claim_ledger_head_write_failed");
  } finally {
    await handle?.close().catch(() => {});
  }
}

async function repairClaimLedgerTerminalPrefix(
  layout,
  store,
  assertStable,
) {
  const ledger = await readClaimLedgerEntries(layout, store);
  const head = await readClaimLedgerHead(layout, store);
  requireClaimLedgerHeadPrefix(ledger, head);
  const lag = ledger.entries.length - head.heads.length;
  if (lag === 0) return readClaimLedger(layout, store);
  if (lag !== 1) reject("claim_ledger_head_mismatch");

  const witnessEntries = await readClaimLedgerWitnessDirectory(
    layout,
    store,
  );
  const terminalEntry = ledger.entries.at(-1);
  const terminalName = claimLedgerWitnessName(terminalEntry);
  const committedNames = new Set(
    ledger.entries.slice(0, -1).map(claimLedgerWitnessName),
  );
  if (
    witnessEntries.some(
      (entry) =>
        !entry.isFile() ||
        (!committedNames.has(entry.name) &&
          entry.name !== terminalName),
    ) ||
    [...committedNames].some(
      (name) => !witnessEntries.some((entry) => entry.name === name),
    )
  ) {
    reject("claim_ledger_witness_mismatch");
  }
  for (const [index, entry] of ledger.entries
    .slice(0, -1)
    .entries()) {
    await verifyClaimLedgerWitness(layout, entry, head.heads[index]);
  }
  let terminalWitness;
  if (witnessEntries.some((entry) => entry.name === terminalName)) {
    terminalWitness = await verifyClaimLedgerWitness(
      layout,
      terminalEntry,
    );
  } else {
    const witness = claimLedgerWitnessFromEntry(terminalEntry);
    await writeRecordAtomic(
      join(layout.claim_ledger_witness_directory, terminalName),
      witness,
      "claim_ledger_witness_conflict",
    );
    await fsyncDirectory(layout.claim_ledger_witness_directory);
    await fsyncDirectory(layout.artifact_root);
    await assertStable();
    terminalWitness = await verifyClaimLedgerWitness(
      layout,
      terminalEntry,
    );
  }
  await assertDirectoryIdentity(
    layout.claim_ledger_witness_directory,
    store.claimLedgerWitnessDirectoryIdentity,
    "claim_ledger_witness_directory_replaced",
  );
  const repairedHead = claimLedgerHeadFromEntry(
    terminalEntry,
    head.lastHeadHash,
    ledger.ledgerByteLengths.at(-1),
    terminalWitness.witness,
    terminalWitness.identity,
  );
  await appendClaimLedgerHeadRecord(
    layout,
    store,
    repairedHead,
    head.byteLength,
    assertStable,
  );
  return readClaimLedger(layout, store);
}

async function appendClaimLedgerEntry(
  layout,
  store,
  intent,
  ledger,
  assertStable,
  boundaryDelays,
) {
  if (ledger.entriesByFingerprint.has(intent.request_fingerprint)) {
    reject("claim_ledger_conflict");
  }
  const entry = claimLedgerEntryFromIntent(
    intent,
    ledger.lastEntryHash,
    ledger.entries.length + 1,
  );
  const encoded = `${canonicalJson(entry)}\n`;
  if (Buffer.byteLength(encoded, "utf8") > CLAIM_LEDGER_ENTRY_LIMIT) {
    reject("claim_ledger_invalid");
  }
  const flags =
    fsConstants.O_WRONLY |
    fsConstants.O_APPEND |
    (fsConstants.O_NOFOLLOW ?? 0) |
    (fsConstants.O_CLOEXEC ?? 0);
  let handle;
  try {
    handle = await open(layout.claim_ledger_path, flags);
    await assertOpenedNamedIdentity(
      layout.claim_ledger_path,
      handle,
      "claim_ledger_invalid",
    );
    const metadata = await handle.stat();
    if (
      !sameIdentity(
        metadataIdentity(metadata),
        store.claimLedgerIdentity,
      ) ||
      metadata.size !== ledger.byteLength
    ) {
      reject("claim_ledger_changed");
    }
    await handle.writeFile(encoded);
    await handle.sync();
    await assertOpenedNamedIdentity(
      layout.claim_ledger_path,
      handle,
      "claim_ledger_invalid",
    );
    await handle.close();
    handle = undefined;
    await fsyncDirectory(layout.artifact_root);
    await boundaryDelay(boundaryDelays.postLedgerFsyncDelayMs);
    await assertStable();
    const witness = claimLedgerWitnessFromEntry(entry);
    await writeRecordAtomic(
      join(
        layout.claim_ledger_witness_directory,
        claimLedgerWitnessName(entry),
      ),
      witness,
      "claim_ledger_witness_conflict",
    );
    await fsyncDirectory(layout.claim_ledger_witness_directory);
    await fsyncDirectory(layout.artifact_root);
    await boundaryDelay(boundaryDelays.postWitnessFsyncDelayMs);
    await assertStable();
    const witnessIdentity = await namedPrivateFileIdentity(
      join(
        layout.claim_ledger_witness_directory,
        claimLedgerWitnessName(entry),
      ),
      "claim_ledger_witness_invalid",
    );
    const head = claimLedgerHeadFromEntry(
      entry,
      ledger.lastHeadHash,
      ledger.byteLength + Buffer.byteLength(encoded, "utf8"),
      witness,
      witnessIdentity,
    );
    await appendClaimLedgerHeadRecord(
      layout,
      store,
      head,
      ledger.headByteLength,
      assertStable,
    );
    const persisted = await readClaimLedger(layout, store);
    const persistedEntry = persisted.entriesByFingerprint.get(
      intent.request_fingerprint,
    );
    if (
      !persistedEntry ||
      canonicalJson(persistedEntry) !== canonicalJson(entry) ||
      canonicalJson(persisted.heads.at(-1)) !== canonicalJson(head)
    ) {
      reject("claim_ledger_unstable");
    }
    return { entry, ledger: persisted };
  } catch (error) {
    if (error instanceof OracleSubagentIdempotencyError) throw error;
    reject("claim_ledger_write_failed");
  } finally {
    await handle?.close().catch(() => {});
  }
}

function requireReceiptBinding(index, runDirectoryIdentity, lockIdentity) {
  if (
    index.run_directory_dev !== undefined &&
    (index.run_directory_dev !== runDirectoryIdentity.dev ||
      index.run_directory_ino !== runDirectoryIdentity.ino ||
      index.receipt_lock_dev !== lockIdentity.dev ||
      index.receipt_lock_ino !== lockIdentity.ino ||
      index.receipt_lock_ctime_ns !== lockIdentity.ctime_ns)
  ) {
    reject("receipt_lock_replaced");
  }
}

async function verifiedReceipt(artifactRoot, index, { initial = false } = {}) {
  const receiptPath = join(artifactRoot, index.run_id, "receipt.json");
  const runDirectory = dirname(receiptPath);
  const runDirectoryIdentity = await privateDirectoryIdentity(
    runDirectory,
    "receipt_invalid",
  );
  try {
    const preLockIdentity = await namedPrivateFileIdentity(
      `${receiptPath}.lock`,
      "receipt_invalid",
    );
    requireReceiptBinding(
      index,
      runDirectoryIdentity,
      preLockIdentity,
    );
    const verified = await withReceiptFileLock(
      receiptPath,
      async (assertReceiptLockStable) => {
        await assertReceiptLockStable();
        await assertDirectoryIdentity(
          runDirectory,
          runDirectoryIdentity,
          "receipt_invalid",
        );
        const receiptLockIdentity = await namedPrivateFileIdentity(
          `${receiptPath}.lock`,
          "receipt_invalid",
        );
        requireReceiptBinding(
          index,
          runDirectoryIdentity,
          receiptLockIdentity,
        );
        await assertReceiptLockStable();
        const first = await readReceiptFile(receiptPath);
        await assertReceiptLockStable();
        await assertDirectoryIdentity(
          runDirectory,
          runDirectoryIdentity,
          "receipt_invalid",
        );
        const second = await readReceiptFile(receiptPath);
        await assertReceiptLockStable();
        if (canonicalJson(first) !== canonicalJson(second)) {
          reject("receipt_unstable");
        }
        if (
          second.run_id !== index.run_id ||
          second.request_fingerprint !== index.request_fingerprint ||
          (initial &&
            (second.state !== "created" ||
              (index.initial_receipt_hash &&
                second.receipt_hash !== index.initial_receipt_hash)))
        ) {
          reject("receipt_invalid");
        }
        requireReceiptBinding(
          index,
          runDirectoryIdentity,
          receiptLockIdentity,
        );
        return {
          receiptPath,
          receipt: second,
          receiptLockIdentity,
          runDirectoryIdentity,
        };
      },
    );
    await assertDirectoryIdentity(
      runDirectory,
      runDirectoryIdentity,
      "receipt_invalid",
    );
    const namedLock = await namedPrivateFileIdentity(
      `${receiptPath}.lock`,
      "receipt_invalid",
    );
    if (
      namedLock.dev !== verified.receiptLockIdentity.dev ||
      namedLock.ino !== verified.receiptLockIdentity.ino ||
      namedLock.ctime_ns !== verified.receiptLockIdentity.ctime_ns
    ) {
      reject("receipt_lock_replaced");
    }
    return verified;
  } catch (error) {
    if (error instanceof OracleSubagentIdempotencyError) throw error;
    if (
      error instanceof Error &&
      [
        "oracle-subagent state: receipt lock was replaced",
        "oracle-subagent state: receipt lock does not match its immutable receipt binding",
      ].includes(error.message)
    ) {
      reject("receipt_lock_replaced");
    }
    reject("receipt_invalid");
  }
}

function ownerStatus(ownerPid) {
  try {
    process.kill(ownerPid, 0);
    return "live";
  } catch (error) {
    if (error.code === "ESRCH") return "stale";
    return "unknown";
  }
}

function claimResult(index, receiptPath, receipt, disposition) {
  return deepFreeze({
    schema: IDEMPOTENCY_CLAIM_SCHEMA,
    request_fingerprint: index.request_fingerprint,
    run_id: index.run_id,
    receipt_path: receiptPath,
    initial_receipt_hash: index.initial_receipt_hash,
    disposition,
    owner_status: ownerStatus(index.owner_pid),
    send_authorized: disposition === "owner",
    receipt,
  });
}

function indexFromIntent(intent) {
  const base = {
    schema: IDEMPOTENCY_INDEX_SCHEMA,
    generation_hash: intent.generation_hash,
    intent_hash: intent.intent_hash,
    request_fingerprint: intent.request_fingerprint,
    run_id: intent.run_id,
    receipt_schema: RECEIPT_SCHEMA,
    initial_receipt_hash: intent.initial_receipt_hash,
    receipt_lock_dev: intent.receipt_lock_dev,
    receipt_lock_ino: intent.receipt_lock_ino,
    receipt_lock_ctime_ns: intent.receipt_lock_ctime_ns,
    run_directory_dev: intent.run_directory_dev,
    run_directory_ino: intent.run_directory_ino,
    owner_id: intent.owner_id,
    owner_pid: intent.owner_pid,
    claimed_at: intent.claimed_at,
  };
  return { ...base, index_hash: indexHash(base) };
}

function claimMarkerFromIntent(intent) {
  const base = {
    schema: IDEMPOTENCY_CLAIM_MARKER_SCHEMA,
    generation_hash: intent.generation_hash,
    request_fingerprint: intent.request_fingerprint,
    intent_hash: intent.intent_hash,
  };
  return { ...base, marker_hash: claimMarkerHash(base) };
}

function publicationFromIndex(index) {
  const base = {
    schema: IDEMPOTENCY_PUBLICATION_SCHEMA,
    generation_hash: index.generation_hash,
    intent_hash: index.intent_hash,
    request_fingerprint: index.request_fingerprint,
    run_id: index.run_id,
    index_hash: index.index_hash,
    published_at: index.claimed_at,
  };
  return { ...base, publication_hash: publicationHash(base) };
}

function requireIntentBinding(intent, index) {
  if (canonicalJson(indexFromIntent(intent)) !== canonicalJson(index)) {
    reject("intent_index_mismatch");
  }
}

function requireClaimMarkerBinding(marker, intent) {
  if (
    canonicalJson(claimMarkerFromIntent(intent)) !== canonicalJson(marker)
  ) {
    reject("claim_marker_intent_mismatch");
  }
}

function requirePublicationBinding(publication, index) {
  if (
    publication.generation_hash !== index.generation_hash ||
    publication.intent_hash !== index.intent_hash ||
    publication.request_fingerprint !== index.request_fingerprint ||
    publication.run_id !== index.run_id ||
    publication.index_hash !== index.index_hash ||
    publication.published_at !== index.claimed_at
  ) {
    reject("publication_index_mismatch");
  }
}

async function readStableRecordSnapshot(
  layout,
  requestFingerprint,
  expectedGenerationHash,
) {
  const markerFirst = await readClaimMarker(
    layout.claim_marker_path,
    requestFingerprint,
    { missing: true },
  );
  const intentFirst = await readIntent(
    layout.intent_path,
    requestFingerprint,
    { missing: true },
  );
  const publicationFirst = await readPublication(
    layout.publication_path,
    requestFingerprint,
    { missing: true },
  );
  const indexFirst = await readIndex(
    layout.index_path,
    requestFingerprint,
    { missing: true },
  );
  const markerSecond = await readClaimMarker(
    layout.claim_marker_path,
    requestFingerprint,
    { missing: true },
  );
  const intentSecond = await readIntent(
    layout.intent_path,
    requestFingerprint,
    { missing: true },
  );
  const publicationSecond = await readPublication(
    layout.publication_path,
    requestFingerprint,
    { missing: true },
  );
  const indexSecond = await readIndex(
    layout.index_path,
    requestFingerprint,
    { missing: true },
  );
  if (
    canonicalJson(markerFirst) !== canonicalJson(markerSecond) ||
    canonicalJson(intentFirst) !== canonicalJson(intentSecond) ||
    canonicalJson(publicationFirst) !== canonicalJson(publicationSecond) ||
    canonicalJson(indexFirst) !== canonicalJson(indexSecond)
  ) {
    reject("publication_unstable");
  }
  if (
    [markerSecond, intentSecond, publicationSecond, indexSecond]
      .filter(Boolean)
      .some((record) => record.generation_hash !== expectedGenerationHash)
  ) {
    reject("record_generation_mismatch");
  }
  return {
    marker: markerSecond,
    intent: intentSecond,
    publication: publicationSecond,
    index: indexSecond,
  };
}

function validateStableRecords(records) {
  const { marker, intent, publication, index } = records;
  if (marker && !intent) {
    reject("intent_missing_after_marker");
  }
  if (!intent && (publication || index)) {
    reject("intent_missing_for_records");
  }
  if (intent && !marker && (publication || index)) {
    reject("claim_marker_missing_for_records");
  }
  if (publication && !index) {
    reject("index_missing_after_publication");
  }
  if (!publication && index) {
    reject("publication_missing_for_index");
  }
  if (marker && intent) {
    requireClaimMarkerBinding(marker, intent);
  }
  if (intent && publication && index) {
    requireIntentBinding(intent, index);
    requirePublicationBinding(publication, index);
  }
  return records;
}

async function readStableRecords(
  layout,
  requestFingerprint,
  expectedGenerationHash,
) {
  return validateStableRecords(
    await readStableRecordSnapshot(
      layout,
      requestFingerprint,
      expectedGenerationHash,
    ),
  );
}

async function repairTerminalIndexPrefix(
  layout,
  requestFingerprint,
  expectedGenerationHash,
  ledgerEntry,
  assertStable,
) {
  const records = await readStableRecordSnapshot(
    layout,
    requestFingerprint,
    expectedGenerationHash,
  );
  if (
    records.intent &&
    records.marker &&
    records.publication &&
    !records.index &&
    ledgerEntry
  ) {
    requireClaimLedgerIntentBinding(ledgerEntry, records.intent);
    requireClaimMarkerBinding(records.marker, records.intent);
    const repairedIndex = indexFromIntent(records.intent);
    requirePublicationBinding(records.publication, repairedIndex);
    await writeRecordAtomic(
      layout.index_path,
      repairedIndex,
      "index_conflict",
    );
    await assertStable();
    const repaired = await readStableRecords(
      layout,
      requestFingerprint,
      expectedGenerationHash,
    );
    if (
      canonicalJson(repaired.index) !== canonicalJson(repairedIndex)
    ) {
      reject("publication_unstable");
    }
    return repaired;
  }
  return validateStableRecords(records);
}

export async function claimIdempotentRequest(
  artifactRoot,
  rawClaim,
  lockOptions = {},
) {
  const claim = exactObject(
    rawClaim,
    ["request_fingerprint", "candidate_run_id", "owner_id"],
    [],
    "claim_invalid",
  );
  const requestFingerprint = patternedString(
    claim.request_fingerprint,
    SHA256_PATTERN,
    "claim_invalid",
  );
  const candidateRunId = safeIdentifier(
    claim.candidate_run_id,
    RUN_ID_PATTERN,
    "claim_invalid",
  );
  const ownerId = safeIdentifier(
    claim.owner_id,
    OWNER_ID_PATTERN,
    "claim_invalid",
  );
  const normalizedLockOptions = normalizeLockOptions(lockOptions);
  const layout = idempotencyLayout(artifactRoot, requestFingerprint);
  const store = await ensureIdempotencyStore(layout);

  const result = await withFingerprintLock(
    layout.claim_ledger_lock_path,
    async (assertClaimLedgerLockStable) => {
      const assertGlobalStable = async () => {
        await assertClaimLedgerLockStable();
        await store.assertStoreStable();
      };
      await assertGlobalStable();
      let claimLedger = await repairClaimLedgerTerminalPrefix(
        layout,
        store,
        assertGlobalStable,
      );
      await assertGlobalStable();

      return withFingerprintLock(
        layout.lock_path,
        async (assertLockStable) => {
          const assertClaimStable = async () => {
            await assertClaimLedgerLockStable();
            await assertLockStable();
            await store.assertStoreStable();
          };
          const assertClaimLedgerStable = async () => {
            await assertClaimStable();
            const observed = await readClaimLedger(layout, store);
            if (
              observed.byteLength !== claimLedger.byteLength ||
              observed.headByteLength !==
                claimLedger.headByteLength ||
              canonicalJson(observed.entries) !==
                canonicalJson(claimLedger.entries) ||
              canonicalJson(observed.heads) !==
                canonicalJson(claimLedger.heads)
            ) {
              reject("claim_ledger_changed");
            }
          };
          await assertClaimStable();
          let claimLedgerEntry =
            claimLedger.entriesByFingerprint.get(requestFingerprint);
          let records = await repairTerminalIndexPrefix(
            layout,
            requestFingerprint,
            store.generation.generation_hash,
            claimLedgerEntry,
            assertClaimStable,
          );
          await assertClaimLedgerStable();
          if (records.index) {
            if (!claimLedgerEntry) {
              reject("claim_ledger_entry_missing");
            }
            requireClaimLedgerIntentBinding(
              claimLedgerEntry,
              records.intent,
            );
            const { receiptPath, receipt } = await verifiedReceipt(
              layout.artifact_root,
              records.index,
            );
            await assertClaimLedgerStable();
            return claimResult(
              records.index,
              receiptPath,
              receipt,
              "reattached",
            );
          }

          if (records.intent || claimLedgerEntry) {
            const recoveredIntent =
              records.intent ??
              intentFromClaimLedgerEntry(claimLedgerEntry);
            if (!claimLedgerEntry) {
              reject("claim_ledger_entry_missing");
            }
            requireClaimLedgerIntentBinding(
              claimLedgerEntry,
              recoveredIntent,
            );
            const recoveredMarker =
              claimMarkerFromIntent(recoveredIntent);
            const recoveredIndex = indexFromIntent(recoveredIntent);
            const recoveredPublication =
              publicationFromIndex(recoveredIndex);
            await assertClaimStable();
            if (!records.intent) {
              await writeRecordAtomic(
                layout.intent_path,
                recoveredIntent,
                "intent_conflict",
              );
              await assertClaimStable();
            }
            if (!records.marker) {
              await writeRecordAtomic(
                layout.claim_marker_path,
                recoveredMarker,
                "claim_marker_conflict",
              );
              await assertClaimStable();
            }
            await writeRecordAtomic(
              layout.publication_path,
              recoveredPublication,
              "publication_conflict",
            );
            await assertClaimStable();
            await writeRecordAtomic(
              layout.index_path,
              recoveredIndex,
              "index_conflict",
            );
            await assertClaimStable();
            records = await readStableRecords(
              layout,
              requestFingerprint,
              store.generation.generation_hash,
            );
            requireClaimLedgerIntentBinding(
              claimLedgerEntry,
              records.intent,
            );
            const recovered = await verifiedReceipt(
              layout.artifact_root,
              records.index,
            );
            await assertClaimLedgerStable();
            return claimResult(
              records.index,
              recovered.receiptPath,
              recovered.receipt,
              "reattached",
            );
          }

          const provisional = {
            run_id: candidateRunId,
            request_fingerprint: requestFingerprint,
            initial_receipt_hash: "",
          };
          const initial = await verifiedReceipt(
            layout.artifact_root,
            provisional,
            { initial: true },
          );
          const intentBase = {
            schema: IDEMPOTENCY_INTENT_SCHEMA,
            generation_hash: store.generation.generation_hash,
            request_fingerprint: requestFingerprint,
            run_id: candidateRunId,
            receipt_schema: RECEIPT_SCHEMA,
            initial_receipt_hash: initial.receipt.receipt_hash,
            receipt_lock_dev: initial.receiptLockIdentity.dev,
            receipt_lock_ino: initial.receiptLockIdentity.ino,
            receipt_lock_ctime_ns:
              initial.receiptLockIdentity.ctime_ns,
            run_directory_dev: initial.runDirectoryIdentity.dev,
            run_directory_ino: initial.runDirectoryIdentity.ino,
            owner_id: ownerId,
            owner_pid: process.pid,
            claimed_at: initial.receipt.timestamps.created,
          };
          const intent = {
            ...intentBase,
            intent_hash: intentHash(intentBase),
          };
          const marker = claimMarkerFromIntent(intent);
          const index = indexFromIntent(intent);
          const publication = publicationFromIndex(index);
          await assertClaimStable();
          const appended = await appendClaimLedgerEntry(
            layout,
            store,
            intent,
            claimLedger,
            assertClaimStable,
            normalizedLockOptions,
          );
          claimLedger = appended.ledger;
          claimLedgerEntry = appended.entry;
          requireClaimLedgerIntentBinding(claimLedgerEntry, intent);
          await assertClaimLedgerStable();
          await writeRecordAtomic(
            layout.intent_path,
            intent,
            "intent_conflict",
          );
          await assertClaimStable();
          await writeRecordAtomic(
            layout.claim_marker_path,
            marker,
            "claim_marker_conflict",
          );
          await assertClaimStable();
          await writeRecordAtomic(
            layout.publication_path,
            publication,
            "publication_conflict",
          );
          await boundaryDelay(
            normalizedLockOptions.postPublicationFsyncDelayMs,
          );
          await assertClaimStable();
          await writeRecordAtomic(
            layout.index_path,
            index,
            "index_conflict",
          );
          await assertClaimStable();
          const persisted = await readStableRecords(
            layout,
            requestFingerprint,
            store.generation.generation_hash,
          );
          if (
            canonicalJson(marker) !==
              canonicalJson(persisted.marker) ||
            canonicalJson(intent) !==
              canonicalJson(persisted.intent) ||
            canonicalJson(index) !==
              canonicalJson(persisted.index) ||
            canonicalJson(publication) !==
              canonicalJson(persisted.publication)
          ) {
            reject("publication_unstable");
          }
          requireClaimLedgerIntentBinding(
            claimLedgerEntry,
            persisted.intent,
          );
          const verified = await verifiedReceipt(
            layout.artifact_root,
            persisted.index,
            { initial: true },
          );
          await assertClaimLedgerStable();
          try {
            await fsyncDirectory(layout.artifact_root);
          } catch {
            reject("bootstrap_durability_failed");
          }
          await assertClaimLedgerStable();
          return claimResult(
            persisted.index,
            verified.receiptPath,
            verified.receipt,
            "owner",
          );
        },
        normalizedLockOptions,
      );
    },
    {
      timeoutMs: normalizedLockOptions.timeoutMs,
      pollMs: normalizedLockOptions.pollMs,
      postAcquireDelayMs: 0,
    },
  );
  await store.assertStoreStable();
  return result;
}
