#!/usr/bin/env node

import { constants as fsConstants } from "node:fs";
import { open, realpath } from "node:fs/promises";
import { isAbsolute, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const TARGET_ID_PATTERN = /^[A-Fa-f0-9]{16,128}$/;
const PRO_MODEL_PATTERN = /^gpt-[a-z0-9]+(?:[.-][a-z0-9]+)*-pro$/;
const ACTIONS = new Set([
  "inspect",
  "clear",
  "select-pro",
  "replace-content",
  "send",
]);
const ADAPTER_ONLY_ACTIONS = new Set(["replace-content", "send"]);
const MAX_PRIVATE_INPUT_BYTES = 32 * 1024 * 1024;
const CDP_TIMEOUT_MS = 20_000;

export class ChatGptComposerError extends Error {
  constructor(code) {
    super("chatgpt composer: rejected");
    this.name = "ChatGptComposerError";
    this.code = code;
  }
}

function reject(code) {
  throw new ChatGptComposerError(code);
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

function normalizedAbsolutePath(value, code) {
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

export function normalizeLoopbackCdpEndpoint(value) {
  if (typeof value !== "string") reject("endpoint_invalid");
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    reject("endpoint_invalid");
  }
  const port = Number.parseInt(parsed.port, 10);
  if (
    parsed.protocol !== "http:" ||
    parsed.hostname !== "127.0.0.1" ||
    !Number.isSafeInteger(port) ||
    port < 1 ||
    port > 65_535 ||
    parsed.username ||
    parsed.password ||
    (parsed.pathname !== "/" && parsed.pathname !== "") ||
    parsed.search ||
    parsed.hash
  ) {
    reject("endpoint_invalid");
  }
  return `http://127.0.0.1:${port}`;
}

export function normalizeExactChatGptUrl(value) {
  if (typeof value !== "string") reject("target_url_invalid");
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    reject("target_url_invalid");
  }
  if (
    parsed.protocol !== "https:" ||
    parsed.hostname !== "chatgpt.com" ||
    parsed.origin !== "https://chatgpt.com" ||
    parsed.port ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash
  ) {
    reject("target_url_invalid");
  }
  return parsed.href;
}

export function normalizeExactTarget(value) {
  exactObject(
    value,
    ["target_id", "target_url"],
    [],
    "target_invalid",
  );
  if (
    typeof value.target_id !== "string" ||
    !TARGET_ID_PATTERN.test(value.target_id)
  ) {
    reject("target_invalid");
  }
  return Object.freeze({
    target_id: value.target_id,
    target_url: normalizeExactChatGptUrl(value.target_url),
  });
}

function validateWebSocketUrl(value, endpoint, targetId) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    reject("target_transport_invalid");
  }
  const base = new URL(endpoint);
  if (
    parsed.protocol !== "ws:" ||
    parsed.hostname !== "127.0.0.1" ||
    parsed.port !== base.port ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash ||
    parsed.pathname !== `/devtools/page/${targetId}`
  ) {
    reject("target_transport_invalid");
  }
  return parsed.href;
}

function normalizeTargetRecord(rawTarget, endpoint) {
  if (!isPlainObject(rawTarget)) reject("target_transport_invalid");
  if (
    rawTarget.type !== "page" ||
    typeof rawTarget.id !== "string" ||
    !TARGET_ID_PATTERN.test(rawTarget.id)
  ) {
    reject("target_transport_invalid");
  }
  return Object.freeze({
    id: rawTarget.id,
    type: "page",
    url: normalizeExactChatGptUrl(rawTarget.url),
    webSocketDebuggerUrl: validateWebSocketUrl(
      rawTarget.webSocketDebuggerUrl,
      endpoint,
      rawTarget.id,
    ),
  });
}

async function resolveWebSocketConstructor(WebSocketImpl) {
  if (WebSocketImpl) return WebSocketImpl;
  if (globalThis.WebSocket) return globalThis.WebSocket;
  return (await import("ws")).default;
}

