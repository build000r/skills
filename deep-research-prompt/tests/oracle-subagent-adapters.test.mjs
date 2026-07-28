import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import {
  mkdtemp,
  readFile,
  realpath,
  rm,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  ADAPTER_RESULT_SCHEMA,
  OracleSubagentAdapterError,
  PUBLIC_RENDER_INSTRUCTION,
  oracleRenderArguments,
  runOracleSubagentAdapter,
} from "../assets/scripts/oracle-subagent-adapters.mjs";
import {
  composerPageActionDeclaration,
  createLoopbackCdpTransport,
  normalizeLoopbackCdpEndpoint,
} from "../assets/scripts/chatgpt-composer.mjs";
import {
  captureConversationBaseline,
  conversationPageProbeExpression,
  EMPTY_ROOT_BASELINE_TURN_ID,
  EMPTY_ROOT_BASELINE_TURN_POSITION,
  OracleConversationError,
  proveCausalConversationUrl,
  proveDeepResearchCompleted,
  proveSubmittedUserTurn,
} from "../assets/scripts/await-deep-research.mjs";
import {
  deepResearchPageActionDeclaration,
} from "../assets/scripts/toggle-deep-research.mjs";
import {
  createRunArtifacts,
} from "../assets/scripts/oracle-subagent-artifacts.mjs";
import {
  readReceiptFile,
  transitionReceiptFile,
} from "../assets/scripts/oracle-subagent-state.mjs";

const TARGET_ID = "A".repeat(32);
const TARGET_URL = "https://chatgpt.com/c/adapter-proof";
const ROOT_TARGET_URL = "https://chatgpt.com/";
const FRESH_CONVERSATION_URL =
  "https://chatgpt.com/c/adapter-fresh-root";
const MODEL = "gpt-5.4-pro";
const NOW = "2026-07-28T08:30:00.000Z";
const DEADLINE = "2026-07-28T10:30:00.000Z";
const FINGERPRINT = "f".repeat(64);
const RAW_PROMPT =
  "PRIVATE_REQUEST_SENTINEL research confidential acquisition details";
const RENDERED = `Rendered private bundle: ${RAW_PROMPT}`;

function selectorObservation(
  mode,
  overrides = {},
  targetUrl = TARGET_URL,
) {
  return {
    schema: "oracle-subagent.selector-observation.v1",
    observed_at: NOW,
    target_id: TARGET_ID,
    target_url: targetUrl,
    composer_count: 1,
    composer_visible: true,
    prompt_field_count: 1,
    model_control_count: 1,
    model_control_enabled: true,
    model_machine_id: MODEL,
    model_selection: "pro",
    catalog_pro_model_ids: [MODEL],
    active_tool_count: mode === "deep-research" ? 1 : 0,
    active_tools_enabled: true,
    tool_selection:
      mode === "deep-research" ? "deep-research" : "none",
    ...overrides,
  };
}

function turn(rawId, role, position, status, content = "") {
  return {
    raw_id: rawId,
    role,
    position,
    status,
    content,
  };
}

function conversationObservation({
  turns,
  reviewCards = [],
  activeResearch = [],
  dossiers = [],
  overrides = {},
}) {
  return {
    schema: "oracle-subagent.conversation-observation.v1",
    observed_at: NOW,
    target_id: TARGET_ID,
    target_url: TARGET_URL,
    main_count: 1,
    turns,
    review_cards: reviewCards,
    active_research: activeResearch,
    dossiers,
    ...overrides,
  };
}

const baselineTurn = turn(
  "assistant-baseline-001",
  "assistant",
  10,
  "completed",
  "An existing completed assistant turn.",
);
const submittedTurn = turn(
  "user-request-001",
  "user",
  20,
  "submitted",
);
const proAssistantStreaming = turn(
  "assistant-result-001",
  "assistant",
  30,
  "streaming",
);
const proAssistantCompleted = turn(
  "assistant-result-001",
  "assistant",
  30,
  "completed",
  "# Standard Pro result\n\nVerified result.",
);
const deepAssistantStreaming = turn(
  "assistant-research-001",
  "assistant",
  30,
  "streaming",
);
const deepAssistantCompleted = turn(
  "assistant-research-001",
  "assistant",
  30,
  "completed",
  "# Deep Research dossier\n\nComplete.",
);
const freshSubmittedTurn = turn(
  "user-request-001",
  "user",
  10,
  "submitted",
);
const freshProAssistantStreaming = turn(
  "assistant-result-001",
  "assistant",
  20,
  "streaming",
);
const freshProAssistantCompleted = turn(
  "assistant-result-001",
  "assistant",
  20,
  "completed",
  "# Fresh-root Standard Pro result\n\nVerified result.",
);
const freshDeepAssistantStreaming = turn(
  "assistant-research-001",
  "assistant",
  20,
  "streaming",
);
const freshDeepAssistantCompleted = turn(
  "assistant-research-001",
  "assistant",
  20,
  "completed",
  "# Fresh-root Deep Research dossier\n\nComplete.",
);

function proConversationSequence() {
  return [
    conversationObservation({ turns: [baselineTurn] }),
    conversationObservation({
      turns: [baselineTurn, submittedTurn],
    }),
    conversationObservation({
      turns: [
        baselineTurn,
        submittedTurn,
        proAssistantStreaming,
      ],
    }),
    conversationObservation({
      turns: [
        baselineTurn,
        submittedTurn,
        proAssistantCompleted,
      ],
    }),
  ];
}

