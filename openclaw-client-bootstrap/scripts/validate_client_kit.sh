#!/usr/bin/env bash
set -euo pipefail

DEST="${1:-.}"
ERRORS=0

required_files=(
  "openclaw.json"
  ".env.example"
  "SOUL.md"
  "AGENTS.md"
  "USER.md"
  "checklists/FIRST_CLAW_CHECKLIST.md"
  "checklists/OPERATOR_RUNBOOK.md"
  "security/WRITE_GATEWAY_CONTRACT.md"
  "security/PERMISSIONS_PLAYBOOK.md"
  "scripts/01-bootstrap-do.sh"
  "scripts/02-install-tailscale.sh"
  "scripts/03-install-openclaw.sh"
  "scripts/04-validate.sh"
  "scripts/05-setup-collab-tmux.sh"
)

echo "=== File existence checks ==="

for rel in "${required_files[@]}"; do
  if [[ ! -f "${DEST}/${rel}" ]]; then
    echo "FAIL: Missing file: ${DEST}/${rel}"
    ERRORS=$((ERRORS + 1))
  fi
done

echo "=== JSON validity and schema checks ==="

if [[ -f "${DEST}/openclaw.json" ]]; then
  if command -v jq >/dev/null 2>&1; then
    if ! jq empty "${DEST}/openclaw.json" >/dev/null 2>&1; then
      echo "FAIL: Invalid JSON: ${DEST}/openclaw.json"
      ERRORS=$((ERRORS + 1))
    else
      # Check for removed/invalid keys that indicate outdated config.
      if jq -e '.agents.list[0].prompt' "${DEST}/openclaw.json" >/dev/null 2>&1; then
        echo "FAIL: agents.list[0].prompt is no longer valid in v2026.2.15"
        ERRORS=$((ERRORS + 1))
      fi
      if jq -e '.channels.pairing' "${DEST}/openclaw.json" >/dev/null 2>&1; then
        echo "FAIL: channels.pairing is removed; use channels.telegram group policy fields"
        ERRORS=$((ERRORS + 1))
      fi
      if jq -e '.channels.telegram.token' "${DEST}/openclaw.json" >/dev/null 2>&1; then
        echo "FAIL: channels.telegram.token renamed to channels.telegram.botToken"
        ERRORS=$((ERRORS + 1))
      fi
      if jq -e '.telegram' "${DEST}/openclaw.json" >/dev/null 2>&1; then
        echo "FAIL: top-level telegram block is legacy; use channels.telegram"
        ERRORS=$((ERRORS + 1))
      fi
      if jq -e '.channels.telegram.dmPolicy' "${DEST}/openclaw.json" >/dev/null 2>&1; then
        echo "FAIL: channels.telegram.dmPolicy is out of scope for group-only runtime mode"
        ERRORS=$((ERRORS + 1))
      fi
      if ! jq -e '.channels.telegram.groupPolicy == "allowlist"' "${DEST}/openclaw.json" >/dev/null 2>&1; then
        echo "FAIL: channels.telegram.groupPolicy must be \"allowlist\""
        ERRORS=$((ERRORS + 1))
      fi
      if ! jq -e '.channels.telegram.groupAllowFrom | type == "array" and length > 0' "${DEST}/openclaw.json" >/dev/null 2>&1; then
        echo "FAIL: channels.telegram.groupAllowFrom must be a non-empty array"
        ERRORS=$((ERRORS + 1))
      fi
      if ! jq -e '.channels.telegram.groups | type == "object" and (keys | length) > 0' "${DEST}/openclaw.json" >/dev/null 2>&1; then
        echo "FAIL: channels.telegram.groups must be a non-empty object keyed by chatId"
        ERRORS=$((ERRORS + 1))
      fi
      if ! jq -e 'all(.channels.telegram.groups | keys[]?; (type == "string" and length > 0))' "${DEST}/openclaw.json" >/dev/null 2>&1; then
        echo "FAIL: every channels.telegram.groups key must be a non-empty chatId string"
        ERRORS=$((ERRORS + 1))
      fi
      if ! jq -e '.tools.elevated.enabled == true' "${DEST}/openclaw.json" >/dev/null 2>&1; then
        echo "FAIL: tools.elevated.enabled must be true"
        ERRORS=$((ERRORS + 1))
      fi
      if ! jq -e '.tools.elevated.allowFrom.telegram | type == "array" and length > 0' "${DEST}/openclaw.json" >/dev/null 2>&1; then
        echo "FAIL: tools.elevated.allowFrom.telegram must be a non-empty array"
        ERRORS=$((ERRORS + 1))
      fi
      if jq -e '.approvals.exec.spaps' "${DEST}/openclaw.json" >/dev/null 2>&1; then
        echo "FAIL: approvals.exec.spaps is legacy; use approvals.exec.targets forwarding"
        ERRORS=$((ERRORS + 1))
      fi
      targets_count="$(jq -r '.approvals.exec.targets | length' "${DEST}/openclaw.json" 2>/dev/null || echo "0")"
      if [[ "${targets_count}" -lt 1 ]]; then
        echo "FAIL: approvals.exec.targets must include at least one target"
        ERRORS=$((ERRORS + 1))
      fi
      target_env_placeholders="$(jq -r '.approvals.exec.targets[]?.to | strings | select(test("^\\$\\{env:"))' "${DEST}/openclaw.json" 2>/dev/null || true)"
      if [[ -n "${target_env_placeholders}" ]]; then
        echo "FAIL: approvals.exec.targets[*].to uses unsupported env interpolation (use concrete ID):"
        echo "${target_env_placeholders}" | sed 's/^/  - /'
        ERRORS=$((ERRORS + 1))
      fi

      # Check that tools.exec.ask is a string, not an array.
      ask_type="$(jq -r '.tools.exec.ask | type' "${DEST}/openclaw.json" 2>/dev/null || echo "null")"
      if [[ "${ask_type}" == "array" ]]; then
        echo "FAIL: tools.exec.ask must be a string (e.g. \"always\"), not an array"
        ERRORS=$((ERRORS + 1))
      fi

      # Check safeBins shape and semantics (must be executable names, not paths).
      safe_bins_type="$(jq -r '.tools.exec.safeBins | type' "${DEST}/openclaw.json" 2>/dev/null || echo "null")"
      if [[ "${safe_bins_type}" != "array" ]]; then
        echo "FAIL: tools.exec.safeBins must be an array of executable names"
        ERRORS=$((ERRORS + 1))
      else
        safe_bins_count="$(jq -r '.tools.exec.safeBins | length' "${DEST}/openclaw.json" 2>/dev/null || echo "0")"
        if [[ "${safe_bins_count}" -lt 1 ]]; then
          echo "FAIL: tools.exec.safeBins must include at least one executable name"
          ERRORS=$((ERRORS + 1))
        fi
        path_like_bins="$(jq -r '.tools.exec.safeBins[]? | select(test("[/\\\\]"))' "${DEST}/openclaw.json" 2>/dev/null || true)"
        if [[ -n "${path_like_bins}" ]]; then
          echo "FAIL: tools.exec.safeBins entries must be executable names (no path separators):"
          echo "${path_like_bins}" | sed 's/^/  - /'
          ERRORS=$((ERRORS + 1))
        fi
      fi
    fi
  fi

  # Placeholder checks.
  if grep -q '{{TELEGRAM_ALLOWED_USER_ID}}' "${DEST}/openclaw.json"; then
    echo "FAIL: Placeholder still present in openclaw.json: {{TELEGRAM_ALLOWED_USER_ID}}"
    ERRORS=$((ERRORS + 1))
  fi
  if grep -q '{{TELEGRAM_GROUP_CHAT_ID}}' "${DEST}/openclaw.json"; then
    echo "FAIL: Placeholder still present in openclaw.json: {{TELEGRAM_GROUP_CHAT_ID}}"
    ERRORS=$((ERRORS + 1))
  fi
  # Catch legacy placeholder format.
  if grep -q '<YOUR_TELEGRAM_USER_ID>' "${DEST}/openclaw.json"; then
    echo "FAIL: Legacy placeholder in openclaw.json: <YOUR_TELEGRAM_USER_ID>"
    ERRORS=$((ERRORS + 1))
  fi
fi

echo "=== Template marker check ==="

# Catch unresolved {{...}} template markers across all kit files.
# Exclude USER.md — its placeholders are intentionally filled per-client.
# Allow known runtime placeholders used by media CLI tooling.
unresolved_markers=""
while IFS= read -r file; do
  tokens="$(grep -oE '\{\{[^}]+\}\}' "${file}" 2>/dev/null | sort -u || true)"
  if [[ -z "${tokens}" ]]; then
    continue
  fi
  while IFS= read -r token; do
    case "${token}" in
      "{{Body}}"|"{{RawBody}}"|"{{BodyStripped}}"|"{{From}}"|"{{To}}"|"{{MessageSid}}"|"{{SessionId}}"|"{{IsNewSession}}"|"{{MediaUrl}}"|"{{MediaPath}}"|"{{MediaType}}"|"{{Transcript}}"|"{{Prompt}}"|"{{MaxChars}}"|"{{ChatType}}"|"{{GroupSubject}}"|"{{GroupMembers}}"|"{{SenderName}}"|"{{SenderE164}}"|"{{Provider}}")
        ;;
      *)
        unresolved_markers="${unresolved_markers}${file}: ${token}"$'\n'
        ;;
    esac
  done <<< "${tokens}"
