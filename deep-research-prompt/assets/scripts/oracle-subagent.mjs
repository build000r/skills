#!/usr/bin/env node

import { spawn } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { constants as fsConstants } from "node:fs";
import {
  chmod,
  mkdir,
  open,
  readFile,
  realpath,
  rename,
  unlink,
} from "node:fs/promises";
import { homedir } from "node:os";
import {
  dirname,
  extname,
  isAbsolute,
  join,
  resolve,
} from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import {
  createRunArtifacts,
  runArtifactLayout,
  REQUEST_SCHEMA,
} from "./oracle-subagent-artifacts.mjs";
import {
  renderRequestWithSnapshot,
  runOracleSubagentAdapter,
} from "./oracle-subagent-adapters.mjs";
import {
  authPageProbeSource,
  evaluateAuthDoctor,
  readAuthPolicy,
} from "./oracle-subagent-auth.mjs";
import {
  createLoopbackCdpTransport,
} from "./chatgpt-composer.mjs";
import {
  resumeOracleRun,
} from "./oracle-subagent-resume.mjs";
import {
  readReceiptFile,
  TERMINAL_STATES,
  transitionReceiptFile,
} from "./oracle-subagent-state.mjs";

export const CLI_RESULT_SCHEMA = "oracle-subagent.cli-result.v1";
export const WORKER_CONTROL_SCHEMA =
  "oracle-subagent.worker-control.v1";
export const BROWSER_POOL_SCHEMA =
  "oracle-subagent.browser-pool.v1";

const THIS_FILE = fileURLToPath(import.meta.url);
const SKILL_ROOT = resolve(dirname(THIS_FILE), "../..");
const DEFAULT_ARTIFACT_ROOT = join(
  homedir(),
  ".oracle",
  "oracle-subagent",
  "runs",
);
const DEFAULT_ORACLE_BINARY = "/opt/homebrew/bin/oracle";
const DEFAULT_MODEL = "gpt-5.4-pro";
const AUTH_POLICY_PATH = join(
  homedir(),
  ".oracle",
  "oracle-subagent",
  "auth-policy.json",
);
const DEFAULT_TIMEOUT_SECONDS = 7_200;
// A fresh launcher invocation mints a new blank target. The auth doctor cannot
// classify account, plan, or composer until that tab hydrates, so its first
// observation is not evidence of a blocked session.
const BROWSER_SETTLE_DEADLINE_MS = 15_000;
const BROWSER_SETTLE_POLL_MS = 500;
const MAX_TIMEOUT_SECONDS = 24 * 60 * 60;
const WORKER_DEADLINE_SECONDS = 12 * 60 * 60;
const QUEUE_LEASE_SECONDS = 24 * 60 * 60;
const MAX_INPUT_BYTES = 32 * 1024 * 1024;
const TERMINAL_SET = new Set(TERMINAL_STATES);
const STARTED_STATES = new Set([
  "started",
  "completed",
  "delivery_failed",
]);
const UNSUCCESSFUL_STATES = new Set([
  "failed",
  "timed_out",
  "cancelled",
  "delivery_failed",
]);
const RUN_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$/;
const SLUG_PATTERN = /^[a-z0-9][a-z0-9-]{0,79}$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const TARGET_ID_PATTERN = /^[A-Za-z0-9_-]{8,128}$/;
const SAFE_CODE_PATTERN = /^[a-z][a-z0-9_]{1,63}$/;
const RESUME_DIRECTIVES = new Set([
  "backpressure",
  "execute",
  "monitor",
  "reattached",
  "reconcile_submission",
  "repair_required",
  "restart_worker",
  "terminal",
  "wait",
]);
const SENSITIVE_PATTERN =
  /(?:authorization|bearer|cookie|password|prompt|secret|session[_-]?token|token|https?:\/\/)/i;
const MEDIA_TYPES = Object.freeze({
  ".csv": "text/csv",
  ".gif": "image/gif",
  ".htm": "text/html",
  ".html": "text/html",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".json": "application/json",
  ".md": "text/markdown",
  ".pdf": "application/pdf",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".txt": "text/plain",
  ".webp": "image/webp",
  ".xml": "application/xml",
});

const HELP = `usage: oracle-subagent <command> [options]

Commands:
  run       create or reattach a run and start its hidden browser worker
  status    read one run without changing it
  wait      wait for a run to start or finish

Run:
  oracle-subagent run --slug NAME [--prompt-file PATH | < stdin]
    [--file PATH ...] [--mode pro|deep-research]
    [--wait none|started|completed] [--timeout-seconds N]
    [--result PATH] [--json]
  oracle-subagent run --reattach RUN_ID
    [--wait none|started|completed] [--timeout-seconds N]
    [--result PATH] [--json]

Status:
  oracle-subagent status --run-id RUN_ID [--json]

Wait:
  oracle-subagent wait --run-id RUN_ID
    [--for started|completed] [--timeout-seconds N]
    [--result PATH] [--json]

Common:
  --artifact-root DIR   private run root
  -h, --help            show this help

Prompt text is accepted only from a file or stdin, never from argv.
Machine JSON is one quiet line on stdout.
--timeout-seconds bounds this caller's wait, not detached execution.`;

export class OracleSubagentCliError extends Error {
  constructor(code) {
    super("oracle-subagent cli: rejected");
    this.name = "OracleSubagentCliError";
    this.code = code;
  }
}

