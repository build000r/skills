#!/usr/bin/env node

import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { lookup as dnsLookup } from "node:dns/promises";
import { constants as fsConstants, realpathSync } from "node:fs";
import {
  chmod,
  lstat,
  mkdtemp,
  open,
  realpath,
  rm,
} from "node:fs/promises";
import http from "node:http";
import { homedir } from "node:os";
import { basename, dirname, extname, isAbsolute, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

import {
  executeCli as executeOracleCli,
  parseCliArguments as parseOracleCliArguments,
} from "./oracle-subagent.mjs";

export const ORACLE_FLEET_REQUEST_SCHEMA = "oracle-fleet.request.v1";
export const ORACLE_FLEET_RESPONSE_SCHEMA = "oracle-fleet.response.v1";
export const ORACLE_FLEET_RECEIPT_SCHEMA = "oracle-fleet.receipt.v1";

export const FLEET_LIMITS = Object.freeze({
  body_bytes: 12 * 1024 * 1024,
  prompt_bytes: 256 * 1024,
  file_bytes: 4 * 1024 * 1024,
  files_bytes: 8 * 1024 * 1024,
  file_count: 8,
  result_bytes: 32 * 1024 * 1024,
  replay_window_ms: 5 * 60 * 1000,
  future_clock_skew_ms: 30 * 1000,
  replay_entries: 10_000,
});

const LOCAL_API_SOCKET = "/var/run/tailscale/tailscaled.sock";
const REQUEST_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{15,127}$/;
const SAFE_NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._ -]{0,127}$/;
const MEDIA_TYPE_PATTERN =
  /^[a-z0-9][a-z0-9!#$&^_.+-]{0,63}\/[a-z0-9][a-z0-9!#$&^_.+-]{0,63}$/;
const TAG_PATTERN = /^tag:[a-z][a-z0-9-]{0,62}$/;
const SAFE_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:+@-]{0,255}$/;
const MAGIC_DNS_PATTERN =
  /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*$/;
const POLICY_CALLER_PATTERN = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const FORBIDDEN_KEYS = new Set([
  "authorization",
  "browserconfig",
  "browserconfiguration",
  "browserprofile",
  "cdp",
  "cdpendpoint",
  "cdptarget",
  "command",
  "cookie",
  "cookies",
  "env",
  "environment",
  "exec",
  "executable",
  "headers",
  "hook",
  "hooks",
  "path",
  "paths",
  "profile",
  "replay",
  "sessiontoken",
  "token",
]);
const SERVER_HELP = `usage: oracle-rpc-server --bind-host MAGICDNS [options]

Options:
  --port N                         listener port (default: 4117)
  --artifact-root DIR              private local Oracle run root
  --mode pro|deep-research         server-owned Oracle mode
  --policy-bridge PATH             Skillbox policy authority entrypoint
  --required-peer-tag tag:NAME     repeatable caller allowlist tag
  -h, --help                       show this help

The listener fails closed unless MAGICDNS resolves to this node's live
Tailscale addresses. No credential, browser, CDP, hook, or exec input exists.`;

export class OracleFleetRpcError extends Error {
  constructor(code, status = 400) {
    super("oracle fleet rpc: rejected");
    this.name = "OracleFleetRpcError";
    this.code = code;
    this.status = status;
  }
}

function reject(code, status = 400) {
  throw new OracleFleetRpcError(code, status);
}

function isPlainObject(value) {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.getPrototypeOf(value) === Object.prototype
  );
}

function exactObject(value, required, code = "request_schema_rejected") {
  if (!isPlainObject(value)) reject(code);
  if (
    Object.keys(value).length !== required.length ||
    required.some((key) => !Object.hasOwn(value, key))
  ) {
    reject(code);
  }
  return value;
}

function normalizedKey(value) {
  return value.toLowerCase().replaceAll(/[-_]/g, "");
}

function isForbiddenKey(value) {
  const key = normalizedKey(value);
  return (
    FORBIDDEN_KEYS.has(key) ||
    key.includes("browserconfig") ||
    key.includes("browserprofile") ||
    key.startsWith("cdp") ||
    key.includes("cookie") ||
    key.startsWith("environment") ||
    key.startsWith("exec") ||
    key.startsWith("hook") ||
    key.endsWith("path") ||
    key.endsWith("token")
  );
}

