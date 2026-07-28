// Fail-closed Oracle browser capability gate.
//
// Version text is descriptive only. This gate verifies pinned source bytes,
// checks the security-critical source ordering, and executes no-submit
// subprocess probes for browser config, dry-run, and render behavior.

import { execFile as execFileCallback } from "node:child_process";
import { createHash } from "node:crypto";
import { constants as fsConstants } from "node:fs";
import {
  chmod,
  lstat,
  mkdtemp,
  open,
  readdir,
  readlink,
  realpath,
  rm,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { promisify } from "node:util";

export const ORACLE_CAPABILITY_PIN_SCHEMA =
  "oracle-subagent.oracle-capability-pin.v1";
export const ORACLE_CAPABILITY_SCHEMA =
  "oracle-subagent.oracle-capability.v1";
export const ORACLE_PACKAGE_TREE_SCHEMA =
  "oracle-subagent.oracle-package-tree.v1";

const PACKAGE_NAME = "@steipete/oracle";
const MAX_SOURCE_BYTES = 8 * 1024 * 1024;
const TREE_HASH_CONCURRENCY = 24;
const PROBE_PROMPT = "oracle-capability-public-sentinel";
const PROBE_FILE_CONTENT = "oracle capability public fixture\n";
const PROBE_HOOK = "exit 97";
const PROBE_REMOTE = "127.0.0.1:1";
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const SEMVER_PATTERN =
  /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-(?:alpha|beta|rc)(?:\.(0|[1-9][0-9]*))?)?$/;
const EXPECTED_PATHS = Object.freeze({
  cli: "dist/bin/oracle-cli.js",
  browser_config: "dist/src/cli/browserConfig.js",
  browser_runner: "dist/src/browser/index.js",
  dry_run: "dist/src/cli/dryRun.js",
});
const execFile = promisify(execFileCallback);

export class OracleCapabilityProbeError extends Error {
  constructor(code) {
    super("oracle capability probe: rejected");
    this.name = "OracleCapabilityProbeError";
    this.code = code;
  }
}

export class OracleCapabilityCleanupError extends Error {
  constructor(primaryError, cleanupFailures) {
    const hasPrimaryError = primaryError !== undefined;
    super(
      "oracle capability probe: cleanup rejected",
      hasPrimaryError ? { cause: primaryError } : undefined,
    );
    this.name = "OracleCapabilityCleanupError";
    this.code = hasPrimaryError
      ? "cleanup_failed_after_primary"
      : "cleanup_failed";
    this.cleanup_failures = Object.freeze([...cleanupFailures]);
  }
}

function reject(code) {
  throw new OracleCapabilityProbeError(code);
}

function isPlainObject(value) {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.getPrototypeOf(value) === Object.prototype
  );
}

function exactObject(value, keys, code = "manifest_invalid") {
  if (
    !isPlainObject(value) ||
    Object.keys(value).length !== keys.length ||
    keys.some((key) => !Object.hasOwn(value, key))
  ) {
    reject(code);
  }
  return value;
}

function exactString(value, expected, code = "manifest_invalid") {
  if (value !== expected) reject(code);
  return value;
}

function patternedString(value, pattern, code = "manifest_invalid") {
  if (typeof value !== "string" || !pattern.test(value)) reject(code);
  return value;
}

function normalizePin(value, key) {
  exactObject(value, ["path", "sha256"]);
  return {
    path: exactString(value.path, EXPECTED_PATHS[key]),
    sha256: patternedString(value.sha256, SHA256_PATTERN),
  };
}

