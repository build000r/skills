#!/usr/bin/env bash
set -euo pipefail

# Review / grade an openclaw-client-bootstrap skill template, generated kit,
# or LIVE deployed instance via SSH.
#
# Usage:
#   review_kit.sh                          # review the skill template (assets/client-kit)
#   review_kit.sh /path/to/kit             # review a generated kit
#   review_kit.sh --skill                  # explicit: review the skill template
#   review_kit.sh --live                   # SSH into droplet (delegates to review_live.sh)
#   review_kit.sh --live openclaw@<tailscale-ip> # SSH into specific host

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# --- Handle --live by delegating to review_live.sh ---

if [[ "${1:-}" == "--live" ]]; then
  shift
  exec bash "${SCRIPT_DIR}/review_live.sh" "$@"
fi

# --- File-based review ---

PASS=0
FAIL=0
WARNINGS=()

pass() {
  PASS=$((PASS + 1))
  echo "  PASS  $1"
}

fail() {
  FAIL=$((FAIL + 1))
  echo "  FAIL  $1"
}

warn() {
  WARNINGS+=("$1")
  echo "  WARN  $1"
}

TARGET=""
REVIEWING_TEMPLATE="true"

if [[ $# -eq 0 ]] || [[ "${1:-}" == "--skill" ]]; then
  TARGET="${SKILL_DIR}/assets/client-kit"
  REVIEWING_TEMPLATE="true"
elif [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
  head -14 "$0" | tail -9
  exit 0
else
  TARGET="$1"
  REVIEWING_TEMPLATE="false"
fi

if [[ ! -d "${TARGET}" ]]; then
  echo "Directory not found: ${TARGET}"
  exit 1
fi

if [[ "${REVIEWING_TEMPLATE}" == "true" ]]; then
  echo "Reviewing skill template: ${TARGET}"
else
  echo "Reviewing generated kit: ${TARGET}"
fi

echo

# ============================================================
echo "=== 1. Config Schema (openclaw.json) ==="
# ============================================================

CONFIG="${TARGET}/openclaw.json"

if [[ ! -f "${CONFIG}" ]]; then
  fail "1.1 openclaw.json missing"
else
  if command -v jq >/dev/null 2>&1; then
    if jq empty "${CONFIG}" >/dev/null 2>&1; then
      pass "1.1 Valid JSON"
    else
      fail "1.1 Invalid JSON"
    fi

    removed_keys=0
    jq -e '.agents.list[0].prompt' "${CONFIG}" >/dev/null 2>&1 && removed_keys=$((removed_keys + 1)) && echo "       found: agents.list[0].prompt"
    jq -e '.telegram' "${CONFIG}" >/dev/null 2>&1 && removed_keys=$((removed_keys + 1)) && echo "       found: top-level telegram block"
    jq -e '.channels.pairing' "${CONFIG}" >/dev/null 2>&1 && removed_keys=$((removed_keys + 1)) && echo "       found: channels.pairing"
    jq -e '.channels.telegram.token' "${CONFIG}" >/dev/null 2>&1 && removed_keys=$((removed_keys + 1)) && echo "       found: channels.telegram.token"
    if [[ ${removed_keys} -eq 0 ]]; then pass "1.2 No removed keys"; else fail "1.2 Found ${removed_keys} removed key(s)"; fi

    if jq -e '.channels.telegram.botToken // .telegram.botToken' "${CONFIG}" >/dev/null 2>&1; then
      pass "1.3 Uses Telegram botToken"
    else
      fail "1.3 Missing Telegram botToken"
    fi

    ask_type="$(jq -r '.tools.exec.ask | type' "${CONFIG}" 2>/dev/null || echo "null")"
    if [[ "${ask_type}" == "string" ]]; then
      pass "1.4 tools.exec.ask is string"
    else
      fail "1.4 tools.exec.ask is ${ask_type}, should be string"
    fi

    safe_bins_type="$(jq -r '.tools.exec.safeBins | type' "${CONFIG}" 2>/dev/null || echo "null")"
    if [[ "${safe_bins_type}" != "array" ]]; then
      fail "1.4b tools.exec.safeBins must be an array"
    else
      safe_bins_count="$(jq -r '.tools.exec.safeBins | length' "${CONFIG}" 2>/dev/null || echo "0")"
      path_like_bins="$(jq -r '.tools.exec.safeBins[]? | select(test("[/\\\\]"))' "${CONFIG}" 2>/dev/null || true)"
      if [[ "${safe_bins_count}" -lt 1 ]]; then
        fail "1.4b tools.exec.safeBins is empty"
      elif [[ -n "${path_like_bins}" ]]; then
        fail "1.4b tools.exec.safeBins contains path-style entries"
        echo "${path_like_bins}" | sed 's/^/       /'
      else
        pass "1.4b tools.exec.safeBins uses executable names"
      fi
    fi

    if jq -e '.channels.telegram.groupPolicy == "allowlist"' "${CONFIG}" >/dev/null 2>&1 \
      && jq -e '.channels.telegram.groupAllowFrom | type == "array" and length > 0' "${CONFIG}" >/dev/null 2>&1 \
      && jq -e '(.channels.telegram.groups // empty) | ((type == "array" and length > 0) or (type == "object" and (keys | length) > 0))' "${CONFIG}" >/dev/null 2>&1; then
      pass "1.5 Telegram group allowlist policy present"
    else
      fail "1.5 Telegram group allowlist policy missing or incomplete"
    fi

    if jq -e '.approvals.exec.mode' "${CONFIG}" >/dev/null 2>&1; then
      pass "1.6 approvals.exec.mode present"
    else
      fail "1.6 approvals.exec.mode missing"
    fi

    if jq -e '.approvals.exec.targets[0].channel // .approvals.exec.notify[0].channel' "${CONFIG}" >/dev/null 2>&1; then
      pass "1.7 Approval routing target present"
    else
      fail "1.7 Approval routing target missing"
    fi

    target_env_placeholders="$(jq -r '.approvals.exec.targets[]?.to | strings | select(test("^\\$\\{env:"))' "${CONFIG}" 2>/dev/null || true)"
    if [[ -n "${target_env_placeholders}" ]]; then
      fail "1.7b approvals.exec.targets[*].to uses unsupported env interpolation"
      echo "${target_env_placeholders}" | sed 's/^/       /'
    else
      pass "1.7b Approval recipients are concrete values"
    fi

    ws="$(jq -r '.agents.defaults.sandbox.workspaceAccess' "${CONFIG}" 2>/dev/null)"
    if [[ "${ws}" == "ro" ]]; then pass "1.8 Sandbox is read-only"; else fail "1.8 workspaceAccess is '${ws}', expected 'ro'"; fi

    deny_list="$(jq -r '.tools.deny[]?' "${CONFIG}" 2>/dev/null)"
    deny_ok=true
    for tool in write edit apply_patch; do
      if ! echo "${deny_list}" | grep -qx "${tool}"; then
        deny_ok=false
        echo "       missing from tools.deny: ${tool}"
      fi
    done
    if [[ "${deny_ok}" == "true" ]]; then pass "1.9 Write tools denied"; else fail "1.9 Write tools not fully denied"; fi
  else
    warn "1.1-1.9 jq not installed, skipping JSON checks"
  fi

  if grep -q '<YOUR_TELEGRAM_USER_ID>' "${CONFIG}"; then
    fail "1.10 Legacy placeholder <YOUR_TELEGRAM_USER_ID> found"
  else
    pass "1.10 No legacy placeholders"
  fi
fi

echo

# ============================================================
echo "=== 2. Environment (.env.example) ==="
# ============================================================

ENV_FILE="${TARGET}/.env.example"

if [[ ! -f "${ENV_FILE}" ]]; then
  fail "2.0 .env.example missing"
else
  for check in \
    "2.1:OPENCLAW_GATEWAY_TOKEN" \
    "2.2:OPENCLAW_TG_TOKEN" \
    "2.2b:TELEGRAM_GROUP_CHAT_IDS" \
    "2.2c:TELEGRAM_ALLOWED_USER_IDS" \
    "2.3a:SPAPS_API_URL" \
    "2.3b:SPAPS_API_KEY" \
    "2.3c:SPAPS_AGENT_ID" \
    "2.3d:SPAPS_AGENT_SECRET" \
    "2.4:UNCLAWG_PORTAL_URL"; do
    num="${check%%:*}"
    var="${check##*:}"
    if grep -q "^${var}=" "${ENV_FILE}"; then
      pass "${num} ${var} present"
    else
      fail "${num} ${var} missing"
    fi
  done

  if grep -q '^TELEGRAM_APPROVAL_CHAT_ID=' "${ENV_FILE}"; then
    fail "2.5 Legacy TELEGRAM_APPROVAL_CHAT_ID still present"
  else
    pass "2.5 No legacy TELEGRAM_APPROVAL_CHAT_ID"
  fi
fi

echo

# ============================================================
echo "=== 3. Scripts ==="
# ============================================================

syntax_ok=true
for sh_file in "${TARGET}"/scripts/*.sh; do
  if [[ -f "${sh_file}" ]]; then
    if ! bash -n "${sh_file}" 2>/dev/null; then
      syntax_ok=false
      echo "       syntax error: ${sh_file}"
    fi
  fi
done
if [[ "${syntax_ok}" == "true" ]]; then pass "3.1 Shell syntax OK"; else fail "3.1 Shell syntax errors"; fi

BOOTSTRAP="${TARGET}/scripts/01-bootstrap-do.sh"
if [[ -f "${BOOTSTRAP}" ]]; then
  bs_ok=true
  grep -q 'nodesource\|setup_22' "${BOOTSTRAP}" 2>/dev/null || { bs_ok=false; echo "       missing: Node.js install"; }
  grep -q 'docker' "${BOOTSTRAP}" 2>/dev/null || { bs_ok=false; echo "       missing: Docker install"; }
  grep -q 'tmux' "${BOOTSTRAP}" 2>/dev/null || { bs_ok=false; echo "       missing: tmux install"; }
  if [[ "${bs_ok}" == "true" ]]; then pass "3.2 Bootstrap installs Node.js + Docker + tmux"; else fail "3.2 Bootstrap missing prereqs"; fi
else
  fail "3.2 01-bootstrap-do.sh missing"
fi

INSTALL="${TARGET}/scripts/03-install-openclaw.sh"
if [[ -f "${INSTALL}" ]]; then
  prereq_ok=true
  grep -q 'command -v node' "${INSTALL}" 2>/dev/null || { prereq_ok=false; echo "       missing: node check"; }
  grep -q 'command -v docker' "${INSTALL}" 2>/dev/null || { prereq_ok=false; echo "       missing: docker check"; }
  if [[ "${prereq_ok}" == "true" ]]; then pass "3.3 Install script checks prereqs"; else fail "3.3 Install script missing prereq checks"; fi
else
  fail "3.3 03-install-openclaw.sh missing"
fi

TAILSCALE_INSTALL="${TARGET}/scripts/02-install-tailscale.sh"
if [[ -f "${TAILSCALE_INSTALL}" ]]; then
  hardening_ok=true
  grep -q 'PermitRootLogin no' "${TAILSCALE_INSTALL}" 2>/dev/null || { hardening_ok=false; echo "       missing: PermitRootLogin no"; }
  grep -q 'AllowUsers' "${TAILSCALE_INSTALL}" 2>/dev/null || { hardening_ok=false; echo "       missing: AllowUsers"; }
  grep -q 'TAILNET_SSH_CIDR\|tailscale0' "${TAILSCALE_INSTALL}" 2>/dev/null || { hardening_ok=false; echo "       missing: Tailnet SSH rule"; }
  if [[ "${hardening_ok}" == "true" ]]; then
    pass "3.10 Tailscale install enforces Tailnet-only non-root SSH"
  else
    fail "3.10 Tailscale install missing SSH hardening"
  fi
else
  fail "3.10 02-install-tailscale.sh missing"
fi

COLLAB_SCRIPT="${TARGET}/scripts/05-setup-collab-tmux.sh"
if [[ -f "${COLLAB_SCRIPT}" ]]; then
  pass "3.11 Optional tmux collaboration hardening script present"
else
  warn "3.11 Optional tmux collaboration hardening script missing"
fi

if [[ -f "${INSTALL}" ]]; then
  config_line="$(grep -n 'install.*openclaw.json\|install.*\.env' "${INSTALL}" 2>/dev/null | head -1 | cut -d: -f1 || echo 999)"
  cli_line="$(grep -n 'curl.*install\.sh\|openclaw.ai' "${INSTALL}" 2>/dev/null | head -1 | cut -d: -f1 || echo 0)"
  if [[ "${config_line}" -lt "${cli_line}" ]]; then
    pass "3.4 Config pre-placed before CLI install"
  else
    fail "3.4 Config placed after CLI install"
  fi
fi

if [[ -f "${INSTALL}" ]]; then
  if [[ "${REVIEWING_TEMPLATE}" == "true" ]]; then
    if grep -Eq '{{TELEGRAM_ALLOWED_USER_ID}}|{{TELEGRAM_GROUP_CHAT_ID}}' "${INSTALL}" \
      && ! grep -q '<YOUR_TELEGRAM_USER_ID>' "${INSTALL}"; then
      pass "3.5 Install uses new placeholder format"
    else
      fail "3.5 Install uses legacy placeholder format"
    fi
  else
    if grep -q '<YOUR_TELEGRAM_USER_ID>' "${INSTALL}"; then
      fail "3.5 Generated kit still contains legacy placeholder format"
    elif grep -Eq '{{TELEGRAM_ALLOWED_USER_ID}}|{{TELEGRAM_GROUP_CHAT_ID}}' "${INSTALL}"; then
      fail "3.5 Generated kit still contains unresolved placeholder"
    else
      pass "3.5 Install placeholders resolved in generated kit"
    fi
  fi
fi

VALIDATE="${TARGET}/scripts/04-validate.sh"
if [[ -f "${VALIDATE}" ]]; then
  if grep -q 'SPAPS' "${VALIDATE}"; then pass "3.6 Validate checks SPAPS"; else fail "3.6 Validate missing SPAPS check"; fi
  if grep -q 'UNCLAWG\|portal' "${VALIDATE}"; then pass "3.7 Validate checks portal"; else fail "3.7 Validate missing portal check"; fi
  if grep -q 'channels\.telegram\.enabled' "${VALIDATE}"; then
    pass "3.8 Validate checks channels.telegram.enabled"
  elif grep -q 'telegram\.enabled' "${VALIDATE}"; then
    warn "3.8 Validate uses legacy telegram.enabled path"
  else
    fail "3.8 Validate missing Telegram config check"
  fi
  if grep -q 'approvals\.exec\.targets' "${VALIDATE}" && grep -q '\${env:' "${VALIDATE}"; then
    pass "3.9 Validate enforces concrete approval recipients"
  else
    fail "3.9 Validate missing approval recipient sanity check"
  fi
else
  fail "3.6 04-validate.sh missing"
fi

echo

# ============================================================
echo "=== 4. Documentation Consistency ==="
# ============================================================

DOC_FILES=()
for f in \
  "${TARGET}/README.md" \
  "${TARGET}/AGENTS.md" \
  "${TARGET}/checklists/FIRST_CLAW_CHECKLIST.md" \
  "${TARGET}/checklists/OPERATOR_RUNBOOK.md" \
  "${TARGET}/security/WRITE_GATEWAY_CONTRACT.md" \
  "${TARGET}/security/PERMISSIONS_PLAYBOOK.md"; do
  [[ -f "${f}" ]] && DOC_FILES+=("${f}")
done

if [[ "${REVIEWING_TEMPLATE}" == "true" ]]; then
  for f in \
    "${SKILL_DIR}/SKILL.md" \
    "${SKILL_DIR}/references/deployment-workflow.md" \
    "${SKILL_DIR}/references/read-only-governance.md"; do
    [[ -f "${f}" ]] && DOC_FILES+=("${f}")
  done
fi

tg_approval_refs=0
for f in "${DOC_FILES[@]}"; do
  matches="$(grep -ni 'telegram.*approval.*chat\|approve.*reject.*telegram\|telegram.*inline.*approv\|approval.*route.*telegram' "${f}" 2>/dev/null || true)"
  if [[ -n "${matches}" ]]; then
    filtered="$(echo "${matches}" | grep -vi 'never\|not\|sends.*link\|notification\|portal' || true)"
    if [[ -n "${filtered}" ]]; then
      tg_approval_refs=$((tg_approval_refs + 1))
      echo "       ${f##*/}: describes Telegram as approval surface"
    fi
  fi
done
if [[ ${tg_approval_refs} -eq 0 ]]; then pass "4.1 Architecture aligned"; else fail "4.1 ${tg_approval_refs} doc(s) describe Telegram as approval surface"; fi

spaps_count=0
for f in "${DOC_FILES[@]}"; do
  grep -qi 'SPAPS' "${f}" 2>/dev/null && spaps_count=$((spaps_count + 1))
done
if [[ ${spaps_count} -ge 3 ]]; then pass "4.2 SPAPS referenced in ${spaps_count} docs"; else fail "4.2 SPAPS only in ${spaps_count} doc(s)"; fi

portal_count=0
for f in "${DOC_FILES[@]}"; do
  grep -qi 'unclawg\|portal' "${f}" 2>/dev/null && portal_count=$((portal_count + 1))
done
if [[ ${portal_count} -ge 3 ]]; then pass "4.3 Portal referenced in ${portal_count} docs"; else fail "4.3 Portal only in ${portal_count} doc(s)"; fi

legacy_placeholder_docs=0
for f in "${DOC_FILES[@]}"; do
  if grep -q '<YOUR_TELEGRAM_USER_ID>' "${f}" 2>/dev/null; then
    legacy_placeholder_docs=$((legacy_placeholder_docs + 1))
    echo "       ${f##*/}: uses legacy placeholder"
  fi
done
if [[ ${legacy_placeholder_docs} -eq 0 ]]; then pass "4.4 Placeholder format consistent"; else fail "4.4 ${legacy_placeholder_docs} doc(s) use legacy placeholder"; fi

bad_spec_docs=0
for f in "${DOC_FILES[@]}"; do
  if grep -qi '1.*GB.*RAM\|minimum.*1.*GB\|1 GB' "${f}" 2>/dev/null; then
    if ! grep -qi '2.*GB\|4.*GB' "${f}" 2>/dev/null; then
      bad_spec_docs=$((bad_spec_docs + 1))
    fi
  fi
done
if [[ ${bad_spec_docs} -eq 0 ]]; then pass "4.5 Min spec is 2GB+"; else fail "4.5 ${bad_spec_docs} doc(s) reference 1GB minimum"; fi

legacy_chat_id=0
for f in "${DOC_FILES[@]}"; do
  if grep -q 'TELEGRAM_APPROVAL_CHAT_ID' "${f}" 2>/dev/null; then
    legacy_chat_id=$((legacy_chat_id + 1))
  fi
done
if [[ ${legacy_chat_id} -eq 0 ]]; then pass "4.6 No TELEGRAM_APPROVAL_CHAT_ID references"; else fail "4.6 ${legacy_chat_id} doc(s) reference removed variable"; fi

channels_pairing=0
for f in "${DOC_FILES[@]}"; do
  matches="$(grep -n 'channels\.pairing\|channels.pairing' "${f}" 2>/dev/null || true)"
  filtered="$(echo "${matches}" | grep -vi 'not.*valid\|removed\|is not\|use.*instead\|use.*dmPolicy' || true)"
  if [[ -n "${filtered}" ]]; then
    channels_pairing=$((channels_pairing + 1))
  fi
done
if [[ ${channels_pairing} -eq 0 ]]; then pass "4.7 No channels.pairing references"; else fail "4.7 ${channels_pairing} doc(s) reference removed config"; fi

tools_elevated=0
for f in "${DOC_FILES[@]}"; do
  matches="$(grep -n 'allowWhenRequestedBy\|tools\.elevated\.require' "${f}" 2>/dev/null || true)"
  filtered="$(echo "${matches}" | grep -vi 'not.*recognized\|removed\|is not\|no longer\|legacy' || true)"
  if [[ -n "${filtered}" ]]; then
    tools_elevated=$((tools_elevated + 1))
  fi
done
if [[ ${tools_elevated} -eq 0 ]]; then pass "4.8 No legacy tools.elevated references"; else fail "4.8 ${tools_elevated} doc(s) reference legacy elevated keys"; fi

echo

# ============================================================
echo "=== 5. Generator (new_client_kit.sh) ==="
# ============================================================

GEN="${SKILL_DIR}/scripts/new_client_kit.sh"
if [[ "${REVIEWING_TEMPLATE}" != "true" ]]; then
  warn "5.x Skipping generator checks"
else
  if [[ ! -f "${GEN}" ]]; then
    fail "5.0 new_client_kit.sh missing"
  else
    if grep -q '\-\-interactive' "${GEN}"; then pass "5.1 Supports --interactive"; else fail "5.1 Missing --interactive flag"; fi

    spaps_flags=true
    for flag in spaps-url spaps-key spaps-agent-id spaps-secret; do
      if ! grep -q "\-\-${flag}" "${GEN}"; then
        spaps_flags=false
      fi
    done
    if [[ "${spaps_flags}" == "true" ]]; then pass "5.2 SPAPS flags present"; else fail "5.2 Missing SPAPS flags"; fi

    if grep -q '{{TELEGRAM_ALLOWED_USER_ID}}' "${GEN}" \
      && grep -q '{{TELEGRAM_GROUP_CHAT_ID}}' "${GEN}" \
      && grep -q '{{CLIENT_NAME}}' "${GEN}"; then
      pass "5.3 Substitutes placeholders"
    else
      fail "5.3 Missing placeholder substitution"
    fi

    if grep -q 'Substitution Summary\|Filled\|remaining' "${GEN}"; then
      pass "5.4 Shows substitution summary"
    else
      fail "5.4 Missing summary output"
    fi

    if grep -q 'remaining_markers\|remaining.*{{' "${GEN}"; then
      pass "5.5 Reports remaining markers"
    else
      fail "5.5 Missing remaining marker report"
    fi
  fi
fi

echo

# ============================================================
echo "=== 6. Validator (validate_client_kit.sh) ==="
# ============================================================

VAL="${SKILL_DIR}/scripts/validate_client_kit.sh"
if [[ "${REVIEWING_TEMPLATE}" != "true" ]]; then
  warn "6.x Skipping validator checks"
else
  if [[ ! -f "${VAL}" ]]; then
    fail "6.0 validate_client_kit.sh missing"
  else
    schema_checks=true
    for pattern in 'agents.*prompt\|\.prompt' 'channels.*pairing\|pairing' 'channels\.telegram\.token' 'groupPolicy' 'groupAllowFrom' 'tools\.elevated\.enabled'; do
      if ! grep -q "${pattern}" "${VAL}" 2>/dev/null; then
        schema_checks=false
      fi
    done
    if [[ "${schema_checks}" == "true" ]]; then pass "6.1 Schema checks for removed keys"; else fail "6.1 Missing schema checks"; fi

    if grep -q 'ask.*type\|type.*ask\|ask_type' "${VAL}"; then pass "6.2 Checks exec.ask type"; else fail "6.2 Missing exec.ask type check"; fi
    if grep -q 'safeBins\|safe_bins' "${VAL}" && grep -q 'test(\"\\[/\\\\\\\\\\]\\\")\|path separators\|path-style' "${VAL}"; then
      pass "6.2b Checks exec.safeBins semantics"
    else
      fail "6.2b Missing exec.safeBins semantic checks"
    fi
    if grep -q 'PermitRootLogin no' "${VAL}" && grep -q 'AllowUsers' "${VAL}" && grep -q 'Tailnet SSH firewall rule\|TAILNET_SSH_CIDR' "${VAL}"; then
      pass "6.2d Checks SSH hardening expectations"
    else
      fail "6.2d Missing SSH hardening checks"
    fi
    if grep -q 'spaps-api-key\|replace-with-spaps\|SPAPS_API_KEY' "${VAL}"; then pass "6.3 SPAPS placeholder checks"; else fail "6.3 Missing SPAPS checks"; fi
    if grep -q '{{' "${VAL}"; then pass "6.4 Template marker catch-all"; else fail "6.4 Missing marker check"; fi
    if grep -q '<YOUR_TELEGRAM_USER_ID>' "${VAL}"; then pass "6.5 Catches legacy placeholder"; else fail "6.5 Missing legacy check"; fi
  fi
fi

echo

# ============================================================
echo "========================================="
echo "           REVIEW RESULTS"
echo "========================================="
echo
TOTAL=$((PASS + FAIL))
echo "  Passed: ${PASS}/${TOTAL}"
echo "  Failed: ${FAIL}/${TOTAL}"
if [[ ${#WARNINGS[@]} -gt 0 ]]; then
  echo "  Warnings: ${#WARNINGS[@]}"
fi
echo
if [[ ${TOTAL} -gt 0 ]]; then
  pct=$(( (PASS * 100) / TOTAL ))
  if [[ ${FAIL} -eq 0 ]]; then
    echo "  Grade: PASS -- ${pct}%"
  elif [[ ${pct} -ge 90 ]]; then
    echo "  Grade: MINOR GAPS -- ${pct}%"
  elif [[ ${pct} -ge 80 ]]; then
    echo "  Grade: NEEDS ANOTHER PASS -- ${pct}%"
  else
    echo "  Grade: SIGNIFICANT REWORK -- ${pct}%"
  fi
fi

exit "${FAIL}"
