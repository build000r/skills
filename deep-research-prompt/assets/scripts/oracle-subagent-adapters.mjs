#!/usr/bin/env node

import { spawn } from "node:child_process";
import { constants as fsConstants } from "node:fs";
import { open, readFile, realpath } from "node:fs/promises";
import { isAbsolute, resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { withProvenOracleSnapshot } from "./oracle-capability-probe.mjs";
import {
  readRunRequest,
  runArtifactLayout,
  writeRunResult,
} from "./oracle-subagent-artifacts.mjs";
import {
  readReceiptFile,
  transitionReceiptFile,
} from "./oracle-subagent-state.mjs";
import {
  proveSelectorObservation,
  selectorPageProbeExpression,
} from "./chatgpt-selector-contract.mjs";
import {
  bindExactChatGptTarget,
  ChatGptComposerError,
  createLoopbackCdpTransport,
  normalizeExactChatGptUrl,
  normalizeExactTarget,
  normalizeLoopbackCdpEndpoint,
  runComposerAction,
} from "./chatgpt-composer.mjs";
import {
  captureConversationBaseline,
  OracleConversationError,
  probeConversation,
  proveCausalConversationUrl,
  proveDeepResearchCompleted,
  proveDeepResearchReview,
  proveDeepResearchStarted,
  proveProCompleted,
  proveProStarted,
  proveSubmittedUserTurn,
  waitForConversationEvidence,
} from "./await-deep-research.mjs";
import {
  DeepResearchComposerError,
  runDeepResearchAction,
} from "./toggle-deep-research.mjs";

export const ADAPTER_RESULT_SCHEMA = "oracle-subagent.adapter-result.v1";
export const PUBLIC_RENDER_INSTRUCTION =
  "Render the attached private oracle-subagent request and its referenced attachments as one submission-ready document. Follow the attached request exactly. Return only that document.";

const RUN_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$/;
const PRO_MODEL_PATTERN = /^gpt-[a-z0-9.]+-pro$/;
const MAX_RENDER_BYTES = 32 * 1024 * 1024;
const MAX_CONTROL_BYTES = 128 * 1024;
const SHARED_LIFECYCLE = Object.freeze([
  "model_tool_verified",
  "submitted",
  "started",
  "completed",
]);

export class OracleSubagentAdapterError extends Error {
  constructor(code) {
    super("oracle-subagent adapter: rejected");
    this.name = "OracleSubagentAdapterError";
    this.code = code;
  }
}

function reject(code) {
  throw new OracleSubagentAdapterError(code);
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

function clockNow(clock) {
  const value = clock.now();
  return canonicalTimestamp(value, "clock_invalid");
}

function normalizeConfiguration(rawConfiguration, now) {
  const configuration = exactObject(
    rawConfiguration,
    [
      "artifact_root",
      "run_id",
      "oracle_binary",
      "expected_manifest",
      "cdp_endpoint",
      "target_id",
      "target_url",
      "model",
    ],
    ["deadline_at", "poll_interval_ms", "max_polls"],
    "configuration_invalid",
  );
  if (
    typeof configuration.run_id !== "string" ||
    !RUN_ID_PATTERN.test(configuration.run_id) ||
    typeof configuration.model !== "string" ||
    !PRO_MODEL_PATTERN.test(configuration.model) ||
    !isPlainObject(configuration.expected_manifest)
  ) {
    reject("configuration_invalid");
  }
  const target = normalizeExactTarget({
    target_id: configuration.target_id,
    target_url: configuration.target_url,
  });
  const deadlineAt =
    configuration.deadline_at ??
    new Date(Date.parse(now) + 2 * 60 * 60 * 1000).toISOString();
  canonicalTimestamp(deadlineAt, "configuration_invalid");
  if (Date.parse(deadlineAt) <= Date.parse(now)) {
    reject("configuration_invalid");
  }
  const pollIntervalMs = configuration.poll_interval_ms ?? 1_000;
  const maxPolls = configuration.max_polls ?? 7_200;
  if (
    !Number.isSafeInteger(pollIntervalMs) ||
    pollIntervalMs < 0 ||
    pollIntervalMs > 60_000 ||
    !Number.isSafeInteger(maxPolls) ||
    maxPolls < 1 ||
    maxPolls > 10_000
  ) {
    reject("configuration_invalid");
  }
  return Object.freeze({
    artifact_root: absolutePath(
      configuration.artifact_root,
      "configuration_invalid",
    ),
    run_id: configuration.run_id,
    oracle_binary: absolutePath(
      configuration.oracle_binary,
      "configuration_invalid",
    ),
    expected_manifest: structuredClone(configuration.expected_manifest),
    cdp_endpoint: normalizeLoopbackCdpEndpoint(
      configuration.cdp_endpoint,
    ),
    target_id: target.target_id,
    target_url: target.target_url,
    model: configuration.model,
    deadline_at: deadlineAt,
    poll_interval_ms: pollIntervalMs,
    max_polls: maxPolls,
  });
}

async function assertPrivateRequestFile(pathname) {
  const flags =
    fsConstants.O_RDONLY |
    (fsConstants.O_NOFOLLOW ?? 0) |
    (fsConstants.O_CLOEXEC ?? 0);
  let handle;
  try {
    handle = await open(pathname, flags);
    const metadata = await handle.stat();
    if (
      !metadata.isFile() ||
      metadata.nlink !== 1 ||
      metadata.size < 1 ||
      (metadata.mode & 0o077) !== 0 ||
      (typeof process.getuid === "function" &&
        metadata.uid !== process.getuid()) ||
      (await realpath(pathname)) !== pathname
    ) {
      reject("request_file_invalid");
    }
  } catch (error) {
    if (error instanceof OracleSubagentAdapterError) throw error;
    reject("request_file_invalid");
  } finally {
    await handle?.close().catch(() => {});
  }
}

async function loadRunContext(configuration) {
  const layout = runArtifactLayout(
    configuration.artifact_root,
    configuration.run_id,
  );
  await assertPrivateRequestFile(layout.request);
  const [request, receipt] = await Promise.all([
    readRunRequest(layout),
    readReceiptFile(layout.receipt),
  ]);
  if (
    request.run_id !== configuration.run_id ||
    receipt.run_id !== configuration.run_id ||
    receipt.request_fingerprint !== request.request_fingerprint ||
    receipt.mode !== request.mode ||
    receipt.state !== "target_bound" ||
    receipt.target?.id !== configuration.target_id ||
    normalizeExactChatGptUrl(receipt.target?.url) !==
      configuration.target_url
  ) {
    reject("run_context_invalid");
  }
  return { layout, request, receipt };
}

export function oracleRenderArguments(
  snapshot,
  { layout, request, model },
) {
  if (
    !isPlainObject(snapshot) ||
    typeof snapshot.oracle_entry !== "string" ||
    typeof snapshot.package_root !== "string" ||
    !isPlainObject(snapshot.environment) ||
    !isPlainObject(layout) ||
    !isPlainObject(request) ||
    typeof model !== "string" ||
    !PRO_MODEL_PATTERN.test(model) ||
    !Array.isArray(request.attachments)
  ) {
    reject("render_configuration_invalid");
  }
  const arguments_ = [
    snapshot.oracle_entry,
    "--render",
    "--render-plain",
    "--engine",
    "browser",
    "--model",
    model,
    "--slug",
    request.slug,
    "-p",
    PUBLIC_RENDER_INSTRUCTION,
    "--file",
    layout.request,
  ];
  for (const attachment of request.attachments) {
    arguments_.push("--file", attachment.path);
  }
  return Object.freeze([...arguments_]);
}

async function collectRender(
  executable,
  arguments_,
  options,
  spawnImpl = spawn,
) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawnImpl(executable, arguments_, {
      cwd: options.cwd,
      env: options.env,
      stdio: ["ignore", "pipe", "pipe"],
      shell: false,
    });
    const standardOutput = [];
    let outputBytes = 0;
    let standardErrorBytes = 0;
    let settled = false;
    const fail = (code) => {
      if (settled) return;
      settled = true;
      try {
        child.kill("SIGKILL");
      } catch {}
      rejectPromise(new OracleSubagentAdapterError(code));
    };
    child.stdout.on("data", (chunk) => {
      outputBytes += chunk.length;
      if (outputBytes > MAX_RENDER_BYTES) {
        fail("render_output_too_large");
      } else {
        standardOutput.push(chunk);
      }
    });
    child.stderr.on("data", (chunk) => {
      standardErrorBytes += chunk.length;
      if (standardErrorBytes > 0) fail("render_stderr_rejected");
    });
    child.once("error", () => fail("render_spawn_failed"));
    child.once("exit", (code, signal) => {
      if (settled) return;
      settled = true;
      if (code !== 0 || signal !== null || standardErrorBytes !== 0) {
        rejectPromise(
          new OracleSubagentAdapterError("render_process_failed"),
        );
        return;
      }
      const rendered = Buffer.concat(standardOutput).toString("utf8");
      if (!rendered.trim()) {
        rejectPromise(new OracleSubagentAdapterError("render_empty"));
        return;
      }
      resolvePromise(rendered);
    });
  });
}

