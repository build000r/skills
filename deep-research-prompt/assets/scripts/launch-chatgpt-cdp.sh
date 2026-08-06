#!/bin/bash -p
# Start or reuse the dedicated hidden ChatGPT Chrome and create one exact CDP
# target. This launcher never submits a prompt and never clones auth state.
set -euo pipefail
umask 077

TEST_MODE="${ORACLE_LAUNCHER_TEST_MODE:-0}"
ATTESTATION_TEST_MODE="${ORACLE_LAUNCHER_TEST_ATTESTATION:-0}"
PORT="${ORACLE_CDP_PORT:-9222}"
PROFILE_ROOT="${ORACLE_BROWSER_PROFILE_DIR:-$HOME/.oracle/browser-profile}"
PROFILE_DIR="${ORACLE_PROFILE_DIRECTORY:-Default}"
URL="${ORACLE_CHATGPT_PROJECT_URL:-https://chatgpt.com/}"
RUNTIME_ROOT="${ORACLE_SUBAGENT_RUNTIME_DIR:-$HOME/.oracle/oracle-subagent}"
WAIT_SECONDS="${ORACLE_BROWSER_WAIT_SECONDS:-30}"
LOCK_WAIT_TENTHS="${ORACLE_BROWSER_LOCK_WAIT_TENTHS:-200}"
JSON_OUTPUT=0
FRESH=0
NO_SUBMIT_SMOKE=0

die() {
  local code="$1"
  shift
  printf 'oracle browser: %s\n' "$*" >&2
  exit "$code"
}

HOST_PLATFORM=""
CHROME_BIN="${ORACLE_CHROME_BIN:-}"
case "$TEST_MODE" in
  0)
    UNAME_BIN="/usr/bin/uname"
    HOST_OS="$("$UNAME_BIN" -s 2>/dev/null || true)"
    case "$HOST_OS" in
      Darwin)
        HOST_PLATFORM="darwin"
        CHROME_APP="Google Chrome"
        CURL_BIN="/usr/bin/curl"
        ID_BIN="/usr/bin/id"
        LSOF_BIN="/usr/sbin/lsof"
        NODE_BIN="/opt/homebrew/bin/node"
        OPEN_BIN="/usr/bin/open"
        OSASCRIPT_BIN="/usr/bin/osascript"
        APP_RESOLVER_BIN="$OSASCRIPT_BIN"
        PROCESS_INSPECTOR_BIN=""
        PYTHON_BIN="/usr/bin/python3"
        SLEEP_BIN="/bin/sleep"
        STAT_BIN="/usr/bin/stat"
        CODESIGN_BIN="/usr/bin/codesign"
        SPCTL_BIN="/usr/sbin/spctl"
        ;;
      Linux)
        # skillbox-portfolio-devbox: Xvfb hidden-headful, no Gatekeeper/codesign.
        HOST_PLATFORM="linux"
        CHROME_APP="Chrome"
        CURL_BIN="/usr/bin/curl"
        ID_BIN="/usr/bin/id"
        LSOF_BIN="/usr/bin/lsof"
        if [ -x /usr/bin/node ]; then
          NODE_BIN="/usr/bin/node"
        else
          NODE_BIN="$(command -v node 2>/dev/null || true)"
        fi
        OPEN_BIN=""
        OSASCRIPT_BIN=""
        APP_RESOLVER_BIN=""
        PROCESS_INSPECTOR_BIN=""
        PYTHON_BIN="/usr/bin/python3"
        SLEEP_BIN="/bin/sleep"
        STAT_BIN="/usr/bin/stat"
        CODESIGN_BIN=""
        SPCTL_BIN=""
        if [ -z "$CHROME_BIN" ]; then
          for candidate in \
            "$HOME/.local/bin/chrome-wrapper.sh" \
            /usr/bin/google-chrome-stable \
            /usr/bin/google-chrome \
            /usr/bin/chromium-browser \
            /usr/bin/chromium
          do
            if [ -n "$candidate" ] && [ -x "$candidate" ]; then
              CHROME_BIN="$candidate"
              break
            fi
          done
        fi
        ;;
      *)
        die 2 "unsupported host OS for production launcher: ${HOST_OS:-unknown}"
        ;;
    esac
    ;;
  1)
    HOST_PLATFORM="darwin"
    CHROME_APP="${CHROME_APP:-Google Chrome}"
    CURL_BIN="${ORACLE_CURL_BIN:-curl}"
    ID_BIN="${ORACLE_ID_BIN:-id}"
    LSOF_BIN="${ORACLE_LSOF_BIN:-lsof}"
    NODE_BIN="${ORACLE_NODE_BIN:-node}"
    OPEN_BIN="${ORACLE_OPEN_BIN:-open}"
    OSASCRIPT_BIN="${ORACLE_OSASCRIPT_BIN:-osascript}"
    APP_RESOLVER_BIN="${ORACLE_APP_RESOLVER_BIN:-$OSASCRIPT_BIN}"
    PROCESS_INSPECTOR_BIN="${ORACLE_PROCESS_INSPECTOR_BIN:-}"
    PYTHON_BIN="/usr/bin/python3"
    SLEEP_BIN="${ORACLE_SLEEP_BIN:-sleep}"
    STAT_BIN="${ORACLE_STAT_BIN:-stat}"
    UNAME_BIN="${ORACLE_UNAME_BIN:-uname}"
    CODESIGN_BIN="${ORACLE_CODESIGN_BIN:-codesign}"
    SPCTL_BIN="${ORACLE_SPCTL_BIN:-spctl}"
    ;;
  *) die 2 "ORACLE_LAUNCHER_TEST_MODE must be 0 or 1" ;;
esac
case "$ATTESTATION_TEST_MODE" in
  0) ;;
  1)
    [ "$TEST_MODE" -eq 1 ] ||
      die 2 "ORACLE_LAUNCHER_TEST_ATTESTATION requires test mode"
    ;;
  *) die 2 "ORACLE_LAUNCHER_TEST_ATTESTATION must be 0 or 1" ;;
esac
# Darwin Gatekeeper/codesign attestation is macOS-only. Linux production uses
# binary-path + /proc identity attestation (same receipt booleans the doctor
# requires) because there is no Gatekeeper on skillbox-portfolio-devbox.
if [ "$HOST_PLATFORM" = "linux" ] && [ "$TEST_MODE" -eq 0 ]; then
  ATTESTATION_ENABLED=0
  LINUX_ATTESTATION=1
elif [ "$TEST_MODE" -eq 0 ] || [ "$ATTESTATION_TEST_MODE" -eq 1 ]; then
  ATTESTATION_ENABLED=1
  LINUX_ATTESTATION=0
else
  ATTESTATION_ENABLED=0
  LINUX_ATTESTATION=0
fi
if [ "$TEST_MODE" -eq 1 ]; then
  ATTESTATION_SCHEMA="oracle-subagent.browser-attestation-test.v1"
else
  ATTESTATION_SCHEMA="oracle-subagent.browser-attestation.v1"
fi

# Portable owner/mode: GNU stat uses -c; BSD/macOS stat uses -f. Prefer the
# dialect the selected STAT_BIN actually supports so test-mode fakes and Linux
# production both work.
stat_owner() {
  if "$STAT_BIN" -c '%u' "$1" >/dev/null 2>&1; then
    "$STAT_BIN" -c '%u' "$1"
  else
    "$STAT_BIN" -f '%u' "$1"
  fi
}

stat_mode_octal() {
  if "$STAT_BIN" -c '%a' "$1" >/dev/null 2>&1; then
    "$STAT_BIN" -c '%a' "$1"
  else
    "$STAT_BIN" -f '%Lp' "$1"
  fi
}

