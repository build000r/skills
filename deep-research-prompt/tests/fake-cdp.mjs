import { createHash } from "node:crypto";
import { createServer } from "node:http";

const METHOD_PATTERN = /^[A-Za-z][A-Za-z0-9.]{1,127}$/;
const TARGET_PATTERN = /^[A-Za-z0-9_-]{8,128}$/;
const LOGGABLE_METHODS = new Set([
  "Browser.getWindowForTarget",
  "Browser.setWindowBounds",
  "Runtime.evaluate",
  "SystemInfo.getProcessInfo",
  "Target.activateTarget",
  "Target.createTarget",
  "Target.getTargetInfo",
]);

function fail(code) {
  throw new Error(`fake-cdp: ${code}`);
}

function safeTarget(target, port) {
  if (
    !target ||
    typeof target !== "object" ||
    typeof target.id !== "string" ||
    !TARGET_PATTERN.test(target.id) ||
    target.type !== "page"
  ) {
    fail("invalid_target");
  }
  let parsed;
  try {
    parsed = new URL(target.url);
  } catch {
    fail("invalid_target");
  }
  if (
    parsed.protocol !== "https:" ||
    parsed.hostname !== "chatgpt.com" ||
    parsed.username ||
    parsed.password
  ) {
    fail("invalid_target");
  }
  return {
    id: target.id,
    type: "page",
    url: parsed.href,
    title: typeof target.title === "string" ? target.title.slice(0, 120) : "ChatGPT",
    webSocketDebuggerUrl: `ws://127.0.0.1:${port}/devtools/page/${target.id}`,
  };
}

function encodeTextFrame(text) {
  const payload = Buffer.from(text, "utf8");
  let header;
  if (payload.length < 126) {
    header = Buffer.from([0x81, payload.length]);
  } else if (payload.length <= 0xffff) {
    header = Buffer.alloc(4);
    header[0] = 0x81;
    header[1] = 126;
    header.writeUInt16BE(payload.length, 2);
  } else {
    header = Buffer.alloc(10);
    header[0] = 0x81;
    header[1] = 127;
    header.writeBigUInt64BE(BigInt(payload.length), 2);
  }
  return Buffer.concat([header, payload]);
}

function decodeFrames(buffer) {
  const frames = [];
  let offset = 0;
  while (buffer.length - offset >= 2) {
    const first = buffer[offset];
    const second = buffer[offset + 1];
    const final = (first & 0x80) !== 0;
    const opcode = first & 0x0f;
    const masked = (second & 0x80) !== 0;
    let length = second & 0x7f;
    let headerLength = 2;
    if (length === 126) {
      if (buffer.length - offset < 4) break;
      length = buffer.readUInt16BE(offset + 2);
      headerLength = 4;
    } else if (length === 127) {
      if (buffer.length - offset < 10) break;
      const extended = buffer.readBigUInt64BE(offset + 2);
      if (extended > BigInt(Number.MAX_SAFE_INTEGER)) fail("frame_too_large");
      length = Number(extended);
      headerLength = 10;
    }
    const maskLength = masked ? 4 : 0;
    const total = headerLength + maskLength + length;
    if (buffer.length - offset < total) break;
    if (!final) fail("fragmented_frame");
    const maskOffset = offset + headerLength;
    const payloadOffset = maskOffset + maskLength;
    const payload = Buffer.from(
      buffer.subarray(payloadOffset, payloadOffset + length),
    );
    if (masked) {
      const mask = buffer.subarray(maskOffset, maskOffset + 4);
      for (let index = 0; index < payload.length; index += 1) {
        payload[index] ^= mask[index % 4];
      }
    }
    frames.push({ opcode, payload });
    offset += total;
  }
  return { frames, remaining: buffer.subarray(offset) };
}

function normalizeMethodSet(values) {
  if (!Array.isArray(values)) fail("invalid_scenario");
  for (const value of values) {
    if (typeof value !== "string" || !METHOD_PATTERN.test(value)) {
      fail("invalid_scenario");
    }
  }
  return new Set(values);
}

