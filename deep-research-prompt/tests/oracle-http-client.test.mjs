import assert from "node:assert/strict";
import test from "node:test";

import {
  CONVERSATION_PATH,
  ORIGIN,
  OracleHttpError,
  SENTINEL_HEADERS,
  assertSentinelBundle,
  buildConversationBody,
  extractFinalAnswer,
  getConversation,
  isConversationEndpoint,
  listModels,
  parseSseFrames,
  postConversation,
  projectIdFromUrl,
  redact,
  sseComplete,
  summariseConversationStream,
} from "../assets/scripts/oracle-http-client.mjs";

/* ------------------------------------------------------------------ *
 * Fixtures — shapes reduced from the 2026-07-28 live capture.
 * No live calls in this file.
 * ------------------------------------------------------------------ */

const CONVERSATION_ID = "6a693893-789c-83e8-8abc-ec20a2b45cb3";
const TURN = "f1182aff-e5b4-4208-a333-09d96734f76c";

const PRO_HANDOFF_SSE = [
  `event: delta_encoding`,
  `data: "v1"`,
  ``,
  `data: {"type": "resume_conversation_token", "kind": "topic", "token": "eyJhbGciOiJFUzI1NiJ9.x.y", "conversation_id": "${CONVERSATION_ID}"}`,
  ``,
  `data: {"type": "input_message", "input_message": {"id": "6f966856-82c6-466d-ae64-01c524d19140", "author": {"role": "user"}, "content": {"content_type": "text", "parts": ["Reply with exactly: HTTP_OK"]}}, "conversation_id": "${CONVERSATION_ID}"}`,
  ``,
  `event: delta`,
  `data: {"p": "", "o": "add", "v": {"message": {"id": "1276dae2", "author": {"role": "tool", "name": "a8km123"}, "content": {"content_type": "text", "parts": [""]}, "recipient": "all", "metadata": {"model_slug": "gpt-5-6-pro"}}}, "c": 0}`,
  ``,
  `data: {"type": "stream_handoff", "conversation_id": "${CONVERSATION_ID}", "turn_exchange_id": "${TURN}", "options": [{"type": "resume_sse_endpoint", "topic_id": "conversation-turn-${TURN}"}, {"type": "subscribe_ws_topic", "topic_id": "conversation-turn-${TURN}"}]}`,
  ``,
  `data: {"type": "server_ste_metadata", "metadata": {"plan_type": "pro", "model_slug": "gpt-5-6-pro", "pro_mode_turn_topic_streaming": true}, "conversation_id": "${CONVERSATION_ID}"}`,
  ``,
  `data: {"type": "conversation_detail_metadata", "default_model_slug": "gpt-5-6-pro", "conversation_id": "${CONVERSATION_ID}"}`,
  ``,
  `data: [DONE]`,
  ``,
].join("\n");

const INLINE_SSE = [
  `event: delta_encoding`,
  `data: "v1"`,
  ``,
  `data: {"type": "input_message", "input_message": {"id": "u1"}, "conversation_id": "${CONVERSATION_ID}"}`,
  ``,
  `event: delta`,
  `data: {"p": "", "o": "add", "v": {"message": {"id": "a1", "author": {"role": "assistant"}, "recipient": "all", "content": {"content_type": "text", "parts": ["HTTP"]}}}, "c": 0}`,
  ``,
  `data: {"p": "/message/content/parts/0", "o": "append", "v": "_OK"}`,
  ``,
  `data: [DONE]`,
  ``,
].join("\n");

