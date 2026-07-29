import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { EventEmitter } from "node:events";
import {
  chmod,
  mkdtemp,
  readFile,
  readdir,
  realpath,
  rename,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  CLI_RESULT_SCHEMA,
  OracleSubagentCliError,
  executeCli,
  normalizeChatGptTargetUrl,
  parseCliArguments,
  prepareOracleRun,
  proveStableTarget,
  runWorker,
  startDetachedWorker,
  WORKER_CONTROL_SCHEMA,
} from "../assets/scripts/oracle-subagent.mjs";
import {
  readRunRequest,
  runArtifactLayout,
  writeRunResult,
} from "../assets/scripts/oracle-subagent-artifacts.mjs";
import {
  readReceiptFile,
  transitionReceiptFile,
} from "../assets/scripts/oracle-subagent-state.mjs";
import {
  AUTH_OBSERVATION_SCHEMA,
  AUTH_POLICY_SCHEMA,
} from "../assets/scripts/oracle-subagent-auth.mjs";

const THIS_FILE = fileURLToPath(import.meta.url);
const CLI = fileURLToPath(
  new URL("../assets/scripts/oracle-subagent.mjs", import.meta.url),
);
const BASE_TIME = Date.parse("2026-07-28T20:00:00.000Z");
const TARGET_ID = "0123456789abcdef0123456789abcdef";
const PROJECT_TARGET_URL =
  "https://chatgpt.com/g/g-p-local-proof/project";
const PRIVATE_PROMPT =
  "Private analysis with cookie=session-private and an internal URL.";

function at(offset) {
  return new Date(BASE_TIME + offset * 1_000).toISOString();
}

async function workspace(t) {
  const parent = await realpath(
    await mkdtemp(path.join(os.tmpdir(), "oracle-cli-test-")),
  );
  await chmod(parent, 0o700);
  t.after(() => rm(parent, { recursive: true, force: true }));
  return { parent, root: path.join(parent, "runs") };
}

function transition(to, revision, observedAt, runId, evidence) {
  return {
    to,
    expectedRevision: revision,
    eventId: `event-${to}-${revision}-${runId}`,
    observedAt,
    evidence: { run_id: runId, ...evidence },
  };
}

async function advanceRun(
  artifactRoot,
  runId,
  requestFingerprint,
  targetState,
) {
  const layout = runArtifactLayout(artifactRoot, runId);
  let receipt = await transitionReceiptFile(
    layout.receipt,
    transition("auth_ready", 0, at(1), runId, {
      source: "browser",
      profile_fingerprint: "b".repeat(64),
      challenge_observed: false,
    }),
  );
  if (targetState === "auth_ready") return receipt;
  receipt = await transitionReceiptFile(
    layout.receipt,
    transition("target_bound", 1, at(2), runId, {
      source: "browser",
      target_id: TARGET_ID,
      target_url: "https://chatgpt.com/",
      browser_pid: 4242,
    }),
  );
  if (targetState === "target_bound") return receipt;
  receipt = await transitionReceiptFile(
    layout.receipt,
    transition("model_tool_verified", 2, at(3), runId, {
      source: "browser",
      target_id: TARGET_ID,
      model_requested: "gpt-5.4-pro",
      model_observed: "gpt-5.4-pro",
      model_proven: true,
      tool_requested: "none",
      tool_observed: "none",
      tool_proven: true,
    }),
  );
  if (targetState === "model_tool_verified") return receipt;
  const conversationUrl = `https://chatgpt.com/c/${runId}`;
  const userTurnId = `user-${runId}`;
  receipt = await transitionReceiptFile(
    layout.receipt,
    transition("submitted", 3, at(4), runId, {
      source: "browser",
      target_id: TARGET_ID,
      conversation_url: conversationUrl,
      baseline_assistant_turn_id: `baseline-${runId}`,
      baseline_assistant_turn_position: 10,
      user_turn_id: userTurnId,
      user_turn_position: 11,
      request_fingerprint: requestFingerprint,
      deadline_at: at(100),
    }),
  );
  if (targetState === "submitted") return receipt;
  receipt = await transitionReceiptFile(
    layout.receipt,
    transition("started", 4, at(5), runId, {
      source: "browser",
      target_id: TARGET_ID,
      conversation_url: conversationUrl,
      user_turn_id: userTurnId,
      assistant_signal_id: `progress-${runId}`,
      assistant_signal_position: 12,
    }),
  );
  if (targetState === "started") return receipt;
  const result = await writeRunResult(
    layout,
    "# Verified CLI result\n",
  );
  return transitionReceiptFile(
    layout.receipt,
    transition("completed", 5, at(6), runId, {
      source: "browser",
      target_id: TARGET_ID,
      conversation_url: conversationUrl,
      user_turn_id: userTurnId,
      final_assistant_turn_id: `final-${runId}`,
      final_assistant_turn_position: 13,
      result,
    }),
  );
}

function assertCliError(error, code) {
  assert.ok(error instanceof OracleSubagentCliError);
  assert.equal(error.code, code);
  assert.equal(error.message, "oracle-subagent cli: rejected");
  return true;
}

