import {
  RECEIPT_SCHEMA,
  STATES,
  readReceiptFile,
  withReceiptFileLock,
} from "./oracle-subagent-state.mjs";

export const PROVENANCE_SCHEMA = "oracle-subagent.provenance.v1";
export const PROVENANCE_RECEIPT_SCHEMA =
  "oracle-subagent.provenance-receipt.v1";
export const SELECTOR_OBSERVATION_SCHEMA =
  "oracle-subagent.selector-observation.v1";
export const SELECTOR_PROOF_SCHEMA = "oracle-subagent.selector-proof.v1";
export const PROVENANCE_WRITER_CONTRACT = Object.freeze({
  schema: "oracle-subagent.provenance-writer-contract.v1",
  receipt_lock: "oracle-subagent-state.withReceiptFileLock",
  result_and_proof_writes: "receipt-lock-required",
  terminal_result_and_proof: "immutable",
});

const RUN_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$/;
const SEMVER_PATTERN =
  /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-(?:alpha|beta|rc)(?:\.(0|[1-9][0-9]*))?)?$/;
const CHROME_VERSION_PATTERN =
  /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const RECEIPT_STATES = new Set(STATES);
const MAX_STABILITY_DELAY_MS = 10_000;

export class OracleSubagentProvenanceError extends Error {
  constructor(code) {
    super("oracle-subagent provenance: rejected");
    this.name = "OracleSubagentProvenanceError";
    this.code = code;
  }
}

function reject(code) {
  throw new OracleSubagentProvenanceError(code);
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

function exactString(value, expected, code) {
  if (value !== expected) reject(code);
  return value;
}

function patternedString(value, pattern, code) {
  if (typeof value !== "string" || !pattern.test(value)) reject(code);
  return value;
}

function versionedArtifact(value, hashKey, code, versionPattern = SEMVER_PATTERN) {
  exactObject(value, ["version", hashKey], code);
  return {
    version: patternedString(value.version, versionPattern, code),
    [hashKey]: patternedString(value[hashKey], SHA256_PATTERN, code),
  };
}

function normalizeComponents(value, code = "components_invalid") {
  exactObject(
    value,
    ["wrapper", "oracle", "chrome", "policy", "selector_contract"],
    code,
  );
  const selector = exactObject(
    value.selector_contract,
    ["version", "sha256", "observation_schema", "proof_schema"],
    code,
  );
  return {
    wrapper: versionedArtifact(value.wrapper, "sha256", code),
    oracle: versionedArtifact(value.oracle, "sha256", code),
    chrome: versionedArtifact(
      value.chrome,
      "executable_sha256",
      code,
      CHROME_VERSION_PATTERN,
    ),
    policy: versionedArtifact(value.policy, "sha256", code),
    selector_contract: {
      version: patternedString(selector.version, SEMVER_PATTERN, code),
      sha256: patternedString(selector.sha256, SHA256_PATTERN, code),
      observation_schema: exactString(
        selector.observation_schema,
        SELECTOR_OBSERVATION_SCHEMA,
        code,
      ),
      proof_schema: exactString(
        selector.proof_schema,
        SELECTOR_PROOF_SCHEMA,
        code,
      ),
    },
  };
}

function stableValue(value) {
  if (Array.isArray(value)) return value.map(stableValue);
  if (isPlainObject(value)) {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, stableValue(value[key])]),
    );
  }
  return value;
}

function canonicalJson(value) {
  return JSON.stringify(stableValue(value));
}

function deepFreeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value)) deepFreeze(child);
  }
  return value;
}

function normalizeProvenance(value) {
  exactObject(
    value,
    [
      "schema",
      "run_id",
      "wrapper",
      "oracle",
      "chrome",
      "policy",
      "selector_contract",
    ],
    "provenance_invalid",
  );
  exactString(value.schema, PROVENANCE_SCHEMA, "provenance_invalid");
  const runId = patternedString(
    value.run_id,
    RUN_ID_PATTERN,
    "provenance_invalid",
  );
  const components = {
    wrapper: value.wrapper,
    oracle: value.oracle,
    chrome: value.chrome,
    policy: value.policy,
    selector_contract: value.selector_contract,
  };
  return {
    schema: PROVENANCE_SCHEMA,
    run_id: runId,
    ...normalizeComponents(components, "provenance_invalid"),
  };
}

function normalizeExpected(value) {
  return normalizeComponents(value, "expected_provenance_invalid");
}

