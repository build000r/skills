# shellcheck shell=sh
# Fail-closed loader for resolve_overlay_config.py.
#
# Source this, then call overlay_env_load:
#
#     . "<skill-issue>/scripts/overlay_env.sh"
#     overlay_env_load oracle || exit 1
#
# WHY THIS EXISTS
#
# The obvious consumer line is unsafe:
#
#     eval "$(python3 resolve_overlay_config.py --section oracle --format env)"
#
# Command substitution throws away the resolver's exit status: `eval` reports
# the status of the *text it evaluated*, not of the process that produced it.
# Empty text evaluates to 0. So when the resolver dies -- a stack trace, a
# missing dependency, a PEP-604 union under Python 3.9 -- that line returns 0
# with no variables set, and the caller proceeds with its own defaults as though
# no overlay had been configured. `--require` does not help: its non-zero exit
# is discarded by the same substitution. Neither does `set -e`.
#
# Silently running unoverlaid is the dangerous outcome, because the fallback
# defaults are plausible: the wrong CDP port, the wrong ChatGPT account, the
# wrong model. The run appears to work and targets the wrong thing.
#
# This helper separates the two cases that line conflates:
#
#   resolver ABSENT   -> no-op, return 0. skill-issue is an optional dependency;
#                        a consumer without it is expected to use its defaults.
#   resolver PRESENT
#     and it fails    -> return non-zero, set nothing. LOUD.
#     and its output
#     is not exports  -> return non-zero, set nothing. Never eval it.
#
# The output check is an allowlist, not a scan for bad content: every non-empty
# line must be `export NAME=...`. Partial output from a resolver killed mid-write
# fails it, and so does anything that is not an assignment. Text that never
# reaches `eval` cannot execute.

# Locate the resolver. Order mirrors the documented consumer contract.
overlay_env_find_resolver() {
    # bash sets BASH_SOURCE for a sourced file; zsh sets $0 to it. Under a plain
    # POSIX sh, $0 is the shell rather than this file, so the lookup simply
    # falls through to the path candidates below.
    # shellcheck disable=SC2128
    _oe_self="${BASH_SOURCE:-$0}"
    _oe_dir=""
    if [ -n "$_oe_self" ] && [ -f "$_oe_self" ]; then
        _oe_dir="$(CDPATH='' cd -- "$(dirname -- "$_oe_self")" && pwd -P)"
    fi

    for _oe_candidate in \
        "${OVERLAY_ENV_RESOLVER:-}" \
        "${_oe_dir:+$_oe_dir/resolve_overlay_config.py}" \
        "./.claude/skills/skill-issue/scripts/resolve_overlay_config.py" \
        "$HOME/.claude/skills/skill-issue/scripts/resolve_overlay_config.py"
    do
        [ -n "$_oe_candidate" ] || continue
        if [ -f "$_oe_candidate" ]; then
            printf '%s\n' "$_oe_candidate"
            unset _oe_dir _oe_candidate _oe_self
            return 0
        fi
    done
    unset _oe_dir _oe_candidate _oe_self
    return 1
}

# Allowlist the output shape before it can execute: every non-blank line must be
# `export NAME=<anything>` with NAME a valid identifier. Returns 0 if the whole
# text is safe to eval, else 1 with the offender in $_oe_bad_line.
#
# Deliberately implemented with `case` and parameter expansion rather than grep.
# This machine's `grep` is ugrep, whose `-q -v` reports whether the pattern
# matched rather than whether any line failed to match -- the inverse of BSD and
# GNU grep. A safety check that silently inverts depending on which grep is
# installed is not a safety check, and this one is load-bearing enough to owe
# nothing to $PATH.
#
# A value containing a literal newline fails this and is refused rather than
# partially evaluated. Use --format json for structured or multi-line values.
overlay_env_is_pure_exports() {
    _oe_bad_line=""
    # A here-doc keeps the loop in the current shell (a pipeline would subshell
    # it and discard _oe_bad_line).
    while IFS= read -r _oe_line || [ -n "$_oe_line" ]; do
        # Blank or whitespace-only: fine.
        case "$_oe_line" in
            *[!" 	"]*) ;;
            *) continue ;;
        esac
        case "$_oe_line" in
            "export "*) ;;
            *) _oe_bad_line="$_oe_line"; unset _oe_line; return 1 ;;
        esac
        _oe_rest="${_oe_line#export }"
        _oe_name="${_oe_rest%%=*}"
        # No '=' at all, or an empty name.
        if [ "$_oe_name" = "$_oe_rest" ] || [ -z "$_oe_name" ]; then
            _oe_bad_line="$_oe_line"
            unset _oe_line _oe_rest _oe_name
            return 1
        fi
        # NAME must be a plain identifier: no spaces, metacharacters, or digits
        # leading. Anything else means the line is not a simple assignment.
        case "$_oe_name" in
            [0-9]*|*[!A-Za-z0-9_]*)
                _oe_bad_line="$_oe_line"
                unset _oe_line _oe_rest _oe_name
                return 1
                ;;
        esac
    done <<EOF
$1
EOF
    unset _oe_line _oe_rest _oe_name
    return 0
}

overlay_env_load() {
    if [ "$#" -lt 1 ]; then
        printf 'overlay_env_load: usage: overlay_env_load SECTION [resolver args...]\n' >&2
        return 2
    fi
    _oe_section="$1"
    shift

    if ! _oe_resolver="$(overlay_env_find_resolver)"; then
        if [ "${OVERLAY_ENV_REQUIRE:-0}" = "1" ]; then
            printf 'overlay_env_load: resolver not found and OVERLAY_ENV_REQUIRE=1\n' >&2
            unset _oe_section _oe_resolver
            return 1
        fi
        # Optional dependency absent: the documented no-op. The caller's own
        # defaults apply, which is correct -- nothing was ever configured here.
        unset _oe_section _oe_resolver
        return 0
    fi

    # Capture stdout and status separately. This is the whole point: the status
    # must survive to be checked, which it cannot inside eval "$(...)".
    _oe_stderr="$(mktemp -t overlay_env.XXXXXX)" || return 1
    _oe_out="$("${OVERLAY_ENV_PYTHON:-python3}" "$_oe_resolver" \
        --section "$_oe_section" --format env "$@" 2>"$_oe_stderr")"
    _oe_status=$?

    if [ "$_oe_status" -ne 0 ]; then
        printf 'overlay_env_load: resolver FAILED (exit %s) -- refusing to continue unoverlaid.\n' \
            "$_oe_status" >&2
        printf 'overlay_env_load: resolver: %s\n' "$_oe_resolver" >&2
        printf 'overlay_env_load: interpreter: %s\n' \
            "$("${OVERLAY_ENV_PYTHON:-python3}" -V 2>&1)" >&2
        sed 's/^/overlay_env_load: | /' "$_oe_stderr" >&2
        rm -f "$_oe_stderr"
        unset _oe_section _oe_resolver _oe_out _oe_status _oe_stderr
        return 1
    fi
    rm -f "$_oe_stderr"

    if ! overlay_env_is_pure_exports "$_oe_out"; then
        printf 'overlay_env_load: resolver output is not pure export lines -- refusing to eval.\n' >&2
        printf 'overlay_env_load: offending line: %s\n' "$_oe_bad_line" >&2
        unset _oe_section _oe_resolver _oe_out _oe_status _oe_bad_line
        return 1
    fi

    eval "$_oe_out"
    _oe_status=$?
    unset _oe_section _oe_resolver _oe_out _oe_stderr
    return $_oe_status
}
