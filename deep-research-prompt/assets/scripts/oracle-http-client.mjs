#!/usr/bin/env node
/**
 * oracle-http-client.mjs
 *
 * Direct HTTPS client for the ChatGPT backend conversation API.
 *
 * Replaces DOM automation for the ask-a-question path. Contains ZERO
 * ChatGPT-specific CSS selectors, zero `data-testid` contracts, and zero
 * exact-text assertions. Model selection is a JSON field (`model`), not a
 * dropdown click.
 *
 * Reconstructed contract: ../../references/chatgpt-backend-api.md
 *
 * ARCHITECTURE
 * ------------
 * The conversation endpoint is gated by OpenAI's "sentinel" anti-abuse system,
 * which requires three per-request headers whose values are produced by
 * executing obfuscated challenge programs inside a real browser. Those programs
 * are a bot defense: this client does NOT reimplement, emulate, or defeat them.
 *
 * Instead the operator's own already-authenticated browser mints the tokens
 * exactly as it normally would, and this client brokers them over loopback CDP.
 * The browser satisfies the defense; the client only carries the result.
 *
 *   [operator's Chrome]  --mint-->  sentinel triple + session cookies
 *            |                                   |
 *            +--------- loopback CDP ------------+
 *                                                v
 *                                   [this client]  --HTTPS-->  chatgpt.com
 *
 * The mint trigger uses only generic HTML semantics (`document.activeElement`,
 * `Element.closest("form")`, `HTMLFormElement.requestSubmit()`), so a ChatGPT
 * redesign of class names, test ids, or button labels cannot break it.
 *
 * USAGE
 *   node oracle-http-client.mjs --prompt "..." [--model gpt-5-6-pro]
 *   node oracle-http-client.mjs --list-models
 *
 * ENV
 *   ORACLE_CDP_PORT           loopback CDP port (default 9222)
 *   ORACLE_HTTP_TIMEOUT_MS    overall answer deadline (default 900000)
 */

import { randomUUID } from "node:crypto";

export const ORIGIN = "https://chatgpt.com";
export const CONVERSATION_PATH = "/backend-api/f/conversation";
export const SESSION_PATH = "/api/auth/session";
export const ACCOUNTS_PATH = "/backend-api/accounts/check/v4-2023-04-27";
export const MODELS_PATH = "/backend-api/models?history_and_training_disabled=false";

/** Headers the browser mints per submission; all three are required (403 otherwise). */
export const SENTINEL_HEADERS = Object.freeze([
  "openai-sentinel-chat-requirements-token",
  "openai-sentinel-proof-token",
  "openai-sentinel-turnstile-token",
]);

const DEFAULT_PORT = 9222;
const DEFAULT_TIMEOUT_MS = 900_000;
const POLL_INTERVAL_MS = 5_000;
const CDP_TIMEOUT_MS = 30_000;

export class OracleHttpError extends Error {
  constructor(code, detail) {
    super(detail ? `${code}: ${detail}` : code);
    this.name = "OracleHttpError";
    this.code = code;
    this.detail = detail ?? null;
  }
}

const fail = (code, detail) => {
  throw new OracleHttpError(code, detail);
};

/* ------------------------------------------------------------------ *
 * Pure helpers (unit-tested without a live browser)
 * ------------------------------------------------------------------ */

/**
 * Parse an SSE body into ordered frames.
 * Framing (observed): `event: <name>` lines optionally precede `data: <json>`
 * lines; frames are separated by a blank line; the stream terminates with the
 * literal frame `data: [DONE]`.
 */
export function parseSseFrames(text) {
  if (typeof text !== "string") fail("sse_invalid", "body is not a string");
  const frames = [];
  for (const block of text.split(/\r?\n\r?\n/)) {
    if (!block.trim()) continue;
    let event = null;
    const dataLines = [];
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (!dataLines.length) continue;
    const raw = dataLines.join("\n");
    if (raw === "[DONE]") {
      frames.push({ event, done: true, raw, data: null });
      continue;
    }
    let data = null;
    try {
      data = JSON.parse(raw);
    } catch {
      /* non-JSON data frames are preserved raw */
    }
    frames.push({ event, done: false, raw, data });
  }
  return frames;
}

