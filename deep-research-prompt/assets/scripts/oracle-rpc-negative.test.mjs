import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import http from "node:http";
import { mkdtemp, readFile, rm, stat, symlink } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  createOracleRpcHandler,
  FLEET_LIMITS,
  resolveTailscaleCaller,
  validateTailnetBindHost,
  verifyTailnetBindHost,
} from "./oracle-rpc-server.mjs";
import {
  prepareOracleFleetRequest,
  submitOracleFleetRequest,
} from "./oracle-rpc-client.mjs";

const CALLER = Object.freeze({
  node_id: "node-fixture-0001",
  node_name: "caller.tailnet.ts.net",
  user_login: "caller@example.test",
  tags: Object.freeze(["tag:oracle-client"]),
});
const FORBIDDEN_FIELDS = Object.freeze([
  "hooks",
  "environmentVariables",
  "cdpTarget",
  "browserConfig",
  "cookieJar",
  "execPath",
  "path",
  "replay",
]);

function fixtureWhois(tags = CALLER.tags) {
  return Object.freeze({
    Node: Object.freeze({
      StableID: CALLER.node_id,
      Name: `${CALLER.node_name}.`,
      Tags: Object.freeze([...tags]),
    }),
    UserProfile: Object.freeze({ LoginName: CALLER.user_login }),
  });
}

async function listen(server) {
  await new Promise((resolvePromise, rejectPromise) => {
    server.once("error", rejectPromise);
    server.listen(0, "localhost", () => {
      server.off("error", rejectPromise);
      resolvePromise();
    });
  });
  return `http://localhost:${server.address().port}/v1/oracle`;
}

async function close(server) {
  if (!server.listening) return;
  await new Promise((resolvePromise, rejectPromise) => {
    server.close((error) =>
      error ? rejectPromise(error) : resolvePromise(),
    );
  });
}

async function postJson(endpoint, body) {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: Buffer.isBuffer(body) ? body : JSON.stringify(body),
  });
  return Object.freeze({
    status: response.status,
    body: await response.json(),
  });
}

function postDeclaredOversize(port) {
  return new Promise((resolvePromise, rejectPromise) => {
    const request = http.request(
      {
        hostname: "localhost",
        port,
        path: "/v1/oracle",
        method: "POST",
        headers: {
          "content-type": "application/json",
          "content-length": String(FLEET_LIMITS.body_bytes + 1),
          connection: "close",
        },
      },
      (response) => {
        const chunks = [];
        response.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
        response.on("end", () => {
          try {
            resolvePromise(
              Object.freeze({
                status: response.statusCode,
                body: JSON.parse(Buffer.concat(chunks).toString("utf8")),
              }),
            );
          } catch (error) {
            rejectPromise(error);
          }
        });
      },
    );
    request.once("error", rejectPromise);
    request.end();
  });
}

test("PC-FLEET-1 persists eleven pre-browser negative controls", async (t) => {
  let browserContacts = 0;
  let releases = 0;
  let whoisCalls = 0;
  const resolveCaller = (socket) =>
    resolveTailscaleCaller(socket, {
      requiredPeerTags: ["tag:oracle-client"],
      localApiJson: async (pathname) => {
        assert.match(pathname, /^\/localapi\/v0\/whois\?addr=/);
        whoisCalls += 1;
        return fixtureWhois();
      },
    });
  const handler = createOracleRpcHandler({
    resolveCaller,
    authorizeCaller: async ({ caller }) => ({
      allowed: true,
      context: { caller_id: caller.node_id },
      receipt: {
        policy_id: "fixture-policy",
        quota_bucket: "interactive",
        remaining: 3,
      },
    }),
    releaseCaller: async () => {
      releases += 1;
    },
    runOracle: async (request, context) => {
      browserContacts += 1;
      assert.equal(context.caller.node_id, CALLER.node_id);
      assert.equal(request.files[0]?.bytes.toString("utf8"), "proof");
      return {
        run_id: `oracle-run-${browserContacts}-fixture`,
        state: "completed",
        bytes: Buffer.from("# verified result\n", "utf8"),
      };
    },
  });
  const server = http.createServer(handler);
  t.after(() => close(server));
  const endpoint = await listen(server);
  const prepared = await prepareOracleFleetRequest({
    prompt: "Bounded research request",
    files: [
      {
        name: "evidence.txt",
        media_type: "text/plain",
        bytes: Buffer.from("proof", "utf8"),
      },
    ],
    request_id: "request-fixture-00000001",
  });

  let negativeControls = 0;
  for (const [index, field] of FORBIDDEN_FIELDS.entries()) {
    const response = await postJson(endpoint, {
      ...prepared.request,
      request_id: `negative-${String(index).padStart(2, "0")}-fixture-0001`,
      [field]: true,
    });
    assert.equal(response.status, 400);
    assert.equal(response.body.error.code, "forbidden_field");
    negativeControls += 1;
  }
  assert.equal(browserContacts, 0);
  const browserContactsAfterForbiddenControls = browserContacts;

  const oversized = await postDeclaredOversize(server.address().port);
  assert.equal(oversized.status, 413);
  assert.equal(oversized.body.error.code, "body_size_rejected");
  assert.equal(browserContacts, 0);
  negativeControls += 1;

  await assert.rejects(
    resolveTailscaleCaller(
      { remoteAddress: "fixture-address", remotePort: 43211 },
      {
        requiredPeerTags: ["tag:oracle-client"],
        localApiJson: async () => fixtureWhois([]),
      },
    ),
    (error) => error.code === "caller_tag_rejected",
  );
  assert.equal(browserContacts, 0);
  negativeControls += 1;

  const success = await postJson(endpoint, prepared.body);
  assert.equal(success.status, 200);
  assert.equal(success.body.receipt.caller.node_id, CALLER.node_id);
  assert.equal(success.body.receipt.caller.node_name, CALLER.node_name);
  assert.equal(success.body.receipt.caller.user_login, CALLER.user_login);
  assert.deepEqual(success.body.receipt.caller.tags, CALLER.tags);
  assert.equal(success.body.receipt.policy.policy_id, "fixture-policy");
  assert.equal(browserContacts, 1);
  assert.equal(releases, 1);
  assert.ok(whoisCalls > 0);

  const replay = await postJson(endpoint, prepared.body);
  assert.equal(replay.status, 409);
  assert.equal(replay.body.error.code, "replay_rejected");
  assert.equal(browserContacts, 1);
  negativeControls += 1;

  assert.equal(negativeControls, 11);
  t.diagnostic(
    JSON.stringify({
      pc_fleet_1_negative_controls: negativeControls,
      browser_contacts_after_forbidden_controls:
        browserContactsAfterForbiddenControls,
      whois_fixture_observed: whoisCalls > 0,
      receipt_caller: success.body.receipt.caller.node_id,
      replay_status: replay.status,
    }),
  );
});