function reject(code) {
  throw new OracleSubagentCliError(code);
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

function safeRunId(value, code = "arguments_invalid") {
  if (
    typeof value !== "string" ||
    !RUN_ID_PATTERN.test(value) ||
    SENSITIVE_PATTERN.test(value)
  ) {
    reject(code);
  }
  return value;
}

function safeSlug(value) {
  if (
    typeof value !== "string" ||
    !SLUG_PATTERN.test(value) ||
    SENSITIVE_PATTERN.test(value)
  ) {
    reject("arguments_invalid");
  }
  return value;
}

function safeAbsolutePath(value, code = "arguments_invalid") {
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

function resolvedPath(value) {
  if (typeof value !== "string" || value.length === 0) {
    reject("arguments_invalid");
  }
  return resolve(value);
}

export function normalizeChatGptTargetUrl(
  value,
  code = "target_url_invalid",
) {
  if (typeof value !== "string") reject(code);
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    reject(code);
  }
  if (
    parsed.protocol !== "https:" ||
    parsed.hostname !== "chatgpt.com" ||
    parsed.port ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash ||
    parsed.origin !== "https://chatgpt.com" ||
    parsed.href !== value ||
    value !== `${parsed.origin}${parsed.pathname}` ||
    !(
      parsed.pathname === "/" ||
      /^\/g\/g-p-[A-Za-z0-9_-]{8,128}\/project$/.test(
        parsed.pathname,
      )
    )
  ) {
    reject(code);
  }
  return parsed.href;
}

function configuredTargetUrl() {
  return normalizeChatGptTargetUrl(
    process.env.ORACLE_CHATGPT_PROJECT_URL ??
      "https://chatgpt.com/",
  );
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

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
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

function takeValue(arguments_, index, flag) {
  if (index + 1 >= arguments_.length) reject("arguments_invalid");
  const value = arguments_[index + 1];
  if (value.startsWith("--")) reject("arguments_invalid");
  return [value, index + 1];
}

function commonDefaults(command) {
  return {
    command,
    artifact_root: DEFAULT_ARTIFACT_ROOT,
    json: false,
    help: false,
  };
}

export function parseCliArguments(rawArguments) {
  if (!Array.isArray(rawArguments)) reject("arguments_invalid");
  if (
    rawArguments.length === 0 ||
    rawArguments[0] === "--help" ||
    rawArguments[0] === "-h"
  ) {
    return Object.freeze({
      ...commonDefaults("help"),
      help: true,
    });
  }
  const command = rawArguments[0];
  if (!["run", "status", "wait", "_worker"].includes(command)) {
    reject("arguments_invalid");
  }
  const parsed = commonDefaults(command);
  if (command === "run") {
    Object.assign(parsed, {
      slug: null,
      prompt_file: null,
      files: [],
      mode: "pro",
      wait: "started",
      timeout_seconds: DEFAULT_TIMEOUT_SECONDS,
      result: null,
      reattach: null,
    });
  } else if (command === "status") {
    parsed.run_id = null;
  } else if (command === "wait") {
    Object.assign(parsed, {
      run_id: null,
      for: "completed",
      timeout_seconds: DEFAULT_TIMEOUT_SECONDS,
      result: null,
    });
  } else {
    parsed.control_file = null;
  }

  for (let index = 1; index < rawArguments.length; index += 1) {
    const flag = rawArguments[index];
    if (flag === "--json") {
      parsed.json = true;
      continue;
    }
    if (flag === "--help" || flag === "-h") {
      parsed.help = true;
      continue;
    }
    let value;
    [value, index] = takeValue(rawArguments, index, flag);
    if (flag === "--artifact-root" && command !== "_worker") {
      parsed.artifact_root = resolvedPath(value);
    } else if (flag === "--slug" && command === "run") {
      parsed.slug = safeSlug(value);
    } else if (flag === "--prompt-file" && command === "run") {
      parsed.prompt_file = resolvedPath(value);
    } else if (flag === "--file" && command === "run") {
      parsed.files.push(resolvedPath(value));
    } else if (flag === "--mode" && command === "run") {
      if (!["pro", "deep-research"].includes(value)) {
        reject("arguments_invalid");
      }
      parsed.mode = value;
    } else if (flag === "--wait" && command === "run") {
      if (!["none", "started", "completed"].includes(value)) {
        reject("arguments_invalid");
      }
      parsed.wait = value;
    } else if (flag === "--timeout-seconds" && ["run", "wait"].includes(command)) {
      parsed.timeout_seconds = safeInteger(
        Number(value),
        1,
        MAX_TIMEOUT_SECONDS,
        "arguments_invalid",
      );
    } else if (flag === "--result" && ["run", "wait"].includes(command)) {
      parsed.result = resolvedPath(value);
    } else if (flag === "--reattach" && command === "run") {
      parsed.reattach = safeRunId(value);
    } else if (flag === "--run-id" && ["status", "wait"].includes(command)) {
      parsed.run_id = safeRunId(value);
    } else if (flag === "--for" && command === "wait") {
      if (!["started", "completed"].includes(value)) {
        reject("arguments_invalid");
      }
      parsed.for = value;
    } else if (flag === "--control-file" && command === "_worker") {
      parsed.control_file = resolvedPath(value);
    } else {
      reject("arguments_invalid");
    }
  }

  if (parsed.help) return Object.freeze(parsed);
  if (command === "run") {
    if (parsed.reattach !== null) {
      if (
        parsed.slug !== null ||
        parsed.prompt_file !== null ||
        parsed.files.length > 0
      ) {
        reject("arguments_invalid");
      }
    } else if (parsed.slug === null) {
      reject("arguments_invalid");
    }
    if (parsed.wait !== "completed" && parsed.result !== null) {
      reject("arguments_invalid");
    }
  } else if (command === "status" && parsed.run_id === null) {
    reject("arguments_invalid");
  } else if (command === "wait" && parsed.run_id === null) {
    reject("arguments_invalid");
  } else if (command === "_worker" && parsed.control_file === null) {
    reject("arguments_invalid");
  }
  return Object.freeze({
    ...parsed,
    ...(parsed.files ? { files: Object.freeze([...parsed.files]) } : {}),
  });
}

async function readPrivateInput(pathname, label) {
  let handle;
  try {
    handle = await open(
      safeAbsolutePath(pathname),
      fsConstants.O_RDONLY |
        (fsConstants.O_NOFOLLOW ?? 0) |
        (fsConstants.O_CLOEXEC ?? 0),
    );
    const metadata = await handle.stat();
    if (
      !metadata.isFile() ||
      metadata.size < 1 ||
      metadata.size > MAX_INPUT_BYTES ||
      (typeof process.getuid === "function" &&
        metadata.uid !== process.getuid()) ||
      (await realpath(pathname)) !== pathname
    ) {
      reject(`${label}_invalid`);
    }
    const bytes = await handle.readFile();
    return { bytes, metadata };
  } catch (error) {
    if (error instanceof OracleSubagentCliError) throw error;
    reject(`${label}_invalid`);
  } finally {
    await handle?.close().catch(() => {});
  }
}

async function defaultReadStdin() {
  const chunks = [];
  let total = 0;
  for await (const chunk of process.stdin) {
    const bytes = Buffer.from(chunk);
    total += bytes.length;
    if (total > MAX_INPUT_BYTES) reject("stdin_invalid");
    chunks.push(bytes);
  }
  const result = Buffer.concat(chunks);
  if (result.length === 0) reject("stdin_invalid");
  return result;
}

async function attachmentFor(pathname) {
  const { bytes } = await readPrivateInput(pathname, "attachment");
  return Object.freeze({
    path: pathname,
    bytes: bytes.length,
    sha256: sha256(bytes),
    media_type:
      MEDIA_TYPES[extname(pathname).toLowerCase()] ??
      "application/octet-stream",
  });
}

function requestFingerprint(mode, prompt, attachments) {
  const hash = createHash("sha256");
  hash.update(`${mode}\0`, "utf8");
  hash.update(prompt, "utf8");
  for (const attachment of attachments) {
    hash.update("\0");
    hash.update(attachment.sha256, "ascii");
    hash.update("\0");
    hash.update(attachment.media_type, "ascii");
  }
  return hash.digest("hex");
}

function createIdentifiers(now) {
  const suffix = randomUUID();
  const compact = now.replace(/[-:.TZ]/g, "").slice(0, 14);
  return {
    run_id: `run-${compact}-${suffix}`,
    event_id: `event-created-${suffix}`,
    owner_id: `cli:${suffix}`,
  };
}

async function materializeRunInputs(
  layout,
  {
    run_id: runId,
    slug,
    mode,
    request_fingerprint: requestFingerprintValue,
    prompt,
    attachments,
    created_at: createdAt,
    event_id: eventId,
  },
) {
  const inputDirectory = join(layout.directory, "inputs");
  try {
    await mkdir(inputDirectory, { mode: 0o700 });
    if ((await realpath(inputDirectory)) !== inputDirectory) {
      reject("input_snapshot_failed");
    }
  } catch {
    reject("input_snapshot_failed");
  }
  const snapshots = [];
  for (let index = 0; index < attachments.length; index += 1) {
    const attachment = attachments[index];
    const { bytes } = await readPrivateInput(
      attachment.path,
      "attachment",
    );
    if (
      bytes.length !== attachment.bytes ||
      sha256(bytes) !== attachment.sha256
    ) {
      reject("input_changed");
    }
    const suffix = extname(attachment.path).toLowerCase();
    const snapshotPath = join(
      inputDirectory,
      `${String(index).padStart(3, "0")}-${attachment.sha256}${suffix}`,
    );
    let handle;
    try {
      handle = await open(
        snapshotPath,
        fsConstants.O_CREAT |
          fsConstants.O_EXCL |
          fsConstants.O_WRONLY |
          (fsConstants.O_NOFOLLOW ?? 0),
        0o400,
      );
      await handle.writeFile(bytes);
      await handle.sync();
    } catch {
      reject("input_snapshot_failed");
    } finally {
      await handle?.close().catch(() => {});
    }
    snapshots.push({
      path: snapshotPath,
      bytes: bytes.length,
      sha256: attachment.sha256,
      media_type: attachment.media_type,
    });
  }
  const request = {
    schema: REQUEST_SCHEMA,
    run_id: runId,
    slug,
    mode,
    request_fingerprint: requestFingerprintValue,
    prompt,
    attachments: snapshots,
    created_at: createdAt,
    event_id: eventId,
  };
  const temporary = join(
    layout.directory,
    `.request-snapshot.${randomUUID()}.tmp`,
  );
  let handle;
  try {
    handle = await open(
      temporary,
      fsConstants.O_CREAT |
        fsConstants.O_EXCL |
        fsConstants.O_WRONLY |
        (fsConstants.O_NOFOLLOW ?? 0),
      0o400,
    );
    await handle.writeFile(`${JSON.stringify(request)}\n`);
    await handle.sync();
    await handle.close();
    handle = undefined;
    await rename(temporary, layout.request);
    await chmod(layout.request, 0o400);
  } catch {
    reject("input_snapshot_failed");
  } finally {
    await handle?.close().catch(() => {});
    await unlink(temporary).catch(() => {});
  }
  return Object.freeze(snapshots.map(Object.freeze));
}

function resultPathFromReceipt(receipt) {
  return receipt.result?.path ?? null;
}

function publicStatus(command, receipt, extras = {}) {
  return Object.freeze({
    schema: CLI_RESULT_SCHEMA,
    command,
    ok: !UNSUCCESSFUL_STATES.has(receipt.state),
    run_id: receipt.run_id,
    slug: receipt.slug,
    mode: receipt.mode,
    state: receipt.state,
    revision: receipt.revision,
    terminal: TERMINAL_SET.has(receipt.state),
    result_path: resultPathFromReceipt(receipt),
    result_bytes: receipt.result?.bytes ?? null,
    ...extras,
  });
}

async function atomicCopyResult(source, destination) {
  source = safeAbsolutePath(source, "result_invalid");
  destination = safeAbsolutePath(destination, "result_invalid");
  const { bytes } = await readPrivateInput(source, "result");
  const parent = dirname(destination);
  const temporary = join(
    parent,
    `.oracle-subagent-result.${randomUUID()}.tmp`,
  );
  let handle;
  try {
    handle = await open(
      temporary,
      fsConstants.O_CREAT |
        fsConstants.O_EXCL |
        fsConstants.O_WRONLY |
        (fsConstants.O_NOFOLLOW ?? 0),
      0o600,
    );
    await handle.writeFile(bytes);
    await handle.sync();
    await handle.close();
    handle = undefined;
    await rename(temporary, destination);
    await chmod(destination, 0o600);
  } catch {
    reject("result_write_failed");
  } finally {
    await handle?.close().catch(() => {});
    await unlink(temporary).catch(() => {});
  }
  return destination;
}

async function readStatus(artifactRoot, runId, command = "status") {
  const layout = runArtifactLayout(artifactRoot, runId);
  const receipt = await readReceiptFile(layout.receipt);
  return publicStatus(command, receipt);
}

async function waitForRun(
  artifactRoot,
  runId,
  waitFor,
  timeoutSeconds,
  resultDestination,
  dependencies,
) {
  const deadline = dependencies.nowMs() + timeoutSeconds * 1_000;
  while (true) {
    const layout = runArtifactLayout(artifactRoot, runId);
    const receipt = await readReceiptFile(layout.receipt);
    const reached =
      waitFor === "started"
        ? STARTED_STATES.has(receipt.state) ||
          TERMINAL_SET.has(receipt.state)
        : TERMINAL_SET.has(receipt.state);
    if (reached) {
      let copied = null;
      if (resultDestination !== null) {
        if (!["completed", "delivery_failed"].includes(receipt.state)) {
          reject("result_unavailable");
        }
        copied = await atomicCopyResult(
          receipt.result.path,
          resultDestination,
        );
      }
      return publicStatus("wait", receipt, {
        waited_for: waitFor,
        result_written: copied,
      });
    }
    if (dependencies.nowMs() >= deadline) reject("wait_timeout");
    await dependencies.sleep(100);
  }
}

async function writeWorkerControl(layout, rawControl) {
  const control = normalizeWorkerControl(rawControl);
  const controlId = sha256(canonicalJson(control)).slice(0, 24);
  const pathname = join(
    layout.directory,
    `worker-control-${controlId}.json`,
  );
  let handle;
  try {
    handle = await open(
      pathname,
      fsConstants.O_CREAT |
        fsConstants.O_EXCL |
        fsConstants.O_WRONLY |
        (fsConstants.O_NOFOLLOW ?? 0),
      0o600,
    );
    await handle.writeFile(`${JSON.stringify(control)}\n`);
    await handle.sync();
  } catch (error) {
    if (error?.code === "EEXIST") {
      const existing = await readWorkerControl(pathname);
      if (JSON.stringify(existing) === JSON.stringify(control)) {
        return pathname;
      }
    }
    reject("worker_control_failed");
  } finally {
    await handle?.close().catch(() => {});
  }
  return pathname;
}

function normalizeWorkerControl(raw) {
  const value = exactObject(
    raw,
    [
      "schema",
      "artifact_root",
      "run_id",
      "request_fingerprint",
      "owner_id",
      "queue_config",
      "oracle_binary",
      "manifest_path",
      "cdp_endpoint",
      "target_id",
      "target_url",
      "model",
      "deadline_at",
    ],
    [],
    "worker_control_invalid",
  );
  if (
    value.schema !== WORKER_CONTROL_SCHEMA ||
    !SHA256_PATTERN.test(value.request_fingerprint) ||
    typeof value.owner_id !== "string" ||
    typeof value.queue_config !== "object" ||
    typeof value.oracle_binary !== "string" ||
    typeof value.model !== "string" ||
    typeof value.deadline_at !== "string"
  ) {
    reject("worker_control_invalid");
  }
  return Object.freeze({
    ...value,
    artifact_root: safeAbsolutePath(
      value.artifact_root,
      "worker_control_invalid",
    ),
    run_id: safeRunId(value.run_id, "worker_control_invalid"),
    oracle_binary: safeAbsolutePath(
      value.oracle_binary,
      "worker_control_invalid",
    ),
    manifest_path: safeAbsolutePath(
      value.manifest_path,
      "worker_control_invalid",
    ),
  });
}

function normalizePreparedRun(raw) {
  const value = exactObject(
    raw,
    ["run_id", "start_worker", "control"],
    ["directive"],
    "prepare_result_invalid",
  );
  const runId = safeRunId(value.run_id, "prepare_result_invalid");
  const directive =
    value.directive ??
    (value.start_worker ? "execute" : "reattached");
  if (typeof value.start_worker !== "boolean") {
    reject("prepare_result_invalid");
  }
  if (!RESUME_DIRECTIVES.has(directive)) {
    reject("prepare_result_invalid");
  }
  if (value.start_worker) {
    if (value.control === null) {
      reject("prepare_result_invalid");
    }
    const control = normalizeWorkerControl(value.control);
    if (control.run_id !== runId) reject("prepare_result_invalid");
    return Object.freeze({
      run_id: runId,
      start_worker: true,
      control,
      directive,
    });
  }
  if (value.control !== null) reject("prepare_result_invalid");
  return Object.freeze({
    run_id: runId,
    start_worker: false,
    control: null,
    directive,
  });
}

async function readWorkerControl(pathname) {
  const { bytes } = await readPrivateInput(pathname, "worker_control");
  try {
    return normalizeWorkerControl(JSON.parse(bytes.toString("utf8")));
  } catch (error) {
    if (error instanceof OracleSubagentCliError) throw error;
    reject("worker_control_invalid");
  }
}

async function childJson(command, arguments_) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(command, arguments_, {
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderrBytes = 0;
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      if (stdout.length < 1024 * 1024) stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderrBytes += chunk.length;
    });
    child.once("error", () => rejectPromise(new Error("child_failed")));
    child.once("exit", (code) => {
      if (code !== 0 || stderrBytes > 64 * 1024) {
        rejectPromise(new Error("child_failed"));
        return;
      }
      try {
        resolvePromise(JSON.parse(stdout));
      } catch {
        rejectPromise(new Error("child_invalid"));
      }
    });
  });
}