function runOptions(root, overrides = {}) {
  return parseCliArguments([
    "run",
    "--artifact-root",
    root,
    "--slug",
    "cli-proof",
    "--wait",
    "none",
    ...Object.entries(overrides).flatMap(([flag, value]) => [
      `--${flag}`,
      String(value),
    ]),
  ]);
}

function workerControl(root, runId, requestFingerprint, overrides = {}) {
  return {
    schema: WORKER_CONTROL_SCHEMA,
    artifact_root: root,
    run_id: runId,
    request_fingerprint: requestFingerprint,
    owner_id: "cli:worker-owner-0001",
    queue_config: {
      target_ids: [TARGET_ID],
      max_active: 1,
      max_depth: 8,
      lease_duration_ms: 86_400_000,
    },
    oracle_binary: "/opt/homebrew/bin/oracle",
    manifest_path: "/private/oracle-manifest.json",
    cdp_endpoint: "http://127.0.0.1:9222",
    target_id: TARGET_ID,
    target_url: "https://chatgpt.com/",
    model: "gpt-5.4-pro",
    deadline_at: at(100),
    ...overrides,
  };
}

function spawnJson(arguments_) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(process.execPath, [CLI, ...arguments_], {
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.once("error", rejectPromise);
    child.once("exit", (code) =>
      resolvePromise({ code, stdout, stderr }),
    );
  });
}

test("parser exposes one strict run, status, wait, and reattach interface", () => {
  const run = parseCliArguments([
    "run",
    "--slug",
    "one-command",
    "--prompt-file",
    "/tmp/prompt.md",
    "--file",
    "/tmp/a.pdf",
    "--file",
    "/tmp/b.csv",
    "--mode",
    "deep-research",
    "--wait",
    "completed",
    "--timeout-seconds",
    "90",
    "--result",
    "/tmp/result.md",
    "--json",
  ]);
  assert.equal(run.command, "run");
  assert.equal(run.slug, "one-command");
  assert.deepEqual(run.files, ["/tmp/a.pdf", "/tmp/b.csv"]);
  assert.equal(run.mode, "deep-research");
  assert.equal(run.wait, "completed");
  assert.equal(run.timeout_seconds, 90);
  assert.equal(run.json, true);

  assert.deepEqual(
    parseCliArguments([
      "run",
      "--reattach",
      "run-reattach-0001",
      "--wait",
      "started",
    ]).reattach,
    "run-reattach-0001",
  );
  assert.equal(
    parseCliArguments([
      "status",
      "--run-id",
      "run-status-0001",
    ]).command,
    "status",
  );
  assert.equal(
    parseCliArguments([
      "wait",
      "--run-id",
      "run-wait-0001",
      "--for",
      "started",
    ]).for,
    "started",
  );

  for (const arguments_ of [
    ["run", "--slug", "x", "--prompt", PRIVATE_PROMPT],
    ["run", "--slug", "x", "--result", "/tmp/result.md"],
    ["run", "--reattach", "run-reattach-0001", "--slug", "x"],
    ["status"],
    ["wait", "--run-id", "bad"],
    ["run", "--slug", "x", "--timeout-seconds", "0"],
  ]) {
    assert.throws(
      () => parseCliArguments(arguments_),
      (error) => assertCliError(error, "arguments_invalid"),
    );
  }
});

test("configured target accepts only canonical private ChatGPT paths", () => {
  assert.equal(
    normalizeChatGptTargetUrl("https://chatgpt.com/"),
    "https://chatgpt.com/",
  );
  assert.equal(
    normalizeChatGptTargetUrl(PROJECT_TARGET_URL),
    PROJECT_TARGET_URL,
  );
  for (const value of [
    "http://chatgpt.com/",
    "https://chatgpt.com:443/",
    "https://user@chatgpt.com/",
    "https://chatgpt.com/project?leak=1",
    "https://chatgpt.com/project#fragment",
    "https://chatgpt.com/?",
    "https://chatgpt.com/#",
    "https://chatgpt.com/?#",
    `${PROJECT_TARGET_URL}?`,
    `${PROJECT_TARGET_URL}#`,
    "https://chatgpt.com/project/../other",
    "https://chatgpt.com/c/existing-conversation",
    "https://chatgpt.com/backend-api/me",
    "https://chatgpt.com/g/not-a-project/project",
    "https://chatgpt.com/g/g-p-local-proof/project/",
    "https://chatgpt.com//g/g-p-local-proof/project",
    "https://chatgpt.com/g%2Fg-p-local-proof%2Fproject",
    "https://evil.example/project",
  ]) {
    assert.throws(
      () => normalizeChatGptTargetUrl(value),
      (error) => assertCliError(error, "target_url_invalid"),
    );
  }
});