/** Mirrors the real mapping: tool node + reasoning recap + real answer. */
const CONVERSATION_PAYLOAD = {
  title: "Capture Request",
  default_model_slug: "gpt-5-6-pro",
  mapping: {
    root: { id: "root" },
    u1: {
      id: "u1",
      message: {
        id: "u1",
        author: { role: "user" },
        recipient: "all",
        create_time: 1000,
        status: "finished_successfully",
        end_turn: null,
        content: { content_type: "text", parts: ["Reply with exactly: HTTP_OK"] },
        metadata: {},
      },
    },
    t1: {
      id: "t1",
      message: {
        id: "t1",
        author: { role: "tool", name: "a8km123" },
        recipient: "all",
        create_time: 1001,
        status: "finished_successfully",
        end_turn: null,
        content: { content_type: "text", parts: [""] },
        metadata: { model_slug: "gpt-5-6-pro" },
      },
    },
    r1: {
      // reasoning recap: assistant + end_turn true, but NO model_slug
      id: "r1",
      message: {
        id: "r1",
        author: { role: "assistant" },
        recipient: "all",
        create_time: 1002,
        status: "finished_successfully",
        end_turn: true,
        content: { content_type: "text", parts: ["reasoning_recap"] },
        metadata: {},
      },
    },
    a1: {
      id: "a1",
      message: {
        id: "a1",
        author: { role: "assistant" },
        recipient: "all",
        create_time: 1003,
        status: "finished_successfully",
        end_turn: true,
        content: { content_type: "text", parts: ["HTTP_OK"] },
        metadata: { model_slug: "gpt-5-6-pro" },
      },
    },
  },
};

const SENTINEL_BUNDLE = Object.freeze({
  authorization: "Bearer header.payload.signature",
  "content-type": "application/json",
  accept: "text/event-stream",
  "openai-sentinel-chat-requirements-token": "gAAAAAB-requirements",
  "openai-sentinel-proof-token": "gAAAAAB-proof",
  "openai-sentinel-turnstile-token": "turnstile-payload",
  "chatgpt-account-id": "00000000-0000-4000-8000-000000000001",
});

const CREDS = Object.freeze({
  accessToken: "header.payload.signature",
  accountId: "00000000-0000-4000-8000-000000000001",
  userAgent: "Mozilla/5.0 (Macintosh) Chrome/150",
  cookieHeader: "cf_clearance=abc; __cf_bm=def",
});

function stubFetch(handler) {
  return async (url, init = {}) => handler(String(url), init);
}
function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}
function sseResponse(text, status = 200) {
  return new Response(text, { status, headers: { "content-type": "text/event-stream" } });
}

/* ------------------------------------------------------------------ *
 * SSE framing
 * ------------------------------------------------------------------ */

test("parseSseFrames splits frames and keeps event names", () => {
  const frames = parseSseFrames(PRO_HANDOFF_SSE);
  assert.equal(frames[0].event, "delta_encoding");
  assert.equal(frames[0].data, "v1");
  assert.ok(frames.some((f) => f.event === "delta"));
  assert.equal(frames.filter((f) => f.event === null).length > 0, true);
});

test("parseSseFrames recognises the [DONE] terminator", () => {
  const frames = parseSseFrames(PRO_HANDOFF_SSE);
  const last = frames[frames.length - 1];
  assert.equal(last.done, true);
  assert.equal(last.data, null);
  assert.equal(sseComplete(frames), true);
});

test("sseComplete is false for a truncated stream", () => {
  const truncated = PRO_HANDOFF_SSE.replace("data: [DONE]", "");
  assert.equal(sseComplete(parseSseFrames(truncated)), false);
});

test("parseSseFrames tolerates CRLF framing", () => {
  const frames = parseSseFrames(PRO_HANDOFF_SSE.replace(/\n/g, "\r\n"));
  assert.equal(sseComplete(frames), true);
});

test("parseSseFrames rejects a non-string body", () => {
  assert.throws(() => parseSseFrames(null), (e) => e instanceof OracleHttpError && e.code === "sse_invalid");
});

/* ------------------------------------------------------------------ *
 * Stream summary
 * ------------------------------------------------------------------ */