function rejectForbiddenKeys(value) {
  if (Array.isArray(value)) {
    for (const item of value) rejectForbiddenKeys(item);
    return;
  }
  if (!isPlainObject(value)) return;
  for (const [key, child] of Object.entries(value)) {
    if (isForbiddenKey(key)) reject("forbidden_field");
    rejectForbiddenKeys(child);
  }
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function canonicalTimestamp(value, code = "request_timestamp_invalid") {
  if (typeof value !== "string") reject(code);
  const milliseconds = Date.parse(value);
  if (
    !Number.isFinite(milliseconds) ||
    new Date(milliseconds).toISOString() !== value
  ) {
    reject(code);
  }
  return milliseconds;
}

function canonicalBase64(value, expectedBytes) {
  if (
    typeof value !== "string" ||
    value.length !== 4 * Math.ceil(expectedBytes / 3) ||
    !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(
      value,
    )
  ) {
    reject("file_encoding_invalid");
  }
  const bytes = Buffer.from(value, "base64");
  if (bytes.length !== expectedBytes || bytes.toString("base64") !== value) {
    reject("file_encoding_invalid");
  }
  return bytes;
}

function normalizeLimits(raw = {}) {
  if (!isPlainObject(raw)) reject("server_configuration_invalid", 500);
  const limits = { ...FLEET_LIMITS, ...raw };
  for (const [key, value] of Object.entries(limits)) {
    if (!Object.hasOwn(FLEET_LIMITS, key) || !Number.isSafeInteger(value) || value < 1) {
      reject("server_configuration_invalid", 500);
    }
  }
  return Object.freeze(limits);
}

export function validateOracleFleetRequest(raw, options = {}) {
  const limits = normalizeLimits(options.limits);
  const nowMs = options.nowMs ?? Date.now();
  rejectForbiddenKeys(raw);
  const value = exactObject(raw, [
    "schema",
    "request_id",
    "created_at",
    "prompt",
    "files",
  ]);
  if (
    value.schema !== ORACLE_FLEET_REQUEST_SCHEMA ||
    typeof value.request_id !== "string" ||
    !REQUEST_ID_PATTERN.test(value.request_id)
  ) {
    reject("request_schema_rejected");
  }
  const createdAtMs = canonicalTimestamp(value.created_at);
  if (
    createdAtMs < nowMs - limits.replay_window_ms ||
    createdAtMs > nowMs + limits.future_clock_skew_ms
  ) {
    reject("request_expired");
  }
  if (typeof value.prompt !== "string") reject("request_schema_rejected");
  const promptBytes = Buffer.byteLength(value.prompt, "utf8");
  if (promptBytes < 1 || promptBytes > limits.prompt_bytes) {
    reject("prompt_size_rejected", 413);
  }
  if (!Array.isArray(value.files) || value.files.length > limits.file_count) {
    reject("file_count_rejected", 413);
  }
  let filesBytes = 0;
  const files = value.files.map((rawFile) => {
    const file = exactObject(rawFile, [
      "name",
      "media_type",
      "bytes",
      "sha256",
      "data_base64",
    ]);
    if (
      typeof file.name !== "string" ||
      !SAFE_NAME_PATTERN.test(file.name) ||
      basename(file.name) !== file.name ||
      file.name === "." ||
      file.name === ".." ||
      typeof file.media_type !== "string" ||
      !MEDIA_TYPE_PATTERN.test(file.media_type) ||
      !Number.isSafeInteger(file.bytes) ||
      file.bytes < 1 ||
      file.bytes > limits.file_bytes ||
      typeof file.sha256 !== "string" ||
      !/^[0-9a-f]{64}$/.test(file.sha256)
    ) {
      reject("file_schema_rejected");
    }
    filesBytes += file.bytes;
    if (filesBytes > limits.files_bytes) reject("files_size_rejected", 413);
    const bytes = canonicalBase64(file.data_base64, file.bytes);
    if (sha256(bytes) !== file.sha256) reject("file_digest_rejected");
    return Object.freeze({
      name: file.name,
      media_type: file.media_type,
      bytes,
      byte_length: file.bytes,
      sha256: file.sha256,
    });
  });
  return Object.freeze({
    schema: ORACLE_FLEET_REQUEST_SCHEMA,
    request_id: value.request_id,
    created_at: value.created_at,
    created_at_ms: createdAtMs,
    prompt: value.prompt,
    prompt_bytes: promptBytes,
    files: Object.freeze(files),
    files_bytes: filesBytes,
  });
}

export async function readBoundedJsonBody(request, options = {}) {
  const limits = normalizeLimits(options.limits);
  const contentType = request.headers?.["content-type"] ?? "";
  const contentEncoding = request.headers?.["content-encoding"];
  if (!/^application\/json(?:;\s*charset=utf-8)?$/i.test(contentType)) {
    reject("content_type_rejected", 415);
  }
  if (contentEncoding !== undefined && contentEncoding !== "identity") {
    reject("content_encoding_rejected", 415);
  }
  const declaredLength = Number(request.headers?.["content-length"] ?? 0);
  if (
    !Number.isSafeInteger(declaredLength) ||
    declaredLength < 0 ||
    declaredLength > limits.body_bytes
  ) {
    reject("body_size_rejected", 413);
  }
  const chunks = [];
  let total = 0;
  for await (const chunk of request) {
    const bytes = Buffer.from(chunk);
    total += bytes.length;
    if (total > limits.body_bytes) reject("body_size_rejected", 413);
    chunks.push(bytes);
  }
  if (total < 1) reject("body_empty");
  try {
    return JSON.parse(Buffer.concat(chunks, total).toString("utf8"));
  } catch {
    reject("body_json_rejected");
  }
}

export function createReplayGuard(options = {}) {
  const limits = normalizeLimits(options.limits);
  const now = options.nowMs ?? (() => Date.now());
  const entries = new Map();
  return Object.freeze({
    claim(callerId, requestId, createdAtMs) {
      const current = now();
      for (const [key, expiresAt] of entries) {
        if (expiresAt <= current) entries.delete(key);
      }
      const key = sha256(`${callerId}\0${requestId}`);
      if (entries.has(key)) reject("replay_rejected", 409);
      if (entries.size >= limits.replay_entries) reject("replay_capacity_rejected", 503);
      entries.set(
        key,
        Math.max(current, createdAtMs) + limits.replay_window_ms,
      );
    },
  });
}

function localApiJson(pathname, options = {}) {
  const socketPath = options.socketPath ?? LOCAL_API_SOCKET;
  const requestImpl = options.requestImpl ?? http.request;
  const maximumBytes = options.maximumBytes ?? 256 * 1024;
  return new Promise((resolvePromise, rejectPromise) => {
    const request = requestImpl(
      {
        socketPath,
        path: pathname,
        method: "GET",
        headers: {
          accept: "application/json",
          host: "local-tailscaled.sock",
        },
      },
      (response) => {
        const chunks = [];
        let total = 0;
        response.on("data", (chunk) => {
          total += chunk.length;
          if (total <= maximumBytes) chunks.push(Buffer.from(chunk));
        });
        response.on("end", () => {
          if (response.statusCode !== 200 || total > maximumBytes) {
            rejectPromise(new Error("tailscale LocalAPI rejected request"));
            return;
          }
          try {
            resolvePromise(JSON.parse(Buffer.concat(chunks, total).toString("utf8")));
          } catch {
            rejectPromise(new Error("tailscale LocalAPI returned invalid JSON"));
          }
        });
      },
    );
    request.once("error", rejectPromise);
    request.end();
  });
}

export function createTailscaleLocalApi(options = {}) {
  return (pathname) => localApiJson(pathname, options);
}

function safeIdentity(value, code) {
  const string = typeof value === "number" ? String(value) : value;
  if (typeof string !== "string" || !SAFE_ID_PATTERN.test(string)) reject(code, 403);
  return string;
}

function socketAddress(socket) {
  const address = socket?.remoteAddress;
  const port = socket?.remotePort;
  if (typeof address !== "string" || !Number.isSafeInteger(port)) {
    reject("caller_identity_unavailable", 403);
  }
  const normalized = address.startsWith("::ffff:") ? address.slice(7) : address;
  return normalized.includes(":") ? `[${normalized}]:${port}` : `${normalized}:${port}`;
}

export async function resolveTailscaleCaller(socket, options = {}) {
  const callLocalApi = options.localApiJson ?? createTailscaleLocalApi(options);
  let whois;
  try {
    whois = await callLocalApi(
      `/localapi/v0/whois?addr=${encodeURIComponent(socketAddress(socket))}`,
    );
  } catch {
    reject("caller_identity_unavailable", 403);
  }
  if (!isPlainObject(whois) || !isPlainObject(whois.Node)) {
    reject("caller_identity_unavailable", 403);
  }
  const nodeId = safeIdentity(
    whois.Node.StableID ?? whois.Node.ID,
    "caller_identity_unavailable",
  );
  const nodeName = safeIdentity(
    String(whois.Node.Name ?? "").replace(/\.$/, ""),
    "caller_identity_unavailable",
  );
  const loginName = safeIdentity(
    whois.UserProfile?.LoginName ?? "tailnet-user",
    "caller_identity_unavailable",
  );
  const tags = Array.isArray(whois.Node.Tags)
    ? whois.Node.Tags.filter((tag) => typeof tag === "string" && TAG_PATTERN.test(tag))
    : [];
  const requiredTags = options.requiredPeerTags ?? ["tag:oracle-client"];
  if (
    !Array.isArray(requiredTags) ||
    requiredTags.length < 1 ||
    requiredTags.some((tag) => typeof tag !== "string" || !TAG_PATTERN.test(tag))
  ) {
    reject("server_configuration_invalid", 500);
  }
  if (!requiredTags.some((tag) => tags.includes(tag))) {
    reject("caller_tag_rejected", 403);
  }
  return Object.freeze({
    node_id: nodeId,
    node_name: nodeName,
    user_login: loginName,
    tags: Object.freeze([...tags].sort()),
  });
}

function isIpLiteral(value) {
  return /^\d{1,3}(?:\.\d{1,3}){3}$/.test(value) || value.includes(":");
}

export function validateTailnetBindHost(value) {
  if (
    typeof value !== "string" ||
    !MAGIC_DNS_PATTERN.test(value) ||
    isIpLiteral(value) ||
    ["localhost", "0.0.0.0", "::", "::0", "*"].includes(value.toLowerCase())
  ) {
    reject("tailnet_bind_required", 500);
  }
  return value.toLowerCase();
}

export async function verifyTailnetBindHost(host, options = {}) {
  host = validateTailnetBindHost(host);
  const callLocalApi = options.localApiJson ?? createTailscaleLocalApi(options);
  const lookup = options.lookup ?? dnsLookup;
  if (typeof lookup !== "function") reject("tailnet_bind_proof_unavailable", 500);
  let status;
  let addresses = [];
  try {
    status = await callLocalApi("/localapi/v0/status");
  } catch {
    reject("tailnet_bind_proof_unavailable", 500);
  }
  try {
    addresses = await lookup(host, { all: true, verbatim: true });
  } catch {
    addresses = [];
  }
  const selfAddresses = new Set(status?.Self?.TailscaleIPs ?? []);
  const selfDnsName = String(status?.Self?.DNSName ?? "")
    .replace(/\.$/, "")
    .toLowerCase();
  const resolvedAddresses = Array.isArray(addresses)
    ? addresses.map((entry) => entry?.address)
    : [];
  if (selfAddresses.size < 1) {
    reject("tailnet_bind_proof_failed", 500);
  }
  if (
    resolvedAddresses.length > 0 &&
    resolvedAddresses.every((address) => selfAddresses.has(address))
  ) {
    return options.returnBindAddress ? resolvedAddresses[0] : host;
  }
  if (selfDnsName === host) {
    return options.returnBindAddress ? [...selfAddresses][0] : host;
  }
  reject("tailnet_bind_proof_failed", 500);
}

function publicRequestMetadata(request) {
  return Object.freeze({
    request_id: request.request_id,
    prompt_bytes: request.prompt_bytes,
    file_count: request.files.length,
    files_bytes: request.files_bytes,
  });
}

function normalizePolicyResult(raw) {
  if (!isPlainObject(raw)) reject("caller_policy_rejected", 403);
  if (raw.allowed === false) reject("caller_policy_rejected", 429);
  const receipt = raw.receipt;
  exactObject(receipt, ["policy_id", "quota_bucket", "remaining"], "caller_policy_invalid");
  if (
    !SAFE_ID_PATTERN.test(receipt.policy_id) ||
    !SAFE_ID_PATTERN.test(receipt.quota_bucket) ||
    !Number.isSafeInteger(receipt.remaining) ||
    receipt.remaining < 0
  ) {
    reject("caller_policy_invalid", 500);
  }
  return Object.freeze({
    context: raw.context,
    receipt: Object.freeze({ ...receipt }),
  });
}

function policyCallerId(caller) {
  const value = String(caller?.node_name ?? "")
    .replace(/\.$/, "")
    .split(".")[0]
    .toLowerCase();
  if (!POLICY_CALLER_PATTERN.test(value)) reject("caller_policy_rejected", 403);
  return value;
}

function runPolicyBridge(policyBridge, action, payload = null) {
  if (typeof policyBridge !== "string" || !isAbsolute(policyBridge)) {
    reject("caller_policy_unavailable", 500);
  }
  const result = spawnSync(
    "python3",
    [policyBridge, "oracle-policy-bridge", action],
    {
      input: payload === null ? undefined : `${JSON.stringify(payload)}\n`,
      encoding: "utf8",
      maxBuffer: 256 * 1024,
      timeout: 10_000,
      env: process.env,
    },
  );
  if (result.error || typeof result.stdout !== "string") {
    reject("caller_policy_unavailable", 503);
  }
  let response;
  try {
    response = JSON.parse(result.stdout);
  } catch {
    reject("caller_policy_unavailable", 503);
  }
  if (!isPlainObject(response) || response.ok !== true) {
    if (
      action === "reserve" &&
      typeof response?.error?.code === "string" &&
      SAFE_ID_PATTERN.test(response.error.code)
    ) {
      reject("caller_policy_rejected", 429);
    }
    reject("caller_policy_unavailable", 503);
  }
  if (result.status !== 0) reject("caller_policy_unavailable", 503);
  return response;
}

export function createPolicyBridgeAuthority(options = {}) {
  const policyBridge = options.policyBridge;
  const mode = options.mode === "deep-research" ? "deep-research" : "standard";
  const timeoutSeconds = options.timeoutSeconds ?? 7_200;
  return Object.freeze({
    check() {
      const response = runPolicyBridge(policyBridge, "doctor");
      if (response.policy_id !== "skillbox-oracle-v1") {
        reject("caller_policy_unavailable", 503);
      }
    },
    authorizeCaller({ caller, request }) {
      const callerId = policyCallerId(caller);
      const response = runPolicyBridge(policyBridge, "reserve", {
        caller_id: callerId,
        request: {
          schema: "skillbox.oracle-request-facts.v1",
          mode,
          prompt_bytes: request.prompt_bytes,
          file_count: request.file_count,
          attachment_bytes: request.files_bytes,
          timeout_seconds: timeoutSeconds,
        },
      });
      return {
        allowed: true,
        context: response.reservation,
        receipt: response.receipt,
      };
    },
    releaseCaller(context) {
      if (!isPlainObject(context)) reject("caller_policy_invalid", 500);
      exactObject(
        context,
        ["caller_id", "reservation_id"],
        "caller_policy_invalid",
      );
      runPolicyBridge(policyBridge, "release", context);
    },
  });
}

function normalizeResult(raw, limits) {
  if (!isPlainObject(raw)) reject("oracle_result_invalid", 502);
  const bytes = Buffer.isBuffer(raw.bytes)
    ? raw.bytes
    : raw.bytes instanceof Uint8Array
      ? Buffer.from(raw.bytes)
      : null;
  if (
    typeof raw.run_id !== "string" ||
    !SAFE_ID_PATTERN.test(raw.run_id) ||
    typeof raw.state !== "string" ||
    !SAFE_ID_PATTERN.test(raw.state) ||
    bytes === null ||
    bytes.length < 1 ||
    bytes.length > limits.result_bytes
  ) {
    reject("oracle_result_invalid", 502);
  }
  const name = raw.name ?? "result.md";
  const mediaType = raw.media_type ?? "text/markdown";
  if (
    !SAFE_NAME_PATTERN.test(name) ||
    basename(name) !== name ||
    !MEDIA_TYPE_PATTERN.test(mediaType)
  ) {
    reject("oracle_result_invalid", 502);
  }
  return Object.freeze({
    run_id: raw.run_id,
    state: raw.state,
    name,
    media_type: mediaType,
    bytes,
    sha256: sha256(bytes),
  });
}

function jsonResponse(response, status, value) {
  const bytes = Buffer.from(`${JSON.stringify(value)}\n`, "utf8");
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": bytes.length,
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
  });
  response.end(bytes);
}