export async function renderRequestWithSnapshot(
  snapshot,
  renderContext,
  { spawnImpl = spawn } = {},
) {
  const arguments_ = oracleRenderArguments(snapshot, renderContext);
  return collectRender(
    process.execPath,
    arguments_,
    {
      cwd: snapshot.package_root,
      env: { ...snapshot.environment },
    },
    spawnImpl,
  );
}

async function selectorProof(
  transport,
  target,
  request,
  clock,
) {
  await bindExactChatGptTarget(transport, target);
  let observation;
  try {
    observation = await transport.evaluate(
      target.target_id,
      selectorPageProbeExpression(target.target_id),
    );
  } catch (error) {
    if (error instanceof ChatGptComposerError) throw error;
    reject("selector_probe_failed");
  }
  if (
    observation?.model_machine_id !== request.model ||
    !Array.isArray(observation?.catalog_pro_model_ids) ||
    observation.catalog_pro_model_ids.length !== 1 ||
    observation.catalog_pro_model_ids[0] !== request.model
  ) {
    reject("selector_proof_failed");
  }
  try {
    return proveSelectorObservation(observation, {
      target_id: target.target_id,
      target_url: target.target_url,
      mode: request.mode,
      model: request.model,
      now: clockNow(clock),
    });
  } catch {
    reject("selector_proof_failed");
  }
}