usage() {
  printf '%s\n' \
    'usage: launch-chatgpt-cdp.sh [options]' \
    '' \
    'Options:' \
    '  --port N                    loopback DevTools port (default 9222)' \
    '  --profile-root DIR          persistent dedicated Chrome user-data-dir' \
    '  --profile-directory NAME    Chrome subprofile (default Default)' \
    '  --url URL                   chatgpt.com URL for the new exact target' \
    '  --fresh                     require that no supervisor is already running' \
    '  --no-submit-smoke           assert the launch-only validation path' \
    '  --json                      emit compact ownership JSON' \
    '  -h, --help                  show this help' \
    '' \
    'The steady-state browser is hidden-headful because true headless Chrome is' \
    'blocked by Cloudflare. This command never sends a ChatGPT message.'
}

need_value() {
  [ "$#" -ge 2 ] || die 2 "missing value for $1"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --port)
      need_value "$@"
      PORT="$2"
      shift 2
      ;;
    --profile-root)
      need_value "$@"
      PROFILE_ROOT="$2"
      shift 2
      ;;
    --profile-directory)
      need_value "$@"
      PROFILE_DIR="$2"
      shift 2
      ;;
    --url)
      need_value "$@"
      URL="$2"
      shift 2
      ;;
    --fresh)
      FRESH=1
      shift
      ;;
    --no-submit-smoke)
      NO_SUBMIT_SMOKE=1
      shift
      ;;
    --json)
      JSON_OUTPUT=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die 2 "unknown argument: $1"
      ;;
  esac
done

case "$PORT" in
  ''|*[!0-9]*) die 2 "port must be an integer" ;;
esac
[ "$PORT" -ge 1 ] && [ "$PORT" -le 65535 ] || die 2 "port must be between 1 and 65535"
case "$WAIT_SECONDS" in
  ''|*[!0-9]*) die 2 "ORACLE_BROWSER_WAIT_SECONDS must be a non-negative integer" ;;
esac
case "$LOCK_WAIT_TENTHS" in
  ''|*[!0-9]*) die 2 "ORACLE_BROWSER_LOCK_WAIT_TENTHS must be a non-negative integer" ;;
