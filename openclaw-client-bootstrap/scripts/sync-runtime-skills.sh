#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

SOURCE_DIR_DEFAULT="${REPO_ROOT}/openclaw-client-bootstrap/assets/runtime-skills"
REMOTE_SKILLS_DIR_DEFAULT="/home/openclaw/.openclaw/custom-skills"
REMOTE_CONFIG_PATH_DEFAULT="/home/openclaw/.openclaw/openclaw.json"

HOST="${OPENCLAW_SYNC_HOST:-}"
SSH_USER="${OPENCLAW_SYNC_SSH_USER:-openclaw}"
SSH_PORT="${OPENCLAW_SYNC_SSH_PORT:-22}"
SSH_KEY_PATH="${OPENCLAW_SYNC_SSH_KEY_PATH:-${HOME}/.ssh/id_ed25519}"
KNOWN_HOSTS_PATH="${OPENCLAW_SYNC_KNOWN_HOSTS_PATH:-${HOME}/.ssh/known_hosts}"
SOURCE_DIR="${OPENCLAW_SYNC_SOURCE_DIR:-${SOURCE_DIR_DEFAULT}}"
REMOTE_SKILLS_DIR="${OPENCLAW_SYNC_REMOTE_SKILLS_DIR:-${REMOTE_SKILLS_DIR_DEFAULT}}"
REMOTE_CONFIG_PATH="${OPENCLAW_SYNC_REMOTE_CONFIG_PATH:-${REMOTE_CONFIG_PATH_DEFAULT}}"

DRY_RUN="false"
VERBOSE="false"

usage() {
  cat <<'EOF'
Usage: sync-runtime-skills.sh [options]

Syncs the tracked reusable runtime-safe skills to a live OpenClaw home
with fail-closed, atomic promotion semantics.

Options:
  --host <host>               SSH host or IP (required unless --dry-run)
  --ssh-user <user>           SSH user (default: openclaw)
  --ssh-port <port>           SSH port (default: 22)
  --ssh-key <path>            SSH private key path (default: ~/.ssh/id_ed25519)
  --known-hosts <path>        known_hosts file for strict verification
  --source-dir <path>         Local custom-skills source directory
  --remote-skills-dir <path>  Remote custom-skills directory
  --remote-config <path>      Remote openclaw.json path for parity checks
  --dry-run                   Validate locally only, no network calls
  --verbose                   Print command progress
  -h, --help                  Show this help

Environment variable equivalents:
  OPENCLAW_SYNC_HOST
  OPENCLAW_SYNC_SSH_USER
  OPENCLAW_SYNC_SSH_PORT
  OPENCLAW_SYNC_SSH_KEY_PATH
  OPENCLAW_SYNC_KNOWN_HOSTS_PATH
  OPENCLAW_SYNC_SOURCE_DIR
  OPENCLAW_SYNC_REMOTE_SKILLS_DIR
  OPENCLAW_SYNC_REMOTE_CONFIG_PATH
EOF
}

log() {
  printf '[sync-runtime-skills] %s\n' "$*"
}

die() {
  printf '[sync-runtime-skills] ERROR: %s\n' "$*" >&2
  exit 1
}

require_bin() {
  local bin="$1"
  command -v "${bin}" >/dev/null 2>&1 || die "Missing required binary: ${bin}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:?--host requires a value}"
      shift 2
      ;;
    --ssh-user)
      SSH_USER="${2:?--ssh-user requires a value}"
      shift 2
      ;;
    --ssh-port)
      SSH_PORT="${2:?--ssh-port requires a value}"
      shift 2
      ;;
    --ssh-key)
      SSH_KEY_PATH="${2:?--ssh-key requires a value}"
      shift 2
      ;;
    --known-hosts)
      KNOWN_HOSTS_PATH="${2:?--known-hosts requires a value}"
      shift 2
      ;;
    --source-dir)
      SOURCE_DIR="${2:?--source-dir requires a value}"
      shift 2
      ;;
    --remote-skills-dir)
      REMOTE_SKILLS_DIR="${2:?--remote-skills-dir requires a value}"
      shift 2
      ;;
    --remote-config)
      REMOTE_CONFIG_PATH="${2:?--remote-config requires a value}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    --verbose)
      VERBOSE="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

