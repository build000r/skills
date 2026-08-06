#!/usr/bin/env node

import { createHash, randomUUID } from "node:crypto";
import { constants as fsConstants } from "node:fs";
import {
  chmod,
  open,
  realpath,
  rename,
  unlink,
} from "node:fs/promises";
import {
  basename,
  dirname,
  extname,
  isAbsolute,
  join,
  resolve,
} from "node:path";
import { pathToFileURL } from "node:url";

import {
  FLEET_LIMITS,
  ORACLE_FLEET_RECEIPT_SCHEMA,
  ORACLE_FLEET_REQUEST_SCHEMA,
  ORACLE_FLEET_RESPONSE_SCHEMA,
} from "./oracle-rpc-server.mjs";

const MAGIC_DNS_PATTERN =
  /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*$/;
const SAFE_NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._ -]{0,127}$/;
const MEDIA_TYPE_PATTERN =
  /^[a-z0-9][a-z0-9!#$&^_.+-]{0,63}\/[a-z0-9][a-z0-9!#$&^_.+-]{0,63}$/;
const SAFE_CODE_PATTERN = /^[a-z][a-z0-9_]{1,63}$/;
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
const CLIENT_HELP = `usage: oracle-rpc-client (--host MAGICDNS | --endpoint URL) --result PATH [options]

Options:
  --port N              direct-tailnet port (default: 4117)
  --https               use HTTPS with --host
  --prompt-file PATH    prompt source (default: stdin)
  --file PATH           repeatable bounded attachment
  --result PATH         verified private result destination
  -h, --help            show this help

Prompt text is never accepted in argv. The wire request contains prompt text
and inline file bytes only; local paths and credentials are never sent.`;

export class OracleFleetClientError extends Error {
  constructor(code) {
    super("oracle fleet client: rejected");
    this.name = "OracleFleetClientError";
    this.code = code;
  }
}

function reject(code) {
  throw new OracleFleetClientError(code);
}

function isPlainObject(value) {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.getPrototypeOf(value) === Object.prototype
  );
}