function browserPoolPath(artifactRoot) {
  return join(artifactRoot, ".oracle-subagent-browser-pool.json");
}

function normalizeBrowserPool(raw, requestedTargetUrl) {
  const value = exactObject(
    raw,
    [
      "schema",
      "target_id",
      "target_url",
      "port",
      "profile_root",
      "profile_directory",
    ],
    [],
    "browser_pool_invalid",
  );
  if (
    value.schema !== BROWSER_POOL_SCHEMA ||
    typeof value.target_id !== "string" ||
    !TARGET_ID_PATTERN.test(value.target_id) ||
    typeof value.profile_directory !== "string" ||
    value.profile_directory.length < 1 ||
    value.profile_directory.includes("/") ||
    value.profile_directory.includes("\0")
  ) {
    reject("browser_pool_invalid");
  }
  const targetUrl = normalizeChatGptTargetUrl(
    value.target_url,
    "browser_pool_invalid",
  );
  if (targetUrl !== requestedTargetUrl) {
    reject("browser_pool_invalid");
  }
  return Object.freeze({
    schema: BROWSER_POOL_SCHEMA,
    target_id: value.target_id,
    target_url: targetUrl,
    port: safeInteger(
      value.port,
      1,
      65_535,
      "browser_pool_invalid",
    ),
    profile_root: safeAbsolutePath(
      value.profile_root,
      "browser_pool_invalid",
    ),
    profile_directory: value.profile_directory,
  });
}