function normalizeManifest(value) {
  exactObject(value, ["schema", "package", "files"]);
  exactString(value.schema, ORACLE_CAPABILITY_PIN_SCHEMA);
  exactObject(value.package, [
    "name",
    "version",
    "package_json_sha256",
    "tree",
  ]);
  exactObject(value.package.tree, [
    "schema",
    "sha256",
    "files",
    "directories",
    "symlinks",
    "bytes",
  ]);
  exactString(value.package.name, PACKAGE_NAME);
  exactObject(value.files, [
    "cli",
    "browser_config",
    "browser_runner",
    "dry_run",
  ]);
  return {
    schema: ORACLE_CAPABILITY_PIN_SCHEMA,
    package: {
      name: PACKAGE_NAME,
      version: patternedString(value.package.version, SEMVER_PATTERN),
      package_json_sha256: patternedString(
        value.package.package_json_sha256,
        SHA256_PATTERN,
      ),
      tree: {
        schema: exactString(
          value.package.tree.schema,
          ORACLE_PACKAGE_TREE_SCHEMA,
        ),
        sha256: patternedString(value.package.tree.sha256, SHA256_PATTERN),
        files: boundedCount(value.package.tree.files),
        directories: boundedCount(value.package.tree.directories),
        symlinks: boundedCount(value.package.tree.symlinks),
        bytes: boundedCount(value.package.tree.bytes, Number.MAX_SAFE_INTEGER),
      },
    },
    files: Object.fromEntries(
      Object.keys(EXPECTED_PATHS).map((key) => [
        key,
        normalizePin(value.files[key], key),
      ]),
    ),
  };
}