async function cdpRequest(
  webSocketUrl,
  method,
  params,
  { WebSocketImpl, timeoutMs = CDP_TIMEOUT_MS } = {},
) {
  const WebSocketConstructor =
    await resolveWebSocketConstructor(WebSocketImpl);
  const socket = new WebSocketConstructor(webSocketUrl);
  const identifier = 1;
  return new Promise((resolvePromise, rejectPromise) => {
    let settled = false;
    const finish = (action, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try {
        socket.close();
      } catch {}
      action(value);
    };
    const timer = setTimeout(
      () => finish(rejectPromise, new ChatGptComposerError("cdp_timeout")),
      timeoutMs,
    );
    const onOpen = () => {
      socket.send(JSON.stringify({ id: identifier, method, params }));
    };
    const onMessage = (raw) => {
      const bytes = raw?.data ?? raw;
      let message;
      try {
        message = JSON.parse(
          typeof bytes === "string" ? bytes : Buffer.from(bytes).toString(),
        );
      } catch {
        finish(
          rejectPromise,
          new ChatGptComposerError("cdp_response_invalid"),
        );
        return;
      }
      if (message.id !== identifier) return;
      if (message.error) {
        finish(rejectPromise, new ChatGptComposerError("cdp_call_failed"));
      } else {
        finish(resolvePromise, message.result);
      }
    };
    const onError = () =>
      finish(rejectPromise, new ChatGptComposerError("cdp_failed"));
    if (typeof socket.addEventListener === "function") {
      socket.addEventListener("open", onOpen, { once: true });
      socket.addEventListener("message", onMessage);
      socket.addEventListener("error", onError, { once: true });
    } else {
      socket.once("open", onOpen);
      socket.on("message", onMessage);
      socket.once("error", onError);
    }
  });
}

export function createLoopbackCdpTransport(
  endpoint,
  {
    fetchImpl = globalThis.fetch,
    WebSocketImpl = null,
    timeoutMs = CDP_TIMEOUT_MS,
  } = {},
) {
  endpoint = normalizeLoopbackCdpEndpoint(endpoint);
  if (typeof fetchImpl !== "function") reject("transport_invalid");
  let targetsById = new Map();

  async function listTargets() {
    let response;
    try {
      response = await fetchImpl(`${endpoint}/json`, {
        method: "GET",
        redirect: "error",
        cache: "no-store",
      });
    } catch {
      reject("target_list_failed");
    }
    if (!response?.ok) reject("target_list_failed");
    let payload;
    try {
      payload = await response.json();
    } catch {
      reject("target_list_invalid");
    }
    if (!Array.isArray(payload)) reject("target_list_invalid");
    const targets = payload
      .filter((target) => {
        if (
          !isPlainObject(target) ||
          target.type !== "page" ||
          typeof target.url !== "string"
        ) {
          return false;
        }
        try {
          normalizeExactChatGptUrl(target.url);
          return true;
        } catch {
          return false;
        }
      })
      .map((target) => normalizeTargetRecord(target, endpoint));
    targetsById = new Map(targets.map((target) => [target.id, target]));
    if (targetsById.size !== targets.length) reject("target_list_invalid");
    return targets;
  }

  async function targetForCall(targetId) {
    if (!targetsById.has(targetId)) await listTargets();
    const target = targetsById.get(targetId);
    if (!target) reject("target_missing");
    return target;
  }

  return Object.freeze({
    endpoint,
    listTargets,
    async evaluate(targetId, expression) {
      if (typeof expression !== "string" || expression.length === 0) {
        reject("expression_invalid");
      }
      const target = await targetForCall(targetId);
      const response = await cdpRequest(
        target.webSocketDebuggerUrl,
        "Runtime.evaluate",
        {
          expression,
          awaitPromise: true,
          returnByValue: true,
        },
        { WebSocketImpl, timeoutMs },
      );
      if (!isPlainObject(response?.result)) reject("cdp_response_invalid");
      if (response.exceptionDetails) reject("page_action_failed");
      return response.result.value;
    },
    async invoke(targetId, functionDeclaration, arguments_) {
      if (
        typeof functionDeclaration !== "string" ||
        functionDeclaration.length === 0 ||
        !Array.isArray(arguments_)
      ) {
        reject("page_action_invalid");
      }
      const target = await targetForCall(targetId);
      const globalResult = await cdpRequest(
        target.webSocketDebuggerUrl,
        "Runtime.evaluate",
        {
          expression: "globalThis",
          returnByValue: false,
        },
        { WebSocketImpl, timeoutMs },
      );
      const objectId = globalResult?.result?.objectId;
      if (typeof objectId !== "string") reject("cdp_response_invalid");
      try {
        const response = await cdpRequest(
          target.webSocketDebuggerUrl,
          "Runtime.callFunctionOn",
          {
            objectId,
            functionDeclaration,
            arguments: arguments_.map((value) => ({ value })),
            awaitPromise: true,
            returnByValue: true,
          },
          { WebSocketImpl, timeoutMs },
        );
        if (!isPlainObject(response?.result)) reject("cdp_response_invalid");
        if (response.exceptionDetails) reject("page_action_failed");
        return response.result.value;
      } finally {
        await cdpRequest(
          target.webSocketDebuggerUrl,
          "Runtime.releaseObject",
          { objectId },
          { WebSocketImpl, timeoutMs },
        ).catch(() => {});
      }
    },
  });
}

