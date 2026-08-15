import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_MODEL_ALIAS,
  DEFAULT_PORT,
  DEFAULT_TIMEOUT_SECONDS,
  EXIT,
  MODEL_ALIASES,
  USAGE,
  UsageError,
  checkReady,
  diagnose,
  install,
  installTargetPath,
  parseArgs,
  rememberThread,
  resolveModel,
  resolvePrompt,
} from "../assets/scripts/oracle-ask.mjs";

/* ------------------------------------------------------------------ *
 * Argument parsing — the "one command" surface
 * ------------------------------------------------------------------ */

test("bare positional words are the prompt; no quoting ceremony required", () => {
  const args = parseArgs(["why", "is", "p99", "bimodal?"], {});
  assert.equal(args.prompt, "why is p99 bimodal?");
  assert.equal(args.model, DEFAULT_MODEL_ALIAS);
  assert.equal(args.timeoutSeconds, DEFAULT_TIMEOUT_SECONDS);
  assert.equal(args.port, DEFAULT_PORT);
  assert.equal(args.json, false);
});

test("a single quoted argument is equally valid", () => {
  assert.equal(parseArgs(["why is p99 bimodal?"], {}).prompt, "why is p99 bimodal?");
});

test("env supplies defaults without any flag", () => {
  const args = parseArgs([], {
    ORACLE_ASK_MODEL: "thinking",
    ORACLE_ASK_TIMEOUT_SECONDS: "60",
    ORACLE_CDP_PORT: "9333",
  });
  assert.equal(args.model, "thinking");
  assert.equal(args.timeoutSeconds, 60);
  assert.equal(args.port, 9333);
});

test("value flags consume their value and never leak into the prompt", () => {
  const args = parseArgs(["--model", "instant", "--timeout", "30", "--out", "/tmp/a.md", "hello", "world"], {});
  assert.equal(args.model, "instant");
  assert.equal(args.timeoutSeconds, 30);
  assert.equal(args.out, "/tmp/a.md");
  assert.equal(args.prompt, "hello world");
});

test("`--` ends option parsing so a prompt may start with a dash", () => {
  const args = parseArgs(["--", "--model", "is", "a", "confusing", "question"], {});
  assert.equal(args.prompt, "--model is a confusing question");
  assert.equal(args.model, DEFAULT_MODEL_ALIAS);
});

test("a misspelled flag fails loudly instead of becoming prompt text", () => {
  assert.throws(() => parseArgs(["--modle", "pro", "hi"], {}), UsageError);
});

test("a value flag with no value fails", () => {
  assert.throws(() => parseArgs(["--model"], {}), UsageError);
});

test("non-positive or non-numeric timeout and port are rejected", () => {
  assert.throws(() => parseArgs(["--timeout", "0", "hi"], {}), UsageError);
  assert.throws(() => parseArgs(["--timeout", "soon", "hi"], {}), UsageError);
  assert.throws(() => parseArgs(["--port", "-1", "hi"], {}), UsageError);
});

test("boolean flags are recognised", () => {
  const args = parseArgs(["--json", "--quiet", "--doctor", "--models", "--install", "--help"], {});
  assert.equal(args.json, true);
  assert.equal(args.quiet, true);
  assert.equal(args.doctor, true);
  assert.equal(args.models, true);
  assert.equal(args.install, true);
  assert.equal(args.help, true);
});

/* ------------------------------------------------------------------ *
 * Model resolution
 * ------------------------------------------------------------------ */

test("the default model is Pro without the caller naming a slug", () => {
  assert.equal(resolveModel(undefined), "gpt-5-6-pro");
  assert.equal(resolveModel(""), "gpt-5-6-pro");
  assert.equal(resolveModel("pro"), "gpt-5-6-pro");
  assert.equal(resolveModel("PRO"), "gpt-5-6-pro");
});

test("aliases cover the picker entries an operator would name", () => {
  assert.equal(resolveModel("deep-research"), "research");
  assert.equal(resolveModel("thinking"), "gpt-5-6-thinking");
  assert.equal(resolveModel("instant"), "gpt-5-5-instant");
  assert.equal(MODEL_ALIASES[DEFAULT_MODEL_ALIAS], "gpt-5-6-pro");
});

test("an unknown slug passes through so new models need no code change", () => {
  assert.equal(resolveModel("gpt-5-7-pro"), "gpt-5-7-pro");
});

/* ------------------------------------------------------------------ *
 * Prompt resolution
 * ------------------------------------------------------------------ */

test("prompt comes from argv, a file, or stdin", async () => {
  assert.equal(await resolvePrompt(parseArgs(["hello"], {}), {}), "hello");

  const fromFile = await resolvePrompt(parseArgs(["--prompt-file", "/tmp/q.md"], {}), {
    readFileImpl: async () => "  file question\n",
  });
  assert.equal(fromFile, "file question");

  const fromStdin = await resolvePrompt(parseArgs([], {}), { readStdin: async () => "piped question\n" });
  assert.equal(fromStdin, "piped question");
});