/** True when the stream reached its terminator. */
export function sseComplete(frames) {
  return frames.some((f) => f.done);
}

/**
 * Summarise a conversation SSE stream.
 * Returns conversation_id, the assistant text assembled from inline `delta`
 * frames (fast models), and whether the turn was handed off to a resumable
 * channel (Pro / reasoning models finish out-of-band).
 */
export function summariseConversationStream(frames) {
  let conversationId = null;
  let handoff = false;
  let inputMessageId = null;
  let error = null;
  let activePath = null;
  const parts = [];

  for (const f of frames) {
    const d = f.data;
    if (!d || typeof d !== "object") continue;
    if (typeof d.conversation_id === "string") conversationId ??= d.conversation_id;
    if (d.type === "stream_handoff") handoff = true;
    if (d.type === "input_message") inputMessageId ??= d.input_message?.id ?? null;
    if (d.type === "error" || d.error) error ??= d.error ?? d.detail ?? null;

    // Inline streaming, delta_encoding v1. Three frame shapes carry answer
    // text and all three are required: the opening `add` message, an explicit
    // `append` naming the parts path, and then bare `{"v":"…"}` continuation
    // frames that omit both `p` and `o` because the path is already implied.
    // The continuation frames are the bulk of the answer — dropping them
    // truncates every fast-model reply after its first chunk.
    const msg = d.v?.message ?? d.message;
    if (msg && msg.author?.role === "assistant" && msg.recipient === "all") {
      const p = msg.content?.parts;
      if (Array.isArray(p) && typeof p[0] === "string" && p[0]) parts.push(p[0]);
      activePath = "/message/content/parts/0";
    } else if (d.o === "append" && typeof d.v === "string" && /\/parts\//.test(d.p ?? "")) {
      parts.push(d.v);
      activePath = d.p;
    } else if (
      activePath &&
      d.o === undefined &&
      d.p === undefined &&
      typeof d.v === "string"
    ) {
      parts.push(d.v);
    } else if (d.o === "patch" && Array.isArray(d.v)) {
      for (const op of d.v) {
        if (op?.o === "append" && typeof op.v === "string" && /\/parts\//.test(op.p ?? "")) {
          parts.push(op.v);
        }
      }
    }
  }
  return {
    conversationId,
    inputMessageId,
    handoff,
    error,
    complete: sseComplete(frames),
    inlineText: parts.join(""),
  };
}

/**
 * Extract the final assistant answer from a `GET /backend-api/conversation/{id}`
 * payload. Ignores reasoning/tool nodes (`recipient !== "all"`, tool authors,
 * and `content_type` values other than `text`).
 */
/**
 * Observed `conversation.async_status` while a Pro turn is still generating.
 * This is the API counterpart of ChatGPT's composer still showing the stop
 * button: while it holds, the turn can still be cancelled, so it is not done.
 */
export const ASYNC_STATUS_GENERATING = 3;

/**
 * True while the turn is still producing output.
 *
 * `end_turn` alone is NOT sufficient on Pro. Observed 2026-07-28: 32s into a
 * Pro turn the conversation already contained an assistant/all text message
 * with `status: finished_successfully`, `end_turn: true` and a `model_slug` —
 * satisfying every "looks final" filter — while `web.run` was still running and
 * `async_status` stayed 3 for minutes afterwards. Treating that as the answer
 * returned a 189-character fragment instead of the real reply.
 *
 * Two independent signals, either of which means "still going": a message in
 * `in_progress`, or the async turn status. The pair covers the gap between
 * messages where nothing is individually in progress yet.
 */
export function turnInProgress(conversation) {
  if (conversation?.async_status === ASYNC_STATUS_GENERATING) return true;
  const mapping = conversation?.mapping;
  if (!mapping || typeof mapping !== "object") return false;
  return Object.values(mapping).some((node) => node?.message?.status === "in_progress");
}

