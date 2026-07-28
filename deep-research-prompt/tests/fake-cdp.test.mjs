import assert from "node:assert/strict";
import test from "node:test";

import {
  cdpRequest,
  fetchFakeTargets,
  selectExactPageTarget,
  startFakeCdp,
} from "./fake-cdp.mjs";

async function fixture(t, options = {}) {
  const fake = await startFakeCdp(options);
  t.after(async () => {
    await fake.close();
  });
  return fake;
}

test("serves loopback-only CDP version and exact target metadata", async (t) => {
  const fake = await fixture(t);
  const versionResponse = await fetch(`${fake.base_url}/json/version`);
  assert.equal(versionResponse.status, 200);
  const version = await versionResponse.json();
  assert.equal(version.Browser, "FakeChrome/1.0");
  assert.equal(version.webSocketDebuggerUrl, fake.browser_websocket_url);

  const targets = await fetchFakeTargets(fake.base_url);
  assert.equal(targets.length, 1);
  const target = selectExactPageTarget(targets, {
    target_id: "FAKEPAGE00000001",
    target_url: "https://chatgpt.com/",
  });
  assert.equal(target.id, "FAKEPAGE00000001");
  assert.equal(
    target.webSocketDebuggerUrl,
    `ws://127.0.0.1:${fake.port}/devtools/page/FAKEPAGE00000001`,
  );
});

test("zero and two matching targets fail closed", async (t) => {
  const zero = await fixture(t, { targets: [] });
  await assert.rejects(
    async () =>
      selectExactPageTarget(await fetchFakeTargets(zero.base_url), {
        target_url: "https://chatgpt.com/",
      }),
    /target_ambiguous/,
  );

  const two = await fixture(t, {
    targets: [
      {
        id: "FAKEPAGE00000001",
        type: "page",
        url: "https://chatgpt.com/",
      },
      {
        id: "FAKEPAGE00000002",
        type: "page",
        url: "https://chatgpt.com/",
      },
    ],
  });
  await assert.rejects(
    async () =>
      selectExactPageTarget(await fetchFakeTargets(two.base_url), {
        target_url: "https://chatgpt.com/",
      }),
    /target_ambiguous/,
  );
  const exact = selectExactPageTarget(await fetchFakeTargets(two.base_url), {
    target_id: "FAKEPAGE00000002",
  });
  assert.equal(exact.id, "FAKEPAGE00000002");
});

test("browser PID and queued Runtime.evaluate results are deterministic", async (t) => {
  const fake = await fixture(t, {
    pid: 81818,
    runtime_results: {
      FAKEPAGE00000001: [
        { schema: "fixture.v1", state: "active" },
        { schema: "fixture.v1", state: "completed", result_nonempty: true },
      ],
    },
  });
  const processInfo = await cdpRequest(
    fake.browser_websocket_url,
    "SystemInfo.getProcessInfo",
  );
  assert.deepEqual(processInfo.processInfo, [
    { type: "browser", id: 81818, cpuTime: 0 },
  ]);
  const pageWebSocket = fake.targets[0].webSocketDebuggerUrl;
  assert.deepEqual(
    await cdpRequest(pageWebSocket, "Runtime.evaluate", {
      expression: "synthetic-private-request-never-log",
    }),
    {
      result: {
        type: "object",
        value: { schema: "fixture.v1", state: "active" },
      },
    },
  );
  assert.deepEqual(
    await cdpRequest(pageWebSocket, "Runtime.evaluate", {
      expression: "synthetic-private-request-never-log",
    }),
    {
      result: {
        type: "object",
        value: {
          schema: "fixture.v1",
          state: "completed",
          result_nonempty: true,
        },
      },
    },
  );
  const encodedCalls = JSON.stringify(fake.calls);
  assert.doesNotMatch(encodedCalls, /synthetic|private|request|expression/);
  assert.deepEqual(fake.calls, [
    {
      channel: "browser",
      target_id: null,
      method: "SystemInfo.getProcessInfo",
    },
    {
      channel: "page",
      target_id: "FAKEPAGE00000001",
      method: "Runtime.evaluate",
    },
    {
      channel: "page",
      target_id: "FAKEPAGE00000001",
      method: "Runtime.evaluate",
    },
  ]);
});