function safeError(error) {
  return error instanceof OracleFleetRpcError
    ? error
    : new OracleFleetRpcError("operation_failed", 500);
}

export function createOracleRpcHandler(options = {}) {
  const limits = normalizeLimits(options.limits);
  const replayGuard = options.replayGuard ?? createReplayGuard({ limits });
  const resolveCaller = options.resolveCaller;
  const authorizeCaller = options.authorizeCaller;
  const releaseCaller = options.releaseCaller;
  const runOracle = options.runOracle;
  const nowMs = options.nowMs ?? (() => Date.now());
  if (
    typeof resolveCaller !== "function" ||
    typeof authorizeCaller !== "function" ||
    typeof releaseCaller !== "function" ||
    typeof runOracle !== "function"
  ) {
    reject("server_configuration_invalid", 500);
  }
  return async function oracleRpcHandler(request, response) {
    try {
      if (request.method === "GET" && request.url === "/healthz") {
        jsonResponse(response, 200, {
          ok: true,
          ready: true,
          policy: "required",
        });
        return;
      }
      if (request.method !== "POST" || request.url !== "/v1/oracle") {
        reject("route_not_found", 404);
      }
      const caller = await resolveCaller(request.socket);
      const raw = await readBoundedJsonBody(request, { limits });
      const fleetRequest = validateOracleFleetRequest(raw, {
        limits,
        nowMs: nowMs(),
      });
      replayGuard.claim(
        caller.node_id,
        fleetRequest.request_id,
        fleetRequest.created_at_ms,
      );
      const policy = normalizePolicyResult(
        await authorizeCaller({
          caller,
          request: publicRequestMetadata(fleetRequest),
        }),
      );
      const acceptedAt = new Date(nowMs()).toISOString();
      let oracleResult;
      try {
        oracleResult = normalizeResult(
          await runOracle(
            {
              prompt: fleetRequest.prompt,
              files: fleetRequest.files,
            },
            {
              caller,
              request_id: fleetRequest.request_id,
              policy: policy.context,
            },
          ),
          limits,
        );
      } catch (error) {
        if (error instanceof OracleFleetRpcError) throw error;
        reject("oracle_failed", 502);
      } finally {
        await releaseCaller(policy.context);
      }
      const completedAt = new Date(nowMs()).toISOString();
      const receipt = Object.freeze({
        schema: ORACLE_FLEET_RECEIPT_SCHEMA,
        request_id: fleetRequest.request_id,
        accepted_at: acceptedAt,
        completed_at: completedAt,
        caller,
        policy: policy.receipt,
        oracle: Object.freeze({
          run_id: oracleResult.run_id,
          state: oracleResult.state,
        }),
        result: Object.freeze({
          name: oracleResult.name,
          media_type: oracleResult.media_type,
          bytes: oracleResult.bytes.length,
          sha256: oracleResult.sha256,
        }),
      });
      jsonResponse(response, 200, {
        schema: ORACLE_FLEET_RESPONSE_SCHEMA,
        receipt,
        result: {
          ...receipt.result,
          data_base64: oracleResult.bytes.toString("base64"),
        },
      });
    } catch (error) {
      const failure = safeError(error);
      jsonResponse(response, failure.status, {
        schema: ORACLE_FLEET_RESPONSE_SCHEMA,
        ok: false,
        error: { code: failure.code },
      });
    }
  };
}