test("summariseConversationStream detects a Pro handoff", () => {
  const s = summariseConversationStream(parseSseFrames(PRO_HANDOFF_SSE));
  assert.equal(s.handoff, true);
  assert.equal(s.complete, true);
  assert.equal(s.conversationId, CONVERSATION_ID);
  assert.equal(s.inputMessageId, "6f966856-82c6-466d-ae64-01c524d19140");
  assert.equal(s.error, null);
});

test("summariseConversationStream ignores tool-authored delta messages", () => {
  // the only delta in the Pro fixture is authored by the `a8km123` tool
  const s = summariseConversationStream(parseSseFrames(PRO_HANDOFF_SSE));
  assert.equal(s.inlineText, "");
});

test("summariseConversationStream assembles inline assistant text", () => {
  const s = summariseConversationStream(parseSseFrames(INLINE_SSE));
  assert.equal(s.handoff, false);
  assert.equal(s.inlineText, "HTTP_OK");
});

/* ------------------------------------------------------------------ *
 * Answer extraction
 * ------------------------------------------------------------------ */

test("extractFinalAnswer returns the answer, not the reasoning recap", () => {
  const answer = extractFinalAnswer(CONVERSATION_PAYLOAD);
  assert.equal(answer.text, "HTTP_OK");
  assert.equal(answer.messageId, "a1");
  assert.equal(answer.modelSlug, "gpt-5-6-pro");
});

test("extractFinalAnswer skips tool authors", () => {
  const answer = extractFinalAnswer(CONVERSATION_PAYLOAD);
  assert.notEqual(answer.messageId, "t1");
});

test("extractFinalAnswer honours afterCreateTime so stale turns are ignored", () => {
  assert.equal(extractFinalAnswer(CONVERSATION_PAYLOAD, { afterCreateTime: 5000 }), null);
  assert.ok(extractFinalAnswer(CONVERSATION_PAYLOAD, { afterCreateTime: 1003 }));
});

test("extractFinalAnswer returns null while the turn is still streaming", () => {
  const inflight = structuredClone(CONVERSATION_PAYLOAD);
  inflight.mapping.a1.message.status = "in_progress";
  inflight.mapping.a1.message.end_turn = null;
  assert.equal(extractFinalAnswer(inflight), null);
});

test("extractFinalAnswer rejects a payload without a mapping", () => {
  assert.throws(
    () => extractFinalAnswer({}),
    (e) => e instanceof OracleHttpError && e.code === "conversation_invalid",
  );
});

/* ------------------------------------------------------------------ *
 * Request body
 * ------------------------------------------------------------------ */

test("buildConversationBody puts the model in the JSON body", () => {
  const body = buildConversationBody(
    { conversation_id: CONVERSATION_ID, parent_message_id: "p1", model: "gpt-5-5", thinking_effort: "standard" },
    { prompt: "hi", model: "gpt-5-6-pro" },
  );
  assert.equal(body.model, "gpt-5-6-pro");
  assert.equal(body.action, "next");
  assert.equal(body.conversation_id, CONVERSATION_ID);
  assert.equal(body.parent_message_id, "p1");
  assert.equal(body.thinking_effort, "standard");
});

test("projectIdFromUrl accepts a project URL, a bare id, and rejects junk", () => {
  assert.equal(
    projectIdFromUrl("https://chatgpt.com/g/g-p-000000000test01/project"),
    "g-p-000000000test01",
  );
  assert.equal(projectIdFromUrl("https://chatgpt.com/c/abc"), null);
  assert.equal(projectIdFromUrl(""), null);
  assert.equal(projectIdFromUrl(undefined), null);
});

test("a projectId binds the turn to the Project via conversation_mode", () => {
  const body = buildConversationBody(
    { conversation_mode: { kind: "primary_assistant" } },
    {
      prompt: "hi",
      model: "gpt-5-5-instant",
      parentMessageId: "root",
      projectId: "g-p-000000000test01",
    },
  );
  assert.deepEqual(body.conversation_mode, {
    kind: "gizmo_interaction",
    gizmo_id: "g-p-000000000test01",
  });
});

