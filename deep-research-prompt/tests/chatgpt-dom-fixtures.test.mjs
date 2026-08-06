import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const FIXTURE_DIRECTORY = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "fixtures",
  "chatgpt-dom",
);
const EXPECTED_CASES = [
  "active",
  "challenge",
  "completed-ui-only",
  "completed",
  "error",
  "logged-out",
  "model-tool-drift",
  "old-assistant-turn",
  "ready-pro-deep",
];

function attribute(attributes, name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return attributes.match(new RegExp(`(?:^|\\s)${escaped}="([^"]*)"`))?.[1] ?? null;
}

function stripMarkup(value) {
  return value
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function parseManifest(html) {
  const match = html.match(
    /<script type="application\/json" id="fixture-contract">\s*([\s\S]*?)\s*<\/script>/,
  );
  assert.ok(match, "fixture manifest is required");
  return JSON.parse(match[1]);
}

function extractContract(html) {
  const main = html.match(/<main\b([^>]*)>/);
  assert.ok(main, "main element is required");
  const composer = html.match(
    /<form\b(?=[^>]*data-testid="composer")[^>]*>([\s\S]*?)<\/form>/,
  )?.[1] ?? "";
  const modelAttributes = composer.match(
    /<button\b(?=[^>]*data-testid="model-switcher")([^>]*)>/,
  )?.[1] ?? null;
  const toolAttributes = composer.match(
    /<button\b(?=[^>]*data-testid="composer-tool-chip")([^>]*)>/,
  )?.[1] ?? null;
  const turns = Array.from(
    html.matchAll(/<article\b([^>]*)>([\s\S]*?)<\/article>/g),
    (match) => {
      const rawPosition = attribute(match[1], "data-turn-position");
      return {
        role: attribute(match[1], "data-message-author-role"),
        id: attribute(match[1], "data-message-id"),
        position:
          typeof rawPosition === "string" && /^[1-9][0-9]*$/.test(rawPosition)
            ? Number(rawPosition)
            : null,
        state: attribute(match[1], "data-run-state"),
        text: stripMarkup(match[2]),
        markup: match[2],
      };
    },
  );
  const messageIds = turns.map((turn) => turn.id);
  const turnPositions = turns.map((turn) => turn.position);
  const turnIdentityValid =
    messageIds.every((id) => typeof id === "string" && id.length > 0) &&
    new Set(messageIds).size === messageIds.length &&
    turnPositions.every(
      (position) => Number.isSafeInteger(position) && position > 0,
    ) &&
    new Set(turnPositions).size === turnPositions.length;
  const hasUserTurn = turns.some((turn) => turn.role === "user");
  const users = turns.filter(
    (turn) => turn.role === "user" && Number.isSafeInteger(turn.position),
  );
  const userPosition =
    users.length > 0 ? Math.max(...users.map((turn) => turn.position)) : null;
  const assistantsAfterUser =
    userPosition === null
      ? []
      : turns.filter(
          (turn) =>
            turn.role === "assistant" &&
            Number.isSafeInteger(turn.position) &&
            turn.position > userPosition,
        );
  const currentAssistant =
    turnIdentityValid && assistantsAfterUser.length > 0
      ? assistantsAfterUser.sort((left, right) => right.position - left.position)[0]
      : null;
  const dedicatedResult = (currentAssistant?.markup ?? "").match(
    /<(?:div|section)\b(?=[^>]*data-testid="assistant-result")[^>]*>([\s\S]*?)<\/(?:div|section)>/,
  );
  const errorState = html.match(
    /<(?:section|div)\b(?=[^>]*data-testid="run-error")([^>]*)>/,
  );
  const runState = errorState
    ? attribute(errorState[1], "data-run-state")
    : currentAssistant
      ? currentAssistant.state
      : !turnIdentityValid && hasUserTurn
        ? "ambiguous"
      : userPosition !== null
        ? "submitted"
        : "idle";
  return {
    session: attribute(main[1], "data-session"),
    challenge:
      /data-testid="challenge"|class="[^"]*\bcf-challenge\b/.test(html),
    model_id:
      modelAttributes === null
        ? null
        : attribute(modelAttributes, "data-model-id"),
    tool:
      toolAttributes !== null &&
      attribute(toolAttributes, "aria-pressed") === "true"
        ? attribute(toolAttributes, "data-tool")
        : "none",
    run_state: runState,
    assistant_after_user: currentAssistant !== null,
    result_nonempty:
      currentAssistant?.state === "completed" &&
      dedicatedResult !== null &&
      stripMarkup(dedicatedResult[1]).length > 0,
  };
}

async function fixtures() {
  const names = (await readdir(FIXTURE_DIRECTORY))
    .filter((name) => name.endsWith(".html"))
    .sort();
  return Promise.all(
    names.map(async (name) => {
      const html = await readFile(path.join(FIXTURE_DIRECTORY, name), "utf8");
      return {
        name,
        html,
        manifest: parseManifest(html),
        observed: extractContract(html),
      };
    }),
  );
}