done < <(find "${DEST}" -type f \( -name '*.json' -o -name '*.md' -o -name '*.sh' \) ! -name 'USER.md' 2>/dev/null)

if [[ -n "${unresolved_markers}" ]]; then
  echo "FAIL: Unfilled {{...}} template markers found:"
  echo "${unresolved_markers}"
  ERRORS=$((ERRORS + 1))
fi

echo "=== Environment file checks ==="

if [[ -f "${DEST}/.env.example" ]]; then
  if ! grep -q '^TELEGRAM_GROUP_CHAT_IDS=' "${DEST}/.env.example"; then
    echo "FAIL: .env.example missing TELEGRAM_GROUP_CHAT_IDS"
    ERRORS=$((ERRORS + 1))
  fi
  if ! grep -q '^TELEGRAM_ALLOWED_USER_IDS=' "${DEST}/.env.example"; then
    echo "FAIL: .env.example missing TELEGRAM_ALLOWED_USER_IDS"
    ERRORS=$((ERRORS + 1))
  fi
fi

if [[ -f "${DEST}/.env" ]]; then
  if grep -q "replace-with-64-plus-random-chars" "${DEST}/.env"; then
    echo "FAIL: OPENCLAW_GATEWAY_TOKEN still using placeholder value"
    ERRORS=$((ERRORS + 1))
  fi
  if grep -q "replace-with-real-bot-token" "${DEST}/.env"; then
    echo "FAIL: OPENCLAW_TG_TOKEN still using placeholder value"
    ERRORS=$((ERRORS + 1))
  fi
  if grep -q "replace-with-spaps-api-key" "${DEST}/.env"; then
    echo "FAIL: SPAPS_API_KEY still using placeholder value"
    ERRORS=$((ERRORS + 1))
  fi
  if grep -q "replace-with-spaps-agent-id" "${DEST}/.env"; then
    echo "FAIL: SPAPS_AGENT_ID still using placeholder value"
    ERRORS=$((ERRORS + 1))
  fi
  if grep -q "replace-with-spaps-agent-secret" "${DEST}/.env"; then
    echo "FAIL: SPAPS_AGENT_SECRET still using placeholder value"
    ERRORS=$((ERRORS + 1))
  fi
