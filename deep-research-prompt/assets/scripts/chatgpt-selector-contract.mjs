// Exact, observation-only ChatGPT composer selector contract.
//
// The page probe reads only a minimal set of composer attributes plus the
// same-origin model catalog. The verifier fails closed unless one exact CDP
// target has one visible composer, one selected Pro control, one canonical
// available gpt-*-pro model, and the mode's exact active tool state.

import { canonicalProCapability } from "./oracle-subagent-auth.mjs";

export const SELECTOR_OBSERVATION_SCHEMA =
  "oracle-subagent.selector-observation.v1";
export const SELECTOR_PROOF_SCHEMA = "oracle-subagent.selector-proof.v1";

const TARGET_ID_PATTERN = /^[A-Fa-f0-9]{16,128}$/;
const PRO_MODEL_PATTERN =
  /^gpt-[a-z0-9]+(?:[.-][a-z0-9]+)*-pro$/;
const MODEL_ID_PATTERN = /^gpt-[a-z0-9]+(?:[.-][a-z0-9]+)*$/;
const MODES = new Set(["pro", "deep-research"]);
const MODEL_SELECTIONS = new Set([
  "pro",
  "instant",
  "thinking",
  "auto",
  "ambiguous",
]);
const TOOL_SELECTIONS = new Set(["none", "deep-research", "ambiguous"]);

class SelectorContractError extends Error {
  constructor(code) {
    super("chatgpt selector contract: rejected");
    this.name = "SelectorContractError";
    this.code = code;
  }
}

function reject(code) {
  throw new SelectorContractError(code);
}

function isPlainObject(value) {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.getPrototypeOf(value) === Object.prototype
  );
}

function exactObject(value, keys, code) {
  if (
    !isPlainObject(value) ||
    Object.keys(value).length !== keys.length ||
    keys.some((key) => !Object.hasOwn(value, key))
  ) {
    reject(code);
  }
  return value;
}

function parseTimestamp(value) {
  if (typeof value !== "string") reject("observation_invalid");
  const milliseconds = Date.parse(value);
  if (
    !Number.isFinite(milliseconds) ||
    new Date(milliseconds).toISOString() !== value
  ) {
    reject("observation_invalid");
  }
  return milliseconds;
}

function normalizeTargetUrl(value) {
  if (typeof value !== "string") reject("observation_invalid");
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    reject("observation_invalid");
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
    reject("observation_invalid");
  }
  return parsed.href;
}

function positiveCount(value) {
  return Number.isSafeInteger(value) && value >= 0 && value <= 100;
}

function normalizeObservation(value) {
  exactObject(
    value,
    [
      "schema",
      "observed_at",
      "target_id",
      "target_url",
      "composer_count",
      "composer_visible",
      "prompt_field_count",
      "model_control_count",
      "model_control_enabled",
      "model_machine_id",
      "model_selection",
      "catalog_pro_model_ids",
      "active_tool_count",
      "active_tools_enabled",
      "tool_selection",
    ],
    "observation_invalid",
  );
  if (
    value.schema !== SELECTOR_OBSERVATION_SCHEMA ||
    typeof value.target_id !== "string" ||
    !TARGET_ID_PATTERN.test(value.target_id) ||
    !positiveCount(value.composer_count) ||
    typeof value.composer_visible !== "boolean" ||
    !positiveCount(value.prompt_field_count) ||
    !positiveCount(value.model_control_count) ||
    typeof value.model_control_enabled !== "boolean" ||
    (value.model_machine_id !== null &&
      (typeof value.model_machine_id !== "string" ||
        !MODEL_ID_PATTERN.test(value.model_machine_id))) ||
    !MODEL_SELECTIONS.has(value.model_selection) ||
    !Array.isArray(value.catalog_pro_model_ids) ||
    value.catalog_pro_model_ids.some(
      (identifier) =>
        typeof identifier !== "string" ||
        !PRO_MODEL_PATTERN.test(identifier),
    ) ||
    new Set(value.catalog_pro_model_ids).size !==
      value.catalog_pro_model_ids.length ||
    !positiveCount(value.active_tool_count) ||
    typeof value.active_tools_enabled !== "boolean" ||
    !TOOL_SELECTIONS.has(value.tool_selection)
  ) {
    reject("observation_invalid");
  }
  const sortedModels = [...value.catalog_pro_model_ids].sort();
  if (
    sortedModels.some(
      (identifier, index) => identifier !== value.catalog_pro_model_ids[index],
    )
  ) {
    reject("observation_invalid");
  }
  return {
    ...structuredClone(value),
    target_url: normalizeTargetUrl(value.target_url),
    observed_at_ms: parseTimestamp(value.observed_at),
  };
}