test("two prompt sources is an ambiguity, not a merge", async () => {
  await assert.rejects(
    () => resolvePrompt(parseArgs(["--prompt-file", "/tmp/q.md", "inline"], {}), { readFileImpl: async () => "x" }),
    UsageError,
  );
});

test("an empty or unreadable prompt file fails with a usage error", async () => {
  await assert.rejects(
    () => resolvePrompt(parseArgs(["--prompt-file", "/tmp/q.md"], {}), { readFileImpl: async () => "   \n" }),
    UsageError,
  );
  await assert.rejects(
    () =>
      resolvePrompt(parseArgs(["--prompt-file", "/tmp/nope.md"], {}), {
        readFileImpl: async () => {
          const e = new Error("nope");
          e.code = "ENOENT";
          throw e;
        },
      }),
    UsageError,
  );
});

test("no prompt anywhere is a usage error, never an empty submission", async () => {
  await assert.rejects(() => resolvePrompt(parseArgs([], {}), {}), UsageError);
  await assert.rejects(() => resolvePrompt(parseArgs([], {}), { readStdin: async () => "\n\n" }), UsageError);
});

/* ------------------------------------------------------------------ *
 * Failure diagnosis — degrade with a message, never silently
 * ------------------------------------------------------------------ */

test("every transport failure maps to an exit code and a concrete action", () => {
  const cases = {
    cdp_unreachable: EXIT.notReady,
    cdp_no_chatgpt_target: EXIT.notReady,
    cdp_failed: EXIT.notReady,
    session_unavailable: EXIT.notReady,
    cookies_unavailable: EXIT.notReady,
    auth_expired: EXIT.refused,
    sentinel_rejected: EXIT.refused,
    sentinel_missing: EXIT.refused,
    mint_timeout: EXIT.refused,
    mint_trigger_failed: EXIT.refused,
    harvest_busy: EXIT.refused,
    answer_timeout: EXIT.timeout,
    stream_error: EXIT.failed,
    conversation_post_failed: EXIT.failed,
    models_failed: EXIT.failed,
  };
  for (const [code, exit] of Object.entries(cases)) {
    const d = diagnose(code, { env: {}, launchHint: () => "LAUNCH" });
    assert.equal(d.exit, exit, `${code} should exit ${exit}`);
    assert.ok(d.summary.length > 0, `${code} needs a summary`);
    assert.ok(d.action.trim().length > 0, `${code} needs an action`);
    assert.notEqual(d.exit, EXIT.ok, `${code} must never look like success`);
  }
});

test("an unrecognised code still degrades with an action, not a silent pass", () => {
  const d = diagnose("something_new", { env: {}, launchHint: () => "LAUNCH" });
  assert.equal(d.exit, EXIT.failed);
  assert.match(d.action, /--doctor/);
});

test("an answer timeout directs recovery of the submitted thread, never a resend", () => {
  const d = diagnose("answer_timeout", { env: {} });
  assert.match(d.action, /last-conversation\.json/);
  assert.match(d.action, /Do not resend/);
  assert.doesNotMatch(d.action, /Re-run with a longer/);
});

test("the not-ready action tells the operator how to start the browser", () => {
  const d = diagnose("cdp_unreachable", {
    env: { ORACLE_PROFILE_DIRECTORY: "Profile 1", ORACLE_CHATGPT_PROJECT_URL: "https://example.test/project" },
  });
  assert.match(d.action, /launch-chatgpt-cdp\.sh/);
  assert.match(d.action, /Profile 1/);
  assert.match(d.action, /example\.test\/project/);
});

test("without env hints the launch action names the variables to set", () => {
  const d = diagnose("cdp_unreachable", { env: {} });
  assert.match(d.action, /ORACLE_PROFILE_DIRECTORY/);
  assert.match(d.action, /ORACLE_CHATGPT_PROJECT_URL/);
});

/* ------------------------------------------------------------------ *
 * Readiness
 * ------------------------------------------------------------------ */

function fakeCdp(overrides = {}) {
  const state = { closed: false };
  return {
    state,
    cdp: { url: "https://chatgpt.com/c/abc", close: () => { state.closed = true; }, ...overrides },
  };
}

test("checkReady reports a signed-in Pro session", async () => {
  const { cdp, state } = fakeCdp();
  const status = await checkReady({
    port: 9222,
    connect: async () => cdp,
    harvest: async () => ({ planType: "pro" }),
  });
  assert.deepEqual(status, { ready: true, planType: "pro", target: "https://chatgpt.com/c/abc", port: 9222 });
  assert.equal(state.closed, true, "the CDP socket must be closed");
});

test("checkReady treats the HTTP-200 guest downgrade as not ready", async () => {
  const { cdp } = fakeCdp();
  const status = await checkReady({ connect: async () => cdp, harvest: async () => ({ planType: "guest" }) });
  assert.equal(status.ready, false);
  assert.equal(status.code, "session_unavailable");
  assert.match(status.detail, /guest/);
});