export async function bindExactChatGptTarget(transport, rawTarget) {
  const target = normalizeExactTarget(rawTarget);
  if (
    !transport ||
    typeof transport.listTargets !== "function" ||
    typeof transport.evaluate !== "function" ||
    typeof transport.invoke !== "function"
  ) {
    reject("transport_invalid");
  }
  let targets;
  try {
    targets = await transport.listTargets();
  } catch (error) {
    if (error instanceof ChatGptComposerError) throw error;
    reject("target_list_failed");
  }
  if (!Array.isArray(targets)) reject("target_list_invalid");
  const matches = targets.filter(
    (candidate) =>
      candidate?.type === "page" &&
      candidate.id === target.target_id &&
      candidate.url === target.target_url,
  );
  if (matches.length !== 1) reject("target_mismatch");
  return target;
}

export async function composerPageAction(action, payload) {
  if (
    typeof payload?.expected_target_url !== "string" ||
    location.href !== payload.expected_target_url
  ) {
    return { ok: false, code: "target_url_mismatch" };
  }
  const visible = (element) => {
    if (!element) return false;
    const rectangle = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return (
      rectangle.width > 1 &&
      rectangle.height > 1 &&
      style.display !== "none" &&
      style.visibility !== "hidden"
    );
  };
  const enabled = (element) =>
    !element.disabled && element.getAttribute("aria-disabled") !== "true";
  const sleep = (milliseconds) =>
    new Promise((resolvePromise) =>
      setTimeout(resolvePromise, milliseconds),
    );
  const uniqueVisible = (root, selector) => {
    const candidates = Array.from(root.querySelectorAll(selector)).filter(
      visible,
    );
    return candidates.length === 1 ? candidates[0] : null;
  };
  const promptFields = Array.from(
    document.querySelectorAll(
      "#prompt-textarea[contenteditable='true'],[contenteditable='true'][role='textbox']",
    ),
  ).filter(visible);
  if (promptFields.length !== 1) {
    return { ok: false, code: "composer_ambiguous" };
  }
  const promptField = promptFields[0];
  const composer =
    promptField.closest("[data-testid='composer']") ||
    promptField.closest("form");
  if (!composer || !visible(composer)) {
    return { ok: false, code: "composer_ambiguous" };
  }
  const summary = () => ({
    ok: true,
    target_url: location.href,
    prompt_field_count: promptFields.length,
    prompt_length: String(
      promptField.innerText || promptField.textContent || "",
    ).length,
  });
  const click = (element) => {
    element.scrollIntoView({ block: "center", inline: "center" });
    element.click();
  };

  if (action === "inspect") return summary();

  if (action === "clear" || action === "replace-content") {
    const content =
      action === "replace-content" && typeof payload?.content === "string"
        ? payload.content
        : "";
    if (action === "replace-content" && content.length === 0) {
      return { ok: false, code: "content_invalid" };
    }
    promptField.focus();
    document.execCommand("selectAll", false, null);
    document.execCommand("delete", false, null);
    if (content) {
      const inserted = document.execCommand("insertText", false, content);
      if (!inserted) promptField.textContent = content;
    } else {
      promptField.textContent = "";
    }
    promptField.dispatchEvent(
      new InputEvent("input", {
        bubbles: true,
        inputType: content ? "insertText" : "deleteContentBackward",
        data: content ? content.slice(0, 1) : null,
      }),
    );
    await sleep(100);
    const result = summary();
    result.ok =
      action === "clear"
        ? result.prompt_length === 0
        : result.prompt_length > 0;
    if (!result.ok) result.code = "content_write_failed";
    return result;
  }

  if (action === "select-pro") {
    const model = payload?.model;
    if (
      typeof model !== "string" ||
      !/^gpt-[a-z0-9]+(?:[.-][a-z0-9]+)*-pro$/.test(model)
    ) {
      return { ok: false, code: "model_invalid" };
    }
    const control = uniqueVisible(
      composer,
      "[data-testid='model-switcher-dropdown-button'],[data-testid='model-switcher']",
    );
    if (!control || !enabled(control)) {
      return { ok: false, code: "model_control_ambiguous" };
    }
    click(control);
    await sleep(150);
    const menuRoots = Array.from(
      document.querySelectorAll(
        "[role='menu'],[role='listbox'],[data-radix-menu-content]",
      ),
    ).filter(visible);
    const candidates = menuRoots.flatMap((root) =>
      Array.from(
        root.querySelectorAll(
          "[role='menuitem'][data-model-id],[role='option'][data-model-id],[data-testid][data-model-id]",
        ),
      ).filter(
        (element) =>
          visible(element) &&
          enabled(element) &&
          element.getAttribute("data-model-id") === model,
      ),
    );
    if (candidates.length !== 1) {
      return { ok: false, code: "model_option_ambiguous" };
    }
    click(candidates[0]);
    await sleep(150);
    return { ...summary(), selected_model: model };
  }

  if (action === "send") {
    const button = uniqueVisible(
      composer,
      "[data-testid='send-button'],#composer-submit-button",
    );
    if (!button || !enabled(button)) {
      return { ok: false, code: "send_control_ambiguous" };
    }
    click(button);
    return { ok: true, sent: true };
  }

  return { ok: false, code: "action_invalid" };
}

