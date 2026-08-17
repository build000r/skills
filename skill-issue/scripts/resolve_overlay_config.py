#!/usr/bin/env python3
"""Resolve a section of the matched client overlay into environment variables.

This is the runtime bridge from per-project overlay config to CLI tools that
read their settings from the environment. Given the current working directory,
it finds the best-matching client overlay (the same selection logic as
`manage_overlays.py match`), reads `client.context.<section>` (or a flattened
top-level `<section>`, for already-generated context.yaml files), and emits
shell `export` lines named `<PREFIX><KEY>` (KEY uppercased), or JSON.

It is generic: any tool that reads env vars can have a per-project config
section. The motivating consumer is the `oracle` CLI and the
`deep-research-prompt` skill's CDP helpers, whose env knobs map 1:1 from
`oracle` block keys:

    oracle:
      cdp_host: 127.0.0.1            ->  ORACLE_CDP_HOST
      cdp_port: 9222                 ->  ORACLE_CDP_PORT
      chatgpt_url_match: g-p-abc123  ->  ORACLE_CHATGPT_URL_MATCH
      chatgpt_target_id: ""          ->  ORACLE_CHATGPT_TARGET_ID
      browser_profile_dir: ~/.oracle/browser-profile  -> ORACLE_BROWSER_PROFILE_DIR
      default_engine: browser        ->  ORACLE_DEFAULT_ENGINE
      default_model: gpt-5.4-pro     ->  ORACLE_DEFAULT_MODEL
      deep_research_default: true    ->  ORACLE_DEEP_RESEARCH_DEFAULT
      slug_prefix: skills            ->  ORACLE_SLUG_PREFIX

Designed to be eval-safe and a silent no-op when no overlay or section is
present, so callers can unconditionally do:

    eval "$(resolve_overlay_config.py --section oracle --format env)"

and fall back to their own defaults if nothing was emitted. Pass --require to
turn a missing section into a non-zero exit instead.

Usage:
    resolve_overlay_config.py --section SECTION [--cwd DIR] [--format env|json]
                              [--prefix PREFIX] [--require] [--verbose]

`~` and `$VAR` references in scalar values are expanded. Non-scalar values
(nested mappings/lists) are skipped in env output and reported on stderr with
--verbose; use --format json to read them structurally.

Runtime floor: **Python 3.9**. This module is invoked by shell `eval` from
whatever `python3` is on a consumer's PATH -- on macOS that is `/usr/bin/python3`
(3.9.6), and `tests/live/oracle-subagent-local-proof.sh` hardcodes exactly that
interpreter. PEP-604 unions (`dict | None`) are evaluated eagerly at function
definition time, so a single one anywhere in this module or in `manage_overlays`
raises TypeError at import and the resolver emits nothing. Keep the
`from __future__ import annotations` import below, and keep `|` unions out of
runtime (non-annotation) positions. See tests/test_resolve_overlay_config_py39.py.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path

import yaml

# Reuse the overlay discovery + matching logic so selection stays identical to
# `manage_overlays.py match`.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from manage_overlays import find_config_roots, find_matches  # noqa: E402


def best_match(cwd: str) -> dict | None:
    """Return the single best-matching overlay across all local config roots.

    Mirrors cmd_match_roots: longest cwd_match wins, then the closest
    (lowest-index) config root, then the first overlay-sourced candidate.
    """
    config_roots = find_config_roots(cwd)
    if not config_roots:
        return None

    matches = []
    for root_index, config_root in enumerate(config_roots):
        for match in find_matches(cwd, config_root):
            match["_root_index"] = root_index
            match["_match_len"] = len(match["expanded"])
            matches.append(match)

    if not matches:
        return None

    best_len = max(m["_match_len"] for m in matches)
    matches = [m for m in matches if m["_match_len"] == best_len]
    best_root = min(m["_root_index"] for m in matches)
    matches = [m for m in matches if m["_root_index"] == best_root]
    # Prefer an overlay-sourced match (source_kind == "overlay") so we read the
    # source-of-truth file rather than a generated context.yaml when both exist.
    matches.sort(key=lambda m: 0 if m.get("source_kind") == "overlay" else 1)
    return matches[0]


def load_section(overlay_path: str, section: str):
    """Read `client.context.<section>`, falling back to a top-level `<section>`.

    overlay.yaml nests runtime config under client.context.*; a generated
    context.yaml flattens those keys to the top level. Support both so the
    resolver works whether it lands on the source overlay or the read-model.
    """
    try:
        data = yaml.safe_load(Path(overlay_path).read_text()) or {}
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    ctx = data.get("client", {}).get("context", {})
    if isinstance(ctx, dict) and section in ctx:
        return ctx[section]
    if section in data:
        return data[section]
    return None


def _expand_scalar(value) -> str:
    return os.path.expanduser(os.path.expandvars(str(value)))


def to_env(section_data: dict, prefix: str):
    """Turn a flat section mapping into (export_lines, skipped_keys)."""
    lines = []
    skipped = []
    for key, value in section_data.items():
        name = f"{prefix}{str(key).upper()}"
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, (str, int, float)):
            rendered = _expand_scalar(value)
        else:
            skipped.append(str(key))
            continue
        lines.append(f"export {name}={shlex.quote(rendered)}")
    return lines, skipped


def default_prefix(section: str) -> str:
    return section.strip().upper().replace("-", "_") + "_"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve a matched overlay config section into env vars or JSON.",
    )
    parser.add_argument("--section", required=True, help="Config section to resolve (e.g. oracle)")
    parser.add_argument("--cwd", default=os.getcwd(), help="Working directory to match (default: cwd)")
    parser.add_argument("--format", choices=("env", "json"), default="env", help="Output format")
    parser.add_argument("--prefix", default=None, help="Env var prefix (default: <SECTION>_)")
    parser.add_argument(
        "--require",
        action="store_true",
        help="Exit non-zero if no overlay matched or the section is missing/empty",
    )
    parser.add_argument("--verbose", action="store_true", help="Diagnostics to stderr")
    args = parser.parse_args()

    prefix = args.prefix if args.prefix is not None else default_prefix(args.section)

    def fail_or_noop(message: str, code: int) -> int:
        if args.verbose:
            print(message, file=sys.stderr)
        if args.require:
            if not args.verbose:
                print(message, file=sys.stderr)
            return code
        if args.format == "json":
            print(json.dumps({"section": args.section, "matched": False, "env": {}}))
        return 0

    match = best_match(args.cwd)
    if match is None:
        return fail_or_noop(f"resolve_overlay_config: no overlay matches cwd {args.cwd}", 3)

    section_data = load_section(match["path"], args.section)
    if section_data is None:
        return fail_or_noop(
            f"resolve_overlay_config: overlay '{match['client_id']}' has no '{args.section}' section",
            4,
        )
    if not isinstance(section_data, dict):
        return fail_or_noop(
            f"resolve_overlay_config: section '{args.section}' is not a mapping",
            5,
        )
    if not section_data:
        return fail_or_noop(
            f"resolve_overlay_config: section '{args.section}' is empty",
            4,
        )

    lines, skipped = to_env(section_data, prefix)
    if args.verbose and skipped:
        print(
            f"resolve_overlay_config: skipped non-scalar keys (use --format json): {', '.join(skipped)}",
            file=sys.stderr,
        )

    if args.format == "json":
        env = {}
        for line in lines:
            # "export NAME=value" -> NAME, value (value already shell-quoted)
            assignment = line[len("export "):]
            name, _, quoted = assignment.partition("=")
            env[name] = shlex.split(quoted)[0] if quoted else ""
        print(json.dumps({
            "section": args.section,
            "matched": True,
            "client_id": match["client_id"],
            "path": match["path"],
            "prefix": prefix,
            "env": env,
            "raw": section_data,
            "skipped": skipped,
        }, indent=2))
    else:
        if args.verbose:
            print(
                f"resolve_overlay_config: {args.section} from overlay '{match['client_id']}' ({match['path']})",
                file=sys.stderr,
            )
        for line in lines:
            print(line)

    return 0


if __name__ == "__main__":
    sys.exit(main())