require_bin find
require_bin sort
require_bin tar
require_bin python3

[[ -d "${SOURCE_DIR}" ]] || die "Source directory not found: ${SOURCE_DIR}"

if find "${SOURCE_DIR}" -mindepth 1 -maxdepth 1 ! -type d | grep -q .; then
  die "Source directory contains non-directory entries; expected only skill directories"
fi

if find "${SOURCE_DIR}" -type l | grep -q .; then
  die "Source directory contains symlinks; refusing to deploy"
fi

mapfile -t SKILL_DIRS < <(find "${SOURCE_DIR}" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort)
[[ "${#SKILL_DIRS[@]}" -gt 0 ]] || die "No skills found in ${SOURCE_DIR}"

for skill_name in "${SKILL_DIRS[@]}"; do
  [[ "${skill_name}" =~ ^[a-z0-9._-]+$ ]] || die "Invalid skill directory name: ${skill_name}"
  skill_file="${SOURCE_DIR}/${skill_name}/SKILL.md"
  [[ -s "${skill_file}" ]] || die "Missing or empty ${skill_file}"

  declared_name="$(awk -F': *' '/^name:/ {print $2; exit}' "${skill_file}" | tr -d '"' | tr -d "'")"
  if [[ -n "${declared_name}" && "${declared_name}" != "${skill_name}" ]]; then
    die "Frontmatter name mismatch in ${skill_file}: expected ${skill_name}, got ${declared_name}"
  fi
done

EXPECTED_SKILLS_CSV="$(IFS=,; echo "${SKILL_DIRS[*]}")"

log "Validated ${#SKILL_DIRS[@]} local skills from ${SOURCE_DIR}"
log "Skill set: ${EXPECTED_SKILLS_CSV}"

if [[ "${DRY_RUN}" == "true" ]]; then
  log "Dry run complete. No remote changes were made."
  exit 0
fi

[[ -n "${HOST}" ]] || die "Missing host. Use --host or OPENCLAW_SYNC_HOST."
[[ -r "${SSH_KEY_PATH}" ]] || die "SSH key not readable: ${SSH_KEY_PATH}"
[[ -r "${KNOWN_HOSTS_PATH}" ]] || die "known_hosts file not readable: ${KNOWN_HOSTS_PATH}"

require_bin ssh
require_bin scp
require_bin mktemp

SSH_OPTS=(
  -o BatchMode=yes
  -o StrictHostKeyChecking=yes
  -o UserKnownHostsFile="${KNOWN_HOSTS_PATH}"
  -o ConnectTimeout=15
  -o ServerAliveInterval=15
  -o ServerAliveCountMax=3
  -i "${SSH_KEY_PATH}"
  -p "${SSH_PORT}"
)

SCP_OPTS=(
  -o BatchMode=yes
  -o StrictHostKeyChecking=yes
  -o UserKnownHostsFile="${KNOWN_HOSTS_PATH}"
  -o ConnectTimeout=15
  -i "${SSH_KEY_PATH}"
  -P "${SSH_PORT}"
)

LOCAL_TAR="$(mktemp "${TMPDIR:-/tmp}/openclaw-runtime-skills.XXXXXX.tar")"
cleanup_local() {
  rm -f "${LOCAL_TAR}"
}
trap cleanup_local EXIT

tar -C "${SOURCE_DIR}" -cf "${LOCAL_TAR}" .

if [[ "${VERBOSE}" == "true" ]]; then
  log "Archive contents:"
  tar -tf "${LOCAL_TAR}" | sed 's/^/[sync-runtime-skills]   /'
fi

REMOTE_TAR="/tmp/openclaw-runtime-skills.$(date +%s).$$.tar"
REMOTE_TARGET="${SSH_USER}@${HOST}"

log "Uploading runtime skill archive to ${REMOTE_TARGET}:${REMOTE_TAR}"
scp "${SCP_OPTS[@]}" "${LOCAL_TAR}" "${REMOTE_TARGET}:${REMOTE_TAR}"