test("stable Project navigation waits for the exact loaded composer before auth proof", async () => {
  const calls = [];
  const closedTargets = [];
  let nowMs = BASE_TIME;
  let targetUrl = "https://chatgpt.com/c/old-conversation";
  let readinessChecks = 0;
  const profileFingerprint = createHash("sha256")
    .update("/private/profile\0Profile 1")
    .digest("hex");
  const accountFingerprint = "a".repeat(64);
  const observation = {
    schema: AUTH_OBSERVATION_SCHEMA,
    observed_at: new Date(BASE_TIME).toISOString(),
    profile_fingerprint: "",
    account_fingerprint: accountFingerprint,
    session_state: "authenticated",
    challenge: { present: false, observed_at: null },
    project_access: "granted",
    pro_plan: true,
    pro_model_available: true,
    deep_research_available: true,
    composer_available: true,
  };
  const browser = {
    target_id: "fedcba9876543210fedcba9876543210",
    target_url: PROJECT_TARGET_URL,
    port: 9222,
    profile_root: "/private/profile",
    profile_directory: "Profile 1",
  };
  const pool = {
    target_id: TARGET_ID,
    target_url: PROJECT_TARGET_URL,
    port: 9222,
    profile_root: "/private/profile",
    profile_directory: "Profile 1",
  };
  const stable = await proveStableTarget(
    browser,
    pool,
    PROJECT_TARGET_URL,
    {
      nowMs: () => nowMs,
      sleep: async (milliseconds) => {
        nowMs += milliseconds;
      },
      createTransport: () => ({
        listTargets: async () => [
          { id: TARGET_ID, url: targetUrl },
        ],
        evaluate: async (_targetId, expression) => {
          calls.push(expression);
          if (expression.startsWith("location.replace(")) {
            targetUrl = PROJECT_TARGET_URL;
            return true;
          }
          if (expression.includes("document.readyState") &&
              !expression.startsWith("(async()=>")) {
            readinessChecks += 1;
            return readinessChecks >= 2;
          }
          return {
            exact_target: true,
            observation: structuredClone(observation),
          };
        },
      }),
      readPolicy: async () => ({
        schema: AUTH_POLICY_SCHEMA,
        profile_fingerprint: profileFingerprint,
        account_fingerprint: accountFingerprint,
        enrolled_at: new Date(BASE_TIME - 1_000).toISOString(),
      }),
      closeTarget: async (endpoint, targetId) => {
        closedTargets.push([endpoint, targetId]);
      },
    },
  );
  assert.equal(stable.endpoint, "http://127.0.0.1:9222");
  assert.equal(stable.pool.target_url, PROJECT_TARGET_URL);
  assert.equal(readinessChecks, 2);
  assert.deepEqual(closedTargets, [
    [
      "http://127.0.0.1:9222",
      "fedcba9876543210fedcba9876543210",
    ],
  ]);
  assert.match(calls[0], /location\.replace/);
  assert.match(calls.at(-1), new RegExp(PROJECT_TARGET_URL));
  assert.match(calls.at(-1), /exact_target/);

  await assert.rejects(
    proveStableTarget(
      { ...browser, target_id: TARGET_ID },
      pool,
      PROJECT_TARGET_URL,
      {
        nowMs: () => BASE_TIME,
        sleep: async () => {},
        createTransport: () => ({
          listTargets: async () => [
            { id: TARGET_ID, url: PROJECT_TARGET_URL },
          ],
          evaluate: async (_targetId, expression) =>
            expression.startsWith("(async()=>")
              ? {
                  exact_target: false,
                  observation: structuredClone(observation),
                }
              : true,
        }),
        readPolicy: async () => {
          throw new Error("drifted auth proof must stop before policy");
        },
      },
    ),
    (error) =>
      assertCliError(error, "browser_pool_navigation_failed"),
  );
});

test("run accepts a private prompt file and attachments without public prompt leakage", async (t) => {
  const { parent, root } = await workspace(t);
  const promptPath = path.join(parent, "prompt.md");
  const attachmentPath = path.join(parent, "evidence.pdf");
  await writeFile(promptPath, PRIVATE_PROMPT, { mode: 0o600 });
  await writeFile(attachmentPath, "%PDF-private-fixture\n", {
    mode: 0o600,
  });
  let prepared;
  const result = await executeCli(
    parseCliArguments([
      "run",
      "--artifact-root",
      root,
      "--slug",
      "file-input",
      "--prompt-file",
      promptPath,
      "--file",
      attachmentPath,
      "--mode",
      "deep-research",
      "--wait",
      "none",
      "--json",
    ]),
    {
      nowMs: () => BASE_TIME,
      prepareRun: async (context) => {
        prepared = context;
        return {
          run_id: context.candidate_run_id,
          start_worker: false,
          control: null,
        };
      },
    },
  );
  assert.equal(result.schema, CLI_RESULT_SCHEMA);
  assert.equal(result.command, "run");
  assert.equal(result.state, "created");
  assert.equal(result.wait_policy, "none");
  assert.equal(result.worker_pid, null);
  assert.doesNotMatch(JSON.stringify(result), /cookie|internal URL/i);
  assert.equal(prepared.artifact_root, root);
  assert.match(prepared.request_fingerprint, /^[0-9a-f]{64}$/);

  const request = await readRunRequest(
    runArtifactLayout(root, result.run_id),
  );
  assert.equal(request.prompt, PRIVATE_PROMPT);
  assert.equal(request.mode, "deep-research");
  assert.equal(request.attachments.length, 1);
  assert.equal(
    path.dirname(request.attachments[0].path),
    path.join(root, result.run_id, "inputs"),
  );
  assert.equal(
    await readFile(request.attachments[0].path, "utf8"),
    "%PDF-private-fixture\n",
  );
  assert.equal(
    (await stat(request.attachments[0].path)).mode & 0o777,
    0o400,
  );
  assert.equal(
    (await stat(runArtifactLayout(root, result.run_id).request)).mode &
      0o777,
    0o400,
  );
  assert.equal(request.attachments[0].media_type, "application/pdf");
});