async function readBrowserPool(
  artifactRoot,
  requestedTargetUrl = configuredTargetUrl(),
) {
  const pathname = browserPoolPath(artifactRoot);
  let handle;
  try {
    handle = await open(
      pathname,
      fsConstants.O_RDONLY |
        (fsConstants.O_NOFOLLOW ?? 0) |
        (fsConstants.O_CLOEXEC ?? 0),
    );
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    reject("browser_pool_invalid");
  }
  try {
    const metadata = await handle.stat();
    if (
      !metadata.isFile() ||
      metadata.size < 1 ||
      metadata.size > 64 * 1024 ||
      (metadata.mode & 0o077) !== 0 ||
      (typeof process.getuid === "function" &&
        metadata.uid !== process.getuid()) ||
      (await realpath(pathname)) !== pathname
    ) {
      reject("browser_pool_invalid");
    }
    return normalizeBrowserPool(
      JSON.parse(await handle.readFile("utf8")),
      requestedTargetUrl,
    );
  } catch (error) {
    if (error instanceof OracleSubagentCliError) throw error;
    reject("browser_pool_invalid");
  } finally {
    await handle.close().catch(() => {});
  }
}

async function publishBrowserPool(
  artifactRoot,
  browser,
  requestedTargetUrl = configuredTargetUrl(),
) {
  const pool = normalizeBrowserPool({
    schema: BROWSER_POOL_SCHEMA,
    target_id: browser.target_id,
    target_url: browser.target_url,
    port: browser.port,
    profile_root: browser.profile_root,
    profile_directory: browser.profile_directory,
  }, requestedTargetUrl);
  const pathname = browserPoolPath(artifactRoot);
  let handle;
  try {
    handle = await open(
      pathname,
      fsConstants.O_CREAT |
        fsConstants.O_EXCL |
        fsConstants.O_WRONLY |
        (fsConstants.O_NOFOLLOW ?? 0),
      0o600,
    );
    await handle.writeFile(`${JSON.stringify(pool)}\n`);
    await handle.sync();
    return pool;
  } catch (error) {
    if (error?.code === "EEXIST") {
      return readBrowserPool(artifactRoot, requestedTargetUrl);
    }
    reject("browser_pool_write_failed");
  } finally {
    await handle?.close().catch(() => {});
  }
}

async function closeUnusedTarget(endpoint, targetId) {
  let response;
  try {
    response = await fetch(
      `${endpoint}/json/close/${encodeURIComponent(targetId)}`,
      {
        method: "GET",
        redirect: "error",
        cache: "no-store",
      },
    );
  } catch {
    reject("browser_pool_cleanup_failed");
  }
  if (!response.ok) reject("browser_pool_cleanup_failed");
}