export function proveSelectorObservation(
  rawObservation,
  {
    target_id,
    target_url,
    mode,
    model,
    now = new Date().toISOString(),
    max_age_ms = 10_000,
  },
) {
  const observation = normalizeObservation(rawObservation);
  if (
    typeof target_id !== "string" ||
    !TARGET_ID_PATTERN.test(target_id) ||
    !MODES.has(mode) ||
    typeof model !== "string" ||
    !PRO_MODEL_PATTERN.test(model) ||
    !Number.isSafeInteger(max_age_ms) ||
    max_age_ms < 1
  ) {
    reject("request_invalid");
  }
  const expectedUrl = normalizeTargetUrl(target_url);
  const nowMs = parseTimestamp(now);
  const age = nowMs - observation.observed_at_ms;
  if (age < -2_000 || age > max_age_ms) reject("observation_stale");
  if (
    observation.target_id !== target_id ||
    observation.target_url !== expectedUrl
  ) {
    reject("target_mismatch");
  }
  if (
    observation.composer_count !== 1 ||
    observation.composer_visible !== true ||
    observation.prompt_field_count !== 1
  ) {
    reject("composer_ambiguous");
  }
  if (
    observation.model_control_count !== 1 ||
    observation.model_control_enabled !== true ||
    observation.model_selection !== "pro"
  ) {
    reject("model_not_pro");
  }
  if (
    observation.catalog_pro_model_ids.length !== 1 ||
    observation.catalog_pro_model_ids[0] !== model
  ) {
    reject("model_catalog_ambiguous");
  }
  if (
    observation.model_machine_id !== null &&
    observation.model_machine_id !== model
  ) {
    reject("model_machine_mismatch");
  }
  const expectedTool = mode === "deep-research" ? "deep-research" : "none";
  const expectedToolCount = mode === "deep-research" ? 1 : 0;
  if (
    observation.active_tool_count !== expectedToolCount ||
    observation.active_tools_enabled !== true ||
    observation.tool_selection !== expectedTool
  ) {
    reject("tool_not_exact");
  }
  return {
    schema: SELECTOR_PROOF_SCHEMA,
    source: "browser",
    observed_at: observation.observed_at,
    target_id,
    target_url: expectedUrl,
    composer_proven: true,
    model_requested: model,
    model_observed: observation.model_machine_id ?? model,
    model_proven: true,
    tool_requested: expectedTool,
    tool_observed: expectedTool,
    tool_proven: true,
  };
}