fi

echo "=== Shell syntax checks ==="

for sh_file in "${DEST}"/scripts/*.sh; do
  if ! bash -n "${sh_file}"; then
    echo "FAIL: Shell syntax failed: ${sh_file}"
    ERRORS=$((ERRORS + 1))
  fi
done

echo "=== SSH hardening script checks ==="

if [[ -f "${DEST}/scripts/02-install-tailscale.sh" ]]; then
  if ! grep -q 'PermitRootLogin no' "${DEST}/scripts/02-install-tailscale.sh"; then
    echo "FAIL: 02-install-tailscale.sh missing PermitRootLogin no hardening"
    ERRORS=$((ERRORS + 1))
  fi
  if ! grep -q 'AllowUsers' "${DEST}/scripts/02-install-tailscale.sh"; then
    echo "FAIL: 02-install-tailscale.sh missing AllowUsers hardening"
    ERRORS=$((ERRORS + 1))
  fi
  if ! grep -q '100\.64\.0\.0/10\|TAILNET_SSH_CIDR' "${DEST}/scripts/02-install-tailscale.sh"; then
    echo "FAIL: 02-install-tailscale.sh missing Tailnet SSH firewall rule"
    ERRORS=$((ERRORS + 1))
  fi
fi

echo "=== Results ==="

if [[ "${ERRORS}" -gt 0 ]]; then
  echo "Validation failed with ${ERRORS} error(s)."
  exit 1
fi

echo "Client kit validation passed: ${DEST}"