function deepConversationSequence({
  reviewParent = "user-request-001",
  dossierContent = "# Deep Research dossier\n\nComplete.",
} = {}) {
  return [
    conversationObservation({ turns: [baselineTurn] }),
    conversationObservation({
      turns: [baselineTurn, submittedTurn],
    }),
    conversationObservation({
      turns: [baselineTurn, submittedTurn],
      reviewCards: [
        {
          review_id: "review-card-001",
          parent_user_message_id: reviewParent,
          state: "awaiting-start",
        },
      ],
    }),
    conversationObservation({
      turns: [
        baselineTurn,
        submittedTurn,
        deepAssistantStreaming,
      ],
      activeResearch: [
        {
          research_id: "research-active-001",
          parent_user_message_id: "user-request-001",
          assistant_message_id: "assistant-research-001",
          position: 30,
        },
      ],
    }),
    conversationObservation({
      turns: [
        baselineTurn,
        submittedTurn,
        deepAssistantCompleted,
      ],
      dossiers: [
        {
          dossier_id: "dossier-result-001",
          research_id: "research-active-001",
          parent_user_message_id: "user-request-001",
          assistant_message_id: "assistant-research-001",
          position: 30,
          content: dossierContent,
        },
      ],
    }),
  ];
}

function freshRootProConversationSequence() {
  return [
    conversationObservation({
      turns: [],
      overrides: { target_url: ROOT_TARGET_URL },
    }),
    conversationObservation({
      turns: [freshSubmittedTurn],
      overrides: { target_url: FRESH_CONVERSATION_URL },
    }),
    conversationObservation({
      turns: [freshSubmittedTurn, freshProAssistantStreaming],
      overrides: { target_url: FRESH_CONVERSATION_URL },
    }),
    conversationObservation({
      turns: [freshSubmittedTurn, freshProAssistantCompleted],
      overrides: { target_url: FRESH_CONVERSATION_URL },
    }),
  ];
}

function freshRootDeepConversationSequence() {
  return [
    conversationObservation({
      turns: [],
      overrides: { target_url: ROOT_TARGET_URL },
    }),
    conversationObservation({
      turns: [freshSubmittedTurn],
      overrides: { target_url: FRESH_CONVERSATION_URL },
    }),
    conversationObservation({
      turns: [freshSubmittedTurn],
      reviewCards: [
        {
          review_id: "review-card-001",
          parent_user_message_id: "user-request-001",
          state: "awaiting-start",
        },
      ],
      overrides: { target_url: FRESH_CONVERSATION_URL },
    }),
    conversationObservation({
      turns: [freshSubmittedTurn, freshDeepAssistantStreaming],
      activeResearch: [
        {
          research_id: "research-active-001",
          parent_user_message_id: "user-request-001",
          assistant_message_id: "assistant-research-001",
          position: 20,
        },
      ],
      overrides: { target_url: FRESH_CONVERSATION_URL },
    }),
    conversationObservation({
      turns: [freshSubmittedTurn, freshDeepAssistantCompleted],
      dossiers: [
        {
          dossier_id: "dossier-result-001",
          research_id: "research-active-001",
          parent_user_message_id: "user-request-001",
          assistant_message_id: "assistant-research-001",
          position: 20,
          content:
            "# Fresh-root Deep Research dossier\n\nComplete.",
        },
      ],
      overrides: { target_url: FRESH_CONVERSATION_URL },
    }),
  ];
}

function runContext(mode, targetUrl = TARGET_URL) {
  const runId = `run-adapter-${mode.replaceAll("-", "")}`;
  const layout = {
    root: "/private/oracle-artifacts",
    run_id: runId,
    directory: `/private/oracle-artifacts/${runId}`,
    request: `/private/oracle-artifacts/${runId}/request.json`,
    events: `/private/oracle-artifacts/${runId}/events.ndjson`,
    receipt: `/private/oracle-artifacts/${runId}/receipt.json`,
    result: `/private/oracle-artifacts/${runId}/result.md`,
  };
  const request = {
    schema: "oracle-subagent.request.v1",
    run_id: runId,
    slug: `adapter-${mode}`,
    mode,
    request_fingerprint: FINGERPRINT,
    prompt: RAW_PROMPT,
    attachments: [
      {
        path: "/private/oracle-input/context.pdf",
        bytes: 123,
        sha256: "a".repeat(64),
        media_type: "application/pdf",
      },
    ],
    created_at: NOW,
    event_id: `event-created-${mode}`,
  };
  const receipt = {
    run_id: runId,
    mode,
    request_fingerprint: FINGERPRINT,
    state: "target_bound",
    target: {
      id: TARGET_ID,
      url: targetUrl,
      browser_pid: 4242,
    },
  };
  return { layout, request, receipt };
}

function adapterConfiguration(runId, overrides = {}) {
  return {
    artifact_root: "/private/oracle-artifacts",
    run_id: runId,
    oracle_binary: "/opt/homebrew/bin/oracle",
    expected_manifest: {
      schema: "oracle-capability-pin.test",
    },
    cdp_endpoint: "http://127.0.0.1:9222",
    target_id: TARGET_ID,
    target_url: TARGET_URL,
    model: MODEL,
    deadline_at: DEADLINE,
    poll_interval_ms: 0,
    max_polls: 1,
    ...overrides,
  };
}

function fakeTransport(
  mode,
  conversations,
  selectorOverrides = {},
  {
    pre_send_url = TARGET_URL,
    post_send_url = pre_send_url,
  } = {},
) {
  const calls = [];
  let selectorCount = 0;
  let conversationCount = 0;
  let currentTargetUrl = pre_send_url;
  const transport = {
    calls,
    async listTargets() {
      calls.push({ channel: "target-list" });
      return [
        {
          id: TARGET_ID,
          type: "page",
          url: currentTargetUrl,
        },
      ];
    },
    async evaluate(targetId, expression) {
      assert.equal(targetId, TARGET_ID);
      if (expression.includes("selector-observation")) {
        selectorCount += 1;
        calls.push({
          channel: "Runtime.evaluate",
          kind: "selector",
          ordinal: selectorCount,
        });
        return selectorObservation(
          mode,
          selectorOverrides,
          currentTargetUrl,
        );
      }
      if (expression.includes("conversation-observation")) {
        const value =
          conversations[
            Math.min(conversationCount, conversations.length - 1)
          ];
        conversationCount += 1;
        calls.push({
          channel: "Runtime.evaluate",
          kind: "conversation",
          ordinal: conversationCount,
        });
        return structuredClone(value);
      }
      throw new Error("unexpected expression");
    },
    async invoke(targetId, functionDeclaration, arguments_) {
      assert.equal(targetId, TARGET_ID);
      const [action, payload] = arguments_;
      const source =
        functionDeclaration.includes("start-review")
          ? "deep-research"
          : "composer";
      calls.push({
        channel: "Runtime.callFunctionOn",
        source,
        action,
        payload: structuredClone(payload),
      });
      if (action === "start-review") {
        return {
          ok: true,
          review_id: "review-card-001",
          parent_user_message_id: "user-request-001",
          started: true,
        };
      }
      if (action === "set-tool") {
        return {
          ok: true,
          tool: payload.enabled ? "deep-research" : "none",
          enabled: true,
        };
      }
      if (action === "select-pro") {
        return { ok: true, selected_model: payload.model };
      }
      if (action === "replace-content") {
        return {
          ok: true,
          target_url: currentTargetUrl,
          prompt_field_count: 1,
          prompt_length: payload.content.length,
        };
      }
      if (action === "send") {
        currentTargetUrl = post_send_url;
        return { ok: true, sent: true };
      }
      throw new Error(`unexpected action ${action}`);
    },
  };
  return transport;
}

