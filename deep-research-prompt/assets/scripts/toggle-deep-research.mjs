#!/usr/bin/env node

import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import {
  bindExactChatGptTarget,
  ChatGptComposerError,
  createLoopbackCdpTransport,
} from "./chatgpt-composer.mjs";

const MESSAGE_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/;
const MAX_CONTROL_BYTES = 64 * 1024;

export class DeepResearchComposerError extends Error {
  constructor(code) {
    super("deep research composer: rejected");
    this.name = "DeepResearchComposerError";
    this.code = code;
  }
}

function reject(code) {
  throw new DeepResearchComposerError(code);
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

export async function deepResearchPageAction(action, payload) {
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
  const promptFields = Array.from(
    document.querySelectorAll(
      "#prompt-textarea[contenteditable='true'],[contenteditable='true'][role='textbox']",
    ),
  ).filter(visible);
  if (promptFields.length !== 1) {
    return { ok: false, code: "composer_ambiguous" };
  }
  const composer =
    promptFields[0].closest("[data-testid='composer']") ||
    promptFields[0].closest("form");
  if (!composer || !visible(composer)) {
    return { ok: false, code: "composer_ambiguous" };
  }
  const activeDeepResearchChips = () =>
    Array.from(
      composer.querySelectorAll(
        "[data-testid='composer-tool-chip'][data-tool='deep-research'],[data-tool='deep-research']",
      ),
    ).filter(
      (element) =>
        visible(element) &&
        (element.getAttribute("aria-pressed") === "true" ||
          ["active", "on"].includes(element.getAttribute("data-state"))),
    );
  const click = (element) => {
    element.scrollIntoView({ block: "center", inline: "center" });
    element.click();
  };

  if (action === "set-tool") {
    if (typeof payload?.enabled !== "boolean") {
      return { ok: false, code: "tool_request_invalid" };
    }
    const active = activeDeepResearchChips();
    if (active.length > 1) {
      return { ok: false, code: "tool_state_ambiguous" };
    }
    if (payload.enabled && active.length === 1) {
      return { ok: true, tool: "deep-research", enabled: true };
    }
    if (!payload.enabled && active.length === 0) {
      return { ok: true, tool: "none", enabled: true };
    }
    if (!payload.enabled) {
      if (!enabled(active[0])) {
        return { ok: false, code: "tool_control_disabled" };
      }
      click(active[0]);
      await sleep(100);
      if (activeDeepResearchChips().length !== 0) {
        return { ok: false, code: "tool_verification_failed" };
      }
      return { ok: true, tool: "none", enabled: true };
    }

    const toolButtons = Array.from(
      composer.querySelectorAll("[data-testid='composer-plus-btn']"),
    ).filter((element) => visible(element) && enabled(element));
    if (toolButtons.length !== 1) {
      return { ok: false, code: "tool_button_ambiguous" };
    }
    click(toolButtons[0]);
    await sleep(100);
    const menuRoots = Array.from(
      document.querySelectorAll(
        "[role='menu'],[role='listbox'],[data-radix-menu-content]",
      ),
    ).filter(visible);
    const options = menuRoots.flatMap((root) =>
      Array.from(
        root.querySelectorAll(
          "[role='menuitem'][data-tool='deep-research'],[role='option'][data-tool='deep-research']",
        ),
      ).filter((element) => visible(element) && enabled(element)),
    );
    if (options.length !== 1) {
      return { ok: false, code: "tool_option_ambiguous" };
    }
    click(options[0]);
    await sleep(100);
    if (activeDeepResearchChips().length !== 1) {
      return { ok: false, code: "tool_verification_failed" };
    }
    return { ok: true, tool: "deep-research", enabled: true };
  }

  if (action === "start-review") {
    const userMessageId = payload?.user_message_id;
    if (
      typeof userMessageId !== "string" ||
      !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/.test(userMessageId)
    ) {
      return { ok: false, code: "user_message_invalid" };
    }
    const cards = Array.from(
      document.querySelectorAll(
        "[data-testid='deep-research-review-card'][data-parent-message-id][data-review-id]",
      ),
    ).filter(
      (element) =>
        visible(element) &&
        element.getAttribute("data-parent-message-id") === userMessageId &&
        element.getAttribute("data-state") === "awaiting-start",
    );
    if (cards.length !== 1) {
      return { ok: false, code: "review_card_ambiguous" };
    }
    const buttons = Array.from(
      cards[0].querySelectorAll(
        "[data-testid='deep-research-start-button']",
      ),
    ).filter((element) => visible(element) && enabled(element));
    if (buttons.length !== 1) {
      return { ok: false, code: "review_start_ambiguous" };
    }
    const reviewId = cards[0].getAttribute("data-review-id");
    if (
      typeof reviewId !== "string" ||
      !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/.test(reviewId)
    ) {
      return { ok: false, code: "review_id_invalid" };
    }
    click(buttons[0]);
    await sleep(100);
    return {
      ok: true,
      review_id: reviewId,
      parent_user_message_id: userMessageId,
      started: true,
    };
  }

  return { ok: false, code: "action_invalid" };
}

export function deepResearchPageActionDeclaration() {
  return deepResearchPageAction.toString();
}

export async function runDeepResearchAction(
  transport,
  rawTarget,
  action,
  payload,
) {
  const target = await bindExactChatGptTarget(transport, rawTarget);
  if (!["set-tool", "start-review"].includes(action)) {
    reject("action_invalid");
  }
  if (
    action === "set-tool" &&
    (!isPlainObject(payload) || typeof payload.enabled !== "boolean")
  ) {
    reject("tool_request_invalid");
  }
  if (
    action === "start-review" &&
    (!isPlainObject(payload) ||
      typeof payload.user_message_id !== "string" ||
      !MESSAGE_ID_PATTERN.test(payload.user_message_id))
  ) {
    reject("user_message_invalid");
  }
  let result;
  try {
    const pagePayload = {
      ...payload,
      expected_target_url: target.target_url,
    };
    result = await transport.invoke(
      target.target_id,
      deepResearchPageActionDeclaration(),
      [action, pagePayload],
    );
  } catch (error) {
    if (
      error instanceof DeepResearchComposerError ||
      error instanceof ChatGptComposerError
    ) {
      throw error;
    }
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

async function readStdin() {
  const chunks = [];
  let bytes = 0;
  for await (const chunk of process.stdin) {
    bytes += chunk.length;
    if (bytes > MAX_CONTROL_BYTES) reject("control_invalid");
    chunks.push(chunk);
  }
  if (bytes === 0) reject("control_invalid");
  return Buffer.concat(chunks).toString("utf8");
}

export async function main(rawArguments = process.argv.slice(2)) {
  if (
    rawArguments.length !== 1 ||
    rawArguments[0] !== "--control-stdin"
  ) {
    reject("arguments_invalid");
  }
  let control;
  try {
    control = JSON.parse(await readStdin());
  } catch (error) {
    if (error instanceof DeepResearchComposerError) throw error;
    reject("control_invalid");
  }
  exactObject(
    control,
    ["endpoint", "target_id", "target_url", "action"],
    ["enabled", "user_message_id"],
    "control_invalid",
  );
  if (control.action === "start-review") {
    reject("adapter_required");
  }
  const transport = createLoopbackCdpTransport(control.endpoint);
  const payload =
    control.action === "set-tool"
      ? { enabled: control.enabled }
      : { user_message_id: control.user_message_id };
  const result = await runDeepResearchAction(
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
      error instanceof DeepResearchComposerError ||
      error instanceof ChatGptComposerError
        ? error.code
        : "unexpected_failure";
    process.stderr.write(`toggle-deep-research:${code}\n`);
    process.exitCode = 1;
  });
}