async function secureReadResult(pathname, artifactRoot, maximumBytes) {
  const root = await realpath(artifactRoot);
  const path = await realpath(pathname);
  if (path !== root && !path.startsWith(`${root}/`)) reject("oracle_result_invalid", 502);
  const metadata = await lstat(path);
  if (
    !metadata.isFile() ||
    metadata.isSymbolicLink() ||
    metadata.size < 1 ||
    metadata.size > maximumBytes ||
    (metadata.mode & 0o077) !== 0
  ) {
    reject("oracle_result_invalid", 502);
  }
  const handle = await open(
    path,
    fsConstants.O_RDONLY |
      (fsConstants.O_NOFOLLOW ?? 0) |
      (fsConstants.O_CLOEXEC ?? 0),
  );
  try {
    const after = await handle.stat();
    if (after.dev !== metadata.dev || after.ino !== metadata.ino || after.size !== metadata.size) {
      reject("oracle_result_invalid", 502);
    }
    return await handle.readFile();
  } finally {
    await handle.close();
  }
}

function safeStageName(index, file) {
  const suffix = extname(file.name).toLowerCase().replaceAll(/[^a-z0-9.]/g, "");
  return `${String(index).padStart(3, "0")}-${file.sha256}${suffix}`;
}

export function createLocalOracleRunner(options = {}) {
  const artifactRoot = resolve(
    options.artifactRoot ?? join(homedir(), ".oracle", "oracle-subagent", "runs"),
  );
  const mode = options.mode ?? "pro";
  const timeoutSeconds = options.timeoutSeconds ?? 7_200;
  const limits = normalizeLimits(options.limits);
  const executeCli = options.executeCli ?? executeOracleCli;
  if (!isAbsolute(artifactRoot) || !["pro", "deep-research"].includes(mode)) {
    reject("server_configuration_invalid", 500);
  }
  return async function runLocalOracle(request, context) {
    const stage = await mkdtemp(join(artifactRoot, ".fleet-input-"));
    await chmod(stage, 0o700);
    const paths = [];
    try {
      for (const [index, file] of request.files.entries()) {
        const pathname = join(stage, safeStageName(index, file));
        const handle = await open(
          pathname,
          fsConstants.O_CREAT |
            fsConstants.O_EXCL |
            fsConstants.O_WRONLY |
            (fsConstants.O_NOFOLLOW ?? 0),
          0o600,
        );
        try {
          await handle.writeFile(file.bytes);
          await handle.sync();
        } finally {
          await handle.close();
        }
        paths.push(pathname);
      }
      const slug = `fleet-${sha256(context.request_id).slice(0, 24)}`;
      const arguments_ = [
        "run",
        "--artifact-root",
        artifactRoot,
        "--slug",
        slug,
        "--mode",
        mode,
        "--wait",
        "completed",
        "--timeout-seconds",
        String(timeoutSeconds),
        ...paths.flatMap((path) => ["--file", path]),
      ];
      const result = await executeCli(parseOracleCliArguments(arguments_), {
        readStdin: async () => Buffer.from(request.prompt, "utf8"),
      });
      if (result?.state !== "completed" || typeof result.result_path !== "string") {
        reject("oracle_failed", 502);
      }
      return {
        run_id: result.run_id,
        state: result.state,
        name: "result.md",
        media_type: "text/markdown",
        bytes: await secureReadResult(result.result_path, artifactRoot, limits.result_bytes),
      };
    } finally {
      await rm(stage, { recursive: true, force: true });
    }
  };
}