function fakeDependencies(
  context,
  transport,
  { rendered = RENDERED } = {},
) {
  const lifecycle = [];
  const writes = [];
  const snapshotCalls = [];
  const renderCalls = [];
  return {
    lifecycle,
    writes,
    snapshotCalls,
    renderCalls,
    dependencies: {
      transport,
      clock: { now: () => NOW },
      sleep: async () => {},
      loadRun: async () => structuredClone(context),
      withSnapshot: async (options, callback) => {
        snapshotCalls.push(structuredClone(options));
        const value = await callback({
          proof: {
            schema: "oracle-capability-proof.test",
            submit_performed: false,
          },
          oracle_entry:
            "/private/snapshot/oracle-package/dist/bin/oracle-cli.js",
          package_root: "/private/snapshot/oracle-package",
          oracle_home: "/private/snapshot",
          environment: {
            CI: "1",
            LANG: "C",
            LC_ALL: "C",
            NO_COLOR: "1",
            ORACLE_HOME_DIR: "/private/snapshot",
            PATH: "/usr/bin:/bin",
          },
        });
        return {
          proof: {
            schema: "oracle-capability-proof.test",
            submit_performed: false,
          },
          value,
        };
      },
      renderRequest: async (snapshot, renderContext) => {
        renderCalls.push({
          snapshot: structuredClone(snapshot),
          renderContext: structuredClone(renderContext),
        });
        return rendered;
      },
      emitLifecycle: async (stage, evidence) => {
        lifecycle.push({
          stage,
          evidence: structuredClone(evidence),
        });
        return { state: stage };
      },
      writeResult: async (content) => {
        writes.push(content);
        return {
          path: context.layout.result,
          bytes: Buffer.byteLength(content),
          sha256: "b".repeat(64),
          run_id: context.request.run_id,
          atomic_write_id: `write-${context.request.run_id}`,
          proof_path: `${context.layout.result}.oracle-write-proof.json`,
        };
      },
    },
  };
}

function actionRecords(transport, action) {
  return transport.calls.filter(
    (call) =>
      call.channel === "Runtime.callFunctionOn" &&
      call.action === action,
  );
}

function runNodeCli(script, arguments_, input = "") {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(
      process.execPath,
      [fileURLToPath(script), ...arguments_],
      {
        stdio: ["pipe", "pipe", "pipe"],
      },
    );
    const stdout = [];
    const stderr = [];
    child.stdout.on("data", (chunk) => stdout.push(chunk));
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.once("error", rejectPromise);
    child.once("close", (status, signal) => {
      resolvePromise({
        status,
        signal,
        stdout: Buffer.concat(stdout).toString("utf8"),
        stderr: Buffer.concat(stderr).toString("utf8"),
      });
    });
    child.stdin.end(input);
  });
}

test("standard Pro uses immutable render seam, exact pre-send proof, and the shared lifecycle", async () => {
  const context = runContext("pro");
  const transport = fakeTransport("pro", proConversationSequence());
  const harness = fakeDependencies(context, transport);
  const result = await runOracleSubagentAdapter(
    adapterConfiguration(context.request.run_id),
    harness.dependencies,
  );

  assert.equal(result.schema, ADAPTER_RESULT_SCHEMA);
  assert.equal(result.mode, "pro");
  assert.deepEqual(result.lifecycle_stages, [
    "model_tool_verified",
    "submitted",
    "started",
    "completed",
  ]);
  assert.deepEqual(
    harness.lifecycle.map((event) => event.stage),
    result.lifecycle_stages,
  );
  assert.equal(actionRecords(transport, "send").length, 1);
  assert.equal(actionRecords(transport, "start-review").length, 0);
  assert(
    transport.calls
      .filter((call) => call.channel === "Runtime.callFunctionOn")
      .every(
        (call) => call.payload.expected_target_url === TARGET_URL,
      ),
  );
  assert.equal(
    transport.calls.filter(
      (call) =>
        call.channel === "Runtime.evaluate" &&
        call.kind === "selector",
    ).length,
    3,
  );
  const sendIndex = transport.calls.findIndex(
    (call) => call.action === "send",
  );
  const immediateProofIndex = transport.calls
    .map((call, index) => ({ call, index }))
    .filter(
      ({ call }) =>
        call.channel === "Runtime.evaluate" &&
        call.kind === "selector",
    )
    .at(-1).index;
  assert(immediateProofIndex < sendIndex);
  assert.equal(
    transport.calls
      .slice(immediateProofIndex + 1, sendIndex)
      .filter((call) => call.channel === "Runtime.callFunctionOn")
      .length,
    0,
  );
  assert.equal(harness.snapshotCalls.length, 1);
  assert.equal(harness.renderCalls.length, 1);
  assert.equal(harness.writes[0], "# Standard Pro result\n\nVerified result.");
  assert.match(result.user_turn_id, /^user:user-request-001:submitted$/);
  assert.match(
    result.assistant_signal_id,
    /^assistant:assistant-result-001:started$/,
  );
  assert.match(
    result.final_assistant_turn_id,
    /^assistant:assistant-result-001:completed$/,
  );
  const promptBearingCdpCalls = transport.calls.filter((call) =>
    JSON.stringify(call).includes(RAW_PROMPT),
  );
  assert.equal(promptBearingCdpCalls.length, 1);
  assert.equal(
    promptBearingCdpCalls[0].channel,
    "Runtime.callFunctionOn",
  );
  assert.equal(promptBearingCdpCalls[0].action, "replace-content");
  assert.doesNotMatch(
    JSON.stringify(harness.lifecycle),
    new RegExp(RAW_PROMPT),
  );
  assert.doesNotMatch(JSON.stringify(result), new RegExp(RAW_PROMPT));
});

