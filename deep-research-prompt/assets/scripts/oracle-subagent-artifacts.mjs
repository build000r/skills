import { createHash } from "node:crypto";
import { constants as fsConstants } from "node:fs";
import {
  lstat,
  mkdir,
  open,
  realpath,
} from "node:fs/promises";
import {
  basename,
  dirname,
  isAbsolute,
  join,
  resolve,
} from "node:path";

import {
  createReceiptFile,
  readReceiptFile,
  STATES,
  TERMINAL_STATES,
  withReceiptFileLock,
  writeResultAtomic,
} from "./oracle-subagent-state.mjs";

export const REQUEST_SCHEMA = "oracle-subagent.request.v1";
export const EVENT_SCHEMA = "oracle-subagent.event.v1";

const RUN_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$/;
const SLUG_PATTERN = /^[a-z0-9][a-z0-9-]{0,79}$/;
const IDENTIFIER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/;
const CODE_PATTERN = /^[a-z][a-z0-9_]{1,63}$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const MEDIA_TYPE_PATTERN =
  /^[a-z0-9][a-z0-9!#$&^_.+-]{0,63}\/[a-z0-9][a-z0-9!#$&^_.+-]{0,63}$/;
const EVENT_SOURCES = new Set([
  "browser",
  "controller",
  "delivery",
  "operator",
  "user",
]);
const SENSITIVE_LOG_PATTERN =
  /(?:authorization|bearer|cookie|password|prompt|secret|session[_-]?token|token|https?:\/\/)/i;
const CREDENTIAL_SHAPE_PATTERN =
  /(?:sk-(?:proj-)?[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{12,}|xapp-[A-Za-z0-9-]{12,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})/i;

function fail(message) {
  throw new Error(`oracle-subagent artifacts: ${message}`);
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
  const object = requirePlainObject(value, "object");
  const allowed = new Set([...required, ...optional]);
  for (const key of required) {
    if (!Object.hasOwn(object, key)) fail(`object is missing ${key}`);
  }
  for (const key of Object.keys(object)) {
    if (!allowed.has(key)) fail("object contains a forbidden field");
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
    SENSITIVE_LOG_PATTERN.test(identifier) ||
    CREDENTIAL_SHAPE_PATTERN.test(identifier)
  ) {
    fail(`${label} contains sensitive log text`);
  }
  return identifier;
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
  const normalized = new Date(milliseconds).toISOString();
  if (value !== normalized) fail(`${label} must be canonical RFC3339`);
  return value;
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

function identifierFingerprint(value) {
  return createHash("sha256").update(value, "utf8").digest("hex");
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

/**
 * Allow only root-owned intermediate symlinks (macOS /tmp -> /private/tmp).
 * Leaf must already be a real directory; user-owned redirect still fails closed.
 */
async function assertNoHostileSymlinkTraversal(absolutePath, label) {
  const resolved = await realpath(absolutePath);
  if (resolved === absolutePath) return;

  // Without uid checks we cannot distinguish system vs hostile intermediates.
  if (typeof process.getuid !== "function") {
    fail(`${label} traverses a symlink`);
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
    // Leaf symlink is already rejected by the caller; any remaining symlink
    // component must be root-owned (system path), never a user redirect.
    if (prefix === absolutePath || metadata.uid !== 0) {
      fail(`${label} traverses a symlink`);
    }
    sawSystemSymlink = true;
  }

  // realpath differed with no intermediate system symlink: fail closed
  // (case alias / other non-canonical form).
  if (!sawSystemSymlink) {
    fail(`${label} traverses a symlink`);
  }
}

async function assertPrivateDirectory(path, label) {
  const metadata = await lstat(path);
  if (!metadata.isDirectory() || metadata.isSymbolicLink()) {
    fail(`${label} is not a real directory`);
  }
  if ((metadata.mode & 0o077) !== 0) {
    fail(`${label} grants group/world access`);
  }
  if (
    typeof process.getuid === "function" &&
    metadata.uid !== process.getuid()
  ) {
    fail(`${label} is not owned by the current user`);
  }
  await assertNoHostileSymlinkTraversal(path, label);
  return metadata;
}

async function assertPrivateFile(path, label, { allowEmpty = true } = {}) {
  const metadata = await lstat(path);
  if (!metadata.isFile() || metadata.isSymbolicLink()) {
    fail(`${label} is not a regular file`);
  }
  if ((metadata.mode & 0o077) !== 0) {
    fail(`${label} grants group/world access`);
  }
  if (
    typeof process.getuid === "function" &&
    metadata.uid !== process.getuid()
  ) {
    fail(`${label} is not owned by the current user`);
  }
  if (!allowEmpty && metadata.size === 0) fail(`${label} is empty`);
  return metadata;
}

function assertPrivateFileMetadata(metadata, label, { allowEmpty = true } = {}) {
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
  if (!allowEmpty && metadata.size === 0) fail(`${label} is empty`);
}

async function readPrivateFile(path, label, { allowEmpty = true } = {}) {
  const flags =
    fsConstants.O_RDONLY |
    (fsConstants.O_NOFOLLOW ?? 0) |
    (fsConstants.O_CLOEXEC ?? 0);
  const handle = await open(path, flags);
  try {
    assertPrivateFileMetadata(await handle.stat(), label, { allowEmpty });
    return await handle.readFile("utf8");
  } finally {
    await handle.close();
  }
}

async function createPrivateRoot(path) {
  requireAbsolutePath(path, "artifact root");
  try {
    await assertPrivateDirectory(path, "artifact root");
    return;
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  const parent = dirname(path);
  await assertPrivateDirectory(parent, "artifact root parent");
  try {
    await mkdir(path, { mode: 0o700 });
  } catch (error) {
    if (error.code !== "EEXIST") throw error;
  }
  await assertPrivateDirectory(path, "artifact root");
  await fsyncDirectory(parent);
}

async function writeNewPrivateFile(path, bytes) {
  requireAbsolutePath(path, "artifact path");
  const handle = await open(
    path,
    fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_WRONLY,
    0o600,
  );
  try {
    await handle.writeFile(bytes);
    await handle.sync();
  } finally {
    await handle.close();
  }
  await fsyncDirectory(dirname(path));
  await assertPrivateFile(path, basename(path));
}

function normalizeAttachments(rawAttachments = []) {
  if (!Array.isArray(rawAttachments)) fail("attachments must be an array");
  return rawAttachments.map((rawAttachment, index) => {
    const attachment = requireExactKeys(rawAttachment, [
      "path",
      "bytes",
      "sha256",
      "media_type",
    ]);
    return {
      path: requireAbsolutePath(attachment.path, `attachment ${index} path`),
      bytes: requireInteger(attachment.bytes, `attachment ${index} bytes`, 1),
      sha256: requireSha256(
        attachment.sha256,
        `attachment ${index} sha256`,
      ),
      media_type: requireString(
        attachment.media_type,
        `attachment ${index} media_type`,
        MEDIA_TYPE_PATTERN,
      ),
    };
  });
}

function normalizeRequest(rawRequest) {
  const request = requireExactKeys(rawRequest, [
    "run_id",
    "slug",
    "mode",
    "request_fingerprint",
    "prompt",
    "attachments",
    "created_at",
    "event_id",
  ]);
  const prompt =
    typeof request.prompt === "string" ? request.prompt : fail("prompt must be text");
  if (Buffer.byteLength(prompt, "utf8") === 0) fail("prompt must be nonempty");
  const mode = request.mode;
  if (!["pro", "deep-research"].includes(mode)) {
    fail("mode must be pro or deep-research");
  }
  return {
    schema: REQUEST_SCHEMA,
    run_id: requireSafeIdentifier(request.run_id, "run_id", RUN_ID_PATTERN),
    slug: requireSafeIdentifier(request.slug, "slug", SLUG_PATTERN),
    mode,
    request_fingerprint: requireSha256(
      request.request_fingerprint,
      "request_fingerprint",
    ),
    prompt,
    attachments: normalizeAttachments(request.attachments),
    created_at: requireTimestamp(request.created_at, "created_at"),
    event_id: requireSafeIdentifier(request.event_id, "event_id"),
  };
}

export function runArtifactLayout(root, runId) {
  const normalizedRoot = requireAbsolutePath(root, "artifact root");
  const normalizedRunId = requireSafeIdentifier(
    runId,
    "run_id",
    RUN_ID_PATTERN,
  );
  const directory = join(normalizedRoot, normalizedRunId);
  return Object.freeze({
    root: normalizedRoot,
    run_id: normalizedRunId,
    directory,
    request: join(directory, "request.json"),
    events: join(directory, "events.ndjson"),
    receipt: join(directory, "receipt.json"),
    result: join(directory, "result.md"),
  });
}

function requireRunArtifactLayout(rawLayout) {
  const layout = requireExactKeys(rawLayout, [
    "root",
    "run_id",
    "directory",
    "request",
    "events",
    "receipt",
    "result",
  ]);
  const expected = runArtifactLayout(layout.root, layout.run_id);
  if (canonicalJson(layout) !== canonicalJson(expected)) {
    fail("artifact layout does not match its root and run_id");
  }
  return expected;
}

export async function createRunArtifacts(root, rawRequest) {
  const request = normalizeRequest(rawRequest);
  const layout = runArtifactLayout(root, request.run_id);
  await createPrivateRoot(layout.root);
  await mkdir(layout.directory, { mode: 0o700 });
  await assertPrivateDirectory(layout.directory, "run directory");
  await fsyncDirectory(layout.root);

  await writeNewPrivateFile(
    layout.request,
    `${canonicalJson(request)}\n`,
  );
  await writeNewPrivateFile(layout.events, "");
  const receipt = await createReceiptFile(layout.receipt, {
    runId: request.run_id,
    slug: request.slug,
    mode: request.mode,
    requestFingerprint: request.request_fingerprint,
    createdAt: request.created_at,
    eventId: request.event_id,
  });
  await appendRunEvent(layout, {
    event_id: request.event_id,
    run_id: request.run_id,
    state: "created",
    revision: 0,
    observed_at: request.created_at,
    source: "controller",
    receipt_hash: receipt.receipt_hash,
  });
  return {
    layout,
    receipt,
    public_request: publicRequestMetadata(request),
  };
}

export function publicRequestMetadata(rawRequest) {
  let requestInput = rawRequest;
  if (isPlainObject(rawRequest) && Object.hasOwn(rawRequest, "schema")) {
    const withSchema = requireExactKeys(rawRequest, [
      "schema",
      "run_id",
      "slug",
      "mode",
      "request_fingerprint",
      "prompt",
      "attachments",
      "created_at",
      "event_id",
    ]);
    if (withSchema.schema !== REQUEST_SCHEMA) fail("request schema is invalid");
    const { schema: _schema, ...withoutSchema } = withSchema;
    requestInput = withoutSchema;
  }
  const request = normalizeRequest(requestInput);
  return Object.freeze({
    schema: REQUEST_SCHEMA,
    run_id: request.run_id,
    slug: request.slug,
    mode: request.mode,
    request_fingerprint: request.request_fingerprint,
    attachment_count: request.attachments.length,
    created_at: request.created_at,
  });
}

function normalizeEvent(rawEvent) {
  const event = requireExactKeys(
    rawEvent,
    [
      "event_id",
      "run_id",
      "state",
      "revision",
      "observed_at",
      "source",
      "receipt_hash",
    ],
    ["code", "target_fingerprint", "result_sha256"],
  );
  if (!STATES.includes(event.state)) fail("event state is invalid");
  if (!EVENT_SOURCES.has(event.source)) fail("event source is invalid");
  const normalized = {
    schema: EVENT_SCHEMA,
    event_id: requireSafeIdentifier(event.event_id, "event_id"),
    run_id: requireSafeIdentifier(event.run_id, "run_id", RUN_ID_PATTERN),
    state: event.state,
    revision: requireInteger(event.revision, "event revision"),
    observed_at: requireTimestamp(event.observed_at, "event observed_at"),
    source: event.source,
    receipt_hash: requireSha256(event.receipt_hash, "event receipt_hash"),
  };
  if (Object.hasOwn(event, "code")) {
    normalized.code = requireSafeIdentifier(event.code, "event code", CODE_PATTERN);
  }
  if (Object.hasOwn(event, "target_fingerprint")) {
    normalized.target_fingerprint = requireSha256(
      event.target_fingerprint,
      "target_fingerprint",
    );
  }
  if (Object.hasOwn(event, "result_sha256")) {
    normalized.result_sha256 = requireSha256(
      event.result_sha256,
      "result_sha256",
    );
  }
  const encoded = canonicalJson(normalized);
  if (SENSITIVE_LOG_PATTERN.test(encoded)) {
    fail("event contains sensitive log text");
  }
  if (Buffer.byteLength(encoded, "utf8") > 4096) {
    fail("event exceeds the durable append limit");
  }
  return normalized;
}

export async function readRunRequest(layout) {
  layout = requireRunArtifactLayout(layout);
  await assertPrivateDirectory(layout.directory, "run directory");
  let request;
  try {
    request = JSON.parse(
      await readPrivateFile(layout.request, "request file", { allowEmpty: false }),
    );
  } catch (error) {
    if (error?.message?.startsWith("oracle-subagent artifacts:")) throw error;
    fail("request file is not valid JSON");
  }
  if (request.schema !== REQUEST_SCHEMA) fail("request schema is invalid");
  const { schema, ...withoutSchema } = request;
  const normalized = normalizeRequest(withoutSchema);
  if (normalized.run_id !== layout.run_id) {
    fail("request file is not bound to this run");
  }
  return normalized;
}

export async function readRunEvents(layout) {
  layout = requireRunArtifactLayout(layout);
  await assertPrivateDirectory(layout.directory, "run directory");
  const encoded = await readPrivateFile(layout.events, "events file");
  if (!encoded) return [];
  if (!encoded.endsWith("\n")) fail("events log has a torn final record");
  const events = encoded
    .slice(0, -1)
    .split("\n")
    .map((line, index) => {
      let event;
      try {
        event = JSON.parse(line);
      } catch {
        fail(`event ${index} is not valid JSON`);
      }
      if (event.schema !== EVENT_SCHEMA) fail(`event ${index} schema is invalid`);
      const { schema, ...withoutSchema } = event;
      return normalizeEvent(withoutSchema);
    });
  const eventIds = new Set();
  for (const [index, event] of events.entries()) {
    if (eventIds.has(event.event_id)) fail("events log has a duplicate event_id");
    eventIds.add(event.event_id);
    if (event.run_id !== layout.run_id) fail("events log is not run-bound");
    if (event.revision !== index) fail("events log revisions are not contiguous");
    if (
      index > 0 &&
      Date.parse(event.observed_at) < Date.parse(events[index - 1].observed_at)
    ) {
      fail("events log timestamps regress");
    }
  }
  return events;
}

async function requireReceiptProjection(layout, event) {
  const receipt = await readReceiptFile(layout.receipt);
  const head = receipt.history.at(-1);
  const expected = {
    event_id: head.event_id,
    run_id: receipt.run_id,
    state: receipt.state,
    revision: receipt.revision,
    observed_at: head.observed_at,
    source: head.evidence.source,
    receipt_hash: receipt.receipt_hash,
  };
  if (receipt.error) expected.code = receipt.error.code;
  if (receipt.target) {
    expected.target_fingerprint = identifierFingerprint(receipt.target.id);
  }
  if (receipt.result) expected.result_sha256 = receipt.result.sha256;
  if (canonicalJson(event) !== canonicalJson({ schema: EVENT_SCHEMA, ...expected })) {
    fail("event does not exactly project the current receipt head");
  }
}

export async function appendRunEvent(layout, rawEvent) {
  layout = requireRunArtifactLayout(layout);
  const event = normalizeEvent(rawEvent);
  if (event.run_id !== layout.run_id) fail("event is not bound to this run");
  return withReceiptFileLock(layout.receipt, async () => {
    await requireReceiptProjection(layout, event);
    const existing = await readRunEvents(layout);
    if (event.revision !== existing.length) {
      fail("event revision does not append to the current log");
    }
    if (existing.some((item) => item.event_id === event.event_id)) {
      fail("event_id already exists");
    }
    if (
      existing.length > 0 &&
      Date.parse(event.observed_at) <
        Date.parse(existing.at(-1).observed_at)
    ) {
      fail("event timestamp precedes the current log");
    }
    const flags =
      fsConstants.O_APPEND |
      fsConstants.O_WRONLY |
      (fsConstants.O_NOFOLLOW ?? 0) |
      (fsConstants.O_CLOEXEC ?? 0);
    const handle = await open(layout.events, flags);
    try {
      assertPrivateFileMetadata(await handle.stat(), "events file");
      await handle.writeFile(`${canonicalJson(event)}\n`);
      await handle.sync();
    } finally {
      await handle.close();
    }
    await fsyncDirectory(layout.directory);
    return event;
  });
}

export async function writeRunResult(layout, content) {
  layout = requireRunArtifactLayout(layout);
  await assertPrivateDirectory(layout.directory, "run directory");
  return withReceiptFileLock(layout.receipt, async () => {
    const receipt = await readReceiptFile(layout.receipt);
    if (TERMINAL_STATES.includes(receipt.state)) {
      fail("cannot replace a result after the receipt is terminal");
    }
    const result = await writeResultAtomic(layout.result, content, {
      runId: layout.run_id,
    });
    await assertPrivateFile(layout.result, "result file", { allowEmpty: false });
    await assertPrivateFile(result.proof_path, "result proof file", {
      allowEmpty: false,
    });
    return result;
  });
}

export async function verifyRunArtifactPermissions(
  layout,
  { requireResult = false } = {},
) {
  layout = requireRunArtifactLayout(layout);
  await assertPrivateDirectory(layout.root, "artifact root");
  await assertPrivateDirectory(layout.directory, "run directory");
  await assertPrivateFile(layout.request, "request file", { allowEmpty: false });
  await assertPrivateFile(layout.events, "events file");
  await assertPrivateFile(layout.receipt, "receipt file", { allowEmpty: false });
  if (requireResult) {
    await assertPrivateFile(layout.result, "result file", { allowEmpty: false });
    await assertPrivateFile(
      `${layout.result}.oracle-write-proof.json`,
      "result proof file",
      { allowEmpty: false },
    );
  }
  return true;
}