export async function proveStableTarget(
  browser,
  pool,
  requestedTargetUrl = configuredTargetUrl(),
  injected = {},
) {
  const dependencies = {
    createTransport: createLoopbackCdpTransport,
    nowMs: () => Date.now(),
    sleep: (milliseconds) =>
      new Promise((resolvePromise) =>
        setTimeout(resolvePromise, milliseconds),
      ),
    closeTarget: closeUnusedTarget,
    readPolicy: readAuthPolicy,
    evaluateDoctor: evaluateAuthDoctor,
    ...injected,
  };
  if (
    pool.port !== browser.port ||
    pool.profile_root !== browser.profile_root ||
    pool.profile_directory !== browser.profile_directory ||
    pool.target_url !== requestedTargetUrl ||
    browser.target_url !== requestedTargetUrl
  ) {
    reject("browser_pool_context_changed");
  }
  const endpoint = `http://127.0.0.1:${pool.port}`;
  const transport = dependencies.createTransport(endpoint);
  let targets = await transport.listTargets();
  let target = targets.find((candidate) => candidate.id === pool.target_id);
  if (!target) reject("browser_pool_target_lost");
  const navigationDeadline = dependencies.nowMs() + 30_000;
  if (target.url !== requestedTargetUrl) {
    await transport.evaluate(
      pool.target_id,
      `location.replace(${JSON.stringify(requestedTargetUrl)}); true`,
    );
    do {
      await dependencies.sleep(100);
      targets = await transport.listTargets();
      target = targets.find(
        (candidate) => candidate.id === pool.target_id,
      );
      if (target?.url === requestedTargetUrl) break;
    } while (dependencies.nowMs() < navigationDeadline);
  }
  if (target?.url !== requestedTargetUrl) {
    reject("browser_pool_navigation_failed");
  }
  let composerReady = false;
  const exactComposerExpression =
    `location.href === ${JSON.stringify(requestedTargetUrl)} && ` +
    `document.readyState === "complete" && ` +
    `Boolean(document.querySelector("#prompt-textarea[contenteditable='true'],[contenteditable='true'][role='textbox']"))`;
  do {
    try {
      composerReady =
        (await transport.evaluate(
          pool.target_id,
          exactComposerExpression,
        )) === true;
    } catch {
      composerReady = false;
    }
    if (composerReady) break;
    await dependencies.sleep(100);
  } while (dependencies.nowMs() < navigationDeadline);
  if (!composerReady) reject("browser_pool_navigation_failed");
  const authProof = await transport.evaluate(
    pool.target_id,
    `(async()=>{${authPageProbeSource()}
if (!(${exactComposerExpression})) {
  return { exact_target: false, observation: null };
}
const observation = await authPageProbe(
  ${JSON.stringify(requestedTargetUrl)},
  canonicalProCapability,
  deriveAccountCapability
);
return {
  exact_target: (${exactComposerExpression}),
  observation
};
})()`,
  );
  if (
    !isPlainObject(authProof) ||
    authProof.exact_target !== true ||
    !isPlainObject(authProof.observation)
  ) {
    reject("browser_pool_navigation_failed");
  }
  const observation = authProof.observation;
  observation.profile_fingerprint = sha256(
    `${pool.profile_root}\0${pool.profile_directory}`,
  );
  const policy = await dependencies.readPolicy(AUTH_POLICY_PATH);
  const now = new Date(dependencies.nowMs()).toISOString();
  const report = dependencies.evaluateDoctor({
    receipt_observed_at: now,
    observation,
    policy,
    security: {
      runtime_private: true,
      receipt_private: true,
      profile_private: true,
      policy_private: true,
    },
    transport: {
      single_listener: true,
      loopback_only: true,
      pid_matches: true,
      target_matches: authProof.exact_target,
      hidden: true,
    },
    now,
  });
  if (!report.ok) reject("browser_pool_auth_blocked");
  if (browser.target_id !== pool.target_id) {
    await dependencies.closeTarget(endpoint, browser.target_id);
  }
  return Object.freeze({ pool, endpoint });
}

function validateBrowserPreflight(
  browser,
  authReport,
  requestedTargetUrl = configuredTargetUrl(),
) {
  if (
    browser?.schema !== "oracle-subagent.browser.v1" ||
    browser.state !== "ready" ||
    browser.production_evidence !== true ||
    browser.submit_performed !== false ||
    browser.bind !== "127.0.0.1" ||
    browser.visibility !== "hidden-headful" ||
    browser.visibility_verified !== true ||
    browser.target_observed !== true ||
    typeof browser.target_id !== "string" ||
    browser.target_url !== requestedTargetUrl ||
    !Number.isSafeInteger(browser.pid) ||
    !Number.isSafeInteger(browser.port) ||
    authReport?.ok !== true ||
    authReport.state !== "ready"
  ) {
    reject("browser_preflight_blocked");
  }
  return browser;
}

async function launchVerifiedBrowser() {
  const launcher = join(
    SKILL_ROOT,
    "assets",
    "scripts",
    "launch-chatgpt-cdp.sh",
  );
  const auth = join(
    SKILL_ROOT,
    "assets",
    "scripts",
    "oracle-subagent-auth.mjs",
  );
  let browser;
  try {
    browser = await childJson(launcher, ["--json"]);
  } catch {
    reject("browser_preflight_failed");
  }
  const sleep = (milliseconds) =>
    new Promise((resolvePromise) =>
      setTimeout(resolvePromise, milliseconds),
    );
  const deadline = Date.now() + BROWSER_SETTLE_DEADLINE_MS;
  let authReport = null;
  for (;;) {
    try {
      authReport = await childJson(process.execPath, [
        auth,
        "doctor",
        "--json",
      ]);
    } catch {
      authReport = null;
    }
    if (authReport?.ok === true && authReport.state === "ready") break;
    if (Date.now() >= deadline) break;
    await sleep(BROWSER_SETTLE_POLL_MS);
  }
  if (!authReport) {
    reject("browser_preflight_failed");
  }
  return validateBrowserPreflight(
    browser,
    authReport,
    configuredTargetUrl(),
  );
}

export async function prepareOracleRun(context, injected = {}) {
  const dependencies = {
    launchBrowser: launchVerifiedBrowser,
    readPool: readBrowserPool,
    publishPool: publishBrowserPool,
    proveTarget: proveStableTarget,
    resume: resumeOracleRun,
    readReceipt: readReceiptFile,
    transitionReceipt: transitionReceiptFile,
    nowMs: () => Date.now(),
    targetUrl: configuredTargetUrl(),
    ...injected,
  };
  let browser = null;
  let pool = await dependencies.readPool(
    context.artifact_root,
    dependencies.targetUrl,
  );
  if (pool === null) {
    browser = validateBrowserPreflight(
      await dependencies.launchBrowser(),
      { ok: true, state: "ready" },
      dependencies.targetUrl,
    );
    pool = await dependencies.publishPool(
      context.artifact_root,
      browser,
      dependencies.targetUrl,
    );
  }
  const queueConfig = {
    target_ids: [pool.target_id],
    max_active: 1,
    max_depth: 8,
    lease_duration_ms: QUEUE_LEASE_SECONDS * 1_000,
  };
  const resumed = await dependencies.resume(
    context.artifact_root,
    {
      request_fingerprint: context.request_fingerprint,
      candidate_run_id: context.candidate_run_id,
      owner_id: context.owner_id,
      now_ms: dependencies.nowMs(),
    },
    queueConfig,
  );
  const mayStart =
    (resumed.directive === "execute" &&
      resumed.send_authorized === true) ||
    (resumed.directive === "restart_worker" &&
      resumed.send_authorized === false);
  if (!mayStart) {
    return Object.freeze({
      run_id: resumed.run_id,
      start_worker: false,
      control: null,
      directive: resumed.directive,
    });
  }
  if (browser === null) {
    browser = validateBrowserPreflight(
      await dependencies.launchBrowser(),
      { ok: true, state: "ready" },
      dependencies.targetUrl,
    );
  }
  const stable = await dependencies.proveTarget(
    browser,
    pool,
    dependencies.targetUrl,
  );
  const layout = runArtifactLayout(
    context.artifact_root,
    resumed.run_id,
  );
  let receipt = await dependencies.readReceipt(layout.receipt);
  const now = new Date(dependencies.nowMs()).toISOString();
  const profileFingerprint = sha256(
    `${pool.profile_root}\0${pool.profile_directory}`,
  );
  if (receipt.state === "created") {
    receipt = await dependencies.transitionReceipt(layout.receipt, {
      to: "auth_ready",
      expectedRevision: receipt.revision,
      eventId: `auth-${randomUUID()}`,
      observedAt: now,
      evidence: {
        run_id: receipt.run_id,
        source: "browser",
        profile_fingerprint: profileFingerprint,
        challenge_observed: false,
      },
    });
  }
  if (receipt.state === "auth_ready") {
    receipt = await dependencies.transitionReceipt(layout.receipt, {
      to: "target_bound",
      expectedRevision: receipt.revision,
      eventId: `target-${randomUUID()}`,
      observedAt: new Date(dependencies.nowMs()).toISOString(),
      evidence: {
        run_id: receipt.run_id,
        source: "browser",
        target_id: pool.target_id,
        target_url: pool.target_url,
        browser_pid: browser.pid,
      },
    });
  }
  if (
    receipt.state !== "target_bound" ||
    receipt.target?.id !== pool.target_id
  ) {
    reject("resume_state_invalid");
  }
  return Object.freeze({
    run_id: receipt.run_id,
    start_worker: true,
    directive: resumed.directive,
    control: {
      schema: WORKER_CONTROL_SCHEMA,
      artifact_root: context.artifact_root,
      run_id: receipt.run_id,
      request_fingerprint: context.request_fingerprint,
      owner_id: context.owner_id,
      queue_config: queueConfig,
      oracle_binary: DEFAULT_ORACLE_BINARY,
      manifest_path: join(
        SKILL_ROOT,
        "tests",
        "fixtures",
        "oracle-capabilities",
        "oracle-0.9.0.json",
      ),
      cdp_endpoint: stable.endpoint,
      target_id: pool.target_id,
      target_url: pool.target_url,
      model: DEFAULT_MODEL,
      deadline_at: new Date(
        dependencies.nowMs() + WORKER_DEADLINE_SECONDS * 1_000,
      ).toISOString(),
    },
  });
}

