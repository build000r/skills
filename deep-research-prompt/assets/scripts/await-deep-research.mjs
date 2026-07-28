#!/usr/bin/env node

import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import {
  bindExactChatGptTarget,
  ChatGptComposerError,
  normalizeExactChatGptUrl,
  normalizeExactTarget,
} from "./chatgpt-composer.mjs";

export const CONVERSATION_OBSERVATION_SCHEMA =
  "oracle-subagent.conversation-observation.v1";
export const EMPTY_ROOT_BASELINE_TURN_ID =
  "baseline:empty-root:no-assistant";
export const EMPTY_ROOT_BASELINE_TURN_POSITION = 0;

const TARGET_ID_PATTERN = /^[A-Fa-f0-9]{16,128}$/;
const MESSAGE_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/;
const CONVERSATION_PATH_PATTERN =
  /^\/c\/[A-Za-z0-9][A-Za-z0-9_-]{0,255}$/;
const CHATGPT_ROOT_URL = "https://chatgpt.com/";
const MAX_RESULT_CHARACTERS = 16 * 1024 * 1024;

export class OracleConversationError extends Error {
  constructor(code) {
    super("oracle conversation: rejected");
    this.name = "OracleConversationError";
    this.code = code;
  }
}

function reject(code) {
  throw new OracleConversationError(code);
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

function identifier(value, code) {
  if (typeof value !== "string" || !MESSAGE_ID_PATTERN.test(value)) {
    reject(code);
  }
  return value;
}

function position(value, code) {
  if (!Number.isSafeInteger(value) || value < 1) reject(code);
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

export function conversationPageProbe(targetId) {
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
  const safeId = (value) =>
    /^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/.test(String(value || ""))
      ? String(value)
      : null;
  const mainRoots = Array.from(document.querySelectorAll("main")).filter(
    visible,
  );
  const root = mainRoots.length === 1 ? mainRoots[0] : null;
  const messageNodes = root
    ? Array.from(
        root.querySelectorAll(
          "[data-message-author-role='user'][data-message-id],[data-message-author-role='assistant'][data-message-id]",
        ),
      ).filter(visible)
    : [];
  const turns = messageNodes.map((node, index) => {
    const role = node.getAttribute("data-message-author-role");
    const rawId = safeId(node.getAttribute("data-message-id"));
    const basePosition = (index + 1) * 10;
    let status = role === "user" ? "submitted" : "ambiguous";
    if (role === "assistant") {
      const explicit = node.getAttribute("data-message-status");
      const streaming = Array.from(
        node.querySelectorAll("[data-testid='message-streaming-indicator']"),
      ).filter(visible);
      const completed = Array.from(
        node.querySelectorAll("[data-testid='message-complete']"),
      ).filter(visible);
      if (
        ["streaming", "completed", "error"].includes(explicit) &&
        streaming.length <= 1 &&
        completed.length <= 1
      ) {
        status = explicit;
      } else if (streaming.length === 1 && completed.length === 0) {
        status = "streaming";
      } else if (completed.length === 1 && streaming.length === 0) {
        status = "completed";
      }
    }
    const contentNodes =
      role === "assistant"
        ? Array.from(node.querySelectorAll("[data-message-content]")).filter(
            visible,
          )
        : [];
    const content =
      contentNodes.length === 1
        ? String(contentNodes[0].innerText || contentNodes[0].textContent || "")
            .replace(/[ \t]+\n/g, "\n")
            .replace(/\n[ \t]+/g, "\n")
            .replace(/\n{3,}/g, "\n\n")
            .trim()
        : "";
    return {
      raw_id: rawId,
      role,
      position: basePosition,
      status,
      content,
    };
  });
  const turnByRawId = new Map(
    turns.filter((turn) => turn.raw_id).map((turn) => [turn.raw_id, turn]),
  );
  const reviewCards = root
    ? Array.from(
        root.querySelectorAll(
          "[data-testid='deep-research-review-card'][data-parent-message-id][data-review-id]",
        ),
      )
        .filter(visible)
        .map((card) => ({
          review_id: safeId(card.getAttribute("data-review-id")),
          parent_user_message_id: safeId(
            card.getAttribute("data-parent-message-id"),
          ),
          state: card.getAttribute("data-state") || "",
        }))
    : [];
  const activeResearch = root
    ? Array.from(
        root.querySelectorAll(
          "[data-testid='deep-research-progress'][data-state='active'][data-parent-message-id][data-research-id]",
        ),
      )
        .filter(visible)
        .map((element) => {
          const message = element.closest(
            "[data-message-author-role='assistant'][data-message-id]",
          );
          const turn = turnByRawId.get(
            message?.getAttribute("data-message-id"),
          );
          return {
            research_id: safeId(element.getAttribute("data-research-id")),
            parent_user_message_id: safeId(
              element.getAttribute("data-parent-message-id"),
            ),
            assistant_message_id: turn?.raw_id || null,
            position: turn?.position || 0,
          };
        })
    : [];
  const dossiers = root
    ? Array.from(
        root.querySelectorAll(
          "[data-testid='deep-research-dossier'][data-state='completed'][data-parent-message-id][data-research-id][data-dossier-id]",
        ),
      )
        .filter(visible)
        .map((element) => {
          const message = element.closest(
            "[data-message-author-role='assistant'][data-message-id]",
          );
          const turn = turnByRawId.get(
            message?.getAttribute("data-message-id"),
          );
          const content = String(
            element.innerText || element.textContent || "",
          )
            .replace(/[ \t]+\n/g, "\n")
            .replace(/\n[ \t]+/g, "\n")
            .replace(/\n{3,}/g, "\n\n")
            .trim();
          return {
            dossier_id: safeId(element.getAttribute("data-dossier-id")),
            research_id: safeId(element.getAttribute("data-research-id")),
            parent_user_message_id: safeId(
              element.getAttribute("data-parent-message-id"),
            ),
            assistant_message_id: turn?.raw_id || null,
            position: turn?.position || 0,
            content,
          };
        })
    : [];
  return {
    schema: "oracle-subagent.conversation-observation.v1",
    observed_at: new Date().toISOString(),
    target_id: targetId,
    target_url: location.href,
    main_count: mainRoots.length,
    turns,
    review_cards: reviewCards,
    active_research: activeResearch,
    dossiers,
  };
}

export function conversationPageProbeExpression(targetId) {
  if (
    typeof targetId !== "string" ||
    !TARGET_ID_PATTERN.test(targetId)
  ) {
    reject("target_invalid");
  }
  return `(${conversationPageProbe})(${JSON.stringify(targetId)})`;
}

function normalizeTurn(rawTurn) {
  exactObject(
    rawTurn,
    ["raw_id", "role", "position", "status", "content"],
    [],
    "observation_invalid",
  );
  if (
    !["user", "assistant"].includes(rawTurn.role) ||
    !["submitted", "streaming", "completed", "error", "ambiguous"].includes(
      rawTurn.status,
    ) ||
    typeof rawTurn.content !== "string" ||
    rawTurn.content.length > MAX_RESULT_CHARACTERS
  ) {
    reject("observation_invalid");
  }
  return {
    raw_id: identifier(rawTurn.raw_id, "observation_invalid"),
    role: rawTurn.role,
    position: position(rawTurn.position, "observation_invalid"),
    status: rawTurn.status,
    content: rawTurn.content,
  };
}

function normalizeReview(rawReview) {
  exactObject(
    rawReview,
    ["review_id", "parent_user_message_id", "state"],
    [],
    "observation_invalid",
  );
  if (!["awaiting-start", "started"].includes(rawReview.state)) {
    reject("observation_invalid");
  }
  return {
    review_id: identifier(rawReview.review_id, "observation_invalid"),
    parent_user_message_id: identifier(
      rawReview.parent_user_message_id,
      "observation_invalid",
    ),
    state: rawReview.state,
  };
}

function normalizeActive(rawActive) {
  exactObject(
    rawActive,
    [
      "research_id",
      "parent_user_message_id",
      "assistant_message_id",
      "position",
    ],
    [],
    "observation_invalid",
  );
  return {
    research_id: identifier(rawActive.research_id, "observation_invalid"),
    parent_user_message_id: identifier(
      rawActive.parent_user_message_id,
      "observation_invalid",
    ),
    assistant_message_id: identifier(
      rawActive.assistant_message_id,
      "observation_invalid",
    ),
    position: position(rawActive.position, "observation_invalid"),
  };
}

function normalizeDossier(rawDossier) {
  exactObject(
    rawDossier,
    [
      "dossier_id",
      "research_id",
      "parent_user_message_id",
      "assistant_message_id",
      "position",
      "content",
    ],
    [],
    "observation_invalid",
  );
  if (
    typeof rawDossier.content !== "string" ||
    rawDossier.content.length > MAX_RESULT_CHARACTERS
  ) {
    reject("observation_invalid");
  }
  return {
    dossier_id: identifier(rawDossier.dossier_id, "observation_invalid"),
    research_id: identifier(
      rawDossier.research_id,
      "observation_invalid",
    ),
    parent_user_message_id: identifier(
      rawDossier.parent_user_message_id,
      "observation_invalid",
    ),
    assistant_message_id: identifier(
      rawDossier.assistant_message_id,
      "observation_invalid",
    ),
    position: position(rawDossier.position, "observation_invalid"),
    content: rawDossier.content,
  };
}

export function normalizeConversationObservation(rawObservation, expected) {
  exactObject(
    rawObservation,
    [
      "schema",
      "observed_at",
      "target_id",
      "target_url",
      "main_count",
      "turns",
      "review_cards",
      "active_research",
      "dossiers",
    ],
    [],
    "observation_invalid",
  );
  const target = normalizeExactTarget(expected);
  if (
    rawObservation.schema !== CONVERSATION_OBSERVATION_SCHEMA ||
    rawObservation.target_id !== target.target_id ||
    normalizeExactChatGptUrl(rawObservation.target_url) !==
      target.target_url ||
    rawObservation.main_count !== 1 ||
    !Array.isArray(rawObservation.turns) ||
    !Array.isArray(rawObservation.review_cards) ||
    !Array.isArray(rawObservation.active_research) ||
    !Array.isArray(rawObservation.dossiers)
  ) {
    reject("observation_invalid");
  }
  canonicalTimestamp(rawObservation.observed_at, "observation_invalid");
  const turns = rawObservation.turns.map(normalizeTurn);
  if (
    new Set(turns.map((turn) => turn.raw_id)).size !== turns.length ||
    turns.some(
      (turn, index) =>
        index > 0 && turn.position <= turns[index - 1].position,
    )
  ) {
    reject("observation_invalid");
  }
  return Object.freeze({
    schema: CONVERSATION_OBSERVATION_SCHEMA,
    observed_at: rawObservation.observed_at,
    target_id: target.target_id,
    target_url: target.target_url,
    turns,
    review_cards: rawObservation.review_cards.map(normalizeReview),
    active_research: rawObservation.active_research.map(normalizeActive),
    dossiers: rawObservation.dossiers.map(normalizeDossier),
  });
}

export async function probeConversation(transport, rawTarget) {
  const target = await bindExactChatGptTarget(transport, rawTarget);
  let rawObservation;
  try {
    rawObservation = await transport.evaluate(
      target.target_id,
      conversationPageProbeExpression(target.target_id),
    );
  } catch (error) {
    if (
      error instanceof OracleConversationError ||
      error instanceof ChatGptComposerError
    ) {
      throw error;
    }
    reject("probe_failed");
  }
  return normalizeConversationObservation(rawObservation, target);
}

export function captureConversationBaseline(observation) {
  if (
    !isPlainObject(observation) ||
    observation.schema !== CONVERSATION_OBSERVATION_SCHEMA ||
    !Array.isArray(observation.turns)
  ) {
    reject("baseline_invalid");
  }
  const turns = observation.turns;
  const last = turns.at(-1);
  let targetUrl;
  try {
    targetUrl = normalizeExactChatGptUrl(observation.target_url);
  } catch {
    reject("baseline_invalid");
  }
  if (turns.length === 0 && targetUrl === CHATGPT_ROOT_URL) {
    return Object.freeze({
      target_id: observation.target_id,
      target_url: targetUrl,
      turns: [],
      baseline_assistant_turn_id: EMPTY_ROOT_BASELINE_TURN_ID,
      baseline_assistant_turn_position:
        EMPTY_ROOT_BASELINE_TURN_POSITION,
    });
  }
  if (
    !last ||
    last.role !== "assistant" ||
    last.status !== "completed" ||
    !last.content
  ) {
    reject("baseline_missing");
  }
  return Object.freeze({
    target_id: observation.target_id,
    target_url: targetUrl,
    turns: turns.map(({ raw_id, role, position }) => ({
      raw_id,
      role,
      position,
    })),
    baseline_assistant_turn_id: `assistant:${last.raw_id}:completed`,
    baseline_assistant_turn_position: last.position + 1,
  });
}

export function proveCausalConversationUrl(
  preSendUrl,
  observedUrl,
) {
  let before;
  let after;
  try {
    before = normalizeExactChatGptUrl(preSendUrl);
    after = normalizeExactChatGptUrl(observedUrl);
  } catch {
    reject("target_url_drift");
  }
  if (after === before) return after;
  const beforePath = new URL(before).pathname;
  const afterPath = new URL(after).pathname;
  if (
    beforePath !== "/" ||
    !CONVERSATION_PATH_PATTERN.test(afterPath)
  ) {
    reject("target_url_drift");
  }
  return after;
}

function assertBaselinePrefix(baseline, observation) {
  const observedUrl = proveCausalConversationUrl(
    baseline.target_url,
    observation.target_url,
  );
  if (
    baseline.target_id !== observation.target_id ||
    baseline.turns.length > observation.turns.length
  ) {
    reject("thread_mismatch");
  }
  for (const [index, expected] of baseline.turns.entries()) {
    const actual = observation.turns[index];
    if (
      !actual ||
      actual.raw_id !== expected.raw_id ||
      actual.role !== expected.role ||
      actual.position !== expected.position
    ) {
      reject("thread_mismatch");
    }
  }
  return observedUrl;
}

export function proveSubmittedUserTurn(baseline, observation) {
  const observedUrl = assertBaselinePrefix(baseline, observation);
  const additions = observation.turns.slice(baseline.turns.length);
  if (
    additions.length === 0 ||
    (new URL(baseline.target_url).pathname === "/" &&
      observedUrl === baseline.target_url)
  ) {
    reject("evidence_pending");
  }
  const users = additions.filter((turn) => turn.role === "user");
  if (
    additions[0]?.role !== "user" ||
    users.length !== 1 ||
    users[0].status !== "submitted" ||
    users[0].position <= baseline.baseline_assistant_turn_position
  ) {
    reject("submitted_turn_invalid");
  }
  return Object.freeze({
    conversation_url: observation.target_url,
    raw_user_message_id: users[0].raw_id,
    user_turn_id: `user:${users[0].raw_id}:submitted`,
    user_turn_position: users[0].position,
  });
}

function assertSubmittedThread(observation, submitted) {
  const matchingUsers = observation.turns.filter(
    (turn) =>
      turn.role === "user" && turn.raw_id === submitted.raw_user_message_id,
  );
  const laterUsers = observation.turns.filter(
    (turn) =>
      turn.role === "user" &&
      turn.position >= submitted.user_turn_position,
  );
  if (
    observation.target_url !== submitted.conversation_url ||
    matchingUsers.length !== 1 ||
    laterUsers.length !== 1
  ) {
    reject("thread_mismatch");
  }
}

export function proveProStarted(observation, submitted) {
  assertSubmittedThread(observation, submitted);
  const assistants = observation.turns.filter(
    (turn) =>
      turn.role === "assistant" &&
      turn.position > submitted.user_turn_position,
  );
  if (
    assistants.length !== 1 ||
    !["streaming", "completed"].includes(assistants[0].status)
  ) {
    reject("evidence_pending");
  }
  return Object.freeze({
    assistant_signal_id: `assistant:${assistants[0].raw_id}:started`,
    assistant_signal_position: assistants[0].position,
    raw_assistant_message_id: assistants[0].raw_id,
  });
}

export function proveProCompleted(observation, submitted, started) {
  assertSubmittedThread(observation, submitted);
  const assistants = observation.turns.filter(
    (turn) =>
      turn.role === "assistant" &&
      turn.position > submitted.user_turn_position,
  );
  if (
    assistants.length !== 1 ||
    assistants[0].status !== "completed" ||
    assistants[0].content.length === 0
  ) {
    reject("evidence_pending");
  }
  if (
    assistants[0].raw_id !== started.raw_assistant_message_id
  ) {
    reject("assistant_identity_mismatch");
  }
  const finalPosition = assistants[0].position + 1;
  if (finalPosition <= started.assistant_signal_position) {
    reject("completion_invalid");
  }
  if (assistants[0].position !== started.assistant_signal_position) {
    reject("completion_invalid");
  }
  return Object.freeze({
    final_assistant_turn_id: `assistant:${assistants[0].raw_id}:completed`,
    final_assistant_turn_position: finalPosition,
    content: assistants[0].content,
  });
}

export function proveDeepResearchReview(observation, submitted) {
  assertSubmittedThread(observation, submitted);
  const matches = observation.review_cards.filter(
    (card) =>
      card.parent_user_message_id === submitted.raw_user_message_id &&
      card.state === "awaiting-start",
  );
  if (matches.length !== 1) reject("evidence_pending");
  return Object.freeze({
    review_id: matches[0].review_id,
    parent_user_message_id: matches[0].parent_user_message_id,
    review_position: submitted.user_turn_position + 1,
  });
}

export function proveDeepResearchStarted(observation, submitted, review) {
  assertSubmittedThread(observation, submitted);
  const matches = observation.active_research.filter(
    (active) =>
      active.parent_user_message_id === submitted.raw_user_message_id &&
      active.position > review.review_position,
  );
  if (matches.length !== 1) reject("evidence_pending");
  const assistants = observation.turns.filter(
    (turn) =>
      turn.role === "assistant" &&
      turn.raw_id === matches[0].assistant_message_id &&
      turn.position === matches[0].position &&
      ["streaming", "completed"].includes(turn.status),
  );
  if (assistants.length !== 1) reject("evidence_pending");
  return Object.freeze({
    assistant_signal_id: `research:${matches[0].research_id}:active`,
    assistant_signal_position: matches[0].position,
    raw_research_id: matches[0].research_id,
    raw_assistant_message_id: matches[0].assistant_message_id,
  });
}

export function proveDeepResearchCompleted(
  observation,
  submitted,
  started,
) {
  assertSubmittedThread(observation, submitted);
  const matches = observation.dossiers.filter(
    (dossier) =>
      dossier.parent_user_message_id === submitted.raw_user_message_id &&
      dossier.content.length > 0,
  );
  if (matches.length !== 1) reject("evidence_pending");
  if (matches[0].research_id !== started.raw_research_id) {
    reject("research_identity_mismatch");
  }
  if (
    matches[0].assistant_message_id !==
      started.raw_assistant_message_id
  ) {
    reject("assistant_identity_mismatch");
  }
  const assistants = observation.turns.filter(
    (turn) =>
      turn.role === "assistant" &&
      turn.raw_id === matches[0].assistant_message_id &&
      turn.position === matches[0].position &&
      turn.status === "completed",
  );
  if (assistants.length !== 1) reject("evidence_pending");
  const finalPosition = matches[0].position + 1;
  if (finalPosition <= started.assistant_signal_position) {
    reject("completion_invalid");
  }
  if (matches[0].position !== started.assistant_signal_position) {
    reject("completion_invalid");
  }
  return Object.freeze({
    final_assistant_turn_id: `dossier:${matches[0].dossier_id}:completed`,
    final_assistant_turn_position: finalPosition,
    content: matches[0].content,
  });
}

export async function waitForConversationEvidence({
  probe,
  prove,
  sleep,
  poll_interval_ms = 1_000,
  max_polls = 120,
}) {
  if (
    typeof probe !== "function" ||
    typeof prove !== "function" ||
    typeof sleep !== "function" ||
    !Number.isSafeInteger(poll_interval_ms) ||
    poll_interval_ms < 0 ||
    !Number.isSafeInteger(max_polls) ||
    max_polls < 1 ||
    max_polls > 10_000
  ) {
    reject("wait_options_invalid");
  }
  for (let poll = 0; poll < max_polls; poll += 1) {
    const observation = await probe();
    try {
      return await prove(observation);
    } catch (error) {
      if (
        !(error instanceof OracleConversationError) ||
        error.code !== "evidence_pending"
      ) {
        throw error;
      }
    }
    if (poll + 1 < max_polls) await sleep(poll_interval_ms);
  }
  reject("evidence_timeout");
}

export async function main(rawArguments = process.argv.slice(2)) {
  if (
    rawArguments.length !== 1 ||
    rawArguments[0] !== "--control-stdin"
  ) {
    reject("arguments_invalid");
  }
  reject("adapter_required");
}

const invokedPath = process.argv[1]
  ? pathToFileURL(resolve(process.argv[1])).href
  : "";
if (invokedPath === import.meta.url) {
  main().catch((error) => {
    const code =
      error instanceof OracleConversationError ||
      error instanceof ChatGptComposerError
        ? error.code
        : "unexpected_failure";
    process.stderr.write(`await-deep-research:${code}\n`);
    process.exitCode = 1;
  });
}