log "Running remote validation and atomic promotion"
# shellcheck disable=SC2029
ssh "${SSH_OPTS[@]}" "${REMOTE_TARGET}" \
  "bash -s -- '${REMOTE_SKILLS_DIR}' '${REMOTE_CONFIG_PATH}' '${REMOTE_TAR}' '${EXPECTED_SKILLS_CSV}'" <<'REMOTE_SCRIPT'
set -euo pipefail

remote_skills_dir="$1"
remote_config_path="$2"
remote_tar="$3"
expected_skills_csv="$4"

die() {
  printf '[remote-sync] ERROR: %s\n' "$*" >&2
  exit 1
}

[[ -f "${remote_tar}" ]] || die "Uploaded tarball not found at ${remote_tar}"
[[ -f "${remote_config_path}" ]] || die "Remote config not found: ${remote_config_path}"

parent_dir="$(dirname "${remote_skills_dir}")"
mkdir -p "${parent_dir}"

tmp_dir="$(mktemp -d "${parent_dir}/.runtime-skills-sync.XXXXXX")"
backup_dir=""
had_backup="0"

cleanup() {
  rm -f "${remote_tar}" || true
  [[ -d "${tmp_dir}" ]] && rm -rf "${tmp_dir}" || true
}
trap cleanup EXIT

tar -xf "${remote_tar}" -C "${tmp_dir}"

if find "${tmp_dir}" -mindepth 1 -maxdepth 1 ! -type d | grep -q .; then
  die "Extracted payload contains non-directory entries"
fi

mapfile -t actual_skills < <(find "${tmp_dir}" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort)
[[ "${#actual_skills[@]}" -gt 0 ]] || die "Extracted payload is empty"

IFS=',' read -r -a expected_skills <<< "${expected_skills_csv}"
for skill_name in "${expected_skills[@]}"; do
  [[ -d "${tmp_dir}/${skill_name}" ]] || die "Missing expected skill directory after extract: ${skill_name}"
  [[ -s "${tmp_dir}/${skill_name}/SKILL.md" ]] || die "Missing SKILL.md in ${skill_name}"
done

python3 - "${remote_config_path}" "${tmp_dir}" "${expected_skills_csv}" <<'PY'
import json
import pathlib
import sys

config_path = pathlib.Path(sys.argv[1])
skills_dir = pathlib.Path(sys.argv[2])
expected = {x for x in sys.argv[3].split(",") if x}

cfg = json.loads(config_path.read_text(encoding="utf-8"))
entries = (((cfg.get("skills") or {}).get("entries")) or {})
enabled = {
    name
    for name, value in entries.items()
    if isinstance(value, dict) and value.get("enabled") is True
}
actual = {p.name for p in skills_dir.iterdir() if p.is_dir()}

if actual != expected:
    print(f"actual skill directories do not match expected set: actual={sorted(actual)} expected={sorted(expected)}", file=sys.stderr)
    sys.exit(20)

if enabled != actual:
    print(f"enabled skill set mismatch with payload: enabled={sorted(enabled)} payload={sorted(actual)}", file=sys.stderr)
    sys.exit(21)
PY

if [[ -d "${remote_skills_dir}" ]]; then
  backup_dir="${remote_skills_dir}.bak.$(date +%Y%m%d%H%M%S)"
  mv "${remote_skills_dir}" "${backup_dir}"
  had_backup="1"
fi

if ! mv "${tmp_dir}" "${remote_skills_dir}"; then
  if [[ "${had_backup}" == "1" && -d "${backup_dir}" ]]; then
    mv "${backup_dir}" "${remote_skills_dir}" || true
  fi
  die "Atomic promote failed; previous skill directory restored"
fi

tmp_dir=""

if [[ "${had_backup}" == "1" && -d "${backup_dir}" ]]; then
  rm -rf "${backup_dir}"
fi

find "${remote_skills_dir}" -type d -exec chmod 755 {} +
find "${remote_skills_dir}" -type f -name SKILL.md -exec chmod 644 {} +

printf '[remote-sync] SYNC_OK skills=%s target=%s\n' "${expected_skills_csv}" "${remote_skills_dir}"
REMOTE_SCRIPT

log "Deployment completed successfully on ${REMOTE_TARGET}"