test("Deep Research proves exact tool, bound review Start, active research, dossier, and the same lifecycle", async () => {
  const context = runContext("deep-research");
  const transport = fakeTransport(
    "deep-research",
    deepConversationSequence(),
  );
  const harness = fakeDependencies(context, transport);
  const result = await runOracleSubagentAdapter(
    adapterConfiguration(context.request.run_id),
    harness.dependencies,
  );

  assert.deepEqual(
    harness.lifecycle.map((event) => event.stage),
    ["model_tool_verified", "submitted", "started", "completed"],
  );
  assert.deepEqual(result.lifecycle_stages, [
    "model_tool_verified",
    "submitted",
    "started",
    "completed",
  ]);
  assert.deepEqual(result.deep_research, {
    tool_proven: true,
    review_id: "review-card-001",
    review_started: true,
    active_research_proven: true,
    dossier_proven: true,
  });
  assert.equal(actionRecords(transport, "send").length, 1);
  assert.equal(actionRecords(transport, "start-review").length, 1);
  assert.equal(
    actionRecords(transport, "start-review")[0].payload
      .user_message_id,
    "user-request-001",
  );
  assert.equal(
    harness.writes[0],
    "# Deep Research dossier\n\nComplete.",
  );
  const submitted = harness.lifecycle[1].evidence;
  const started = harness.lifecycle[2].evidence;
  const completed = harness.lifecycle[3].evidence;
  assert(
    submitted.baseline_assistant_turn_position <
      submitted.user_turn_position,
  );
  assert(
    submitted.user_turn_position <
      started.assistant_signal_position,
  );
  assert(
    started.assistant_signal_position <
      completed.final_assistant_turn_position,
  );
});

test("fresh-root Deep Research proves the causal conversation transition and full dossier chain", async () => {
  const context = runContext("deep-research", ROOT_TARGET_URL);
  const transport = fakeTransport(
    "deep-research",
    freshRootDeepConversationSequence(),
    {},
    {
      pre_send_url: ROOT_TARGET_URL,
      post_send_url: FRESH_CONVERSATION_URL,
    },
  );
  const harness = fakeDependencies(context, transport);
  const result = await runOracleSubagentAdapter(
    adapterConfiguration(context.request.run_id, {
      target_url: ROOT_TARGET_URL,
    }),
    harness.dependencies,
  );

  assert.equal(result.conversation_url, FRESH_CONVERSATION_URL);
  assert.deepEqual(
    harness.lifecycle.map((event) => event.stage),
    ["model_tool_verified", "submitted", "started", "completed"],
  );
  assert.equal(
    harness.lifecycle[1].evidence.baseline_assistant_turn_id,
    EMPTY_ROOT_BASELINE_TURN_ID,
  );
  assert.equal(
    harness.lifecycle[1].evidence.baseline_assistant_turn_position,
    EMPTY_ROOT_BASELINE_TURN_POSITION,
  );
  assert.equal(actionRecords(transport, "send").length, 1);
  assert.equal(
    actionRecords(transport, "send")[0].payload.expected_target_url,
    ROOT_TARGET_URL,
  );
  assert.equal(actionRecords(transport, "start-review").length, 1);
  assert.equal(
    actionRecords(transport, "start-review")[0].payload
      .expected_target_url,
    FRESH_CONVERSATION_URL,
  );
  assert.deepEqual(result.deep_research, {
    tool_proven: true,
    review_id: "review-card-001",
    review_started: true,
    active_research_proven: true,
    dossier_proven: true,
  });
  assert.equal(
    harness.writes[0],
    "# Fresh-root Deep Research dossier\n\nComplete.",
  );
});