function exactObject(value, required, code) {
  if (!isPlainObject(value)) reject(code);
  if (
    Object.keys(value).length !== required.length ||
    required.some((key) => !Object.hasOwn(value, key))
  ) {
    reject(code);
  }
  return value;
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function isIpLiteral(value) {
  return /^\d{1,3}(?:\.\d{1,3}){3}$/.test(value) || value.includes(":");
}

export function normalizeOracleFleetEndpoint(value) {
  let endpoint;
  try {
    endpoint = new URL(value);
  } catch {
    reject("endpoint_invalid");
  }
  const hostname = endpoint.hostname.toLowerCase();
  if (
    !["http:", "https:"].includes(endpoint.protocol) ||
    endpoint.username ||
    endpoint.password ||
    endpoint.search ||
    endpoint.hash ||
    endpoint.pathname !== "/v1/oracle" ||
    !MAGIC_DNS_PATTERN.test(hostname) ||
    isIpLiteral(hostname) ||
    hostname === "localhost" ||
    !(hostname.endsWith(".ts.net") || !hostname.includes("."))
  ) {
    reject("endpoint_invalid");
  }
  return endpoint.href;
}

function normalizeLimits(raw = {}) {
  if (!isPlainObject(raw)) reject("configuration_invalid");
  const limits = { ...FLEET_LIMITS, ...raw };
  for (const [key, value] of Object.entries(limits)) {
    if (!Object.hasOwn(FLEET_LIMITS, key) || !Number.isSafeInteger(value) || value < 1) {
      reject("configuration_invalid");
    }
  }
  return Object.freeze(limits);
}

async function readLocalFile(pathname, maximumBytes) {
  pathname = resolve(pathname);
  if (!isAbsolute(pathname)) reject("file_invalid");
  let handle;
  try {
    if ((await realpath(pathname)) !== pathname) reject("file_invalid");
    handle = await open(
      pathname,
      fsConstants.O_RDONLY |
        (fsConstants.O_NOFOLLOW ?? 0) |
        (fsConstants.O_CLOEXEC ?? 0),
    );
    const metadata = await handle.stat();
    if (
      !metadata.isFile() ||
      metadata.size < 1 ||
      metadata.size > maximumBytes
    ) {
      reject("file_invalid");
    }
    const bytes = await handle.readFile();
    const after = await handle.stat();
    if (
      after.dev !== metadata.dev ||
      after.ino !== metadata.ino ||
      after.size !== metadata.size ||
      after.ctimeMs !== metadata.ctimeMs
    ) {
      reject("file_changed");
    }
    return bytes;
  } catch (error) {
    if (error instanceof OracleFleetClientError) throw error;
    reject("file_invalid");
  } finally {
    await handle?.close().catch(() => {});
  }
}

function validateWireName(name) {
  if (
    typeof name !== "string" ||
    !SAFE_NAME_PATTERN.test(name) ||
    basename(name) !== name ||
    name === "." ||
    name === ".."
  ) {
    reject("file_invalid");
  }
  return name;
}

function mediaTypeFor(name, override) {
  const value = override ?? MEDIA_TYPES[extname(name).toLowerCase()] ?? "application/octet-stream";
  if (typeof value !== "string" || !MEDIA_TYPE_PATTERN.test(value)) {
    reject("file_invalid");
  }
  return value;
}

async function normalizeClientFile(raw, limits) {
  if (typeof raw === "string") {
    const pathname = resolve(raw);
    const name = validateWireName(basename(pathname));
    const bytes = await readLocalFile(pathname, limits.file_bytes);
    return { name, media_type: mediaTypeFor(name), bytes };
  }
  if (!isPlainObject(raw)) reject("file_invalid");
  if (Object.hasOwn(raw, "path")) {
    const allowed = new Set(["path", "name", "media_type"]);
    if (Object.keys(raw).some((key) => !allowed.has(key)) || typeof raw.path !== "string") {
      reject("file_invalid");
    }
    const pathname = resolve(raw.path);
    const name = validateWireName(raw.name ?? basename(pathname));
    const bytes = await readLocalFile(pathname, limits.file_bytes);
    return { name, media_type: mediaTypeFor(name, raw.media_type), bytes };
  }
  const file = exactObject(raw, ["name", "media_type", "bytes"], "file_invalid");
  const name = validateWireName(file.name);
  const bytes = Buffer.isBuffer(file.bytes)
    ? Buffer.from(file.bytes)
    : file.bytes instanceof Uint8Array
      ? Buffer.from(file.bytes)
      : null;
  if (bytes === null || bytes.length < 1 || bytes.length > limits.file_bytes) {
    reject("file_invalid");
  }
  return { name, media_type: mediaTypeFor(name, file.media_type), bytes };
}

export async function prepareOracleFleetRequest(input, options = {}) {
  if (!isPlainObject(input)) reject("request_invalid");
  const allowed = new Set(["prompt", "files", "request_id", "created_at"]);
  if (Object.keys(input).some((key) => !allowed.has(key))) reject("request_invalid");
  const limits = normalizeLimits(options.limits);
  if (typeof input.prompt !== "string") reject("request_invalid");
  const promptBytes = Buffer.byteLength(input.prompt, "utf8");
  if (promptBytes < 1 || promptBytes > limits.prompt_bytes) reject("prompt_size_rejected");
  const rawFiles = input.files ?? [];
  if (!Array.isArray(rawFiles) || rawFiles.length > limits.file_count) {
    reject("file_count_rejected");
  }
  const files = [];
  const names = new Set();
  let totalBytes = 0;
  for (const rawFile of rawFiles) {
    const file = await normalizeClientFile(rawFile, limits);
    if (names.has(file.name)) reject("file_name_repeated");
    names.add(file.name);
    totalBytes += file.bytes.length;
    if (totalBytes > limits.files_bytes) reject("files_size_rejected");
    files.push({
      name: file.name,
      media_type: file.media_type,
      bytes: file.bytes.length,
      sha256: sha256(file.bytes),
      data_base64: file.bytes.toString("base64"),
    });
  }
  const request = Object.freeze({
    schema: ORACLE_FLEET_REQUEST_SCHEMA,
    request_id: input.request_id ?? randomUUID(),
    created_at: input.created_at ?? new Date(options.nowMs?.() ?? Date.now()).toISOString(),
    prompt: input.prompt,
    files: Object.freeze(files.map(Object.freeze)),
  });
  const body = Buffer.from(JSON.stringify(request), "utf8");
  if (body.length > limits.body_bytes) reject("body_size_rejected");
  return Object.freeze({ request, body });
}

async function readBoundedResponse(response, maximumBytes) {
  if (response.body && typeof response.body.getReader === "function") {
    const reader = response.body.getReader();
    const chunks = [];
    let total = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const bytes = Buffer.from(value);
      total += bytes.length;
      if (total > maximumBytes) {
        await reader.cancel().catch(() => {});
        reject("response_size_rejected");
      }
      chunks.push(bytes);
    }
    return Buffer.concat(chunks, total);
  }
  if (typeof response.arrayBuffer !== "function") reject("response_invalid");
  const bytes = Buffer.from(await response.arrayBuffer());
  if (bytes.length > maximumBytes) reject("response_size_rejected");
  return bytes;
}

