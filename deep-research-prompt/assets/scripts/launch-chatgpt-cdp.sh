#!/usr/bin/env bash
# launch-chatgpt-cdp.sh — start a dedicated CDP-enabled Chrome on a CLONE of the
# logged-in ChatGPT profile and wait until a chatgpt.com tab is reachable.
#
# Why a clone, and why `open -na` (observed June 2026):
#  - If the profile root is already attached to a running Chrome, launching the
#    Chrome binary against it silently forwards to that process and never binds
#    the DevTools port. Cloning sidesteps the profile lock entirely.
#  - Even with a free profile, exec'ing the Chrome binary directly can fail to
#    bind the port via the macOS app-singleton handoff. `open -na` starts a
#    genuinely separate instance and was the only reliable launch path.
#  - The logged-in ChatGPT session may live in a SUBPROFILE (e.g. "Profile 1"),
#    not "Default". Pass --profile-directory / ORACLE_PROFILE_DIRECTORY.
#
# Env defaults (overlay-sourced via resolve_overlay_config.py --section oracle):
#   ORACLE_CDP_PORT             DevTools port           (default 9222)
#   ORACLE_BROWSER_PROFILE_DIR  Chrome user-data-dir    (default ~/.oracle/browser-profile)
#   ORACLE_PROFILE_DIRECTORY    subprofile name         (default Default)
#   ORACLE_CHATGPT_PROJECT_URL  URL to open             (default https://chatgpt.com/)
#
# Exit codes: 0 = CDP up with a chatgpt.com tab; 2 = bad args/missing profile;
# 3 = CDP port never became reachable; 4 = no chatgpt.com tab appeared.
set -euo pipefail

PORT="${ORACLE_CDP_PORT:-9222}"
PROFILE_ROOT="${ORACLE_BROWSER_PROFILE_DIR:-$HOME/.oracle/browser-profile}"
PROFILE_DIR="${ORACLE_PROFILE_DIRECTORY:-Default}"
URL="${ORACLE_CHATGPT_PROJECT_URL:-https://chatgpt.com/}"
FRESH=0
CHROME_APP="${CHROME_APP:-Google Chrome}"

usage() {
  cat <<'EOF'
usage: launch-chatgpt-cdp.sh [--port N] [--profile-root DIR] [--profile-directory NAME] [--url URL] [--fresh]

Reuses an existing healthy CDP endpoint on the port unless --fresh is given.
Prints the page targets (id, title, url) on success.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --profile-root) PROFILE_ROOT="$2"; shift 2 ;;
    --profile-directory) PROFILE_DIR="$2"; shift 2 ;;
    --url) URL="$2"; shift 2 ;;
    --fresh) FRESH=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

# Expand a leading ~ that survived quoting.
case "$PROFILE_ROOT" in "~/"*) PROFILE_ROOT="$HOME/${PROFILE_ROOT#\~/}" ;; esac

cdp_json() { curl -fsS --max-time 3 "http://127.0.0.1:${PORT}/json" 2>/dev/null; }

print_tabs() {
  cdp_json | python3 -c 'import json,sys; [print(t["id"], (t.get("title") or "")[:60], t.get("url",""), sep="\t") for t in json.load(sys.stdin) if t.get("type")=="page"]'
}

has_chatgpt_tab() { cdp_json | grep -q '"url": *"https://chatgpt.com' ; }

# Reuse an already-healthy endpoint unless --fresh.
if [ "$FRESH" -eq 0 ] && curl -fsS --max-time 2 "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1; then
  if has_chatgpt_tab; then
    echo "reusing CDP endpoint on port ${PORT}" >&2
    print_tabs
    exit 0
  fi
  echo "CDP up on port ${PORT} but no chatgpt.com tab; will not hijack it — pick another --port or open the tab manually" >&2
  exit 4
fi

[ -d "$PROFILE_ROOT/$PROFILE_DIR" ] || { echo "profile not found: $PROFILE_ROOT/$PROFILE_DIR" >&2; exit 2; }

# Clone root metadata + the target subprofile, skipping locks and caches.
CLONE="$(mktemp -d /tmp/chatgpt-cdp-profile.XXXXXX)"
RSYNC_EXCLUDES=(
  --exclude='Singleton*' --exclude='DevToolsActivePort' --exclude='BrowserMetrics*'
  --exclude='Cache*' --exclude='Code Cache' --exclude='GPUCache' --exclude='ShaderCache'
  --exclude='GrShaderCache' --exclude='DawnGraphiteCache' --exclude='DawnWebGPUCache'
  --exclude='Service Worker/CacheStorage' --exclude='Crashpad' --exclude='Safe Browsing'
  --exclude='optimization_guide*' --exclude='component_crx_cache'
)
[ -f "$PROFILE_ROOT/Local State" ] && rsync -a "${RSYNC_EXCLUDES[@]}" "$PROFILE_ROOT/Local State" "$CLONE/"
[ -f "$PROFILE_ROOT/First Run" ] && rsync -a "$PROFILE_ROOT/First Run" "$CLONE/"
rsync -a "${RSYNC_EXCLUDES[@]}" "$PROFILE_ROOT/$PROFILE_DIR/" "$CLONE/$PROFILE_DIR/"
printf '%s\n' "$CLONE" > "/tmp/chatgpt-cdp-profile-${PORT}.path"
echo "cloned $PROFILE_ROOT/$PROFILE_DIR -> $CLONE ($(du -sh "$CLONE" | cut -f1))" >&2

open -na "$CHROME_APP" --args \
  --remote-debugging-port="$PORT" \
  --user-data-dir="$CLONE" \
  --profile-directory="$PROFILE_DIR" \
  --no-first-run --no-default-browser-check \
  --window-size=1400,1000 \
  "$URL"

for _ in $(seq 1 30); do
  if curl -fsS --max-time 2 "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS --max-time 2 "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1 || {
  echo "CDP never became reachable on port ${PORT}; Chrome may have forwarded into an existing instance" >&2
  exit 3
}

for _ in $(seq 1 30); do
  if has_chatgpt_tab; then
    print_tabs
    exit 0
  fi
  sleep 1
done
echo "CDP is up on port ${PORT} but no chatgpt.com tab loaded; profile may be logged out" >&2
print_tabs || true
exit 4