function boundedCount(value, maximum = 1_000_000) {
  if (!Number.isSafeInteger(value) || value < 0 || value > maximum) {
    reject("manifest_invalid");
  }
  return value;
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function sameFile(left, right) {
  return left.dev === right.dev && left.ino === right.ino;
}

function sameSnapshot(left, right) {
  return (
    sameFile(left, right) &&
    left.size === right.size &&
    left.mode === right.mode &&
    left.uid === right.uid &&
    left.nlink === right.nlink &&
    left.mtimeMs === right.mtimeMs &&
    left.ctimeMs === right.ctimeMs
  );
}

async function readStableRegularFile(
  filePath,
  label,
  { allowEmpty = false } = {},
) {
  let handle;
  try {
    handle = await open(
      filePath,
      fsConstants.O_RDONLY |
        (fsConstants.O_NOFOLLOW ?? 0) |
        (fsConstants.O_CLOEXEC ?? 0),
    );
    const before = await handle.stat();
    if (
      !before.isFile() ||
      before.nlink !== 1 ||
      (!allowEmpty && before.size < 1) ||
      before.size > MAX_SOURCE_BYTES ||
      (before.mode & 0o022) !== 0
    ) {
      reject("source_file_invalid");
    }
    const bytes = await handle.readFile();
    const after = await handle.stat();
    const pathMetadata = await lstat(filePath);
    if (
      bytes.length !== before.size ||
      !sameSnapshot(before, after) ||
      !sameFile(after, pathMetadata) ||
      !pathMetadata.isFile()
    ) {
      reject("source_file_changed");
    }
    return bytes;
  } catch (error) {
    if (error instanceof OracleCapabilityProbeError) throw error;
    reject(label === "package" ? "package_invalid" : "source_file_invalid");
  } finally {
    await handle?.close().catch(() => {});
  }
}

async function collectTreeRecords(
  packageRoot,
  directory,
  relativeDirectory,
  requireReadOnly,
  records,
) {
  let entries;
  try {
    entries = await readdir(directory, { withFileTypes: true });
  } catch {
    reject("package_tree_invalid");
  }
  entries.sort((left, right) =>
    Buffer.from(left.name).compare(Buffer.from(right.name)),
  );
  for (const entry of entries) {
    if (
      !entry.name ||
      entry.name.includes("\0") ||
      entry.name.includes("/") ||
      entry.name === "." ||
      entry.name === ".."
    ) {
      reject("package_tree_invalid");
    }
    const absolutePath = path.join(directory, entry.name);
    const relativePath = relativeDirectory
      ? `${relativeDirectory}/${entry.name}`
      : entry.name;
    let metadata;
    try {
      metadata = await lstat(absolutePath);
    } catch {
      reject("package_tree_changed");
    }
    if (requireReadOnly && (metadata.mode & 0o222) !== 0) {
      reject("package_snapshot_mutable");
    }
    if (metadata.isDirectory()) {
      records.push({
        type: "directory",
        path: relativePath,
      });
      await collectTreeRecords(
        packageRoot,
        absolutePath,
        relativePath,
        requireReadOnly,
        records,
      );
      continue;
    }
    if (metadata.isFile()) {
      if (
        metadata.nlink !== 1 ||
        metadata.size < 0 ||
        metadata.size > MAX_SOURCE_BYTES
      ) {
        reject("package_tree_invalid");
      }
      records.push({
        type: "file",
        path: relativePath,
        absolutePath,
        bytes: metadata.size,
        sha256: null,
      });
      continue;
    }
    if (metadata.isSymbolicLink()) {
      let target;
      try {
        target = await readlink(absolutePath);
      } catch {
        reject("package_tree_changed");
      }
      if (
        !target ||
        target.includes("\0") ||
        path.isAbsolute(target)
      ) {
        reject("package_tree_invalid");
      }
      const resolvedTarget = path.resolve(path.dirname(absolutePath), target);
      if (
        resolvedTarget === packageRoot ||
        !resolvedTarget.startsWith(`${packageRoot}${path.sep}`)
      ) {
        reject("package_tree_invalid");
      }
      records.push({
        type: "symlink",
        path: relativePath,
        target,
      });
      continue;
    }
    reject("package_tree_invalid");
  }
}

async function hashTreeFiles(records) {
  const files = records.filter(({ type }) => type === "file");
  let cursor = 0;
  const workers = Array.from(
    { length: Math.min(TREE_HASH_CONCURRENCY, Math.max(files.length, 1)) },
    async () => {
      while (cursor < files.length) {
        const index = cursor;
        cursor += 1;
        const record = files[index];
        const bytes = await readStableRegularFile(
          record.absolutePath,
          "tree",
          { allowEmpty: true },
        );
        if (bytes.length !== record.bytes) reject("package_tree_changed");
        record.sha256 = sha256(bytes);
      }
    },
  );
  await Promise.all(workers);
}

export async function inspectOraclePackageTree(
  packageRoot,
  { require_read_only = false } = {},
) {
  if (
    typeof packageRoot !== "string" ||
    !path.isAbsolute(packageRoot) ||
    path.resolve(packageRoot) !== packageRoot ||
    (await realpath(packageRoot).catch(() => null)) !== packageRoot
  ) {
    reject("package_tree_invalid");
  }
  const rootMetadata = await lstat(packageRoot).catch(() => null);
  if (
    !rootMetadata?.isDirectory() ||
    (require_read_only && (rootMetadata.mode & 0o222) !== 0)
  ) {
    reject(
      require_read_only
        ? "package_snapshot_mutable"
        : "package_tree_invalid",
    );
  }
  const records = [];
  await collectTreeRecords(
    packageRoot,
    packageRoot,
    "",
    require_read_only,
    records,
  );
  await hashTreeFiles(records);
  records.sort((left, right) =>
    Buffer.from(left.path).compare(Buffer.from(right.path)),
  );
  const digest = createHash("sha256");
  digest.update(`${ORACLE_PACKAGE_TREE_SCHEMA}\n`);
  let files = 0;
  let directories = 0;
  let symlinks = 0;
  let bytes = 0;
  for (const record of records) {
    if (record.type === "file") {
      files += 1;
      bytes += record.bytes;
      digest.update(
        `${JSON.stringify([
          "file",
          record.path,
          record.bytes,
          record.sha256,
        ])}\n`,
      );
    } else if (record.type === "directory") {
      directories += 1;
      digest.update(
        `${JSON.stringify(["directory", record.path])}\n`,
      );
    } else {
      symlinks += 1;
      digest.update(
        `${JSON.stringify(["symlink", record.path, record.target])}\n`,
      );
    }
  }
  return deepFreeze({
    schema: ORACLE_PACKAGE_TREE_SCHEMA,
    sha256: digest.digest("hex"),
    files,
    directories,
    symlinks,
    bytes,
  });
}

function safePackageRoot(entryPath, entryRelativePath) {
  const suffix = `${path.sep}${entryRelativePath}`;
  if (!entryPath.endsWith(suffix)) reject("source_layout_invalid");
  const root = entryPath.slice(0, -suffix.length);
  if (
    !path.isAbsolute(root) ||
    path.resolve(root) !== root ||
    root === path.parse(root).root
  ) {
    reject("source_layout_invalid");
  }
  return root;
}

async function resolvePinnedSources(oracleBinary, manifest) {
  if (
    typeof oracleBinary !== "string" ||
    !path.isAbsolute(oracleBinary) ||
    path.resolve(oracleBinary) !== oracleBinary
  ) {
    reject("oracle_binary_invalid");
  }
  let entryPath;
  try {
    entryPath = await realpath(oracleBinary);
  } catch {
    reject("oracle_binary_invalid");
  }
  const packageRoot = safePackageRoot(entryPath, manifest.files.cli.path);
  if ((await realpath(packageRoot).catch(() => null)) !== packageRoot) {
    reject("source_layout_invalid");
  }
  const paths = Object.fromEntries(
    Object.entries(manifest.files).map(([key, pin]) => {
      const candidate = path.resolve(packageRoot, pin.path);
      if (
        candidate === packageRoot ||
        !candidate.startsWith(`${packageRoot}${path.sep}`)
      ) {
        reject("source_layout_invalid");
      }
      return [key, candidate];
    }),
  );
  if (paths.cli !== entryPath) reject("source_layout_invalid");
  const packagePath = path.join(packageRoot, "package.json");
  const resolved = await Promise.all(
    [packagePath, ...Object.values(paths)].map((candidate) =>
      realpath(candidate).catch(() => null),
    ),
  );
  if (
    resolved[0] !== packagePath ||
    Object.values(paths).some(
      (candidate, index) => resolved[index + 1] !== candidate,
    )
  ) {
    reject("source_layout_invalid");
  }
  const [packageBytes, ...sourceBytes] = await Promise.all([
    readStableRegularFile(packagePath, "package"),
    ...Object.entries(paths).map(([key, candidate]) =>
      readStableRegularFile(candidate, key),
    ),
  ]);
  const bytes = Object.fromEntries(
    Object.keys(paths).map((key, index) => [key, sourceBytes[index]]),
  );
  if (
    sha256(packageBytes) !== manifest.package.package_json_sha256 ||
    Object.entries(bytes).some(
      ([key, content]) => sha256(content) !== manifest.files[key].sha256,
    )
  ) {
    reject("source_pin_mismatch");
  }
  let packageDocument;
  try {
    packageDocument = JSON.parse(packageBytes.toString("utf8"));
  } catch {
    reject("package_invalid");
  }
  if (
    packageDocument?.name !== PACKAGE_NAME ||
    packageDocument?.version !== manifest.package.version ||
    packageDocument?.type !== "module" ||
    packageDocument?.bin?.oracle !== manifest.files.cli.path
  ) {
    reject("package_mismatch");
  }
  return { packageRoot, paths, bytes };
}

function ordered(source, needles, code) {
  let cursor = -1;
  for (const needle of needles) {
    const next = source.indexOf(needle, cursor + 1);
    if (next < 0 || next <= cursor) reject(code);
    cursor = next;
  }
}

function verifyPinnedSemantics(bytes) {
  const cli = bytes.cli.toString("utf8");
  const config = bytes.browser_config.toString("utf8");
  const runner = bytes.browser_runner.toString("utf8");
  const dryRun = bytes.dry_run.toString("utf8");

  for (const option of [
    "--browser-headless",
    "--browser-hide-window",
    "--pre-submit-hook <command>",
    "--remote-chrome <host:port>",
    "--dry-run [mode]",
    "--render",
  ]) {
    if (!cli.includes(option)) reject("cli_capability_missing");
  }
  ordered(
    config,
    [
      "if (options.remoteChrome)",
      "remoteChrome = parseRemoteChromeTarget(options.remoteChrome)",
      "headless: undefined",
      "preSubmitHook: options.preSubmitHook",
      "remoteChrome,",
    ],
    "browser_config_semantics_invalid",
  );
  ordered(
    runner,
    [
      "remoteTargetId = connection.targetId ?? null;",
      "if (config.preSubmitHook)",
      "await runPreSubmitHook(config.preSubmitHook",
      "targetId: remoteTargetId ?? undefined",
      "const submitOnce = async",
      "await runProviderSubmissionFlow",
    ],
    "pre_submit_ordering_invalid",
  );
  const hookFunction = runner.indexOf(
    "async function runPreSubmitHook(command, context, logger)",
  );
  const targetEnvironment = runner.indexOf(
    "ORACLE_CHATGPT_TARGET_ID: context.targetId ?? ''",
    hookFunction,
  );
  if (hookFunction < 0 || targetEnvironment < hookFunction) {
    reject("remote_target_binding_invalid");
  }
  const dryRunStart = dryRun.indexOf("async function runBrowserDryRun");
  const nextFunction = dryRun.indexOf("\nfunction ", dryRunStart + 1);
  const dryRunBlock = dryRun.slice(
    dryRunStart,
    nextFunction < 0 ? undefined : nextFunction,
  );
  if (
    dryRunStart < 0 ||
    !dryRunBlock.includes("assemblePromptImpl") ||
    /runBrowserMode|executeBrowser|runProviderSubmissionFlow/.test(
      dryRunBlock,
    )
  ) {
    reject("dry_run_semantics_invalid");
  }
}

function sanitizedEnvironment(temporaryHome) {
  return {
    PATH: [
      path.dirname(process.execPath),
      "/opt/homebrew/bin",
      "/usr/bin",
      "/bin",
    ].join(":"),
    ORACLE_HOME_DIR: temporaryHome,
    NO_COLOR: "1",
    CI: "1",
    LANG: "C",
    LC_ALL: "C",
  };
}

async function runProgram(program, arguments_, options, code) {
  try {
    const result = await execFile(program, arguments_, {
      ...options,
      encoding: "utf8",
      timeout: 20_000,
      killSignal: "SIGKILL",
      maxBuffer: 16 * 1024 * 1024,
    });
    return {
      stdout: String(result.stdout || ""),
      stderr: String(result.stderr || ""),
    };
  } catch {
    reject(code);
  }
}

const CONFIG_FEATURE_PROBE = `
const moduleUrl = process.argv[1];
const imported = await import(moduleUrl);
const config = await imported.buildBrowserConfig({
  model: "gpt-5.4-pro",
  browserHeadless: true,
  browserHideWindow: true,
  remoteChrome: "127.0.0.1:9222",
  preSubmitHook: "exit 97",
  chatgptUrl: "https://chatgpt.com/"
});
process.stdout.write(JSON.stringify({
  schema: "oracle-subagent.oracle-config-feature.v1",
  headless_disabled: config.headless === undefined,
  remote_target_parsed:
    config.remoteChrome?.host === "127.0.0.1" &&
    config.remoteChrome?.port === 9222,
  pre_submit_hook_preserved: config.preSubmitHook === "exit 97",
  hidden_requested: config.hideWindow === true,
  exact_url: config.url === "https://chatgpt.com/",
  inline_cookies_absent: config.inlineCookies === undefined
}));
`;

function verifyConfigFeatureOutput(result) {
  if (result.stderr.trim()) reject("browser_config_probe_failed");
  let value;
  try {
    value = JSON.parse(result.stdout);
  } catch {
    reject("browser_config_probe_failed");
  }
  exactObject(
    value,
    [
      "schema",
      "headless_disabled",
      "remote_target_parsed",
      "pre_submit_hook_preserved",
      "hidden_requested",
      "exact_url",
      "inline_cookies_absent",
    ],
    "browser_config_probe_failed",
  );
  if (
    value.schema !== "oracle-subagent.oracle-config-feature.v1" ||
    value.headless_disabled !== true ||
    value.remote_target_parsed !== true ||
    value.pre_submit_hook_preserved !== true ||
    value.hidden_requested !== true ||
    value.exact_url !== true ||
    value.inline_cookies_absent !== true
  ) {
    reject("browser_config_probe_failed");
  }
}

function oracleProbeArguments(entryPath, mode, probeFile) {
  const common = [
    entryPath,
    "--engine",
    "browser",
    "--remote-chrome",
    PROBE_REMOTE,
    "--pre-submit-hook",
    PROBE_HOOK,
    "--browser-headless",
    "--no-notify",
  ];
  if (mode === "dry-run") {
    common.push("--dry-run", "json");
  } else if (mode === "render") {
    common.push("--render", "--render-plain");
  } else {
    reject("probe_plan_invalid");
  }
  common.push("--prompt", PROBE_PROMPT, "--file", probeFile);
  return common;
}

function verifyNoSubmitCliOutput(result, mode) {
  const combined = `${result.stdout}\n${result.stderr}`;
  if (
    result.stderr.trim() ||
    !combined.includes(PROBE_PROMPT) ||
    /Connecting to remote Chrome|Running pre-submit hook|Launching browser mode|connect ECONN|User error/.test(
      combined,
    )
  ) {
    reject(`${mode}_probe_failed`);
  }
  if (mode === "dry-run") {
    if (
      !combined.includes("Preview JSON") ||
      !/"engine"\s*:\s*"browser"/.test(combined)
    ) {
      reject("dry_run_probe_failed");
    }
    return;
  }
  if (!combined.includes("[SYSTEM]")) reject("render_system_missing");
  if (!combined.includes("[USER]")) reject("render_user_missing");
  if (!combined.includes("### File:")) reject("render_file_missing");
}

function deepFreeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value)) deepFreeze(child);
  }
  return value;
}