test("browser death rejects an in-flight CDP request", async (t) => {
  const fake = await fixture(t, {
    close_on_methods: ["Runtime.evaluate"],
  });
  await assert.rejects(
    cdpRequest(
      fake.targets[0].webSocketDebuggerUrl,
      "Runtime.evaluate",
      {},
      { timeout_ms: 500 },
    ),
    /disconnected/,
  );
  assert.deepEqual(fake.calls, [
    {
      channel: "page",
      target_id: "FAKEPAGE00000001",
      method: "Runtime.evaluate",
    },
  ]);
});

test("hung and delayed methods obey deterministic client timeouts", async (t) => {
  const hung = await fixture(t, {
    hang_methods: ["Runtime.evaluate"],
  });
  await assert.rejects(
    cdpRequest(
      hung.targets[0].webSocketDebuggerUrl,
      "Runtime.evaluate",
      {},
      { timeout_ms: 40 },
    ),
    /timeout/,
  );

  const delayed = await fixture(t, {
    delay_ms: { "Runtime.evaluate": 80 },
  });
  await assert.rejects(
    cdpRequest(
      delayed.targets[0].webSocketDebuggerUrl,
      "Runtime.evaluate",
      {},
      { timeout_ms: 40 },
    ),
    /timeout/,
  );
  const eventual = await cdpRequest(
    delayed.targets[0].webSocketDebuggerUrl,
    "Runtime.evaluate",
    {},
    { timeout_ms: 200 },
  );
  assert.equal(eventual.result.value.state, "idle");
});

test("unsupported and malformed requests fail without echoing inputs", async (t) => {
  const fake = await fixture(t);
  await assert.rejects(
    cdpRequest(fake.browser_websocket_url, "Browser.sendSecret", {
      credential: "sk-proj-never-echo",
    }),
    (error) => {
      assert.match(error.message, /method_error/);
      assert.doesNotMatch(error.message, /sendSecret|credential|sk-proj/);
      return true;
    },
  );
  assert.deepEqual(fake.calls, [
    {
      channel: "browser",
      target_id: null,
      method: "unsupported",
    },
  ]);
  assert.doesNotMatch(
    JSON.stringify(fake.calls),
    /sendSecret|credential|sk-proj|secret/i,
  );
});

test("invalid targets fail before listen and delayed timers are cancelled", async () => {
  await assert.rejects(
    startFakeCdp({
      targets: [
        {
          id: "FAKEPAGE00000001",
          type: "page",
          url: "https://example.test/",
        },
      ],
    }),
    /invalid_target/,
  );

  const delayed = await startFakeCdp({
    delay_ms: { "Runtime.evaluate": 5_000 },
  });
  await assert.rejects(
    cdpRequest(
      delayed.targets[0].webSocketDebuggerUrl,
      "Runtime.evaluate",
      {},
      { timeout_ms: 20 },
    ),
    /timeout/,
  );
  const started = performance.now();
  await delayed.close();
  assert.ok(performance.now() - started < 500);
});

test("startup snapshots targets before its first asynchronous boundary", async () => {
  const callerOwned = {
    id: "FAKEPAGE00000001",
    type: "page",
    url: "https://chatgpt.com/",
    title: "Original",
  };
  const started = startFakeCdp({ targets: [callerOwned] });
  callerOwned.url = "https://example.test/";
  callerOwned.id = "mutated-secret-shaped-value";
  const fake = await started;
  try {
    assert.equal(fake.targets[0].id, "FAKEPAGE00000001");
    assert.equal(fake.targets[0].url, "https://chatgpt.com/");
    assert.equal(fake.targets[0].title, "Original");
  } finally {
    await fake.close();
  }
});