function modelToolEvidence(runId, proof) {
  return {
    run_id: runId,
    source: "browser",
    target_id: proof.target_id,
    model_requested: proof.model_requested,
    model_observed: proof.model_observed,
    model_proven: proof.model_proven,
    tool_requested: proof.tool_requested,
    tool_observed: proof.tool_observed,
    tool_proven: proof.tool_proven,
  };
}

function lifecycleTransitionEmitter(layout, clock) {
  return async (stage, evidence) => {
    const receipt = await readReceiptFile(layout.receipt);
    return transitionReceiptFile(layout.receipt, {
      to: stage,
      expectedRevision: receipt.revision,
      eventId: `adapter-${stage}-${receipt.revision}-${layout.run_id}`,
      observedAt: clockNow(clock),
      evidence,
    });
  };
}

async function refreshCausalTarget(transport, preSendTarget) {
  let targets;
  try {
    targets = await transport.listTargets();
  } catch (error) {
    if (error instanceof ChatGptComposerError) throw error;
    reject("target_refresh_failed");
  }
  if (!Array.isArray(targets)) reject("target_refresh_failed");
  const matches = targets.filter(
    (candidate) =>
      candidate?.type === "page" &&
      candidate.id === preSendTarget.target_id,
  );
  if (matches.length !== 1) reject("target_refresh_failed");
  const target = normalizeExactTarget({
    target_id: matches[0].id,
    target_url: matches[0].url,
  });
  proveCausalConversationUrl(
    preSendTarget.target_url,
    target.target_url,
  );
  return target;
}