export function startDetachedWorker(
  controlPath,
  injected = {},
) {
  const spawnImpl = injected.spawnImpl ?? spawn;
  return new Promise((resolvePromise, rejectPromise) => {
    let child;
    try {
      child = spawnImpl(
        process.execPath,
        [THIS_FILE, "_worker", "--control-file", controlPath],
        {
          detached: true,
          stdio: "ignore",
        },
      );
    } catch (error) {
      rejectPromise(error);
      return;
    }
    let settled = false;
    child.once("error", (error) => {
      if (settled) return;
      settled = true;
      rejectPromise(error);
    });
    child.once("spawn", () => {
      if (settled) return;
      settled = true;
      child.unref();
      resolvePromise(child.pid);
    });
  });
}

async function executeNewRun(options, dependencies) {
  const now = new Date(dependencies.nowMs()).toISOString();
  const promptBytes =
    options.prompt_file === null
      ? await dependencies.readStdin()
      : (await readPrivateInput(options.prompt_file, "prompt_file")).bytes;
  const prompt = promptBytes.toString("utf8");
  if (Buffer.byteLength(prompt, "utf8") === 0) {
    reject("prompt_file_invalid");
  }
  const attachments = await Promise.all(
    options.files.map(attachmentFor),
  );
  const fingerprint = requestFingerprint(
    options.mode,
    prompt,
    attachments,
  );
  const identifiers = createIdentifiers(now);
  const request = {
    run_id: identifiers.run_id,
    slug: options.slug,
    mode: options.mode,
    request_fingerprint: fingerprint,
    prompt,
    attachments,
    created_at: now,
    event_id: identifiers.event_id,
  };
  const created = await createRunArtifacts(
    options.artifact_root,
    request,
  );
  try {
    await materializeRunInputs(created.layout, request);
  } catch (error) {
    await markRunFailure(
      options.artifact_root,
      identifiers.run_id,
      error?.code ?? "input_snapshot_failed",
    );
    throw error;
  }
  let prepared;
  try {
    prepared = normalizePreparedRun(
      await dependencies.prepareRun({
        artifact_root: options.artifact_root,
        candidate_run_id: identifiers.run_id,
        request_fingerprint: fingerprint,
        owner_id: identifiers.owner_id,
        timeout_seconds: options.timeout_seconds,
      }),
    );
  } catch (error) {
    await markRunFailure(
      options.artifact_root,
      identifiers.run_id,
      error?.code ?? "preflight_failed",
    );
    throw error;
  }
  const workerPid = await startPreparedWorker(
    options,
    prepared,
    dependencies,
  );
  return finishRunCommand(
    options,
    prepared.run_id,
    workerPid,
    dependencies,
    { resume_directive: prepared.directive },
  );
}

async function startPreparedWorker(options, prepared, dependencies) {
  if (!prepared.start_worker) return null;
  try {
    const controlPath = await writeWorkerControl(
      runArtifactLayout(options.artifact_root, prepared.run_id),
      prepared.control,
    );
    return await dependencies.startWorker(controlPath);
  } catch (error) {
    await markRunFailure(
      options.artifact_root,
      prepared.run_id,
      "worker_start_failed",
    );
    await dependencies
      .resume(
        options.artifact_root,
        {
          request_fingerprint:
            prepared.control.request_fingerprint,
          candidate_run_id: prepared.run_id,
          owner_id: prepared.control.owner_id,
          now_ms: dependencies.nowMs(),
        },
        prepared.control.queue_config,
      )
      .catch(() => {});
    throw error;
  }
}

async function finishRunCommand(
  options,
  runId,
  workerPid,
  dependencies,
  extras = {},
) {
  if (options.wait === "none") {
    const status = await readStatus(options.artifact_root, runId, "run");
    return Object.freeze({
      ...status,
      wait_policy: "none",
      worker_pid: workerPid,
      ...extras,
    });
  }
  const waited = await waitForRun(
    options.artifact_root,
    runId,
    options.wait,
    options.timeout_seconds,
    options.result,
    dependencies,
  );
  return Object.freeze({
    ...waited,
    command: "run",
    wait_policy: options.wait,
    worker_pid: workerPid,
    ...extras,
  });
}

async function executeReattach(options, dependencies) {
  const layout = runArtifactLayout(
    options.artifact_root,
    options.reattach,
  );
  const receipt = await readReceiptFile(layout.receipt);
  if (TERMINAL_SET.has(receipt.state)) {
    return finishRunCommand(
      options,
      options.reattach,
      null,
      dependencies,
      { resume_directive: "terminal" },
    );
  }
  const identifiers = createIdentifiers(
    new Date(dependencies.nowMs()).toISOString(),
  );
  const prepared = normalizePreparedRun(
    await dependencies.prepareRun({
      artifact_root: options.artifact_root,
      candidate_run_id: options.reattach,
      request_fingerprint: receipt.request_fingerprint,
      owner_id: identifiers.owner_id,
      timeout_seconds: options.timeout_seconds,
    }),
  );
  if (prepared.run_id !== options.reattach) {
    reject("reattach_identity_changed");
  }
  const workerPid = await startPreparedWorker(
    options,
    prepared,
    dependencies,
  );
  return finishRunCommand(
    options,
    prepared.run_id,
    workerPid,
    dependencies,
    { resume_directive: prepared.directive },
  );
}

