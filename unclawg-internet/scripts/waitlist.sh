#!/usr/bin/env bash
# Manage signup proof-of-humanity waitlist entries.
# Commands:
#   waitlist.sh list [limit]
#   waitlist.sh detail <approval_id>
#   waitlist.sh approve <approval_id>
#   waitlist.sh deny <approval_id>
#   waitlist.sh ssh-list [limit]

set -euo pipefail

OPENCLAW_API_URL="${OPENCLAW_API_URL:-https://api.unclawg.com}"
WAITLIST_CONTEXT_TYPE="${WAITLIST_CONTEXT_TYPE:-apply_job}"
WAITLIST_ACTION="${WAITLIST_ACTION:-signup:human_proof}"
WAITLIST_RESOURCE_TYPE="${WAITLIST_RESOURCE_TYPE:-signup_request}"

HTTP_STATUS=""
HTTP_BODY=""

usage() {
  cat <<'USAGE'
Usage:
  waitlist.sh list [limit]
  waitlist.sh detail <approval_id>
  waitlist.sh approve <approval_id>
  waitlist.sh deny <approval_id>
  waitlist.sh ssh-list [limit]

Required for API commands:
  OPENCLAW_ACCESS_TOKEN   Human bearer token
  OPENCLAW_TENANT_ID      Tenant id

Optional:
  OPENCLAW_API_URL        Default: https://api.unclawg.com
  OPENCLAW_API_KEY        For self-hosted gateways that do not inject app binding
  OPENCLAW_APP_ID         Optional app id header
  WAITLIST_CONTEXT_TYPE   Default: apply_job
  WAITLIST_ACTION         Default: signup:human_proof
  WAITLIST_RESOURCE_TYPE  Default: signup_request

SSH fallback requires:
  WAITLIST_SSH_HOST
  WAITLIST_DB_CONTAINER
  WAITLIST_DB_USER
  WAITLIST_DB_NAME
USAGE
}

require_env() {
  local key="$1"
  if [[ -z "${!key:-}" ]]; then
    echo "Missing required env var: ${key}" >&2
    exit 1
  fi
}

require_tool() {
  local tool="$1"
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "Missing required tool: ${tool}" >&2
    exit 1
  fi
}

require_api_auth() {
  require_env OPENCLAW_ACCESS_TOKEN
  require_env OPENCLAW_TENANT_ID
}

http_call() {
  local method="$1"
  local path="$2"
  local body="${3-}"
  local response
  local -a args=(
    curl -sS -w "\nHTTP_STATUS:%{http_code}" -X "${method}"
    -H "Authorization: Bearer ${OPENCLAW_ACCESS_TOKEN}"
    -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}"
  )

  if [[ -n "${OPENCLAW_API_KEY:-}" ]]; then
    args+=(-H "X-API-Key: ${OPENCLAW_API_KEY}")
  fi
  if [[ -n "${OPENCLAW_APP_ID:-}" ]]; then
    args+=(-H "X-App-Id: ${OPENCLAW_APP_ID}")
  fi
  if [[ -n "${body}" ]]; then
    args+=(-H "Content-Type: application/json" -d "${body}")
  fi

  response="$("${args[@]}" "${OPENCLAW_API_URL%/}${path}")"
  HTTP_STATUS="$(printf '%s\n' "${response}" | awk -F: '/HTTP_STATUS:/{print $2}' | tail -n1)"
  HTTP_BODY="$(printf '%s\n' "${response}" | sed '/HTTP_STATUS:/d')"
}

ensure_ok() {
  local expected="$1"
  if [[ "${HTTP_STATUS}" != "${expected}" ]]; then
    echo "HTTP ${HTTP_STATUS} (expected ${expected})" >&2
    printf '%s\n' "${HTTP_BODY}" >&2
    exit 1
  fi
}

list_waitlist() {
  local limit="${1:-200}"
  require_api_auth
  require_tool jq
  http_call "GET" "/v0/approval-requests?status=pending&context_type=${WAITLIST_CONTEXT_TYPE}&limit=${limit}"
  ensure_ok "200"

  local rows
  rows="$(printf '%s\n' "${HTTP_BODY}" | jq -r --arg action "${WAITLIST_ACTION}" --arg resource "${WAITLIST_RESOURCE_TYPE}" '
    .data.items // []
    | map(select(.action == $action and .resource_type == $resource))
    | if length == 0 then
        empty
      else
        .[] | [.id, (.resource_id // ""), (.created_at // ""), (.status // "")] | @tsv
      end
  ')"

  if [[ -z "${rows}" ]]; then
    echo "No pending waitlist entries."
    return 0
  fi

  local table
  table="$({
    printf "approval_id\tsignup_email\tcreated_at\tstatus\n"
    printf '%s\n' "${rows}"
  })"

  if command -v column >/dev/null 2>&1; then
    printf '%s\n' "${table}" | column -t -s $'\t'
  else
    printf '%s\n' "${table}"
  fi
}