export async function startOracleRpcServer(options = {}) {
  const host = validateTailnetBindHost(options.host);
  const port = options.port ?? 4117;
  if (!Number.isSafeInteger(port) || port < 1 || port > 65_535) {
    reject("server_configuration_invalid", 500);
  }
  const verifyBind = options.verifyBind ?? verifyTailnetBindHost;
  const provenBind = await verifyBind(host, {
    ...(options.bindProof ?? {}),
    returnBindAddress: true,
  });
  const bindAddress =
    typeof provenBind === "string" && provenBind !== host ? provenBind : host;
  const localApi = options.localApiJson ?? createTailscaleLocalApi(options.localApi ?? {});
  const resolveCaller =
    options.resolveCaller ??
    ((socket) =>
      resolveTailscaleCaller(socket, {
        localApiJson: localApi,
        requiredPeerTags: options.requiredPeerTags,
      }));
  const runOracle =
    options.runOracle ??
    createLocalOracleRunner({
      artifactRoot: options.artifactRoot,
      mode: options.mode,
      timeoutSeconds: options.timeoutSeconds,
      limits: options.limits,
    });
  let authorizeCaller = options.authorizeCaller;
  let releaseCaller = options.releaseCaller;
  if (authorizeCaller === undefined && releaseCaller === undefined) {
    const authority = createPolicyBridgeAuthority({
      policyBridge: options.policyBridge,
      mode: options.mode,
      timeoutSeconds: options.timeoutSeconds,
    });
    authority.check();
    authorizeCaller = authority.authorizeCaller;
    releaseCaller = authority.releaseCaller;
  }
  if (typeof authorizeCaller !== "function" || typeof releaseCaller !== "function") {
    reject("server_configuration_invalid", 500);
  }
  const handler = createOracleRpcHandler({
    limits: options.limits,
    replayGuard: options.replayGuard,
    resolveCaller,
    authorizeCaller,
    releaseCaller,
    runOracle,
    nowMs: options.nowMs,
  });
  const server = (options.createServer ?? http.createServer)(handler);
  server.maxHeadersCount = 32;
  server.headersTimeout = 10_000;
  server.requestTimeout = (options.timeoutSeconds ?? 7_200) * 1_000;
  await new Promise((resolvePromise, rejectPromise) => {
    server.once("error", rejectPromise);
    server.listen(port, bindAddress, () => {
      server.off("error", rejectPromise);
      resolvePromise();
    });
  });
  const actualPort = server.address()?.port;
  return Object.freeze({
    host,
    port: Number.isSafeInteger(actualPort) ? actualPort : port,
    close: () =>
      new Promise((resolvePromise, rejectPromise) =>
        server.close((error) => (error ? rejectPromise(error) : resolvePromise())),
      ),
    server,
  });
}