test("a projectId never inherits a drifted tab's conversation_id", () => {
  // Harvesting from a /c/ tab leaves conversation_id in the template. Carrying
  // it would append to that chat instead of starting one in the Project.
  const body = buildConversationBody(
    { conversation_id: "stale-conversation", conversation_mode: { kind: "primary_assistant" } },
    { prompt: "hi", model: "gpt-5-5-instant", parentMessageId: "root", projectId: "g-p-x1234567" },
  );
  assert.equal(body.conversation_id, undefined);
  assert.equal(body.conversation_mode.gizmo_id, "g-p-x1234567");
});

test("without a projectId the harvested conversation_mode is preserved", () => {
  const body = buildConversationBody(
    { conversation_mode: { kind: "primary_assistant" }, conversation_id: "keep-me" },
    { prompt: "hi", model: "gpt-5-6-pro", parentMessageId: "root" },
  );
  assert.deepEqual(body.conversation_mode, { kind: "primary_assistant" });
  assert.equal(body.conversation_id, "keep-me");
});

test("buildConversationBody produces one well-formed user message", () => {
  const body = buildConversationBody({}, { prompt: "hello", model: "gpt-5-6-pro", parentMessageId: "root" });
  assert.equal(body.messages.length, 1);
  const [m] = body.messages;
  assert.equal(m.author.role, "user");
  assert.equal(m.content.content_type, "text");
  assert.deepEqual(m.content.parts, ["hello"]);
  assert.match(m.id, /^[0-9a-f-]{36}$/);
  assert.equal(typeof m.create_time, "number");
});

test("buildConversationBody drops client_prepare_state from the template", () => {
  const body = buildConversationBody(
    { client_prepare_state: "success", parent_message_id: "p1" },
    { prompt: "x", model: "gpt-5-6-pro" },
  );
  assert.equal("client_prepare_state" in body, false);
});

test("buildConversationBody validates prompt and model", () => {
  assert.throws(
    () => buildConversationBody({}, { prompt: "", model: "gpt-5-6-pro" }),
    (e) => e.code === "prompt_invalid",
  );
  assert.throws(
    () => buildConversationBody({}, { prompt: "x", model: "" }),
    (e) => e.code === "model_invalid",
  );
});

/* ------------------------------------------------------------------ *
 * Sentinel bundle contract
 * ------------------------------------------------------------------ */

test("SENTINEL_HEADERS names the three required tokens", () => {
  assert.deepEqual([...SENTINEL_HEADERS], [
    "openai-sentinel-chat-requirements-token",
    "openai-sentinel-proof-token",
    "openai-sentinel-turnstile-token",
  ]);
});

test("assertSentinelBundle accepts a complete bundle", () => {
  assert.equal(assertSentinelBundle(SENTINEL_BUNDLE), true);
});

for (const header of SENTINEL_HEADERS) {
  test(`assertSentinelBundle rejects a bundle missing ${header}`, () => {
    const partial = { ...SENTINEL_BUNDLE };
    delete partial[header];
    assert.throws(
      () => assertSentinelBundle(partial),
      (e) => e.code === "sentinel_missing" && e.detail.includes(header),
    );
  });
}

test("assertSentinelBundle rejects a missing bearer", () => {
  const partial = { ...SENTINEL_BUNDLE, authorization: "Basic nope" };
  assert.throws(
    () => assertSentinelBundle(partial),
    (e) => e.code === "sentinel_missing" && e.detail === "authorization",
  );
});

/* ------------------------------------------------------------------ *
 * HTTP surface against stubbed transports
 * ------------------------------------------------------------------ */