test("stdin run waits for started while the canonical run is established before detach", async (t) => {
  const { root } = await workspace(t);
  let started = 0;
  const result = await executeCli(
    parseCliArguments([
      "run",
      "--artifact-root",
      root,
      "--slug",
      "stdin-input",
      "--wait",
      "started",
      "--timeout-seconds",
      "10",
    ]),
    {
      nowMs: () => BASE_TIME,
      readStdin: async () => Buffer.from(PRIVATE_PROMPT),
      prepareRun: async (context) => {
        await advanceRun(
          context.artifact_root,
          context.candidate_run_id,
          context.request_fingerprint,
          "started",
        );
        return {
          run_id: context.candidate_run_id,
          start_worker: true,
          control: {
            schema: WORKER_CONTROL_SCHEMA,
            artifact_root: context.artifact_root,
            run_id: context.candidate_run_id,
            request_fingerprint: context.request_fingerprint,
            owner_id: context.owner_id,
            queue_config: {
              target_ids: [TARGET_ID],
              max_active: 1,
              max_depth: 8,
              lease_duration_ms: 10_000,
            },
            oracle_binary: "/opt/homebrew/bin/oracle",
            manifest_path: "/tmp/oracle-manifest.json",
            cdp_endpoint: "http://127.0.0.1:9222",
            target_id: TARGET_ID,
            target_url: "https://chatgpt.com/",
            model: "gpt-5.4-pro",
            deadline_at: at(100),
          },
        };
      },
      startWorker: async (controlPath) => {
        started += 1;
        assert.match(
          path.basename(controlPath),
          /^worker-control-[0-9a-f]{24}\.json$/,
        );
        assert.doesNotMatch(
          await readFile(controlPath, "utf8"),
          /cookie|internal URL/i,
        );
        return 9090;
      },
    },
  );
  assert.equal(result.run_id.startsWith("run-"), true);
  assert.equal(result.state, "started");
  assert.equal(result.wait_policy, "started");
  assert.equal(result.worker_pid, 9090);
  assert.equal(started, 1);
});

test("completed wait copies only the verified atomic result", async (t) => {
  const { parent, root } = await workspace(t);
  const destination = path.join(parent, "result.md");
  const result = await executeCli(
    parseCliArguments([
      "run",
      "--artifact-root",
      root,
      "--slug",
      "completed-copy",
      "--wait",
      "completed",
      "--timeout-seconds",
      "10",
      "--result",
      destination,
    ]),
    {
      nowMs: () => BASE_TIME,
      readStdin: async () => Buffer.from(PRIVATE_PROMPT),
      prepareRun: async (context) => {
        await advanceRun(
          context.artifact_root,
          context.candidate_run_id,
          context.request_fingerprint,
          "completed",
        );
        return {
          run_id: context.candidate_run_id,
          start_worker: false,
          control: null,
        };
      },
    },
  );
  assert.equal(result.state, "completed");
  assert.equal(result.result_written, destination);
  assert.equal(
    await readFile(destination, "utf8"),
    "# Verified CLI result\n",
  );
  assert.equal((await statMode(destination)) & 0o777, 0o600);
});

async function statMode(pathname) {
  return (await stat(pathname)).mode;
}

test("status is quiet read-only JSON and reattach never starts a second worker", async (t) => {
  const { root } = await workspace(t);
  const created = await executeCli(
    runOptions(root),
    {
      nowMs: () => BASE_TIME,
      readStdin: async () => Buffer.from(PRIVATE_PROMPT),
      prepareRun: async (context) => ({
        run_id: context.candidate_run_id,
        start_worker: false,
        control: null,
      }),
    },
  );
  const before = await readReceiptFile(
    runArtifactLayout(root, created.run_id).receipt,
  );
  const processResult = await spawnJson([
    "status",
    "--artifact-root",
    root,
    "--run-id",
    created.run_id,
    "--json",
  ]);
  assert.equal(processResult.code, 0, processResult.stderr);
  assert.equal(processResult.stderr, "");
  assert.equal(processResult.stdout.trim().split("\n").length, 1);
  const status = JSON.parse(processResult.stdout);
  assert.equal(status.schema, CLI_RESULT_SCHEMA);
  assert.equal(status.state, "created");
  assert.doesNotMatch(processResult.stdout, /cookie|internal URL/i);
  const after = await readReceiptFile(
    runArtifactLayout(root, created.run_id).receipt,
  );
  assert.deepEqual(after, before);

  let workers = 0;
  const reattached = await executeCli(
    parseCliArguments([
      "run",
      "--artifact-root",
      root,
      "--reattach",
      created.run_id,
      "--wait",
      "none",
    ]),
    {
      prepareRun: async (context) => ({
        run_id: context.candidate_run_id,
        start_worker: false,
        control: null,
        directive: "reattached",
      }),
      startWorker: async () => {
        workers += 1;
      },
    },
  );
  assert.equal(reattached.run_id, created.run_id);
  assert.equal(reattached.state, "created");
  assert.equal(reattached.resume_directive, "reattached");
  assert.equal(workers, 0);
});