function publicAdapterResult({
  request,
  target,
  submitted,
  started,
  completion,
  result,
  review,
}) {
  const value = {
    schema: ADAPTER_RESULT_SCHEMA,
    run_id: request.run_id,
    mode: request.mode,
    target_id: target.target_id,
    conversation_url: submitted.conversation_url,
    lifecycle_stages: [...SHARED_LIFECYCLE],
    user_turn_id: submitted.user_turn_id,
    assistant_signal_id: started.assistant_signal_id,
    final_assistant_turn_id: completion.final_assistant_turn_id,
    result: structuredClone(result),
  };
  if (review) {
    value.deep_research = {
      tool_proven: true,
      review_id: review.review_id,
      review_started: true,
      active_research_proven: true,
      dossier_proven: true,
    };
  }
  return Object.freeze(value);
}

export async function runOracleSubagentAdapter(
  rawConfiguration,
  injected = {},
) {
  if (!isPlainObject(injected)) reject("dependencies_invalid");
  const clock = injected.clock ?? {
    now: () => new Date().toISOString(),
  };
  const sleep =
    injected.sleep ??
    ((milliseconds) =>
      new Promise((resolvePromise) =>
        setTimeout(resolvePromise, milliseconds),
      ));
  if (typeof clock.now !== "function" || typeof sleep !== "function") {
    reject("dependencies_invalid");
  }
  const configuration = normalizeConfiguration(
    rawConfiguration,
    clockNow(clock),
  );
  const loadRun = injected.loadRun ?? loadRunContext;
  const withSnapshot =
    injected.withSnapshot ?? withProvenOracleSnapshot;
  const renderRequest =
    injected.renderRequest ?? renderRequestWithSnapshot;
  const transport =
    injected.transport ??
    createLoopbackCdpTransport(configuration.cdp_endpoint);
  if (
    typeof loadRun !== "function" ||
    typeof withSnapshot !== "function" ||
    typeof renderRequest !== "function"
  ) {
    reject("dependencies_invalid");
  }

  const context = await loadRun(configuration);
  if (
    !isPlainObject(context) ||
    !isPlainObject(context.layout) ||
    !isPlainObject(context.request) ||
    !isPlainObject(context.receipt)
  ) {
    reject("run_context_invalid");
  }
  const { layout, request, receipt } = context;
  if (
    request.run_id !== configuration.run_id ||
    receipt.run_id !== configuration.run_id ||
    receipt.mode !== request.mode ||
    receipt.request_fingerprint !== request.request_fingerprint ||
    receipt.state !== "target_bound" ||
    receipt.target?.id !== configuration.target_id ||
    normalizeExactChatGptUrl(receipt.target?.url) !==
      configuration.target_url ||
    !["pro", "deep-research"].includes(request.mode)
  ) {
    reject("run_context_invalid");
  }
  const target = normalizeExactTarget({
    target_id: configuration.target_id,
    target_url: configuration.target_url,
  });
  const selectorRequest = {
    mode: request.mode,
    model: configuration.model,
  };
  const emit =
    injected.emitLifecycle ??
    lifecycleTransitionEmitter(layout, clock);
  const writeResult =
    injected.writeResult ??
    ((content) => writeRunResult(layout, content));
  if (typeof emit !== "function" || typeof writeResult !== "function") {
    reject("dependencies_invalid");
  }

  await bindExactChatGptTarget(transport, target);
  const baseline = captureConversationBaseline(
    await probeConversation(transport, target),
  );

  await runComposerAction(transport, target, "select-pro", {
    model: configuration.model,
  });
  await runDeepResearchAction(transport, target, "set-tool", {
    enabled: request.mode === "deep-research",
  });
  await selectorProof(
    transport,
    target,
    selectorRequest,
    clock,
  );

  const snapshotSession = await withSnapshot(
    {
      oracle_binary: configuration.oracle_binary,
      expected_manifest: configuration.expected_manifest,
    },
    (snapshot) =>
      renderRequest(snapshot, {
        layout,
        request,
        model: configuration.model,
      }),
  );
  const rendered = snapshotSession?.value;
  if (
    typeof rendered !== "string" ||
    rendered.length === 0 ||
    Buffer.byteLength(rendered, "utf8") > MAX_RENDER_BYTES
  ) {
    reject("render_invalid");
  }

  await runComposerAction(transport, target, "replace-content", {
    content: rendered,
  });
  const verified = await selectorProof(
    transport,
    target,
    selectorRequest,
    clock,
  );
  await emit(
    "model_tool_verified",
    modelToolEvidence(request.run_id, verified),
  );

  // This is the final browser observation before the only send action.
  await selectorProof(
    transport,
    target,
    selectorRequest,
    clock,
  );
  await runComposerAction(transport, target, "send");

  const submitted = await waitForConversationEvidence({
    probe: async () => {
      const candidate = await refreshCausalTarget(
        transport,
        target,
      );
      return probeConversation(transport, candidate);
    },
    prove: (observation) =>
      proveSubmittedUserTurn(baseline, observation),
    sleep,
    poll_interval_ms: configuration.poll_interval_ms,
    max_polls: configuration.max_polls,
  });
  const conversationTarget = normalizeExactTarget({
    target_id: target.target_id,
    target_url: submitted.conversation_url,
  });
  const probe = () =>
    probeConversation(transport, conversationTarget);
  await emit("submitted", {
    run_id: request.run_id,
    source: "browser",
    target_id: target.target_id,
    conversation_url: submitted.conversation_url,
    baseline_assistant_turn_id:
      baseline.baseline_assistant_turn_id,
    baseline_assistant_turn_position:
      baseline.baseline_assistant_turn_position,
    user_turn_id: submitted.user_turn_id,
    user_turn_position: submitted.user_turn_position,
    request_fingerprint: request.request_fingerprint,
    deadline_at: configuration.deadline_at,
  });

  let review = null;
  let started;
  let completion;
  if (request.mode === "deep-research") {
    review = await waitForConversationEvidence({
      probe,
      prove: (observation) =>
        proveDeepResearchReview(observation, submitted),
      sleep,
      poll_interval_ms: configuration.poll_interval_ms,
      max_polls: configuration.max_polls,
    });
    const startedReview = await runDeepResearchAction(
      transport,
      conversationTarget,
      "start-review",
      { user_message_id: submitted.raw_user_message_id },
    );
    if (
      startedReview.review_id !== review.review_id ||
      startedReview.parent_user_message_id !==
        submitted.raw_user_message_id
    ) {
      reject("review_binding_invalid");
    }
    started = await waitForConversationEvidence({
      probe,
      prove: (observation) =>
        proveDeepResearchStarted(observation, submitted, review),
      sleep,
      poll_interval_ms: configuration.poll_interval_ms,
      max_polls: configuration.max_polls,
    });
    await emit("started", {
      run_id: request.run_id,
      source: "browser",
      target_id: target.target_id,
      conversation_url: submitted.conversation_url,
      user_turn_id: submitted.user_turn_id,
      assistant_signal_id: started.assistant_signal_id,
      assistant_signal_position: started.assistant_signal_position,
    });
    completion = await waitForConversationEvidence({
      probe,
      prove: (observation) =>
        proveDeepResearchCompleted(
          observation,
          submitted,
          started,
        ),
      sleep,
      poll_interval_ms: configuration.poll_interval_ms,
      max_polls: configuration.max_polls,
    });
  } else {
    started = await waitForConversationEvidence({
      probe,
      prove: (observation) =>
        proveProStarted(observation, submitted),
      sleep,
      poll_interval_ms: configuration.poll_interval_ms,
      max_polls: configuration.max_polls,
    });
    await emit("started", {
      run_id: request.run_id,
      source: "browser",
      target_id: target.target_id,
      conversation_url: submitted.conversation_url,
      user_turn_id: submitted.user_turn_id,
      assistant_signal_id: started.assistant_signal_id,
      assistant_signal_position: started.assistant_signal_position,
    });
    completion = await waitForConversationEvidence({
      probe,
      prove: (observation) =>
        proveProCompleted(observation, submitted, started),
      sleep,
      poll_interval_ms: configuration.poll_interval_ms,
      max_polls: configuration.max_polls,
    });
  }

  if (!completion.content) reject("completion_empty");
  const result = await writeResult(completion.content);
  await emit("completed", {
    run_id: request.run_id,
    source: "browser",
    target_id: target.target_id,
    conversation_url: submitted.conversation_url,
    user_turn_id: submitted.user_turn_id,
    final_assistant_turn_id:
      completion.final_assistant_turn_id,
    final_assistant_turn_position:
      completion.final_assistant_turn_position,
    result,
  });

  return publicAdapterResult({
    request,
    target,
    submitted,
    started,
    completion,
    result,
    review,
  });
}

