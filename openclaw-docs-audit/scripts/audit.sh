#!/usr/bin/env bash
# openclaw-docs-audit/scripts/audit.sh
#
# Fetch latest OpenClaw releases + config schema docs, compare against
# a local openclaw-client-bootstrap skill, and produce a ranked drift report.
#
# Usage:
#   bash audit.sh                              # auto-detect skill path
#   bash audit.sh --skill-path /path/to/skill  # explicit skill root
#   bash audit.sh --since v2026.2.17           # only releases after this tag
#   bash audit.sh --releases 5                 # how many releases to fetch (default: 10)
#   bash audit.sh --json                       # machine-readable output
#   bash audit.sh --instances                  # also audit deployed instance configs
#   bash audit.sh --help

set -euo pipefail

# --- defaults ---
SKILL_PATH=""
SINCE_TAG=""
NUM_RELEASES=10
JSON_OUT=false
AUDIT_INSTANCES=false
REPO="openclaw/openclaw"
DOCS_URL="https://docs.openclaw.ai/gateway/configuration-reference"
OUTDIR=""

usage() {
  cat <<'EOF'
openclaw-docs-audit — upstream drift checker

Usage:
  audit.sh [OPTIONS]

Options:
  --skill-path PATH   Path to openclaw-client-bootstrap skill root
  --since TAG         Only show changes after this release tag (e.g. v2026.2.17)
  --releases N        Number of releases to fetch (default: 10)
  --instances         Also audit assets/instances/* configs
  --json              Machine-readable JSON output
  --help              This message

When --skill-path is omitted, searches:
  ~/.claude/skills/openclaw-client-bootstrap
  ~/.codex/skills/openclaw-client-bootstrap
  ./openclaw-client-bootstrap (sibling in same repo)
EOF
  exit 0
}

# --- parse args ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skill-path) SKILL_PATH="$2"; shift 2 ;;
    --since)      SINCE_TAG="$2"; shift 2 ;;
    --releases)   NUM_RELEASES="$2"; shift 2 ;;
    --json)       JSON_OUT=true; shift ;;
    --instances)  AUDIT_INSTANCES=true; shift ;;
    --help|-h)    usage ;;
    *) echo "Unknown option: $1" >&2; usage ;;
  esac
done

# --- locate skill ---
if [[ -z "$SKILL_PATH" ]]; then
  for candidate in \
    "$HOME/.claude/skills/openclaw-client-bootstrap" \
    "$HOME/.codex/skills/openclaw-client-bootstrap" \
    "$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)/../openclaw-client-bootstrap" \
    ; do
    if [[ -f "$candidate/SKILL.md" ]]; then
      SKILL_PATH="$candidate"
      break
    fi
  done
fi

if [[ -z "$SKILL_PATH" || ! -f "$SKILL_PATH/SKILL.md" ]]; then
  echo "ERROR: Could not find openclaw-client-bootstrap skill." >&2
  echo "Use --skill-path to specify location." >&2
  exit 1
fi

echo "=== OpenClaw Docs Audit ==="
echo "Skill path: $SKILL_PATH"

# --- prereqs ---
for cmd in gh jq; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "ERROR: $cmd is required but not found." >&2
    exit 1
  fi
done

# --- temp workspace ---
OUTDIR="$(mktemp -d)"
trap 'rm -rf "$OUTDIR"' EXIT

# --- 1. Fetch releases ---
echo ""
echo "--- Fetching latest $NUM_RELEASES releases from $REPO ---"
gh release list --repo "$REPO" --limit "$NUM_RELEASES" --json tagName,name,publishedAt,isPrerelease \
  > "$OUTDIR/releases.json" 2>/dev/null || {
    echo "WARN: Could not fetch releases (network/auth issue)." >&2
    echo "[]" > "$OUTDIR/releases.json"
  }

LATEST_TAG=$(jq -r '.[0].tagName // "unknown"' "$OUTDIR/releases.json")
echo "Latest release: $LATEST_TAG"

# --- 2. Read local pinned version ---
TEMPLATE_CONFIG="$SKILL_PATH/assets/client-kit/openclaw.json"
if [[ -f "$TEMPLATE_CONFIG" ]]; then
  LOCAL_VERSION=$(jq -r '.meta.lastTouchedVersion // "unknown"' "$TEMPLATE_CONFIG")
else
  LOCAL_VERSION="unknown"
  echo "WARN: No template openclaw.json found at $TEMPLATE_CONFIG"
fi
echo "Local pinned version: $LOCAL_VERSION"

# strip leading 'v' for comparison
LATEST_CLEAN="${LATEST_TAG#v}"
LOCAL_CLEAN="${LOCAL_VERSION#v}"

if [[ "$LATEST_CLEAN" == "$LOCAL_CLEAN" ]]; then
  echo "STATUS: Template is current with latest release."
elif [[ "$LOCAL_VERSION" == "unknown" ]]; then
  echo "STATUS: Cannot determine local version."
else
  echo "STATUS: DRIFT DETECTED — local $LOCAL_VERSION vs upstream $LATEST_TAG"
fi

# --- 3. Fetch release notes for versions after SINCE_TAG ---
SINCE="${SINCE_TAG:-v$LOCAL_CLEAN}"
echo ""
echo "--- Release notes since $SINCE ---"

# get tags newer than SINCE
NEWER_TAGS=$(jq -r --arg since "${SINCE#v}" \
  '[.[] | select(.isPrerelease == false) | .tagName] | map(ltrimstr("v")) | map(select(. > $since)) | map("v" + .) | .[]' \
  "$OUTDIR/releases.json" 2>/dev/null || true)

if [[ -z "$NEWER_TAGS" ]]; then
  echo "No new stable releases found after $SINCE."
  echo "(Latest: $LATEST_TAG, Pinned: $LOCAL_VERSION)"
else
  echo "$NEWER_TAGS" | while read -r tag; do
    echo ""
    echo "=== $tag ==="
    gh release view "$tag" --repo "$REPO" --json body -q '.body' 2>/dev/null \
      | head -100 || echo "(could not fetch)"
  done > "$OUTDIR/release_notes.txt"

  RELEASE_COUNT=$(echo "$NEWER_TAGS" | wc -l | tr -d ' ')
  echo "Fetched notes for $RELEASE_COUNT release(s). Saved to temp."
fi

# --- 4. Extract local config keys ---
echo ""
echo "--- Analyzing local template config ---"

if [[ -f "$TEMPLATE_CONFIG" ]]; then
  # extract all leaf keys as dot-notation paths
  jq -r '[paths(scalars)] | map(map(tostring) | join(".")) | sort | .[]' \
    "$TEMPLATE_CONFIG" > "$OUTDIR/local_keys.txt"

  LOCAL_KEY_COUNT=$(wc -l < "$OUTDIR/local_keys.txt" | tr -d ' ')
  echo "Template config has $LOCAL_KEY_COUNT leaf keys."

  # known-bad keys from SKILL.md schema notes
  echo ""
  echo "--- Schema violation check (known removed/invalid keys) ---"
  REMOVED_KEYS=(
    "channels.pairing"
    "channels.telegram.token"
    "tools.policyMode"
    "tools.exec.fallback"
    "tools.exec.rules"
    "tools.elevated.require"
    "tools.elevated.allowWhenRequestedBy"
    "agents.defaults.model.reasoningEffort"
  )
  VIOLATIONS=0
  for key in "${REMOVED_KEYS[@]}"; do
    if grep -q "^${key}" "$OUTDIR/local_keys.txt" 2>/dev/null; then
      echo "  BREAKING: Removed key present: $key"
      VIOLATIONS=$((VIOLATIONS + 1))
    fi
  done

  if [[ $VIOLATIONS -eq 0 ]]; then
    echo "  OK: No known removed keys found in template."
  fi
fi

# --- 5. Audit instances ---
if [[ "$AUDIT_INSTANCES" == "true" ]]; then
  echo ""
  echo "--- Auditing deployed instance configs ---"
  INSTANCES_DIR="$SKILL_PATH/assets/instances"
  if [[ -d "$INSTANCES_DIR" ]]; then
    for instance_dir in "$INSTANCES_DIR"/*/; do
      instance_name=$(basename "$instance_dir")
      instance_config="$instance_dir/openclaw.json"
      if [[ -f "$instance_config" ]]; then
        inst_version=$(jq -r '.meta.lastTouchedVersion // "unknown"' "$instance_config")
        inst_model=$(jq -r '.agents.defaults.model.primary // "unset"' "$instance_config")
        inst_ask=$(jq -r '.tools.exec.ask // "unset"' "$instance_config")
        inst_safebins=$(jq -r '.tools.exec.safeBins // [] | length' "$instance_config")
        inst_approvals=$(jq -r '.approvals.exec.enabled // false' "$instance_config")

        echo ""
        echo "  Instance: $instance_name"
        echo "    Version: $inst_version (latest: $LATEST_CLEAN)"
        echo "    Model: $inst_model"
        echo "    Ask mode: $inst_ask"
        echo "    SafeBins count: $inst_safebins"
        echo "    Approvals enabled: $inst_approvals"

        if [[ "$inst_version" != "$LATEST_CLEAN" ]]; then
          echo "    STATUS: DRIFT — $inst_version vs $LATEST_CLEAN"
        fi

        # check for removed keys in instance
        inst_keys=$(jq -r '[paths(scalars)] | map(map(tostring) | join(".")) | .[]' "$instance_config")
        for key in "${REMOVED_KEYS[@]}"; do
          if echo "$inst_keys" | grep -q "^${key}"; then
            echo "    BREAKING: Removed key: $key"
          fi
        done

        # check dmPolicy enforcement (v2026.2.26 fix)
        dm_policy=$(jq -r '.channels.telegram.dmPolicy // "unset"' "$instance_config")
        allow_from=$(jq -r '.channels.telegram.allowFrom // [] | length' "$instance_config")
        if [[ "$dm_policy" == "allowlist" && "$allow_from" -eq 0 ]]; then
          echo "    BREAKING: dmPolicy=allowlist but allowFrom is empty (DMs will be silently dropped since v2026.2.26)"
        fi
      fi
    done
  else
    echo "  No instances directory found."
  fi
fi

# --- 6. SKILL.md schema notes freshness ---
echo ""
echo "--- SKILL.md schema notes freshness ---"
SKILL_MD="$SKILL_PATH/SKILL.md"
if [[ -f "$SKILL_MD" ]]; then
  # find the latest version mentioned in schema notes
  LATEST_MENTIONED=$(grep -oE 'v?2026\.[0-9]+\.[0-9]+' "$SKILL_MD" | sort -t. -k2,2n -k3,3n | tail -1)
  echo "Latest version mentioned in SKILL.md: ${LATEST_MENTIONED:-none}"
  echo "Latest upstream release: $LATEST_TAG"
  if [[ -n "$LATEST_MENTIONED" && "${LATEST_MENTIONED#v}" != "$LATEST_CLEAN" ]]; then
    echo "RECOMMENDED: Update SKILL.md schema notes to cover changes through $LATEST_TAG"
  fi
fi

# --- 7. Summary ---
echo ""
echo "========================================="
echo "  AUDIT SUMMARY"
echo "========================================="
echo "Upstream latest:    $LATEST_TAG"
echo "Template pinned:    $LOCAL_VERSION"
echo "SKILL.md covers:    ${LATEST_MENTIONED:-unknown}"
if [[ -n "$NEWER_TAGS" ]]; then
  echo "Releases behind:    $RELEASE_COUNT"
else
  echo "Releases behind:    0"
fi
echo ""
echo "Next steps:"
echo "  1. Review release notes above for breaking/config changes"
echo "  2. Update template openclaw.json meta.lastTouchedVersion"
echo "  3. Add new schema notes to SKILL.md"
echo "  4. Run: bash scripts/validate_client_kit.sh assets/client-kit"
echo "  5. Run: bash scripts/review_kit.sh --skill"
echo ""
echo "For the agent: Feed the release notes + config reference into"
echo "the conversation for a full diff analysis. Use WebFetch on:"
echo "  $DOCS_URL"
echo "========================================="