function responseForMethod({
  method,
  params,
  pid,
  targetId,
  targets,
  runtimeQueues,
  methodResults,
}) {
  if (Object.hasOwn(methodResults, method)) {
    return structuredClone(methodResults[method]);
  }
  if (method === "SystemInfo.getProcessInfo") {
    return {
      processInfo: [{ type: "browser", id: pid, cpuTime: 0 }],
    };
  }
  if (method === "Target.getTargetInfo") {
    const requested =
      typeof params?.targetId === "string" ? params.targetId : targetId;
    const target = targets.find((entry) => entry.id === requested);
    if (!target) return { __error: "target_not_found" };
    return {
      targetInfo: {
        targetId: target.id,
        type: target.type,
        title: target.title,
        url: target.url,
        attached: false,
      },
    };
  }
  if (method === "Runtime.evaluate") {
    const queue = runtimeQueues.get(targetId) || [];
    const value =
      queue.length > 1
        ? queue.shift()
        : queue[0] ?? {
            schema: "fake-cdp.runtime.v1",
            state: "idle",
          };
    return {
      result: {
        type: typeof value,
        value: structuredClone(value),
      },
    };
  }
  return { __error: "method_not_supported" };
}

export async function startFakeCdp({
  pid = 42424,
  targets: rawTargets = [
    {
      id: "FAKEPAGE00000001",
      type: "page",
      url: "https://chatgpt.com/",
      title: "ChatGPT fixture",
    },
  ],
  runtime_results = {},
  method_results = {},
  hang_methods = [],
  close_on_methods = [],
  delay_ms = {},
} = {}) {
  if (!Number.isSafeInteger(pid) || pid <= 1) fail("invalid_pid");
  if (
    !Array.isArray(rawTargets) ||
    !rawTargets.every((target) => target && typeof target === "object") ||
    !method_results ||
    typeof method_results !== "object" ||
    Array.isArray(method_results) ||
    !delay_ms ||
    typeof delay_ms !== "object" ||
    Array.isArray(delay_ms)
  ) {
    fail("invalid_scenario");
  }
  const hangMethods = normalizeMethodSet(hang_methods);
  const closeOnMethods = normalizeMethodSet(close_on_methods);
  for (const [method, milliseconds] of Object.entries(delay_ms)) {
    if (
      !METHOD_PATTERN.test(method) ||
      !Number.isSafeInteger(milliseconds) ||
      milliseconds < 0 ||
      milliseconds > 10_000
    ) {
      fail("invalid_scenario");
    }
  }
  const runtimeQueues = new Map();
  for (const [targetId, results] of Object.entries(runtime_results)) {
    if (!TARGET_PATTERN.test(targetId) || !Array.isArray(results)) {
      fail("invalid_scenario");
    }
    runtimeQueues.set(targetId, structuredClone(results));
  }
  // Validate and detach every target from caller-owned mutable objects before
  // creating a listening socket. `safeTarget` only uses the port to construct
  // fixture metadata.
  const targetSnapshots = rawTargets.map((target) => {
    const normalized = safeTarget(target, 1);
    return {
      id: normalized.id,
      type: normalized.type,
      url: normalized.url,
      title: normalized.title,
    };
  });

  const calls = [];
  const sockets = new Set();
  const timers = new Set();
  let port = null;
  let targets = [];
  const server = createServer((request, response) => {
    const host = request.headers.host || "";
    if (host !== `127.0.0.1:${port}`) {
      response.writeHead(400, { "content-type": "application/json" });
      response.end('{"error":"invalid_host"}\n');
      return;
    }
    if (request.method !== "GET") {
      response.writeHead(405, { "content-type": "application/json" });
      response.end('{"error":"method_not_allowed"}\n');
      return;
    }
    if (request.url === "/json/version") {
      response.writeHead(200, {
        "content-type": "application/json",
        "cache-control": "no-store",
      });
      response.end(
        `${JSON.stringify({
          Browser: "FakeChrome/1.0",
          "Protocol-Version": "1.3",
          webSocketDebuggerUrl: `ws://127.0.0.1:${port}/devtools/browser/fake-browser`,
        })}\n`,
      );
      return;
    }
    if (request.url === "/json" || request.url === "/json/list") {
      response.writeHead(200, {
        "content-type": "application/json",
        "cache-control": "no-store",
      });
      response.end(`${JSON.stringify(targets)}\n`);
      return;
    }
    response.writeHead(404, { "content-type": "application/json" });
    response.end('{"error":"not_found"}\n');
  });

  server.on("upgrade", (request, socket, head) => {
    const key = request.headers["sec-websocket-key"];
    const browserPath = request.url === "/devtools/browser/fake-browser";
    const pageMatch = request.url?.match(
      /^\/devtools\/page\/([A-Za-z0-9_-]{8,128})$/,
    );
    const pageTarget = pageMatch
      ? targets.find((target) => target.id === pageMatch[1])
      : null;
    if (
      request.headers.host !== `127.0.0.1:${port}` ||
      typeof key !== "string" ||
      (!browserPath && !pageTarget)
    ) {
      socket.end("HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n");
      return;
    }
    const accept = createHash("sha1")
      .update(`${key}258EAFA5-E914-47DA-95CA-C5AB0DC85B11`)
      .digest("base64");
    socket.write(
      [
        "HTTP/1.1 101 Switching Protocols",
        "Upgrade: websocket",
        "Connection: Upgrade",
        `Sec-WebSocket-Accept: ${accept}`,
        "\r\n",
      ].join("\r\n"),
    );
    sockets.add(socket);
    socket.once("close", () => sockets.delete(socket));
    let pending = Buffer.from(head);
    const channel = browserPath ? "browser" : "page";
    const targetId = pageTarget?.id ?? null;

    const processPending = () => {
      let decoded;
      try {
        decoded = decodeFrames(pending);
      } catch {
        socket.destroy();
        return;
      }
      pending = Buffer.from(decoded.remaining);
      for (const frame of decoded.frames) {
        if (frame.opcode === 0x8) {
          socket.end();
          continue;
        }
        if (frame.opcode === 0x9) {
          socket.write(Buffer.from([0x8a, 0x00]));
          continue;
        }
        if (frame.opcode !== 0x1) {
          socket.destroy();
          continue;
        }
        let message;
        try {
          message = JSON.parse(frame.payload.toString("utf8"));
        } catch {
          socket.destroy();
          continue;
        }
        if (
          !Number.isSafeInteger(message.id) ||
          message.id < 1 ||
          typeof message.method !== "string" ||
          !METHOD_PATTERN.test(message.method)
        ) {
          socket.write(
            encodeTextFrame(
              JSON.stringify({
                id: Number.isSafeInteger(message?.id) ? message.id : 0,
                error: { code: -32600, message: "invalid_request" },
              }),
            ),
          );
          continue;
        }
        const method = message.method;
        calls.push(
          Object.freeze({
            channel,
            target_id: targetId,
            method: LOGGABLE_METHODS.has(method) ? method : "unsupported",
          }),
        );
        if (closeOnMethods.has(method)) {
          socket.destroy();
          continue;
        }
        if (hangMethods.has(method)) continue;
        const result = responseForMethod({
          method,
          params: message.params,
          pid,
          targetId,
          targets,
          runtimeQueues,
          methodResults: method_results,
        });
        const reply =
          result?.__error === undefined
            ? { id: message.id, result }
            : {
                id: message.id,
                error: { code: -32601, message: result.__error },
              };
        const sendReply = () => {
          if (!socket.destroyed) {
            socket.write(encodeTextFrame(JSON.stringify(reply)));
          }
        };
        const delay = delay_ms[method] ?? 0;
        if (delay > 0) {
          const timer = setTimeout(() => {
            timers.delete(timer);
            sendReply();
          }, delay);
          timers.add(timer);
        } else {
          sendReply();
        }
      }
    };
    if (pending.length > 0) processPending();
    socket.on("data", (chunk) => {
      pending = Buffer.concat([pending, chunk]);
      processPending();
    });
  });

  await new Promise((resolvePromise, rejectPromise) => {
    server.once("error", rejectPromise);
    server.listen(0, "127.0.0.1", resolvePromise);
  });
  port = server.address().port;
  targets = targetSnapshots.map((target) => safeTarget(target, port));

  let closed = false;
  return {
    pid,
    port,
    base_url: `http://127.0.0.1:${port}`,
    browser_websocket_url: `ws://127.0.0.1:${port}/devtools/browser/fake-browser`,
    get targets() {
      return structuredClone(targets);
    },
    get calls() {
      return calls.map((call) => ({ ...call }));
    },
    setTargets(nextTargets) {
      if (!Array.isArray(nextTargets)) fail("invalid_target");
      targets = nextTargets.map((target) => safeTarget(target, port));
    },
    crash() {
      for (const socket of sockets) socket.destroy();
    },
    async close() {
      if (closed) return;
      closed = true;
      for (const timer of timers) clearTimeout(timer);
      timers.clear();
      for (const socket of sockets) socket.destroy();
      await new Promise((resolvePromise) => server.close(resolvePromise));
    },
  };
}