async function readPrivateControl(pathname) {
  pathname = absolutePath(pathname, "control_invalid");
  const flags =
    fsConstants.O_RDONLY |
    (fsConstants.O_NOFOLLOW ?? 0) |
    (fsConstants.O_CLOEXEC ?? 0);
  let handle;
  try {
    handle = await open(pathname, flags);
    const metadata = await handle.stat();
    if (
      !metadata.isFile() ||
      metadata.nlink !== 1 ||
      (metadata.mode & 0o077) !== 0 ||
      metadata.size < 1 ||
      metadata.size > MAX_CONTROL_BYTES ||
      (typeof process.getuid === "function" &&
        metadata.uid !== process.getuid()) ||
      (await realpath(pathname)) !== pathname
    ) {
      reject("control_invalid");
    }
    return JSON.parse(await handle.readFile("utf8"));
  } catch (error) {
    if (error instanceof OracleSubagentAdapterError) throw error;
    reject("control_invalid");
  } finally {
    await handle?.close().catch(() => {});
  }
}

export async function main(rawArguments = process.argv.slice(2)) {
  if (
    rawArguments.length !== 2 ||
    rawArguments[0] !== "--control-file"
  ) {
    reject("arguments_invalid");
  }
  const control = exactObject(
    await readPrivateControl(rawArguments[1]),
    [
      "artifact_root",
      "run_id",
      "oracle_binary",
      "manifest_path",
      "cdp_endpoint",
      "target_id",
      "target_url",
      "model",
    ],
    ["deadline_at", "poll_interval_ms", "max_polls"],
    "control_invalid",
  );
  let expectedManifest;
  try {
    expectedManifest = JSON.parse(
      await readFile(
        absolutePath(control.manifest_path, "control_invalid"),
        "utf8",
      ),
    );
  } catch {
    reject("control_invalid");
  }
  const { manifest_path: _manifestPath, ...configuration } = control;
  const result = await runOracleSubagentAdapter({
    ...configuration,
    expected_manifest: expectedManifest,
  });
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

const invokedPath = process.argv[1]
  ? pathToFileURL(resolve(process.argv[1])).href
  : "";
if (invokedPath === import.meta.url) {
  main().catch((error) => {
    const recognized =
      error instanceof OracleSubagentAdapterError ||
      error instanceof ChatGptComposerError ||
      error instanceof OracleConversationError ||
      error instanceof DeepResearchComposerError;
    process.stderr.write(
      `oracle-subagent-adapters:${
        recognized ? error.code : "unexpected_failure"
      }\n`,
    );
    process.exitCode = 1;
  });
}