export function composerPageActionDeclaration() {
  return composerPageAction.toString();
}

export async function runComposerAction(
  transport,
  rawTarget,
  action,
  payload = null,
) {
  const target = await bindExactChatGptTarget(transport, rawTarget);
  if (!ACTIONS.has(action)) reject("action_invalid");
  if (
    action === "select-pro" &&
    (!isPlainObject(payload) ||
      typeof payload.model !== "string" ||
      !PRO_MODEL_PATTERN.test(payload.model))
  ) {
    reject("model_invalid");
  }
  if (
    action === "replace-content" &&
    (!isPlainObject(payload) ||
      typeof payload.content !== "string" ||
      payload.content.length === 0)
  ) {
    reject("content_invalid");
  }
  let result;
  try {
    const pagePayload = isPlainObject(payload)
      ? { ...payload, expected_target_url: target.target_url }
      : { expected_target_url: target.target_url };
    result = await transport.invoke(
      target.target_id,
      composerPageActionDeclaration(),
      [action, pagePayload],
    );
  } catch (error) {
    if (error instanceof ChatGptComposerError) throw error;
    reject("page_action_failed");
  }
  if (!isPlainObject(result) || result.ok !== true) {
    reject(
      typeof result?.code === "string"
        ? `page_${result.code}`
        : "page_action_failed",
    );
  }
  return Object.freeze(structuredClone(result));
}

async function readPrivateText(pathname) {
  pathname = normalizedAbsolutePath(pathname, "private_file_invalid");
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
      metadata.size > MAX_PRIVATE_INPUT_BYTES ||
      (typeof process.getuid === "function" &&
        metadata.uid !== process.getuid()) ||
      (await realpath(pathname)) !== pathname
    ) {
      reject("private_file_invalid");
    }
    return await handle.readFile("utf8");
  } catch (error) {
    if (error instanceof ChatGptComposerError) throw error;
    reject("private_file_invalid");
  } finally {
    await handle?.close().catch(() => {});
  }
}

async function readControl(pathname) {
  let value;
  try {
    value = JSON.parse(await readPrivateText(pathname));
  } catch (error) {
    if (error instanceof ChatGptComposerError) throw error;
    reject("control_invalid");
  }
  return exactObject(
    value,
    ["endpoint", "target_id", "target_url", "action"],
    ["model", "request_file"],
    "control_invalid",
  );
}

export async function main(rawArguments = process.argv.slice(2)) {
  if (
    rawArguments.length !== 2 ||
    rawArguments[0] !== "--control-file"
  ) {
    reject("arguments_invalid");
  }
  const control = await readControl(rawArguments[1]);
  if (ADAPTER_ONLY_ACTIONS.has(control.action)) {
    reject("adapter_required");
  }
  const transport = createLoopbackCdpTransport(control.endpoint);
  let payload = null;
  if (control.action === "select-pro") {
    payload = { model: control.model };
  }
  const result = await runComposerAction(
    transport,
    {
      target_id: control.target_id,
      target_url: control.target_url,
    },
    control.action,
    payload,
  );
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

const invokedPath = process.argv[1]
  ? pathToFileURL(resolve(process.argv[1])).href
  : "";
if (invokedPath === import.meta.url) {
  main().catch((error) => {
    const code =
      error instanceof ChatGptComposerError ? error.code : "unexpected_failure";
    process.stderr.write(`chatgpt-composer:${code}\n`);
    process.exitCode = 1;
  });
}