function normalizeVerificationOptions(value) {
  if (value === undefined) return { stabilityDelayMs: 0 };
  exactObject(value, ["stabilityDelayMs"], "verification_options_invalid");
  if (
    !Number.isSafeInteger(value.stabilityDelayMs) ||
    value.stabilityDelayMs < 0 ||
    value.stabilityDelayMs > MAX_STABILITY_DELAY_MS
  ) {
    reject("verification_options_invalid");
  }
  return { stabilityDelayMs: value.stabilityDelayMs };
}

async function readStableLifecycle(
  receiptPath,
  verificationOptions,
  callback,
) {
  const { stabilityDelayMs } = normalizeVerificationOptions(
    verificationOptions,
  );
  try {
    return await withReceiptFileLock(receiptPath, async () => {
      let first;
      try {
        first = await readReceiptFile(receiptPath);
      } catch {
        reject("lifecycle_receipt_invalid");
      }
      if (stabilityDelayMs > 0) {
        await new Promise((resolvePromise) =>
          setTimeout(resolvePromise, stabilityDelayMs),
        );
      }
      let second;
      try {
        second = await readReceiptFile(receiptPath);
      } catch {
        reject("lifecycle_receipt_unstable");
      }
      if (canonicalJson(first) !== canonicalJson(second)) {
        reject("lifecycle_receipt_unstable");
      }
      return callback(second);
    });
  } catch (error) {
    if (error instanceof OracleSubagentProvenanceError) throw error;
    reject("lifecycle_receipt_invalid");
  }
}

export function verifyProvenance(rawProvenance, trustedExpected) {
  const provenance = normalizeProvenance(rawProvenance);
  const expected = normalizeExpected(trustedExpected);
  const observedComponents = {
    wrapper: provenance.wrapper,
    oracle: provenance.oracle,
    chrome: provenance.chrome,
    policy: provenance.policy,
    selector_contract: provenance.selector_contract,
  };
  if (canonicalJson(observedComponents) !== canonicalJson(expected)) {
    reject("provenance_mismatch");
  }
  return deepFreeze(structuredClone(provenance));
}

function provenanceReceipt(lifecycle, provenance) {
  return {
    schema: PROVENANCE_RECEIPT_SCHEMA,
    run_id: lifecycle.run_id,
    state: lifecycle.state,
    lifecycle_receipt_schema: RECEIPT_SCHEMA,
    lifecycle_receipt_hash: lifecycle.receipt_hash,
    provenance,
  };
}

export async function createProvenanceReceipt(
  receiptPath,
  rawProvenance,
  trustedExpected,
  verificationOptions,
) {
  return readStableLifecycle(
    receiptPath,
    verificationOptions,
    (lifecycle) => {
      const provenance = verifyProvenance(rawProvenance, trustedExpected);
      if (provenance.run_id !== lifecycle.run_id) {
        reject("run_binding_invalid");
      }
      return deepFreeze(provenanceReceipt(lifecycle, provenance));
    },
  );
}

export async function verifyProvenanceReceipt(
  receiptPath,
  rawProvenanceReceipt,
  trustedExpected,
  verificationOptions,
) {
  return readStableLifecycle(
    receiptPath,
    verificationOptions,
    (lifecycle) => {
      exactObject(
        rawProvenanceReceipt,
        [
          "schema",
          "run_id",
          "state",
          "lifecycle_receipt_schema",
          "lifecycle_receipt_hash",
          "provenance",
        ],
        "provenance_receipt_invalid",
      );
      if (
        rawProvenanceReceipt.schema !== PROVENANCE_RECEIPT_SCHEMA ||
        rawProvenanceReceipt.lifecycle_receipt_schema !== RECEIPT_SCHEMA ||
        !RECEIPT_STATES.has(rawProvenanceReceipt.state) ||
        rawProvenanceReceipt.run_id !== lifecycle.run_id ||
        rawProvenanceReceipt.state !== lifecycle.state ||
        rawProvenanceReceipt.lifecycle_receipt_hash !== lifecycle.receipt_hash
      ) {
        reject("provenance_receipt_invalid");
      }
      const provenance = verifyProvenance(
        rawProvenanceReceipt.provenance,
        trustedExpected,
      );
      if (provenance.run_id !== lifecycle.run_id) {
        reject("run_binding_invalid");
      }
      return deepFreeze(provenanceReceipt(lifecycle, provenance));
    },
  );
}
