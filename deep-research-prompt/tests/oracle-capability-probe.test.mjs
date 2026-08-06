import assert from "node:assert/strict";
import { lstat, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  ORACLE_CAPABILITY_PIN_SCHEMA,
  ORACLE_CAPABILITY_SCHEMA,
  OracleCapabilityCleanupError,
  OracleCapabilityProbeError,
  __oracleCapabilityTesting,
  probeOracleCapabilities,
  withProvenOracleSnapshot,
} from "../assets/scripts/oracle-capability-probe.mjs";

const TEST_DIRECTORY = path.dirname(fileURLToPath(import.meta.url));
const MANIFEST_PATH = path.join(
  TEST_DIRECTORY,
  "fixtures",
  "oracle-capabilities",
  "oracle-0.9.0.json",
);

async function manifest() {
  return JSON.parse(await readFile(MANIFEST_PATH, "utf8"));
}

function assertRejected(action, code) {
  return assert.rejects(action, (error) => {
    assert(error instanceof OracleCapabilityProbeError);
    assert.equal(error.code, code);
    assert.equal(error.message, "oracle capability probe: rejected");
    return true;
  });
}

test("live pinned Oracle proves capabilities and binds a private snapshot callback", async () => {
  const expected = await manifest();
  assert.equal(expected.schema, ORACLE_CAPABILITY_PIN_SCHEMA);
  let ephemeralEntry;
  const session = await withProvenOracleSnapshot(
    {
      oracle_binary: "/opt/homebrew/bin/oracle",
      expected_manifest: expected,
    },
    async (context) => {
      ephemeralEntry = context.oracle_entry;
      assert.notEqual(
        context.oracle_entry,
        "/opt/homebrew/lib/node_modules/@steipete/oracle/dist/bin/oracle-cli.js",
      );
      assert(context.oracle_entry.startsWith(`${context.package_root}/`));
      assert(context.package_root.startsWith(`${context.oracle_home}/`));
      assert.equal(
        context.environment.ORACLE_HOME_DIR,
        context.oracle_home,
      );
      assert.deepEqual(Object.keys(context.environment).sort(), [
        "CI",
        "LANG",
        "LC_ALL",
        "NO_COLOR",
        "ORACLE_HOME_DIR",
        "PATH",
      ]);
      assert.doesNotMatch(
        JSON.stringify(context.environment),
        /authorization|bearer|cookie|password|prompt|secret|token/i,
      );
      const [entryMetadata, rootMetadata] = await Promise.all([
        lstat(context.oracle_entry),
        lstat(context.package_root),
      ]);
      assert.equal(entryMetadata.mode & 0o222, 0);
      assert.equal(rootMetadata.mode & 0o222, 0);
      assert.equal(context.proof.submit_performed, false);
      return "snapshot-callback-ok";
    },
  );
  assert.equal(session.value, "snapshot-callback-ok");
  await assert.rejects(lstat(ephemeralEntry), { code: "ENOENT" });
  const { proof } = session;
  assert.deepEqual(proof, {
    schema: ORACLE_CAPABILITY_SCHEMA,
    oracle: {
      package: "@steipete/oracle",
      version: "0.9.0",
      package_json_sha256:
        "b612197c2dc1fa55e664718028a62571d51772c5b748c3d422310cca71859e77",
      entry_sha256:
        "1c96b766be6e182b92c90fa7c2716cfa3e44737d0db5490bab88ffd9348e77f2",
      tree_sha256:
        "ad508bbbb5e3c4d405c7afee2da75027d32783e1cfefcb1924c311d315741950",
    },
    source_pins: {
      browser_config_sha256:
        "d21c5be24462bf9e60cb2e762ae1849205d8c793cdd3e3df4ddfdcc1639879e1",
      browser_runner_sha256:
        "ca86ba9cb8dc5696987394e14fbbf312b658a6b7f2894138a184e11dce006e1e",
      dry_run_sha256:
        "83dcbf78773c4acf8589c8049ecaf8847db5b3a279869b1b73fde7efebd30881",
    },
    capabilities: {
      pre_submit_hook_before_submission: true,
      remote_target_bound_to_hook: true,
      headless_forced_off: true,
      dry_run_no_submit: true,
      render_no_submit: true,
    },
    evidence: {
      source_hashes: "verified",
      source_semantics: "verified",
      browser_config_feature_probe: "verified",
      cli_dry_run_probe: "verified",
      cli_render_probe: "verified",
    },
    submit_performed: false,
  });
  assert(Object.isFrozen(proof));
  assert(Object.isFrozen(proof.capabilities));
  assert.doesNotMatch(
    JSON.stringify(proof),
    /authorization|bearer|cookie|environment|password|prompt|secret|session|token/i,
  );
});

test("source drift fails before any capability can be claimed", async () => {
  const expected = await manifest();
  expected.files.browser_runner.sha256 = "f".repeat(64);
  await assertRejected(
    probeOracleCapabilities({
      oracle_binary: "/opt/homebrew/bin/oracle",
      expected_manifest: expected,
    }),
    "source_pin_mismatch",
  );
});