test("fixture bind proof rejects wildcard and non-self resolution", async () => {
  const wildcard = ["0", "0", "0", "0"].join(".");
  assert.throws(
    () => validateTailnetBindHost(wildcard),
    (error) => error.code === "tailnet_bind_required",
  );
  assert.throws(
    () => validateTailnetBindHost("*"),
    (error) => error.code === "tailnet_bind_required",
  );

  const localApiJson = async () => ({
    Self: { TailscaleIPs: ["tailnet-address-fixture"] },
  });
  assert.equal(
    await verifyTailnetBindHost("skillbox-portfolio-devbox", {
      localApiJson,
      lookup: async () => [{ address: "tailnet-address-fixture" }],
    }),
    "skillbox-portfolio-devbox",
  );
  await assert.rejects(
    verifyTailnetBindHost("skillbox-portfolio-devbox", {
      localApiJson,
      lookup: async () => [{ address: "off-tailnet-address-fixture" }],
    }),
    (error) => error.code === "tailnet_bind_proof_failed",
  );
});

test("client writes the caller-stamped file-backed result with mode 0600", async (t) => {
  let browserContacts = 0;
  const handler = createOracleRpcHandler({
    resolveCaller: async () => CALLER,
    authorizeCaller: async () => ({
      allowed: true,
      context: { caller_id: CALLER.node_id },
      receipt: {
        policy_id: "fixture-policy",
        quota_bucket: "interactive",
        remaining: 2,
      },
    }),
    releaseCaller: async () => {},
    runOracle: async () => {
      browserContacts += 1;
      return {
        run_id: "oracle-run-client-fixture",
        state: "completed",
        bytes: Buffer.from("# verified result\n", "utf8"),
      };
    },
  });
  const server = http.createServer(handler);
  t.after(() => close(server));
  const localEndpoint = await listen(server);
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "oracle-rpc-negative-"),
  );
  t.after(() => rm(directory, { recursive: true, force: true }));
  const resultPath = path.join(directory, "result.md");

  const result = await submitOracleFleetRequest(
    {
      prompt: "Client request",
      files: [
        {
          name: "evidence.txt",
          media_type: "text/plain",
          bytes: Buffer.from("proof", "utf8"),
        },
      ],
    },
    {
      endpoint: "http://skillbox-portfolio-devbox:4117/v1/oracle",
      resultPath,
      fetchImpl: (_endpoint, options) => fetch(localEndpoint, options),
    },
  );

  assert.equal(browserContacts, 1);
  assert.equal(result.receipt.caller.node_id, CALLER.node_id);
  assert.equal(result.result_path, resultPath);
  assert.equal(await readFile(resultPath, "utf8"), "# verified result\n");
  assert.equal((await stat(resultPath)).mode & 0o777, 0o600);
  t.diagnostic(
    JSON.stringify({
      result_file_mode: "0600",
      result_bytes: result.result_bytes,
      receipt_caller: result.receipt.caller.node_id,
    }),
  );
});

test("server construction fails closed without a policy authority", () => {
  assert.throws(
    () =>
      createOracleRpcHandler({
        resolveCaller: async () => CALLER,
        runOracle: async () => ({
          run_id: "never",
          state: "completed",
          bytes: Buffer.from("never"),
        }),
      }),
    (error) => error.code === "server_configuration_invalid",
  );
});

test("symlinked Oracle CLI entrypoints execute instead of silently exiting", async (t) => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "oracle-cli-links-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const scripts = path.dirname(fileURLToPath(import.meta.url));
  const linkedScripts = path.join(directory, "scripts");
  await symlink(scripts, linkedScripts, "dir");
  for (const [name, arguments_] of [
    ["oracle-subagent.mjs", ["--help"]],
    ["oracle-subagent-auth.mjs", ["--help"]],
    ["oracle-rpc-client.mjs", ["--help"]],
    ["oracle-rpc-server.mjs", ["--help"]],
  ]) {
    const result = spawnSync("node", [path.join(linkedScripts, name), ...arguments_], {
      encoding: "utf8",
      timeout: 10_000,
    });
    assert.equal(result.error, undefined, name);
    assert.ok(`${result.stdout}${result.stderr}`.length > 0, name);
  }
});