export function parseServerArguments(rawArguments) {
  if (
    rawArguments.length === 1 &&
    ["-h", "--help"].includes(rawArguments[0])
  ) {
    return Object.freeze({ help: true });
  }
  const parsed = {
    host: null,
    port: 4117,
    artifactRoot: join(homedir(), ".oracle", "oracle-subagent", "runs"),
    mode: "pro",
    policyBridge: null,
    requiredPeerTags: [],
  };
  for (let index = 0; index < rawArguments.length; index += 1) {
    const flag = rawArguments[index];
    const value = rawArguments[index + 1];
    if (typeof value !== "string") reject("arguments_invalid");
    index += 1;
    if (flag === "--bind-host") parsed.host = validateTailnetBindHost(value);
    else if (flag === "--port") parsed.port = Number(value);
    else if (flag === "--artifact-root") parsed.artifactRoot = resolve(value);
    else if (flag === "--policy-bridge" && isAbsolute(value)) parsed.policyBridge = value;
    else if (flag === "--mode" && ["pro", "deep-research"].includes(value)) parsed.mode = value;
    else if (flag === "--required-peer-tag" && TAG_PATTERN.test(value)) parsed.requiredPeerTags.push(value);
    else reject("arguments_invalid");
  }
  if (parsed.host === null) reject("arguments_invalid");
  if (parsed.policyBridge === null) reject("arguments_invalid");
  if (parsed.requiredPeerTags.length === 0) parsed.requiredPeerTags.push("tag:oracle-client");
  return Object.freeze(parsed);
}

export async function main(rawArguments = process.argv.slice(2), injected = {}) {
  try {
    const options = parseServerArguments(rawArguments);
    if (options.help) {
      process.stdout.write(`${SERVER_HELP}\n`);
      return 0;
    }
    const running = await startOracleRpcServer({ ...options, ...injected });
    process.stdout.write(
      `${JSON.stringify({ ok: true, host: running.host, port: running.port })}\n`,
    );
    return 0;
  } catch (error) {
    const failure = safeError(error);
    process.stderr.write(`oracle-rpc-server:${failure.code}\n`);
    return [
      "tailnet_bind_proof_unavailable",
      "tailnet_bind_proof_failed",
    ].includes(failure.code)
      ? 2
      : failure.code === "operation_failed"
        ? 3
        : 1;
  }
}

let invokedAsMain = false;
try {
  invokedAsMain =
    Boolean(process.argv[1]) &&
    import.meta.url === pathToFileURL(realpathSync(resolve(process.argv[1]))).href;
} catch {
  invokedAsMain = false;
}
if (invokedAsMain) {
  process.exitCode = await main();
}