export function extractFinalAnswer(conversation, { afterCreateTime = 0 } = {}) {
  const mapping = conversation?.mapping;
  if (!mapping || typeof mapping !== "object") fail("conversation_invalid", "missing mapping");
  const candidates = Object.values(mapping)
    .map((node) => node?.message)
    .filter(Boolean)
    .filter((m) => m.author?.role === "assistant")
    .filter((m) => m.recipient === "all")
    .filter((m) => m.status === "finished_successfully" && m.end_turn === true)
    .filter((m) => m.content?.content_type === "text")
    .filter((m) => (m.create_time ?? 0) >= afterCreateTime)
    // reasoning recaps carry no model_slug; the answer message does
    .filter((m) => typeof m.metadata?.model_slug === "string")
    .sort((a, b) => (a.create_time ?? 0) - (b.create_time ?? 0));
  // A genuinely finished reply carries finish_details (observed `type: "stop"`);
  // Pro's interim end_turn message does not. Prefer a stopped message when one
  // exists, else fall back to newest-wins so models that omit the field still
  // resolve.
  const stopped = candidates.filter((m) => m.metadata?.finish_details?.type);
  const pool = stopped.length ? stopped : candidates;
  const last = pool[pool.length - 1];
  if (!last) return null;
  const text = (last.content.parts ?? []).filter((p) => typeof p === "string").join("");
  return { text, messageId: last.id, modelSlug: last.metadata.model_slug, createTime: last.create_time ?? null };
}

/** Build the conversation request body from a harvested template. */
export function buildConversationBody(
  template,
  { prompt, model, parentMessageId, conversationId, projectId },
) {
  if (typeof prompt !== "string" || !prompt.length) fail("prompt_invalid");
  if (typeof model !== "string" || !model.length) fail("model_invalid");
  const base = template && typeof template === "object" ? { ...template } : {};
  delete base.client_prepare_state;
  // A conversation joins a Project through conversation_mode. Set it explicitly
  // rather than inheriting whatever page the template was harvested from,
  // otherwise a drifted tab silently files the answer in root chat.
  const conversationMode = projectId
    ? { kind: "gizmo_interaction", gizmo_id: projectId }
    : base.conversation_mode;
  // A fresh chat is the default. The harvested template carries whatever
  // conversation the donor tab was sitting on, so inheriting it silently
  // appends to an unrelated thread. Continuing is opt-in: the caller must pass
  // an explicit conversationId.
  const resolvedConversationId = conversationId ?? undefined;
  return {
    ...base,
    action: "next",
    model,
    ...(conversationMode ? { conversation_mode: conversationMode } : {}),
    conversation_id: resolvedConversationId ?? undefined,
    parent_message_id: parentMessageId ?? base.parent_message_id,
    messages: [
      {
        id: randomUUID(),
        author: { role: "user" },
        create_time: Date.now() / 1000,
        content: { content_type: "text", parts: [prompt] },
        metadata: { selected_sources: [], serialization_metadata: { custom_symbol_offsets: [] } },
      },
    ],
  };
}

/** Validate that a harvested header bundle carries a usable sentinel triple. */
export function assertSentinelBundle(headers) {
  if (!headers || typeof headers !== "object") fail("sentinel_missing", "no headers");
  const missing = SENTINEL_HEADERS.filter((h) => typeof headers[h] !== "string" || !headers[h].length);
  if (missing.length) fail("sentinel_missing", missing.join(","));
  if (typeof headers.authorization !== "string" || !headers.authorization.startsWith("Bearer ")) {
    fail("sentinel_missing", "authorization");
  }
  return true;
}

/**
 * True only for the conversation submission endpoint itself.
 *
 * Load-bearing: a substring test also matches the sibling
 * `/backend-api/f/conversation/prepare`, which the app fires on every debounced
 * composer edit and which carries NO sentinel headers. Intercepting that one
 * captures an empty bundle and breaks the mint cycle.
 *
 * This function's source is injected verbatim into the page, so the browser and
 * the unit tests run the same predicate.
 */
export function isConversationEndpoint(url, origin, conversationPath) {
  try {
    return new URL(url, origin).pathname === conversationPath;
  } catch {
    return false;
  }
}