export async function fetchFakeTargets(baseUrl) {
  let parsed;
  try {
    parsed = new URL(baseUrl);
  } catch {
    fail("invalid_endpoint");
  }
  if (
    parsed.protocol !== "http:" ||
    parsed.hostname !== "127.0.0.1" ||
    !parsed.port ||
    parsed.pathname !== "/" ||
    parsed.search ||
    parsed.hash
  ) {
    fail("invalid_endpoint");
  }
  const response = await fetch(`${parsed.origin}/json`, {
    signal: AbortSignal.timeout(1_000),
    cache: "no-store",
  });
  if (!response.ok) fail("endpoint_unavailable");
  const targets = await response.json();
  if (!Array.isArray(targets)) fail("invalid_target_list");
  return targets;
}

export function selectExactPageTarget(
  targets,
  { target_id = null, target_url = null } = {},
) {
  if (!Array.isArray(targets)) fail("invalid_target_list");
  if (
    target_id !== null &&
    (typeof target_id !== "string" || !TARGET_PATTERN.test(target_id))
  ) {
    fail("invalid_selector");
  }
  let normalizedUrl = null;
  if (target_url !== null) {
    try {
      normalizedUrl = new URL(target_url).href;
    } catch {
      fail("invalid_selector");
    }
  }
  if (target_id === null && normalizedUrl === null) fail("invalid_selector");
  const candidates = targets.filter((target) => {
    if (!target || target.type !== "page") return false;
    let parsed;
    try {
      parsed = new URL(target.url);
    } catch {
      return false;
    }
    if (parsed.protocol !== "https:" || parsed.hostname !== "chatgpt.com") {
      return false;
    }
    if (target_id !== null && target.id !== target_id) return false;
    if (normalizedUrl !== null && parsed.href !== normalizedUrl) return false;
    return true;
  });
  if (candidates.length !== 1) fail("target_ambiguous");
  return structuredClone(candidates[0]);
}

