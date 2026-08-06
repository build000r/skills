#!/bin/bash
set -euo pipefail
umask 077

usage() {
  printf '%s\n' \
    'usage: oracle-subagent-local-proof.sh --out /tmp/oracle-subagent-e2e/.../local' \
    '' \
    'Runs two bounded live browser submissions (Pro and Deep Research), then' \
    'writes a redacted success/failure/security proof bundle. The configured' \
    'persistent auth profile must already pass oracle-subagent auth doctor.'
}

die() {
  printf 'oracle local proof: %s\n' "$1" >&2
  exit "${2:-2}"
}

OUT=""
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --out)
      [[ "$#" -ge 2 ]] || die "missing value for --out"
      OUT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ -n "$OUT" ]] || die "--out is required"
[[ "$OUT" = /* ]] || die "--out must be absolute"
NORMALIZED_OUT="$(
  /usr/bin/python3 -I - "$OUT" <<'PY'
import os
import sys

path = sys.argv[1]
normalized = os.path.normpath(path)
if normalized != path or not normalized.startswith("/tmp/oracle-subagent-e2e/"):
    raise SystemExit(1)
print(normalized)
PY
)" || die "--out must be normalized under /tmp/oracle-subagent-e2e/"
[[ "$NORMALIZED_OUT" = "$OUT" ]] || die "--out normalization mismatch"
[[ ! -e "$OUT" && ! -L "$OUT" ]] ||
  die "--out already exists; use a fresh proof directory"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
SKILLS_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd -P)"
CLI="$SKILLS_ROOT/deep-research-prompt/assets/scripts/oracle-subagent.mjs"
AUTH="$SKILLS_ROOT/deep-research-prompt/assets/scripts/oracle-subagent-auth.mjs"
RESOLVER="$SKILLS_ROOT/skill-issue/scripts/resolve_overlay_config.py"
ARTIFACT_ROOT="$OUT/runs"
CURRENT_PHASE="bootstrap"

for tool in node jq oracle shasum /usr/bin/python3; do
  command -v "$tool" >/dev/null 2>&1 ||
    die "required command not found: $tool"
done
[[ -f "$CLI" && -f "$AUTH" && -f "$RESOLVER" ]] ||
  die "required Oracle subagent files are missing"

mkdir -p "$(dirname "$OUT")"
mkdir "$OUT"
chmod 700 "$OUT"
mkdir "$OUT/pro" "$OUT/deep-research" "$OUT/failures" \
  "$OUT/logs" "$OUT/private" "$ARTIFACT_ROOT"
chmod 700 "$OUT/pro" "$OUT/deep-research" "$OUT/failures" \
  "$OUT/logs" "$OUT/private" "$ARTIFACT_ROOT"

write_incomplete_manifest() {
  local exit_code="$1"
  jq -n \
    --arg phase "$CURRENT_PHASE" \
    --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --argjson exit_code "$exit_code" \
    '{
      schema: "oracle-subagent.local-proof-manifest.v1",
      hard_gates: "fail",
      phase: $phase,
      exit_code: $exit_code,
      generated_at: $generated_at
    }' > "$OUT/manifest.json.tmp"
  chmod 600 "$OUT/manifest.json.tmp"
  mv "$OUT/manifest.json.tmp" "$OUT/manifest.json"
}

on_error() {
  local exit_code="$?"
  trap - ERR
  write_incomplete_manifest "$exit_code" || true
  printf 'oracle local proof: failed at %s\n' "$CURRENT_PHASE" >&2
  exit "$exit_code"
}
trap on_error ERR

cd "$SKILLS_ROOT"
eval "$(
  /usr/bin/python3 "$RESOLVER" \
    --section oracle \
    --cwd "$SKILLS_ROOT" \
    --format env \
    --require
)"

CURRENT_PHASE="auth-doctor"
AUTH_REPORT="$OUT/auth-doctor.json"
if ! node "$AUTH" doctor --json > "$AUTH_REPORT"; then
  chmod 600 "$AUTH_REPORT"
  exit 20
fi
chmod 600 "$AUTH_REPORT"
jq -e '
  .ok == true and
  .state == "ready" and
  .checks.private_permissions == true and
  .checks.single_listener == true and
  .checks.loopback_only == true and
  .checks.browser_pid == true and
  .checks.exact_target == true and
  .checks.browser_hidden == true and
  .checks.authenticated == true and
  .checks.policy_enrolled == true and
  .checks.profile_matches == true and
  .checks.account_matches == true and
  .checks.project_access == true and
  .checks.pro_plan == true and
  .checks.pro_model == true and
  .checks.composer_available == true
' "$AUTH_REPORT" >/dev/null

NONCE="$(
  node -e 'process.stdout.write(`oracle-proof-${crypto.randomUUID()}`)'
)"
SHORT_NONCE="${NONCE##*-}"
PRO_PROMPT="$OUT/private/pro-prompt.md"
DEEP_PROMPT="$OUT/private/deep-research-prompt.md"

printf '%s\n' \
  'You are executing a bounded Oracle subagent proof.' \
  "Return exactly this marker and nothing else: $NONCE-pro" \
  > "$PRO_PROMPT"
printf '%s\n' \
  'You are executing a bounded Deep Research Oracle subagent proof.' \
  "The first line of the final answer must be exactly: $NONCE-deep" \
  'Then give one sentence identifying the official IETF website and cite only an official IETF source.' \
  > "$DEEP_PROMPT"
chmod 600 "$PRO_PROMPT" "$DEEP_PROMPT"

sha256_file() {
  shasum -a 256 "$1" | awk '{print $1}'
}

write_public_receipt() {
  local command_json="$1"
  local result_file="$2"
  local destination="$3"
  local result_sha
  result_sha="$(sha256_file "$result_file")"
  jq \
    --arg result_sha256 "$result_sha" \
    '{
      schema: "oracle-subagent.local-proof-receipt.v1",
      command: .command,
      ok: .ok,
      run_id: .run_id,
      slug: .slug,
      mode: .mode,
      state: .state,
      revision: .revision,
      terminal: .terminal,
      result_bytes: .result_bytes,
      result_sha256: $result_sha256
    }' "$command_json" > "$destination.tmp"
  chmod 600 "$destination.tmp"
  mv "$destination.tmp" "$destination"
}

write_failure_receipt() {
  local name="$1"
  local proof_kind="$2"
  local evidence="$3"
  local exit_code="$4"
  jq -n \
    --arg name "$name" \
    --arg proof_kind "$proof_kind" \
    --arg evidence "$evidence" \
    --argjson exit_code "$exit_code" \
    '{
      schema: "oracle-subagent.local-negative-proof.v1",
      name: $name,
      hard_gate: "pass",
      proof_kind: $proof_kind,
      evidence: $evidence,
      exit_code: $exit_code
    }' > "$OUT/failures/$name.json.tmp"
  chmod 600 "$OUT/failures/$name.json.tmp"
  mv "$OUT/failures/$name.json.tmp" "$OUT/failures/$name.json"
}

run_test_gate() {
  local name="$1"
  local file="$2"
  local pattern="$3"
  local log="$OUT/logs/$name.tap"
  CURRENT_PHASE="negative-$name"
  node --test --test-name-pattern="$pattern" "$file" > "$log" 2>&1
  chmod 600 "$log"
  write_failure_receipt \
    "$name" \
    "deterministic-local-test" \
    "$file :: $pattern" \
    0
}

CURRENT_PHASE="live-pro"
node "$CLI" run \
  --artifact-root "$ARTIFACT_ROOT" \
  --slug "local-pro-$SHORT_NONCE" \
  --prompt-file "$PRO_PROMPT" \
  --mode pro \
  --wait completed \
  --timeout-seconds 7200 \
  --result "$OUT/pro/result.md" \
  --json > "$OUT/pro/command.json" 2> "$OUT/logs/pro.stderr"
chmod 600 "$OUT/pro/command.json" "$OUT/pro/result.md" "$OUT/logs/pro.stderr"
jq -e '.ok == true and .state == "completed" and .mode == "pro"' \
  "$OUT/pro/command.json" >/dev/null
grep -Fq "$NONCE-pro" "$OUT/pro/result.md"
write_public_receipt \
  "$OUT/pro/command.json" \
  "$OUT/pro/result.md" \
  "$OUT/pro/receipt.json"
PRO_RUN_ID="$(jq -r '.run_id' "$OUT/pro/command.json")"

CURRENT_PHASE="live-duplicate"
node "$CLI" run \
  --artifact-root "$ARTIFACT_ROOT" \
  --slug "local-pro-duplicate-$SHORT_NONCE" \
  --prompt-file "$PRO_PROMPT" \
  --mode pro \
  --wait none \
  --timeout-seconds 30 \
  --json > "$OUT/logs/duplicate-command.json" \
  2> "$OUT/logs/duplicate.stderr"
chmod 600 "$OUT/logs/duplicate-command.json" "$OUT/logs/duplicate.stderr"
jq -e --arg run_id "$PRO_RUN_ID" '
  .ok == true and
  .run_id == $run_id and
  .state == "completed" and
  .worker_pid == null
' "$OUT/logs/duplicate-command.json" >/dev/null
write_failure_receipt \
  "duplicate" \
  "live-no-resend" \
  "same fingerprint reattached to completed canonical run" \
  0

CURRENT_PHASE="live-unwritable-result"
if node "$CLI" wait \
  --artifact-root "$ARTIFACT_ROOT" \
  --run-id "$PRO_RUN_ID" \
  --for completed \
  --timeout-seconds 30 \
  --result "$OUT/pro/nonexistent-parent/result.md" \
  --json > "$OUT/logs/unwritable.stdout" \
  2> "$OUT/logs/unwritable.stderr"; then
  die "unwritable result destination unexpectedly succeeded"
else
  UNWRITABLE_EXIT="$?"
fi
chmod 600 "$OUT/logs/unwritable.stdout" "$OUT/logs/unwritable.stderr"
[[ "$UNWRITABLE_EXIT" -ne 0 ]]
[[ ! -e "$OUT/pro/nonexistent-parent/result.md" ]]
write_failure_receipt \
  "unwritable-result" \
  "live-result-publication" \
  "missing destination parent rejected while canonical receipt remained completed" \
  "$UNWRITABLE_EXIT"

CURRENT_PHASE="live-deep-research-start"
node "$CLI" run \
  --artifact-root "$ARTIFACT_ROOT" \
  --slug "local-deep-$SHORT_NONCE" \
  --prompt-file "$DEEP_PROMPT" \
  --mode deep-research \
  --wait none \
  --timeout-seconds 30 \
  --json > "$OUT/deep-research/start.json" \
  2> "$OUT/logs/deep-research-start.stderr"
chmod 600 "$OUT/deep-research/start.json" \
  "$OUT/logs/deep-research-start.stderr"
DEEP_RUN_ID="$(jq -r '.run_id' "$OUT/deep-research/start.json")"

CURRENT_PHASE="live-timeout"
if node "$CLI" wait \
  --artifact-root "$ARTIFACT_ROOT" \
  --run-id "$DEEP_RUN_ID" \
  --for completed \
  --timeout-seconds 1 \
  --json > "$OUT/logs/timeout.stdout" \
  2> "$OUT/logs/timeout.stderr"; then
  die "one-second completion wait unexpectedly succeeded"
else
  TIMEOUT_EXIT="$?"
fi
chmod 600 "$OUT/logs/timeout.stdout" "$OUT/logs/timeout.stderr"
[[ "$TIMEOUT_EXIT" -ne 0 ]]
node "$CLI" status \
  --artifact-root "$ARTIFACT_ROOT" \
  --run-id "$DEEP_RUN_ID" \
  --json > "$OUT/logs/timeout-status.json"
chmod 600 "$OUT/logs/timeout-status.json"
jq -e '.state != "completed" and .terminal == false' \
  "$OUT/logs/timeout-status.json" >/dev/null
write_failure_receipt \
  "timeout" \
  "live-observer-timeout" \
  "one-second observer wait failed without terminalizing the active run" \
  "$TIMEOUT_EXIT"

CURRENT_PHASE="live-deep-research-complete"
node "$CLI" wait \
  --artifact-root "$ARTIFACT_ROOT" \
  --run-id "$DEEP_RUN_ID" \
  --for completed \
  --timeout-seconds 7200 \
  --result "$OUT/deep-research/result.md" \
  --json > "$OUT/deep-research/command.json" \
  2> "$OUT/logs/deep-research.stderr"
chmod 600 "$OUT/deep-research/command.json" \
  "$OUT/deep-research/result.md" "$OUT/logs/deep-research.stderr"
jq -e '
  .ok == true and
  .state == "completed" and
  .mode == "deep-research"
' "$OUT/deep-research/command.json" >/dev/null
grep -Fq "$NONCE-deep" "$OUT/deep-research/result.md"
write_public_receipt \
  "$OUT/deep-research/command.json" \
  "$OUT/deep-research/result.md" \
  "$OUT/deep-research/receipt.json"

run_test_gate \
  "logged-out" \
  "deep-research-prompt/tests/oracle-subagent-auth.test.mjs" \
  "logged-out and ambiguous sessions"
run_test_gate \
  "wrong-model-tool" \
  "deep-research-prompt/tests/oracle-subagent-adapters.test.mjs" \
  "wrong or stale exact selector proof stops before send"
run_test_gate \
  "stale-output" \
  "deep-research-prompt/tests/chatgpt-dom-fixtures.test.mjs" \
  "historical assistant content cannot complete a later user turn"
run_test_gate \
  "browser-death" \
  "deep-research-prompt/tests/fake-cdp.test.mjs" \
  "browser death rejects an in-flight CDP request"

CURRENT_PHASE="security-audit"
node "$AUTH" doctor --json > "$OUT/logs/final-auth-doctor.json"
chmod 600 "$OUT/logs/final-auth-doctor.json"
jq -e '.ok == true and .state == "ready"' \
  "$OUT/logs/final-auth-doctor.json" >/dev/null

UNEXPECTED_NONCE_PATHS=0
while IFS= read -r pathname; do
  case "$pathname" in
    "$OUT/private/"*|"$OUT/pro/result.md"|"$OUT/deep-research/result.md")
      continue
      ;;
  esac
  if grep -Fq "$NONCE" "$pathname" 2>/dev/null; then
    UNEXPECTED_NONCE_PATHS=$((UNEXPECTED_NONCE_PATHS + 1))
  fi
done < <(find "$OUT" -type f -print)
[[ "$UNEXPECTED_NONCE_PATHS" -eq 0 ]]

WORLD_READABLE="$(
  find "$OUT" -type f -perm -007 -print | wc -l | tr -d ' '
)"
[[ "$WORLD_READABLE" -eq 0 ]]

jq -n \
  --argjson auth "$(jq '{ok,state,checks}' "$OUT/logs/final-auth-doctor.json")" \
  --argjson unexpected_nonce_paths "$UNEXPECTED_NONCE_PATHS" \
  --argjson group_or_world_accessible_files "$WORLD_READABLE" \
  '{
    schema: "oracle-subagent.local-security-audit.v1",
    hard_gate: (
      if (
        $auth.ok == true and
        $auth.state == "ready" and
        $auth.checks.loopback_only == true and
        $auth.checks.exact_target == true and
        $auth.checks.browser_hidden == true and
        $auth.checks.authenticated == true and
        $auth.checks.account_matches == true and
        $auth.checks.project_access == true and
        $unexpected_nonce_paths == 0 and
        $group_or_world_accessible_files == 0
      ) then "pass" else "fail" end
    ),
    browser: {
      loopback_only: $auth.checks.loopback_only,
      exact_target: $auth.checks.exact_target,
      hidden: $auth.checks.browser_hidden,
      authenticated: $auth.checks.authenticated,
      enrolled_account_matches: $auth.checks.account_matches,
      project_access: $auth.checks.project_access
    },
    artifact_scan: {
      unexpected_nonce_paths: $unexpected_nonce_paths,
      group_or_world_accessible_files: $group_or_world_accessible_files
    }
  }' > "$OUT/security-audit.json.tmp"
chmod 600 "$OUT/security-audit.json.tmp"
mv "$OUT/security-audit.json.tmp" "$OUT/security-audit.json"
jq -e '.hard_gate == "pass"' "$OUT/security-audit.json" >/dev/null

CURRENT_PHASE="manifest"
PRO_SHA="$(jq -r '.result_sha256' "$OUT/pro/receipt.json")"
DEEP_SHA="$(jq -r '.result_sha256' "$OUT/deep-research/receipt.json")"
jq -n \
  --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg pro_run_id "$PRO_RUN_ID" \
  --arg deep_run_id "$DEEP_RUN_ID" \
  --arg pro_sha256 "$PRO_SHA" \
  --arg deep_sha256 "$DEEP_SHA" \
  --argjson failures "$(jq -s '.' "$OUT"/failures/*.json)" \
  --argjson security "$(jq '.' "$OUT/security-audit.json")" \
  '{
    schema: "oracle-subagent.local-proof-manifest.v1",
    hard_gates: (
      if (
        ($failures | all(.hard_gate == "pass")) and
        $security.hard_gate == "pass" and
        ($pro_sha256 | test("^[0-9a-f]{64}$")) and
        ($deep_sha256 | test("^[0-9a-f]{64}$")) and
        $pro_sha256 != $deep_sha256
      ) then "pass" else "fail" end
    ),
    generated_at: $generated_at,
    live: {
      pro: {
        run_id: $pro_run_id,
        state: "completed",
        result_sha256: $pro_sha256
      },
      deep_research: {
        run_id: $deep_run_id,
        state: "completed",
        result_sha256: $deep_sha256
      }
    },
    negative_gates: $failures,
    security_audit: "security-audit.json"
  }' > "$OUT/manifest.json.tmp"
chmod 600 "$OUT/manifest.json.tmp"
mv "$OUT/manifest.json.tmp" "$OUT/manifest.json"
jq -e '.hard_gates == "pass"' "$OUT/manifest.json" >/dev/null

jq -n \
  --arg pro_run_id "$PRO_RUN_ID" \
  --arg deep_run_id "$DEEP_RUN_ID" \
  --arg pro_sha256 "$PRO_SHA" \
  --arg deep_sha256 "$DEEP_SHA" \
  '{
    schema: "oracle-subagent.local-proof-receipt.v1",
    hard_gates: "pass",
    pro: {
      run_id: $pro_run_id,
      result_sha256: $pro_sha256
    },
    deep_research: {
      run_id: $deep_run_id,
      result_sha256: $deep_sha256
    }
  }' > "$OUT/receipt.json.tmp"
chmod 600 "$OUT/receipt.json.tmp"
mv "$OUT/receipt.json.tmp" "$OUT/receipt.json"

trap - ERR
jq -c '{
  schema,
  hard_gates,
  pro_run_id: .live.pro.run_id,
  deep_research_run_id: .live.deep_research.run_id
}' "$OUT/manifest.json"