async function markRunFailure(artifactRoot, runId, code) {
  const layout = runArtifactLayout(artifactRoot, runId);
  try {
    const receipt = await readReceiptFile(layout.receipt);
    if (TERMINAL_SET.has(receipt.state)) return;
    const safeCode =
      typeof code === "string" &&
      SAFE_CODE_PATTERN.test(code) &&
      !SENSITIVE_PATTERN.test(code)
        ? code
        : "execution_failed";
    await transitionReceiptFile(layout.receipt, {
      to: "failed",
      expectedRevision: receipt.revision,
      eventId: `failure-${randomUUID()}`,
      observedAt: new Date().toISOString(),
      evidence: {
        run_id: receipt.run_id,
        source: "controller",
        code: safeCode,
        stage: receipt.state,
        ...(receipt.target ? { target_id: receipt.target.id } : {}),
      },
    });
  } catch {
    // A concurrent terminal transition is authoritative.
  }
}

async function markWorkerFailure(control, code) {
  return markRunFailure(control.artifact_root, control.run_id, code);
}

async function readHandleBytes(handle, size) {
  const bytes = Buffer.alloc(size);
  let offset = 0;
  while (offset < size) {
    const read = await handle.read(
      bytes,
      offset,
      size - offset,
      offset,
    );
    if (read.bytesRead === 0) reject("worker_input_invalid");
    offset += read.bytesRead;
  }
  return bytes;
}

async function readWorkerInputBytes(pathname) {
  let handle;
  try {
    handle = await open(
      pathname,
      fsConstants.O_RDONLY |
        (fsConstants.O_NOFOLLOW ?? 0) |
        (fsConstants.O_CLOEXEC ?? 0),
    );
    const before = await handle.stat();
    if (
      !before.isFile() ||
      before.nlink !== 1 ||
      before.size < 1 ||
      before.size > MAX_INPUT_BYTES ||
      (before.mode & 0o777) !== 0o400 ||
      (typeof process.getuid === "function" &&
        before.uid !== process.getuid()) ||
      (await realpath(pathname)) !== pathname
    ) {
      reject("worker_input_invalid");
    }
    const bytes = await readHandleBytes(handle, before.size);
    const after = await handle.stat();
    if (
      before.dev !== after.dev ||
      before.ino !== after.ino ||
      before.size !== after.size ||
      before.ctimeMs !== after.ctimeMs
    ) {
      reject("worker_input_invalid");
    }
    return bytes;
  } catch (error) {
    if (error instanceof OracleSubagentCliError) throw error;
    reject("worker_input_invalid");
  } finally {
    await handle?.close().catch(() => {});
  }
}

function normalizeWorkerRequest(bytes, layout, control) {
  let raw;
  try {
    raw = JSON.parse(bytes.toString("utf8"));
  } catch {
    reject("worker_input_invalid");
  }
  const request = exactObject(
    raw,
    [
      "schema",
      "run_id",
      "slug",
      "mode",
      "request_fingerprint",
      "prompt",
      "attachments",
      "created_at",
      "event_id",
    ],
    [],
    "worker_input_invalid",
  );
  const createdAtMs = Date.parse(request.created_at);
  if (
    request.schema !== REQUEST_SCHEMA ||
    request.run_id !== control.run_id ||
    !SLUG_PATTERN.test(request.slug) ||
    !["pro", "deep-research"].includes(request.mode) ||
    request.request_fingerprint !== control.request_fingerprint ||
    typeof request.prompt !== "string" ||
    Buffer.byteLength(request.prompt, "utf8") < 1 ||
    Buffer.byteLength(request.prompt, "utf8") > MAX_INPUT_BYTES ||
    !Array.isArray(request.attachments) ||
    typeof request.created_at !== "string" ||
    !Number.isFinite(createdAtMs) ||
    new Date(createdAtMs).toISOString() !== request.created_at ||
    typeof request.event_id !== "string"
  ) {
    reject("worker_input_invalid");
  }
  const inputDirectory = join(layout.directory, "inputs");
  const attachments = request.attachments.map((rawAttachment) => {
    const attachment = exactObject(
      rawAttachment,
      ["path", "bytes", "sha256", "media_type"],
      [],
      "worker_input_invalid",
    );
    if (
      dirname(
        safeAbsolutePath(
          attachment.path,
          "worker_input_invalid",
        ),
      ) !== inputDirectory ||
      !Number.isSafeInteger(attachment.bytes) ||
      attachment.bytes < 1 ||
      attachment.bytes > MAX_INPUT_BYTES ||
      !SHA256_PATTERN.test(attachment.sha256) ||
      typeof attachment.media_type !== "string" ||
      !attachment.media_type.includes("/")
    ) {
      reject("worker_input_invalid");
    }
    return Object.freeze({ ...attachment });
  });
  if (
    requestFingerprint(
      request.mode,
      request.prompt,
      attachments,
    ) !== control.request_fingerprint
  ) {
    reject("worker_input_invalid");
  }
  return Object.freeze({
    ...request,
    attachments: Object.freeze(attachments),
  });
}

async function createInputCapability(directory, bytes, label) {
  const pathname = join(
    directory,
    `.worker-input-${label}-${randomUUID()}.tmp`,
  );
  let writer;
  let reader;
  try {
    writer = await open(
      pathname,
      fsConstants.O_CREAT |
        fsConstants.O_EXCL |
        fsConstants.O_WRONLY |
        (fsConstants.O_NOFOLLOW ?? 0),
      0o400,
    );
    await writer.writeFile(bytes);
    await writer.sync();
    await writer.close();
    writer = undefined;
    reader = await open(
      pathname,
      fsConstants.O_RDONLY |
        (fsConstants.O_NOFOLLOW ?? 0) |
        (fsConstants.O_CLOEXEC ?? 0),
    );
    const metadata = await reader.stat();
    if (
      !metadata.isFile() ||
      metadata.nlink !== 1 ||
      metadata.size !== bytes.length ||
      (metadata.mode & 0o777) !== 0o400
    ) {
      reject("worker_input_invalid");
    }
    await unlink(pathname);
    return Object.freeze({
      handle: reader,
      bytes: bytes.length,
      sha256: sha256(bytes),
    });
  } catch (error) {
    await reader?.close().catch(() => {});
    if (error instanceof OracleSubagentCliError) throw error;
    reject("worker_input_invalid");
  } finally {
    await writer?.close().catch(() => {});
    await unlink(pathname).catch(() => {});
  }
}

async function assertInputCapability(capability) {
  const metadata = await capability.handle.stat();
  if (
    !metadata.isFile() ||
    metadata.nlink !== 0 ||
    metadata.size !== capability.bytes ||
    (metadata.mode & 0o777) !== 0o400
  ) {
    reject("worker_input_invalid");
  }
  const bytes = await readHandleBytes(
    capability.handle,
    capability.bytes,
  );
  if (sha256(bytes) !== capability.sha256) {
    reject("worker_input_invalid");
  }
}

