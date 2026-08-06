import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";

import {
  SELECTOR_OBSERVATION_SCHEMA,
  SELECTOR_PROOF_SCHEMA,
  proveSelectorObservation,
  selectorPageProbeExpression,
  selectorPageProbeSource,
} from "../assets/scripts/chatgpt-selector-contract.mjs";
import {
  cdpRequest,
  startFakeCdp,
} from "./fake-cdp.mjs";

const TEST_DIRECTORY = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_PATH = path.join(
  TEST_DIRECTORY,
  "fixtures",
  "chatgpt-selector",
  "cases.json",
);

async function fixture() {
  return JSON.parse(await readFile(FIXTURE_PATH, "utf8"));
}

function baseObservation(contract) {
  return {
    schema: SELECTOR_OBSERVATION_SCHEMA,
    observed_at: contract.observed_at,
    target_id: contract.target_id,
    target_url: contract.target_url,
    composer_count: 1,
    composer_visible: true,
    prompt_field_count: 1,
    model_control_count: 1,
    model_control_enabled: true,
    model_machine_id: null,
    model_selection: "pro",
    catalog_pro_model_ids: [contract.model],
    active_tool_count: 0,
    active_tools_enabled: true,
    tool_selection: "none",
  };
}

function prove(contract, fixtureCase) {
  return proveSelectorObservation(
    {
      ...baseObservation(contract),
      ...fixtureCase.mutate,
    },
    {
      target_id: contract.target_id,
      target_url: contract.target_url,
      model: contract.model,
      mode: fixtureCase.mode,
      now: contract.now,
    },
  );
}

function fakeElement({
  text = "",
  attributes = {},
  disabled = false,
  visible = true,
} = {}) {
  const values = new Map(Object.entries(attributes));
  return {
    disabled,
    innerText: text,
    textContent: text,
    getAttribute(name) {
      return values.has(name) ? values.get(name) : null;
    },
    getBoundingClientRect() {
      return visible
        ? { width: 100, height: 30 }
        : { width: 0, height: 0 };
    },
  };
}

async function executePageProbe(contract, probeCase) {
  const modelControl = fakeElement({
    text: probeCase.dom.model.text,
    attributes: {
      "aria-label": probeCase.dom.model.aria,
      "aria-disabled": probeCase.dom.model.aria_disabled,
      "data-model-id": probeCase.dom.model.data_model_id,
    },
    disabled: probeCase.dom.model.disabled === true,
  });
  const toolChips = probeCase.dom.tools.map((tool) =>
    fakeElement({
      text: tool.text,
      attributes: {
        "aria-label": tool.aria,
        "aria-disabled": tool.aria_disabled,
        "aria-pressed": tool.aria_pressed,
        "data-state": tool.data_state,
        "data-tool": tool.data_tool,
      },
      disabled: tool.disabled === true,
    }),
  );
  const composer = fakeElement();
  composer.querySelectorAll = (selector) => {
    if (selector.includes("model-switcher")) return [modelControl];
    if (selector.includes("composer-tool-chip")) return toolChips;
    throw new Error("unexpected composer selector");
  };
  const promptField = fakeElement();
  promptField.closest = () => composer;
  const document = new Proxy(
    {
      querySelectorAll(selector) {
        assert.equal(
          selector,
          "#prompt-textarea[contenteditable='true'],[contenteditable='true'][role='textbox']",
        );
        return [promptField];
      },
    },
    {
      get(target, property, receiver) {
        if (property === "body") {
          throw new Error(
            `broad body access exposed ${probeCase.dom.distractors.join(",")}`,
          );
        }
        return Reflect.get(target, property, receiver);
      },
    },
  );
  const crossRealmObservation = await runInNewContext(
    selectorPageProbeExpression(contract.target_id),
    {
      document,
      fetch: async (resource, options) => {
        assert.equal(
          resource,
          "/backend-api/models?history_and_training_disabled=false",
        );
        assert.equal(options.credentials, "include");
        assert.equal(options.cache, "no-store");
        assert.deepEqual(Object.keys(options).sort(), [
          "cache",
          "credentials",
        ]);
        return {
          ok: true,
          async json() {
            return {
              models: [
                {
                  slug: contract.model,
                  enabled: true,
                  available: true,
                },
              ],
            };
          },
        };
      },
      getComputedStyle: () => ({
        display: "block",
        visibility: "visible",
      }),
      location: { href: contract.target_url },
    },
  );
  // CDP Runtime.evaluate with returnByValue serializes into the runner realm.
  return JSON.parse(JSON.stringify(crossRealmObservation));
}