test("dedupe resolves the canonical run before any detached worker starts", async (t) => {
  const { root } = await workspace(t);
  const first = await executeCli(
    runOptions(root),
    {
      nowMs: () => BASE_TIME,
      readStdin: async () => Buffer.from(PRIVATE_PROMPT),
      prepareRun: async (context) => ({
        run_id: context.candidate_run_id,
        start_worker: false,
        control: null,
      }),
    },
  );
  let workers = 0;
  const second = await executeCli(
    parseCliArguments([
      "run",
      "--artifact-root",
      root,
      "--slug",
      "cli-proof",
      "--wait",
      "none",
    ]),
    {
      nowMs: () => BASE_TIME + 1_000,
      readStdin: async () => Buffer.from(PRIVATE_PROMPT),
      prepareRun: async () => ({
        run_id: first.run_id,
        start_worker: false,
        control: null,
      }),
      startWorker: async () => {
        workers += 1;
      },
    },
  );
  assert.equal(second.run_id, first.run_id);
  assert.equal(second.state, "created");
  assert.equal(second.worker_pid, null);
  assert.equal(workers, 0);
});

test("wait timeout is bounded and does not mutate lifecycle truth", async (t) => {
  const { root } = await workspace(t);
  const created = await executeCli(
    runOptions(root),
    {
      nowMs: () => BASE_TIME,
      readStdin: async () => Buffer.from(PRIVATE_PROMPT),
      prepareRun: async (context) => ({
        run_id: context.candidate_run_id,
        start_worker: false,
        control: null,
      }),
    },
  );
  let now = BASE_TIME;
  await assert.rejects(
    executeCli(
      parseCliArguments([
        "wait",
        "--artifact-root",
        root,
        "--run-id",
        created.run_id,
        "--for",
        "completed",
        "--timeout-seconds",
        "1",
      ]),
      {
        nowMs: () => now,
        sleep: async () => {
          now += 1_000;
        },
      },
    ),
    (error) => assertCliError(error, "wait_timeout"),
  );
  assert.equal(
    (
      await readReceiptFile(
        runArtifactLayout(root, created.run_id).receipt,
      )
    ).state,
    "created",
  );
});

test("preflight failure leaves a durable generic failed receipt and no worker", async (t) => {
  const { root } = await workspace(t);
  let workers = 0;
  await assert.rejects(
    executeCli(
      runOptions(root),
      {
        nowMs: () => BASE_TIME,
        readStdin: async () => Buffer.from(PRIVATE_PROMPT),
        prepareRun: async () => {
          throw new OracleSubagentCliError(
            "browser_preflight_blocked",
          );
        },
        startWorker: async () => {
          workers += 1;
        },
      },
    ),
    (error) =>
      assertCliError(error, "browser_preflight_blocked"),
  );
  const runIds = (await readdir(root)).filter((entry) =>
    entry.startsWith("run-"),
  );
  assert.equal(runIds.length, 1);
  const receipt = await readReceiptFile(
    runArtifactLayout(root, runIds[0]).receipt,
  );
  assert.equal(receipt.state, "failed");
  assert.deepEqual(receipt.error, {
    code: "browser_preflight_blocked",
    stage: "created",
  });
  assert.equal(workers, 0);
  assert.doesNotMatch(JSON.stringify(receipt), /cookie|internal URL/i);
});

test("wait surfaces terminal failure as truthful unsuccessful run state", async (t) => {
  const { root } = await workspace(t);
  const result = await executeCli(
    parseCliArguments([
      "run",
      "--artifact-root",
      root,
      "--slug",
      "failed-wait",
      "--wait",
      "completed",
      "--timeout-seconds",
      "10",
    ]),
    {
      nowMs: () => BASE_TIME,
      readStdin: async () => Buffer.from(PRIVATE_PROMPT),
      prepareRun: async (context) => {
        const layout = runArtifactLayout(
          context.artifact_root,
          context.candidate_run_id,
        );
        await transitionReceiptFile(
          layout.receipt,
          transition(
            "failed",
            0,
            at(1),
            context.candidate_run_id,
            {
              source: "controller",
              code: "execution_failed",
              stage: "created",
            },
          ),
        );
        return {
          run_id: context.candidate_run_id,
          start_worker: false,
          control: null,
        };
      },
    },
  );
  assert.equal(result.state, "failed");
  assert.equal(result.terminal, true);
  assert.equal(result.ok, false);
  assert.equal(result.result_path, null);
});

test("reattach starts a newly leased queued run and surfaces the resume directive", async (t) => {
  const { root } = await workspace(t);
  const created = await executeCli(
    runOptions(root),
    {
      nowMs: () => BASE_TIME,
      readStdin: async () => Buffer.from(PRIVATE_PROMPT),
      prepareRun: async (context) => ({
        run_id: context.candidate_run_id,
        start_worker: false,
        control: null,
        directive: "wait",
      }),
    },
  );
  let workers = 0;
  const result = await executeCli(
    parseCliArguments([
      "run",
      "--artifact-root",
      root,
      "--reattach",
      created.run_id,
      "--wait",
      "none",
    ]),
    {
      nowMs: () => BASE_TIME + 1_000,
      prepareRun: async (context) => {
        await advanceRun(
          context.artifact_root,
          context.candidate_run_id,
          context.request_fingerprint,
          "target_bound",
        );
        return {
          run_id: context.candidate_run_id,
          start_worker: true,
          directive: "execute",
          control: workerControl(
            context.artifact_root,
            context.candidate_run_id,
            context.request_fingerprint,
          ),
        };
      },
      startWorker: async () => {
        workers += 1;
        return 8181;
      },
    },
  );
  assert.equal(result.run_id, created.run_id);
  assert.equal(result.state, "target_bound");
  assert.equal(result.resume_directive, "execute");
  assert.equal(result.worker_pid, 8181);
  assert.equal(workers, 1);
});