async function openWorkerInputs(control) {
  const layout = runArtifactLayout(
    control.artifact_root,
    control.run_id,
  );
  const capabilities = [];
  try {
    const requestBytes = await readWorkerInputBytes(layout.request);
    const request = normalizeWorkerRequest(
      requestBytes,
      layout,
      control,
    );
    capabilities.push(
      await createInputCapability(
        layout.directory,
        requestBytes,
        "request",
      ),
    );
    for (const [index, attachment] of request.attachments.entries()) {
      const attachmentBytes = await readWorkerInputBytes(
        attachment.path,
      );
      if (
        attachmentBytes.length !== attachment.bytes ||
        sha256(attachmentBytes) !== attachment.sha256
      ) {
        reject("worker_input_invalid");
      }
      capabilities.push(
        await createInputCapability(
          layout.directory,
          attachmentBytes,
          `attachment-${index}`,
        ),
      );
    }
    return Object.freeze({
      layout,
      request,
      capabilities: Object.freeze(capabilities),
    });
  } catch (error) {
    await Promise.all(
      capabilities.map((capability) =>
        capability.handle.close().catch(() => {}),
      ),
    );
    throw error;
  }
}

async function renderBoundWorkerRequest(bound, snapshot, context) {
  await Promise.all(
    bound.capabilities.map(assertInputCapability),
  );
  const childPaths = bound.capabilities.map(
    (_capability, index) => `/dev/fd/${index + 3}`,
  );
  const request = Object.freeze({
    ...bound.request,
    attachments: Object.freeze(
      bound.request.attachments.map((attachment, index) =>
        Object.freeze({
          ...attachment,
          path: childPaths[index + 1],
        }),
      ),
    ),
  });
  const layout = Object.freeze({
    ...bound.layout,
    request: childPaths[0],
  });
  return renderRequestWithSnapshot(
    snapshot,
    {
      ...context,
      layout,
      request,
    },
    {
      spawnImpl: (command, arguments_, options) =>
        spawn(command, arguments_, {
          ...options,
          stdio: [
            "ignore",
            "pipe",
            "pipe",
            ...bound.capabilities.map(
              (capability) => capability.handle.fd,
            ),
          ],
        }),
    },
  );
}

async function closeWorkerInputs(bound) {
  if (!bound) return;
  await Promise.all(
    bound.capabilities.map((capability) =>
      capability.handle.close().catch(() => {}),
    ),
  );
}

export async function runWorker(control, injected = {}) {
  const dependencies = {
    runAdapter: runOracleSubagentAdapter,
    resume: resumeOracleRun,
    nowMs: () => Date.now(),
    loadManifest: async (pathname) =>
      JSON.parse(await readFile(pathname, "utf8")),
    ...injected,
  };
  let boundInputs = null;
  let deadlineTimer = null;
  try {
    if (!injected.skipInputVerification) {
      boundInputs = await openWorkerInputs(control);
    }
    const deadlineMs = Date.parse(control.deadline_at);
    if (
      !Number.isFinite(deadlineMs) ||
      deadlineMs <= dependencies.nowMs()
    ) {
      reject("worker_deadline_exceeded");
    }
    if (injected.hardExitOnDeadline === true) {
      deadlineTimer = setTimeout(() => {
        void markWorkerFailure(
          control,
          "worker_deadline_exceeded",
        ).finally(() => process.exit(1));
      }, deadlineMs - dependencies.nowMs());
    }
    const manifest = await dependencies.loadManifest(
      control.manifest_path,
    );
    await dependencies.runAdapter(
      {
        artifact_root: control.artifact_root,
        run_id: control.run_id,
        oracle_binary: control.oracle_binary,
        expected_manifest: manifest,
        cdp_endpoint: control.cdp_endpoint,
        target_id: control.target_id,
        target_url: control.target_url,
        model: control.model,
        deadline_at: control.deadline_at,
      },
      boundInputs
        ? {
            loadRun: async () => ({
              layout: boundInputs.layout,
              request: boundInputs.request,
              receipt: await readReceiptFile(
                boundInputs.layout.receipt,
              ),
            }),
            renderRequest: (snapshot, context) =>
              renderBoundWorkerRequest(
                boundInputs,
                snapshot,
                context,
              ),
          }
        : undefined,
    );
    await dependencies.resume(
      control.artifact_root,
      {
        request_fingerprint: control.request_fingerprint,
        candidate_run_id: control.run_id,
        owner_id: control.owner_id,
        now_ms: dependencies.nowMs(),
      },
      control.queue_config,
    );
    return 0;
  } catch (error) {
    await markWorkerFailure(control, error?.code);
    return 1;
  } finally {
    if (deadlineTimer !== null) clearTimeout(deadlineTimer);
    await closeWorkerInputs(boundInputs);
  }
}

function defaultDependencies() {
  return {
    nowMs: () => Date.now(),
    sleep: (milliseconds) =>
      new Promise((resolvePromise) =>
        setTimeout(resolvePromise, milliseconds),
    ),
    readStdin: defaultReadStdin,
    prepareRun: prepareOracleRun,
    startWorker: startDetachedWorker,
    resume: resumeOracleRun,
  };
}

export async function executeCli(options, injected = {}) {
  const dependencies = { ...defaultDependencies(), ...injected };
  if (options.command === "help" || options.help) {
    return Object.freeze({ help: HELP });
  }
  if (options.command === "status") {
    return readStatus(
      options.artifact_root,
      options.run_id,
      "status",
    );
  }
  if (options.command === "wait") {
    return waitForRun(
      options.artifact_root,
      options.run_id,
      options.for,
      options.timeout_seconds,
      options.result,
      dependencies,
    );
  }
  if (options.command === "run") {
    return options.reattach === null
      ? executeNewRun(options, dependencies)
      : executeReattach(options, dependencies);
  }
  const control = await readWorkerControl(options.control_file);
  return runWorker(control, injected);
}

function emitResult(result, json) {
  if (result?.help) {
    process.stdout.write(`${result.help}\n`);
    return;
  }
  if (json) {
    process.stdout.write(`${JSON.stringify(result)}\n`);
    return;
  }
  process.stdout.write(
    `oracle-subagent ${result.command}: ${result.run_id} ${result.state}${
      result.result_path ? ` ${result.result_path}` : ""
    }\n`,
  );
}

function safeErrorCode(error) {
  const value = error?.code;
  return typeof value === "string" &&
    SAFE_CODE_PATTERN.test(value) &&
    !SENSITIVE_PATTERN.test(value)
    ? value
    : "operation_failed";
}

export async function main(
  rawArguments = process.argv.slice(2),
  injected = {},
) {
  let options;
  try {
    options = parseCliArguments(rawArguments);
    const result = await executeCli(
      options,
      options.command === "_worker"
        ? {
            ...injected,
            hardExitOnDeadline:
              injected.hardExitOnDeadline ?? true,
          }
        : injected,
    );
    if (options.command === "_worker") return result;
    emitResult(result, options.json);
    return options.command === "status" || result.ok !== false ? 0 : 1;
  } catch (error) {
    const code = safeErrorCode(error);
    const json = options?.json ?? rawArguments.includes("--json");
    if (json) {
      process.stdout.write(
        `${JSON.stringify({
          schema: CLI_RESULT_SCHEMA,
          command: options?.command ?? "unknown",
          ok: false,
          error_code: code,
        })}\n`,
      );
    } else {
      process.stderr.write(`oracle-subagent:${code}\n`);
    }
    return 1;
  }
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(resolve(process.argv[1])).href
) {
  process.exitCode = await main();
}