test("production fresh-root Pro artifact, receipt, and atomic result paths complete under fake Oracle/CDP only", async (t) => {
  const root = await realpath(
    await mkdtemp(path.join(os.tmpdir(), "oracle-adapter-integration-")),
  );
  t.after(async () => {
    await rm(root, { recursive: true, force: true });
  });
  const runId = "run-adapter-integration";
  const created = await createRunArtifacts(root, {
    run_id: runId,
    slug: "adapter-integration",
    mode: "pro",
    request_fingerprint: FINGERPRINT,
    prompt: RAW_PROMPT,
    attachments: [],
    created_at: "2026-07-28T08:00:00.000Z",
    event_id: "event-created-integration",
  });
  await transitionReceiptFile(created.layout.receipt, {
    to: "auth_ready",
    expectedRevision: 0,
    eventId: "event-auth-integration",
    observedAt: "2026-07-28T08:01:00.000Z",
    evidence: {
      run_id: runId,
      source: "browser",
      profile_fingerprint: "c".repeat(64),
      challenge_observed: false,
    },
  });
  await transitionReceiptFile(created.layout.receipt, {
    to: "target_bound",
    expectedRevision: 1,
    eventId: "event-target-integration",
    observedAt: "2026-07-28T08:02:00.000Z",
    evidence: {
      run_id: runId,
      source: "browser",
      target_id: TARGET_ID,
      target_url: ROOT_TARGET_URL,
      browser_pid: 4242,
    },
  });

  const transport = fakeTransport(
    "pro",
    freshRootProConversationSequence(),
    {},
    {
      pre_send_url: ROOT_TARGET_URL,
      post_send_url: FRESH_CONVERSATION_URL,
    },
  );
  const result = await runOracleSubagentAdapter(
    {
      ...adapterConfiguration(runId),
      artifact_root: root,
      target_url: ROOT_TARGET_URL,
    },
    {
      transport,
      clock: { now: () => NOW },
      sleep: async () => {},
      withSnapshot: async (options, callback) => ({
        proof: {
          schema: "oracle-capability-proof.test",
          submit_performed: false,
        },
        value: await callback({
          proof: {
            schema: "oracle-capability-proof.test",
            submit_performed: false,
          },
          oracle_entry:
            "/private/snapshot/oracle-package/dist/bin/oracle-cli.js",
          package_root: "/private/snapshot/oracle-package",
          oracle_home: "/private/snapshot",
          environment: {
            CI: "1",
            LANG: "C",
            LC_ALL: "C",
            NO_COLOR: "1",
            ORACLE_HOME_DIR: "/private/snapshot",
            PATH: "/usr/bin:/bin",
          },
        }),
      }),
      renderRequest: async () => RENDERED,
    },
  );

  const receipt = await readReceiptFile(created.layout.receipt);
  assert.equal(result.mode, "pro");
  assert.equal(result.conversation_url, FRESH_CONVERSATION_URL);
  assert.equal(receipt.state, "completed");
  assert.equal(receipt.revision, 6);
  assert.deepEqual(
    receipt.history.slice(-4).map((event) => event.to),
    ["model_tool_verified", "submitted", "started", "completed"],
  );
  assert.equal(receipt.result.path, created.layout.result);
  assert.equal(receipt.result.sha256, result.result.sha256);
  const submittedHistory = receipt.history.find(
    (event) => event.to === "submitted",
  );
  assert.equal(
    submittedHistory.evidence.baseline_assistant_turn_id,
    EMPTY_ROOT_BASELINE_TURN_ID,
  );
  assert.equal(
    submittedHistory.evidence.baseline_assistant_turn_position,
    EMPTY_ROOT_BASELINE_TURN_POSITION,
  );
  assert.equal(
    await readFile(created.layout.result, "utf8"),
    "# Fresh-root Standard Pro result\n\nVerified result.",
  );
});

test("Oracle render argv contains only the immutable entry, fixed instruction, and file paths", () => {
  const context = runContext("deep-research");
  const snapshot = {
    oracle_entry:
      "/private/snapshot/oracle-package/dist/bin/oracle-cli.js",
    package_root: "/private/snapshot/oracle-package",
    environment: {
      CI: "1",
      LANG: "C",
      LC_ALL: "C",
      NO_COLOR: "1",
      ORACLE_HOME_DIR: "/private/snapshot",
      PATH: "/usr/bin:/bin",
    },
  };
  const arguments_ = oracleRenderArguments(snapshot, {
    layout: context.layout,
    request: context.request,
    model: MODEL,
  });
  assert.equal(arguments_[0], snapshot.oracle_entry);
  assert(arguments_.includes("--render"));
  assert(arguments_.includes(PUBLIC_RENDER_INSTRUCTION));
  assert(arguments_.includes(context.layout.request));
  assert(arguments_.includes(context.request.attachments[0].path));
  assert(!arguments_.includes(context.request.prompt));
  assert.doesNotMatch(JSON.stringify(arguments_), new RegExp(RAW_PROMPT));
});

test("wrong or stale exact selector proof stops before send", async (t) => {
  for (const [name, overrides] of [
    ["wrong model", { model_selection: "instant" }],
    ["missing machine model id", { model_machine_id: null }],
    [
      "stale observation",
      { observed_at: "2026-07-28T08:00:00.000Z" },
    ],
    [
      "wrong tool",
      {
        active_tool_count: 1,
        tool_selection: "deep-research",
      },
    ],
  ]) {
    await t.test(name, async () => {
      const context = runContext("pro");
      const transport = fakeTransport(
        "pro",
        proConversationSequence(),
        overrides,
      );
      const harness = fakeDependencies(context, transport);
      await assert.rejects(
        runOracleSubagentAdapter(
          adapterConfiguration(context.request.run_id),
          harness.dependencies,
        ),
        (error) => {
          assert(error instanceof OracleSubagentAdapterError);
          assert.equal(error.code, "selector_proof_failed");
          assert.equal(
            error.message,
            "oracle-subagent adapter: rejected",
          );
          return true;
        },
      );
      assert.equal(actionRecords(transport, "send").length, 0);
      assert.deepEqual(harness.lifecycle, []);
      assert.deepEqual(harness.writes, []);
    });
  }
});

test("exact target mismatch fails before any page action", async () => {
  const context = runContext("pro");
  const transport = fakeTransport("pro", proConversationSequence());
  transport.listTargets = async () => [
    {
      id: TARGET_ID,
      type: "page",
      url: "https://chatgpt.com/c/different",
    },
  ];
  const harness = fakeDependencies(context, transport);
  await assert.rejects(
    runOracleSubagentAdapter(
      adapterConfiguration(context.request.run_id),
      harness.dependencies,
    ),
    (error) => error?.code === "target_mismatch",
  );
  assert.equal(
    transport.calls.filter(
      (call) => call.channel === "Runtime.callFunctionOn",
    ).length,
    0,
  );
});

test("post-send drift to another conversation fails before submission", async () => {
  const context = runContext("pro");
  const transport = fakeTransport("pro", proConversationSequence());
  transport.listTargets = async () => {
    transport.calls.push({ channel: "target-list" });
    return [
      {
        id: TARGET_ID,
        type: "page",
        url:
          actionRecords(transport, "send").length === 0
            ? TARGET_URL
            : "https://chatgpt.com/c/unrelated-conversation",
      },
    ];
  };
  const harness = fakeDependencies(context, transport);
  await assert.rejects(
    runOracleSubagentAdapter(
      adapterConfiguration(context.request.run_id),
      harness.dependencies,
    ),
    (error) => {
      assert(error instanceof OracleConversationError);
      assert.equal(error.code, "target_url_drift");
      return true;
    },
  );
  assert.equal(actionRecords(transport, "send").length, 1);
  assert.deepEqual(
    harness.lifecycle.map((event) => event.stage),
    ["model_tool_verified"],
  );
  assert.deepEqual(harness.writes, []);
});