test("table fixtures enforce exact composer-scoped Pro and tool proof", async (t) => {
  const contract = await fixture();
  assert.equal(contract.schema, "oracle-subagent.selector-cases.v1");
  const names = new Set();
  for (const fixtureCase of contract.cases) {
    assert.equal(names.has(fixtureCase.case), false, fixtureCase.case);
    names.add(fixtureCase.case);
    await t.test(fixtureCase.case, () => {
      if (fixtureCase.expected.ok) {
        const proof = prove(contract, fixtureCase);
        assert.equal(proof.schema, SELECTOR_PROOF_SCHEMA);
        assert.equal(proof.model_proven, true);
        assert.equal(proof.tool_proven, true);
        return;
      }
      assert.throws(
        () => prove(contract, fixtureCase),
        (error) => {
          assert.equal(error.code, fixtureCase.expected.code);
          assert.equal(error.message, "chatgpt selector contract: rejected");
          assert.doesNotMatch(
            error.message,
            /account|help|history|project|target|model|tool|Pro|Deep/i,
          );
          return true;
        },
      );
    });
  }
  for (const required of [
    "account-badge-pro-is-not-composer-proof",
    "help-copy-deep-research-is-not-active-tool",
    "stale-history-pro-is-not-current-model",
    "instant-is-not-pro",
    "inactive-deep-research-chip",
    "two-composers",
    "disabled-model-control",
    "disabled-active-deep-research-chip",
    "two-canonical-pro-models",
    "wrong-target-id",
    "wrong-target-url",
    "stale-observation",
  ]) {
    assert.equal(names.has(required), true, required);
  }
});

test("standard Pro proof requires no active tool and is lifecycle-ready", async () => {
  const contract = await fixture();
  const fixtureCase = contract.cases.find(
    ({ case: name }) => name === "ready-standard-pro",
  );
  const proof = prove(contract, fixtureCase);
  assert.deepEqual(proof, {
    schema: SELECTOR_PROOF_SCHEMA,
    source: "browser",
    observed_at: contract.observed_at,
    target_id: contract.target_id,
    target_url: contract.target_url,
    composer_proven: true,
    model_requested: contract.model,
    model_observed: contract.model,
    model_proven: true,
    tool_requested: "none",
    tool_observed: "none",
    tool_proven: true,
  });
});

test("Deep Research proof requires exactly one active scoped chip", async () => {
  const contract = await fixture();
  const fixtureCase = contract.cases.find(
    ({ case: name }) => name === "ready-deep-research",
  );
  const proof = prove(contract, fixtureCase);
  assert.equal(proof.tool_requested, "deep-research");
  assert.equal(proof.tool_observed, "deep-research");
});

test("strict observations reject extra fields and attacker text without echo", async () => {
  const contract = await fixture();
  const secretField = "account@example.test?token=sk-proj-never-echo";
  assert.throws(
    () =>
      proveSelectorObservation(
        {
          ...baseObservation(contract),
          [secretField]: "Pro",
        },
        {
          target_id: contract.target_id,
          target_url: contract.target_url,
          model: contract.model,
          mode: "pro",
          now: contract.now,
        },
      ),
    (error) => {
      assert.equal(error.code, "observation_invalid");
      assert.doesNotMatch(
        error.message,
        /account|example|token|sk-proj|never-echo/i,
      );
      return true;
    },
  );
});