test("reattach surfaces reconcile and monitor directives without a second send", async (t) => {
  const { root } = await workspace(t);
  const created = await executeCli(
    runOptions(root),
    {
      nowMs: () => BASE_TIME,
      readStdin: async () => Buffer.from(PRIVATE_PROMPT),
      prepareRun: async (context) => ({
        run_id: context.candidate_run_id,
        start_worker: false,
        control: null,
      }),
    },
  );
  const receipt = await readReceiptFile(
    runArtifactLayout(root, created.run_id).receipt,
  );
  await advanceRun(
    root,
    created.run_id,
    receipt.request_fingerprint,
    "model_tool_verified",
  );
  let workers = 0;
  for (const directive of ["reconcile_submission", "monitor"]) {
    const result = await executeCli(
      parseCliArguments([
        "run",
        "--artifact-root",
        root,
        "--reattach",
        created.run_id,
        "--wait",
        "none",
      ]),
      {
        nowMs: () => BASE_TIME + 10_000,
        prepareRun: async (context) => ({
          run_id: context.candidate_run_id,
          start_worker: false,
          control: null,
          directive,
        }),
        startWorker: async () => {
          workers += 1;
        },
      },
    );
    assert.equal(result.resume_directive, directive);
    assert.equal(result.worker_pid, null);
  }
  assert.equal(workers, 0);
});

test("detached worker resolves only after spawn confirmation", async () => {
  const child = new EventEmitter();
  child.pid = 4242;
  let unrefCalls = 0;
  child.unref = () => {
    unrefCalls += 1;
  };
  let resolved = false;
  const started = startDetachedWorker("/private/control.json", {
    spawnImpl: () => child,
  }).then((pid) => {
    resolved = true;
    return pid;
  });
  await Promise.resolve();
  assert.equal(resolved, false);
  assert.equal(unrefCalls, 0);
  child.emit("spawn");
  assert.equal(await started, 4242);
  assert.equal(unrefCalls, 1);
});

test("worker start failure durably fails the run and reconciles its queue lease", async (t) => {
  const { root } = await workspace(t);
  let reconciliations = 0;
  let unrefCalls = 0;
  await assert.rejects(
    executeCli(
      runOptions(root),
      {
        nowMs: () => BASE_TIME,
        readStdin: async () => Buffer.from(PRIVATE_PROMPT),
        prepareRun: async (context) => {
          await advanceRun(
            context.artifact_root,
            context.candidate_run_id,
            context.request_fingerprint,
            "target_bound",
          );
          return {
            run_id: context.candidate_run_id,
            start_worker: true,
            directive: "execute",
            control: workerControl(
              context.artifact_root,
              context.candidate_run_id,
              context.request_fingerprint,
            ),
          };
        },
        startWorker: (controlPath) =>
          startDetachedWorker(controlPath, {
            spawnImpl: () => {
              const child = new EventEmitter();
              child.pid = undefined;
              child.unref = () => {
                unrefCalls += 1;
              };
              queueMicrotask(() => {
                const error = new Error("synthetic detach failure");
                error.code = "ENOENT";
                child.emit("error", error);
              });
              return child;
            },
          }),
        resume: async () => {
          reconciliations += 1;
          return { directive: "terminal" };
        },
      },
    ),
    /synthetic detach failure/,
  );
  const runIds = (await readdir(root)).filter((entry) =>
    entry.startsWith("run-"),
  );
  assert.equal(runIds.length, 1);
  const receipt = await readReceiptFile(
    runArtifactLayout(root, runIds[0]).receipt,
  );
  assert.equal(receipt.state, "failed");
  assert.equal(receipt.error.code, "worker_start_failed");
  assert.equal(reconciliations, 1);
  assert.equal(unrefCalls, 0);
});