test("fresh-root submission still requires a causal conversation URL and one new user", async (t) => {
  await t.test("an unchanged root URL never becomes submitted", async () => {
    const context = runContext("pro", ROOT_TARGET_URL);
    const transport = fakeTransport(
      "pro",
      [
        conversationObservation({
          turns: [],
          overrides: { target_url: ROOT_TARGET_URL },
        }),
        conversationObservation({
          turns: [freshSubmittedTurn],
          overrides: { target_url: ROOT_TARGET_URL },
        }),
      ],
      {},
      {
        pre_send_url: ROOT_TARGET_URL,
        post_send_url: ROOT_TARGET_URL,
      },
    );
    const harness = fakeDependencies(context, transport);
    await assert.rejects(
      runOracleSubagentAdapter(
        adapterConfiguration(context.request.run_id, {
          target_url: ROOT_TARGET_URL,
        }),
        harness.dependencies,
      ),
      (error) => error?.code === "evidence_timeout",
    );
    assert.equal(actionRecords(transport, "send").length, 1);
    assert.deepEqual(
      harness.lifecycle.map((event) => event.stage),
      ["model_tool_verified"],
    );
    assert.deepEqual(harness.writes, []);
  });

  await t.test("two new users cannot claim the fresh conversation", async () => {
    const context = runContext("pro", ROOT_TARGET_URL);
    const transport = fakeTransport(
      "pro",
      [
        conversationObservation({
          turns: [],
          overrides: { target_url: ROOT_TARGET_URL },
        }),
        conversationObservation({
          turns: [
            freshSubmittedTurn,
            turn("user-racing-002", "user", 20, "submitted"),
          ],
          overrides: { target_url: FRESH_CONVERSATION_URL },
        }),
      ],
      {},
      {
        pre_send_url: ROOT_TARGET_URL,
        post_send_url: FRESH_CONVERSATION_URL,
      },
    );
    const harness = fakeDependencies(context, transport);
    await assert.rejects(
      runOracleSubagentAdapter(
        adapterConfiguration(context.request.run_id, {
          target_url: ROOT_TARGET_URL,
        }),
        harness.dependencies,
      ),
      (error) => error?.code === "submitted_turn_invalid",
    );
    assert.equal(actionRecords(transport, "send").length, 1);
    assert.deepEqual(
      harness.lifecycle.map((event) => event.stage),
      ["model_tool_verified"],
    );
    assert.deepEqual(harness.writes, []);
  });

  await t.test("a non-conversation route is causal drift", async () => {
    const context = runContext("pro", ROOT_TARGET_URL);
    const transport = fakeTransport(
      "pro",
      [
        conversationObservation({
          turns: [],
          overrides: { target_url: ROOT_TARGET_URL },
        }),
      ],
      {},
      {
        pre_send_url: ROOT_TARGET_URL,
        post_send_url: "https://chatgpt.com/g/unrelated-surface",
      },
    );
    const harness = fakeDependencies(context, transport);
    await assert.rejects(
      runOracleSubagentAdapter(
        adapterConfiguration(context.request.run_id, {
          target_url: ROOT_TARGET_URL,
        }),
        harness.dependencies,
      ),
      (error) => error?.code === "target_url_drift",
    );
    assert.equal(actionRecords(transport, "send").length, 1);
    assert.deepEqual(
      harness.lifecycle.map((event) => event.stage),
      ["model_tool_verified"],
    );
    assert.deepEqual(harness.writes, []);
  });
});

test("two new user turns never become submitted or completed", async () => {
  const context = runContext("pro");
  const conversations = proConversationSequence();
  conversations[1] = conversationObservation({
    turns: [
      baselineTurn,
      submittedTurn,
      turn("user-racing-002", "user", 30, "submitted"),
    ],
  });
  const transport = fakeTransport("pro", conversations);
  const harness = fakeDependencies(context, transport);
  await assert.rejects(
    runOracleSubagentAdapter(
      adapterConfiguration(context.request.run_id),
      harness.dependencies,
    ),
    (error) => {
      assert(error instanceof OracleConversationError);
      assert.equal(error.code, "submitted_turn_invalid");
      return true;
    },
  );
  assert.deepEqual(
    harness.lifecycle.map((event) => event.stage),
    ["model_tool_verified"],
  );
  assert.deepEqual(harness.writes, []);
});

test("wrong-parent review card and empty dossier fail closed", async (t) => {
  await t.test("wrong-parent review", async () => {
    const context = runContext("deep-research");
    const transport = fakeTransport(
      "deep-research",
      deepConversationSequence({
        reviewParent: "different-user-999",
      }),
    );
    const harness = fakeDependencies(context, transport);
    await assert.rejects(
      runOracleSubagentAdapter(
        adapterConfiguration(context.request.run_id),
        harness.dependencies,
      ),
      (error) => error?.code === "evidence_timeout",
    );
    assert.equal(actionRecords(transport, "start-review").length, 0);
    assert.deepEqual(
      harness.lifecycle.map((event) => event.stage),
      ["model_tool_verified", "submitted"],
    );
  });

  await t.test("empty dossier", async () => {
    const context = runContext("deep-research");
    const transport = fakeTransport(
      "deep-research",
      deepConversationSequence({ dossierContent: "" }),
    );
    const harness = fakeDependencies(context, transport);
    await assert.rejects(
      runOracleSubagentAdapter(
        adapterConfiguration(context.request.run_id),
        harness.dependencies,
      ),
      (error) => error?.code === "evidence_timeout",
    );
    assert.deepEqual(
      harness.lifecycle.map((event) => event.stage),
      ["model_tool_verified", "submitted", "started"],
    );
    assert.deepEqual(harness.writes, []);
  });
});