/** Never log secrets: reduce a credential to an identifying prefix. */
export function redact(value, keep = 8) {
  if (typeof value !== "string" || !value.length) return null;
  return `${value.slice(0, keep)}…[${value.length}]`;
}

/* ------------------------------------------------------------------ *
 * Loopback CDP transport (JSON + Input only; no DOM queries)
 * ------------------------------------------------------------------ */

function assertLoopback(url, port) {
  const parsed = new URL(url);
  if (parsed.protocol !== "ws:" || parsed.hostname !== "127.0.0.1" || parsed.port !== String(port)) {
    fail("cdp_transport_invalid", url);
  }
  return parsed.href;
}

/** Extract the `g-p-…` Project id from a ChatGPT project URL. */
export function projectIdFromUrl(value) {
  const match = /\/g\/(g-p-[A-Za-z0-9_-]{8,128})\b/.exec(String(value ?? ""));
  return match ? match[1] : null;
}

export async function connectCdp(
  port = DEFAULT_PORT,
  { fetchImpl = globalThis.fetch, WebSocketImpl, projectId = null } = {},
) {
  const endpoint = `http://127.0.0.1:${port}`;
  let targets;
  try {
    targets = await (await fetchImpl(`${endpoint}/json`, { cache: "no-store" })).json();
  } catch (cause) {
    fail("cdp_unreachable", `${endpoint} (${cause?.message ?? cause})`);
  }
  const pages = (Array.isArray(targets) ? targets : []).filter(
    (t) => t?.type === "page" && typeof t.url === "string" && t.url.startsWith(ORIGIN),
  );
  if (!pages.length) fail("cdp_no_chatgpt_target", `${endpoint} has no chatgpt.com page target`);
  // When a Project is configured, harvest from that Project's page so the
  // template carries its gizmo binding. Only fall back to a conversation tab
  // when no Project is set — a `/c/` tab would file the answer in root chat.
  const projectPage = projectId
    ? pages.find((t) => t.url.includes(`/g/${projectId}`))
    : null;
  const target = projectPage ?? pages.find((t) => t.url.includes("/c/")) ?? pages[0];
  const WebSocketCtor = WebSocketImpl ?? globalThis.WebSocket;
  const socket = new WebSocketCtor(assertLoopback(target.webSocketDebuggerUrl, port));
  const pending = new Map();
  let nextId = 1;
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", () => reject(new OracleHttpError("cdp_failed", target.id)), { once: true });
  });
  socket.addEventListener("message", (ev) => {
    let msg;
    try {
      msg = JSON.parse(typeof ev.data === "string" ? ev.data : Buffer.from(ev.data).toString());
    } catch {
      return;
    }
    const entry = msg.id && pending.get(msg.id);
    if (!entry) return;
    pending.delete(msg.id);
    clearTimeout(entry.timer);
    if (msg.error) entry.reject(new OracleHttpError("cdp_call_failed", JSON.stringify(msg.error)));
    else entry.resolve(msg.result);
  });

  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const id = nextId++;
      // The timer must be cleared on settle, otherwise every call keeps the
      // event loop alive for CDP_TIMEOUT_MS after the work is finished.
      const timer = setTimeout(() => {
        if (pending.delete(id)) reject(new OracleHttpError("cdp_timeout", method));
      }, CDP_TIMEOUT_MS);
      if (typeof timer.unref === "function") timer.unref();
      pending.set(id, { resolve, reject, timer });
      socket.send(JSON.stringify({ id, method, params }));
    });

  return {
    targetId: target.id,
    url: target.url,
    send,
    async evaluate(expression) {
      const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
      if (r?.exceptionDetails) fail("page_eval_failed", r.exceptionDetails.exception?.description ?? "unknown");
      return r?.result?.value;
    },
    close() {
      try {
        socket.close();
      } catch {
        /* already closed */
      }
    },
  };
}

/* ------------------------------------------------------------------ *
 * Credential + sentinel brokerage
 * ------------------------------------------------------------------ */