test("complete package-tree drift rejects the private snapshot before probes", async () => {
  const expected = await manifest();
  expected.package.tree.sha256 = "e".repeat(64);
  await assertRejected(
    probeOracleCapabilities({
      oracle_binary: "/opt/homebrew/bin/oracle",
      expected_manifest: expected,
    }),
    "package_tree_mismatch",
  );
});

test("manifest is strict and cannot redirect a pinned source path", async () => {
  const expected = await manifest();
  await assertRejected(
    probeOracleCapabilities({
      oracle_binary: "/opt/homebrew/bin/oracle",
      expected_manifest: {
        ...structuredClone(expected),
        environment: "forbidden",
      },
    }),
    "manifest_invalid",
  );

  const redirected = structuredClone(expected);
  redirected.files.browser_runner.path = "../../tmp/attacker.js";
  await assertRejected(
    probeOracleCapabilities({
      oracle_binary: "/opt/homebrew/bin/oracle",
      expected_manifest: redirected,
    }),
    "manifest_invalid",
  );
});

test("snapshot execution requires an explicit callback", async () => {
  await assertRejected(
    withProvenOracleSnapshot(
      {
        oracle_binary: "/opt/homebrew/bin/oracle",
        expected_manifest: await manifest(),
      },
      null,
    ),
    "snapshot_callback_invalid",
  );
});

test("cleanup failure rejects success after explicit absence verification", async () => {
  await assertRejected(
    __oracleCapabilityTesting.settleCapabilitySession(
      {
        temporaryHome: "/must/not/be/removed",
        snapshotRoot: "/must/not/be/removed/oracle-package",
        environment: {},
        result: {},
        hasPrimaryError: false,
        primaryError: undefined,
      },
      undefined,
    ),
    "test_cleanup_operations_invalid",
  );

  const calls = [];
  const operations = {
    async lstat(target) {
      calls.push(["lstat", target]);
      return {};
    },
    async execFile(file, arguments_) {
      calls.push(["execFile", file, arguments_]);
      const error = new Error("synthetic unlock failure");
      error.code = "SYNTHETIC";
      throw error;
    },
    async rm(target, options) {
      calls.push(["rm", target, options]);
      const error = new Error("synthetic remove failure");
      error.code = "SYNTHETIC";
      throw error;
    },
  };

  await assert.rejects(
    __oracleCapabilityTesting.settleCapabilitySession(
      {
        temporaryHome: "/private/test/oracle-home",
        snapshotRoot: "/private/test/oracle-home/oracle-package",
        environment: {},
        result: { proof: "must-not-return" },
        hasPrimaryError: false,
        primaryError: undefined,
      },
      operations,
    ),
    (error) => {
      assert(error instanceof OracleCapabilityCleanupError);
      assert.equal(error.code, "cleanup_failed");
      assert.equal(
        error.message,
        "oracle capability probe: cleanup rejected",
      );
      assert.deepEqual(error.cleanup_failures, [
        "snapshot_unlock_failed",
        "temporary_home_remove_failed",
        "temporary_home_still_present",
      ]);
      assert(Object.isFrozen(error.cleanup_failures));
      return true;
    },
  );
  assert.deepEqual(calls.at(-1), [
    "lstat",
    "/private/test/oracle-home",
  ]);
});

test("primary probe error is preserved when cleanup also fails", async () => {
  const primaryError = new OracleCapabilityProbeError("callback_failed");
  const absent = Object.assign(new Error("absent"), { code: "ENOENT" });
  const operations = {
    async lstat(target) {
      if (target.endsWith("/oracle-package")) return {};
      throw absent;
    },
    async execFile() {
      throw new Error("synthetic unlock failure");
    },
    async rm() {},
  };

  await assert.rejects(
    __oracleCapabilityTesting.settleCapabilitySession(
      {
        temporaryHome: "/private/test/oracle-home",
        snapshotRoot: "/private/test/oracle-home/oracle-package",
        environment: {},
        result: undefined,
        hasPrimaryError: true,
        primaryError,
      },
      operations,
    ),
    (error) => {
      assert(error instanceof OracleCapabilityCleanupError);
      assert.equal(error.code, "cleanup_failed_after_primary");
      assert.equal(error.cause, primaryError);
      assert.deepEqual(error.cleanup_failures, [
        "snapshot_unlock_failed",
      ]);
      return true;
    },
  );
});

test("probe source exposes only fixed no-submit execution plans", async () => {
  const source = await readFile(
    new URL(
      "../assets/scripts/oracle-capability-probe.mjs",
      import.meta.url,
    ),
    "utf8",
  );
  assert.match(source, /"--dry-run", "json"/);
  assert.match(source, /"--render", "--render-plain"/);
  assert.match(source, /const PROBE_HOOK = "exit 97"/);
  assert.match(source, /const PROBE_REMOTE = "127\.0\.0\.1:1"/);
  assert.match(source, /\["-cR", sourceRoot, snapshotRoot\]/);
  assert.match(source, /\["-R", "a-w", snapshotRoot\]/);
  assert.match(source, /inspectOraclePackageTree\(snapshotRoot/);
  assert.doesNotMatch(source, /--force|--background|--wait/);
  assert.doesNotMatch(source, /\bconsole\s*\./);
  assert.doesNotMatch(source, /process\.env/);
  assert.doesNotMatch(source, /WebSocket|\bfetch\s*\(/);
});