test("completion identity must match the exact started chain", async (t) => {
  await t.test("Pro assistant identity switch", async () => {
    const context = runContext("pro");
    const conversations = proConversationSequence();
    conversations[3] = conversationObservation({
      turns: [
        baselineTurn,
        submittedTurn,
        turn(
          "assistant-switched-999",
          "assistant",
          30,
          "completed",
          "Switched assistant result.",
        ),
      ],
    });
    const transport = fakeTransport("pro", conversations);
    const harness = fakeDependencies(context, transport);
    await assert.rejects(
      runOracleSubagentAdapter(
        adapterConfiguration(context.request.run_id),
        harness.dependencies,
      ),
      (error) => error?.code === "assistant_identity_mismatch",
    );
    assert.deepEqual(
      harness.lifecycle.map((event) => event.stage),
      ["model_tool_verified", "submitted", "started"],
    );
    assert.deepEqual(harness.writes, []);
  });

  await t.test("Deep Research identity switch", async () => {
    const context = runContext("deep-research");
    const conversations = deepConversationSequence();
    conversations[4].dossiers[0].research_id =
      "research-switched-999";
    const transport = fakeTransport("deep-research", conversations);
    const harness = fakeDependencies(context, transport);
    await assert.rejects(
      runOracleSubagentAdapter(
        adapterConfiguration(context.request.run_id),
        harness.dependencies,
      ),
      (error) => error?.code === "research_identity_mismatch",
    );
    assert.deepEqual(
      harness.lifecycle.map((event) => event.stage),
      ["model_tool_verified", "submitted", "started"],
    );
    assert.deepEqual(harness.writes, []);
  });

  await t.test("Deep Research assistant identity switch", async () => {
    const context = runContext("deep-research");
    const conversations = deepConversationSequence();
    conversations[4].dossiers[0].assistant_message_id =
      "assistant-switched-999";
    const transport = fakeTransport("deep-research", conversations);
    const harness = fakeDependencies(context, transport);
    await assert.rejects(
      runOracleSubagentAdapter(
        adapterConfiguration(context.request.run_id),
        harness.dependencies,
      ),
      (error) => error?.code === "assistant_identity_mismatch",
    );
    assert.deepEqual(
      harness.lifecycle.map((event) => event.stage),
      ["model_tool_verified", "submitted", "started"],
    );
    assert.deepEqual(harness.writes, []);
  });
});

test("legacy production mains reject adapter-only lifecycle actions", async (t) => {
  const root = await realpath(
    await mkdtemp(path.join(os.tmpdir(), "oracle-legacy-main-")),
  );
  t.after(async () => {
    await rm(root, { recursive: true, force: true });
  });
  const composerScript = new URL(
    "../assets/scripts/chatgpt-composer.mjs",
    import.meta.url,
  );
  const toggleScript = new URL(
    "../assets/scripts/toggle-deep-research.mjs",
    import.meta.url,
  );
  const awaitScript = new URL(
    "../assets/scripts/await-deep-research.mjs",
    import.meta.url,
  );

  for (const action of ["replace-content", "send"]) {
    await t.test(`composer ${action}`, async () => {
      const controlPath = path.join(root, `composer-${action}.json`);
      await writeFile(
        controlPath,
        JSON.stringify({
          endpoint: "http://127.0.0.1:9222",
          target_id: TARGET_ID,
          target_url: TARGET_URL,
          action,
        }),
        { mode: 0o600 },
      );
      const result = await runNodeCli(
        composerScript,
        ["--control-file", controlPath],
      );
      assert.equal(result.status, 1);
      assert.equal(result.signal, null);
      assert.equal(result.stdout, "");
      assert.equal(
        result.stderr,
        "chatgpt-composer:adapter_required\n",
      );
    });
  }

  await t.test("Deep Research review Start", async () => {
    const result = await runNodeCli(
      toggleScript,
      ["--control-stdin"],
      JSON.stringify({
        endpoint: "http://127.0.0.1:9222",
        target_id: TARGET_ID,
        target_url: TARGET_URL,
        action: "start-review",
        user_message_id: "user-request-001",
      }),
    );
    assert.equal(result.status, 1);
    assert.equal(result.signal, null);
    assert.equal(result.stdout, "");
    assert.equal(
      result.stderr,
      "toggle-deep-research:adapter_required\n",
    );
  });

  await t.test("caller-supplied completion capture", async () => {
    const result = await runNodeCli(
      awaitScript,
      ["--control-stdin"],
      JSON.stringify({
        endpoint: "http://127.0.0.1:9222",
        target_id: TARGET_ID,
        target_url: TARGET_URL,
        mode: "pro",
        submitted: {},
        started: {},
      }),
    );
    assert.equal(result.status, 1);
    assert.equal(result.signal, null);
    assert.equal(result.stdout, "");
    assert.equal(
      result.stderr,
      "await-deep-research:adapter_required\n",
    );
  });
});