test("fixture inventory is complete, deterministic, and secret-free", async () => {
  const loaded = await fixtures();
  assert.deepEqual(
    loaded.map(({ name }) => name.replace(/\.html$/, "")),
    EXPECTED_CASES,
  );
  for (const { name, html, manifest } of loaded) {
    assert.equal(manifest.schema, "oracle-subagent.dom-fixture.v1", name);
    assert.equal(`${manifest.case}.html`, name);
    assert.equal(
      (html.match(/<script\b/g) || []).length,
      1,
      `${name} has only its inert manifest script`,
    );
    assert.doesNotMatch(
      html,
      /(?:sk-(?:proj-)?[A-Za-z0-9_-]{12,}|github_pat_|xox[baprs]-|xapp-|cookie=|authorization:|https?:\/\/|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})/i,
      name,
    );
  }
});

test("every manifest exactly matches composer-scoped and causal DOM evidence", async () => {
  for (const { name, manifest, observed } of await fixtures()) {
    assert.deepEqual(observed, manifest.expected, name);
  }
});

test("account/help distractors cannot prove Pro or active Deep Research", async () => {
  const drift = (await fixtures()).find(
    ({ manifest }) => manifest.case === "model-tool-drift",
  );
  assert.match(drift.html, />Pro<\/button>/);
  assert.match(drift.html, /Deep Research guide/);
  assert.equal(drift.observed.model_id, "gpt-5-instant");
  assert.equal(drift.observed.tool, "none");
});

test("historical assistant content cannot complete a later user turn", async () => {
  const historical = (await fixtures()).find(
    ({ manifest }) => manifest.case === "old-assistant-turn",
  );
  assert.match(historical.html, /Historical answer that must not complete/);
  assert.equal(historical.observed.run_state, "submitted");
  assert.equal(historical.observed.assistant_after_user, false);
  assert.equal(historical.observed.result_nonempty, false);
});

test("duplicate or missing turn identity fails closed without cross-binding markup", async () => {
  const complete = (await fixtures()).find(
    ({ manifest }) => manifest.case === "completed",
  ).html;
  const duplicate = complete.replace(
    'data-message-id="assistant-current"',
    'data-message-id="assistant-baseline"',
  );
  const duplicateObserved = extractContract(duplicate);
  assert.equal(duplicateObserved.run_state, "ambiguous");
  assert.equal(duplicateObserved.assistant_after_user, false);
  assert.equal(duplicateObserved.result_nonempty, false);

  const missing = complete.replace(
    'data-message-id="assistant-current"',
    "",
  );
  const missingObserved = extractContract(missing);
  assert.equal(missingObserved.run_state, "ambiguous");
  assert.equal(missingObserved.assistant_after_user, false);
  assert.equal(missingObserved.result_nonempty, false);

  const missingPosition = complete.replace(
    'data-turn-position="2"',
    "",
  );
  const missingPositionObserved = extractContract(missingPosition);
  assert.equal(missingPositionObserved.run_state, "ambiguous");
  assert.equal(missingPositionObserved.assistant_after_user, false);
  assert.equal(missingPositionObserved.result_nonempty, false);

  const duplicatePosition = complete.replace(
    'data-turn-position="2"',
    'data-turn-position="1"',
  );
  const duplicatePositionObserved = extractContract(duplicatePosition);
  assert.equal(duplicatePositionObserved.run_state, "ambiguous");
  assert.equal(duplicatePositionObserved.assistant_after_user, false);
  assert.equal(duplicatePositionObserved.result_nonempty, false);
});

test("active, completed, and error states remain mutually distinct", async () => {
  const byCase = new Map(
    (await fixtures()).map((fixture) => [fixture.manifest.case, fixture.observed]),
  );
  assert.deepEqual(
    [
      byCase.get("active").run_state,
      byCase.get("completed").run_state,
      byCase.get("error").run_state,
    ],
    ["active", "completed", "failed"],
  );
  assert.equal(byCase.get("active").result_nonempty, false);
  assert.equal(byCase.get("completed").result_nonempty, true);
  assert.equal(byCase.get("completed-ui-only").run_state, "completed");
  assert.equal(byCase.get("completed-ui-only").result_nonempty, false);
  assert.equal(byCase.get("error").result_nonempty, false);
});

test("login and challenge fixtures cannot satisfy authenticated readiness", async () => {
  const byCase = new Map(
    (await fixtures()).map((fixture) => [fixture.manifest.case, fixture.observed]),
  );
  assert.equal(byCase.get("logged-out").session, "guest");
  assert.equal(byCase.get("logged-out").model_id, null);
  assert.equal(byCase.get("challenge").session, "ambiguous");
  assert.equal(byCase.get("challenge").challenge, true);
});