test("postConversation sends the sentinel triple and the cookie jar", async () => {
  let seen = null;
  const fetchImpl = stubFetch((url, init) => {
    seen = { url, headers: init.headers, body: JSON.parse(init.body), method: init.method };
    return sseResponse(PRO_HANDOFF_SSE);
  });
  const out = await postConversation({
    body: buildConversationBody({ parent_message_id: "p1" }, { prompt: "hi", model: "gpt-5-6-pro" }),
    headers: SENTINEL_BUNDLE,
    cookieHeader: CREDS.cookieHeader,
    creds: CREDS,
    fetchImpl,
  });
  assert.equal(seen.method, "POST");
  assert.equal(seen.url, `${ORIGIN}${CONVERSATION_PATH}`);
  for (const h of SENTINEL_HEADERS) assert.equal(seen.headers[h], SENTINEL_BUNDLE[h]);
  assert.equal(seen.headers.cookie, CREDS.cookieHeader);
  assert.equal(seen.headers.origin, ORIGIN);
  assert.equal(seen.body.model, "gpt-5-6-pro");
  assert.equal(sseComplete(parseSseFrames(out.sse)), true);
});

test("postConversation maps the sentinel 403 to sentinel_rejected", async () => {
  const fetchImpl = stubFetch(() =>
    jsonResponse({ detail: "Unusual activity has been detected from your device. Try again later. (abc)" }, 403),
  );
  await assert.rejects(
    postConversation({
      body: { messages: [] },
      headers: SENTINEL_BUNDLE,
      cookieHeader: CREDS.cookieHeader,
      creds: CREDS,
      fetchImpl,
    }),
    (e) => e.code === "sentinel_rejected" && /Unusual activity/.test(e.detail),
  );
});

test("postConversation maps 401 to auth_expired", async () => {
  const fetchImpl = stubFetch(() => jsonResponse({ detail: "Unauthorized" }, 401));
  await assert.rejects(
    postConversation({
      body: { messages: [] },
      headers: SENTINEL_BUNDLE,
      cookieHeader: CREDS.cookieHeader,
      creds: CREDS,
      fetchImpl,
    }),
    (e) => e.code === "auth_expired",
  );
});

test("postConversation refuses to send without a sentinel bundle", async () => {
  let called = false;
  const fetchImpl = stubFetch(() => {
    called = true;
    return sseResponse("");
  });
  await assert.rejects(
    postConversation({
      body: { messages: [] },
      headers: { authorization: "Bearer x" },
      cookieHeader: CREDS.cookieHeader,
      creds: CREDS,
      fetchImpl,
    }),
    (e) => e.code === "sentinel_missing",
  );
  assert.equal(called, false, "no request may be sent without the anti-abuse tokens");
});

test("getConversation sends the bearer and account id", async () => {
  let seen = null;
  const fetchImpl = stubFetch((url, init) => {
    seen = { url, headers: init.headers };
    return jsonResponse(CONVERSATION_PAYLOAD);
  });
  const conv = await getConversation(CONVERSATION_ID, CREDS, { fetchImpl });
  assert.equal(seen.url, `${ORIGIN}/backend-api/conversation/${CONVERSATION_ID}`);
  assert.equal(seen.headers.authorization, `Bearer ${CREDS.accessToken}`);
  assert.equal(seen.headers["chatgpt-account-id"], CREDS.accountId);
  assert.equal(extractFinalAnswer(conv).text, "HTTP_OK");
});

test("getConversation maps 401 to auth_expired", async () => {
  const fetchImpl = stubFetch(() => jsonResponse({ detail: "Unauthorized" }, 401));
  await assert.rejects(
    getConversation(CONVERSATION_ID, CREDS, { fetchImpl }),
    (e) => e.code === "auth_expired",
  );
});