test("persistent browser pool keeps queue target stable across sequential runs", async (t) => {
  const { parent, root } = await workspace(t);
  const targetIds = [
    TARGET_ID,
    "fedcba9876543210fedcba9876543210",
  ];
  const queueConfigs = [];
  const controls = [];
  let launches = 0;
  let browserNow = BASE_TIME;
  const browserDependencies = {
    nowMs: () => browserNow,
    targetUrl: PROJECT_TARGET_URL,
    launchBrowser: async () => ({
      schema: "oracle-subagent.browser.v1",
      state: "ready",
      production_evidence: true,
      submit_performed: false,
      bind: "127.0.0.1",
      visibility: "hidden-headful",
      visibility_verified: true,
      target_observed: true,
      target_id: targetIds[launches++],
      target_url: PROJECT_TARGET_URL,
      pid: 4242,
      port: 9222,
      profile_root: path.join(parent, "profile"),
      profile_directory: "Profile 1",
    }),
    proveTarget: async (_browser, pool) => ({
      pool,
      endpoint: "http://127.0.0.1:9222",
    }),
    resume: async (_root, request, queueConfig) => {
      queueConfigs.push(structuredClone(queueConfig));
      return {
        run_id: request.candidate_run_id,
        directive: "execute",
        send_authorized: true,
      };
    },
  };
  for (const [index, prompt] of ["first", "second"].entries()) {
    browserNow = BASE_TIME + index * 1_000;
    const result = await executeCli(
      parseCliArguments([
        "run",
        "--artifact-root",
        root,
        "--slug",
        `stable-${index}`,
        "--wait",
        "none",
      ]),
      {
        nowMs: () => BASE_TIME + index * 1_000,
        readStdin: async () => Buffer.from(prompt),
        prepareRun: (context) =>
          prepareOracleRun(context, browserDependencies),
        startWorker: async (controlPath) => {
          controls.push(
            JSON.parse(await readFile(controlPath, "utf8")),
          );
          return 9000 + index;
        },
      },
    );
    assert.equal(result.state, "target_bound");
  }
  assert.equal(launches, 2);
  assert.deepEqual(
    queueConfigs.map((configuration) => configuration.target_ids),
    [[TARGET_ID], [TARGET_ID]],
  );
  assert.deepEqual(
    controls.map((control) => control.target_id),
    [TARGET_ID, TARGET_ID],
  );
  assert.deepEqual(
    controls.map((control) => control.target_url),
    [PROJECT_TARGET_URL, PROJECT_TARGET_URL],
  );
  const pool = JSON.parse(
    await readFile(
      path.join(root, ".oracle-subagent-browser-pool.json"),
      "utf8",
    ),
  );
  assert.equal(pool.target_url, PROJECT_TARGET_URL);
  assert.deepEqual(
    controls.map(
      (control) => control.queue_config.lease_duration_ms,
    ),
    [86_400_000, 86_400_000],
  );
  assert.deepEqual(
    controls.map((control) => control.deadline_at),
    [
      new Date(BASE_TIME + 43_200_000).toISOString(),
      new Date(BASE_TIME + 43_201_000).toISOString(),
    ],
  );
  await assert.rejects(
    executeCli(
      parseCliArguments([
        "run",
        "--artifact-root",
        root,
        "--slug",
        "changed-target",
        "--wait",
        "none",
      ]),
      {
        nowMs: () => BASE_TIME + 2_000,
        readStdin: async () => Buffer.from("third"),
        prepareRun: (context) =>
          prepareOracleRun(context, {
            ...browserDependencies,
            targetUrl: "https://chatgpt.com/",
          }),
        startWorker: async () => {
          throw new Error("worker must not start");
        },
      },
    ),
    (error) => assertCliError(error, "browser_pool_invalid"),
  );
  assert.equal(launches, 2);
});

test("worker renders unlinked admitted bytes after named inputs are replaced", async (t) => {
  const { parent, root } = await workspace(t);
  const attachmentPath = path.join(parent, "evidence.pdf");
  await writeFile(attachmentPath, "%PDF-original\n", { mode: 0o600 });
  const created = await executeCli(
    parseCliArguments([
      "run",
      "--artifact-root",
      root,
      "--slug",
      "bound-inputs",
      "--file",
      attachmentPath,
      "--wait",
      "none",
    ]),
    {
      nowMs: () => BASE_TIME,
      readStdin: async () => Buffer.from(PRIVATE_PROMPT),
      prepareRun: async (context) => ({
        run_id: context.candidate_run_id,
        start_worker: false,
        control: null,
      }),
    },
  );
  const layout = runArtifactLayout(root, created.run_id);
  const request = await readRunRequest(layout);
  await advanceRun(
    root,
    created.run_id,
    request.request_fingerprint,
    "target_bound",
  );
  const renderer = path.join(parent, "renderer.mjs");
  await writeFile(
    renderer,
    [
      'import { readFileSync } from "node:fs";',
      "const files = [];",
      "for (let i = 0; i < process.argv.length; i += 1) {",
      '  if (process.argv[i] === "--file") files.push(process.argv[i + 1]);',
      "}",
      'process.stdout.write(files.map((file) => readFileSync(file, "utf8")).join("\\n---\\n"));',
      "",
    ].join("\n"),
    { mode: 0o600 },
  );
  let rendered = null;
  let renderError = null;
  const exitCode = await runWorker(
    workerControl(root, created.run_id, request.request_fingerprint),
    {
      nowMs: () => BASE_TIME,
      loadManifest: async () => ({ schema: "pin" }),
      runAdapter: async (configuration, adapterDependencies) => {
        const context = await adapterDependencies.loadRun(configuration);
        const forgedRequest = path.join(parent, "forged-request.json");
        const forgedAttachment = path.join(parent, "forged.pdf");
        await writeFile(forgedRequest, '{"forged":true}\n', {
          mode: 0o400,
        });
        await writeFile(forgedAttachment, "%PDF-forged\n", {
          mode: 0o400,
        });
        await rename(forgedRequest, layout.request);
        await rename(
          forgedAttachment,
          request.attachments[0].path,
        );
        try {
          rendered = await adapterDependencies.renderRequest(
            {
              oracle_entry: renderer,
              package_root: parent,
              environment: {},
            },
            { ...context, model: configuration.model },
          );
        } catch (error) {
          renderError = error;
          throw error;
        }
      },
      resume: async () => ({ directive: "terminal" }),
    },
  );
  assert.equal(exitCode, 0, renderError?.stack);
  assert.match(rendered, /Private analysis/);
  assert.match(rendered, /%PDF-original/);
  assert.doesNotMatch(rendered, /forged/);
});