export async function cdpRequest(
  webSocketUrl,
  method,
  params = {},
  { timeout_ms = 250 } = {},
) {
  let parsed;
  try {
    parsed = new URL(webSocketUrl);
  } catch {
    fail("invalid_endpoint");
  }
  if (
    parsed.protocol !== "ws:" ||
    parsed.hostname !== "127.0.0.1" ||
    !parsed.port ||
    typeof method !== "string" ||
    !METHOD_PATTERN.test(method) ||
    !Number.isSafeInteger(timeout_ms) ||
    timeout_ms < 10 ||
    timeout_ms > 5_000
  ) {
    fail("invalid_request");
  }
  const socket = new WebSocket(parsed.href);
  return new Promise((resolvePromise, rejectPromise) => {
    let settled = false;
    const settle = (callback, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try {
        socket.close();
      } catch {}
      callback(value);
    };
    const timer = setTimeout(
      () => settle(rejectPromise, new Error("fake-cdp: timeout")),
      timeout_ms,
    );
    socket.addEventListener(
      "open",
      () => {
        socket.send(JSON.stringify({ id: 1, method, params }));
      },
      { once: true },
    );
    socket.addEventListener("message", (event) => {
      let message;
      try {
        message = JSON.parse(String(event.data));
      } catch {
        settle(rejectPromise, new Error("fake-cdp: invalid_response"));
        return;
      }
      if (message.id !== 1) return;
      if (message.error) {
        settle(rejectPromise, new Error("fake-cdp: method_error"));
        return;
      }
      settle(resolvePromise, message.result);
    });
    socket.addEventListener(
      "error",
      () => settle(rejectPromise, new Error("fake-cdp: disconnected")),
      { once: true },
    );
    socket.addEventListener(
      "close",
      () => settle(rejectPromise, new Error("fake-cdp: disconnected")),
      { once: true },
    );
  });
}