function verifyPackageTree(observed, expected) {
  if (
    observed.schema !== expected.schema ||
    observed.sha256 !== expected.sha256 ||
    observed.files !== expected.files ||
    observed.directories !== expected.directories ||
    observed.symlinks !== expected.symlinks ||
    observed.bytes !== expected.bytes
  ) {
    reject("package_tree_mismatch");
  }
}

async function createReadonlyPackageSnapshot(
  sourceRoot,
  snapshotRoot,
  environment,
  expectedTree,
) {
  await runProgram(
    "/bin/cp",
    ["-cR", sourceRoot, snapshotRoot],
    { cwd: path.dirname(snapshotRoot), env: environment },
    "package_snapshot_copy_failed",
  );
  await runProgram(
    "/bin/chmod",
    ["-R", "a-w", snapshotRoot],
    { cwd: path.dirname(snapshotRoot), env: environment },
    "package_snapshot_lock_failed",
  );
  const [sourceEntry, snapshotEntry] = await Promise.all([
    lstat(path.join(sourceRoot, EXPECTED_PATHS.cli)),
    lstat(path.join(snapshotRoot, EXPECTED_PATHS.cli)),
  ]).catch(() => reject("package_snapshot_invalid"));
  if (sameFile(sourceEntry, snapshotEntry)) {
    reject("package_snapshot_invalid");
  }
  const first = await inspectOraclePackageTree(snapshotRoot, {
    require_read_only: true,
  });
  verifyPackageTree(first, expectedTree);
  const second = await inspectOraclePackageTree(snapshotRoot, {
    require_read_only: true,
  });
  verifyPackageTree(second, expectedTree);
  if (first.sha256 !== second.sha256) reject("package_snapshot_unstable");
}