test("worker rejects attachment mutation before admission to its FD snapshot", async (t) => {
  const { parent, root } = await workspace(t);
  const attachmentPath = path.join(parent, "evidence.pdf");
  await writeFile(attachmentPath, "%PDF-original\n", { mode: 0o600 });
  const created = await executeCli(
    parseCliArguments([
      "run",
      "--artifact-root",
      root,
      "--slug",
      "tampered-input",
      "--file",
      attachmentPath,
      "--wait",
      "none",
    ]),
    {
      nowMs: () => BASE_TIME,
      readStdin: async () => Buffer.from(PRIVATE_PROMPT),
      prepareRun: async (context) => ({
        run_id: context.candidate_run_id,
        start_worker: false,
        control: null,
      }),
    },
  );
  const layout = runArtifactLayout(root, created.run_id);
  const request = await readRunRequest(layout);
  await chmod(request.attachments[0].path, 0o600);
  await writeFile(request.attachments[0].path, "%PDF-mutated\n");
  let adapterCalls = 0;
  const exitCode = await runWorker(
    workerControl(root, created.run_id, request.request_fingerprint),
    {
      nowMs: () => BASE_TIME,
      loadManifest: async () => ({ schema: "pin" }),
      runAdapter: async () => {
        adapterCalls += 1;
      },
      resume: async () => ({ directive: "terminal" }),
    },
  );
  assert.equal(exitCode, 1);
  assert.equal(adapterCalls, 0);
  assert.equal((await readReceiptFile(layout.receipt)).state, "failed");
});

test("worker deadline expires before adapter execution and durably fails the run", async (t) => {
  const { root } = await workspace(t);
  const created = await executeCli(
    runOptions(root),
    {
      nowMs: () => BASE_TIME,
      readStdin: async () => Buffer.from(PRIVATE_PROMPT),
      prepareRun: async (context) => ({
        run_id: context.candidate_run_id,
        start_worker: false,
        control: null,
      }),
    },
  );
  const layout = runArtifactLayout(root, created.run_id);
  const request = await readRunRequest(layout);
  let adapterCalls = 0;
  const exitCode = await runWorker(
    workerControl(
      root,
      created.run_id,
      request.request_fingerprint,
      { deadline_at: at(-1) },
    ),
    {
      nowMs: () => BASE_TIME,
      loadManifest: async () => ({ schema: "pin" }),
      runAdapter: async () => {
        adapterCalls += 1;
      },
      resume: async () => ({ directive: "terminal" }),
    },
  );
  assert.equal(exitCode, 1);
  assert.equal(adapterCalls, 0);
  const receipt = await readReceiptFile(layout.receipt);
  assert.equal(receipt.state, "failed");
  assert.equal(receipt.error.code, "worker_deadline_exceeded");
});

test("worker invokes the proven adapter then terminal resume with no prompt-bearing control", async () => {
  const calls = [];
  const control = workerControl(
    "/private/runs",
    "run-worker-0001",
    "a".repeat(64),
  );
  const exitCode = await runWorker(control, {
    skipInputVerification: true,
    nowMs: () => BASE_TIME,
    loadManifest: async () => ({ schema: "pin" }),
    runAdapter: async (configuration) => {
      calls.push(["adapter", configuration]);
      return { state: "completed" };
    },
    resume: async (...arguments_) => {
      calls.push(["resume", arguments_]);
      return { directive: "terminal" };
    },
  });
  assert.equal(exitCode, 0);
  assert.equal(calls[0][0], "adapter");
  assert.equal(calls[1][0], "resume");
  assert.equal(calls[0][1].run_id, control.run_id);
  assert.equal(calls[0][1].target_id, TARGET_ID);
  assert.deepEqual(calls[0][1].expected_manifest, {
    schema: "pin",
  });
  assert.doesNotMatch(
    JSON.stringify(control),
    /cookie|password|prompt|secret|session[_-]?token/i,
  );
});

test("source has no prompt argv, callback, network listener, or logging surface", async () => {
  const source = await readFile(
    fileURLToPath(
      new URL(
        "../assets/scripts/oracle-subagent.mjs",
        import.meta.url,
      ),
    ),
    "utf8",
  );
  assert.doesNotMatch(source, /--prompt(?:\s|["'])/);
  assert.doesNotMatch(source, /console\.(?:log|error|warn)/);
  assert.doesNotMatch(source, /createServer|listen\s*\(/);
  assert.doesNotMatch(source, /cookie(?:s)?\s*[:=]/i);
  assert.doesNotMatch(source, /authorization\s*[:=]/i);
  assert.match(source, /Prompt text is accepted only from a file or stdin/);
  assert.equal(path.basename(THIS_FILE), "oracle-subagent-cli.test.mjs");
});