function parseJson(bytes) {
  try {
    return JSON.parse(bytes.toString("utf8"));
  } catch {
    reject("response_invalid");
  }
}

function validateReceipt(raw, result) {
  const receipt = exactObject(
    raw,
    [
      "schema",
      "request_id",
      "accepted_at",
      "completed_at",
      "caller",
      "policy",
      "oracle",
      "result",
    ],
    "response_invalid",
  );
  if (
    receipt.schema !== ORACLE_FLEET_RECEIPT_SCHEMA ||
    !isPlainObject(receipt.caller) ||
    typeof receipt.caller.node_id !== "string" ||
    typeof receipt.caller.node_name !== "string" ||
    typeof receipt.caller.user_login !== "string" ||
    !Array.isArray(receipt.caller.tags) ||
    !isPlainObject(receipt.oracle) ||
    typeof receipt.oracle.run_id !== "string" ||
    typeof receipt.oracle.state !== "string" ||
    !isPlainObject(receipt.result) ||
    JSON.stringify(receipt.result) !== JSON.stringify({
      name: result.name,
      media_type: result.media_type,
      bytes: result.bytes,
      sha256: result.sha256,
    })
  ) {
    reject("response_invalid");
  }
  return receipt;
}

export function decodeOracleFleetResponse(raw, options = {}) {
  const limits = normalizeLimits(options.limits);
  if (!isPlainObject(raw) || raw.schema !== ORACLE_FLEET_RESPONSE_SCHEMA) {
    reject("response_invalid");
  }
  if (raw.ok === false) {
    const code = raw.error?.code;
    reject(typeof code === "string" && SAFE_CODE_PATTERN.test(code) ? code : "remote_rejected");
  }
  const response = exactObject(raw, ["schema", "receipt", "result"], "response_invalid");
  const result = exactObject(
    response.result,
    ["name", "media_type", "bytes", "sha256", "data_base64"],
    "response_invalid",
  );
  if (
    typeof result.name !== "string" ||
    !SAFE_NAME_PATTERN.test(result.name) ||
    basename(result.name) !== result.name ||
    typeof result.media_type !== "string" ||
    !MEDIA_TYPE_PATTERN.test(result.media_type) ||
    !Number.isSafeInteger(result.bytes) ||
    result.bytes < 1 ||
    result.bytes > limits.result_bytes ||
    typeof result.sha256 !== "string" ||
    !/^[0-9a-f]{64}$/.test(result.sha256) ||
    typeof result.data_base64 !== "string"
  ) {
    reject("response_invalid");
  }
  const bytes = Buffer.from(result.data_base64, "base64");
  if (
    bytes.length !== result.bytes ||
    bytes.toString("base64") !== result.data_base64 ||
    sha256(bytes) !== result.sha256
  ) {
    reject("response_invalid");
  }
  return Object.freeze({
    receipt: validateReceipt(response.receipt, result),
    result: Object.freeze({
      name: result.name,
      media_type: result.media_type,
      bytes,
      byte_length: result.bytes,
      sha256: result.sha256,
    }),
  });
}

export async function writeOracleFleetResult(destination, bytes) {
  destination = resolve(destination);
  const parent = dirname(destination);
  if ((await realpath(parent)) !== parent) reject("result_destination_invalid");
  const temporary = join(parent, `.oracle-fleet-result-${randomUUID()}.tmp`);
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
    return destination;
  } catch (error) {
    if (error instanceof OracleFleetClientError) throw error;
    reject("result_write_failed");
  } finally {
    await handle?.close().catch(() => {});
    await unlink(temporary).catch(() => {});
  }
}

export async function submitOracleFleetRequest(input, options = {}) {
  const endpoint = normalizeOracleFleetEndpoint(options.endpoint);
  const fetchImpl = options.fetchImpl ?? globalThis.fetch;
  if (typeof fetchImpl !== "function") reject("transport_unavailable");
  const limits = normalizeLimits(options.limits);
  const prepared = await prepareOracleFleetRequest(input, {
    limits,
    nowMs: options.nowMs,
  });
  let response;
  try {
    response = await fetchImpl(endpoint, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        accept: "application/json",
      },
      body: prepared.body,
      redirect: "error",
      signal: options.signal,
    });
  } catch {
    reject("transport_failed");
  }
  const responseType = response.headers?.get?.("content-type") ?? "";
  if (!/^application\/json(?:;\s*charset=utf-8)?$/i.test(responseType)) {
    reject("response_invalid");
  }
  const responseBytes = await readBoundedResponse(
    response,
    Math.ceil((limits.result_bytes * 4) / 3) + 1024 * 1024,
  );
  const decoded = decodeOracleFleetResponse(parseJson(responseBytes), { limits });
  if (!response.ok) reject("remote_rejected");
  if (
    decoded.receipt.request_id !== prepared.request.request_id ||
    decoded.receipt.accepted_at !== prepared.request.created_at
  ) {
    reject("response_mismatch");
  }
  const resultPath = options.resultPath
    ? await writeOracleFleetResult(options.resultPath, decoded.result.bytes)
    : null;
  return Object.freeze({
    receipt: decoded.receipt,
    result_path: resultPath,
    result_name: decoded.result.name,
    result_bytes: decoded.result.byte_length,
    result_sha256: decoded.result.sha256,
  });
}