test("executable DOM probe fixtures fail closed on contradictory local signals", async (t) => {
  const contract = await fixture();
  const names = new Set();
  for (const probeCase of contract.probe_cases) {
    assert.equal(names.has(probeCase.case), false, probeCase.case);
    names.add(probeCase.case);
    await t.test(probeCase.case, async () => {
      const observation = await executePageProbe(contract, probeCase);
      for (const [key, value] of Object.entries(
        probeCase.expected.observation,
      )) {
        assert.deepEqual(observation[key], value, key);
      }
      const request = {
        target_id: contract.target_id,
        target_url: contract.target_url,
        model: contract.model,
        mode: probeCase.mode,
        now: observation.observed_at,
      };
      if (probeCase.expected.ok) {
        const proof = proveSelectorObservation(observation, request);
        assert.equal(proof.model_proven, true);
        assert.equal(proof.tool_proven, true);
        return;
      }
      assert.throws(
        () => proveSelectorObservation(observation, request),
        (error) => {
          assert.equal(error.code, probeCase.expected.code);
          assert.equal(error.message, "chatgpt selector contract: rejected");
          return true;
        },
      );
    });
  }
  for (const required of [
    "probe-model-conflict-instant-vs-pro",
    "probe-model-conflict-pro-vs-instant",
    "probe-model-machine-id-conflict",
    "probe-machine-pro-id-mismatch",
    "probe-tool-state-conflict-inactive-vs-active",
    "probe-tool-state-conflict-active-vs-inactive",
    "probe-tool-state-unsupported-aria",
    "probe-tool-state-unsupported-data",
    "probe-tool-identity-image-vs-deep-research",
    "probe-tool-identity-deep-research-vs-image",
    "probe-inactive-deep-research",
    "probe-account-help-history-distractors-ignored",
  ]) {
    assert.equal(names.has(required), true, required);
  }
});

test("the generated page probe is observation-only and composer-scoped", async () => {
  const contract = await fixture();
  const source = selectorPageProbeSource();
  const expression = selectorPageProbeExpression(contract.target_id);
  assert.match(source, /model-switcher-dropdown-button/);
  assert.match(source, /composer-tool-chip/);
  assert.match(source, /closest\\?\(|closest\(/);
  assert.match(source, /backend-api\/models/);
  assert.doesNotMatch(source, /document\.body|body\.innerText/);
  assert.doesNotMatch(source, /\.click\(|dispatchEvent|Input\.|focus\(/);
  assert.doesNotMatch(
    source,
    /send-button|composer-submit|Send prompt|textContent\s*=/,
  );
  assert.doesNotMatch(source, /promptText|innerHTML|outerHTML/);
  assert.match(expression, new RegExp(contract.target_id));
});

test("proof composes through fake exact-target CDP without submission", async (t) => {
  const contract = await fixture();
  const observation = {
    ...baseObservation(contract),
    active_tool_count: 1,
    tool_selection: "deep-research",
  };
  const fake = await startFakeCdp({
    targets: [
      {
        id: contract.target_id,
        type: "page",
        url: contract.target_url,
      },
    ],
    runtime_results: {
      [contract.target_id]: [observation],
    },
  });
  t.after(async () => {
    await fake.close();
  });
  const evaluated = await cdpRequest(
    fake.targets[0].webSocketDebuggerUrl,
    "Runtime.evaluate",
    {
      expression: selectorPageProbeExpression(contract.target_id),
      awaitPromise: true,
      returnByValue: true,
    },
  );
  const proof = proveSelectorObservation(evaluated.result.value, {
    target_id: contract.target_id,
    target_url: contract.target_url,
    model: contract.model,
    mode: "deep-research",
    now: contract.now,
  });
  assert.equal(proof.model_proven, true);
  assert.equal(proof.tool_proven, true);
  assert.deepEqual(fake.calls, [
    {
      channel: "page",
      target_id: contract.target_id,
      method: "Runtime.evaluate",
    },
  ]);
  assert.doesNotMatch(
    JSON.stringify(fake.calls),
    /send|click|input|prompt|expression/i,
  );
});