esac
case "$PROFILE_DIR" in
  ''|.|..|*/*) die 2 "profile directory must be one direct child name" ;;
esac
case "$URL" in
  https://chatgpt.com|https://chatgpt.com/*) ;;
  *) die 2 "URL must use https://chatgpt.com" ;;
esac
case "$PROFILE_ROOT" in
  "~/"*) PROFILE_ROOT="$HOME/${PROFILE_ROOT#\~/}" ;;
esac

required_tools=("$CURL_BIN" "$ID_BIN" "$LSOF_BIN" "$NODE_BIN" "$PYTHON_BIN" "$SLEEP_BIN" "$STAT_BIN" "$UNAME_BIN")
if [ "$HOST_PLATFORM" = "darwin" ]; then
  required_tools+=("$OPEN_BIN" "$OSASCRIPT_BIN" "$APP_RESOLVER_BIN")
fi
if [ "$HOST_PLATFORM" = "linux" ]; then
  [ -n "$CHROME_BIN" ] ||
    die 2 "Linux Chrome binary not found; set ORACLE_CHROME_BIN to a hidden-headful Chrome executable"
  [ -x "$CHROME_BIN" ] || die 2 "ORACLE_CHROME_BIN is not executable: $CHROME_BIN"
fi
for tool in "${required_tools[@]}"; do
  [ -n "$tool" ] || die 2 "required command path is empty"
  command -v "$tool" >/dev/null 2>&1 || die 2 "required command not found: $tool"
done
if [ "$ATTESTATION_ENABLED" -eq 1 ]; then
  for tool in "$CODESIGN_BIN" "$SPCTL_BIN"; do
    command -v "$tool" >/dev/null 2>&1 ||
      die 2 "required command not found: $tool"
  done
fi
if [ -n "$PROCESS_INSPECTOR_BIN" ]; then
  command -v "$PROCESS_INSPECTOR_BIN" >/dev/null 2>&1 ||
    die 2 "process inspector not found: $PROCESS_INSPECTOR_BIN"
fi

case "$RUNTIME_ROOT" in
  "~/"*) RUNTIME_ROOT="$HOME/${RUNTIME_ROOT#\~/}" ;;
esac

invalidate_existing_receipt() {
  "$PYTHON_BIN" -I - "$RUNTIME_ROOT" "$HOME" <<'PY'
import os
import stat
import sys

root, home = sys.argv[1:]
if not os.path.isabs(root) or os.path.normpath(root) != root:
    raise SystemExit("runtime directory must be a normalized absolute path")
home = os.path.realpath(home)
if not os.path.lexists(root):
    parent = os.path.dirname(root)
    if not os.path.isdir(parent):
        raise SystemExit("runtime parent not found")
    canonical = os.path.join(os.path.realpath(parent), os.path.basename(root))
    if canonical in {"/", home}:
        raise SystemExit("runtime directory is too broad")
    print(canonical)
    raise SystemExit(0)
metadata = os.lstat(root)
if stat.S_ISLNK(metadata.st_mode):
    raise SystemExit("runtime directory must not be a symlink")
if not stat.S_ISDIR(metadata.st_mode):
    raise SystemExit("runtime directory must be a real directory")
if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
    raise SystemExit("runtime directory must be private and current-user-owned")
root = os.path.realpath(root)
if root in {"/", home}:
    raise SystemExit("runtime directory is too broad")
receipt = os.path.join(root, "browser.json")
try:
    receipt_metadata = os.lstat(receipt)
except FileNotFoundError:
    print(root)
    raise SystemExit(0)
if not (stat.S_ISREG(receipt_metadata.st_mode) or stat.S_ISLNK(receipt_metadata.st_mode)):
    raise SystemExit("browser receipt path is not a regular file or symlink")
if receipt_metadata.st_uid != os.getuid():
    raise SystemExit("browser receipt is not current-user-owned")
os.unlink(receipt)
directory = os.open(root, os.O_RDONLY)
try:
    os.fsync(directory)
finally:
    os.close(directory)
print(root)
PY
}

# A previous ready receipt is never evidence for this invocation. Clear it
# before app/signature validation can fail, then clear it again under the
# launcher lock below to close the concurrent-publication window.
RUNTIME_ROOT="$(invalidate_existing_receipt)" ||
  die 2 "could not invalidate a prior browser receipt"

resolve_chrome_app_path() {
  local app_path
  case "$CHROME_APP" in
    /*) app_path="$CHROME_APP" ;;
    *)
      app_path="$("$APP_RESOLVER_BIN" - "$CHROME_APP" <<'APPLESCRIPT'
on run argv
  set appName to item 1 of argv
  return POSIX path of (path to application appName)
end run
APPLESCRIPT
)" || die 2 "could not resolve Chrome application: $CHROME_APP"
      ;;
  esac
  "$PYTHON_BIN" -I - "$app_path" <<'PY'
from pathlib import Path
import sys

raw = sys.argv[1]
if "\0" in raw or "\n" in raw:
    raise SystemExit("invalid Chrome application path")
app = Path(raw).expanduser().resolve(strict=True)
if not app.is_dir() or app.suffix != ".app":
    raise SystemExit("Chrome application must resolve to an app bundle")
print(app)
PY
}

if [ "$HOST_PLATFORM" = "linux" ]; then
  CHROME_APP_PATH="$CHROME_BIN"
  # Shell wrappers (e.g. chrome-wrapper.sh) exec the real ELF; ownership checks
  # compare /proc/<pid>/exe, so resolve to the binary that will actually run.
  EXPECTED_CHROME_EXECUTABLE="$("$PYTHON_BIN" -I - "$CHROME_BIN" <<'PY'
import os
import re
from pathlib import Path
import sys

raw = Path(sys.argv[1]).expanduser().resolve(strict=True)
if not raw.is_file() or not os.access(raw, os.X_OK):
    raise SystemExit("Chrome binary is missing or not executable")
text = raw.read_text(encoding="utf-8", errors="replace")
if text.startswith("#!"):
    match = re.search(
        r"(?m)(?:exec\s+)?(/[^\s'\"]+/chrome(?:-linux64)?/chrome)\b",
        text,
    )
    if match:
        candidate = Path(match.group(1)).expanduser().resolve(strict=True)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            print(candidate)
            raise SystemExit(0)
print(raw)
PY
)" || die 2 "could not resolve the exact Linux Chrome executable"
  # Launch through the wrapper when provided so LD_LIBRARY_PATH / --no-sandbox
  # and other host-local shims stay intact.
  LINUX_CHROME_LAUNCHER="$CHROME_BIN"
else
  CHROME_APP_PATH="$(resolve_chrome_app_path)" ||
    die 2 "could not resolve the exact Chrome application"
  EXPECTED_CHROME_EXECUTABLE="$("$PYTHON_BIN" -I - "$CHROME_APP_PATH" <<'PY'
import os
from pathlib import Path
import sys

app = Path(sys.argv[1])
executable = (app / "Contents" / "MacOS" / app.stem).resolve(strict=True)
if not executable.is_file() or not os.access(executable, os.X_OK):
    raise SystemExit("Chrome application executable is missing or not executable")
print(executable)
PY
)" ||
    die 2 "could not resolve the exact Chrome executable"
fi

EXPECTED_CHROME_CDHASH=""
if [ "$ATTESTATION_ENABLED" -eq 1 ]; then
  chrome_signature="$("$CODESIGN_BIN" -d --verbose=4 "$CHROME_APP_PATH" 2>&1)" ||
    die 2 "could not inspect Chrome application signature"
  EXPECTED_CHROME_CDHASH="$("$PYTHON_BIN" -I - "$chrome_signature" <<'PY'
import sys

fields = {}
authorities = []
for line in sys.argv[1].splitlines():
    key, separator, value = line.partition("=")
    if separator:
        if key == "Authority":
            authorities.append(value)
        fields[key] = value
if fields.get("Identifier") != "com.google.Chrome":
    raise SystemExit("unexpected Chrome bundle identifier")
if fields.get("TeamIdentifier") != "EQHXZ8M8AV":
    raise SystemExit("unexpected Chrome signing team")
if authorities != [
    "Developer ID Application: Google LLC (EQHXZ8M8AV)",
    "Developer ID Certification Authority",
    "Apple Root CA",
]:
    raise SystemExit("unexpected Chrome signing authority chain")
if fields.get("Notarization Ticket") != "stapled":
    raise SystemExit("Chrome notarization ticket is not stapled")
cdhash = fields.get("CDHash")
if not cdhash or len(cdhash) != 40 or any(
    character not in "0123456789abcdef" for character in cdhash
):
    raise SystemExit("Chrome CDHash is invalid")
print(cdhash)
PY
)" ||
  {
    die 2 "Chrome application does not have the expected Google identity"
  }
fi

URL="$("$PYTHON_BIN" -I - "$URL" <<'PY'
from urllib.parse import urlsplit, urlunsplit
import sys

raw = sys.argv[1]
if any(ord(character) < 32 for character in raw):
    raise SystemExit("control characters are not allowed")
parsed = urlsplit(raw)
try:
    port = parsed.port
except ValueError as exc:
    raise SystemExit(str(exc))
if (
    parsed.scheme != "https"
    or parsed.hostname != "chatgpt.com"
    or parsed.username is not None
    or parsed.password is not None
    or port is not None
    or parsed.netloc != "chatgpt.com"
    or parsed.fragment
    or parsed.query
):
    raise SystemExit("URL is not an exact https://chatgpt.com target")
path = parsed.path or "/"
print(urlunsplit(("https", "chatgpt.com", path, parsed.query, "")))
PY
)" || die 2 "URL must be an exact https://chatgpt.com URL without credentials, port, query, or fragment"

[ -d "$PROFILE_ROOT" ] || die 2 "profile root not found: $PROFILE_ROOT"
PROFILE_ROOT="$(cd "$PROFILE_ROOT" && pwd -P)"
[ -d "$PROFILE_ROOT/$PROFILE_DIR" ] || die 2 "profile not found: $PROFILE_ROOT/$PROFILE_DIR"
[ ! -L "$PROFILE_ROOT/$PROFILE_DIR" ] ||
  die 2 "profile directory must not be a symlink: $PROFILE_ROOT/$PROFILE_DIR"

secure_directory() {
  local path="$1"
  local label="$2"
  local owner mode permission
  owner="$(stat_owner "$path" 2>/dev/null)" || die 2 "cannot inspect $label owner: $path"
  mode="$(stat_mode_octal "$path" 2>/dev/null)" || die 2 "cannot inspect $label permissions: $path"
  [ "$owner" = "$("$ID_BIN" -u)" ] || die 2 "$label must be owned by the current user: $path"
  case "$mode" in
    ''|*[!0-7]*) die 2 "unexpected $label permission mode: $mode" ;;
  esac
  permission=$((8#$mode))
  (( (permission & 077) == 0 )) || die 2 "$label must not grant group/world access: $path (mode $mode)"
}

secure_directory "$PROFILE_ROOT" "profile root"
secure_directory "$PROFILE_ROOT/$PROFILE_DIR" "profile directory"

[ "$RUNTIME_ROOT" != "/" ] && [ "$RUNTIME_ROOT" != "$HOME" ] ||
  die 2 "runtime directory is too broad: $RUNTIME_ROOT"
[ ! -L "$RUNTIME_ROOT" ] || die 2 "runtime directory must not be a symlink: $RUNTIME_ROOT"
if [ ! -e "$RUNTIME_ROOT" ]; then
  runtime_parent="${RUNTIME_ROOT%/*}"
  [ -n "$runtime_parent" ] && [ "$runtime_parent" != "$RUNTIME_ROOT" ] ||
    die 2 "runtime directory must have an existing parent"
  [ -d "$runtime_parent" ] || die 2 "runtime parent not found: $runtime_parent"
  [ ! -L "$runtime_parent" ] || die 2 "runtime parent must not be a symlink: $runtime_parent"
  parent_owner="$(stat_owner "$runtime_parent" 2>/dev/null)" ||
    die 2 "cannot inspect runtime parent owner"
  parent_mode="$(stat_mode_octal "$runtime_parent" 2>/dev/null)" ||
    die 2 "cannot inspect runtime parent permissions"
  [ "$parent_owner" = "$("$ID_BIN" -u)" ] ||
    die 2 "runtime parent must be owned by the current user"
  parent_permission=$((8#$parent_mode))
  (( (parent_permission & 022) == 0 )) ||
    die 2 "runtime parent must not be group/world writable"
  if ! /bin/mkdir -m 700 "$RUNTIME_ROOT" 2>/dev/null; then
    [ -d "$RUNTIME_ROOT" ] ||
      die 2 "could not create runtime directory: $RUNTIME_ROOT"
  fi
fi
[ ! -L "$RUNTIME_ROOT" ] || die 2 "runtime directory must not be a symlink: $RUNTIME_ROOT"
[ -d "$RUNTIME_ROOT" ] || die 2 "runtime path is not a directory: $RUNTIME_ROOT"
secure_directory "$RUNTIME_ROOT" "runtime directory"
RUNTIME_ROOT="$(cd "$RUNTIME_ROOT" && pwd -P)"
RECEIPT_PATH="$RUNTIME_ROOT/browser.json"
ATTESTATION_PATH="$RUNTIME_ROOT/browser-attestation.json"
LOCK_PATH="$RUNTIME_ROOT/launcher.lock"
RECLAIM_GUARD_PATH="$RUNTIME_ROOT/launcher-reclaim.guard"

release_lock() {
  local current_fields current_pid current_token
  if [ "${lock_acquired:-0}" -eq 1 ] &&
    [ -f "$LOCK_PATH" ] &&
    [ ! -L "$LOCK_PATH" ]; then
    current_fields="$(read_lock_fields 2>/dev/null || true)"
    IFS=$'\t' read -r current_pid current_token <<<"$current_fields"
    if [ "$current_pid" = "$$" ] && [ "$current_token" = "${lock_token:-}" ]; then
      /bin/rm -f "$LOCK_PATH"
    fi
  fi
  if [ -n "${lock_candidate:-}" ] && [ ! -L "$lock_candidate" ]; then
    /bin/rm -f "$lock_candidate"
  fi
}

rehide_browser_best_effort() {
  local exact_pid="$1"
  if [ "$HOST_PLATFORM" = "linux" ]; then
    return 0
  fi
  "$OSASCRIPT_BIN" - "$exact_pid" >/dev/null 2>&1 <<'APPLESCRIPT' || true
on run argv
  set chromePid to (item 1 of argv) as integer
  tell application "System Events"
    set chromeProcess to first application process whose unix id is chromePid
    repeat with chromeWindow in windows of chromeProcess
      try
        set position of chromeWindow to {-32000, -32000}
      end try
    end repeat
    set visible of chromeProcess to false
    delay 0.5
    return (visible of chromeProcess as text) & ":" & (frontmost of chromeProcess as text)
  end tell
end run
APPLESCRIPT
}

launcher_exit_cleanup() {
  local exit_code="${1:-0}"
  trap - EXIT
  if [ "$exit_code" -ne 0 ] &&
    [ "${owned_pid_verified:-0}" -eq 1 ] &&
    [ -n "${pid:-}" ]; then
    rehide_browser_best_effort "$pid"
  fi
  release_lock
  exit "$exit_code"
}

read_lock_fields() {
  "$PYTHON_BIN" -I - "$LOCK_PATH" <<'PY'
import os
import re
import stat
import sys

path = sys.argv[1]
metadata = os.lstat(path)
if not stat.S_ISREG(metadata.st_mode):
    raise SystemExit("lock is not a regular file")
with open(path, "r", encoding="ascii") as handle:
    lines = handle.read().splitlines()
if len(lines) != 2 or not lines[0].startswith("pid=") or not lines[1].startswith("token="):
    raise SystemExit("invalid lock record")
pid = lines[0][4:]
token = lines[1][6:]
if not pid.isdecimal() or int(pid) <= 1:
    raise SystemExit("invalid lock pid")
if not re.fullmatch(r"[0-9]+-[0-9]+-[0-9]+-[0-9]+", token):
    raise SystemExit("invalid lock token")
print(f"{pid}\t{token}")
PY
}

reclaim_stale_lock() {
  local status test_delay
  if [ "$TEST_MODE" -eq 1 ]; then
    test_delay="${ORACLE_LAUNCHER_TEST_RECLAIM_DELAY:-0}"
  else
    test_delay=0
  fi
  if "$PYTHON_BIN" -I - \
    "$LOCK_PATH" "$RECLAIM_GUARD_PATH" "$("$ID_BIN" -u)" "$test_delay" <<'PY'
import errno
import fcntl
import os
import re
import stat
import sys
import time

lock_path, guard_path, expected_uid_raw, delay_raw = sys.argv[1:]
expected_uid = int(expected_uid_raw)


def fatal(message):
    print(f"oracle browser: {message}", file=sys.stderr)
    raise SystemExit(5)


try:
    delay = float(delay_raw)
except ValueError:
    fatal("test reclaim delay is invalid")
if delay < 0 or delay > 5:
    fatal("test reclaim delay is out of range")

guard_flags = os.O_RDWR | os.O_CREAT
guard_flags |= getattr(os, "O_CLOEXEC", 0)
guard_flags |= getattr(os, "O_NOFOLLOW", 0)
try:
    guard_fd = os.open(guard_path, guard_flags, 0o600)
except OSError as error:
    if error.errno == errno.ELOOP:
        fatal("browser launcher reclaim guard must not be a symlink")
    raise

with os.fdopen(guard_fd, "r+b", closefd=True) as guard:
    guard_metadata = os.fstat(guard.fileno())
    if not stat.S_ISREG(guard_metadata.st_mode):
        fatal("browser launcher reclaim guard is not a regular file")
    if guard_metadata.st_uid != expected_uid:
        fatal("browser launcher reclaim guard is not owned by the current user")
    if stat.S_IMODE(guard_metadata.st_mode) & 0o077:
        fatal("browser launcher reclaim guard grants group/world access")
    fcntl.flock(guard.fileno(), fcntl.LOCK_EX)

    lock_flags = os.O_RDONLY
    lock_flags |= getattr(os, "O_CLOEXEC", 0)
    lock_flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        lock_fd = os.open(lock_path, lock_flags)
    except FileNotFoundError:
        raise SystemExit(0)
    except OSError as error:
        if error.errno == errno.ELOOP:
            fatal("browser launcher lock must not be a symlink")
        raise

    with os.fdopen(lock_fd, "rb", closefd=True) as lock:
        metadata = os.fstat(lock.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            fatal("browser launcher lock path is not a regular file")
        if metadata.st_uid != expected_uid:
            fatal("browser launcher lock is not owned by the current user")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            fatal("browser launcher lock grants group/world access")
        try:
            record = lock.read(1025)
        except OSError:
            raise SystemExit(1)

    if len(record) > 1024:
        fatal("browser launcher lock record is too large")
    try:
        encoded = record.decode("ascii")
    except UnicodeDecodeError:
        encoded = ""
    match = re.fullmatch(
        r"pid=([0-9]+)\ntoken=([0-9]+-[0-9]+-[0-9]+-[0-9]+)\n?",
        encoded,
    )
    stale = False
    if match and int(match.group(1)) > 1:
        try:
            os.kill(int(match.group(1)), 0)
        except ProcessLookupError:
            stale = True
        except PermissionError:
            raise SystemExit(1)
        else:
            raise SystemExit(1)
    elif time.time() - metadata.st_mtime >= 2:
        stale = True
    else:
        raise SystemExit(1)

    if stale:
        if delay:
            time.sleep(delay)
        try:
            current = os.stat(lock_path, follow_symlinks=False)
        except FileNotFoundError:
            raise SystemExit(0)
        if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise SystemExit(1)
        os.unlink(lock_path)
        raise SystemExit(0)
PY
  then
    return 0
  else
    status=$?
    [ "$status" -eq 1 ] && return 1
    die 5 "browser launcher lock reclamation failed"
  fi
}

create_lock_candidate() {
  local attempt
  attempt=0
  while [ "$attempt" -lt 20 ]; do
    lock_token="$$-$RANDOM-$RANDOM-$RANDOM"
    lock_candidate="$RUNTIME_ROOT/.launcher-owner.$lock_token"
    if (
      set -o noclobber
      printf 'pid=%s\ntoken=%s\n' "$$" "$lock_token" > "$lock_candidate"
    ) 2>/dev/null; then
      return
    fi
    attempt=$((attempt + 1))
  done
  die 5 "could not create a private browser launcher lock candidate"
}

publish_lock_candidate() {
  "$PYTHON_BIN" -I - "$lock_candidate" "$LOCK_PATH" <<'PY'
import os
import sys

source, destination = sys.argv[1:]
os.link(source, destination, follow_symlinks=False)
PY
}

lock_acquired=0
lock_candidate=""
lock_token=""
lock_attempt=0
owned_pid_verified=0
trap 'launcher_exit_cleanup "$?"' EXIT
create_lock_candidate
until publish_lock_candidate 2>/dev/null; do
  /bin/rm -f "$lock_candidate"
  lock_candidate=""
  if reclaim_stale_lock; then
    create_lock_candidate
    continue
  fi
  [ "$lock_attempt" -lt "$LOCK_WAIT_TENTHS" ] ||
    die 5 "timed out waiting for the browser launcher lock"
  "$SLEEP_BIN" 0.1
  lock_attempt=$((lock_attempt + 1))
  create_lock_candidate
done
lock_acquired=1
/bin/rm -f "$lock_candidate"
lock_candidate=""
RUNTIME_ROOT="$(invalidate_existing_receipt)" ||
  die 5 "could not invalidate a prior browser receipt under launcher lock"

endpoint_url="http://127.0.0.1:${PORT}"

cdp_ready() {
  "$CURL_BIN" -q -fsS --max-time 2 "$endpoint_url/json/version" >/dev/null 2>&1
}

listener_pids() {
  local raw
  raw="$("$LSOF_BIN" -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true)"
  printf '%s\n' "$raw" | "$PYTHON_BIN" -I -c '
import sys

pids = set()
for raw_line in sys.stdin:
    line = raw_line.strip()
    if not line:
        continue
    if not line.isdecimal() or int(line) <= 1:
        raise SystemExit("invalid listener pid")
    pids.add(int(line))
for pid in sorted(pids):
    print(pid)
'
}

single_listener_pid() {
  local pids
  pids="$(listener_pids)" || die 5 "could not enumerate listener owners on port $PORT"
  [ -n "$pids" ] || die 5 "CDP endpoint has no resolvable listener owner on port $PORT"
  case "$pids" in
    *$'\n'*) die 5 "CDP port $PORT has multiple listener owners" ;;
  esac
  printf '%s\n' "$pids"
}

inspect_process() {
  local pid="$1"
  if [ -n "$PROCESS_INSPECTOR_BIN" ]; then
    "$PROCESS_INSPECTOR_BIN" "$pid"
    return
  fi
  if [ "$HOST_PLATFORM" = "linux" ]; then
    "$PYTHON_BIN" -I - "$pid" <<'PY'
import json
import os
import shlex
import sys

pid = int(sys.argv[1])
exe_link = f"/proc/{pid}/exe"
cmdline_path = f"/proc/{pid}/cmdline"
try:
    executable = os.path.realpath(exe_link)
except OSError as exc:
    raise SystemExit(f"cannot resolve /proc/{pid}/exe: {exc}") from exc
try:
    with open(cmdline_path, "rb") as handle:
        raw = handle.read()
except OSError as exc:
    raise SystemExit(f"cannot read /proc/{pid}/cmdline: {exc}") from exc
parts = [os.fsdecode(part) for part in raw.split(b"\0") if part]
if not parts:
    raise SystemExit("process argv is empty")
# Chrome for Testing on Linux often collapses cmdline to one space-joined
# string. Re-split so ownership checks see individual flags.
if len(parts) == 1 and " --" in parts[0]:
    try:
        parts = shlex.split(parts[0])
    except ValueError:
        pass
print(json.dumps({"executable": executable, "argv": parts}, separators=(",", ":")))
PY
    return
  fi
  "$PYTHON_BIN" -I - "$pid" <<'PY'
import ctypes
import ctypes.util
import json
import os
import struct
import sys

if sys.platform != "darwin":
    raise SystemExit("exact process argv inspection currently requires macOS")

pid = int(sys.argv[1])
CTL_KERN = 1
KERN_PROCARGS2 = 49
libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
mib = (ctypes.c_int * 3)(CTL_KERN, KERN_PROCARGS2, pid)
size = ctypes.c_size_t()
if libc.sysctl(mib, 3, None, ctypes.byref(size), None, 0) != 0:
    error = ctypes.get_errno()
    raise OSError(error, os.strerror(error))
buffer = ctypes.create_string_buffer(size.value)
if libc.sysctl(mib, 3, buffer, ctypes.byref(size), None, 0) != 0:
    error = ctypes.get_errno()
    raise OSError(error, os.strerror(error))

raw = buffer.raw[: size.value]
argc = struct.unpack_from("i", raw, 0)[0]
offset = struct.calcsize("i")
executable_end = raw.find(b"\0", offset)
if executable_end < 0:
    raise SystemExit("process executable was not NUL-terminated")
executable = os.fsdecode(raw[offset:executable_end])
offset = executable_end
while offset < len(raw) and raw[offset] == 0:
    offset += 1
argv = []
for _ in range(argc):
    argument_end = raw.find(b"\0", offset)
    if argument_end < 0:
        raise SystemExit("process argv was truncated")
    argv.append(os.fsdecode(raw[offset:argument_end]))
    offset = argument_end + 1

print(json.dumps({"executable": executable, "argv": argv}, separators=(",", ":")))
PY
}

verify_owned_listener() {
  local pid="$1"
  local listener_info listener_uid listener_line listener_name process_json
  local -a listener_names=()
  [ -n "$pid" ] || die 5 "CDP endpoint has no resolvable listener owner on port $PORT"
  listener_info="$("$LSOF_BIN" -nP -a -p "$pid" -iTCP:"$PORT" -sTCP:LISTEN -Fpun 2>/dev/null)" ||
    die 5 "cannot inspect listener $pid"
  listener_uid=""
  while IFS= read -r listener_line; do
    case "$listener_line" in
      u*)
        [ -n "$listener_uid" ] || listener_uid="${listener_line#u}"
        ;;
      n*) listener_names[${#listener_names[@]}]="${listener_line#n}" ;;
    esac
  done <<<"$listener_info"
  [ "$listener_uid" = "$("$ID_BIN" -u)" ] ||
    die 5 "listener $pid is not owned by the current user"
  [ "${#listener_names[@]}" -gt 0 ] ||
    die 5 "listener $pid has no inspectable bind address"
  for listener_name in "${listener_names[@]}"; do
    case "$listener_name" in
      "127.0.0.1:$PORT"|"[::1]:$PORT") ;;
      *) die 5 "listener $pid is not loopback-only: $listener_name" ;;
    esac
  done
  process_json="$(inspect_process "$pid" 2>/dev/null)" ||
    die 5 "cannot inspect exact process arguments for listener $pid"
  "$PYTHON_BIN" -I - "$process_json" \
    "$EXPECTED_CHROME_EXECUTABLE" "$PORT" "$PROFILE_ROOT" "$PROFILE_DIR" <<'PY' ||
import json
import os
import shlex
import sys

process_json, expected_executable, port, profile_root, profile_directory = sys.argv[1:]
process = json.loads(process_json)
executable = process.get("executable")
argv = process.get("argv")
if not isinstance(executable, str) or not executable.startswith("/"):
    raise SystemExit("process executable is not an absolute path")
if not isinstance(argv, list) or not all(isinstance(value, str) for value in argv):
    raise SystemExit("process argv is invalid")
if os.path.realpath(executable) != os.path.realpath(expected_executable):
    raise SystemExit("listener executable is not the requested Chrome app")
# Some Linux Chrome builds collapse /proc/<pid>/cmdline into a single
# space-joined string. Re-split so flag checks stay exact.
if len(argv) == 1 and " --" in argv[0]:
    try:
        argv = shlex.split(argv[0])
    except ValueError as exc:
        raise SystemExit(f"process argv could not be re-split: {exc}") from exc
required = {
    "--remote-debugging-address": "127.0.0.1",
    "--remote-debugging-port": port,
    "--user-data-dir": profile_root,
    "--profile-directory": profile_directory,
}
for option, expected_value in required.items():
    matches = [value for value in argv if value.startswith(option + "=")]
    if matches != [f"{option}={expected_value}"]:
        raise SystemExit(f"listener has invalid or duplicate {option}")
PY
  {
    die 5 "listener $pid does not match the exact Chrome/profile contract"
  }
}

verify_current_listener() {
  local expected_pid="$1"
  local observed_pid
  observed_pid="$(single_listener_pid)"
  [ "$observed_pid" = "$expected_pid" ] ||
    die 5 "CDP listener changed during ownership verification"
  verify_owned_listener "$observed_pid"
}

assess_chrome_bundle() {
  "$SPCTL_BIN" --assess --type execute "$CHROME_APP_PATH" >/dev/null 2>&1 ||
    die 5 "Chrome application failed the macOS Gatekeeper assessment"
}

verify_dynamic_chrome_identity() {
  local pid="$1"
  local dynamic_signature
  "$CODESIGN_BIN" --verify "+$pid" >/dev/null 2>&1 ||
    die 5 "running Chrome process failed dynamic code-signature validation"
  dynamic_signature="$("$CODESIGN_BIN" -d --verbose=4 "+$pid" 2>&1)" ||
    die 5 "could not inspect running Chrome code identity"
  "$PYTHON_BIN" -I - "$dynamic_signature" \
    "$EXPECTED_CHROME_EXECUTABLE" "$EXPECTED_CHROME_CDHASH" <<'PY'
import re
import sys

details, expected_executable, expected_cdhash = sys.argv[1:]
fields = {}
authorities = []
flags = set()
for line in details.splitlines():
    key, separator, value = line.partition("=")
    if separator:
        if key == "Authority":
            authorities.append(value)
        fields[key] = value
    if line.startswith("CodeDirectory "):
        match = re.search(r"flags=0x[0-9a-f]+\(([^)]*)\)", line)
        if match:
            flags = set(match.group(1).split(","))
if fields.get("Executable") != expected_executable:
    raise SystemExit("running executable path does not match the resolved app")
if fields.get("Identifier") != "com.google.Chrome":
    raise SystemExit("running Chrome bundle identifier is unexpected")
if fields.get("TeamIdentifier") != "EQHXZ8M8AV":
    raise SystemExit("running Chrome signing team is unexpected")
if authorities != [
    "Developer ID Application: Google LLC (EQHXZ8M8AV)",
    "Developer ID Certification Authority",
    "Apple Root CA",
]:
    raise SystemExit("running Chrome authority chain is unexpected")
if fields.get("CDHash") != expected_cdhash:
    raise SystemExit("running Chrome CDHash does not match the assessed app")
required_flags = {"kill", "restrict", "library-validation", "runtime"}
if not required_flags.issubset(flags):
    raise SystemExit("running Chrome lacks required hardened code flags")
print(expected_cdhash)
PY
}

attestation_cache_matches() {
  local pid="$1"
  local cdhash="$2"
  local owner mode permission
  if [ ! -e "$ATTESTATION_PATH" ] && [ ! -L "$ATTESTATION_PATH" ]; then
    return 1
  fi
  [ ! -L "$ATTESTATION_PATH" ] ||
    die 5 "browser attestation cache must not be a symlink"
  [ -f "$ATTESTATION_PATH" ] ||
    die 5 "browser attestation cache is not a regular file"
  owner="$(stat_owner "$ATTESTATION_PATH" 2>/dev/null)" ||
    die 5 "cannot inspect browser attestation cache owner"
  mode="$(stat_mode_octal "$ATTESTATION_PATH" 2>/dev/null)" ||
    die 5 "cannot inspect browser attestation cache permissions"
  [ "$owner" = "$("$ID_BIN" -u)" ] ||
    die 5 "browser attestation cache is not owned by the current user"
  permission=$((8#$mode))
  (( (permission & 077) == 0 )) ||
    die 5 "browser attestation cache grants group/world access"
  "$PYTHON_BIN" -I - "$ATTESTATION_PATH" "$pid" "$cdhash" \
    "$EXPECTED_CHROME_EXECUTABLE" "$ATTESTATION_SCHEMA" <<'PY'
import json
import sys

(
    path,
    expected_pid,
    expected_cdhash,
    expected_executable,
    expected_schema,
) = sys.argv[1:]
with open(path, "r", encoding="utf-8") as handle:
    record = json.load(handle)
if record != {
    "schema": expected_schema,
    "pid": int(expected_pid),
    "executable": expected_executable,
    "cdhash": expected_cdhash,
    "gatekeeper_assessed": True,
    "dynamic_code_verified": True,
}:
    raise SystemExit("attestation cache does not match the running browser")
PY
}

write_attestation_cache() {
  local pid="$1"
  local cdhash="$2"
  "$PYTHON_BIN" -I - "$ATTESTATION_PATH" "$pid" \
    "$EXPECTED_CHROME_EXECUTABLE" "$cdhash" "$ATTESTATION_SCHEMA" <<'PY'
import json
import os
import sys
import tempfile

path, pid, executable, cdhash, schema = sys.argv[1:]
record = {
    "schema": schema,
    "pid": int(pid),
    "executable": executable,
    "cdhash": cdhash,
    "gatekeeper_assessed": True,
    "dynamic_code_verified": True,
}
encoded = json.dumps(record, sort_keys=True, separators=(",", ":"))
parent = os.path.dirname(path)
fd, temporary_path = tempfile.mkstemp(
    prefix=".browser-attestation.",
    suffix=".json",
    dir=parent,
)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(encoded + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary_path, path)
except BaseException:
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        os.unlink(temporary_path)
    except FileNotFoundError:
        pass
    raise
PY
}

ensure_linux_binary_attestation() {
  local pid="$1"
  local linux_cdhash process_json
  # Linux has no Gatekeeper. Prove the loopback listener is the expected Chrome
  # binary via /proc, then stamp the same receipt booleans the doctor requires.
  process_json="$(inspect_process "$pid" 2>/dev/null)" ||
    die 5 "cannot inspect Linux Chrome process $pid for attestation"
  "$PYTHON_BIN" -I - "$process_json" "$EXPECTED_CHROME_EXECUTABLE" "$PORT" \
    "$PROFILE_ROOT" "$PROFILE_DIR" <<'PY' ||
import json
import os
import shlex
import sys

process_json, expected_executable, port, profile_root, profile_directory = sys.argv[1:]
process = json.loads(process_json)
executable = process.get("executable")
argv = process.get("argv")
if not isinstance(executable, str) or not executable.startswith("/"):
    raise SystemExit("process executable is not an absolute path")
if os.path.realpath(executable) != os.path.realpath(expected_executable):
    raise SystemExit("listener executable is not the requested Chrome binary")
if not isinstance(argv, list) or not all(isinstance(value, str) for value in argv):
    raise SystemExit("process argv is invalid")
if len(argv) == 1 and " --" in argv[0]:
    try:
        argv = shlex.split(argv[0])
    except ValueError as exc:
        raise SystemExit(f"process argv could not be re-split: {exc}") from exc
required = {
    "--remote-debugging-address": "127.0.0.1",
    "--remote-debugging-port": port,
    "--user-data-dir": profile_root,
    "--profile-directory": profile_directory,
}
for option, expected_value in required.items():
    matches = [value for value in argv if value.startswith(option + "=")]
    if matches != [f"{option}={expected_value}"]:
        raise SystemExit(f"listener has invalid or duplicate {option}")
PY
  {
    die 5 "Linux Chrome process failed binary attestation"
  }
  linux_cdhash="$("$PYTHON_BIN" -I - "$EXPECTED_CHROME_EXECUTABLE" <<'PY'
import hashlib
import sys

path = sys.argv[1]
digest = hashlib.sha256()
with open(path, "rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest()[:40])
PY
)" || die 5 "could not hash Linux Chrome binary for attestation"
  write_attestation_cache "$pid" "$linux_cdhash" ||
    die 5 "could not persist the Linux browser attestation"
  GATEKEEPER_ASSESSED=1
  DYNAMIC_CODE_VERIFIED=1
}

ensure_production_attestation() {
  local pid="$1"
  local gatekeeper_already_assessed="$2"
  local dynamic_cdhash
  if [ "${LINUX_ATTESTATION:-0}" -eq 1 ]; then
    ensure_linux_binary_attestation "$pid"
    return
  fi
  dynamic_cdhash="$(verify_dynamic_chrome_identity "$pid")" ||
    die 5 "running Chrome process identity could not be proven"
  if [ "$gatekeeper_already_assessed" -eq 0 ] &&
    ! attestation_cache_matches "$pid" "$dynamic_cdhash"; then
    assess_chrome_bundle
    verify_current_listener "$pid"
    dynamic_cdhash="$(verify_dynamic_chrome_identity "$pid")" ||
      die 5 "running Chrome identity changed during Gatekeeper assessment"
  fi
  write_attestation_cache "$pid" "$dynamic_cdhash" ||
    die 5 "could not persist the browser code attestation"
  GATEKEEPER_ASSESSED=1
  DYNAMIC_CODE_VERIFIED=1
}

hide_browser() {
  local pid="$1"
  local observed process_visible process_frontmost windows_offscreen window_count
  if [ "$HOST_PLATFORM" = "linux" ]; then
    # Xvfb has no operator-visible display. Contract: process alive, DISPLAY set
    # to a virtual server, windows requested off-screen at launch.
    [ -d "/proc/$pid" ] || die 3 "dedicated Chrome process $pid is not running"
    case "${DISPLAY:-}" in
      :[0-9]|:[0-9][0-9]|:[0-9][0-9][0-9]) ;;
      *)
        die 3 "Linux hidden-headful requires DISPLAY to an Xvfb server (got '${DISPLAY:-empty}')"
        ;;
    esac
    WINDOW_COUNT=0
    WINDOWS_OFFSCREEN=true
    return 0
  fi
  observed="$("$OSASCRIPT_BIN" - "$pid" 2>/dev/null <<'APPLESCRIPT'
on run argv
  set chromePid to (item 1 of argv) as integer
  tell application "System Events"
    set chromeProcess to first application process whose unix id is chromePid
    repeat with chromeWindow in windows of chromeProcess
      set position of chromeWindow to {-32000, -32000}
    end repeat
    set visible of chromeProcess to false
    delay 0.5
    set windowsOffscreen to true
    repeat with chromeWindow in windows of chromeProcess
      set windowPosition to position of chromeWindow
      if (item 1 of windowPosition) > -10000 then set windowsOffscreen to false
    end repeat
    return (visible of chromeProcess as text) & ":" & (frontmost of chromeProcess as text) & ":" & (windowsOffscreen as text) & ":" & (count of windows of chromeProcess as text)
  end tell
end run
APPLESCRIPT
)" || die 3 "could not hide dedicated Chrome process $pid"
  IFS=: read -r process_visible process_frontmost windows_offscreen window_count <<<"$observed"
  case "$window_count" in
    ''|*[!0-9]*) die 3 "dedicated Chrome returned an invalid window count" ;;
  esac
  [ "$process_visible" = "false" ] &&
    [ "$process_frontmost" = "false" ] ||
    die 3 "dedicated Chrome failed visibility contract (visible:frontmost:offscreen=$observed)"
  WINDOW_COUNT="$window_count"
  WINDOWS_OFFSCREEN="$windows_offscreen"
}

reused=false
pid=""
gatekeeper_assessed_now=0
GATEKEEPER_ASSESSED=0
DYNAMIC_CODE_VERIFIED=0
if cdp_ready; then
  [ "$FRESH" -eq 0 ] || die 5 "--fresh requested but the owned supervisor is already running"
  pid="$(single_listener_pid)"
  verify_owned_listener "$pid"
  owned_pid_verified=1
  reused=true
elif [ -n "$(listener_pids)" ]; then
  die 5 "port $PORT is occupied by a non-responsive or foreign listener"
else
  if [ "$HOST_PLATFORM" = "linux" ]; then
    case "${DISPLAY:-}" in
      :[0-9]|:[0-9][0-9]|:[0-9][0-9][0-9]) ;;
      *)
        die 3 "Linux hidden-headful launch requires DISPLAY (start oracle-xvfb-host / Xvfb first)"
        ;;
    esac
    # True headless is Cloudflare-blocked. Hidden-headful under Xvfb only.
    nohup "$LINUX_CHROME_LAUNCHER" \
      --remote-debugging-address=127.0.0.1 \
      --remote-debugging-port="$PORT" \
      --user-data-dir="$PROFILE_ROOT" \
      --profile-directory="$PROFILE_DIR" \
      --no-first-run \
      --no-default-browser-check \
      --disable-background-mode \
      --disable-dev-shm-usage \
      --window-position=-32000,-32000 \
      --window-size=1280,900 \
      about:blank >/dev/null 2>&1 &
  elif [ "$HOST_PLATFORM" = "darwin" ]; then
    if [ "$ATTESTATION_ENABLED" -eq 1 ]; then
      assess_chrome_bundle
      gatekeeper_assessed_now=1
    fi
    "$OPEN_BIN" -n -g -a "$CHROME_APP_PATH" --args \
      --remote-debugging-address=127.0.0.1 \
      --remote-debugging-port="$PORT" \
      --user-data-dir="$PROFILE_ROOT" \
      --profile-directory="$PROFILE_DIR" \
      --no-first-run \
      --no-default-browser-check \
      --disable-background-mode \
      --window-position=-32000,-32000 \
      --window-size=1280,900 \
      about:blank >/dev/null
  else
    die 3 "hidden-headful supervisor unsupported on this host platform"
  fi

  waited=0
  until cdp_ready; do
    [ "$waited" -lt "$WAIT_SECONDS" ] ||
      die 3 "CDP did not become reachable on loopback port $PORT"
    "$SLEEP_BIN" 1
    waited=$((waited + 1))
  done
  pid="$(single_listener_pid)"
  verify_owned_listener "$pid"
  owned_pid_verified=1
fi

verify_current_listener "$pid"
if [ "$ATTESTATION_ENABLED" -eq 1 ] || [ "${LINUX_ATTESTATION:-0}" -eq 1 ]; then
  ensure_production_attestation "$pid" "$gatekeeper_assessed_now"
fi
hide_browser "$pid"
version_json="$("$CURL_BIN" -q -fsS --max-time 3 "$endpoint_url/json/version")" ||
  die 4 "could not inspect the browser CDP endpoint"
verify_current_listener "$pid"
browser_websocket="$(printf '%s' "$version_json" | "$PYTHON_BIN" -I -c '
import json
import sys
from urllib.parse import urlsplit, urlunsplit

port = int(sys.argv[1])
data = json.load(sys.stdin)
raw = data.get("webSocketDebuggerUrl", "")
parsed = urlsplit(raw)
if parsed.scheme != "ws" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
    raise SystemExit("browser websocket is not loopback")
if parsed.port != port:
    raise SystemExit("browser websocket port mismatch")
print(urlunsplit(("ws", f"127.0.0.1:{port}", parsed.path, parsed.query, "")))
' "$PORT")" || die 4 "browser endpoint did not expose the expected loopback websocket"
node_environment=(
  /usr/bin/env
  -i
  PATH=/usr/bin:/bin
  LANG=C
  LC_ALL=C
)
if [ "$TEST_MODE" -eq 1 ]; then
  node_environment+=(
    "FAKE_REQUESTED_URL=${FAKE_REQUESTED_URL:-}"
    "FAKE_NODE_DELAY=${FAKE_NODE_DELAY:-}"
    "FAKE_SWAP_AFTER_TARGET=${FAKE_SWAP_AFTER_TARGET:-}"
    "FAKE_LISTENER_SWAP_STATE=${FAKE_LISTENER_SWAP_STATE:-}"
    "FAKE_TARGET_ID=${FAKE_TARGET_ID:-}"
    "FAKE_TARGET_URL=${FAKE_TARGET_URL:-}"
    "FAKE_BROWSER_PID=${FAKE_BROWSER_PID:-}"
  )
fi
target_json="$("${node_environment[@]}" \
  "$NODE_BIN" - "$browser_websocket" "$URL" "$pid" <<'NODE'
const [websocketUrl, url, expectedPidRaw] = process.argv.slice(2);
const expectedPid = Number(expectedPidRaw);
if (!Number.isSafeInteger(expectedPid) || expectedPid <= 1) {
  throw new Error('invalid expected browser PID');
}
const socket = new WebSocket(websocketUrl);
let createdTargetId = null;
let verifiedBrowserPid = null;
const allowedMethods = new Set([
  'SystemInfo.getProcessInfo',
  'Target.createTarget',
  'Target.getTargetInfo',
]);
const send = (id, method, params = undefined) => {
  if (!allowedMethods.has(method)) {
    throw new Error(`CDP method is not allowed in launch-only mode: ${method}`);
  }
  const message = { id, method };
  if (params !== undefined) message.params = params;
  socket.send(JSON.stringify(message));
};
const timer = setTimeout(() => {
  console.error('browser process binding or target creation timed out');
  socket.close();
  process.exitCode = 1;
}, 10000);

socket.addEventListener('open', () => {
  send(1, 'SystemInfo.getProcessInfo');
});
socket.addEventListener('message', (event) => {
  const message = JSON.parse(String(event.data));
  if (message.id === 1) {
    const browsers = message.result?.processInfo?.filter(
      (process) => process.type === 'browser',
    );
    if (
      message.error ||
      !Array.isArray(browsers) ||
      browsers.length !== 1 ||
      browsers[0].id !== expectedPid
    ) {
      clearTimeout(timer);
      console.error(message.error?.message || 'CDP browser PID did not match the verified listener');
      socket.close();
      process.exitCode = 1;
      return;
    }
    verifiedBrowserPid = browsers[0].id;
    send(2, 'Target.createTarget', {
      url,
      background: true,
      newWindow: false,
    });
    return;
  }
  if (message.id === 2) {
    if (message.error || !message.result?.targetId) {
      clearTimeout(timer);
      console.error(message.error?.message || 'Target.createTarget returned no targetId');
      socket.close();
      process.exitCode = 1;
      return;
    }
    createdTargetId = message.result.targetId;
    send(3, 'Target.getTargetInfo', { targetId: createdTargetId });
    return;
  }
  if (message.id !== 3) return;
  clearTimeout(timer);
  const target = message.result?.targetInfo;
  if (message.error || !target || target.targetId !== createdTargetId) {
    console.error(message.error?.message || 'Target.getTargetInfo did not match the created target');
    socket.close();
    process.exitCode = 1;
    return;
  }
  console.log(JSON.stringify({
    id: target.targetId,
    type: target.type,
    url: target.url,
    title: target.title,
    browser_pid: verifiedBrowserPid,
  }));
  socket.close();
});
socket.addEventListener('error', () => {
  clearTimeout(timer);
  socket.close();
  process.exitCode = 1;
});
NODE
)" || die 4 "could not create an exact background ChatGPT target"
target_id="$(printf '%s' "$target_json" | "$PYTHON_BIN" -I -c '
import json
import sys

expected_url = sys.argv[1]
expected_pid = int(sys.argv[2])
try:
    target = json.load(sys.stdin)
except Exception as exc:
    raise SystemExit(f"invalid target JSON: {exc}")
target_id = target.get("id")
target_type = target.get("type")
target_url = target.get("url", "")
browser_pid = target.get("browser_pid")
if not isinstance(target_id, str) or not target_id:
    raise SystemExit("target has no id")
if target_type != "page":
    raise SystemExit("target is not a page")
if target_url != expected_url:
    raise SystemExit("target URL does not equal the requested normalized URL")
if browser_pid != expected_pid:
    raise SystemExit("target was not created by the verified listener process")
print(target_id)
' "$URL" "$pid")" || die 4 "new target did not satisfy the ChatGPT target contract"
verify_current_listener "$pid"
hide_browser "$pid"

receipt_json="$("$PYTHON_BIN" -I - "$RECEIPT_PATH" "$pid" "$PORT" "$PROFILE_ROOT" "$PROFILE_DIR" "$target_id" "$URL" "$reused" "$NO_SUBMIT_SMOKE" "$TEST_MODE" "$WINDOW_COUNT" "$WINDOWS_OFFSCREEN" "$GATEKEEPER_ASSESSED" "$DYNAMIC_CODE_VERIFIED" "$ATTESTATION_TEST_MODE" <<'PY'
import datetime
import json
import os
import sys
import tempfile

(
    receipt_path,
    pid,
    port,
    profile_root,
    profile_directory,
    target_id,
    target_url,
    reused,
    no_submit_smoke,
    test_mode,
    window_count,
    windows_offscreen,
    gatekeeper_assessed,
    dynamic_code_verified,
    attestation_test_mode,
) = sys.argv[1:]
is_test = test_mode == "1"
attestation_was_simulated = attestation_test_mode == "1"
window_count_value = int(window_count)
gatekeeper_was_assessed = gatekeeper_assessed == "1"
dynamic_code_was_verified = dynamic_code_verified == "1"
receipt = {
    "schema": (
        "oracle-subagent.browser-test.v1"
        if is_test
        else "oracle-subagent.browser.v1"
    ),
    "state": "test_ready" if is_test else "ready",
    "evidence_mode": "test" if is_test else "production",
    "production_evidence": not is_test,
    "attestation_simulated": attestation_was_simulated,
    "gatekeeper_assessed": gatekeeper_was_assessed and not is_test,
    "dynamic_code_verified": dynamic_code_was_verified and not is_test,
    "chrome_signature_verified": (
        gatekeeper_was_assessed
        and dynamic_code_was_verified
        and not is_test
    ),
    "cdp_browser_pid_verified": True,
    "pid": int(pid),
    "port": int(port),
    "bind": "127.0.0.1",
    "profile_root": profile_root,
    "profile_directory": profile_directory,
    "target_id": target_id,
    "target_url": target_url,
    "target_observed": True,
    "background_requested": True,
    "reused": reused == "true",
    "visibility": "hidden-headful",
    "visibility_verified": True,
    "process_visible": False,
    "process_frontmost": False,
    "window_count": window_count_value,
    "windows_offscreen": (
        windows_offscreen == "true"
        if window_count_value > 0
        else None
    ),
    "submit_performed": False,
    "no_submit_smoke": no_submit_smoke == "1",
    "observed_at": datetime.datetime.now(datetime.timezone.utc)
    .replace(microsecond=0)
    .isoformat()
    .replace("+00:00", "Z"),
}
encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
parent = os.path.dirname(receipt_path)
fd, temporary_path = tempfile.mkstemp(prefix=".browser.", suffix=".json", dir=parent)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(encoded + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary_path, receipt_path)
except BaseException:
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        os.unlink(temporary_path)
    except FileNotFoundError:
        pass
    raise
print(encoded)
PY
)"

if [ "$JSON_OUTPUT" -eq 1 ]; then
  printf '%s\n' "$receipt_json"
else
  printf '%s\n' "$target_id"
fi