test("checkReady surfaces an unreachable browser as a coded failure", async () => {
  const status = await checkReady({
    connect: async () => {
      const e = new Error("boom");
      e.code = "cdp_unreachable";
      e.detail = "http://127.0.0.1:9222";
      throw e;
    },
  });
  assert.equal(status.ready, false);
  assert.equal(status.code, "cdp_unreachable");
});

test("checkReady closes the socket even when harvesting throws", async () => {
  const { cdp, state } = fakeCdp();
  const status = await checkReady({
    connect: async () => cdp,
    harvest: async () => {
      const e = new Error("no session");
      e.code = "session_unavailable";
      throw e;
    },
  });
  assert.equal(status.ready, false);
  assert.equal(state.closed, true);
});

/* ------------------------------------------------------------------ *
 * Install shim
 * ------------------------------------------------------------------ */

test("install target honours ORACLE_ASK_BIN_DIR and defaults under ~/.local/bin", () => {
  assert.equal(installTargetPath({ ORACLE_ASK_BIN_DIR: "/opt/bin" }), "/opt/bin/oracle-ask");
  assert.equal(installTargetPath({ HOME: "/home/x" }), "/home/x/.local/bin/oracle-ask");
});

test("install writes an executable shim pointing at the real script", async () => {
  const writes = [];
  const result = await install({
    env: { ORACLE_ASK_BIN_DIR: "/opt/bin" },
    scriptPath: "/skills/deep-research-prompt/assets/scripts/oracle-ask.mjs",
    fs: {
      mkdir: async () => {},
      unlink: async () => {},
      symlink: async () => {},
      writeFile: async (path, body, opts) => writes.push({ path, body, opts }),
    },
  });
  assert.equal(result.target, "/opt/bin/oracle-ask");
  assert.equal(writes.length, 1);
  assert.match(writes[0].body, /^#!\/bin\/sh/);
  assert.match(writes[0].body, /oracle-ask\.mjs/);
  assert.match(writes[0].body, /"\$@"/);
  assert.equal(writes[0].opts.mode, 0o755);
});

test("rememberThread persists a resumable conversation without credential material", async () => {
  const calls = [];
  const result = await rememberThread("conversation-123", "gpt-5-6-pro", {
    path: "/private/last-conversation.json",
    mkdirImpl: async (...args) => calls.push(["mkdir", ...args]),
    writeFileImpl: async (...args) => calls.push(["write", ...args]),
  });
  assert.equal(result, true);
  assert.equal(calls[0][0], "mkdir");
  assert.equal(calls[1][0], "write");
  assert.equal(calls[1][1], "/private/last-conversation.json");
  const payload = JSON.parse(calls[1][2]);
  assert.equal(payload.conversation_id, "conversation-123");
  assert.equal(payload.model, "gpt-5-6-pro");
  assert.equal(calls[1][3].mode, 0o600);
  assert.deepEqual(Object.keys(payload).sort(), ["at", "conversation_id", "model"]);
});

test("the Pro handoff persists its conversation id before the polling deadline", async () => {
  const { readFile } = await import("node:fs/promises");
  const src = await readFile(new URL("../assets/scripts/oracle-http-client.mjs", import.meta.url), "utf8");
  const notify = src.indexOf("await onConversation({");
  const deadline = src.indexOf("const deadline = started + timeoutMs;");
  assert.ok(notify > 0, "askOracle must publish the submitted conversation id");
  assert.ok(deadline > notify, "conversation recovery state must exist before polling can time out");
});

/* ------------------------------------------------------------------ *
 * Surface contract
 * ------------------------------------------------------------------ */

test("usage leads with the bare one-command form", () => {
  const firstExample = USAGE.split("\n").find((l) => l.trim().startsWith("oracle-ask \""));
  assert.ok(firstExample, "usage must show a bare prompt invocation");
  assert.equal(/--/.test(firstExample), false, "the headline example must carry no flags");
});

test("usage names the fallback lane for what this command cannot do", () => {
  assert.match(USAGE, /deep-research-tool-toggle\.md/);
  assert.match(USAGE, /Attachments/);
});

test("the entrypoint never writes a credential value to stdout, a file, or a log", async () => {
  const { readFile } = await import("node:fs/promises");
  const src = await readFile(new URL("../assets/scripts/oracle-ask.mjs", import.meta.url), "utf8");
  const code = src
    .split("\n")
    .filter((line) => !/^\s*(\*|\/\/|\/\*)/.test(line))
    .join("\n");
  for (const banned of ["accessToken", "cookieHeader", "tokenPrefix", "sessionToken", "cookie:"]) {
    assert.equal(code.includes(banned), false, `entrypoint must not handle ${banned}`);
  }
});

test("the entrypoint carries no DOM choreography", async () => {
  const { readFile } = await import("node:fs/promises");
  const src = await readFile(new URL("../assets/scripts/oracle-ask.mjs", import.meta.url), "utf8");
  for (const banned of ["querySelector", "data-testid", "chatgpt-composer", "verify-ready", "select-pro"]) {
    assert.equal(src.includes(banned), false, `entrypoint must not depend on ${banned}`);
  }
});