/** Read bearer token, account id and user agent via the site's own JSON APIs. */
export async function harvestCredentials(cdp) {
  const creds = await cdp.evaluate(`(async () => {
    const s = await (await fetch(${JSON.stringify(SESSION_PATH)}, { credentials: "include", cache: "no-store" })).json();
    if (!s || !s.accessToken) return { error: "no_access_token" };
    const a = await (await fetch(${JSON.stringify(ACCOUNTS_PATH)}, {
      credentials: "include", cache: "no-store",
      headers: { authorization: "Bearer " + s.accessToken },
    })).json();
    const acct = a && a.accounts && a.accounts.default && a.accounts.default.account;
    return {
      accessToken: s.accessToken,
      expires: s.expires || null,
      accountId: acct ? acct.account_id : null,
      planType: acct ? acct.plan_type : null,
      userAgent: navigator.userAgent,
    };
  })()`);
  if (!creds || creds.error) fail("session_unavailable", creds?.error ?? "empty");
  const jar = await cdp.send("Network.getCookies", { urls: [`${ORIGIN}/`] });
  const cookies = (jar?.cookies ?? []).map((c) => `${c.name}=${c.value}`).join("; ");
  if (!cookies) fail("cookies_unavailable", "edge cookies are required (cf_clearance/__cf_bm)");
  return { ...creds, cookieHeader: cookies };
}

/**
 * Ask the operator's browser to mint one fresh, unused sentinel bundle.
 *
 * The app's own outgoing conversation POST is intercepted before it reaches the
 * network and rejected, so the tokens are minted but never spent — no model
 * request is made and no message is created. The trigger uses only generic HTML
 * semantics, never a ChatGPT-specific selector.
 */
export async function harvestSentinelBundle(cdp, { triggerText = "." , timeoutMs = 20_000 } = {}) {
  const installed = await cdp.evaluate(`(() => {
    if (globalThis.__oracleHarvest) return "busy";
    globalThis.__oracleHarvest = { captured: null };
    const isConversationEndpoint = ${isConversationEndpoint.toString()};
    const CONVERSATION_PATH = ${JSON.stringify(CONVERSATION_PATH)};
    const original = globalThis.fetch;
    globalThis.__oracleHarvestOriginal = original;
    globalThis.fetch = function (input, init) {
      const url = typeof input === "string" ? input : (input && input.url) || String(input);
      const method = ((init && init.method) || (input && input.method) || "GET").toUpperCase();
      if (method === "POST" && isConversationEndpoint(url, location.origin, CONVERSATION_PATH)) {
        // Headers may ride on a Request \`input\` instead of \`init\`; merge both.
        let headers = {};
        try {
          if (input && input.headers) {
            headers = Object.fromEntries(new Headers(input.headers).entries());
          }
        } catch {}
        try {
          if (init && init.headers) {
            headers = Object.assign(headers, Object.fromEntries(new Headers(init.headers).entries()));
          }
        } catch {}
        globalThis.__oracleHarvest.captured = {
          headers,
          body: init && typeof init.body === "string" ? init.body : null,
        };
        return Promise.reject(new TypeError("Failed to fetch"));
      }
      return original.apply(this, arguments);
    };
    return "installed";
  })()`);
  if (installed !== "installed") fail("harvest_busy", String(installed));

  const restore = () =>
    cdp
      .evaluate(`(() => {
        if (globalThis.__oracleHarvestOriginal) {
          globalThis.fetch = globalThis.__oracleHarvestOriginal;
          delete globalThis.__oracleHarvestOriginal;
        }
        delete globalThis.__oracleHarvest;
        return "restored";
      })()`)
      .catch(() => null);

  try {
    // Generic-HTML trigger: type into whatever the page focused, submit its form.
    await cdp.send("Input.insertText", { text: triggerText });
    await new Promise((r) => setTimeout(r, 1500));
    const submitted = await cdp.evaluate(`(() => {
      const el = document.activeElement;
      const form = el && typeof el.closest === "function" ? el.closest("form") : null;
      if (!form) return "no_form";
      const btn = form.querySelector("button[type='submit']:not([disabled])");
      if (btn) { btn.click(); return "submit_button"; }
      if (typeof form.requestSubmit === "function") { form.requestSubmit(); return "request_submit"; }
      return "no_submit_path";
    })()`);
    if (submitted === "no_form" || submitted === "no_submit_path") fail("mint_trigger_failed", String(submitted));

    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 400));
      const raw = await cdp.evaluate(`JSON.stringify((globalThis.__oracleHarvest || {}).captured || null)`);
      const captured = raw ? JSON.parse(raw) : null;
      if (captured) {
        assertSentinelBundle(captured.headers);
        let template = {};
        try {
          template = captured.body ? JSON.parse(captured.body) : {};
        } catch {
          template = {};
        }
        return { headers: captured.headers, template, trigger: submitted };
      }
    }
    fail("mint_timeout", `no conversation POST within ${timeoutMs}ms`);
  } finally {
    await restore();
  }
}