test("listModels returns Pro slugs from the catalogue", async () => {
  const fetchImpl = stubFetch(() =>
    jsonResponse({
      models: [
        { slug: "gpt-5-5", title: "GPT-5.5", max_tokens: 137000 },
        { slug: "gpt-5-6-pro", title: "GPT-5.6 Pro", max_tokens: 137000 },
        { slug: "research", title: "Deep Research", max_tokens: 137000 },
      ],
    }),
  );
  const models = await listModels(CREDS, { fetchImpl });
  assert.deepEqual(models.map((m) => m.slug), ["gpt-5-5", "gpt-5-6-pro", "research"]);
});

test("listModels surfaces a non-200 as models_failed", async () => {
  const fetchImpl = stubFetch(() => jsonResponse({}, 500));
  await assert.rejects(listModels(CREDS, { fetchImpl }), (e) => e.code === "models_failed");
});

/* ------------------------------------------------------------------ *
 * Secret hygiene + selector-freedom
 * ------------------------------------------------------------------ */

test("redact never emits a full secret", () => {
  const secret = "eyJhbGciOiJSUzI1NiIsImtpZCI6IlRFU1RLRVkifQ";
  const out = redact(secret);
  assert.equal(out, `eyJhbGci…[${secret.length}]`);
  assert.equal(out.includes(secret), false);
  assert.equal(redact(""), null);
  assert.equal(redact(undefined), null);
});

test("the mint interceptor matches only the submission endpoint, not /prepare", () => {
  const P = CONVERSATION_PATH;
  // The real submission, absolute and relative, with and without a query.
  assert.equal(isConversationEndpoint(`${ORIGIN}${P}`, ORIGIN, P), true);
  assert.equal(isConversationEndpoint(P, ORIGIN, P), true);
  assert.equal(isConversationEndpoint(`${P}?x=1`, ORIGIN, P), true);
  // The debounced composer-edit sibling. A substring test matches this and
  // captures a bundle with no sentinel headers at all — the failure that made
  // a live ask die with `sentinel_missing`.
  assert.equal(isConversationEndpoint(`${ORIGIN}${P}/prepare`, ORIGIN, P), false);
  assert.equal(isConversationEndpoint(`${P}/prepare`, ORIGIN, P), false);
  assert.equal(isConversationEndpoint(`${ORIGIN}${P}/init`, ORIGIN, P), false);
  // Unrelated and unparseable inputs.
  assert.equal(isConversationEndpoint("/backend-api/sentinel/ping", ORIGIN, P), false);
  assert.equal(isConversationEndpoint(undefined, ORIGIN, P), false);
});

test("the injected interceptor uses the exported predicate, not a substring test", async () => {
  const { readFile } = await import("node:fs/promises");
  const src = await readFile(new URL("../assets/scripts/oracle-http-client.mjs", import.meta.url), "utf8");
  assert.ok(src.includes("${isConversationEndpoint.toString()}"), "the page must run the tested predicate");
  assert.equal(src.includes("url.indexOf("), false, "substring endpoint matching must not return");
});

test("the client source contains no ChatGPT-specific selectors", async () => {
  const { readFile } = await import("node:fs/promises");
  const src = await readFile(new URL("../assets/scripts/oracle-http-client.mjs", import.meta.url), "utf8");
  const code = src
    .split("\n")
    .filter((line) => !/^\s*(\*|\/\/|\/\*)/.test(line))
    .join("\n");
  for (const banned of ["data-testid", "prompt-textarea", "#composer", "aria-label", "[role=", "querySelectorAll"]) {
    assert.equal(code.includes(banned), false, `client must not depend on ${banned}`);
  }
  // The single DOM touch is generic HTML, not a ChatGPT contract.
  assert.ok(code.includes('closest("form")'));
  assert.ok(code.includes("requestSubmit"));
  // Exactly one querySelector call exists, and it targets a generic
  // HTML submit button rather than any ChatGPT-specific hook.
  const selectorCalls = code.match(/querySelector\(/g) ?? [];
  assert.equal(selectorCalls.length, 1);
  assert.ok(code.includes(`querySelector("button[type='submit']:not([disabled])")`));
});