export const submitOracleRequest = submitOracleFleetRequest;

async function readStdin(maximumBytes) {
  const chunks = [];
  let total = 0;
  for await (const chunk of process.stdin) {
    const bytes = Buffer.from(chunk);
    total += bytes.length;
    if (total > maximumBytes) reject("prompt_size_rejected");
    chunks.push(bytes);
  }
  if (total < 1) reject("request_invalid");
  return Buffer.concat(chunks, total).toString("utf8");
}

async function readPromptFile(pathname, maximumBytes) {
  return (await readLocalFile(pathname, maximumBytes)).toString("utf8");
}

export function parseClientArguments(rawArguments) {
  if (
    rawArguments.length === 1 &&
    ["-h", "--help"].includes(rawArguments[0])
  ) {
    return Object.freeze({ help: true });
  }
  const parsed = {
    endpoint: null,
    host: null,
    port: 4117,
    https: false,
    prompt_file: null,
    files: [],
    result: null,
  };
  for (let index = 0; index < rawArguments.length; index += 1) {
    const flag = rawArguments[index];
    if (flag === "--https") {
      parsed.https = true;
      continue;
    }
    const value = rawArguments[index + 1];
    if (typeof value !== "string") reject("arguments_invalid");
    index += 1;
    if (flag === "--endpoint") parsed.endpoint = normalizeOracleFleetEndpoint(value);
    else if (flag === "--host") parsed.host = value;
    else if (flag === "--port") parsed.port = Number(value);
    else if (flag === "--prompt-file") parsed.prompt_file = resolve(value);
    else if (flag === "--file") parsed.files.push(resolve(value));
    else if (flag === "--result") parsed.result = resolve(value);
    else reject("arguments_invalid");
  }
  if (
    (parsed.endpoint === null) === (parsed.host === null) ||
    parsed.result === null ||
    !Number.isSafeInteger(parsed.port) ||
    parsed.port < 1 ||
    parsed.port > 65_535
  ) {
    reject("arguments_invalid");
  }
  if (parsed.host !== null) {
    parsed.endpoint = normalizeOracleFleetEndpoint(
      `${parsed.https ? "https" : "http"}://${parsed.host}:${parsed.port}/v1/oracle`,
    );
  }
  return Object.freeze({ ...parsed, files: Object.freeze([...parsed.files]) });
}

export async function main(rawArguments = process.argv.slice(2), injected = {}) {
  try {
    const options = parseClientArguments(rawArguments);
    if (options.help) {
      process.stdout.write(`${CLIENT_HELP}\n`);
      return 0;
    }
    const prompt = options.prompt_file
      ? await readPromptFile(options.prompt_file, FLEET_LIMITS.prompt_bytes)
      : await readStdin(FLEET_LIMITS.prompt_bytes);
    const result = await submitOracleFleetRequest(
      { prompt, files: options.files },
      {
        endpoint: options.endpoint,
        resultPath: options.result,
        fetchImpl: injected.fetchImpl,
      },
    );
    process.stdout.write(`${JSON.stringify({ ok: true, ...result })}\n`);
    return 0;
  } catch (error) {
    const code =
      error instanceof OracleFleetClientError && SAFE_CODE_PATTERN.test(error.code)
        ? error.code
        : "operation_failed";
    process.stderr.write(`oracle-rpc-client:${code}\n`);
    if (
      code.startsWith("transport_") ||
      code.startsWith("response_") ||
      code.startsWith("remote_") ||
      code === "replay_rejected" ||
      code === "caller_policy_rejected" ||
      code === "caller_tag_rejected"
    ) {
      return 2;
    }
    return code === "operation_failed" ? 3 : 1;
  }
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(resolve(process.argv[1])).href
) {
  process.exitCode = await main();
}