test("helpers are composer/conversation scoped and expose no literal-prompt CLI", async () => {
  const paths = [
    new URL(
      "../assets/scripts/oracle-subagent-adapters.mjs",
      import.meta.url,
    ),
    new URL(
      "../assets/scripts/chatgpt-composer.mjs",
      import.meta.url,
    ),
    new URL(
      "../assets/scripts/toggle-deep-research.mjs",
      import.meta.url,
    ),
    new URL(
      "../assets/scripts/await-deep-research.mjs",
      import.meta.url,
    ),
  ];
  const sources = await Promise.all(
    paths.map((pathname) => readFile(pathname, "utf8")),
  );
  for (const source of sources) {
    assert.doesNotMatch(source, /document\.body/);
    assert.doesNotMatch(source, /paste-text/);
    assert.doesNotMatch(source, /URL_MATCH|DEEP_RESEARCH_CHATGPT_URL_MATCH/);
    assert.doesNotMatch(source, /console\.(?:log|error|warn)/);
  }
  assert.match(sources[0], /withProvenOracleSnapshot/);
  assert.match(sources[0], /snapshot\.oracle_entry/);
  assert.doesNotMatch(
    sources[0],
    /--remote-chrome|--pre-submit-hook|--browser-model-strategy/,
  );
  assert.doesNotMatch(composerPageActionDeclaration(), /document\.body/);
  assert.doesNotMatch(
    deepResearchPageActionDeclaration(),
    /document\.body/,
  );
  assert.match(
    conversationPageProbeExpression(TARGET_ID),
    /data-message-author-role/,
  );
  assert.equal(
    normalizeLoopbackCdpEndpoint("http://127.0.0.1:9222"),
    "http://127.0.0.1:9222",
  );
  assert.throws(
    () => normalizeLoopbackCdpEndpoint("http://localhost:9222"),
    (error) => error?.code === "endpoint_invalid",
  );
  const productionTransport = createLoopbackCdpTransport(
    "http://127.0.0.1:9222",
    {
      fetchImpl: async () => ({
        ok: true,
        async json() {
          return [
            {
              id: "B".repeat(32),
              type: "page",
              url: "https://example.com/",
              webSocketDebuggerUrl:
                "ws://127.0.0.1:9222/devtools/page/BBBB",
            },
            {
              id: TARGET_ID,
              type: "page",
              url: TARGET_URL,
              webSocketDebuggerUrl: `ws://127.0.0.1:9222/devtools/page/${TARGET_ID}`,
            },
          ];
        },
      }),
    },
  );
  assert.deepEqual(await productionTransport.listTargets(), [
    {
      id: TARGET_ID,
      type: "page",
      url: TARGET_URL,
      webSocketDebuggerUrl: `ws://127.0.0.1:9222/devtools/page/${TARGET_ID}`,
    },
  ]);
  const noncanonicalTransport = createLoopbackCdpTransport(
    "http://127.0.0.1:9222",
    {
      fetchImpl: async () => ({
        ok: true,
        async json() {
          return [
            {
              id: TARGET_ID,
              type: "page",
              url: TARGET_URL,
              webSocketDebuggerUrl:
                `ws://127.0.0.1:9222/devtools/page/extra/${TARGET_ID}`,
            },
          ];
        },
      }),
    },
  );
  await assert.rejects(
    noncanonicalTransport.listTargets(),
    (error) => error?.code === "target_transport_invalid",
  );
});

test("an empty baseline is truthful only on the exact ChatGPT root", () => {
  const baseline = captureConversationBaseline(
    conversationObservation({
      turns: [],
      overrides: { target_url: ROOT_TARGET_URL },
    }),
  );
  assert.deepEqual(baseline, {
    target_id: TARGET_ID,
    target_url: ROOT_TARGET_URL,
    turns: [],
    baseline_assistant_turn_id: EMPTY_ROOT_BASELINE_TURN_ID,
    baseline_assistant_turn_position:
      EMPTY_ROOT_BASELINE_TURN_POSITION,
  });

  for (const targetUrl of [
    TARGET_URL,
    "https://chatgpt.com/c/another-conversation",
    "https://chatgpt.com/g/project-surface",
  ]) {
    assert.throws(
      () =>
        captureConversationBaseline(
          conversationObservation({
            turns: [],
            overrides: { target_url: targetUrl },
          }),
        ),
      (error) => error?.code === "baseline_missing",
    );
  }
  assert.throws(
    () =>
      captureConversationBaseline(
        conversationObservation({
          turns: [],
          overrides: {
            target_url: "https://chatgpt.com/?not-exact=true",
          },
        }),
      ),
    (error) => error?.code === "baseline_invalid",
  );
});

test("causal proof helpers reject prefix replacement and nonmonotonic dossier completion", () => {
  const baseline = {
    target_id: TARGET_ID,
    target_url: TARGET_URL,
    turns: [
      {
        raw_id: "assistant-baseline-001",
        role: "assistant",
        position: 10,
      },
    ],
    baseline_assistant_turn_id:
      "assistant:assistant-baseline-001:completed",
    baseline_assistant_turn_position: 11,
  };
  const replaced = conversationObservation({
    turns: [
      turn(
        "assistant-replaced-999",
        "assistant",
        10,
        "completed",
        "replacement",
      ),
      submittedTurn,
    ],
  });
  assert.throws(
    () => proveSubmittedUserTurn(baseline, replaced),
    (error) => error?.code === "thread_mismatch",
  );
  const submitted = {
    conversation_url: TARGET_URL,
    raw_user_message_id: "user-request-001",
    user_turn_id: "user:user-request-001:submitted",
    user_turn_position: 20,
  };
  const observation = conversationObservation({
    turns: [
      baselineTurn,
      submittedTurn,
      deepAssistantCompleted,
    ],
    dossiers: [
      {
        dossier_id: "dossier-result-001",
        research_id: "research-active-001",
        parent_user_message_id: "user-request-001",
        assistant_message_id: "assistant-research-001",
        position: 30,
        content: "nonempty",
      },
    ],
  });
  assert.throws(
    () =>
      proveDeepResearchCompleted(observation, submitted, {
        assistant_signal_id: "research:research-active-001:active",
        assistant_signal_position: 31,
        raw_research_id: "research-active-001",
        raw_assistant_message_id: "assistant-research-001",
      }),
    (error) => error?.code === "completion_invalid",
  );
  assert.equal(
    proveCausalConversationUrl(
      "https://chatgpt.com/",
      "https://chatgpt.com/c/new-conversation-001",
    ),
    "https://chatgpt.com/c/new-conversation-001",
  );
  assert.throws(
    () =>
      proveCausalConversationUrl(
        TARGET_URL,
        "https://chatgpt.com/c/unrelated-conversation",
      ),
    (error) => error?.code === "target_url_drift",
  );
  assert.throws(
    () =>
      proveCausalConversationUrl(
        "https://chatgpt.com/",
        "https://chatgpt.com/g/unrelated-surface",
      ),
    (error) => error?.code === "target_url_drift",
  );
});