async function selectorPageProbe(
  targetId,
  canonicalProCapabilityFunction,
) {
  const normalize = (value) =>
    String(value || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
  const visible = (element) => {
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
    !element?.disabled &&
    normalize(element?.getAttribute("aria-disabled")) !== "true";
  const exactModelSelection = (element) => {
    const text = normalize(element?.innerText || element?.textContent);
    const aria = normalize(element?.getAttribute("aria-label"));
    const modelId = String(
      element?.getAttribute("data-model-id") || "",
    )
      .toLowerCase()
      .trim();
    const exactTextSignal = new Map([
      ["pro", "pro"],
      ["instant", "instant"],
      ["thinking", "thinking"],
      ["auto", "auto"],
    ]);
    const exactAriaSignal = new Map([
      ["model selector pro", "pro"],
      ["model pro", "pro"],
      ["model selector instant", "instant"],
      ["model instant", "instant"],
      ["model selector thinking", "thinking"],
      ["model thinking", "thinking"],
      ["model selector auto", "auto"],
      ["model auto", "auto"],
    ]);
    const exactModelIdSignal = (value) => {
      if (!value) return null;
      for (const selection of ["pro", "instant", "thinking", "auto"]) {
        if (
          new RegExp(
            `^gpt-[a-z0-9]+(?:[.-][a-z0-9]+)*-${selection}$`,
          ).test(value)
        ) {
          return selection;
        }
      }
      return "other";
    };
    const semanticSignal = (value, dictionary, neutral = new Set()) => {
      if (!value || neutral.has(value)) return null;
      return dictionary.get(value) || "other";
    };
    const signals = [
      semanticSignal(text, exactTextSignal),
      semanticSignal(aria, exactAriaSignal, new Set(["model selector"])),
      exactModelIdSignal(modelId),
    ].filter(Boolean);
    const selections = new Set(signals);
    const selection = selections.size === 1 ? [...selections][0] : null;
    return new Set(["pro", "instant", "thinking", "auto"]).has(selection)
      ? selection
      : "ambiguous";
  };
  const exactToolSelection = (element) => {
    const tool = normalize(element?.getAttribute("data-tool"));
    const text = normalize(element?.innerText || element?.textContent);
    const aria = normalize(element?.getAttribute("aria-label"));
    const identities = [tool, text, aria]
      .filter(Boolean)
      .map((value) =>
        value === "deep research" ? "deep-research" : "other",
      );
    const selections = new Set(identities);
    return selections.size === 1 && selections.has("deep-research")
      ? "deep-research"
      : "ambiguous";
  };
  const toolState = (element) => {
    const pressed = normalize(element.getAttribute("aria-pressed"));
    const state = normalize(element.getAttribute("data-state"));
    const signals = [];
    if (pressed === "true") signals.push("active");
    if (pressed === "false") signals.push("inactive");
    if (pressed && pressed !== "true" && pressed !== "false") {
      signals.push("ambiguous");
    }
    if (state === "active" || state === "on") signals.push("active");
    if (state === "inactive" || state === "off") signals.push("inactive");
    if (
      state &&
      state !== "active" &&
      state !== "on" &&
      state !== "inactive" &&
      state !== "off"
    ) {
      signals.push("ambiguous");
    }
    const states = new Set(signals);
    if (states.has("ambiguous") || states.size > 1) return "ambiguous";
    return states.size === 1 ? [...states][0] : "inactive";
  };

  const promptFields = Array.from(
    document.querySelectorAll(
      "#prompt-textarea[contenteditable='true'],[contenteditable='true'][role='textbox']",
    ),
  ).filter(visible);
  const composers = Array.from(
    new Set(
      promptFields
        .map((field) =>
          field.closest("[data-testid*='composer'],form"),
        )
        .filter(Boolean),
    ),
  ).filter(visible);
  const composer = composers.length === 1 ? composers[0] : null;
  const modelControls = composer
    ? Array.from(
        composer.querySelectorAll(
          "[data-testid='model-switcher-dropdown-button'],[data-testid='model-switcher']",
        ),
      ).filter(visible)
    : [];
  const modelSelection =
    modelControls.length === 1
      ? exactModelSelection(modelControls[0])
      : "ambiguous";
  const machineModelId =
    modelControls.length === 1
      ? String(modelControls[0].getAttribute("data-model-id") || "")
          .toLowerCase()
          .trim()
      : "";
  const toolChips = composer
    ? Array.from(
        composer.querySelectorAll(
          "[data-testid='composer-tool-chip'],[data-tool]",
        ),
      ).filter(visible)
    : [];
  const toolStates = toolChips.map((element) => ({
    element,
    state: toolState(element),
  }));
  const ambiguousToolState = toolStates.some(
    ({ state }) => state === "ambiguous",
  );
  const activeToolChips = toolStates
    .filter(({ state }) => state === "active")
    .map(({ element }) => element);
  const toolSelection =
    ambiguousToolState
      ? "ambiguous"
      : activeToolChips.length === 0
      ? "none"
      : activeToolChips.length === 1
        ? exactToolSelection(activeToolChips[0])
        : "ambiguous";
  let modelBody = null;
  try {
    const response = await fetch(
      "/backend-api/models?history_and_training_disabled=false",
      { credentials: "include", cache: "no-store" },
    );
    if (response.ok) modelBody = await response.json();
  } catch {}
  const catalog = canonicalProCapabilityFunction(modelBody);
  return {
    schema: "oracle-subagent.selector-observation.v1",
    observed_at: new Date().toISOString(),
    target_id: targetId,
    target_url: location.href,
    composer_count: composers.length,
    composer_visible: composer !== null,
    prompt_field_count: promptFields.length,
    model_control_count: modelControls.length,
    model_control_enabled:
      modelControls.length === 1 && enabled(modelControls[0]),
    model_machine_id:
      /^gpt-[a-z0-9]+(?:[.-][a-z0-9]+)*$/.test(machineModelId)
        ? machineModelId
        : null,
    model_selection: modelSelection,
    catalog_pro_model_ids: [...catalog.identifiers].sort(),
    active_tool_count: activeToolChips.length,
    active_tools_enabled:
      !ambiguousToolState && activeToolChips.every(enabled),
    tool_selection: toolSelection,
  };
}

export function selectorPageProbeExpression(targetId) {
  if (typeof targetId !== "string" || !TARGET_ID_PATTERN.test(targetId)) {
    reject("request_invalid");
  }
  return `(${selectorPageProbe})(${JSON.stringify(
    targetId,
  )}, ${canonicalProCapability})`;
}

export function selectorPageProbeSource() {
  return [
    canonicalProCapability.toString(),
    selectorPageProbe.toString(),
  ].join("\n");
}