/* ------------------------------------------------------------------ *
 * HTTP surface
 * ------------------------------------------------------------------ */

function apiHeaders(creds, extra = {}) {
  return {
    authorization: `Bearer ${creds.accessToken}`,
    "user-agent": creds.userAgent,
    accept: "*/*",
    ...(creds.accountId ? { "chatgpt-account-id": creds.accountId } : {}),
    ...extra,
  };
}

export async function listModels(creds, { fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(`${ORIGIN}${MODELS_PATH}`, { headers: apiHeaders(creds) });
  if (!res.ok) fail("models_failed", `HTTP ${res.status}`);
  const body = await res.json();
  return (body.models ?? []).map((m) => ({
    slug: m.slug,
    title: m.title,
    maxTokens: m.max_tokens ?? null,
  }));
}

export async function getConversation(conversationId, creds, { fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(`${ORIGIN}/backend-api/conversation/${conversationId}`, {
    headers: apiHeaders(creds),
  });
  if (res.status === 401) fail("auth_expired", "HTTP 401");
  if (!res.ok) fail("conversation_read_failed", `HTTP ${res.status}`);
  return res.json();
}

export async function postConversation({ body, headers, cookieHeader, creds, fetchImpl = globalThis.fetch }) {
  assertSentinelBundle(headers);
  const res = await fetchImpl(`${ORIGIN}${CONVERSATION_PATH}`, {
    method: "POST",
    headers: {
      ...headers,
      "user-agent": creds.userAgent,
      "accept-language": "en-US,en;q=0.9",
      origin: ORIGIN,
      referer: `${ORIGIN}/`,
      "sec-fetch-dest": "empty",
      "sec-fetch-mode": "cors",
      "sec-fetch-site": "same-origin",
      cookie: cookieHeader,
    },
    body: JSON.stringify(body),
  });
  if (res.status === 403) {
    const text = await res.text();
    fail("sentinel_rejected", text.slice(0, 200).replace(/\s+/g, " "));
  }
  if (res.status === 401) fail("auth_expired", "HTTP 401");
  if (!res.ok) fail("conversation_post_failed", `HTTP ${res.status}`);
  let sse = "";
  const decoder = new TextDecoder();
  for await (const chunk of res.body) sse += decoder.decode(chunk, { stream: true });
  return { status: res.status, sse };
}

/**
 * Ask the oracle one question over HTTPS and return the assistant's text.
 * No DOM interaction beyond the generic-HTML sentinel mint trigger.
 */
export async function askOracle({
  prompt,
  model = "gpt-5-6-pro",
  port = Number(process.env.ORACLE_CDP_PORT ?? DEFAULT_PORT),
  timeoutMs = Number(process.env.ORACLE_HTTP_TIMEOUT_MS ?? DEFAULT_TIMEOUT_MS),
  project = process.env.ORACLE_CHATGPT_PROJECT_URL ?? null,
  // null starts a fresh chat; pass an id to continue that conversation.
  conversationId = null,
  fetchImpl = globalThis.fetch,
  onProgress = () => {},
} = {}) {
  const started = Date.now();
  const projectId = project ? (projectIdFromUrl(project) ?? project) : null;
  const cdp = await connectCdp(port, { projectId });
  let creds;
  let bundle;
  try {
    creds = await harvestCredentials(cdp);
    onProgress({ phase: "credentials", tokenPrefix: redact(creds.accessToken), planType: creds.planType });
    bundle = await harvestSentinelBundle(cdp);
    onProgress({ phase: "sentinel", trigger: bundle.trigger, headers: Object.keys(bundle.headers).length });
  } finally {
    cdp.close();
  }

  const body = buildConversationBody(bundle.template, {
    prompt,
    model,
    parentMessageId: bundle.template.parent_message_id,
    conversationId,
    projectId,
  });
  onProgress({
    phase: "target",
    project: projectId ?? "root",
    thread: conversationId ? "continued" : "new",
  });
  const postedAt = Date.now() / 1000;
  const { sse } = await postConversation({
    body,
    headers: bundle.headers,
    cookieHeader: creds.cookieHeader,
    creds,
    fetchImpl,
  });
  const frames = parseSseFrames(sse);
  const summary = summariseConversationStream(frames);
  onProgress({ phase: "stream", handoff: summary.handoff, complete: summary.complete, frames: frames.length });
  if (summary.error) fail("stream_error", String(summary.error).slice(0, 200));

  if (!summary.handoff && summary.inlineText) {
    return { text: summary.inlineText, model, conversationId: summary.conversationId, source: "inline", elapsedMs: Date.now() - started };
  }

  // Handed-off turn (Pro / reasoning): the answer lands on the conversation.
  const answerThreadId = summary.conversationId ?? body.conversation_id;
  if (!answerThreadId) fail("conversation_id_missing");
  const deadline = started + timeoutMs;
  while (Date.now() < deadline) {
    const conversation = await getConversation(answerThreadId, creds, { fetchImpl });
    // Never harvest mid-flight: Pro publishes an interim end_turn message long
    // before it stops generating, and reading it yields a fragment.
    const generating = turnInProgress(conversation);
    const answer = generating
      ? null
      : extractFinalAnswer(conversation, { afterCreateTime: postedAt });
    if (answer) {
      return { ...answer, model, conversationId: answerThreadId, source: "polled", elapsedMs: Date.now() - started };
    }
    onProgress({ phase: "poll", elapsedMs: Date.now() - started, generating });
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
  }
  fail("answer_timeout", `${timeoutMs}ms`);
}

/* ------------------------------------------------------------------ *
 * CLI
 * ------------------------------------------------------------------ */

function parseArgv(argv) {
  const out = { model: "gpt-5-6-pro" };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--prompt") out.prompt = argv[++i];
    else if (a === "--model") out.model = argv[++i];
    else if (a === "--port") out.port = Number(argv[++i]);
    else if (a === "--list-models") out.listModels = true;
    else if (a === "--json") out.json = true;
  }
  return out;
}

async function main() {
  const args = parseArgv(process.argv.slice(2));
  if (args.listModels) {
    const cdp = await connectCdp(args.port ?? Number(process.env.ORACLE_CDP_PORT ?? DEFAULT_PORT));
    try {
      const creds = await harvestCredentials(cdp);
      const models = await listModels(creds);
      process.stdout.write(JSON.stringify({ plan_type: creds.planType, models }, null, 2) + "\n");
    } finally {
      cdp.close();
    }
    return;
  }
  if (!args.prompt) {
    process.stderr.write("usage: oracle-http-client.mjs --prompt <text> [--model <slug>] [--list-models]\n");
    process.exitCode = 2;
    return;
  }
  const result = await askOracle({
    prompt: args.prompt,
    model: args.model,
    port: args.port,
    onProgress: (p) => process.stderr.write(`[oracle-http] ${JSON.stringify(p)}\n`),
  });
  process.stdout.write(args.json ? JSON.stringify(result, null, 2) + "\n" : result.text + "\n");
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((error) => {
    process.stderr.write(`[oracle-http] ${error.code ?? "error"}: ${error.detail ?? error.message}\n`);
    process.exitCode = 1;
  });
}