detail_waitlist() {
  local approval_id="${1:-}"
  if [[ -z "${approval_id}" ]]; then
    usage
    exit 1
  fi
  require_api_auth
  require_tool jq
  http_call "GET" "/v0/approval-requests/${approval_id}"
  ensure_ok "200"
  printf '%s\n' "${HTTP_BODY}" | jq '
    .data
    | {
        id,
        code,
        status,
        version,
        action,
        resource_type,
        signup_email: .resource_id,
        created_at,
        expires_at,
        participants,
        context
      }
  '
}

resolve_waitlist() {
  local approval_id="${1:-}"
  local action="${2:-}"
  if [[ -z "${approval_id}" || -z "${action}" ]]; then
    usage
    exit 1
  fi
  require_api_auth
  require_tool jq

  http_call "GET" "/v0/approval-requests/${approval_id}"
  ensure_ok "200"

  local current_status current_action current_resource version
  current_status="$(printf '%s\n' "${HTTP_BODY}" | jq -r '.data.status // ""')"
  current_action="$(printf '%s\n' "${HTTP_BODY}" | jq -r '.data.action // ""')"
  current_resource="$(printf '%s\n' "${HTTP_BODY}" | jq -r '.data.resource_type // ""')"
  version="$(printf '%s\n' "${HTTP_BODY}" | jq -r '.data.version // empty')"

  if [[ "${current_action}" != "${WAITLIST_ACTION}" || "${current_resource}" != "${WAITLIST_RESOURCE_TYPE}" ]]; then
    echo "Approval ${approval_id} is not a signup waitlist record." >&2
    exit 1
  fi
  if [[ "${current_status}" != "pending" ]]; then
    echo "Approval ${approval_id} is already ${current_status}." >&2
    exit 1
  fi
  if [[ -z "${version}" ]]; then
    echo "Could not read expected version for ${approval_id}." >&2
    exit 1
  fi

  local idempotency_key
  idempotency_key="waitlist-${action}-${approval_id}-$(date +%s)"
  local payload
  payload="$(jq -n --arg action "${action}" --arg key "${idempotency_key}" --argjson version "${version}" '
    {action: $action, expected_version: $version, idempotency_key: $key}
  ')"

  http_call "POST" "/v0/approval-requests/${approval_id}/decisions" "${payload}"
  ensure_ok "200"
  printf '%s\n' "${HTTP_BODY}" | jq '.data | {approval_id, status, version, updated_at}'
}

ssh_list_waitlist() {
  local limit="${1:-200}"
  if [[ ! "${limit}" =~ ^[0-9]+$ ]]; then
    echo "Invalid limit: must be a positive integer" >&2
    exit 1
  fi
  require_tool ssh
  require_env WAITLIST_SSH_HOST
  require_env WAITLIST_DB_CONTAINER
  require_env WAITLIST_DB_USER
  require_env WAITLIST_DB_NAME

  ssh "${WAITLIST_SSH_HOST}" \
    "docker exec ${WAITLIST_DB_CONTAINER} psql -U ${WAITLIST_DB_USER} -d ${WAITLIST_DB_NAME} -P pager=off -c \
    \"SELECT id, resource_id AS signup_email, status, created_at, expires_at
      FROM approval_feedback_v2_approvals
      WHERE action='${WAITLIST_ACTION}'
        AND resource_type='${WAITLIST_RESOURCE_TYPE}'
        AND status='pending'
      ORDER BY created_at DESC
      LIMIT ${limit};\""
}

main() {
  local cmd="${1:-}"
  case "${cmd}" in
    list)
      list_waitlist "${2:-200}"
      ;;
    detail)
      detail_waitlist "${2:-}"
      ;;
    approve)
      resolve_waitlist "${2:-}" "approve"
      ;;
    deny)
      resolve_waitlist "${2:-}" "deny"
      ;;
    ssh-list)
      ssh_list_waitlist "${2:-200}"
      ;;
    ""|-h|--help|help)
      usage
      ;;
    *)
      echo "Unknown command: ${cmd}" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