function capabilityProof(manifest) {
  return deepFreeze({
    schema: ORACLE_CAPABILITY_SCHEMA,
    oracle: {
      package: PACKAGE_NAME,
      version: manifest.package.version,
      package_json_sha256: manifest.package.package_json_sha256,
      entry_sha256: manifest.files.cli.sha256,
      tree_sha256: manifest.package.tree.sha256,
    },
    source_pins: {
      browser_config_sha256: manifest.files.browser_config.sha256,
      browser_runner_sha256: manifest.files.browser_runner.sha256,
      dry_run_sha256: manifest.files.dry_run.sha256,
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
}

async function collectCleanupFailures(
  { temporaryHome, snapshotRoot, environment },
  operations = { execFile, lstat, rm },
) {
  const failures = [];
  let snapshotExists = false;
  try {
    await operations.lstat(snapshotRoot);
    snapshotExists = true;
  } catch (error) {
    if (error?.code !== "ENOENT") {
      failures.push("snapshot_inspection_failed");
    }
  }
  if (snapshotExists) {
    try {
      await operations.execFile(
        "/bin/chmod",
        ["-R", "u+w", snapshotRoot],
        {
          env: environment,
          timeout: 20_000,
        },
      );
    } catch {
      failures.push("snapshot_unlock_failed");
    }
  }
  try {
    await operations.rm(temporaryHome, { recursive: true, force: true });
  } catch {
    failures.push("temporary_home_remove_failed");
  }
  try {
    await operations.lstat(temporaryHome);
    failures.push("temporary_home_still_present");
  } catch (error) {
    if (error?.code !== "ENOENT") {
      failures.push("temporary_home_verification_failed");
    }
  }
  return Object.freeze([...new Set(failures)]);
}

async function settleCapabilitySession(
  {
    temporaryHome,
    snapshotRoot,
    environment,
    result,
    hasPrimaryError,
    primaryError,
  },
  operations,
) {
  const cleanupFailures = await collectCleanupFailures(
    { temporaryHome, snapshotRoot, environment },
    operations,
  );
  if (cleanupFailures.length > 0) {
    throw new OracleCapabilityCleanupError(
      hasPrimaryError ? primaryError : undefined,
      cleanupFailures,
    );
  }
  if (hasPrimaryError) throw primaryError;
  return result;
}

async function runCapabilitySession(
  {
    oracle_binary = "/opt/homebrew/bin/oracle",
    expected_manifest,
  } = {},
  callback = null,
) {
  const manifest = normalizeManifest(expected_manifest);
  const sources = await resolvePinnedSources(oracle_binary, manifest);
  verifyPinnedSemantics(sources.bytes);

  const temporaryHome = await realpath(
    await mkdtemp(
      path.join(os.tmpdir(), "oracle-capability-probe-"),
    ),
  );
  await chmod(temporaryHome, 0o700);
  const snapshotRoot = path.join(temporaryHome, "oracle-package");
  const probeFile = path.join(temporaryHome, "public-fixture.txt");
  await writeFile(probeFile, PROBE_FILE_CONTENT, {
    encoding: "utf8",
    mode: 0o600,
    flag: "wx",
  });
  const environment = sanitizedEnvironment(temporaryHome);
  let result;
  let hasPrimaryError = false;
  let primaryError;
  try {
    await createReadonlyPackageSnapshot(
      sources.packageRoot,
      snapshotRoot,
      environment,
      manifest.package.tree,
    );
    const snapshotSources = await resolvePinnedSources(
      path.join(snapshotRoot, manifest.files.cli.path),
      manifest,
    );
    verifyPinnedSemantics(snapshotSources.bytes);

    const configResult = await runProgram(
      process.execPath,
      [
        "--input-type=module",
        "--eval",
        CONFIG_FEATURE_PROBE,
        pathToFileURL(snapshotSources.paths.browser_config).href,
      ],
      {
        cwd: snapshotSources.packageRoot,
        env: environment,
      },
      "browser_config_probe_failed",
    );
    verifyConfigFeatureOutput(configResult);
    await resolvePinnedSources(snapshotSources.paths.cli, manifest);

    const dryRunResult = await runProgram(
      process.execPath,
      oracleProbeArguments(
        snapshotSources.paths.cli,
        "dry-run",
        probeFile,
      ),
      {
        cwd: snapshotSources.packageRoot,
        env: environment,
      },
      "dry_run_probe_failed",
    );
    verifyNoSubmitCliOutput(dryRunResult, "dry-run");
    await resolvePinnedSources(snapshotSources.paths.cli, manifest);

    const renderResult = await runProgram(
      process.execPath,
      oracleProbeArguments(
        snapshotSources.paths.cli,
        "render",
        probeFile,
      ),
      {
        cwd: snapshotSources.packageRoot,
        env: environment,
      },
      "render_probe_failed",
    );
    verifyNoSubmitCliOutput(renderResult, "render");
    const proof = capabilityProof(manifest);
    let value;
    if (callback !== null) {
      value = await callback(
        deepFreeze({
          proof,
          oracle_entry: snapshotSources.paths.cli,
          package_root: snapshotSources.packageRoot,
          oracle_home: temporaryHome,
          environment: { ...environment },
        }),
      );
    }
    const finalTree = await inspectOraclePackageTree(snapshotRoot, {
      require_read_only: true,
    });
    verifyPackageTree(finalTree, manifest.package.tree);
    result = { proof, value };
  } catch (error) {
    hasPrimaryError = true;
    primaryError = error;
  }
  return settleCapabilitySession({
    temporaryHome,
    snapshotRoot,
    environment,
    result,
    hasPrimaryError,
    primaryError,
  });
}

export async function probeOracleCapabilities(options) {
  return (await runCapabilitySession(options)).proof;
}

export async function withProvenOracleSnapshot(options, callback) {
  if (typeof callback !== "function") reject("snapshot_callback_invalid");
  return runCapabilitySession(options, callback);
}

async function settleCapabilitySessionForTest(state, operations) {
  if (
    !isPlainObject(operations) ||
    typeof operations.execFile !== "function" ||
    typeof operations.lstat !== "function" ||
    typeof operations.rm !== "function"
  ) {
    reject("test_cleanup_operations_invalid");
  }
  return settleCapabilitySession(state, operations);
}

export const __oracleCapabilityTesting = Object.freeze({
  settleCapabilitySession: settleCapabilitySessionForTest,
});
